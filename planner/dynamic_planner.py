"""
[模块] planner/dynamic_planner.py — 动态规划调度器（自研纯 Python，不用 LangGraph）
[职责] LLM 按用户目标动态生成 JSON 任务计划 →（可选人审：修改意见→LLM 重生成）→ 顺序执行
[设计思想] 与静态引擎形成互补：动态引擎面向"未知/多变任务"，以 LLM 编排 + 人可干预换灵活性；
           纯顺序无图结构，不依赖 LangGraph interrupt（执行中断点用 human_input 协议实现）
[关键约定] ★ human_input 是协议不是 Agent：计划步骤中出现 {"agent":"human_input","note":"提问"}
           时，_execute 暂停等人工输入写入 state["human_supplement"] 后继续；
           ★ fact_checker 是引擎内置的回溯协议角色：执行后若 fact_check_passed=False 且
             修订次数未达 core.paths.FACT_CHECK_MAX_RETRIES，自动把"最近的 writer 步骤+本次
             fact_checker 步骤"追加到计划尾部回溯修订（有界循环）；
           动态规划只向 LLM 暴露 registry.get_agent_list(engine="dynamic")（自动排除 human_review）
[被谁调用] main.py（auto_run / human_review_plan_run）、web_gui/services/task_manager.py
[修改注意] LLM 调用必须走 get_llm（保日志与统计）；parse_plan 已容错 markdown 代码块，
           若调整 LLM 输出契约需同步改 prompt 与解析
"""
import json
import re
import time
import traceback

from agent_registry.registry import registry
from llm_config import get_llm
from planner.plan_renderer import render_plan
from core.logger import get_logger
from core.paths import FACT_CHECK_MAX_RETRIES

logger = get_logger("dynamic_planner")


class DynamicPlanner:
    @staticmethod
    def generate_raw_plan(user_goal: str, previous_plan=None, user_feedback: str = "", tier: str = "standard") -> str:
        """
        生成（或根据修改意见重新生成）任务计划。
        :param previous_plan: 上一版计划（重新生成时传入）
        :param user_feedback: 人工修改意见（非空时触发重新生成）
        :param tier: 模型档位（默认 standard；任务指定档位时传 state.model_tier 决策结果）
        """
        # 只向 LLM 暴露动态引擎可用的 Agent
        agent_list = registry.get_agent_list(engine="dynamic")
        agent_text = "\n".join([f"- {x['name']}: {x['desc']}" for x in agent_list])

        if previous_plan is None:
            prompt = f"""
你是动态任务规划导演。
可用Agent角色清单：
{agent_text}

特殊节点（可选用）：如需在流程中途请用户补充信息/修改意见，在数组中插入 {{"agent":"human_input","note":"向用户提问的内容"}}。

用户目标：{user_goal}
输出任务执行计划：输出JSON数组。
数组每一项：{{"agent":"角色名", "note":"该步骤简短说明"}}
只输出JSON，禁止额外解释。
"""
        else:
            prompt = f"""
你是动态任务规划导演。
可用Agent角色清单：
{agent_text}

特殊节点（可选用）：如需在流程中途请用户补充信息/修改意见，在数组中插入 {{"agent":"human_input","note":"向用户提问的内容"}}。

用户目标：{user_goal}
上一版任务计划：
{json.dumps(previous_plan, ensure_ascii=False, indent=2)}

用户对计划的修改意见：{user_feedback}
请根据修改意见重新生成任务计划：输出JSON数组。
数组每一项：{{"agent":"角色名", "note":"该步骤简短说明"}}
只输出JSON，禁止额外解释。
"""
        logger.info(f"调用LLM生成任务计划：user_goal={user_goal}, 是否重新生成={previous_plan is not None}")
        resp = get_llm(tier).invoke(prompt)
        return resp.content.strip()

    @staticmethod
    def parse_plan(json_str: str):
        """解析 LLM 输出为 JSON 数组，容错处理 markdown 代码块与首尾杂文本"""
        text = json_str.strip()
        # 提取 ```json ... ``` 代码块
        code_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if code_block:
            text = code_block.group(1).strip()
        # 提取第一个 [ 到最后一个 ]
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end != -1 and end > start:
            text = text[start:end + 1]
        return json.loads(text)

    @staticmethod
    def auto_run(user_goal: str, init_state: dict):
        """全自动模式：生成计划直接执行（规划用档位=任务指定 model_tier，缺省 standard）"""
        tier = (init_state or {}).get("model_tier") or "standard"
        raw = DynamicPlanner.generate_raw_plan(user_goal, tier=tier)
        plan = DynamicPlanner.parse_plan(raw)
        print(render_plan(plan))
        logger.info(f"动态规划-全自动模式启动：目标={user_goal}, 计划={plan}")
        return DynamicPlanner._execute(plan, init_state)

    @staticmethod
    def human_review_plan_run(user_goal: str, init_state: dict):
        """人在回路规划模式：先出方案，人提修改意见，返回 LLM 重新生成计划后执行（规划档位同 auto_run）"""
        tier = (init_state or {}).get("model_tier") or "standard"
        raw = DynamicPlanner.generate_raw_plan(user_goal, tier=tier)
        plan = DynamicPlanner.parse_plan(raw)
        print(render_plan(plan))

        print("\n是否需要修改计划？")
        user_feedback = input("输入修改意见（直接回车=按当前计划执行）：").strip()
        if user_feedback:
            print("\n→ 已收到修改意见，返回 LLM 重新生成计划...")
            raw = DynamicPlanner.generate_raw_plan(user_goal, previous_plan=plan, user_feedback=user_feedback, tier=tier)
            plan = DynamicPlanner.parse_plan(raw)
            print(render_plan(plan))
            logger.info(f"人工修改意见已反馈LLM重新生成计划：{user_feedback}")
        return DynamicPlanner._execute(plan, init_state)

    @staticmethod
    def _execute(plan, state: dict, human_input_fn=None):
        """
        顺序执行计划：每个步骤调用对应 Agent，增量合并更新全局状态。
        :param human_input_fn: 人工断点输入回调（callable(question)->str）；默认用 input()。
                               GUI 等场景可注入自定义回调实现异步输入。
        """
        if human_input_fn is None:
            human_input_fn = input
        current_state = state.copy()
        last_writer_step = None  # 最近一次 writer 步骤（事实审核回溯修订目标）
        for step in plan:
            agent_name = step["agent"]
            note = step.get("note", "")

            # 人工断点节点：流程中途暂停，等待用户补充信息
            if agent_name == "human_input":
                print(f"\n⏸ 人工输入断点：{note}")
                user_input = human_input_fn(note)
                current_state["human_supplement"] = user_input
                logger.info(f"人工输入断点：{note} → {user_input}")
                continue

            if agent_name == "writer":
                last_writer_step = step

            print(f"\n▶ 执行步骤：{note}，调用角色【{agent_name}】")
            logger.info(f"调用Agent: {agent_name}, 步骤说明: {note}")
            run_func = registry.get_run_func(agent_name)
            t0 = time.perf_counter()
            try:
                update = run_func(current_state)
            except Exception as e:
                # 卡住/报错不再静默：记录异常堆栈并抛出，由上层（main/task_manager）转为失败
                logger.error(f"Agent【{agent_name}】执行异常: {e}\n{traceback.format_exc()}")
                raise RuntimeError(f"步骤【{agent_name}】（{note}）执行失败：{e}") from e
            cost = time.perf_counter() - t0
            current_state.update(update)
            logger.info(f"Agent完成: {agent_name}, 耗时 {cost:.1f}s, 更新字段: {list(update.keys())}")

            # 事实审核有界循环（引擎内置回溯协议）：不通过且未达上限 → 回溯最近 writer 修订
            if agent_name == "fact_checker":
                passed = current_state.get("fact_check_passed", True)
                count = current_state.get("fact_check_count", 0)
                if not passed and count < FACT_CHECK_MAX_RETRIES and last_writer_step is not None:
                    logger.warning(
                        f"事实审核第 {count} 次未通过，回溯 writer 修订（上限 {FACT_CHECK_MAX_RETRIES}）")
                    print(f"\n↩ 事实审核未通过，回溯【writer】修订（第 {count}/{FACT_CHECK_MAX_RETRIES} 次）")
                    plan.append(last_writer_step)
                    plan.append(step)
                elif not passed and count >= FACT_CHECK_MAX_RETRIES:
                    logger.warning(f"事实审核已达修订上限 {FACT_CHECK_MAX_RETRIES} 次，强制通过")
                    print(f"\n⚠ 事实审核已达修订上限 {FACT_CHECK_MAX_RETRIES} 次，强制通过")
        # 把实际执行的计划（含回溯追加步骤）写入 state，供过程封存/任务回放使用
        current_state["exec_plan"] = plan
        return current_state
