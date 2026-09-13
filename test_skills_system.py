"""
[测试] test_skills_system.py — Skill 注册 + 主题资料库读写回环 + 调研员读策略
[运行] venv\\Scripts\\python.exe test_skills_system.py
[约定] 真实文件操作（建临时主题库→写→读→清理），AI 提炼摘要走 mock/兜底，不调真实 LLM
"""
import os
import re
import shutil
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ["LLM_API_KEY"] = "fake_test_key"
os.environ["LLM_BASE_URL"] = "https://mock.api.test"
os.environ["LLM_MODELS"] = '[{"name":"router","model":"mock-r","role":"r","capabilities":["text"]},{"name":"standard","model":"mock-s","role":"s","capabilities":["text"]},{"name":"reasoning","model":"mock-m","role":"m","capabilities":["text"]}]'

import langchain_openai
langchain_openai.ChatOpenAI = Mock()

from skills.skill_registry import skill_registry
from core.paths import LOCAL_DB, TOPIC_PREFIX_PATTERN

TEST_TOPIC = "99-测试主题库"


def _clean_test_topic():
    """清理所有去编号后名为"测试主题库"的目录（防编号变体残留）"""
    for name in list(os.listdir(LOCAL_DB)):
        if re.sub(TOPIC_PREFIX_PATTERN, "", name) == "测试主题库":
            shutil.rmtree(os.path.join(LOCAL_DB, name))


def test_skill_registry_load():
    print("=" * 60)
    print("【静态测试：SkillRegistry 自动注册】")
    print("=" * 60)
    skills = skill_registry.get_skill_list()
    names = [s["name"] for s in skills]
    print(f"✅ 注册Skill: {names}")
    expected = {"list_topics", "read_topic_summary", "read_topic_file", "write_local_database"}
    missing = expected - set(names)
    assert not missing, f"缺少Skill: {missing}"
    assert "read_local_database" not in names, "旧的全量读取 Skill 应已移除"
    for s in skills:
        assert s["name"] and s["desc"], f"Skill 元信息不完整: {s}"
        assert "【" in s["desc"] or "参数" in s["desc"] or "使用方法" in s["desc"], \
            f"Skill {s['name']} 缺少写给 LLM 的说明注释"
        assert callable(skill_registry.skills[s["name"]]["run"]), f"Skill {s['name']} 缺少 run 函数"
    print("✅ Skill 注册与元信息校验通过\n")


def test_topic_repo_roundtrip():
    print("=" * 60)
    print("【功能测试：主题库写入→编号→索引→摘要/全文读取 回环】")
    print("=" * 60)
    _clean_test_topic()
    write = skill_registry.get_run_func("write_local_database")
    try:
        # 写入短文件（显式传 summary，避免走 AI 提炼）
        r1 = write("政策要点", "这是短内容测试：2026年政策要点A。", topic=TEST_TOPIC,
                   mode="overwrite", summary="测试摘要A")
        print(f"✅ 写入1: {r1}")
        assert "已写入" in r1 and "测试主题库" in r1 and "01-政策要点.md" in r1

        # 验证文件自动编号 + _repo.md 索引
        repo_dir = os.path.join(LOCAL_DB, TEST_TOPIC)
        files = [f for f in os.listdir(repo_dir) if f.endswith((".md", ".txt")) and not f.startswith("_")]
        assert any(f.startswith("01-") for f in files), f"文件应自动补编号: {files}"
        meta = open(os.path.join(repo_dir, "_repo.md"), encoding="utf-8").read()
        assert "测试摘要A" in meta, "摘要应写入 _repo.md 索引"
        assert "- 文件数：1" in meta, "文件数应更新为 1"

        # 短文件：摘要读取应自动含全文
        summary = skill_registry.get_run_func("read_topic_summary")(TEST_TOPIC)
        assert "2026年政策要点A" in summary, "短文件摘要读取应含全文"
        print("✅ 短文件摘要读取自动含全文")

        # 单文件全文读取
        fname = [f for f in files if f.startswith("01-")][0]
        full = skill_registry.get_run_func("read_topic_file")(TEST_TOPIC, fname)
        assert "短内容测试" in full, "单文件全文读取失败"
        print(f"✅ 单文件全文读取: {fname}")

        # list_topics 应包含该主题库
        overview = skill_registry.get_run_func("list_topics")()
        assert "测试主题库" in overview, "list_topics 应列出新建主题库"
        print("✅ list_topics 概览包含新主题库")
    finally:
        _clean_test_topic()
    print("✅ 主题库回环测试通过\n")


def test_write_append_and_count():
    print("=" * 60)
    print("【功能测试：追加模式 + 文件数自动更新】")
    print("=" * 60)
    _clean_test_topic()
    write = skill_registry.get_run_func("write_local_database")
    try:
        write("文件一", "内容一", topic=TEST_TOPIC, summary="摘要1")
        write("文件二", "内容二", topic=TEST_TOPIC, summary="摘要2")
        write("文件一", "内容一覆盖版", topic=TEST_TOPIC, mode="overwrite", summary="摘要1v2")

        repo_dir = os.path.join(LOCAL_DB, TEST_TOPIC)
        meta = open(os.path.join(repo_dir, "_repo.md"), encoding="utf-8").read()
        assert "- 文件数：2" in meta, f"文件数应更新为 2（覆盖不增数）：\n{meta}"
        assert meta.count("| 摘要：") == 2, "索引应恰好 2 条（同文件去重）"
        f1 = open(os.path.join(repo_dir, "01-文件一.md"), encoding="utf-8").read()
        assert "覆盖版" in f1, "覆盖模式应写入新内容"
        print("✅ 追加/覆盖/文件数/索引去重全部正确")
    finally:
        _clean_test_topic()
    print("✅ 追加与计数测试通过\n")


def test_ai_summary_fallback():
    print("=" * 60)
    print("【功能测试：不传 summary 时 AI 提炼（mock 兜底首行）】")
    print("=" * 60)
    _clean_test_topic()
    write = skill_registry.get_run_func("write_local_database")
    try:
        # ChatOpenAI 已被 mock，llm_simple.invoke 返回 Mock → 兜底取首行
        r = write("无摘要文件", "首行核心信息\n第二行补充", topic=TEST_TOPIC, mode="overwrite")
        meta = open(os.path.join(LOCAL_DB, TEST_TOPIC, "_repo.md"), encoding="utf-8").read()
        assert "首行核心信息" in meta, "应兜底用首行作为摘要"
        print(f"✅ AI 提炼兜底正常: {r}")
    finally:
        _clean_test_topic()
    print("✅ 摘要兜底测试通过\n")


def test_researcher_topic_flow():
    print("=" * 60)
    print("【集成测试：调研员主题读策略（概览→选主题→摘要→素材）】")
    print("=" * 60)
    _clean_test_topic()
    write = skill_registry.get_run_func("write_local_database")
    write("调研资料", "本主题用于测试调研员读取：包含关键事实XYZ。", topic=TEST_TOPIC, summary="调研测试摘要")
    try:
        from agent_registry.agents import researcher_agent

        def fake_llm_invoke(prompt):
            if "主题库概览" in prompt:
                return SimpleNamespace(content=f'["{TEST_TOPIC}"]')
            return SimpleNamespace(content='{"material": "整理后的素材：关键事实XYZ。", "need_full": []}')

        with patch.object(researcher_agent, "get_llm", return_value=SimpleNamespace(invoke=fake_llm_invoke)):
            state = {"topic": "测试调研任务", "task_level": "complex"}
            result = researcher_agent.run(state)
        assert "关键事实XYZ" in result["research_material"], f"素材应包含摘要中的事实: {result}"
        print("✅ 调研员：概览→选主题→读摘要→整理素材，全链路正常")
    finally:
        _clean_test_topic()
    print("✅ 调研员读策略测试通过\n")


def test_archivist_summary():
    print("=" * 60)
    print("【集成测试：归档员 成稿→要点摘要→入库（全文不入库）】")
    print("=" * 60)
    _clean_test_topic()
    try:
        from agent_registry.agents import archivist_agent

        # mock 提炼摘要：返回结构化要点（不含成稿正文）
        fake_llm = SimpleNamespace(invoke=lambda p: SimpleNamespace(
            content="- 核心结论：三远法是宋代山水画的空间观\n- 章节结构：一、定义 / 二、美学思想"))
        with patch.object(archivist_agent, "get_llm", return_value=fake_llm):
            result = archivist_agent.run({
                "topic": TEST_TOPIC,
                "final_article": "这是成稿正文全文，不应被完整写入资料库。",
                "domain": None,
            })
        assert "已写入" in result["archive_result"], result

        repo_dir = os.path.join(LOCAL_DB, TEST_TOPIC)
        files = [f for f in os.listdir(repo_dir) if not f.startswith("_")]
        assert files and "研究要点" in files[0], f"应写入研究要点文件: {files}"
        saved = open(os.path.join(repo_dir, files[0]), encoding="utf-8").read()
        assert "核心结论" in saved and "三远法" in saved, f"应写入提炼后的要点摘要: {saved[:100]}"
        assert "不应被完整写入资料库" not in saved, "全文不得入库（只存要点摘要）"
        meta = open(os.path.join(repo_dir, "_repo.md"), encoding="utf-8").read()
        assert "核心结论" in meta, "索引摘要应使用要点内容"
        print(f"✅ 归档员入库文件: {files[0]}（内容为要点摘要，非全文）")
    finally:
        _clean_test_topic()

    # 提炼失败降级：不阻断流程，截取原文开头
    from agent_registry.agents import archivist_agent
    with patch.object(archivist_agent, "get_llm", return_value=SimpleNamespace(invoke=lambda p: (_ for _ in ()).throw(RuntimeError("模型异常")))):
        result = archivist_agent.run({"topic": TEST_TOPIC, "final_article": "降级测试文章正文内容。", "domain": None})
    assert "已写入" in result["archive_result"], f"失败降级不应阻断: {result}"
    print("✅ 摘要提炼失败降级正常（截取开头入库）")
    print("✅ 归档员摘要测试通过\n")


if __name__ == "__main__":
    test_skill_registry_load()
    test_topic_repo_roundtrip()
    test_write_append_and_count()
    test_ai_summary_fallback()
    test_researcher_topic_flow()
    test_archivist_summary()
