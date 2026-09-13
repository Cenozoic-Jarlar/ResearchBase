"""
[模块] skills/read_topic_summary.py — Skill：主题摘要读取（L2）
[职责] 读指定主题库的摘要索引（_repo.md），短文件直接附全文，长文件只给摘要；
       支持主题域：domain 指定时先查域内库，未命中再查通用层
[设计思想] 摘要先行 + 短内容合并：AI 提炼的摘要（写入时维护在 _repo.md）让 LLM 低 token 判断相关性；
           短文件（≤ SHORT_FILE_THRESHOLD）直接在摘要阶段带出全文，省掉一次"再读全文"轮次
[关键约定] ★ 短文件阈值在 core/paths.py；主题名匹配支持"带编号（01-xxx）"或"纯主题名（xxx）"；
           返回文本标注每个文件长度级别（[短·含全文] / [长·仅摘要]）
[被谁调用] researcher_agent（第二步）
[修改注意] 只读不改；索引维护在 write_local_database
"""
import os
import re

from core.paths import LOCAL_DB, REPO_META_FILE, SHORT_FILE_THRESHOLD, TOPIC_PREFIX_PATTERN, local_db_root


def run(topic: str, domain: str = None) -> str:
    """
    读取指定主题库的摘要（含短文件全文）。
    :param topic: 主题库名（如"01-北京小升初政策"或"北京小升初政策"）
    :param domain: 主题域名；先查域内库，未命中再查通用层
    :return: str 摘要 + 短文件全文；主题库不存在时返回提示
    """
    repo_dir = _resolve_topic_dir(topic, domain)
    if repo_dir is None:
        return f"【提示】主题库「{topic}」不存在，可用 list_topics 查看现有主题库"

    meta_path = os.path.join(repo_dir, REPO_META_FILE)
    parts = [f"==== 主题库：{os.path.basename(repo_dir)} 摘要 ===="]
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            parts.append(f.read().strip())

    files = sorted(f for f in os.listdir(repo_dir)
                   if f.endswith((".md", ".txt")) and not f.startswith("_"))
    for fname in files:
        fpath = os.path.join(repo_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            parts.append(f"\n- {fname}：读取失败（{e}）")
            continue
        if len(content) <= SHORT_FILE_THRESHOLD:
            parts.append(f"\n--- [短文件·含全文] {fname} ---\n{content}")
        else:
            head = content[:200].replace("\n", " ")
            parts.append(f"\n--- [长文件·仅摘要] {fname}（全文 {len(content)} 字符）---\n开头：{head}…")
    parts.append("=" * 30)
    return "\n".join(parts)


def _resolve_topic_dir(topic: str, domain: str = None):
    """按主题名定位目录：先域内库，再通用层"""
    clean = re.sub(TOPIC_PREFIX_PATTERN, "", topic.strip())
    roots = []
    if domain:
        r = local_db_root(domain)
        if r != LOCAL_DB:
            roots.append(r)
    roots.append(LOCAL_DB)
    for root in roots:
        if not os.path.exists(root):
            continue
        for name in sorted(os.listdir(root)):
            repo_dir = os.path.join(root, name)
            if not os.path.isdir(repo_dir):
                continue
            if name == topic.strip():
                return repo_dir
            if re.sub(TOPIC_PREFIX_PATTERN, "", name) == clean:
                return repo_dir
    return None


SKILL_META = {
    "name": "read_topic_summary",
    "description": "【主题摘要读取】读取指定主题库的全部文件摘要（_repo.md 索引），短文件自动附全文。"
                   "参数：topic(主题库名，如「01-北京小升初政策」或「北京小升初政策」)、"
                   "domain(可选，主题域名，先查域内再查通用层)。"
                   "返回：摘要文本+短文件全文。用于低 token 判断内容相关性。",
    "run": run
}
