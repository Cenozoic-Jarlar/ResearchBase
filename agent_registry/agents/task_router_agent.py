"""
[模块] agent_registry/agents/task_router_agent.py — Agent：任务路由员
[职责] 评估用户任务复杂度，输出 simple/complex，供 researcher 选用高低成本模型
[设计思想] 复杂分级是成本优化点：简单任务走便宜模型、复杂任务走强模型；
           同时输出写入 state.task_level，供后续 Agent 读取
[关键约定] 只输出 simple 或 complex（prompt 强制），写入字段 task_level；固定 router 档（AGENT_META.tier）
[依赖] llm_config（get_llm/resolve_tier）
[被谁调用] 动态/静态流程的第一步；DynamicPlanner 编排时自动选用
[修改注意] 分级规则改动同步影响 researcher 的模型选择与 llm_config.TIER_MAP 难度映射
"""
from state_model import State
from llm_config import get_llm, resolve_tier

def run(state: State) -> dict:
    topic = state["topic"]
    prompt = f"""
判断用户研究任务复杂度，只输出simple或者complex，不要多余文字。
simple：简单问答、简短摘要、文本改错、简单改写。
complex：深度调研、长文章撰写、多概念拆解、Agent原理、复杂推理。
任务：{topic}
"""
    resp = get_llm(resolve_tier(state, AGENT_META.get("tier"))).invoke(prompt)
    level = resp.content.strip().lower()
    return {"task_level": level}

AGENT_META = {
    "name": "task_router",
    "display_name": "任务路由员",
    "description": "评估用户任务复杂度，输出simple/complex，用于选择高低成本大模型",
    "persona": {"name": "小航", "tone": "干脆利落", "tags": ["敏捷", "果决"]},
    "consumes": [],
    "tier": "router",  # 固定 router 档：路由判断用最便宜模型
    "run": run
}
