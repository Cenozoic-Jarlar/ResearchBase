"""
[模块] agent_registry/agents/collector_agent.py — Agent：资料采集员
[职责] 从网络（URL）/ 本地文件 / 直接文本获取资料 → LLM 整理清洗 → 智能入库
       （主题归一 + 文件级合并决策，防止同义词碎片化与重复覆盖）
[设计思想] 资料入库的"入口角色"，每条来源独立处理（防爆 token、互不污染）：
           1) 获取：来源解析走 Skill（fetch_url_content / read_local_file），失败不抛异常
           2) 整理：LLM 清洗（去广告/导航噪声，分条列要点）——standard 档
           3) 主题归一：对照现有主题库概览，语义同义→复用现有库（防"宋代山水画"vs"宋画美学"碎片化）；
              主题留空则同时自动提炼主题短语；用户/资料明确要求"独立/分开"→ 强制新建 —— router 档
           4) 合并决策：读目标库现有文件摘要，LLM 判断 合并到某文件 / 新建文件 —— router 档
           5) 写入：merge=备份原文件(_bak_前缀，读端自动忽略)后 原内容+新内容 LLM 清洗合并覆盖；
               new=新建（文件名含主题与来源短标签）
           降级安全：任何一步失败 → 保守走"新建"，绝不误覆盖原文件
[关键约定] 写入字段 collect_result；入库主题 = 归一后的主题（用户填的或自动提炼）；
           支持多来源（逗号/换行分隔）；无来源时返回提示不报错；
           遵循 value_profiles 的 evidence/style 维度（整理侧重）；
           原文件超 MERGE_MAX_CHARS 时强制新建（防单文件膨胀）；
           写入模式 write_mode（state 传入）：auto=AI 自主决策（默认，兼容 CLI/旧调用）、
           new=强制新建文件、merge=尽量合并（无合适文件降级新建）
[依赖] llm_config（get_llm/resolve_tier）、skills（fetch_url_content/read_local_file/
       write_local_database/list_topics/read_topic_summary/read_topic_file）、
       memory.memory_registry.format_values_for
[被谁调用] material_import 静态流程；动态规划按需选用（用户目标含"收集/入库资料"时）；
          /api/import_materials 逐条调用
[修改注意] 决策/合并 prompt 的输出 JSON 契约与解析耦合，改动需同步；主题归一规则
           （同义复用 vs 用户强制独立）改动会影响资料归类，需同步 AGENTS.md §7
"""
import os
import re
import shutil
from datetime import datetime

from state_model import State
from llm_config import get_llm, resolve_tier
from skills.skill_registry import skill_registry
from tools.document_output import sanitize_filename
from memory.memory_registry import format_values_for

# 本角色消费的价值观维度
VP_DIMS = ["evidence", "style"]

# 原文件超过该字符数 → 强制新建不合并（防单文件膨胀、token 爆炸）
MERGE_MAX_CHARS = 8000
# 合并前备份文件名前缀（_ 开头，读端 list/read 自动忽略，不污染检索）
BACKUP_PREFIX = "_bak_"
# 喂给决策/归一调用的内容预览长度（省 token）
PREVIEW_LEN = 1200
# 喂给整理调用的原始内容上限
RAW_LIMIT = 8000
# 喂给合并调用的原文件全文上限
MERGE_OLD_LIMIT = 8000


def run(state: State) -> dict:
    user_topic = str(state.get("topic") or "").strip()
    source = str(state.get("source") or state.get("human_supplement") or "").strip()
    if not source:
        return {"collect_result": "未提供资料来源：请通过 URL / 本地文件路径 / 文本内容指定（可经 material_import 流程的断点输入）"}

    domain = state.get("domain")
    # 写入模式：auto=AI 自主决策（默认，兼容 CLI/旧调用）；new=强制新建文件；merge=尽量合并到现有文件（无合适文件则降级新建）
    write_mode = str(state.get("write_mode") or "auto").strip().lower()
    if write_mode not in ("new", "merge"):
        write_mode = "auto"
    llm = get_llm(resolve_tier(state, AGENT_META.get("tier")))          # 整理/合并（内容操作）
    router_llm = get_llm("router")                                       # 归一/决策（轻量语义判断）

    lines = []
    for item, label, content in _fetch_all(source):
        if content.startswith("【提示】"):
            lines.append(f"❌ [{label}] {content}")
            continue
        cleaned = _organize(content, label, state, llm)
        if not cleaned:
            lines.append(f"❌ [{label}] 整理失败")
            continue
        topic, matched = _resolve_topic(user_topic, cleaned, domain, router_llm)
        if write_mode == "new":
            # 人工指定：强制新建文件（文件名=主题-来源短标签），跳过合并决策
            result = _new_write(topic, cleaned, label, domain)
        else:
            # auto / merge：读目标库摘要由 LLM 判定合并或新建（merge 语义=尽量合并，
            # 无合适文件/决策失败时 _decide_merge 返回 new → 保守新建）
            action, target_file = _decide_merge(topic, cleaned, domain, router_llm)
            if action == "merge":
                result = _merge_write(topic, target_file, cleaned, domain, llm)
            else:
                result = _new_write(topic, cleaned, label, domain)
        note = f"（匹配现有库「{topic}」）" if matched else ""
        lines.append(f"{result}{note}｜来源：{label}")

    return {"collect_result": "\n".join(lines)}


def _fetch_all(source: str):
    """拆分为来源列表，逐个获取，返回 [(来源项, 标签, 内容)]。
    多来源拆分仅对"全 URL 列表"或"全文件路径列表"生效；
    含直接文本（非 URL/文件）时整段作为一个来源——避免中文逗号把正文拆碎"""
    parts = [p.strip() for p in re.split(r"[,，\n]+", source) if p.strip()]
    all_urls = all(p.startswith(("http://", "https://")) for p in parts) if parts else False
    all_files = all(os.path.exists(p) for p in parts) if parts else False
    candidates = parts if (all_urls or all_files) else [source.strip()]
    items = []
    for item in candidates:
        if not item:
            continue
        if item.startswith(("http://", "https://")):
            content = skill_registry.get_run_func("fetch_url_content")(item)
            label = _url_short_label(item)
        elif os.path.exists(item):
            content = skill_registry.get_run_func("read_local_file")(item)
            label = os.path.basename(item)
        else:
            content = item
            label = "直接文本"
        items.append((item, label, content))
    return items


def _url_short_label(url: str) -> str:
    """URL 取域名做来源短标签（用于文件名区分不同来源）"""
    m = re.match(r"https?://([^/]+)", url)
    return m.group(1) if m else url[:20]


def _organize(content: str, label: str, state: State, llm) -> str:
    """LLM 整理清洗：去广告/导航噪声，分条列要点；失败返回空"""
    values_text = format_values_for(state.get("value_profiles"), VP_DIMS)
    values_block = f"【本次任务价值观框架】\n{values_text}\n" if values_text else ""
    prompt = f"""
你是资料整理员。以下是从【{label}】获取的原始内容：
---原始内容开始---
{content[:RAW_LIMIT]}
---原始内容结束---
{values_block}任务：整理为可直接入库的资料文本，严格按以下格式输出：
标题：{sanitize_filename(label, 20)} 资料
来源：{label}
要点：
（分条列出核心内容，去除广告、导航、无关噪声，保留事实与关键信息）
整理时遵循上述价值观框架。
只输出整理后的资料正文，不要多余解释。
"""
    try:
        resp = llm.invoke(prompt)
        text = str(getattr(resp, "content", "")).strip()
        return text or ""
    except Exception:
        return ""


def _resolve_topic(user_topic: str, cleaned: str, domain, router_llm) -> tuple:
    """主题归一：用户给了主题→对照现有库做同义匹配（除非明确要求独立）；
    主题留空→LLM 从资料提炼主题短语并归一。
    返回 (主题库显示名, 是否匹配现有库)"""
    overview = skill_registry.get_run_func("list_topics")(domain)
    if not user_topic:
        prompt = f"""
你是资料库管理员。请为以下待入库资料确定主题库。
现有主题库概览：
{overview}
待入库资料内容预览：
{cleaned[:PREVIEW_LEN]}
任务：
1. 从资料内容提炼一个主题短语（不超过 12 字）；
2. 判断该主题与现有哪个主题库语义相近/同义 → 输出该库主题名（复用，避免碎片化）；
   若无相近库 → 输出新主题短语。
只输出JSON：{{"topic":"主题名","matched_existing":true或false}}，不要多余文字。
"""
    else:
        prompt = f"""
你是资料库管理员。以下资料将入库，请判断主题库归属。
用户填写的主题：{user_topic}
现有主题库概览：
{overview}
待入库资料内容预览：
{cleaned[:PREVIEW_LEN]}
任务：
1. 若用户主题与现有某主题库语义相近/同义 → 复用该库主题名；
2. 否则保留用户主题；
3. 例外：仅当用户主题或资料中明确要求"独立建库/分开存放/不要合并/新建主题"时，才必须使用新主题（不匹配现有库）。
只输出JSON：{{"topic":"主题名","matched_existing":true或false}}，不要多余文字。
"""
    try:
        resp = router_llm.invoke(prompt)
        text = str(getattr(resp, "content", "")).strip()
        obj = _parse_json_obj(text)
        topic = str(obj.get("topic") or "").strip() if isinstance(obj, dict) else ""
        if topic:
            return topic, bool(obj.get("matched_existing"))
    except Exception:
        pass
    return (user_topic or "默认资料"), False


def _decide_merge(topic: str, cleaned: str, domain, router_llm) -> tuple:
    """文件级合并决策：读目标库文件摘要，LLM 判断 merge/new。
    返回 ("merge", 目标文件名) 或 ("new", "")；任何异常 → 保守新建"""
    summary = skill_registry.get_run_func("read_topic_summary")(topic, domain)
    if "【提示】主题库「" in summary or "不存在" in summary:
        return "new", ""
    prompt = f"""
你是资料归档助手。目标主题库「{topic}」现有文件如下（含摘要）：
{summary}
新资料内容预览：
{cleaned[:PREVIEW_LEN]}
任务：判断新资料应合并到某个现有文件，还是新建文件。
规则：
- 与某文件主题相同/互补（如同一话题的补充资料、后续批次）→ 合并
- 内容独立、或与现有文件主题差异大 → 新建
- 现有文件已很长（> {MERGE_MAX_CHARS} 字符，摘要里有标注）→ 不合并，新建
只输出JSON：{{"action":"merge或new","target_file":"要合并的文件名（含扩展名，merge时必填，new时填空）","reason":"一句话"}}，不要多余文字。
"""
    try:
        resp = router_llm.invoke(prompt)
        obj = _parse_json_obj(str(getattr(resp, "content", "")).strip())
        if isinstance(obj, dict) and obj.get("action") == "merge":
            target = str(obj.get("target_file") or "").strip()
            if target:
                return "merge", target
    except Exception:
        pass
    return "new", ""


def _merge_write(topic: str, target_file: str, cleaned: str, domain, llm) -> str:
    """合并写入：读原文件全文 → 备份 → LLM 清洗合并 → 覆盖原文件。
    原文件超长/不存在/合并失败 → 全部保守降级为新建（不动原文件）"""
    old = skill_registry.get_run_func("read_topic_file")(topic, target_file, domain)
    if old.startswith("【提示】") or len(old) > MERGE_MAX_CHARS:
        return _new_write(topic, cleaned, "合并降级-新建", domain)
    try:
        prompt = f"""
你是资料归档助手。请把以下两份同主题资料合并为一份完整资料：
要求：去除重复内容，保留全部关键信息，结构清晰（保留原文小标题与要点），输出合并后的完整正文。
【原资料】
{old[:MERGE_OLD_LIMIT]}
【新资料】
{cleaned}
只输出合并后的正文，不要多余解释。
"""
        resp = llm.invoke(prompt)
        merged = str(getattr(resp, "content", "")).strip()
        if not merged:
            return _new_write(topic, cleaned, "合并失败-新建", domain)
    except Exception:
        return _new_write(topic, cleaned, "合并异常-新建", domain)

    repo_dir = _resolve_repo_dir(topic, domain)
    fpath = os.path.join(repo_dir, target_file)
    if not os.path.exists(fpath):
        return _new_write(topic, cleaned, "目标文件缺失-新建", domain)
    # 备份原文件（_bak_ 前缀，读端自动忽略）
    try:
        shutil.copy2(fpath, os.path.join(repo_dir, f"{BACKUP_PREFIX}{target_file}"))
    except Exception:
        pass
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(merged if merged.endswith("\n") else merged + "\n")
    return f"✅ 已合并写入「{topic}」：{target_file}（原内容+新内容清洗合并，备份 {BACKUP_PREFIX}{target_file}）"


def _new_write(topic: str, cleaned: str, label: str, domain) -> str:
    """新建文件：文件名=主题-来源短标签（自动编号，不同来源自然不同文件）"""
    short = sanitize_filename(label, 16) or "资料"
    fname = f"{sanitize_filename(topic, 24)}-{short}"
    return skill_registry.get_run_func("write_local_database")(
        filename=fname,
        content=cleaned,
        topic=topic or "00-默认资料",
        mode="overwrite",
        domain=domain,
    )


def _resolve_repo_dir(topic: str, domain):
    """按主题名定位主题库目录（与 read 系列同一匹配规则）；找不到返回 None"""
    from core.paths import TOPIC_PREFIX_PATTERN, LOCAL_DB, local_db_root
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
            if os.path.isdir(os.path.join(root, name)) and re.sub(TOPIC_PREFIX_PATTERN, "", name) == clean:
                return os.path.join(root, name)
    return None


def _parse_json_obj(text: str):
    """容错解析 LLM 输出的 JSON 对象（去 markdown 代码块/杂文本）"""
    import json
    if not text:
        return {}
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


AGENT_META = {
    "name": "collector",
    "display_name": "资料采集员",
    "description": "资料采集角色：从网络URL/本地文件/直接文本获取资料，AI整理清洗后智能入库"
                   "（自动归纳主题库、同义词合并、按内容判断新建或追加文件）。"
                   "适合需要收集、整理、入库资料的场景（如把网页文章或本地文件沉淀进资料库）",
    "persona": {"name": "拾贝", "tone": "机敏高效", "tags": ["高效", "广纳"]},
    "consumes": ["evidence", "style"],
    "tier": "standard",  # 固定档位（任务级指定可覆盖）
    "run": run
}
