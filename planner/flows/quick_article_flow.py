"""
[模块] planner/flows/quick_article_flow.py — 静态流程：快速文章流程
[职责] 固定拓扑：任务路由分级 → 知识库调研 → 文章生成（无人工断点，快速产出）
[设计思想] 面向简单/中等主题的"轻量模板"：省略思考型角色与断点，链路最短
[关键约定] 必须用 MemorySaver 编译；节点函数从 registry 获取
[被谁调用] flow_registry.build("quick_article") → StaticWorkflowDirector / GUI 流程下拉
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
    fn_writer = registry.get_run_func("writer")

    builder.add_node("task_router", fn_task_router)
    builder.add_node("researcher", fn_researcher)
    builder.add_node("writer", fn_writer)

    builder.add_edge(START, "task_router")
    builder.add_edge("task_router", "researcher")
    builder.add_edge("researcher", "writer")
    builder.add_edge("writer", END)

    return builder.compile(checkpointer=MemorySaver())


FLOW_META = {
    "name": "quick_article",
    "description": "快速文章流程：任务路由分级 → 知识库调研 → 文章生成（无人工断点，快速产出）",
    "build": build
}
