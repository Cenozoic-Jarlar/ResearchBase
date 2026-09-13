"""
[模块] planner/flows/article_generation_flow.py — 静态流程：文章生成标准流程
[职责] 固定拓扑：任务路由分级 → 知识库调研 → 人工中断补充（人在回路）→ 文章生成输出
[设计思想] 项目第一个示例流程：体现"静态引擎=硬编码 DAG + interrupt 断点"；
           human_review 节点调用 interrupt 暂停，等待人工输入后恢复（执行中人在回路）
[关键约定] ★ 必须用 MemorySaver 编译（interrupt 依赖状态快照）；
           节点函数统一从 registry 获取（复用 Agent），流程文件只定义拓扑
[被谁调用] flow_registry.build("article_generation") → StaticWorkflowDirector / GUI 默认流程
[修改注意] 新增流程复制 _flow_template.py；节点名与 Agent 名一致便于日志追踪
"""
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from agent_registry.registry import registry
from state_model import State


def build():
    """组装文章生成流程的 LangGraph 图"""
    builder = StateGraph(State)

    fn_task_router = registry.get_run_func("task_router")
    fn_researcher = registry.get_run_func("researcher")
    fn_human_review = registry.get_run_func("human_review")
    fn_writer = registry.get_run_func("writer")

    builder.add_node("task_router", fn_task_router)
    builder.add_node("researcher", fn_researcher)
    builder.add_node("human_review", fn_human_review)
    builder.add_node("writer", fn_writer)

    def route_task_level(state: State):
        # 当前所有任务统一进入 researcher；后续可依据 task_level 分支
        return "researcher"

    builder.add_edge(START, "task_router")
    builder.add_conditional_edges("task_router", route_task_level)
    builder.add_edge("researcher", "human_review")
    builder.add_edge("human_review", "writer")
    builder.add_edge("writer", END)

    memory = MemorySaver()
    return builder.compile(checkpointer=memory)


FLOW_META = {
    "name": "article_generation",
    "description": "文章生成标准流程：任务路由分级 → 知识库调研 → 人工中断补充 → 文章生成输出（含人在回路断点）",
    "build": build
}
