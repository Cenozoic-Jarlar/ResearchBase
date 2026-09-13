"""
[测试] test_collector_system.py — 资料采集入库链路（含智能归一与合并）
[运行] venv\\Scripts\\python.exe test_collector_system.py
[约定] URL 抓取 mock requests；本地文件与主题库为真实操作（用完清理）；不调真实 LLM；
       fake LLM 按 prompt 关键词分流（整理/归一/决策/合并四类响应）
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
from core.paths import LOCAL_DB

TEST_TOPIC = "99-采集测试库"
TMP_FILE = "collector_tmp.txt"

HTML_SAMPLE = """
<html><head><script>var bad='noise';</script><style>.x{}</style></head>
<body><nav>导航菜单</nav><h1>标题示例</h1><p>核心内容ABC这是正文。</p><footer>版权页脚</footer></body></html>
"""


def _clean_test_topic():
    for name in list(os.listdir(LOCAL_DB)):
        clean = re.sub(r"^\d{1,3}-", "", name)
        if clean in ("采集测试库", "测试美学库"):  # 测试专用库（含预置同义库），跑完必清理防污染真实资料
            shutil.rmtree(os.path.join(LOCAL_DB, name))


def _topic_dir():
    for name in sorted(os.listdir(LOCAL_DB)):
        if os.path.isdir(os.path.join(LOCAL_DB, name)) and re.sub(r"^\d{1,3}-", "", name) == "采集测试库":
            return os.path.join(LOCAL_DB, name)
    return None


def _make_fake_llm(organize_text, topic_obj=None, decide_obj=None, merge_text=None, holder=None):
    """按 prompt 关键词分流返回不同响应的 fake LLM"""
    def invoke(prompt):
        if "资料库管理员" in prompt and topic_obj is not None:
            return SimpleNamespace(content=__import__("json").dumps(topic_obj, ensure_ascii=False))
        if "现有文件如下" in prompt and decide_obj is not None:
            return SimpleNamespace(content=__import__("json").dumps(decide_obj, ensure_ascii=False))
        if "合并为一份完整资料" in prompt and merge_text is not None:
            return SimpleNamespace(content=merge_text)
        return SimpleNamespace(content=organize_text)
    return SimpleNamespace(invoke=invoke)


def test_fetch_url_content():
    print("=" * 60)
    print("【测试：URL 抓取与正文提取（mock requests）】")
    print("=" * 60)
    import skills.fetch_url_content as mod

    fake_resp = SimpleNamespace(
        text=HTML_SAMPLE, encoding="utf-8",
        raise_for_status=lambda: None,
    )
    with patch.object(mod.requests, "get", return_value=fake_resp):
        body = skill_registry.get_run_func("fetch_url_content")("https://example.com/a")
    assert "核心内容ABC" in body, "正文应被提取"
    assert "导航菜单" not in body, "nav 噪声应被清除"
    assert "版权页脚" not in body, "footer 噪声应被清除"
    assert "bad=" not in body, "script 噪声应被清除"
    print(f"✅ 正文提取: {body.strip()[:60]}...\n")


def test_read_local_file():
    print("=" * 60)
    print("【测试：本地文件读取】")
    print("=" * 60)
    read = skill_registry.get_run_func("read_local_file")
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), TMP_FILE)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("本地资料内容XYZ")
    try:
        content = read(tmp)
        assert "本地资料内容XYZ" in content, "本地文件读取失败"
        miss = read(os.path.join(os.path.dirname(os.path.abspath(__file__)), "不存在.txt"))
        assert miss.startswith("【提示】"), "不存在文件应返回提示"
        print("✅ 本地读取/不存在提示正常")
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    print("✅ 本地文件读取测试通过\n")


def test_collector_import():
    print("=" * 60)
    print("【测试：采集员 本地文件→整理→主题归一→新建入库 全链路】")
    print("=" * 60)
    _clean_test_topic()
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), TMP_FILE)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("这是一段待整理的原始资料：北京小升初政策2026年要点。")
    try:
        from agent_registry.agents import collector_agent

        organize_text = "标题：collector_tmp.txt 资料\n来源：collector_tmp.txt\n要点：\n- 2026年政策要点A\n- 政策要点B"
        fake_llm = _make_fake_llm(
            organize_text,
            topic_obj={"topic": TEST_TOPIC, "matched_existing": False},
            decide_obj={"action": "new", "target_file": "", "reason": "独立"},
        )
        with patch.object(collector_agent, "get_llm", return_value=fake_llm):
            state = {"topic": TEST_TOPIC, "source": tmp}
            result = collector_agent.run(state)

        assert "已写入" in result["collect_result"], f"应成功入库: {result}"
        repo_dir = _topic_dir()
        assert repo_dir, "主题库应被创建"
        files = [f for f in os.listdir(repo_dir) if not f.startswith("_")]
        assert files, "应有入库文件"
        saved = open(os.path.join(repo_dir, files[0]), encoding="utf-8").read()
        assert "要点" in saved and "政策要点A" in saved, "入库内容应为整理后文本"
        print(f"✅ 新建入库成功: {files[0]}")
    finally:
        _clean_test_topic()
        if os.path.exists(tmp):
            os.remove(tmp)
    print("✅ 采集员入库链路测试通过\n")


def test_collector_topic_normalize():
    print("=" * 60)
    print("【测试：主题归一——显式主题与现有库同义→复用并提示】")
    print("=" * 60)
    _clean_test_topic()
    # 预置一个"测试美学库"主题库（测试专用名，跑完清理，不碰真实资料）
    pre = os.path.join(LOCAL_DB, "90-测试美学库")
    os.makedirs(pre, exist_ok=True)
    with open(os.path.join(pre, "_repo.md"), "w", encoding="utf-8") as f:
        f.write("# 主题库：90-测试美学库\n- 简介：测试美学\n- 文件数：1\n\n## 文件索引\n- 01-美学要点.md | 2026-01-01 | 摘要：美学核心\n")
    with open(os.path.join(pre, "01-美学要点.md"), "w", encoding="utf-8") as f:
        f.write("美学核心内容。")
    try:
        from agent_registry.agents import collector_agent
        # 用户显式填"宋代山水画" → LLM 判定与"测试美学库"同义 → 复用
        organize_text = "标题：文本资料\n来源：直接文本\n要点：\n- 宋代山水画技法"
        fake_llm = _make_fake_llm(
            organize_text,
            topic_obj={"topic": "测试美学库", "matched_existing": True},
            decide_obj={"action": "new", "target_file": "", "reason": "首份"},
        )
        with patch.object(collector_agent, "get_llm", return_value=fake_llm):
            result = collector_agent.run({"topic": "宋代山水画", "source": "宋代山水画资料正文"})
        assert "匹配现有库「测试美学库」" in result["collect_result"], f"应提示匹配: {result}"
        # 不应新建"宋代山水画"库，应写入"测试美学库"库
        assert not os.path.exists(os.path.join(LOCAL_DB, "90-宋代山水画")), "不应新建同义库"
        repo_dir = _topic_dir_by("测试美学库")
        files = [f for f in os.listdir(repo_dir) if f.endswith(".md") and not f.startswith("_")]
        assert len(files) == 2, f"应写入现有库（新文件+原文件），实际 {files}"
        print(f"✅ 同义归一成功：写入现有库「测试美学库」，文件 {files}")
    finally:
        _clean_test_topic()
    print("✅ 主题归一测试通过\n")


def _topic_dir_by(display):
    for name in sorted(os.listdir(LOCAL_DB)):
        if os.path.isdir(os.path.join(LOCAL_DB, name)) and re.sub(r"^\d{1,3}-", "", name) == display:
            return os.path.join(LOCAL_DB, name)
    return None


def test_collector_merge():
    print("=" * 60)
    print("【测试：同主题再次采集→合并写入+自动备份】")
    print("=" * 60)
    _clean_test_topic()
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), TMP_FILE)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("北京小升初政策2026年新要点。")
    try:
        from agent_registry.agents import collector_agent
        holder = {"target": ""}
        organize_text = "标题：collector_tmp.txt 资料\n来源：collector_tmp.txt\n要点：\n- 政策要点A"
        # 第一次：新建（库不存在，决策直接 new，无需 decide LLM）
        fake1 = _make_fake_llm(organize_text, topic_obj={"topic": TEST_TOPIC, "matched_existing": True})
        with patch.object(collector_agent, "get_llm", return_value=fake1):
            r1 = collector_agent.run({"topic": TEST_TOPIC, "source": tmp})
        assert "已写入" in r1["collect_result"], r1
        repo_dir = _topic_dir()
        holder["target"] = [f for f in os.listdir(repo_dir) if f.endswith(".md") and not f.startswith("_")][0]
        before = open(os.path.join(repo_dir, holder["target"]), encoding="utf-8").read()

        # 第二次：决策 merge → 合并覆盖 + 备份
        fake2 = _make_fake_llm(
            organize_text,
            topic_obj={"topic": TEST_TOPIC, "matched_existing": True},
            decide_obj={"action": "merge", "target_file": holder["target"], "reason": "同主题补充"},
            merge_text="合并后全文：政策要点A+新增要点B（已去重）",
        )
        with patch.object(collector_agent, "get_llm", return_value=fake2):
            r2 = collector_agent.run({"topic": TEST_TOPIC, "source": tmp})
        assert "合并写入" in r2["collect_result"], f"应合并: {r2}"
        after = open(os.path.join(repo_dir, holder["target"]), encoding="utf-8").read()
        assert "合并后全文" in after, "文件内容应为合并后文本"
        assert "_bak_" in "".join(os.listdir(repo_dir)), "应有备份文件"
        bak = open(os.path.join(repo_dir, f"_bak_{holder['target']}"), encoding="utf-8").read()
        assert bak == before, "备份内容应为合并前原文"
        print(f"✅ 合并写入成功 + 备份验证通过（{holder['target']}）")
    finally:
        _clean_test_topic()
        if os.path.exists(tmp):
            os.remove(tmp)
    print("✅ 合并与备份测试通过\n")


def test_collector_overlong_force_new():
    print("=" * 60)
    print("【测试：原文件超阈值→强制新建（不合并不覆盖）】")
    print("=" * 60)
    _clean_test_topic()
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), TMP_FILE)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("北京小升初政策2026年新要点。")
    try:
        from agent_registry.agents import collector_agent
        # 预置主题库 + 一个超长文件（>8000）
        repo_dir = os.path.join(LOCAL_DB, "99-采集测试库")
        os.makedirs(repo_dir, exist_ok=True)
        with open(os.path.join(repo_dir, "_repo.md"), "w", encoding="utf-8") as f:
            f.write("# 主题库：99-采集测试库\n- 简介：测试\n- 文件数：1\n\n## 文件索引\n- 01-超长.md | 2026-01-01 | 摘要：超长文件\n")
        long_file = os.path.join(repo_dir, "01-超长.md")
        with open(long_file, "w", encoding="utf-8") as f:
            f.write("超长内容" * 2500)  # 10000 字符，超过 MERGE_MAX_CHARS=8000
        original = open(long_file, encoding="utf-8").read()

        organize_text = "标题：文本资料\n来源：直接文本\n要点：\n- 新要点"
        # 决策返回 merge（错误决策），程序应按超阈值强制新建
        fake = _make_fake_llm(
            organize_text,
            topic_obj={"topic": TEST_TOPIC, "matched_existing": True},
            decide_obj={"action": "merge", "target_file": "01-超长.md", "reason": "应被阈值拦截"},
        )
        with patch.object(collector_agent, "get_llm", return_value=fake):
            result = collector_agent.run({"topic": TEST_TOPIC, "source": tmp})
        assert open(long_file, encoding="utf-8").read() == original, "超长原文件不得被覆盖"
        files = [f for f in os.listdir(repo_dir) if f.endswith(".md") and not f.startswith("_")]
        assert len(files) == 2, f"应新建第二个文件而非覆盖，实际 {files}"
        print(f"✅ 超阈值强制新建：原文件未动，新文件 {sorted(files)}")
    finally:
        _clean_test_topic()
        if os.path.exists(tmp):
            os.remove(tmp)
    print("✅ 超阈值护栏测试通过\n")


def test_collector_write_mode():
    print("=" * 60)
    print("【测试：写入模式 write_mode——new 强制新建 / merge 尽量合并】")
    print("=" * 60)
    _clean_test_topic()
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), TMP_FILE)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("北京小升初政策2026年新要点。")
    try:
        from agent_registry.agents import collector_agent
        organize_text = "标题：collector_tmp.txt 资料\n来源：collector_tmp.txt\n要点：\n- 政策要点A"
        # 预置库 + 一个现有文件（让合并决策有机会返回 merge）
        repo_dir = os.path.join(LOCAL_DB, "99-采集测试库")
        os.makedirs(repo_dir, exist_ok=True)
        with open(os.path.join(repo_dir, "_repo.md"), "w", encoding="utf-8") as f:
            f.write("# 主题库：99-采集测试库\n- 简介：测试\n- 文件数：1\n\n## 文件索引\n- 01-旧文件.md | 2026-01-01 | 摘要：旧文件\n")
        with open(os.path.join(repo_dir, "01-旧文件.md"), "w", encoding="utf-8") as f:
            f.write("旧文件内容。")
        old_content = open(os.path.join(repo_dir, "01-旧文件.md"), encoding="utf-8").read()

        # 1) write_mode="new"：跳过合并决策直接新建（旧文件保留原样，另新建一个文件）
        fake_new = _make_fake_llm(organize_text, topic_obj={"topic": TEST_TOPIC, "matched_existing": True})
        with patch.object(collector_agent, "get_llm", return_value=fake_new):
            r1 = collector_agent.run({"topic": TEST_TOPIC, "source": tmp, "write_mode": "new"})
        assert "已写入" in r1["collect_result"], r1
        assert "合并" not in r1["collect_result"], "new 模式不应走合并"
        files1 = [f for f in os.listdir(repo_dir) if f.endswith(".md") and not f.startswith("_") and f != "01-旧文件.md"]
        assert files1, "应新建文件"
        assert open(os.path.join(repo_dir, "01-旧文件.md"), encoding="utf-8").read() == old_content, "旧文件不应被覆盖"
        print(f"✅ new 模式：强制新建 {files1[0]}，旧文件未动")

        # 2) write_mode="merge"：尽量合并到现有文件（备份+覆盖）
        fake_merge = _make_fake_llm(
            organize_text,
            topic_obj={"topic": TEST_TOPIC, "matched_existing": True},
            decide_obj={"action": "merge", "target_file": "01-旧文件.md", "reason": "同主题补充"},
            merge_text="合并后全文：旧+新（已去重）",
        )
        with patch.object(collector_agent, "get_llm", return_value=fake_merge):
            r2 = collector_agent.run({"topic": TEST_TOPIC, "source": tmp, "write_mode": "merge"})
        assert "合并写入" in r2["collect_result"], f"merge 模式应合并: {r2}"
        after = open(os.path.join(repo_dir, "01-旧文件.md"), encoding="utf-8").read()
        assert "合并后全文" in after, "文件内容应为合并后文本"
        print("✅ merge 模式：合并到现有文件（备份+覆盖）")

        # 3) write_mode="merge" 但库无可合并文件（决策失败/无文件）→ 降级新建
        _clean_test_topic()
        repo_dir = os.path.join(LOCAL_DB, "99-采集测试库")
        os.makedirs(repo_dir, exist_ok=True)
        with open(os.path.join(repo_dir, "_repo.md"), "w", encoding="utf-8") as f:
            f.write("# 主题库：99-采集测试库\n- 简介：测试\n- 文件数：0\n")
        fake_new2 = _make_fake_llm(organize_text, topic_obj={"topic": TEST_TOPIC, "matched_existing": False})
        with patch.object(collector_agent, "get_llm", return_value=fake_new2):
            r3 = collector_agent.run({"topic": TEST_TOPIC, "source": tmp, "write_mode": "merge"})
        assert "已写入" in r3["collect_result"] and "合并" not in r3["collect_result"], f"空库应降级新建: {r3}"
        print("✅ merge 模式：无可合并文件时降级新建")
    finally:
        _clean_test_topic()
        if os.path.exists(tmp):
            os.remove(tmp)
    print("✅ 写入模式测试通过\n")


def test_import_materials_api():
    print("=" * 60)
    print("【测试：资料入库 API（异步任务→左侧进度→多来源/失败隔离→write_mode 透传）】")
    print("=" * 60)
    import time
    from web_gui.app import app

    client = app.test_client()
    seen = {}

    def fake_collector_run(state):
        src = str(state.get("source") or "")
        seen["topic"] = state.get("topic")
        seen["domain"] = state.get("domain")
        seen["write_mode"] = state.get("write_mode")
        seen["has_source"] = bool(src)
        return {"collect_result": f"✅ 已写入主题库：来源={src[:20]}..."}

    def wait_done(task_id, timeout=15):
        end = time.time() + timeout
        while time.time() < end:
            t = client.get(f"/api/task/{task_id}").get_json()["task"]
            if t["status"] in ("done", "failed"):
                return t
            time.sleep(0.2)
        return None

    with patch("agent_registry.agents.collector_agent.run", new=fake_collector_run):
        resp = client.post("/api/import_materials", json={
            "topic": "导入测试",
            "domain": "域甲",
            "write_mode": "new",
            "items": [
                {"type": "url", "name": "https://a.com/x", "content": "https://a.com/x"},
                {"type": "text", "name": "直接文本", "content": "一段待整理文本"},
                {"type": "file", "name": "笔记.md", "content": "# 笔记内容"},
            ],
        })
    data = resp.get_json()
    assert resp.status_code == 200 and data["ok"], data
    assert data["count"] == 3, f"应返回 3 个来源计数: {data}"
    task_id = data["task_id"]
    final = wait_done(task_id)
    assert final and final["status"] == "done", f"任务应完成: {final}"
    assert seen["topic"] == "导入测试" and seen["domain"] == "域甲" and seen["has_source"], seen
    assert seen["write_mode"] == "new", f"write_mode 应透传为 new: {seen}"
    # 左侧进度事件：3 个 step_start（来源1/2/3）+ 完成事件
    starts = [e for e in final["events"] if e["type"] == "step_start"]
    assert len(starts) == 3, f"应有 3 条来源进度事件: {final['events']}"
    assert any(e["type"] == "done" for e in final["events"]), "应有完成事件"
    print(f"✅ 异步任务完成：task_id={task_id}，3 条来源进度事件，topic/domain/write_mode 正确传递")

    # write_mode 缺省 → auto（默认）
    with patch("agent_registry.agents.collector_agent.run", new=fake_collector_run):
        resp4 = client.post("/api/import_materials", json={"items": [{"type": "text", "content": "x"}]})
    final4 = wait_done(resp4.get_json()["task_id"])
    assert final4["status"] == "done", "默认 write_mode 任务应完成"
    assert seen["write_mode"] == "auto", f"缺省 write_mode 应为 auto: {seen}"
    print("✅ write_mode 缺省 = auto（向后兼容）")

    # 空来源 → 400
    resp2 = client.post("/api/import_materials", json={"items": []})
    assert resp2.status_code == 400
    print("✅ 空来源正确拒绝（400）")

    # 单条失败隔离：collector 抛异常 → 任务仍 done，且 error 事件存在（不整体 failed）
    def failing_run(state):
        raise RuntimeError("抓取失败")
    with patch("agent_registry.agents.collector_agent.run", new=failing_run):
        resp3 = client.post("/api/import_materials", json={"items": [{"type": "text", "content": "x"}]})
    data3 = resp3.get_json()
    final3 = wait_done(data3["task_id"])
    assert final3["status"] == "done", "单条失败不应让整体任务 failed"
    assert any(e["type"] == "error" for e in final3["events"]), "应有失败事件"
    print("✅ 单条失败隔离（error 事件，任务整体完成）")
    print("\n✅ 资料入库 API 测试通过\n")


if __name__ == "__main__":
    test_fetch_url_content()
    test_read_local_file()
    test_collector_import()
    test_collector_topic_normalize()
    test_collector_merge()
    test_collector_overlong_force_new()
    test_collector_write_mode()
    test_import_materials_api()
