"""
[模块] planner/flows/fact_check_article_flow.py — 静态流程：事实审核文章流程（有界修订循环）
[职责] 固定拓扑：任务路由分级 → 知识库调研 → 写作 → 事实审核 →（不通过且未达上限 → 回溯 writer 修订）
[设计思想] 在标准文章流程上增加"审核-修订"有界循环：fact_checker 输出通过/不通过判定，
           route_fact_check 按判定与修订次数路由（通过或达上限 → 结束；否则回溯 writer）；
           上限常量 core.paths.FACT_CHECK_MAX_RETRIES 防止死循环
[关键约定] ★ 必须用 MemorySaver 编译；节点函数从 registry 获取；
           ★ route_fact_check 读取 fact_check_passed / fact_check_count（fact_checker 自增）；
           ★ 达上限仍不通过时强制结束并记 warning（保证有界）
[被谁调用] flow_registry.build("fact_check_article") → StaticWorkflowDirector / GUI 流程下拉
[修改注意] 判定标记与计数契约见 fact_checker_agent（改动需同步两处 + 动态引擎回溯分支）
"""
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from agent_registry.registry import registry
from state_model import State
from core.paths import FACT_CHECK_MAX_RETRIES
from core.logger import get_logger

logger = get_logger("fact_check_flow")


def route_fact_check(state: State):
    """事实审核路由：通过 → 结束；不通过且未达上限 → 回溯 writer 修订；达上限 → 强制结束"""
    passed = state.get("fact_check_passed", True)
    count = state.get("fact_check_count", 0)
    if passed:
        return END
    if count >= FACT_CHECK_MAX_RETRIES:
        logger.warning(f"事实审核第 {count} 次仍不通过，已达修订上限 {FACT_CHECK_MAX_RETRIES}，强制结束")
        return END
    return "writer"


def build():
    builder = StateGraph(State)

    fn_task_router = registry.get_run_func("task_router")
    fn_researcher = registry.get_run_func("researcher")
    fn_writer = registry.get_run_func("writer")
    fn_fact_checker = registry.get_run_func("fact_checker")

    builder.add_node("task_router", fn_task_router)
    builder.add_node("researcher", fn_researcher)
    builder.add_node("writer", fn_writer)
    builder.add_node("fact_checker", fn_fact_checker)

    builder.add_edge(START, "task_router")
    builder.add_edge("task_router", "researcher")
    builder.add_edge("researcher", "writer")
    builder.add_edge("writer", "fact_checker")
    builder.add_conditional_edges("fact_checker", route_fact_check)

    memory = MemorySaver()
    return builder.compile(checkpointer=memory)


FLOW_META = {
    "name": "fact_check_article",
    "description": "事实审核文章流程：路由 → 调研 → 写作 → 事实审核（不通过自动回溯修订，有界循环）→ 完成",
    "build": build
}
