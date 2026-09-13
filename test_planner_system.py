"""
[测试] test_planner_system.py — 动态规划 + 静态调度器接口
[运行] venv\\Scripts\\python.exe test_planner_system.py
[约定] 不调用真实 LLM：顶部 mock 环境变量与 ChatOpenAI，mock planner.dynamic_planner.get_llm；
       仅校验导入、规划生成/容错解析、流程注册与图构建
"""
# ========= 必须放在文件最顶部，优先 mock，解决导入依赖 =========
import os
from unittest.mock import Mock, patch

os.environ["LLM_API_KEY"] = "fake_test_key"
os.environ["LLM_BASE_URL"] = "https://mock.api.test"
os.environ["LLM_MODELS"] = '[{"name":"router","model":"mock-r","role":"r","capabilities":["text"]},{"name":"standard","model":"mock-s","role":"s","capabilities":["text"]},{"name":"reasoning","model":"mock-m","role":"m","capabilities":["text"]}]'

import langchain_openai
langchain_openai.ChatOpenAI = Mock()
# =================================================================

from agent_registry.registry import registry
from planner.plan_renderer import render_plan
from planner.dynamic_planner import DynamicPlanner
from planner.static_workflow_director import StaticWorkflowDirector
from planner.flow_registry import flow_registry


def test_registry_load():
    """静态测试：Agent 注册表加载 + 引擎过滤"""
    print("=" * 60)
    print("【静态测试：Agent 注册表加载】")
    print("=" * 60)
    all_agents = registry.get_agent_list()
    dynamic_agents = registry.get_agent_list(engine="dynamic")
    print(f"✅ 全部Agent: {[a['name'] for a in all_agents]}")
    print(f"✅ 动态引擎可用Agent: {[a['name'] for a in dynamic_agents]}")
    # human_review 仅 static 引擎，不应出现在动态清单中
    dynamic_names = {a['name'] for a in dynamic_agents}
    assert "human_review" not in dynamic_names, "human_review 不应出现在动态引擎清单"
    assert "task_router" in dynamic_names, "task_router 应出现在动态引擎清单"
    # 思考型 Agent（批判性/科学/人文）应注册且动态引擎可用
    for expected in ("critical_reviewer", "scientific_thinker", "humanities_thinker"):
        assert expected in dynamic_names, f"{expected} 应注册并可用于动态引擎"
    print(f"✅ 思考型Agent已注册: "
          f"{[n for n in dynamic_names if n in ('critical_reviewer','scientific_thinker','humanities_thinker')]}")
    print("✅ 引擎过滤正确\n")


def test_dynamic_planner_mock_generate():
    """模拟测试：Mock LLM，测试计划生成 + 解析 + 渲染"""
    print("=" * 60)
    print("【模拟测试：DynamicPlanner 计划生成（Mock LLM）】")
    print("=" * 60)
    mock_llm = Mock()
    mock_plan_json = json_dumps([
        {"agent": "task_router", "note": "评估任务难度，选择模型"},
        {"agent": "researcher", "note": "读取知识库整理素材"},
        {"agent": "writer", "note": "整合素材，撰写最终文章"},
    ])
    mock_llm.invoke = Mock(return_value=Mock(content=mock_plan_json))

    with patch("planner.dynamic_planner.get_llm", return_value=mock_llm):
        raw = DynamicPlanner.generate_raw_plan("写一篇人工智能发展简史")
        plan = DynamicPlanner.parse_plan(raw)

    print(f"用户请求：写一篇人工智能发展简史")
    print("\n生成任务规划：")
    print(render_plan(plan))
    assert len(plan) == 3, f"计划步骤数应为3，实际{len(plan)}"
    assert plan[0]["agent"] == "task_router"
    print("\n✅ 计划生成测试通过\n")


def test_dynamic_planner_parse_robust():
    """容错测试：解析带 markdown 代码块 / 杂文本的 LLM 输出"""
    print("=" * 60)
    print("【容错测试：parse_plan 解析健壮性】")
    print("=" * 60)
    messy1 = '```json\n[{"agent":"a","note":"x"}]\n```'
    messy2 = '好的，以下是计划：\n[{"agent":"b","note":"y"}] 以上。'
    p1 = DynamicPlanner.parse_plan(messy1)
    p2 = DynamicPlanner.parse_plan(messy2)
    assert p1[0]["agent"] == "a"
    assert p2[0]["agent"] == "b"
    print("✅ markdown 代码块 / 前后杂文本均可正确解析\n")


def test_flow_registry_and_static_director():
    """静态测试：流程注册 + 静态工作流调度器接口"""
    print("=" * 60)
    print("【静态测试：流程注册 + StaticWorkflowDirector】")
    print("=" * 60)
    flows = flow_registry.get_flow_list()
    print(f"✅ 已注册静态流程: {[f['name'] for f in flows]}")
    assert any(f['name'] == "article_generation" for f in flows), "缺少 article_generation 流程"

    graph = StaticWorkflowDirector.build_graph("article_generation")
    print(f"✅ 流程 build 成功，图类型: {type(graph).__name__}")
    print("\n✅ 静态工作流调度器接口测试通过\n")


def json_dumps(plan):
    import json
    return json.dumps(plan, ensure_ascii=False)


def test_execute_agent_exception_and_cost():
    """容错测试：Agent 执行异常应转为 RuntimeError（不静默挂死）；正常步骤记录耗时"""
    print("=" * 60)
    print("【容错测试：_execute 异常捕获（卡住/报错不再静默）】")
    print("=" * 60)
    import planner.dynamic_planner as dp_mod

    # 异常 Agent：抛错 → _execute 应转 RuntimeError（日志记 error，上层转 failed）
    def boom(state):
        raise ValueError("模拟 LLM 超时/服务异常")

    with patch.object(dp_mod.registry, "get_run_func", return_value=boom):
        try:
            DynamicPlanner._execute([{"agent": "researcher", "note": "模拟失败步骤"}], {"topic": "x"})
            raised = False
        except RuntimeError as e:
            raised = True
            assert "researcher" in str(e) and "模拟 LLM 超时" in str(e), f"错误信息应含角色与原因: {e}"
    assert raised, "应抛出 RuntimeError"
    print("✅ 异常 Agent 正确转为 RuntimeError（含角色名与原因）")

    # 正常 Agent：应完成且状态更新（顺带验证耗时日志路径不炸）
    def ok_agent(state):
        return {"task_level": "complex"}

    with patch.object(dp_mod.registry, "get_run_func", return_value=ok_agent):
        final = DynamicPlanner._execute([{"agent": "task_router", "note": "正常步骤"}], {"topic": "x"})
    assert final.get("task_level") == "complex" and "exec_plan" in final, "正常执行应更新状态并写入 exec_plan"
    print("✅ 正常步骤执行 + exec_plan 写入正常")
    print("\n✅ _execute 异常捕获测试通过\n")


if __name__ == "__main__":
    test_registry_load()
    test_dynamic_planner_mock_generate()
    test_dynamic_planner_parse_robust()
    test_flow_registry_and_static_director()
    test_execute_agent_exception_and_cost()
