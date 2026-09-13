"""
[模块] tools/archive_process.py — 研究过程封存（程序内部功能，非 LLM Skill）
[职责] 任务结束后把"元信息+执行计划+各角色中间产出+最终文章"打包为结构化
       Markdown 档案，存入研究档案目录（生成时间+主题命名），实现研究过程可追溯/可复用
[设计思想] 过程是研究资产：archivist 只封存最终文章（产出），本模块封存完整过程
           （怎么一步步得出这篇文章）。与 detail 日志分工：日志=排障（LLM 交互全文），
           档案=知识沉淀（结构化产出摘要）；档案存独立档案目录而非主题库，
           避免被 list_topics 当作调研资料读入
[关键约定] 档案文件命名"YYYYMMDD_HHMM_主题短语.md"（复用 document_output.sanitize_filename）；
           缺失字段自动跳过（思考型角色未参与时不输出空节）；
           最终文章必须存在才有封存价值（无 final_article 时返回 None 不落盘）；
           档案按主题域落盘（domain=None=通用层 archives/，具体域=domains/<域>/archives/）
[被谁调用] main.py（三模式跑完后）、web_gui/services/task_manager.py（任务 done 路径）
[修改注意] 新增 State 产出字段后如需入档案，同步在 _section 各分支补充；
           与 tools/document_output.py 的命名风格保持一致（输出与档案均"时间+主题"）
"""
import os
from datetime import datetime

from core.paths import archive_root
from tools.document_output import sanitize_filename

# 档案中需要封存的 State 字段 → 章节标题（缺失自动跳过）
FIELD_SECTIONS = [
    ("research_material", "调研素材"),
    ("critical_review", "批判性审阅"),
    ("scientific_analysis", "科学思维分析"),
    ("humanities_perspective", "人文视角"),
    ("human_supplement", "人工补充信息"),
    ("advisor_note", "记忆顾问建议"),
]


def _fmt_meta(meta: dict) -> str:
    """把执行元信息渲染为 Markdown 列表"""
    lines = []
    if meta.get("engine"):
        lines.append(f"- 执行引擎：{meta['engine']}")
    if meta.get("mode"):
        lines.append(f"- 运行模式：{meta['mode']}")
    if meta.get("flow_name"):
        lines.append(f"- 静态流程：{meta['flow_name']}")
    if meta.get("domain"):
        lines.append(f"- 主题域：{meta['domain']}")
    return "\n".join(lines)


def _fmt_plan(final_state: dict) -> str:
    """渲染执行计划（动态引擎的 exec_plan 由 _execute 写入 state）"""
    plan = final_state.get("exec_plan") or []
    if not plan:
        return "_（未记录执行计划）_"
    lines = []
    for i, step in enumerate(plan, 1):
        note = step.get("note", "")
        agent = step.get("agent", "?")
        lines.append(f"{i}. **{agent}**：{note}" if note else f"{i}. **{agent}**")
    return "\n".join(lines)


def _fmt_fact_check(final_state: dict) -> str:
    """渲染事实审核结果（有 fact_check 字段才输出）"""
    if "fact_check_passed" not in final_state and "fact_check_issues" not in final_state:
        return ""
    passed = final_state.get("fact_check_passed")
    count = final_state.get("fact_check_count", 0)
    status = "通过" if passed else f"不通过（第 {count} 次达上限强制结束）"
    lines = [f"- 判定：{status}"]
    issues = final_state.get("fact_check_issues", "")
    if issues:
        lines.append(f"- 问题清单：\n\n{issues}")
    return "\n".join(lines)


def archive_research(final_state: dict, meta: dict = None, domain: str = None) -> str:
    """
    把一次研究过程封存为 Markdown 档案，返回档案完整路径。
    :param final_state: 任务最终全局状态（含 topic/final_article/各中间产出/exec_plan）
    :param meta: 执行元信息 {"engine": "dynamic"/"static", "mode": "...", "flow_name": "...", "domain": "..."}
    :param domain: 主题域名（None=通用层 archives/，默认；具体域=domains/<域>/archives/）
    :return: 档案路径；final_article 缺失时返回 None（无封存价值不落盘）
    """
    article = (final_state or {}).get("final_article", "")
    if not article:
        return None

    meta = meta or {}
    topic = final_state.get("topic", "未命名主题")
    domain = domain or (final_state or {}).get("domain")

    arch_dir = archive_root(domain)
    os.makedirs(arch_dir, exist_ok=True)
    now = datetime.now()
    fname = f"{now.strftime('%Y%m%d_%H%M')}_{sanitize_filename(topic)}"
    fpath = os.path.join(arch_dir, f"{fname}.md")

    lines = [
        "# 研究档案",
        "",
        f"- 封存时间：{now.strftime('%Y-%m-%d %H:%M')}",
        f"- 研究主题：{topic}",
    ]
    meta_text = _fmt_meta(meta)
    if meta_text:
        lines.append(meta_text)
    if final_state.get("task_level"):
        lines.append(f"- 任务等级：{final_state['task_level']}")
    vp = final_state.get("value_profiles") or []
    if vp:
        names = ", ".join(p.get("name", "?") for p in vp if isinstance(p, dict))
        if names:
            lines.append(f"- 价值观框架：{names}")
    lines += ["", "## 执行计划", "", _fmt_plan(final_state)]

    for field, title in FIELD_SECTIONS:
        content = final_state.get(field)
        if content:
            lines += ["", f"## {title}", "", str(content)]

    fc = _fmt_fact_check(final_state)
    if fc:
        lines += ["", "## 事实审核", "", fc]

    lines += ["", "## 最终文章", "", article]

    with open(fpath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return fpath
