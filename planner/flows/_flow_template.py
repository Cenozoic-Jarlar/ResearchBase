"""
[模块] planner/flows/_flow_template.py — 静态流程标准模板（复制即用）
[职责] 定义新静态流程的最小骨架：build() 组装 LangGraph 图 + FLOW_META
[设计思想] 流程=固定拓扑：节点函数统一从 agent_registry 获取（复用 Agent），
           本文件只定义节点顺序与分支；放入 planner/flows/ 即被 flow_registry 自动注册
[关键约定] ★ FLOW_META 的 key 名不可改（注册器按名读取）；name 唯一；
           build() 必须返回 compile(checkpointer=MemorySaver()) 的图（断点依赖）；
           文件名以 _ 开头不会注册
[被谁调用] 仅作模板
[修改注意] 新建流程：改 build() 拓扑 + FLOW_META + 头部注释；放入目录即生效
"""
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from agent_registry.registry import registry
from state_model import State


def build():
    """组装本流程的 LangGraph 图（示例骨架，按需替换节点与边）"""
    builder = StateGraph(State)

    # 从注册器获取角色执行函数
    fn_template = registry.get_run_func("template_agent")
    builder.add_node("template_node", fn_template)

    builder.add_edge(START, "template_node")
    builder.add_edge("template_node", END)

    memory = MemorySaver()
    return builder.compile(checkpointer=memory)


FLOW_META = {
    "name": "template_flow",
    "description": "【模板流程】示例骨架：单节点顺序执行，复制后按实际业务定义节点与拓扑",
    "build": build
}
