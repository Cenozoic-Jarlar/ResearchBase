"""
[测试] test_resource_browser_system.py — 资源浏览器插件模块
[运行] venv\\Scripts\\python.exe test_resource_browser_system.py
[约定] 不调 LLM、不起 HTTP 服务（直接测 service 纯逻辑）；
       覆盖：分区配置/树遍历/只读拒绝写/写入备份/目录穿越/扩展名白名单/大文件截断
"""
import os
import shutil

from resource_browser import service
from resource_browser.config import RESOURCE_SECTIONS
from core.paths import PROJECT_ROOT, LOCAL_DB, OUTPUT_DIR

# 测试写入目标：输出库（archives 分区、非只读）
TEST_TARGET = os.path.join(OUTPUT_DIR, "00-资源浏览器测试.md")
BAK_TARGET = TEST_TARGET + ".bak"
# 写入用路径（带 root 前缀）
WRITE_PATH = "output/00-资源浏览器测试.md"


def _cleanup():
    for p in (TEST_TARGET, BAK_TARGET):
        if os.path.exists(p):
            os.remove(p)


def test_sections():
    print("=" * 60)
    print("【测试1：分区配置与权限】")
    print("=" * 60)
    keys = [s["key"] for s in RESOURCE_SECTIONS]
    assert keys == ["assets", "archives", "logs"], f"分区顺序应固定：{keys}"
    by_key = {s["key"]: s for s in service.list_sections()}
    assert by_key["assets"]["readonly"] is True
    assert by_key["archives"]["readonly"] is False
    assert by_key["logs"]["readonly"] is True
    print("✅ 三分区齐全，权限：资产=只读/档案=可编辑/日志=只读\n")


def test_tree():
    print("=" * 60)
    print("【测试2：目录树遍历】")
    print("=" * 60)
    assets = service.tree_for_section("assets")
    names = {e["name"] for e in assets}
    assert any(n == "researcher_agent.py" for n in names), "资产树应含 Agent 代码"
    assert any(n == "fact_check_article_flow.py" for n in names), "资产树应含流程代码"
    assert any(n == "write_local_database.py" for n in names), "资产树应含 Skill 代码"
    assert any(n == "md2docx.py" for n in names), "资产树应含工具代码"
    paths = {e["path"] for e in assets}
    assert "agent_registry/agents/researcher_agent.py" in paths, "路径应带 root 前缀"
    assert "main.py" in paths, "单文件 root 的 path 应为文件名"
    assert not any("__pycache__" in e["path"] for e in assets), "树应排除 __pycache__"
    # 目录节点：dir 条目存在且排在子文件之前（父目录在前）
    dirs = {e["path"] for e in assets if e["type"] == "dir"}
    assert "agent_registry/agents" in dirs, "应输出目录节点（agent_registry/agents）"
    assert "planner/flows" in dirs, "应输出目录节点（planner/flows）"
    d_agents = [e for e in assets if e["path"] == "agent_registry/agents"][0]
    f_agent = [e for e in assets if e["path"] == "agent_registry/agents/researcher_agent.py"][0]
    assert assets.index(d_agents) < assets.index(f_agent), "父目录节点应排在子文件之前"
    logs = service.tree_for_section("logs")
    # 日志区按 root 分组：所有条目应带 logs/ 或 archives/ 前缀（文件在 root 直接下时无需子目录节点）
    assert logs and all(e["path"].startswith(("logs/", "archives/")) for e in logs), "日志区应按 root 分组"
    logs = service.tree_for_section("logs")
    log_names = {e["name"] for e in logs}
    assert "运行日志" in {e["name"] for e in logs} or any(n.endswith(".log") for n in log_names), "日志区应含 .log"
    print(f"✅ 资产树 {len(assets)} 条（含 Agent/流程/Skill/工具），日志树 {len(logs)} 条\n")


def test_read_and_escape():
    print("=" * 60)
    print("【测试3：读取 + 目录穿越防护】")
    print("=" * 60)
    # 正常读（资产区读一个确定存在的文件，路径带 root 前缀）
    data = service.read_entry("assets", "agent_registry/agents/researcher_agent.py", max_chars=5000)
    assert "AGENT_META" in data["content"], "应读到 Agent 代码内容"
    # 目录穿越：尝试读 .env
    for bad in ("../../.env", "..\\..\\.env", ".env", "../.env", "agent_registry/../../.env"):
        try:
            service.read_entry("assets", bad)
            assert False, f"应拒绝穿越路径：{bad}"
        except ValueError:
            pass
    # 扩展名白名单：资产区不允许读 .log（不在白名单）
    try:
        service.read_entry("assets", "llm_config.log")
        assert False, "应拒绝白名单外扩展名"
    except ValueError:
        pass
    print("✅ 穿越路径/非法扩展名均被拒绝\n")


def test_write_readonly_denied():
    print("=" * 60)
    print("【测试4：只读分区拒绝写入】")
    print("=" * 60)
    for key in ("assets", "logs"):
        try:
            service.write_entry(key, "x.md", "内容")
            assert False, f"只读分区 {key} 应拒绝写入"
        except PermissionError:
            pass
    print("✅ assets/logs 只读分区写入均被拒绝\n")


def test_write_and_backup():
    print("=" * 60)
    print("【测试5：档案分区写入 + 自动备份】")
    print("=" * 60)
    _cleanup()
    try:
        # 首次写入：新文件，无备份
        r1 = service.write_entry("archives", WRITE_PATH, "第一版内容")
        assert r1["backup"] is None
        with open(TEST_TARGET, encoding="utf-8") as f:
            assert f.read() == "第一版内容"
        # 二次写入：自动备份 .bak，内容更新
        r2 = service.write_entry("archives", WRITE_PATH, "第二版内容")
        assert r2["backup"] == BAK_TARGET
        with open(BAK_TARGET, encoding="utf-8") as f:
            assert f.read() == "第一版内容"
        with open(TEST_TARGET, encoding="utf-8") as f:
            assert f.read() == "第二版内容"
        print("✅ 写入成功、.bak 备份保留上一版、内容更新正确\n")
    finally:
        _cleanup()


def test_truncate():
    print("=" * 60)
    print("【测试6：大文件截断】")
    print("=" * 60)
    _cleanup()
    try:
        with open(TEST_TARGET, "w", encoding="utf-8") as f:
            f.write("x" * 10000)
        data = service.read_entry("archives", WRITE_PATH, max_chars=100)
        assert data["truncated"] is True
        assert len(data["content"]) == 100
        assert data["total"] == 10000
        print("✅ 超长内容正确截断并标记\n")
    finally:
        _cleanup()


if __name__ == "__main__":
    test_sections()
    test_tree()
    test_read_and_escape()
    test_write_readonly_denied()
    test_write_and_backup()
    test_truncate()
    print("=" * 60)
    print("✅ 资源浏览器测试全部通过！")
    print("=" * 60)
