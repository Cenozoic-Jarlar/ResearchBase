"""
[模块] tools/md2docx.py — Markdown 转 Word（程序内部功能，非 LLM Skill）
[职责] 把 .md 文件（研究文章 output/、研究档案 archives/）转换为 .docx
[设计思想] 分享/存档场景 Word 比 md 通用（非技术人群可读）；链路
           md → markdown.HTML → htmldocx → docx，纯 pip 无系统依赖，
           中文由 Word 样式承载（无字体坑）；PDF 不直接做：docx 在 Word/WPS
           一键另存为 PDF 即可，避免中文 PDF 渲染的依赖负担
[关键约定] 输出与输入同目录同名 .docx（可传 out_path 覆盖）；
           表格/图片不在 htmldocx 0.0.6 支持范围，表格会以文本段落形式保留（可接受降级）；
           标题/段落/列表/引用/加粗等结构正常转换
[被谁调用] 根目录 md2docx.py（CLI 入口）
[修改注意] 若未来需要完整表格/图片/样式控制，改用 pandoc（需另装二进制）；
           新增 md 特性需确认 htmldocx 支持，否则降级为文本
"""
import os

import markdown
from docx import Document
from htmldocx import HtmlToDocx


def md_to_docx(md_file: str, out_path: str = None) -> str:
    """
    把单个 md 文件转换为 docx。
    :param md_file: 源 .md 文件路径
    :param out_path: 输出 .docx 路径；缺省 = 同目录同名 .docx
    :return: 生成的 docx 完整路径
    """
    if not os.path.exists(md_file):
        raise FileNotFoundError(f"文件不存在：{md_file}")
    if not out_path:
        out_path = os.path.splitext(md_file)[0] + ".docx"

    with open(md_file, encoding="utf-8") as f:
        text = f.read()
    html = markdown.markdown(text, extensions=["sane_lists"])

    doc = Document()
    HtmlToDocx().add_html_to_document(html, doc)
    doc.save(out_path)
    return out_path
