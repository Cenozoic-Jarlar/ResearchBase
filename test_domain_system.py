"""
[测试] test_domain_system.py — 主题域（domain）隔离 + 配置 + 管理
[运行] venv\\Scripts\\python.exe test_domain_system.py
[约定] 真实文件操作（建测试域→写→读→清理），不调真实 LLM；
       只清理本测试创建的域（域甲/域乙/_隐藏测试域）与测试主题库，不动 _模板域/用户真实域
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
from core.paths import (LOCAL_DB, DOMAINS_ROOT, DOMAIN_CONFIG_FILE, TOPIC_PREFIX_PATTERN,
                        local_db_root, output_root, archive_root, list_domains,
                        is_reserved_domain_name, ensure_domain_dirs)
from core import domain_config
from core.domain_config import (read_domain_config, default_profiles_for,
                                create_domain, rename_domain, list_domains_with_stats)

TEST_TOPIC = "99-域隔离测试库"
TEST_DOMAINS = ("域甲", "域乙", "域丙", "_隐藏测试域")
TEMPLATE_DOMAIN = "_模板域"


def _clean_test_data():
    """清理测试域目录 + 通用层/测试域内残留的测试主题库（按去编号名匹配）"""
    for d in TEST_DOMAINS:
        dpath = os.path.join(DOMAINS_ROOT, d)
        if os.path.isdir(dpath):
            shutil.rmtree(dpath)
    for root in [LOCAL_DB] + [local_db_root(d) for d in TEST_DOMAINS]:
        if not os.path.isdir(root):
            continue
        for name in list(os.listdir(root)):
            if re.sub(TOPIC_PREFIX_PATTERN, "", name) == "域隔离测试库":
                shutil.rmtree(os.path.join(root, name))


def test_path_functions():
    print("=" * 60)
    print("【静态测试：域路径解析函数（local_db_root / output_root / archive_root）】")
    print("=" * 60)
    assert local_db_root() == LOCAL_DB, "无域应指向通用层 LocalDataBase"
    assert local_db_root(None) == LOCAL_DB
    assert local_db_root("general") == LOCAL_DB, "general 归一化为通用层"
    assert local_db_root("") == LOCAL_DB
    assert local_db_root("域甲") == os.path.join(DOMAINS_ROOT, "域甲", "LocalDataBase")
    assert output_root("域甲") == os.path.join(DOMAINS_ROOT, "域甲", "output")
    assert archive_root("域甲") == os.path.join(DOMAINS_ROOT, "域甲", "archives")
    assert local_db_root("GENERAL") == LOCAL_DB, "域名大小写不敏感"
    print("✅ 路径解析函数全部正确")

    print("=" * 60)
    print("【静态测试：域名保留校验 is_reserved_domain_name】")
    print("=" * 60)
    assert is_reserved_domain_name("") and is_reserved_domain_name(None)
    assert is_reserved_domain_name("general") and is_reserved_domain_name("GENERAL")
    assert is_reserved_domain_name("_模板域"), "下划线开头=保留（隐藏）"
    assert not is_reserved_domain_name("工作A"), "普通域名不保留"
    print("✅ 保留名校验正确")
    print("✅ 路径与保留名测试通过\n")


def test_domain_registration_hidden():
    print("=" * 60)
    print("【功能测试：域自动注册 + 下划线隐藏（模板域不显示）】")
    print("=" * 60)
    _clean_test_data()
    try:
        ensure_domain_dirs("域甲")
        os.makedirs(os.path.join(DOMAINS_ROOT, "_隐藏测试域"), exist_ok=True)
        assert TEMPLATE_DOMAIN in os.listdir(DOMAINS_ROOT), "模板域应存在于磁盘"
        names = list_domains()
        assert "域甲" in names, f"真实域应注册: {names}"
        assert TEMPLATE_DOMAIN not in names, f"模板域应隐藏: {names}"
        assert "_隐藏测试域" not in names, f"下划线目录应隐藏: {names}"
        print(f"✅ 注册列表（模板/下划线已隐藏）: {names}")
    finally:
        _clean_test_data()
    print("✅ 域注册与隐藏测试通过\n")


def test_domain_isolation_write_read():
    print("=" * 60)
    print("【功能测试：域隔离——写域甲，通用层/其他域不可见，域甲可读】")
    print("=" * 60)
    _clean_test_data()
    write = skill_registry.get_run_func("write_local_database")
    try:
        r = write("域内资料", "这是域甲独有内容：隔离标记XYZ。", topic=TEST_TOPIC,
                  mode="overwrite", summary="域甲摘要", domain="域甲")
        assert "已写入主题库" in r, r
        repo_dir = os.path.join(DOMAINS_ROOT, "域甲", "LocalDataBase", TEST_TOPIC)
        assert os.path.isdir(repo_dir), f"应写入 domains/域甲/LocalDataBase/: {repo_dir}"
        print(f"✅ 写入域甲: {r}")

        overview_general = skill_registry.get_run_func("list_topics")()
        assert "域隔离测试库" not in overview_general, "通用层概览不应泄漏域内主题"
        print("✅ 通用层看不到域甲主题（隔离生效）")

        overview_domain = skill_registry.get_run_func("list_topics")("域甲")
        assert "域隔离测试库" in overview_domain, "域甲概览应含本域主题"
        print("✅ 域甲概览含本域主题（域内+通用合并）")

        summary = skill_registry.get_run_func("read_topic_summary")(TEST_TOPIC, "域甲")
        assert "隔离标记XYZ" in summary, "域甲摘要读取应含全文"
        files = [f for f in os.listdir(repo_dir) if f.endswith((".md", ".txt")) and not f.startswith("_")]
        full = skill_registry.get_run_func("read_topic_file")(TEST_TOPIC, files[0], "域甲")
        assert "隔离标记XYZ" in full, "域甲单文件全文读取失败"
        print("✅ 域甲摘要/全文读取正常")

        assert "【提示】主题库" in skill_registry.get_run_func("read_topic_summary")(TEST_TOPIC), \
            "无域（通用层）不应读到域甲主题"
        print("✅ 通用层读不到域甲主题（反向隔离生效）")
    finally:
        _clean_test_data()
    print("✅ 域隔离读写测试通过\n")


def test_domain_general_fallback():
    print("=" * 60)
    print("【功能测试：读取回退——域内没有时回退通用层】")
    print("=" * 60)
    _clean_test_data()
    write = skill_registry.get_run_func("write_local_database")
    try:
        write("通用资料", "通用层内容：共享事实ABC。", topic=TEST_TOPIC, mode="overwrite", summary="通用摘要")
        summary = skill_registry.get_run_func("read_topic_summary")(TEST_TOPIC, "域甲")
        assert "共享事实ABC" in summary, "域内未命中应回退读取通用层"
        overview = skill_registry.get_run_func("list_topics")("域甲")
        assert "域隔离测试库" in overview, "域甲概览应含通用层主题"
        print("✅ 域内未命中自动回退通用层；域概览含通用层主题（合并读取）")
    finally:
        _clean_test_data()
    print("✅ 域→通用层回退测试通过\n")


def test_researcher_domain_pass():
    print("=" * 60)
    print("【集成测试：调研员把 state.domain 传给 Skill】")
    print("=" * 60)
    _clean_test_data()
    write = skill_registry.get_run_func("write_local_database")
    try:
        write("域内调研资料", "域甲调研内容：核心事实KKK。", topic=TEST_TOPIC, mode="overwrite",
              summary="域甲调研摘要", domain="域甲")
        from agent_registry.agents import researcher_agent

        calls = []

        def fake_llm_invoke(prompt):
            if "主题库概览" in prompt:
                return SimpleNamespace(content=f'["{TEST_TOPIC}"]')
            return SimpleNamespace(content='{"material": "素材：核心事实KKK。", "need_full": []}')

        orig_list = skill_registry.get_run_func("list_topics")
        orig_summary = skill_registry.get_run_func("read_topic_summary")

        def spy_list(domain=None):
            calls.append(("list_topics", domain))
            return orig_list(domain)

        def spy_summary(topic, domain=None):
            calls.append(("read_topic_summary", domain))
            return orig_summary(topic, domain)

        with patch.object(skill_registry, "get_run_func",
                          side_effect=lambda n: {"list_topics": spy_list, "read_topic_summary": spy_summary}.get(n, orig_list)):
            with patch.object(researcher_agent, "get_llm", return_value=SimpleNamespace(invoke=fake_llm_invoke)):
                state = {"topic": "域调研任务", "task_level": "complex", "domain": "域甲"}
                result = researcher_agent.run(state)

        assert "核心事实KKK" in result["research_material"], f"应读到域甲资料: {result}"
        assert ("list_topics", "域甲") in calls and ("read_topic_summary", "域甲") in calls, f"域传递: {calls}"
        print(f"✅ 调研员域传递正常：{calls}")
    finally:
        _clean_test_data()
    print("✅ 调研员域传递测试通过\n")


def test_domain_config_parse():
    print("=" * 60)
    print("【功能测试：_domain.md 配置解析（域简介/默认价值观/风格偏好）】")
    print("=" * 60)
    _clean_test_data()
    try:
        # 建域 → 模板存在；未填写时默认空
        msg = create_domain("域甲", intro="测试域")
        assert "已创建域" in msg, msg
        assert os.path.exists(os.path.join(DOMAINS_ROOT, "域甲", DOMAIN_CONFIG_FILE)), "应生成 _domain.md"
        assert os.path.isdir(os.path.join(DOMAINS_ROOT, "域甲", "LocalDataBase")), "应生成骨架子目录"
        assert os.path.isdir(os.path.join(DOMAINS_ROOT, "域甲", "output"))
        assert os.path.isdir(os.path.join(DOMAINS_ROOT, "域甲", "archives"))
        assert default_profiles_for("域甲") == [], "未填默认价值观应为空"
        print("✅ 建域生成骨架 + 配置模板（默认空）")

        # 用户填写配置 → 解析生效
        cfg_path = os.path.join(DOMAINS_ROOT, "域甲", DOMAIN_CONFIG_FILE)
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write("域简介：测试域介绍\n默认价值观：policy, technology\n风格偏好：简洁务实\n")
        cfg = read_domain_config("域甲")
        assert cfg["intro"] == "测试域介绍"
        assert cfg["default_profiles"] == ["policy", "technology"], f"默认价值观解析: {cfg}"
        assert cfg["style"] == "简洁务实"
        assert default_profiles_for("域甲") == ["policy", "technology"]
        print(f"✅ 配置解析: {cfg}")

        # 重复建域幂等 + 保留名拒绝
        msg2 = create_domain("域甲")
        assert "已存在" in msg2, msg2
        assert "保留名" in create_domain("general")
        assert "保留名" in create_domain("_模板域")
        assert "不能为空" in create_domain("")
        print("✅ 建域幂等与保留名拒绝正常")
    finally:
        _clean_test_data()
    print("✅ 域配置解析测试通过\n")


def test_domain_rename():
    print("=" * 60)
    print("【功能测试：域重命名（成功/重名拒绝/保留名拒绝/不存在）】")
    print("=" * 60)
    _clean_test_data()
    try:
        create_domain("域甲", intro="待改名")
        ok, msg = rename_domain("域甲", "域乙")
        assert ok, msg
        assert not os.path.isdir(os.path.join(DOMAINS_ROOT, "域甲")), "旧目录应已移动"
        assert os.path.isdir(os.path.join(DOMAINS_ROOT, "域乙")), "新目录应存在"
        print(f"✅ 重命名成功: {msg}")

        # 配置随目录一起移动
        assert os.path.exists(os.path.join(DOMAINS_ROOT, "域乙", DOMAIN_CONFIG_FILE)), "配置应随目录移动"
        assert "域乙" in list_domains() and "域甲" not in list_domains()
        print("✅ 配置随目录迁移，注册列表已更新")

        # 重名拒绝
        create_domain("域丙")
        ok, msg = rename_domain("域乙", "域丙")
        assert not ok and "已存在" in msg, msg
        # 保留名拒绝
        ok, msg = rename_domain("域乙", "general")
        assert not ok and "保留名" in msg, msg
        # 不存在
        ok, msg = rename_domain("不存在域", "域丁")
        assert not ok and "不存在" in msg, msg
        # 相同名
        ok, msg = rename_domain("域乙", "域乙")
        assert not ok, msg
        print("✅ 重名/保留名/不存在/同名 全部正确拒绝")
    finally:
        _clean_test_data()
    print("✅ 域重命名测试通过\n")


def test_domain_stats():
    print("=" * 60)
    print("【功能测试：域概览统计（主题库数/文件数）】")
    print("=" * 60)
    _clean_test_data()
    write = skill_registry.get_run_func("write_local_database")
    try:
        write("资料一", "内容一", topic=TEST_TOPIC, mode="overwrite", summary="s", domain="域甲")
        stats = list_domains_with_stats()
        assert stats["域甲"]["topics"] == 1 and stats["域甲"]["files"] == 1, f"域甲统计: {stats}"
        assert "general" in stats, f"通用层应在统计中: {stats}"
        assert "_模板域" not in stats, "模板域不应出现在统计中"
        print(f"✅ 域统计: {stats}")
    finally:
        _clean_test_data()
    print("✅ 域概览统计测试通过\n")


def test_domain_default_profiles_inject():
    print("=" * 60)
    print("【集成测试：域默认价值观注入（显式 > 域默认 > 关键词 > general）】")
    print("=" * 60)
    _clean_test_data()
    try:
        from web_gui.services.task_manager import make_init_state

        # 未配置域默认 → 回退关键词自动匹配/general
        create_domain("域甲")
        state = make_init_state("某个无关主题", domain="域甲")
        assert state["domain"] == "域甲"
        names = [p.get("name") for p in state["value_profiles"]]
        assert "general" in names or any("user_prefs" == n for n in names), f"应有兜底价值观: {names}"
        print(f"✅ 无域默认时自动回退: {names}")

        # 配置域默认 → 注入域默认框架（显式 > 域默认）
        cfg_path = os.path.join(DOMAINS_ROOT, "域甲", DOMAIN_CONFIG_FILE)
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write("默认价值观：policy\n")
        state2 = make_init_state("某个无关主题", domain="域甲")
        names2 = [p.get("name") for p in state2["value_profiles"]]
        assert "policy" in names2, f"域默认应注入 policy: {names2}"
        print(f"✅ 域默认价值观注入生效: {names2}")

        # 显式选择 > 域默认
        state3 = make_init_state("某个无关主题", profiles=["technology"], domain="域甲")
        names3 = [p.get("name") for p in state3["value_profiles"]]
        assert "technology" in names3 and "policy" not in names3, f"显式应覆盖域默认: {names3}"
        print(f"✅ 显式选择覆盖域默认: {names3}")

        # 通用层（无域）不受域配置影响
        state4 = make_init_state("某个无关主题")
        assert state4["domain"] is None
        print("✅ 通用层无域默认注入")
    finally:
        _clean_test_data()
    print("✅ 域默认价值观注入测试通过\n")


if __name__ == "__main__":
    test_path_functions()
    test_domain_registration_hidden()
    test_domain_isolation_write_read()
    test_domain_general_fallback()
    test_researcher_domain_pass()
    test_domain_config_parse()
    test_domain_rename()
    test_domain_stats()
    test_domain_default_profiles_inject()
    print("=" * 60)
    print("✅ 主题域（隔离+配置+管理）测试全部通过")
    print("=" * 60)
