"""
[测试] test_flow_system.py — 静态流程注册 + 图构建
[运行] venv\\Scripts\\python.exe test_flow_system.py
[约定] 不执行流程（不触发 LLM / interrupt），仅验证 planner/flows/ 扫描、
       FLOW_META 加载与全部流程图构建
"""
import os
from unittest.mock import Mock

os.environ["LLM_API_KEY"] = "fake_test_key"
os.environ["LLM_BASE_URL"] = "https://mock.api.test"
os.environ["LLM_MODELS"] = '[{"name":"router","model":"mock-r","role":"r","capabilities":["text"]},{"name":"standard","model":"mock-s","role":"s","capabilities":["text"]},{"name":"reasoning","model":"mock-m","role":"m","capabilities":["text"]}]'

import langchain_openai
langchain_openai.ChatOpenAI = Mock()

from planner.flow_registry import flow_registry


def test_flow_registry_load():
    print("=" * 60)
    print("【静态测试：FlowRegistry 自动注册】")
    print("=" * 60)
    flows = flow_registry.get_flow_list()
    names = [f["name"] for f in flows]
    print(f"✅ 注册流程: {names}")
    expected = {"article_generation", "quick_article", "critical_article",
                "comprehensive_research", "knowledge_archiving"}
    missing = expected - set(names)
    assert not missing, f"缺少流程: {missing}"
    assert len(flows) >= len(expected), "流程数量不足"
    for f in flows:
        assert f["name"] and f["desc"], f"流程元信息不完整: {f}"
        assert callable(flow_registry.flows[f["name"]]["build"]), f"流程 {f['name']} 缺少 build 函数"
    print("✅ 流程注册与元信息校验通过\n")


def test_flow_build():
    print("=" * 60)
    print("【静态测试：全部流程 build 构建 LangGraph 图】")
    print("=" * 60)
    for f in flow_registry.get_flow_list():
        graph = flow_registry.build(f["name"])
        print(f"✅ {f['name']}: {type(graph).__name__}")
        assert hasattr(graph, "invoke"), f"流程 {f['name']} 编译图应具备 invoke"
    print("✅ 全部流程图构建测试通过\n")


def test_flow_missing_error():
    print("=" * 60)
    print("【静态测试：不存在流程的报错】")
    print("=" * 60)
    try:
        flow_registry.build("not_exist_flow")
        assert False, "应抛出 KeyError"
    except KeyError as e:
        print(f"✅ 正确抛出 KeyError: {e}")
    print("✅ 错误处理测试通过\n")


if __name__ == "__main__":
    test_flow_registry_load()
    test_flow_build()
    test_flow_missing_error()
