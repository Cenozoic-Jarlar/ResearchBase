"""
[模块] skills/read_topic_file.py — Skill：单文件全文读取（L3）
[职责] 读取指定主题库下指定文件的完整内容；支持主题域（先域内再通用层）
[设计思想] 三级读取的最末级：LLM 从摘要判断文件相关后，按需取全文，
           避免无关文件占用 token
[关键约定] topic 支持带编号/纯主题名；filename 需精确匹配（含扩展名）
[被谁调用] researcher_agent（第三步，仅当 LLM 判定需要全文）
[修改注意] 只读不改
"""
import os
import re

from core.paths import LOCAL_DB, TOPIC_PREFIX_PATTERN, local_db_root


def run(topic: str, filename: str, domain: str = None) -> str:
    """
    读取指定主题库下指定文件全文。
    :param topic: 主题库名（如"01-北京小升初政策"或"北京小升初政策"）
    :param filename: 文件名（含扩展名，如"01-丰台区政策要点.md"）
    :param domain: 主题域名；先查域内库，再查通用层
    :return: str 文件全文；不存在时返回提示
    """
    repo_dir = _resolve_topic_dir(topic, domain)
    if repo_dir is None:
        return f"【提示】主题库「{topic}」不存在"
    fpath = os.path.join(repo_dir, filename)
    if not os.path.exists(fpath):
        avail = [f for f in os.listdir(repo_dir) if f.endswith((".md", ".txt"))]
        return f"【提示】文件「{filename}」不存在，可用：{avail}"
    with open(fpath, "r", encoding="utf-8") as f:
        return f.read()


def _resolve_topic_dir(topic: str, domain: str = None):
    """按主题名定位目录：先域内库，再通用层（与 read_topic_summary 同一匹配规则）"""
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
    "name": "read_topic_file",
    "description": "【单文件全文读取】读取指定主题库下指定文件的完整内容。"
                   "参数：topic(主题库名)、filename(文件名含扩展名)、domain(可选，主题域名)。"
                   "返回：文件全文。用于摘要命中后按需取全文。",
    "run": run
}
