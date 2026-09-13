"""
[模块] skills/write_local_database.py — Skill：写本地资料库（按主题，支持主题域）
[职责] 按主题库写入资料：自动建库（编号+命名）、自动文件编号、AI 提炼摘要并维护 _repo.md 索引；
       写入目标 = 主题域私有库（domain 指定）或通用层（默认）
[设计思想] 资料仓库的"写端"：写入即维护摘要索引（AI 提炼一句话存 _repo.md），
           后续 read_topic_summary 直接读索引，避免每次读取重复提炼；
           编号（NN-）自动生成保证目录/文件排序整齐（人工/AI 均可读）；
           域隔离：默认写通用层（向后兼容），collector/archivist 按 state["domain"] 写入域私有库
[关键约定] ★ 主题库目录名规范 NN-主题短语（中英文均可），同名库自动复用（去编号匹配）；
           ★ 文件自动补 NN- 编号；摘要优先用参数 summary，否则 AI 提炼（router 档，低 token），失败兜底首行
[被谁调用] archivist_agent（沉淀成果）、collector_agent（入库）；未来可被 LLM 直接选用
[修改注意] AI 提炼走 router 档（低token）；改 _repo.md 结构需同步 read_topic_summary 与 list_topics
"""
import os
import re
from datetime import datetime

from llm_config import get_llm
from core.paths import LOCAL_DB, REPO_META_FILE, TOPIC_PREFIX_PATTERN, local_db_root


def run(filename: str, content: str, topic: str = "00-默认资料", mode: str = "append",
        summary: str = None, domain: str = None) -> str:
    """
    向主题库写入资料。
    :param filename: 文件名（自动补编号与 .md 后缀；可含扩展名）
    :param content: 要写入的文本内容
    :param topic: 主题库名（如"北京小升初政策"，自动编号；已存在则复用）
    :param mode: "append" 追加（默认）/"overwrite" 覆盖
    :param summary: 摘要（可选）；不传则 AI 提炼，失败兜底首行
    :param domain: 主题域名（None=通用层，默认）；具体域=写入 domains/<域>/LocalDataBase
    :return: str 写入结果提示
    """
    root = local_db_root(domain)
    os.makedirs(root, exist_ok=True)
    repo_dir = _ensure_topic_dir(topic, root)
    display_topic = re.sub(TOPIC_PREFIX_PATTERN, "", os.path.basename(repo_dir))

    # 文件名：去路径、补扩展名；已有同主题名文件（忽略编号）则复用其完整文件名（覆盖/追加语义）
    fname = os.path.basename(filename).strip()
    if not fname:
        return "❌ 文件名不能为空"
    if not re.search(r"\.(md|txt)$", fname, re.I):
        fname += ".md"
    for f in os.listdir(repo_dir):
        if re.sub(TOPIC_PREFIX_PATTERN, "", f) == re.sub(TOPIC_PREFIX_PATTERN, "", fname):
            fname = f
            break
    else:
        if not re.match(TOPIC_PREFIX_PATTERN, fname):
            fname = f"{_next_file_number(repo_dir):02d}-{fname}"

    # 写文件
    fpath = os.path.join(repo_dir, fname)
    flag = "a" if mode == "append" else "w"
    try:
        with open(fpath, flag, encoding="utf-8") as f:
            f.write(content if content.endswith("\n") else content + "\n")
    except Exception as e:
        return f"❌ 写入失败：{e}"

    # 摘要：参数优先 → AI 提炼 → 首行兜底
    if summary is None or not str(summary).strip():
        summary = _ai_summarize(content)
    _update_repo_meta(repo_dir, fname, summary)

    return f"✅ 已写入主题库「{display_topic}」：{fname}（模式：{mode}）"


def _ai_summarize(content: str) -> str:
    """AI 提炼一句话摘要；异常/无 LLM 时兜底取首行"""
    try:
        prompt = f"用一句话（不超过50字）概括以下资料的核心内容，直接输出概括，不要多余文字：\n{content[:3000]}"
        resp = get_llm("router").invoke(prompt)
        text = str(getattr(resp, "content", "")).strip()
        if text and not text.startswith("<Mock"):
            return text
    except Exception:
        pass
    first = next((l.strip() for l in content.splitlines() if l.strip()), "（无内容）")
    return first[:50]


def _ensure_topic_dir(topic: str, root: str):
    """定位或创建主题库目录（在指定 root 内）：去编号匹配已有库；新建时尊重自带编号，否则自动编号"""
    clean = re.sub(TOPIC_PREFIX_PATTERN, "", topic.strip())
    if not clean:
        clean = "默认资料"
    for name in sorted(os.listdir(root)):
        if os.path.isdir(os.path.join(root, name)) and re.sub(TOPIC_PREFIX_PATTERN, "", name) == clean:
            return os.path.join(root, name)
    # 自带编号优先；否则取现有最大编号 +1
    m = re.match(r"^(\d{1,3})-", topic.strip())
    if m:
        num = int(m.group(1))
    else:
        num = _next_number([n for n in os.listdir(root) if os.path.isdir(os.path.join(root, n))])
    repo_dir = os.path.join(root, f"{num:02d}-{clean}")
    os.makedirs(repo_dir, exist_ok=True)
    _init_repo_meta(repo_dir, clean)
    return repo_dir


def _init_repo_meta(repo_dir: str, display: str):
    """新建主题库时初始化 _repo.md"""
    meta_path = os.path.join(repo_dir, REPO_META_FILE)
    if not os.path.exists(meta_path):
        with open(meta_path, "w", encoding="utf-8") as f:
            f.write(f"# 主题库：{os.path.basename(repo_dir)}\n"
                    f"- 简介：{display}（可在此手工补充说明）\n"
                    f"- 创建时间：{datetime.now().strftime('%Y-%m-%d')}\n"
                    f"- 文件数：0\n\n## 文件索引\n")


def _update_repo_meta(repo_dir: str, fname: str, summary: str):
    """把文件条目（文件名|日期|摘要）追加进 _repo.md 索引，并刷新文件数"""
    meta_path = os.path.join(repo_dir, REPO_META_FILE)
    if not os.path.exists(meta_path):
        _init_repo_meta(repo_dir, os.path.basename(repo_dir))
    with open(meta_path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    entry = f"- {fname} | {datetime.now().strftime('%Y-%m-%d')} | 摘要：{summary}"
    lines = [l for l in lines if not l.startswith(f"- {fname} |")]  # 同文件去重（overwrite 场景）
    # 在 "## 文件索引" 之后插入条目
    idx = next((i for i, l in enumerate(lines) if l.startswith("## 文件索引")), len(lines))
    lines.insert(idx + 1, entry)
    # 刷新文件数（统计非 _ 开头的 .md/.txt）
    file_count = len([f for f in os.listdir(repo_dir)
                      if f.endswith((".md", ".txt")) and not f.startswith("_")])
    lines = [f"- 文件数：{file_count}" if l.startswith("- 文件数：") else l for l in lines]

    with open(meta_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _next_file_number(repo_dir: str) -> int:
    """主题库内下一个文件编号"""
    nums = []
    for f in os.listdir(repo_dir):
        m = re.match(r"^(\d{1,3})-", f)
        if m:
            nums.append(int(m.group(1)))
    return (max(nums) + 1) if nums else 1


def _next_number(names: list) -> int:
    """从目录名中提取最大编号 +1"""
    nums = []
    for n in names:
        m = re.match(r"^(\d{1,3})-", n)
        if m:
            nums.append(int(m.group(1)))
    return (max(nums) + 1) if nums else 1


SKILL_META = {
    "name": "write_local_database",
    "description": "【写本地资料库】按主题库写入 txt/md 资料，用于沉淀研究成果或整理碎片资料。"
                   "参数：filename(文件名，自动补编号和.md后缀)、content(要写入的文本内容)、"
                   "topic(主题库名，如「北京小升初政策」，不存在自动创建，存在则复用)、"
                   "mode(append追加/overwrite覆盖，默认append)、summary(可选，不传则AI提炼摘要)。"
                   "返回：写入结果提示。",
    "run": run
}
