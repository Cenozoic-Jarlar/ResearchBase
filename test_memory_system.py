"""
[测试] test_memory_system.py — 记忆与价值观体系
[运行] venv\\Scripts\\python.exe test_memory_system.py
[约定] 纯离线：框架注册/选择/注入/格式化全部无 LLM 依赖；不触碰真实记忆文件
"""
import os

os.environ["LLM_API_KEY"] = "fake_test_key"
os.environ["LLM_BASE_URL"] = "https://mock.api.test"
os.environ["LLM_MODELS"] = '[{"name":"router","model":"mock-r","role":"r","capabilities":["text"]},{"name":"standard","model":"mock-s","role":"s","capabilities":["text"]},{"name":"reasoning","model":"mock-m","role":"m","capabilities":["text"]}]'

import langchain_openai
langchain_openai.ChatOpenAI = __import__("unittest.mock", fromlist=["Mock"]).Mock()

from memory.memory_registry import (
    memory_registry, select_profiles, inject_value_profiles, format_values_for,
    sediment_task_memory,
)


def test_registry():
    print("=" * 60)
    print("【测试：价值观框架自动注册】")
    print("=" * 60)
    names = {p["name"] for p in memory_registry.get_profile_list()}
    assert {"general", "policy", "technology", "humanities", "cute_style"} <= names, names
    print(f"✅ 已注册框架: {sorted(names)}\n")


def test_select_profiles():
    print("=" * 60)
    print("【测试：框架选择（显式>自动>通用）】")
    print("=" * 60)
    # 关键词自动匹配
    p = select_profiles("北京市小升初政策2026年变化")
    assert p and p[0]["name"] == "policy", f"政策主题应匹配 policy: {p}"
    p = select_profiles("大模型Agent原理分析")
    assert p and p[0]["name"] == "technology", "科技主题应匹配 technology"
    p = select_profiles("城市文化变迁与人文关怀")
    assert p and p[0]["name"] == "humanities", "人文主题应匹配 humanities"
    # 无命中 → 通用兜底
    p = select_profiles("随便一个不相关主题xyz")
    assert p and p[0]["name"] == "general", "无命中应兜底 general"
    # 显式指定优先（风格框架只能显式加载）
    p = select_profiles("小升初政策", explicit=["cute_style"])
    assert p and p[0]["name"] == "cute_style", "显式指定应优先于自动匹配"
    # 叠加：主题 + 风格 多框架同用
    p = select_profiles("小升初政策", explicit=["policy", "cute_style"])
    assert {x["name"] for x in p} == {"policy", "cute_style"}, "应支持多框架叠加"
    # 空框架不参与自动匹配
    p = select_profiles("小升初政策")
    assert all(x.get("values") for x in p), "自动匹配不应选中空框架"
    print("✅ 选择优先级/叠加/空框架规则全部正确\n")


def test_inject_and_format():
    print("=" * 60)
    print("【测试：任务注入 + 维度格式化】")
    print("=" * 60)
    state = inject_value_profiles({"topic": "小升初政策2026年"})
    assert "value_profiles" in state and state["value_profiles"], "应注入 value_profiles"
    names = {p["name"] for p in state["value_profiles"]}
    assert "policy" in names, f"应含 policy: {names}"
    assert "user_prefs" in names, "应附加用户长期偏好"

    # 维度消费：writer 消费全维度，task_router 不消费
    text_writer = format_values_for(state["value_profiles"], ["stance", "evidence", "style", "critique"])
    assert "立场" in text_writer or "证据" in text_writer or "style" in text_writer, text_writer
    text_router = format_values_for(state["value_profiles"], [])
    assert text_router == "", "未声明维度应返回空"
    print(f"✅ 注入成功，writer 视角价值观片段：{text_writer.splitlines()[0] if text_writer else ''} ...\n")


def test_memory_advisor_run():
    print("=" * 60)
    print("【测试：记忆顾问 Agent 集成】")
    print("=" * 60)
    from agent_registry.agents.memory_advisor_agent import run as advisor_run
    result = advisor_run({"topic": "大模型技术趋势", "profiles": ["cute_style"]})
    assert "value_profiles" in result
    names = {p["name"] for p in result["value_profiles"]}
    assert "cute_style" in names, "显式指定应生效"
    assert "advisor_note" in result, "应返回说明"
    print(f"✅ 记忆顾问注入成功：{result['advisor_note']}\n")


def test_memory_advisor_keep_existing():
    """防覆盖：启动钩子已注入显式框架时，记忆顾问保留不重新自动匹配（防 cute_style 被主题覆盖）"""
    print("=" * 60)
    print("【测试：记忆顾问保留已注入框架（防覆盖）】")
    print("=" * 60)
    from agent_registry.agents.memory_advisor_agent import run as advisor_run
    # 模拟 make_init_state 已注入 cute_style（显式风格），主题却是"宋朝文化"（会自动匹配 humanities）
    state = {"topic": "宋朝的文化风气",
             "value_profiles": [{"name": "cute_style", "dimension": "style", "values": {"style": "可爱"}}]}
    result = advisor_run(state)
    names = {p["name"] for p in result["value_profiles"]}
    assert "cute_style" in names, f"已注入的 cute_style 应被保留: {names}"
    assert "humanities" not in names, f"不得被主题自动匹配覆盖为 humanities: {names}"
    assert "保留" in result["advisor_note"], "说明应标注保留"
    print(f"✅ 已注入框架保留成功：{result['advisor_note']}\n")


def test_sediment_task_memory():
    print("=" * 60)
    print("【测试：长期记忆沉淀（写入/追加/排除 user_prefs/上限截断/容错）】")
    print("=" * 60)
    import tempfile
    import shutil
    from pathlib import Path
    from unittest.mock import patch
    from memory import memory_registry as mr

    tmp = Path(tempfile.mkdtemp())
    try:
        history = tmp / "task_history.md"
        with open(history, "w", encoding="utf-8") as f:
            f.write("# 任务历史\n\n> 占位说明\n")

        state = {"topic": "宋代山水画美学研究", "domain": "人文",
                 "value_profiles": [{"name": "humanities"}, {"name": "user_prefs"}],
                 "final_article": "成稿正文"}
        with patch.object(mr, "MEMORY_FOLDER", tmp):
            line = sediment_task_memory(state, {"engine": "dynamic", "flow_name": ""})
        assert line and "宋代山水画美学研究" in line and "人文" in line, f"应含主题与域: {line}"
        assert "humanities" in line and "user_prefs" not in line, f"价值观应含 humanities 且排除 user_prefs: {line}"
        assert "成稿：是" in line, f"应标记成稿: {line}"
        text1 = history.read_text(encoding="utf-8")
        assert "占位说明" in text1 and line in text1, "记录应追加在占位说明之后"
        print(f"✅ 沉淀写入: {line}")

        # 再次沉淀 → 追加两条
        with patch.object(mr, "MEMORY_FOLDER", tmp):
            sediment_task_memory({"topic": "第二主题", "domain": None, "value_profiles": [], "final_article": ""},
                                 {"engine": "static"})
        text2 = history.read_text(encoding="utf-8")
        assert text2.count("主题：") == 2, f"应追加为两条: {text2}"
        assert "域：general" in text2 and "成稿：否" in text2, "无域/无成稿应记默认值"
        print("✅ 追加 + 默认值正确")

        # 上限截断：仅保留最近 N 条
        with patch.object(mr, "MEMORY_FOLDER", tmp), patch.object(mr, "TASK_HISTORY_MAX_LINES", 3):
            for i in range(5):
                sediment_task_memory({"topic": f"主题{i}", "domain": None}, {})
        text3 = history.read_text(encoding="utf-8")
        assert text3.count("主题：") == 3, f"应只保留最近 3 条: {text3}"
        assert "主题4" in text3 and "主题0" not in text3, "应保留最新记录"
        print("✅ 上限截断正确")

        # 容错：空 state 不抛异常
        with patch.object(mr, "MEMORY_FOLDER", tmp):
            empty = sediment_task_memory({}, {})
        assert empty and "主题：-" in empty, "空 state 应返回默认行"
        print("✅ 空 state 容错正常")
    finally:
        shutil.rmtree(str(tmp), ignore_errors=True)
    print("✅ 长期记忆沉淀测试通过\n")


if __name__ == "__main__":
    test_registry()
    test_select_profiles()
    test_inject_and_format()
    test_memory_advisor_run()
    test_memory_advisor_keep_existing()
    test_sediment_task_memory()
