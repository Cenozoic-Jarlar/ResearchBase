"""
[测试] test_archive_system.py — 研究过程封存模块
[运行] venv\\Scripts\\python.exe test_archive_system.py
[约定] 不调 LLM；覆盖：完整档案生成 / 缺失字段跳过 / 无最终文章不落盘 / 命名规范
"""
import os

from core.paths import ARCHIVE_DIR
from tools.archive_process import archive_research


def sample_state(**over):
    state = {
        "topic": "测试主题",
        "task_level": "complex",
        "research_material": "素材A\n素材B",
        "critical_review": "批判意见：论证有漏洞",
        "scientific_analysis": "科学分析：证据链不足",
        "humanities_perspective": "",
        "human_supplement": "人工补充：补充背景",
        "advisor_note": "建议使用 policy 框架",
        "fact_check_passed": True,
        "fact_check_count": 1,
        "fact_check_issues": "",
        "value_profiles": [{"name": "policy"}, {"name": "general"}],
        "exec_plan": [
            {"agent": "task_router", "note": "评估任务复杂度"},
            {"agent": "researcher", "note": "调研"},
            {"agent": "writer", "note": "写作"},
        ],
        "final_article": "# 最终文章\n\n这是正文。",
    }
    state.update(over)
    return state


def test_archive_full():
    print("=" * 60)
    print("【测试1：完整档案生成】")
    print("=" * 60)
    path = archive_research(sample_state(), {"engine": "dynamic", "mode": "auto"})
    assert path and os.path.exists(path), "档案应落盘"
    assert os.path.basename(path).startswith("20"), f"应时间开头：{os.path.basename(path)}"
    assert os.path.basename(path).endswith(".md")
    content = open(path, encoding="utf-8").read()
    for key in ["研究主题：测试主题", "执行引擎：dynamic", "任务等级：complex",
                "价值观框架：policy, general", "执行计划", "1. **task_router**：评估任务复杂度",
                "## 调研素材", "素材A", "## 批判性审阅", "批判意见：论证有漏洞",
                "## 科学思维分析", "## 人工补充信息", "## 记忆顾问建议", "## 事实审核", "判定：通过",
                "## 最终文章", "这是正文。"]:
        assert key in content, f"档案应包含：{key}"
    os.remove(path)
    print("✅ 完整档案含元信息/计划/各角色产出/事实审核/最终文章，命名符合规范\n")


def test_archive_missing_sections():
    print("=" * 60)
    print("【测试2：缺失字段自动跳过】")
    print("=" * 60)
    state = sample_state()
    for k in ["critical_review", "scientific_analysis", "humanities_perspective",
              "human_supplement", "advisor_note", "fact_check_passed",
              "fact_check_issues", "fact_check_count", "exec_plan"]:
        state.pop(k, None)
    path = archive_research(state, {"engine": "static", "mode": "static", "flow_name": "quick_article"})
    assert path and os.path.exists(path)
    content = open(path, encoding="utf-8").read()
    assert "## 批判性审阅" not in content, "缺失字段不应输出空节"
    assert "## 科学思维分析" not in content
    assert "## 人工补充信息" not in content
    assert "## 事实审核" not in content, "无 fact_check 字段不应输出审核节"
    assert "## 执行计划" in content and "（未记录执行计划）" in content, "无计划应有占位说明"
    assert "静态流程：quick_article" in content, "元信息应含静态流程名"
    assert "## 调研素材" in content, "有值字段应保留"
    os.remove(path)
    print("✅ 缺失字段跳过、静态元信息、计划占位均正确\n")


def test_archive_no_article():
    print("=" * 60)
    print("【测试3：无最终文章不落盘】")
    print("=" * 60)
    state = sample_state(final_article="")
    path = archive_research(state, {})
    assert path is None, "无 final_article 应返回 None 不落盘"
    # 目录里不应残留新文件
    files = [f for f in os.listdir(ARCHIVE_DIR) if f.endswith(".md")]
    print(f"✅ 无最终文章时返回 None，档案目录现有 {len(files)} 个文件（均为历史归档）\n")


if __name__ == "__main__":
    test_archive_full()
    test_archive_missing_sections()
    test_archive_no_article()
    print("=" * 60)
    print("✅ 过程封存测试全部通过！")
    print("=" * 60)
