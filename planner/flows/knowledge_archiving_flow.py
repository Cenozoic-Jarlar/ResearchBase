"""
[模块] planner/flows/knowledge_archiving_flow.py — 静态流程：知识归档流程
[职责] 固定拓扑：路由 → 调研 → 文章生成 → 归档员写入本地资料库
[设计思想] 展示"研究-沉淀"闭环：writer 产出文章后，archivist 调 write_local_database
           Skill 入库，体现 Agent 与工具解耦的完整链路
[关键约定] 必须用 MemorySaver 编译；节点函数从 registry 获取；归档动作在 archivist Agent 内
[被谁调用] flow_registry.build("knowledge_archiving") → StaticWorkflowDirector / GUI 流程下拉
[修改注意] 归档目标/命名规则改动在 skills/write_local_database.py
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
    fn_archivist = registry.get_run_func("archivist")

    builder.add_node("task_router", fn_task_router)
    builder.add_node("researcher", fn_researcher)
    builder.add_node("writer", fn_writer)
    builder.add_node("archivist", fn_archivist)

    builder.add_edge(START, "task_router")
    builder.add_edge("task_router", "researcher")
    builder.add_edge("researcher", "writer")
    builder.add_edge("writer", "archivist")
    builder.add_edge("archivist", END)

    return builder.compile(checkpointer=MemorySaver())


FLOW_META = {
    "name": "knowledge_archiving",
    "description": "知识归档流程：任务路由 → 知识库调研 → 文章生成 → 归档员写入本地资料库（沉淀成果）",
    "build": build
}
