"""
[模块] web_gui/services/task_manager.py — 任务管理器（状态机 + 后台线程 + 事件流）
[职责] 管理 Web 任务的完整生命周期：创建→规划→（人审/断点等待）→执行→完成/失败/取消
[设计思想] 不修改任何核心代码，仅 import 核心模块；LLM 阻塞调用放后台线程，
           前端通过轮询事件流感知进度（避免 Flask 阻塞）；两引擎人在回路统一为 waiting_input
[关键约定] 状态机：created → planning → waiting_feedback(动态人审) / executing
           → waiting_input(动态 human_input 断点 / 静态 interrupt 断点) → done/failed/cancelled；
           恢复统一入口 resume_input() 按模式分发（static→interrupt，dynamic→续跑）；
           动态断点进度存 task._exec_progress={index,state}，供 resume_dynamic 从下一步续跑
[被谁调用] web_gui/app.py（唯一外部调用方）
[修改注意] 核心执行逻辑在 _execute_plan（含 human_input 断点识别），改执行语义先看这里；
           事件类型（plan/step_start/agent_done/waiting/...）与前端 app.js 有约定
"""
import threading
import time
import uuid
import os
from datetime import datetime

from agent_registry.registry import registry
from planner.dynamic_planner import DynamicPlanner
from planner.static_workflow_director import StaticWorkflowDirector
from langgraph.types import Command
from memory.memory_registry import inject_value_profiles
from core.domain_config import default_profiles_for


def make_init_state(topic: str, profiles=None, domain: str = None, model_tier: str = None) -> dict:
    """构造初始状态并注入价值观框架。
    优先级：显式 profiles > 域默认（_domain.md）> 关键词自动匹配 > general 兜底；
    domain=主题域（None=通用层），写入 state 供全程 Agent/Skill 读取（域是任务参数，非全局变量）；
    model_tier=模型档位（router/standard/reasoning，空=按难度自动映射，见 llm_config.TIER_MAP）；
    profiles 同时写入 state["profiles"]（显式指定来源，供 memory_advisor 等后续选择逻辑读取，防覆盖）"""
    state = {
        "topic": topic,
        "task_level": None,
        "research_material": None,
        "human_supplement": None,
        "final_article": None,
        "domain": domain,
        "model_tier": (model_tier or "").strip() or None,
        "profiles": list(profiles or []),  # 显式框架名清单（空=自动匹配；写入 state 防后续覆盖）
    }
    if not profiles:
        profiles = default_profiles_for(domain)  # 域默认价值观（未显式选择时生效）
    return inject_value_profiles(state, profiles)


def graph_from_plan(plan) -> dict:
    """把动态计划转成流程图数据结构 {nodes, edges}"""
    nodes = [{"id": step["agent"], "note": step.get("note", "")} for step in plan]
    edges = [{"source": plan[i]["agent"], "target": plan[i + 1]["agent"]} for i in range(len(plan) - 1)]
    return {"nodes": nodes, "edges": edges}


def graph_from_langgraph(graph) -> dict:
    """从 LangGraph 编译图提取拓扑 {nodes, edges}"""
    g = graph.get_graph()
    nodes = [{"id": n} for n in g.nodes]
    edges = [{"source": e.source, "target": e.target} for e in g.edges]
    return {"nodes": nodes, "edges": edges}


class Task:
    def __init__(self, task_id: str, topic: str, mode: str, flow_name: str = "", profiles: list = None,
                 domain: str = None, timeout: float = None, model_tier: str = None, items: list = None,
                 raw_topic: str = "", write_mode: str = "auto"):
        self.id = task_id
        self.topic = topic            # 展示名（任务卡片/日志用）
        self.raw_topic = raw_topic    # import 模式：用户原始主题输入（空=collector 自动提炼），与展示名分离
        self.write_mode = write_mode  # import 模式：auto=AI自主决策 / new=强制新建 / merge=尽量合并
        self.mode = mode          # auto / human_review / static / import
        self.flow_name = flow_name
        self.profiles = profiles or []  # 显式指定的价值观框架（空=自动匹配）
        self.domain = domain      # 主题域（None=通用层）；任务创建时快照，运行中禁止切换
        self.timeout = timeout    # LLM 超时（秒，None=用 .env 默认）；任务启动时 apply_llm_config
        self.model_tier = model_tier  # 模型档位（router/standard/reasoning；None=按难度自动映射）
        self.items = items or []  # import 模式：来源列表 [{type,name,content}]
        self.status = "created"   # created/planning/waiting_feedback/executing/waiting_input/done/failed/cancelled
        self.events = []
        self.graph = {"nodes": [], "edges": []}
        self.plan = None
        self.final_state = None
        self.error = None
        self.created_at = datetime.now().strftime("%H:%M:%S")
        self._cancel = False
        self._thread = None
        # 静态流程断点恢复句柄
        self._graph = None
        self._config = None
        # 动态断点执行进度（human_input 节点暂停时记录）
        self._exec_progress = None
        # 任务级 LLM 用量统计（线程入口 reset 后绑定；done 汇总）
        self._stats = None

    def add_event(self, type_: str, content: str):
        self.events.append({
            "ts": datetime.now().strftime("%H:%M:%S"),
            "type": type_,
            "content": content,
        })

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "topic": self.topic,
            "mode": self.mode,
            "flow_name": self.flow_name,
            "domain": self.domain,
            "model_tier": self.model_tier,
            "timeout": self.timeout,
            "status": self.status,
            "events": self.events,
            "graph": self.graph,
            "plan": self.plan,
            "final_state": self.final_state,
            "error": self.error,
            "created_at": self.created_at,
        }


class TaskManager:
    def __init__(self):
        self.tasks = {}

    def create(self, topic: str, mode: str, flow_name: str = "", profiles: list = None,
               domain: str = None, timeout: float = None, model_tier: str = None, items: list = None,
               raw_topic: str = "", write_mode: str = "auto") -> Task:
        task = Task(uuid.uuid4().hex[:8], topic, mode, flow_name, profiles, domain, timeout, model_tier, items,
                    raw_topic, write_mode)
        self.tasks[task.id] = task
        return task

    def start(self, task: Task):
        task.status = "running"
        task.add_event("info", f"任务启动：主题「{task.topic}」，模式={task.mode}")
        if task.timeout:
            from llm_config import configure_llms
            try:
                configure_llms(timeout=float(task.timeout))
                task.add_event("info", f"LLM 超时已设为 {task.timeout} 秒")
            except Exception as e:
                task.add_event("info", f"（应用 LLM 超时配置失败，沿用默认：{e}）")
        task._thread = threading.Thread(target=self._dispatch, args=(task,), daemon=True)
        task._thread.start()

    def get(self, task_id: str) -> Task:
        return self.tasks.get(task_id)

    def cancel(self, task_id: str):
        task = self.tasks.get(task_id)
        if task and task.status in ("planning", "executing", "waiting_feedback"):
            task._cancel = True
            task.add_event("info", "收到取消请求，将在当前步骤结束后停止")
            return True
        return False

    # ---------- 执行分发 ----------
    def _dispatch(self, task: Task):
        try:
            from llm_config import reset_llm_stats
            task._stats = reset_llm_stats()  # 任务线程入口重置用量统计（绑定到任务，done 汇总不依赖线程）
            if task.mode == "import":
                self._run_import(task)
            elif task.mode == "static":
                self._run_static(task)
            elif task.mode == "human_review":
                self._run_human_review(task)
            else:
                self._run_auto(task)
        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            task.add_event("error", f"任务失败：{e}")

    # ---------- 资料入库任务（mode=import，走左侧任务区进度展示） ----------
    @staticmethod
    def _import_graph(items: list) -> dict:
        """资料入库流程图：每个来源一个节点，线性串联（节点 id 与事件【来源N】匹配着色）"""
        nodes = [{"id": f"来源{i + 1}", "note": str(it.get("name") or "直接文本")[:10]}
                 for i, it in enumerate(items)]
        edges = [{"source": f"来源{i + 1}", "target": f"来源{i + 2}"} for i in range(len(items) - 1)]
        return {"nodes": nodes, "edges": edges}

    def _run_import(self, task: Task):
        """资料入库任务：逐条来源经 collector 整理入库（单条失败隔离，记 error 继续下一条）；
        全部完成 status=done，仅统计用量（不触发研究文章/归档/记忆沉淀）"""
        from agent_registry.agents.collector_agent import run as collector_run
        task.status = "executing"
        items = task.items
        task.graph = self._import_graph(items)
        task.add_event("info", f"资料入库任务启动：{len(items)} 个来源（主题留空=自动提炼，同义词自动归一）")
        for i, it in enumerate(items, 1):
            if task._cancel:
                task.status = "cancelled"
                task.add_event("info", "资料入库已取消")
                return
            content = str(it.get("content") or "").strip()
            if not content:
                continue
            itype = it.get("type", "text")
            label = str(it.get("name") or "直接文本")[:36]
            source = content if itype == "url" else (f"【{label}】\n{content}" if label != "直接文本" else content)
            node_id = f"来源{i}"
            task.add_event("step_start", f"▶【{node_id}】处理中：{label}")
            try:
                state = {"topic": task.raw_topic, "domain": task.domain, "source": source, "human_supplement": source,
                     "write_mode": task.write_mode}
                result = collector_run(state)
                msg = str(result.get("collect_result", "")).split("\n")[0][:80]
                task.add_event("agent_done", f"✅【{node_id}】入库完成：{msg}")
            except Exception as e:
                task.add_event("error", f"❌【{node_id}】处理失败：{e}")
        if task.status != "cancelled":
            task.status = "done"
            task.add_event("done", f"✅ 资料入库完成：{len(items)} 个来源处理完毕（详见上方日志）")
            self._log_usage(task)

    # ---------- 动态全自动 ----------
    def _run_auto(self, task: Task):
        plan = self._plan_and_emit(task)
        self._execute_plan(task, plan)  # 内部处理 done / 断点 / cancelled

    # ---------- 动态人审 ----------
    def _run_human_review(self, task: Task):
        plan = self._plan_and_emit(task)
        task.status = "waiting_feedback"
        task.add_event("waiting", "等待人工修改意见：可提交修改意见重新生成计划，或按当前计划执行")

    def feedback_plan(self, task: Task, content: str):
        """人审反馈：根据修改意见重新生成计划"""
        if task.status != "waiting_feedback":
            return False, "当前状态不允许计划反馈"
        task.add_event("info", f"收到修改意见：{content}")
        raw = DynamicPlanner.generate_raw_plan(task.topic, previous_plan=task.plan, user_feedback=content)
        new_plan = DynamicPlanner.parse_plan(raw)
        task.plan = new_plan
        task.graph = graph_from_plan(new_plan)
        task.add_event("plan", "已根据修改意见重新生成计划")
        return True, "计划已重新生成"

    def start_execute(self, task: Task):
        """人审模式：按当前计划开始执行"""
        if task.status != "waiting_feedback" or not task.plan:
            return False, "无有效计划"
        task.status = "executing"
        task.add_event("info", "按当前计划开始执行")
        task._thread = threading.Thread(target=self._execute_then_done, args=(task,), daemon=True)
        task._thread.start()
        return True, "开始执行"

    def _execute_then_done(self, task: Task):
        try:
            from llm_config import set_llm_stats
            set_llm_stats(getattr(task, "_stats", None) or reset_llm_stats())  # 人审执行线程续接原任务统计
            self._execute_plan(task, task.plan)  # 内部处理 done / 断点 / cancelled
        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            task.add_event("error", f"任务失败：{e}")

    # ---------- 静态流程 ----------
    @staticmethod
    def _static_exec_plan(graph) -> list:
        """静态流程执行计划：从 LangGraph 图节点提取节点顺序（add_node 顺序=流程逻辑顺序），
        转成与动态引擎一致的 [{agent,note}] 格式，供过程封存/档案展示。
        节点集合为 dict 时保序、set 时无序（仅展示用途，测试中允许）"""
        try:
            dg = graph.get_graph()
            nodes = list(getattr(dg, "nodes", {}) or {})
        except Exception:
            return []
        skip = {"START", "END", "__start__", "__end__"}
        return [{"agent": n, "note": "静态流程节点"} for n in nodes if n not in skip]

    def _run_static(self, task: Task):
        task.status = "executing"
        task.add_event("info", f"静态流程启动：flow={task.flow_name}")
        graph, config = StaticWorkflowDirector.run_workflow(
            task.topic, flow_name=task.flow_name,
            init_state=make_init_state(task.topic, task.profiles, task.domain, task.model_tier),
        )
        task._graph, task._config = graph, config
        task.graph = graph_from_langgraph(graph)

        snapshot = graph.get_state(config)
        pending = list(getattr(snapshot, "next", []) or [])
        if pending:
            task.status = "waiting_input"
            task.add_event("waiting", f"流程暂停于人工审阅断点（下一节点：{pending}），等待人工输入")
        else:
            task.status = "done"
            final = dict(graph.get_state(config).values)
            final["exec_plan"] = self._static_exec_plan(graph)  # 静态执行计划入档（与动态引擎对齐）
            task.final_state = final
            task.add_event("done", "✅ 静态流程执行完成")
            self._archive_done(task)

    def resume_static(self, task: Task, content: str):
        """静态断点恢复"""
        if task.status != "waiting_input":
            return False, "当前状态不允许恢复"
        task.status = "executing"
        task.add_event("info", f"收到人工输入：{content}")
        from llm_config import set_llm_stats
        set_llm_stats(getattr(task, "_stats", None) or reset_llm_stats())  # 恢复线程续接原任务统计
        graph, config = task._graph, task._config
        graph.invoke(Command(resume=content), config=config)
        final = dict(graph.get_state(config).values)
        final["exec_plan"] = self._static_exec_plan(graph)  # 静态执行计划入档
        task.final_state = final
        task.status = "done"
        task.add_event("done", "✅ 静态流程执行完成")
        self._archive_done(task)
        return True, "恢复执行完成"

    def resume_dynamic(self, task: Task, content: str):
        """动态断点恢复：从 human_input 断点步骤之后继续执行"""
        if task.status != "waiting_input" or not task._exec_progress:
            return False, "当前状态不允许恢复（无动态断点进度）"
        progress = task._exec_progress
        state = progress["state"]
        state["human_supplement"] = content
        task.add_event("info", f"收到人工输入：{content}")
        task.status = "executing"
        from llm_config import set_llm_stats
        set_llm_stats(getattr(task, "_stats", None) or reset_llm_stats())  # 恢复线程续接原任务统计
        self._execute_plan(task, task.plan, start_index=progress["index"] + 1, state=state)
        return True, "恢复执行完成"

    def resume_input(self, task: Task, content: str):
        """统一断点恢复入口：按任务模式分发（静态 interrupt / 动态 human_input）"""
        if task.mode == "static":
            return self.resume_static(task, content)
        return self.resume_dynamic(task, content)

    # ---------- 过程封存 ----------
    def _archive_done(self, task: Task):
        """任务正常完成时：最终文章保存到 output（干净交付区）+ 过程封存档案 + 沉淀长期记忆。
        三者失败均仅提示不阻断任务结果；静态/动态全部 done 路径统一走这里"""
        meta = {
            "engine": "static" if task.mode == "static" else "dynamic",
            "mode": task.mode,
            "flow_name": task.flow_name,
            "domain": task.domain,
        }
        # 1) 最终文章 → output/（与 CLI main.py 对齐；GUI 跑完也能直接拿到干净成稿）
        try:
            from tools.document_output import save_article
            article = (task.final_state or {}).get("final_article", "")
            topic = (task.final_state or {}).get("topic") or task.topic
            if article:
                fpath = save_article(article, topic, domain=task.domain)
                task.add_event("info", f"📄 文章已保存：{os.path.basename(fpath)}")
        except Exception as e:
            task.add_event("info", f"（文章保存失败，不影响任务结果：{e}）")
        # 2) 研究过程 → archives/
        try:
            from tools.archive_process import archive_research
            path = archive_research(task.final_state or {}, meta, domain=task.domain)
            if path:
                task.add_event("info", f"📦 研究过程已封存：{os.path.basename(path)}")
        except Exception as e:
            task.add_event("info", f"（过程封存失败，不影响任务结果：{e}）")
        # 3) 长期记忆 → task_history.md
        try:
            from memory.memory_registry import sediment_task_memory
            line = sediment_task_memory(task.final_state or {}, meta)
            if line:
                task.add_event("info", "🧠 长期记忆已沉淀一条任务记录")
        except Exception as e:
            task.add_event("info", f"（长期记忆沉淀失败，不影响任务结果：{e}）")
        # 4) 用量统计（轮次/tokens/费用估算）→ 简单日志 + GUI 事件
        self._log_usage(task)

    def _log_usage(self, task: Task):
        """任务用量汇总：对话轮次/上传下载 tokens/费用估算（按模型分桶计价），写简单日志并在 GUI 完成事件展示"""
        try:
            from llm_config import estimate_cost, cost_by_model
            stats = getattr(task, "_stats", None) or {}
            calls = stats.get("calls", 0)
            if not calls:
                return
            cost = estimate_cost(stats)
            summary = (f"对话轮次 {calls} 次 · 上传 {stats['input_tokens']} tokens · "
                       f"下载 {stats['output_tokens']} tokens · 费用估算 ¥{cost:.4f}")
            detail = "；".join(f"{m} ¥{c:.4f}" for m, c in cost_by_model(stats).items())
            if detail:
                summary += f"（按模型：{detail}）"
            from core.logger import get_logger
            get_logger().info(
                f"任务统计: 主题={task.topic} 域={task.domain or 'general'} 模式={task.mode} {summary}")
            task.add_event("info", f"📊 {summary}")
        except Exception as e:
            task.add_event("info", f"（用量统计失败，不影响任务结果：{e}）")

    # ---------- 公共执行器 ----------
    def _plan_and_emit(self, task: Task) -> list:
        task.status = "planning"
        task.add_event("info", "LLM 正在生成任务计划...")
        raw = DynamicPlanner.generate_raw_plan(task.topic)
        plan = DynamicPlanner.parse_plan(raw)
        task.plan = plan
        task.graph = graph_from_plan(plan)
        steps = "; ".join(f"{i + 1}.{s['agent']}" for i, s in enumerate(plan))
        task.add_event("plan", f"任务计划已生成：{steps}")
        return plan

    def _execute_plan(self, task: Task, plan: list, start_index: int = 0, state: dict = None):
        """
        顺序执行计划（支持从指定步骤开始，供断点恢复续跑）。
        - 遇到 human_input 断点：保存进度，状态切 waiting_input，等待人工输入
        - 正常结束：状态 done；取消：状态 cancelled
        """
        if state is None:
            state = make_init_state(task.topic, task.profiles, task.domain, task.model_tier)
        task.status = "executing"
        for i in range(start_index, len(plan)):
            if task._cancel:
                task.status = "cancelled"
                task.add_event("info", "任务已取消")
                return
            step = plan[i]
            agent_name = step["agent"]
            note = step.get("note", "")

            # 动态人工断点节点
            if agent_name == "human_input":
                task._exec_progress = {"index": i, "state": state}
                task.status = "waiting_input"
                task.add_event("waiting", f"⏸ 动态断点：{note}，等待人工输入")
                return

            task.add_event("step_start", f"▶ 执行步骤：{note} → 角色【{agent_name}】")
            run_func = registry.get_run_func(agent_name)
            update = run_func(state)
            state.update(update)
            task.add_event("agent_done", f"✅ 角色【{agent_name}】完成，更新字段：{list(update.keys())}")
        state["exec_plan"] = plan  # 供过程封存/任务回放使用
        task.final_state = state
        task.status = "done"
        task.add_event("done", "✅ 任务执行完成")
        self._archive_done(task)


# 模块级单例
task_manager = TaskManager()
