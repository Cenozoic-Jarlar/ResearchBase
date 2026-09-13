"""
[模块] agent_registry/agents/human_review_agent.py — Agent：人工审阅员（人在回路）
[职责] 流程执行到此处暂停（LangGraph interrupt），等待人工输入补充信息/修改意见
[设计思想] 这是"执行中人在回路"的静态引擎实现：interrupt 只能在 LangGraph 图内工作，
           动态引擎的等价物是 human_input 协议（见 planner/dynamic_planner.py），两者机制不同
[关键约定] ★ engines=["static"]：动态引擎规划时自动排除；interrupt 返回人工输入，
           写入字段 human_supplement 供 writer 使用
[依赖] langgraph.types.interrupt
[被谁调用] 静态流程（如 article_generation）；由 StaticWorkflowDirector.run_workflow/resume_workflow 驱动
[修改注意] 不要在动态引擎中调用本 Agent；动态版人机交互用 human_input 断点
"""
from state_model import State
from langgraph.types import interrupt

def run(state: State) -> dict:
    print("\n✅ 调研完成，进入人工审阅环节")
    user_input = interrupt("请输入补充信息/修改意见，无补充直接输入【无】")
    return {"human_supplement": user_input}

AGENT_META = {
    "name": "human_review",
    "display_name": "人工审阅员",
    "description": "人在回路节点：流程执行到这里暂停，等待人工输入补充信息，仅固定工作流使用",
    "persona": {"name": "把关人", "tone": "审慎负责", "tags": ["负责", "严谨"]},
    "consumes": [],
    "run": run,
    # 依赖 LangGraph interrupt，仅在静态工作流引擎中可用；动态引擎规划时自动排除
    "engines": ["static"]
}
