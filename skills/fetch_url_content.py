"""
[模块] skills/fetch_url_content.py — Skill：网络 URL 抓取（正文提取）
[职责] 抓取网页并提取正文文本（去脚本/样式/导航/页脚等噪声），供资料整理入库
[设计思想] 网络资料入库的原子能力：LLM 不内置实时联网，URL 抓取是覆盖"网页文章入库"
           主场景的轻量方案；实时搜索（关键词→URL）依赖搜索 API，预留为后续增强
[关键约定] ★ 输出为纯文本正文（去 HTML 标签）；超时 15s、正文上限 MAX_CHARS（防超大页）；
           失败返回错误提示文本（不抛异常，供 Agent 直接处理）
[被谁调用] collector_agent（资料采集员）
[修改注意] 加搜索能力时在此扩展 run 的参数（如 keyword）或新增 Skill，保持本函数职责单一
"""
import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
MAX_CHARS = 50000  # 正文最大字符数（超出截断，防超大页面占满上下文）


def run(url: str) -> str:
    """
    抓取 URL 并提取正文文本。
    :param url: 网页地址
    :return: str 正文纯文本；失败时返回【提示】开头的问题说明
    """
    url = str(url).strip()
    if not url.startswith(("http://", "https://")):
        return f"【提示】无效URL：{url}，需以 http:// 或 https:// 开头"
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
    except Exception as e:
        return f"【提示】网页抓取失败：{e}"

    # 编码：优先响应头声明，否则按字节探测
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding

    try:
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside",
                         "iframe", "form", "button", "svg"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
    except Exception as e:
        return f"【提示】正文解析失败：{e}"

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    body = "\n".join(lines)
    if not body.strip():
        return "【提示】页面未提取到正文（可能是纯 JS 渲染页面）"
    if len(body) > MAX_CHARS:
        body = body[:MAX_CHARS] + "\n…（内容过长已截断）"
    return body


SKILL_META = {
    "name": "fetch_url_content",
    "description": "【网络抓取】抓取网页 URL 并提取正文纯文本（自动去脚本/导航/页脚噪声）。"
                   "参数：url(以 http:// 或 https:// 开头的网页地址)。"
                   "返回：正文文本；失败返回【提示】开头的问题说明。用于从网络获取资料。",
    "run": run
}
