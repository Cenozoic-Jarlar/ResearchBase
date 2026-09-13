"""
[模块] skills/list_topics.py — Skill：主题仓库概览（L1）
[职责] 扫描资料库下所有主题库（含 _repo.md 的子目录），返回概览清单；
       支持主题域：domain 指定时返回"域内 + 通用层"合并概览（标注来源）
[设计思想] 三级读取的入口：只读每个主题库 _repo.md 的头部（名称/简介/文件数），
           不读文件正文——极低 token，供 LLM 判断哪些主题相关
[关键约定] 主题库 = 目录名含 _repo.md；返回结构化文本（人类/LLM 均可读）；
           ★ domain=None = 通用层（向后兼容）；domain=具体域 = 域内库 + 通用库合并
[被谁调用] researcher_agent（第一步）；GUI /api/info（主题库清单）
[修改注意] 自动注册逻辑在此：新增主题库目录即自动出现在清单中
"""
import os
import re

from core.paths import LOCAL_DB, REPO_META_FILE, TOPIC_PREFIX_PATTERN, local_db_root


def run(domain: str = None) -> str:
    """
    主题仓库概览（不读文件正文）。
    :param domain: 主题域名；None=通用层（默认），具体域=域内+通用合并
    :return: str 结构化清单；无主题库时返回提示
    """
    roots = _collect_roots(domain)
    lines = ["==== 本地资料主题库概览 ===="]
    found = False
    for root, is_domain in roots:
        if not os.path.exists(root):
            continue
        tag = "（域内）" if is_domain else "（通用）"
        for name in sorted(os.listdir(root)):
            repo_dir = os.path.join(root, name)
            if not os.path.isdir(repo_dir) or not os.path.exists(os.path.join(repo_dir, REPO_META_FILE)):
                continue
            found = True
            display = re.sub(TOPIC_PREFIX_PATTERN, "", name)  # 去掉编号前缀，展示主题名
            meta = _read_repo_head(os.path.join(repo_dir, REPO_META_FILE))
            file_count = len([f for f in os.listdir(repo_dir)
                              if f.endswith((".md", ".txt")) and not f.startswith("_")])
            lines.append(f"- 主题库「{display}」{tag}（目录：{name}，{file_count} 个文件）：{meta}")
    if not found:
        return "【提示】暂无主题库，请用 write_local_database 按主题写入资料"
    lines.append("============================")
    return "\n".join(lines)


def list_topic_names(domain: str = None, include_general: bool = True) -> list:
    """返回主题库目录名列表（供 GUI/API 结构化展示）。
    domain=None 且 include_general=True → 通用层（默认/向后兼容）；
    domain=具体域 → 域内 + 通用（include_general=False 时仅域内）"""
    roots = _collect_roots(domain, include_general)
    names = []
    for root, _ in roots:
        if not os.path.exists(root):
            continue
        names += [
            n for n in os.listdir(root)
            if os.path.isdir(os.path.join(root, n))
            and os.path.exists(os.path.join(root, n, REPO_META_FILE))
        ]
    return sorted(set(names))


def _collect_roots(domain: str = None, include_general: bool = True):
    """收集要扫描的资料库根：(root, is_domain) 列表；去重（domain=通用层时只一次）"""
    roots = []
    if domain:
        r = local_db_root(domain)
        if r != LOCAL_DB:
            roots.append((r, True))
    if include_general:
        roots.append((LOCAL_DB, False))
    return roots


def _read_repo_head(meta_path: str) -> str:
    """读取 _repo.md 前几行（标题/简介），作为概览摘要"""
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            text = f.read()
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("- 简介"):
                return line
        return "（无简介）"
    except Exception:
        return "（读取失败）"


SKILL_META = {
    "name": "list_topics",
    "description": "【主题库概览】列出本地资料库全部主题库（名称+简介+文件数），用于判断哪些主题与当前任务相关。"
                   "参数：domain(可选，主题域名；不传=通用层，传具体域=域内+通用合并)。"
                   "返回：结构化清单文本，token 极低。",
    "run": run
}
