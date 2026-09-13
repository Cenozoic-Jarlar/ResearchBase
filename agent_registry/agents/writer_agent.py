"""
[模块] agent_registry/agents/writer_agent.py — Agent：撰稿员
[职责] 整合调研素材、思考型角色意见（批判/科学/人文）、事实审核意见与人工补充，撰写最终研究文章
[设计思想] 收敛节点：把多 Agent 输出聚合为最终产物；缺失意见自动忽略，
           文章吸收审阅意见修正论证缺陷（体现"审阅-写作"协作闭环）；
           事实审核意见存在时视为"修订轮"：须逐条消除问题后重新成稿（有界循环见事实审核流程）
[关键约定] 写入字段 final_article（全项目最终交付物，main.py/show_result 读取）；
           遵循 state["value_profiles"] 中本角色消费的维度（stance/evidence/style/critique）
[依赖] llm_config（get_llm/resolve_tier）、memory.memory_registry.format_values_for
[被谁调用] 动态/静态流程的收尾环节（含事实审核回溯修订）
[修改注意] 新增思考型 Agent 后如需其意见进入文章，同步在此读取对应 state 字段
"""
from state_model import State
from llm_config import get_llm, resolve_tier
from memory.memory_registry import format_values_for

# 本角色消费的价值观维度（与框架 values 键对应）
VP_DIMS = ["stance", "evidence", "style", "critique"]

def run(state: State) -> dict:
    topic = state["topic"]
    research_material = state.get("research_material", "")
    human_supplement = state.get("human_supplement", "")
    critical_review = state.get("critical_review", "")
    scientific_analysis = state.get("scientific_analysis", "")
    humanities_perspective = state.get("humanities_perspective", "")
    fact_check_issues = state.get("fact_check_issues", "")
    values_text = format_values_for(state.get("value_profiles"), VP_DIMS)
    values_block = f"【本次任务价值观框架】\n{values_text}\n" if values_text else ""
    # 模型档位：任务指定 > 难度映射 > standard 默认（复杂任务默认 standard 档）
    llm = get_llm(resolve_tier(state, AGENT_META.get("tier")))

    prompt = f"""
你是专业撰稿人。
研究主题：{topic}
{values_block}【AI调研素材】
{research_material}
【批判性审阅意见】（如有）
{critical_review}
【科学思维分析】（如有）
{scientific_analysis}
【人文视角补充】（如有）
{humanities_perspective}
【事实审核意见】（如有，本轮修订必须逐条消除所列问题，不得回避）
{fact_check_issues}
【人工补充信息】
{human_supplement}
任务：整合全部信息，输出一篇结构完整、逻辑通顺、经得起推敲的研究文章。
写作时必须遵循上述价值观框架（立场/证据/风格/批判侧重）。
若某部分意见缺失则忽略该部分；文章应吸收审阅意见修正论证缺陷。
"""
    resp = llm.invoke(prompt)
    return {"final_article": resp.content}

AGENT_META = {
    "name": "writer",
    "display_name": "撰稿员",
    "description": "撰稿角色，整合调研素材、思考型角色意见与人工补充信息，撰写最终完整文章",
    "persona": {"name": "晓笔", "tone": "沉稳从容、善表达", "tags": ["稳健", "文采"]},
    "consumes": ["stance", "evidence", "style", "critique"],
    "tier": "standard",  # 固定档位（任务级指定可覆盖）
    "run": run
}
