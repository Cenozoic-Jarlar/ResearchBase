"""
[模块] agent_registry/agents/critical_reviewer_agent.py — Agent：批判性审阅员
[职责] 以批判性思维审视调研素材：逻辑漏洞、证据可靠性、反方观点、待核实事实
[设计思想] 思考型 Agent 之一：不产出最终文章，而是输出"审阅意见"供 writer 吸收，
           提升文章严谨度；动态规划按主题需要选用（非每次必调）
[关键约定] 写入字段 critical_review；prompt 要求"只输出审阅意见本身"；
           遵循 value_profiles 的 critique/evidence 维度（批判侧重）
[依赖] llm_config（get_llm/resolve_tier）、memory.memory_registry.format_values_for
[被谁调用] critical_article / comprehensive_research 流程；动态规划按需选用
[修改注意] 意见维度可增删，但保持输出写入 critical_review 字段
"""
from state_model import State
from llm_config import get_llm, resolve_tier
from memory.memory_registry import format_values_for

# 本角色消费的价值观维度
VP_DIMS = ["critique", "evidence"]

def run(state: State) -> dict:
    topic = state["topic"]
    research_material = state.get("research_material", "")
    values_text = format_values_for(state.get("value_profiles"), VP_DIMS)
    values_block = f"【本次任务价值观框架（批判侧重）】\n{values_text}\n" if values_text else ""
    llm = get_llm(resolve_tier(state, AGENT_META.get("tier")))  # 档位：任务指定 > 难度映射 > standard 默认

    prompt = f"""
你是批判性思维审阅员。
研究主题：{topic}
{values_block}【AI调研素材】
{research_material}
任务：以批判性思维审视上述素材，输出批判性审阅意见，包含：
1. 逻辑漏洞与论证缺陷
2. 证据可靠性评估（哪些结论缺乏足够证据支撑）
3. 被忽略的反方观点或替代解释
4. 需要补充核实的事实
批判时遵循上述价值观框架的批判侧重与证据要求。
要求条理清晰、切中要害，只输出审阅意见本身。
"""
    resp = llm.invoke(prompt)
    return {"critical_review": resp.content}

AGENT_META = {
    "name": "critical_reviewer",
    "display_name": "批判性审阅员",
    "description": "批判性思维角色：审视调研素材的逻辑漏洞、证据可靠性、反方观点，输出审阅意见，供撰稿阶段提升文章严谨度",
    "persona": {"name": "锐评", "tone": "犀利直接、切中要害", "tags": ["敏锐", "挑剔"]},
    "consumes": ["critique", "evidence"],
    "tier": "standard",  # 固定档位（任务级指定可覆盖）
    "run": run
}
