"""
[模块] agent_registry/agents/humanities_thinker_agent.py — Agent：人文思考者
[职责] 从人文视角补充主题：价值关切、伦理权衡、社会文化意义、对普通人的影响
[设计思想] 思考型 Agent 之一：为政策/伦理/社会/文化类主题补充思想深度；
           纯技术/纯数据主题可不调用（动态规划按需选用）
[关键约定] 写入字段 humanities_perspective；prompt 要求"只输出补充内容本身"；
           遵循 value_profiles 的 stance/critique 维度
[依赖] llm_config（get_llm/resolve_tier）、memory.memory_registry.format_values_for
[被谁调用] comprehensive_research 流程；动态规划按需选用
[修改注意] 补充维度可增删，但保持输出写入 humanities_perspective 字段
"""
from state_model import State
from llm_config import get_llm, resolve_tier
from memory.memory_registry import format_values_for

# 本角色消费的价值观维度
VP_DIMS = ["stance", "critique"]

def run(state: State) -> dict:
    topic = state["topic"]
    research_material = state.get("research_material", "")
    values_text = format_values_for(state.get("value_profiles"), VP_DIMS)
    values_block = f"【本次任务价值观框架（立场与批判侧重）】\n{values_text}\n" if values_text else ""
    llm = get_llm(resolve_tier(state, AGENT_META.get("tier")))  # 档位：任务指定 > 难度映射 > standard 默认

    prompt = f"""
你是人文思考者。
研究主题：{topic}
{values_block}【AI调研素材】
{research_material}
任务：从人文视角对主题进行补充思考，输出人文思考补充，包含：
1. 相关群体的价值关切与利益影响
2. 伦理层面的考量与权衡
3. 社会文化意义与历史脉络
4. 对普通人生活的潜在影响
思考时遵循上述价值观框架的立场与批判侧重。
要求有洞察、不空泛，只输出补充内容本身。
"""
    resp = llm.invoke(prompt)
    return {"humanities_perspective": resp.content}

AGENT_META = {
    "name": "humanities_thinker",
    "display_name": "人文思考者",
    "description": "人文思考角色：从价值、伦理、社会文化视角补充主题思考，丰富文章思想深度（适用政策/伦理/社会/文化类主题）",
    "persona": {"name": "思远", "tone": "温和深刻、关怀个体", "tags": ["共情", "洞察"]},
    "consumes": ["stance", "critique"],
    "tier": "standard",  # 固定档位（任务级指定可覆盖）
    "run": run
}
