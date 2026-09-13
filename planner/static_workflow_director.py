"""
[模块] planner/static_workflow_director.py — 静态工作流调度器（基于 LangGraph）
[职责] 按流程名从 flow_registry 加载固定拓扑图，运行/恢复（interrupt 断点）
[设计思想] 与动态引擎互补：静态引擎面向"成熟稳定流程"，以硬编码 DAG 换可控性；
           流程定义全部放在 planner/flows/（FLOW_META），本文件只做按名构建与断点恢复；
           init_state 由调用方传入（已含价值观注入）；未传则内部构造并注入，保证零漏注入
[关键约定] 断点依赖 LangGraph interrupt（human_review Agent 专用）：
           run_workflow 执行到断点返回 (graph, config)，resume_workflow 用 Command(resume=...) 恢复；
           流程图必须用 MemorySaver checkpointer 编译（否则无状态快照）
[被谁调用] main.py、web_gui/services/task_manager.py（_run_static/resume_static）
[修改注意] 新增流程在 planner/flows/ 下加文件即可，勿在本文件硬编码拓扑
"""
from langgraph.types import Command
from planner.flow_registry import flow_registry
from core.logger import get_logger
from memory.memory_registry import inject_value_profiles

logger = get_logger("static_workflow")


class StaticWorkflowDirector:
    @staticmethod
    def list_flows():
        """列出所有已注册的静态流程"""
        return flow_registry.get_flow_list()

    @staticmethod
    def build_graph(flow_name: str = "article_generation"):
        """按流程名构建 LangGraph 图（默认文章生成流程）"""
        return flow_registry.build(flow_name)

    @staticmethod
    def run_workflow(topic: str, flow_name: str = "article_generation",
                     thread_id: str = "static_workflow_001", init_state: dict = None):
        """
        运行静态流程：执行到 interrupt 断点暂停，返回 (graph, config) 供外部恢复。
        :param topic: 研究主题
        :param flow_name: 流程名，默认 article_generation
        :param thread_id: 线程ID，用于状态快照恢复
        :param init_state: 初始状态（含价值观注入）；None 时内部构造并注入
        :return: (graph, config)
        """
        graph = StaticWorkflowDirector.build_graph(flow_name)
        config = {"configurable": {"thread_id": thread_id}}
        if init_state is None:
            init_state = inject_value_profiles({
                "topic": topic,
                "task_level": None,
                "research_material": None,
                "human_supplement": None,
                "final_article": None,
            })
        logger.info(f"静态工作流开始：flow={flow_name}, thread_id={thread_id}, topic={topic}")
        # 执行到 interrupt 断点停下
        graph.invoke(init_state, config=config)
        logger.info(f"静态工作流暂停于中断点：flow={flow_name}")
        return graph, config

    @staticmethod
    def resume_workflow(graph, config, resume_value: str):
        """
        从 interrupt 断点恢复执行。
        :param resume_value: 人工补充信息（interrupt 的返回值）
        :return: 最终状态字典
        """
        logger.info(f"静态工作流恢复执行，人工补充：{resume_value}")
        graph.invoke(Command(resume=resume_value), config=config)
        final_state = graph.get_state(config).values
        logger.info("静态工作流执行完成")
        return final_state
