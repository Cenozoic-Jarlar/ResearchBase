"""
[模块] planner/flows/material_import_flow.py — 静态流程：资料采集入库流程
[职责] 固定拓扑：人工断点询问来源 → 资料采集员获取/整理/入库
[设计思想] 复用人在回路（human_input 断点）：用户无需改代码，在流程断点输入
           URL/本地文件路径/文本即可入库；collector 从 human_supplement 读来源
[关键约定] 必须用 MemorySaver 编译（interrupt 依赖）；human_input 是 static-only Agent
[被谁调用] flow_registry.build("material_import") → StaticWorkflowDirector / GUI 流程下拉
[修改注意] 新增流程复制 _flow_template.py；节点名与 Agent 名一致便于日志追踪
"""
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from agent_registry.registry import registry
from state_model import State


def build():
    builder = StateGraph(State)
    fn_human = registry.get_run_func("human_review")
    fn_collector = registry.get_run_func("collector")

    builder.add_node("human_input", fn_human)
    builder.add_node("collector", fn_collector)

    builder.add_edge(START, "human_input")
    builder.add_edge("human_input", "collector")
    builder.add_edge("collector", END)

    return builder.compile(checkpointer=MemorySaver())


FLOW_META = {
    "name": "material_import",
    "description": "资料采集入库流程：人工断点输入来源（URL/本地文件/文本）→ 资料采集员整理写入主题库",
    "build": build
}
