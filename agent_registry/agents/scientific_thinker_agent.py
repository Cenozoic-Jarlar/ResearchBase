"""
[模块] agent_registry/agents/scientific_thinker_agent.py — Agent：科学思维分析师
[职责] 以科学方法论审视主题：概念界定、假设检验、因果证据强度、可证伪性
[设计思想] 思考型 Agent 之一：为实证/事实类主题补充方法论严谨性，
           输出供 writer 吸收；动态规划按主题需要选用
[关键约定] 写入字段 scientific_analysis；prompt 要求"只输出分析意见本身"；
           遵循 value_profiles 的 evidence 维度
[依赖] llm_config（get_llm/resolve_tier）、memory.memory_registry.format_values_for
[被谁调用] comprehensive_research 流程；动态规划按需选用
[修改注意] 分析维度可增删，但保持输出写入 scientific_analysis 字段
"""
from state_model import State
from llm_config import get_llm, resolve_tier
from memory.memory_registry import format_values_for

# 本角色消费的价值观维度
VP_DIMS = ["evidence"]

def run(state: State) -> dict:
    topic = state["topic"]
    research_material = state.get("research_material", "")
    values_text = format_values_for(state.get("value_profiles"), VP_DIMS)
    values_block = f"【本次任务价值观框架（证据要求）】\n{values_text}\n" if values_text else ""
    llm = get_llm(resolve_tier(state, AGENT_META.get("tier")))  # 档位：任务指定 > 难度映射 > standard 默认

    prompt = f"""
你是科学思维分析师。
研究主题：{topic}
{values_block}【AI调研素材】
{research_material}
任务：以科学方法论对主题进行分析，输出科学分析意见，包含：
1. 核心概念界定与操作化
2. 隐含假设检验
3. 因果关系的证据强度评估（相关≠因果等）
4. 结论的可证伪性与适用范围
分析时遵循上述证据要求。
要求逻辑严密、术语准确，只输出分析意见本身。
"""
    resp = llm.invoke(prompt)
    return {"scientific_analysis": resp.content}

AGENT_META = {
    "name": "scientific_thinker",
    "display_name": "科学思维分析师",
    "description": "科学思维角色：以科学方法论审视主题，检验假设与证据链，输出科学分析意见，增强文章实证严谨性",
    "persona": {"name": "理正", "tone": "理性冷静、逻辑严密", "tags": ["实证", "严谨"]},
    "consumes": ["evidence"],
    "tier": "standard",  # 固定档位（任务级指定可覆盖）
    "run": run
}
