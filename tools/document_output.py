"""
[模块] tools/document_output.py — 文档输出（程序内部功能，非 LLM Skill）
[职责] 把最终文章打印到终端 / 保存到输出目录（生成时间+主题命名，UTF-8）；支持主题域
[设计思想] tools/ 定位为"程序内部非 Skill 功能"：由编排层（main.py / task_manager）直接调用，
           不进入 LLM 工具清单；若未来需要"LLM 自主决定输出方式"再抽为 Skill
[关键约定] 输出文件命名"生成时间+主题"：YYYYMMDD_HHMM_主题短语.md（主题清洗非法字符并截断）；
           默认格式 md（研究文章天然为 Markdown 结构，md 是 txt 超集，纯文本阅读器亦可读）；
           fmt 参数可切换 "txt"/"md"；输出按主题域落盘（domain=None=通用层 output/，
           具体域=domains/<域>/output/），域内暂不分类（平铺），主题短语保证人工/AI 可读
[被谁调用] main.py（show_result）、task_manager（GUI done 路径）
[修改注意] sanitize_filename 被 archivist_agent / collector_agent 复用，改清洗规则需同步
"""
import os
import re
from datetime import datetime

from core.paths import output_root

VALID_FORMATS = ("txt", "md")


def sanitize_filename(text: str, max_len: int = 30) -> str:
    """把任意文本清洗为安全文件名：去非法字符/空白/控制符，截断"""
    text = re.sub(r'[\\/:*?"<>|\r\n\t]', "", text).strip()
    text = re.sub(r"\s+", "", text)
    return text[:max_len] or "untitled"


def save_article(article: str, topic: str, filename: str = None, fmt: str = "md", domain: str = None) -> str:
    """
    将文章保存为文件（生成时间+主题命名）。
    :param article: 文章正文
    :param topic: 研究主题（写入文件头 + 用于命名）
    :param filename: 自定义文件名（不含扩展名）；默认 生成时间_主题短语
    :param fmt: 输出格式 "txt" / "md"（默认 md；md 为纯文本超集，两者均可直接阅读）
    :param domain: 主题域名（None=通用层 output/，默认；具体域=domains/<域>/output/）
    :return: 保存的完整文件路径
    """
    if fmt not in VALID_FORMATS:
        raise ValueError(f"不支持的输出格式：{fmt}，可选 {VALID_FORMATS}")
    out_dir = output_root(domain)
    os.makedirs(out_dir, exist_ok=True)
    if not filename:
        now = datetime.now()
        filename = f"{now.strftime('%Y%m%d_%H%M')}_{sanitize_filename(topic)}"
    fpath = os.path.join(out_dir, f"{filename}.{fmt}")
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(f"研究主题：{topic}\n\n{article}")
    return fpath


def print_article(article: str, topic: str = ""):
    """在终端打印最终文章（带分隔标题）"""
    print("\n" + "=" * 30 + " 最终研究结果 " + "=" * 30)
    if topic:
        print(f"研究主题：{topic}\n")
    print(article)
