"""
[测试] test_md2docx_system.py — Markdown 转 Word 模块
[运行] venv\\Scripts\\python.exe test_md2docx_system.py
[约定] 不调 LLM；覆盖：md→docx 落盘且结构保留 / 默认输出路径 / 文件不存在报错
"""
import os

from tools.md2docx import md_to_docx

TMP_MD = "_tmp_md2docx_test.md"
TMP_DOCX = "_tmp_md2docx_test.docx"


def test_md_to_docx_basic():
    print("=" * 60)
    print("【测试1：md→docx 转换与结构保留】")
    print("=" * 60)
    md_text = """研究主题：测试主题

# 一级标题

这是正文段落，包含**加粗**和普通中文文本。

## 二级标题

- 列表项一
- 列表项二

> 引用内容
"""
    with open(TMP_MD, "w", encoding="utf-8") as f:
        f.write(md_text)
    out = md_to_docx(TMP_MD)
    assert out == TMP_DOCX, f"默认输出应同目录同名 .docx：{out}"
    assert os.path.exists(out), "docx 应落盘"

    # 用 python-docx 读回验证结构
    from docx import Document
    doc = Document(out)
    texts = [p.text for p in doc.paragraphs]
    joined = "\n".join(texts)
    assert "研究主题：测试主题" in joined
    assert "一级标题" in joined
    assert "正文段落" in joined and "加粗" in joined
    assert "列表项一" in joined
    assert "引用内容" in joined
    print("✅ docx 落盘，标题/段落/列表/引用/加粗均保留\n")
    os.remove(TMP_MD)
    os.remove(TMP_DOCX)


def test_md_to_docx_custom_path():
    print("=" * 60)
    print("【测试2：自定义输出路径】")
    print("=" * 60)
    with open(TMP_MD, "w", encoding="utf-8") as f:
        f.write("# 标题\n\n内容")
    out = md_to_docx(TMP_MD, out_path="_tmp_custom.docx")
    assert out == "_tmp_custom.docx" and os.path.exists(out)
    print("✅ 自定义输出路径生效\n")
    os.remove(TMP_MD)
    os.remove("_tmp_custom.docx")


def test_md_to_docx_missing_file():
    print("=" * 60)
    print("【测试3：文件不存在报错】")
    print("=" * 60)
    try:
        md_to_docx("_tmp_不存在.md")
        assert False, "应抛 FileNotFoundError"
    except FileNotFoundError:
        print("✅ 正确抛出 FileNotFoundError\n")


if __name__ == "__main__":
    test_md_to_docx_basic()
    test_md_to_docx_custom_path()
    test_md_to_docx_missing_file()
    print("=" * 60)
    print("✅ md→docx 测试全部通过！")
    print("=" * 60)
