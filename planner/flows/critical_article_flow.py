"""
[模块] planner/flows/critical_article_flow.py — 静态流程：批判性文章流程
[职责] 固定拓扑：任务路由分级 → 知识库调研 → 批判性审阅 → 文章生成
[设计思想] 面向观点争议/需多角度论证主题：插入 critical_reviewer 提升论证严谨度
[关键约定] 必须用 MemorySaver 编译；节点函数从 registry 获取
[被谁调用] flow_registry.build("critical_article") → StaticWorkflowDirector / GUI 流程下拉
[修改注意] 新增流程复制 _flow_template.py；节点名与 Agent 名一致便于日志追踪
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
    fn_writer = registry.get_run_func("writer")

    builder.add_node("task_router", fn_task_router)
    builder.add_node("researcher", fn_researcher)
    builder.add_node("critical_reviewer", fn_critical)
    builder.add_node("writer", fn_writer)

    builder.add_edge(START, "task_router")
    builder.add_edge("task_router", "researcher")
    builder.add_edge("researcher", "critical_reviewer")
    builder.add_edge("critical_reviewer", "writer")
    builder.add_edge("writer", END)

    return builder.compile(checkpointer=MemorySaver())


FLOW_META = {
    "name": "critical_article",
    "description": "批判性文章流程：任务路由分级 → 知识库调研 → 批判性审阅 → 文章生成（提升论证严谨度）",
    "build": build
}
