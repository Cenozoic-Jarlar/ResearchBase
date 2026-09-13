"""
[测试] test_web_gui.py — Web GUI 服务层状态机
[运行] venv\\Scripts\\python.exe test_web_gui.py
[约定] mock LLM 与 Agent（不调用真实模型）；覆盖：动态全自动、动态人审
       （反馈重生成→执行）、静态断点恢复、动态 human_input 断点暂停/恢复
"""
import os
from contextlib import contextmanager
from unittest.mock import Mock, patch

os.environ["LLM_API_KEY"] = "fake_test_key"
os.environ["LLM_BASE_URL"] = "https://mock.api.test"
os.environ["LLM_MODELS"] = '[{"name":"router","model":"mock-r","role":"r","capabilities":["text"]},{"name":"standard","model":"mock-s","role":"s","capabilities":["text"]},{"name":"reasoning","model":"mock-m","role":"m","capabilities":["text"]}]'

import langchain_openai
langchain_openai.ChatOpenAI = Mock()

from agent_registry.registry import registry
from web_gui.services import task_manager as tm
from web_gui.services.task_manager import TaskManager

PLAN_JSON = '[{"agent":"task_router","note":"评估任务难度"},{"agent":"researcher","note":"读取知识库"},{"agent":"writer","note":"撰写文章"}]'


def make_fake_llm(plan_content=None):
    fake = Mock()
    fake.invoke = Mock(return_value=Mock(content=plan_content or PLAN_JSON))
    return fake


def make_fake_run(update=None):
    return Mock(return_value=update or {"fake_field": "ok"})


@contextmanager
def runtime_ctx(fake_llm, fake_run):
    """mock LLM + Agent + 长期记忆沉淀 + 文章保存（done 路径不写真实 output/task_history）"""
    with patch("planner.dynamic_planner.get_llm", return_value=fake_llm), \
         patch.object(registry, "get_run_func", return_value=fake_run), \
         patch("memory.memory_registry.sediment_task_memory", return_value=""), \
         patch("tools.document_output.save_article", return_value="output_fake.md"):
        yield


def test_auto_mode():
    print("=" * 60)
    print("【测试：动态全自动模式状态机】")
    print("=" * 60)
    fake_llm, fake_run = make_fake_llm(), make_fake_run({"research_material": "素材"})
    mgr = TaskManager()
    with runtime_ctx(fake_llm, fake_run):
        task = mgr.create("测试主题", "auto")
        mgr.start(task)
        task._thread.join(timeout=30)
    assert task.status == "done", f"状态应为 done，实际 {task.status}"
    assert task.plan and len(task.plan) == 3, "计划应为3步"
    assert task.graph["nodes"] and task.graph["edges"], "流程图数据应生成"
    assert task.final_state["research_material"] == "素材"
    types = {e["type"] for e in task.events}
    assert {"plan", "step_start", "agent_done", "done"} <= types, f"事件类型缺失: {types}"
    print(f"✅ 状态机: {task.status}，事件 {len(task.events)} 条，流程节点 {len(task.graph['nodes'])} 个\n")


def test_human_review_mode():
    print("=" * 60)
    print("【测试：动态人审模式（反馈重生成 → 执行）】")
    print("=" * 60)
    fake_llm, fake_run = make_fake_llm(), make_fake_run({"final_article": "文章"})
    mgr = TaskManager()
    with runtime_ctx(fake_llm, fake_run):
        task = mgr.create("测试主题", "human_review")
        mgr.start(task)
        task._thread.join(timeout=30)
        assert task.status == "waiting_feedback", f"应停在等待反馈，实际 {task.status}"
        # 提交修改意见 → 重新生成计划
        ok, msg = mgr.feedback_plan(task, "增加批判性审阅")
        assert ok, msg
        assert fake_llm.invoke.call_count == 2, "应重新调用LLM生成计划"
        # 开始执行
        ok, msg = mgr.start_execute(task)
        assert ok, msg
        task._thread.join(timeout=30)
    assert task.status == "done", f"执行后应为 done，实际 {task.status}"
    assert task.final_state["final_article"] == "文章"
    print(f"✅ 反馈重生成成功（LLM调用{2}次），执行完成\n")


def test_static_resume():
    print("=" * 60)
    print("【测试：静态流程断点恢复】")
    print("=" * 60)
    # mock 静态流程：run_workflow 返回假 graph/config，带 next 节点 → 触发等待 → resume
    mgr = TaskManager()
    fake_graph = Mock()
    fake_config = {"configurable": {"thread_id": "t"}}
    fake_snapshot = Mock()
    fake_snapshot.next = ["human_review"]
    fake_snapshot.values = {"topic": "测试主题", "final_article": "文章"}
    fake_graph.get_state.return_value = fake_snapshot
    fake_graph.get_graph.return_value = Mock(
        nodes={"task_router", "writer"}, edges=[])

    with patch.object(tm.StaticWorkflowDirector, "run_workflow", return_value=(fake_graph, fake_config)), \
         patch("memory.memory_registry.sediment_task_memory", return_value=""), \
         patch("tools.document_output.save_article", return_value="output_fake.md"):
        task = mgr.create("测试主题", "static", flow_name="article_generation")
        mgr.start(task)
        task._thread.join(timeout=30)
        assert task.status == "waiting_input", f"应停在人工断点，实际 {task.status}"
        ok, msg = mgr.resume_static(task, "补充意见")
        assert ok, msg
        assert task.status == "done"
        fake_graph.invoke.assert_called_once()
        plan = task.final_state.get("exec_plan")
        assert plan and isinstance(plan, list), "静态流程恢复完成后应写入 exec_plan（执行计划入档）"
        assert any(s.get("agent") == "writer" for s in plan), f"exec_plan 应含流程节点，实际 {plan}"
    print("✅ 静态流程：执行→断点→人工输入→完成，全链路正常（含执行计划入档）\n")


def test_static_done_with_plan():
    print("=" * 60)
    print("【测试：静态流程无断点直接完成 + 执行计划入档】")
    print("=" * 60)
    mgr = TaskManager()
    fake_graph = Mock()
    fake_config = {"configurable": {"thread_id": "t"}}
    fake_snapshot = Mock()
    fake_snapshot.next = []  # 无断点 → 直接 done
    fake_snapshot.values = {"topic": "测试主题", "final_article": "文章"}
    fake_graph.get_state.return_value = fake_snapshot
    fake_graph.get_graph.return_value = Mock(
        nodes={"task_router", "researcher", "writer"}, edges=[])

    with patch.object(tm.StaticWorkflowDirector, "run_workflow", return_value=(fake_graph, fake_config)), \
         patch("memory.memory_registry.sediment_task_memory", return_value=""), \
         patch("tools.document_output.save_article", return_value="output_fake.md"):
        task = mgr.create("测试主题", "static", flow_name="quick_article")
        mgr.start(task)
        task._thread.join(timeout=30)
    assert task.status == "done", f"无断点应直接完成，实际 {task.status}"
    plan = task.final_state.get("exec_plan")
    assert plan and len(plan) == 3, f"exec_plan 应含 3 个流程节点，实际 {plan}"
    print("✅ 静态无断点完成 + 执行计划入档正常\n")


def test_dynamic_breakpoint():
    print("=" * 60)
    print("【测试：动态 human_input 断点暂停与恢复】")
    print("=" * 60)
    plan_with_break = '[{"agent":"task_router","note":"评估难度"},' \
                      '{"agent":"human_input","note":"请补充背景信息"},' \
                      '{"agent":"writer","note":"撰写文章"}]'
    fake_llm = make_fake_llm(plan_with_break)
    fake_run = make_fake_run({"final_article": "文章"})
    mgr = TaskManager()
    with runtime_ctx(fake_llm, fake_run):
        task = mgr.create("测试主题", "auto")
        mgr.start(task)
        task._thread.join(timeout=30)
        assert task.status == "waiting_input", f"应停在动态断点，实际 {task.status}"
        assert task._exec_progress is not None, "应保存断点执行进度"
        ok, msg = mgr.resume_dynamic(task, "补充内容")
        assert ok, msg
        assert task.status == "done", f"恢复后应为 done，实际 {task.status}"
        assert task.final_state["human_supplement"] == "补充内容"
        assert task.final_state["final_article"] == "文章"
    print("✅ 动态断点：执行→暂停→人工输入→续跑完成\n")


if __name__ == "__main__":
    test_auto_mode()
    test_human_review_mode()
    test_static_resume()
    test_static_done_with_plan()
    test_dynamic_breakpoint()
