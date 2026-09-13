"""
[模块] agent_registry/agents/fact_checker_agent.py — Agent：事实审核员
[职责] 对成稿文章（final_article）做事实与幻觉审查：数字/日期/专名准确性、来源真实性、
       编造引用、张冠李戴、前后矛盾、过时信息；输出问题清单 + 通过/不通过判定
[设计思想] 与 critical_reviewer 分工：批判性审阅审"观点与论证"（写前、输出意见）；
           fact_checker 审"信息与事实"（写后、输出判定），判定驱动有界修订循环
           （writer 修订 → 复审，达上限强制通过，见 planner/flows/fact_check_article_flow 与
            dynamic_planner._execute 的 fact_checker 回溯分支）
[关键约定] ★ 必须输出末行判定标记【判定】通过/不通过（引擎/流程据此路由）；
           ★ fact_check_count 每次执行自增（记录审核次数，供上限判断）；上限常量
             core.paths.FACT_CHECK_MAX_RETRIES（默认 2）
[依赖] llm_config（get_llm/resolve_tier）、memory.memory_registry.format_values_for、core.paths
[被谁调用] fact_check_article 流程；动态规划按需选用
[修改注意] 判定标记格式被流程与动态引擎硬编码识别，改动需同步两处 + 测试
"""
from state_model import State
from llm_config import get_llm, resolve_tier
from memory.memory_registry import format_values_for

# 本角色消费的价值观维度（证据要求：来源优先、注明出处）
VP_DIMS = ["evidence"]


def run(state: State) -> dict:
    topic = state["topic"]
    article = state.get("final_article", "")
    values_text = format_values_for(state.get("value_profiles"), VP_DIMS)
    values_block = f"【本次任务价值观框架（证据要求）】\n{values_text}\n" if values_text else ""
    llm = get_llm(resolve_tier(state, AGENT_META.get("tier")))  # 档位：任务指定 > 难度映射 > standard 默认

    prompt = f"""
你是事实审核员，负责对研究文章做事实正确性与幻觉审查。
研究主题：{topic}
{values_block}【待审核文章】
{article}
任务：逐条核查并输出事实审核意见：
1. 数字、日期、名称、专有名词是否准确（对不确定的标注"待核实"）
2. 引用/来源是否真实存在，有无编造来源、张冠李戴
3. 有无大模型幻觉（把可能/推测写成定论、凭空捏造事实）
4. 文章内部有无前后矛盾
5. 有无把过时信息当作最新情况
要求：问题清单条理清晰，逐条说明"原文摘录 → 问题 → 建议修正"。
最后一行必须输出判定标记（不要多余内容）：
【判定】通过   或   【判定】不通过
"""
    resp = llm.invoke(prompt)
    content = resp.content

    # 解析判定：默认通过；内容含"【判定】不通过"即判不通过
    passed = "【判定】不通过" not in content
    issues = content.split("【判定】")[0].strip() or content.strip()
    count = int(state.get("fact_check_count") or 0) + 1

    return {
        "fact_check_issues": issues,
        "fact_check_passed": passed,
        "fact_check_count": count,
    }


AGENT_META = {
    "name": "fact_checker",
    "display_name": "事实审核员",
    "description": "事实审核角色：对成稿文章核查事实正确性、来源真实性与大模型幻觉，输出问题清单并通过/不通过判定（触发修订循环）。适合需要确保文章事实准确的流程",
    "persona": {"name": "核审", "tone": "严谨缜密、实事求是", "tags": ["较真", "查证"]},
    "consumes": ["evidence"],
    "tier": "standard",  # 固定档位（任务级指定可覆盖）
    "run": run
}
