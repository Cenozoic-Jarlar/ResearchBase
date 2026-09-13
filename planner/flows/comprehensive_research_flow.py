"""
[模块] planner/flows/comprehensive_research_flow.py — 静态流程：综合深度研究流程
[职责] 固定拓扑：路由 → 调研 → 批判性审阅 → 科学思维 → 人文视角 → 写作
[设计思想] "全思考链"模板：三种思考型 Agent 依次补充，writer 聚合，
           面向政策/伦理/社会/科学类复杂主题的多维度深度研究
[关键约定] 必须用 MemorySaver 编译；节点函数从 registry 获取；节点顺序=思考递进顺序
[被谁调用] flow_registry.build("comprehensive_research") → StaticWorkflowDirector / GUI 流程下拉
[修改注意] 新增流程复制 _flow_template.py；调整思考链顺序需确认 writer 读取对应字段
"""
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from agent_registry.registry import registry
from state_model import State


def build():
    builder = StateGraph(State)
    fn_task_router = registry.get_run_func("task_router")
    fn_researcher = registry.get_run_func("researcher")
    fn_critical = registry.get_run_func("critical_reviewer")
    fn_scientific = registry.get_run_func("scientific_thinker")
    fn_humanities = registry.get_run_func("humanities_thinker")
    fn_writer = registry.get_run_func("writer")

    builder.add_node("task_router", fn_task_router)
    builder.add_node("researcher", fn_researcher)
    builder.add_node("critical_reviewer", fn_critical)
    builder.add_node("scientific_thinker", fn_scientific)
    builder.add_node("humanities_thinker", fn_humanities)
    builder.add_node("writer", fn_writer)

    builder.add_edge(START, "task_router")
    builder.add_edge("task_router", "researcher")
    builder.add_edge("researcher", "critical_reviewer")
    builder.add_edge("critical_reviewer", "scientific_thinker")
    builder.add_edge("scientific_thinker", "humanities_thinker")
    builder.add_edge("humanities_thinker", "writer")
    builder.add_edge("writer", END)

    return builder.compile(checkpointer=MemorySaver())


FLOW_META = {
    "name": "comprehensive_research",
    "description": "综合深度研究流程：调研 → 批判性审阅 → 科学思维 → 人文视角 → 写作（多维度深度研究）",
    "build": build
}
