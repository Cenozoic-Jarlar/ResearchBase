"""
[测试] test_fact_check_system.py — 事实审核角色 + 有界修订循环
[运行] venv\\Scripts\\python.exe test_fact_check_system.py
[约定] mock LLM（不调用真实模型）；覆盖：
       1. fact_checker 角色注册与判定解析
       2. 静态流程 fact_check_article：不通过→回溯修订→通过（writer 执行 2 次）
       3. 静态流程上限：连续不通过→达上限强制结束
       4. 动态引擎 _execute：fact_checker 回溯分支（自动 append writer 修订）
       5. 动态引擎上限
"""
import os
from unittest.mock import Mock, patch
from types import SimpleNamespace

os.environ["LLM_API_KEY"] = "fake_test_key"
os.environ["LLM_BASE_URL"] = "https://mock.api.test"
os.environ["LLM_MODELS"] = '[{"name":"router","model":"mock-r","role":"r","capabilities":["text"]},{"name":"standard","model":"mock-s","role":"s","capabilities":["text"]},{"name":"reasoning","model":"mock-m","role":"m","capabilities":["text"]}]'

import langchain_openai
langchain_openai.ChatOpenAI = Mock()

from agent_registry.registry import registry
from planner.flow_registry import flow_registry
from planner.dynamic_planner import DynamicPlanner
from core.paths import FACT_CHECK_MAX_RETRIES


def ok_llm(content="ok"):
    fake = Mock()
    fake.invoke = Mock(return_value=SimpleNamespace(content=content))
    return fake


def seq_llm(contents):
    """按调用顺序依次返回内容的 fake LLM（用于模拟 不通过→通过 判定）"""
    fake = Mock()
    fake.invoke = Mock(side_effect=[SimpleNamespace(content=c) for c in contents])
    return fake


def patch_agents(task_level="complex", writer_resp="文章草稿", fact_resps=("【判定】通过",)):
    """patch 各内容型 Agent 的 LLM（get_llm 返回 fake）；返回 writer/fact_checker 的 fake 便于计数
    writer 用固定响应（可被回溯多次调用），判定由 fact_checker 的序列响应控制"""
    writer_fake = ok_llm(writer_resp)
    fact_fake = seq_llm(fact_resps)
    router_fake = ok_llm(task_level)
    researcher_fake = ok_llm("调研素材")
    return [
        patch("agent_registry.agents.task_router_agent.get_llm", return_value=router_fake),
        patch("agent_registry.agents.researcher_agent.get_llm", return_value=researcher_fake),
        patch("agent_registry.agents.writer_agent.get_llm", return_value=writer_fake),
        patch("agent_registry.agents.fact_checker_agent.get_llm", return_value=fact_fake),
    ], writer_fake, fact_fake


def make_init_state():
    return {
        "topic": "测试主题",
        "task_level": None,
        "research_material": None,
        "human_supplement": None,
        "final_article": None,
    }


def test_fact_checker_role():
    print("=" * 60)
    print("【测试1：fact_checker 角色注册与判定解析】")
    print("=" * 60)
    agents = registry.get_agent_list()
    assert any(a["name"] == "fact_checker" for a in agents), "fact_checker 应已注册"
    # 直接调 run：判定通过
    from agent_registry.agents.fact_checker_agent import run as fc_run
    with patch("agent_registry.agents.fact_checker_agent.get_llm", return_value=ok_llm("无问题\n【判定】通过")):
        st = fc_run({"topic": "T", "final_article": "文章", "value_profiles": []})
    assert st["fact_check_passed"] is True and st["fact_check_count"] == 1
    # 判定不通过 + 计数累加
    with patch("agent_registry.agents.fact_checker_agent.get_llm", return_value=ok_llm("数字有误\n【判定】不通过")):
        st2 = fc_run({"topic": "T", "final_article": "文章", "fact_check_count": 3, "value_profiles": []})
    assert st2["fact_check_passed"] is False and st2["fact_check_count"] == 4
    assert "数字有误" in st2["fact_check_issues"]
    print("✅ 角色注册 + 判定解析（通过/不通过/计数累加）正确\n")


def test_static_fact_check_loop():
    print("=" * 60)
    print("【测试2：静态流程 不通过→回溯修订→通过】")
    print("=" * 60)
    patches, writer_fake, fact_fake = patch_agents(
        fact_resps=("存在编造引用\n【判定】不通过", "已修正\n【判定】通过"))
    graph = flow_registry.build("fact_check_article")
    with patches[0], patches[1], patches[2], patches[3]:
        final = graph.invoke(make_init_state(), config={"configurable": {"thread_id": "fc_loop_1"}})
    assert writer_fake.invoke.call_count == 2, f"writer 应执行 2 次，实际 {writer_fake.invoke.call_count}"
    assert fact_fake.invoke.call_count == 2, f"fact_checker 应执行 2 次，实际 {fact_fake.invoke.call_count}"
    assert final["fact_check_passed"] is True
    assert final["fact_check_count"] == 2
    assert final["final_article"]
    print(f"✅ 修订循环正确：writer×{writer_fake.invoke.call_count}，fact_checker×{fact_fake.invoke.call_count}，最终通过\n")


def test_static_fact_check_max_retries():
    print("=" * 60)
    print("【测试3：静态流程 达上限强制结束】")
    print("=" * 60)
    patches, writer_fake, fact_fake = patch_agents(
        fact_resps=("问题1\n【判定】不通过", "问题2\n【判定】不通过", "问题3\n【判定】不通过"))
    graph = flow_registry.build("fact_check_article")
    with patches[0], patches[1], patches[2], patches[3]:
        final = graph.invoke(make_init_state(), config={"configurable": {"thread_id": "fc_loop_2"}})
    assert final["fact_check_count"] == FACT_CHECK_MAX_RETRIES, \
        f"应达上限 {FACT_CHECK_MAX_RETRIES}，实际 {final['fact_check_count']}"
    assert final["fact_check_passed"] is False, "达上限仍不通过应强制结束"
    assert writer_fake.invoke.call_count == FACT_CHECK_MAX_RETRIES, "writer 应执行 上限 次"
    print(f"✅ 有界循环正确：达上限 {FACT_CHECK_MAX_RETRIES} 次强制结束，无死循环\n")


def test_dynamic_fact_check_loop():
    print("=" * 60)
    print("【测试4：动态引擎 事实审核回溯修订】")
    print("=" * 60)
    plan = [
        {"agent": "task_router", "note": "路由"},
        {"agent": "researcher", "note": "调研"},
        {"agent": "writer", "note": "写作"},
        {"agent": "fact_checker", "note": "事实审核"},
    ]
    patches, writer_fake, fact_fake = patch_agents(
        fact_resps=("编造来源\n【判定】不通过", "已修正\n【判定】通过"))
    with patches[0], patches[1], patches[2], patches[3]:
        final = DynamicPlanner._execute(plan, make_init_state())
    assert writer_fake.invoke.call_count == 2, f"writer 应被回溯执行 2 次，实际 {writer_fake.invoke.call_count}"
    assert fact_fake.invoke.call_count == 2
    assert final["fact_check_passed"] is True
    assert final["fact_check_count"] == 2
    assert final["final_article"]
    print(f"✅ 动态回溯正确：writer×{writer_fake.invoke.call_count}，fact_checker×{fact_fake.invoke.call_count}，最终通过\n")


def test_dynamic_fact_check_max_retries():
    print("=" * 60)
    print("【测试5：动态引擎 达上限强制结束】")
    print("=" * 60)
    plan = [
        {"agent": "writer", "note": "写作"},
        {"agent": "fact_checker", "note": "事实审核"},
    ]
    patches, writer_fake, fact_fake = patch_agents(
        fact_resps=("问题1\n【判定】不通过", "问题2\n【判定】不通过", "问题3\n【判定】不通过"))
    with patches[0], patches[1], patches[2], patches[3]:
        final = DynamicPlanner._execute(plan, make_init_state())
    assert final["fact_check_count"] == FACT_CHECK_MAX_RETRIES
    assert final["fact_check_passed"] is False
    assert writer_fake.invoke.call_count == FACT_CHECK_MAX_RETRIES
    print(f"✅ 动态有界循环正确：达上限 {FACT_CHECK_MAX_RETRIES} 次强制结束\n")


if __name__ == "__main__":
    test_fact_checker_role()
    test_static_fact_check_loop()
    test_static_fact_check_max_retries()
    test_dynamic_fact_check_loop()
    test_dynamic_fact_check_max_retries()
    print("=" * 60)
    print("✅ 事实审核循环测试全部通过！")
    print("=" * 60)
