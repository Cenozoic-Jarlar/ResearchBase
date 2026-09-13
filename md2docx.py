"""
[模块] md2docx.py — Markdown → Word 转换入口（独立小工具，不侵入 main.py 主流程）
[职责] 把指定 .md 文件/目录（缺省 output/ 全部）转换为 .docx
[设计思想] 与主流程解耦：研究完成后输出 md，需要分享/存档时按需转换；
           目录模式批量转换（output/ 下的历史文章、archives/ 档案均可）
[关键约定] 转换失败只提示不中断（批量场景继续处理后续文件）；
           不修改源 md 文件
[被谁调用] 直接运行：venv\\Scripts\\python.exe md2docx.py [文件或目录，可多个]
[修改注意] 与 tools/md2docx.py 配套；默认目录改了需同步 core.paths
"""
import os
import sys

from tools.md2docx import md_to_docx
from core.paths import OUTPUT_DIR


def _collect_md(targets: list) -> list:
    """把参数展开为 md 文件列表：文件直接收录，目录递归扫 .md，缺省 output/"""
    if not targets:
        targets = [OUTPUT_DIR]
    files = []
    for t in targets:
        if os.path.isdir(t):
            for root, _, names in os.walk(t):
                for n in sorted(names):
                    if n.endswith(".md"):
                        files.append(os.path.join(root, n))
        elif t.endswith(".md") and os.path.exists(t):
            files.append(t)
        else:
            print(f"⚠ 跳过无效路径：{t}")
    return files


def main():
    files = _collect_md(sys.argv[1:])
    if not files:
        print("未找到可转换的 .md 文件。用法：python md2docx.py [文件或目录]")
        return

    ok, fail = 0, 0
    for f in files:
        try:
            out = md_to_docx(f)
            print(f"✅ {f} → {out}")
            ok += 1
        except Exception as e:
            print(f"❌ {f} 转换失败：{e}")
            fail += 1
    print(f"\n完成：成功 {ok}，失败 {fail}，共 {len(files)} 个文件")


if __name__ == "__main__":
    main()
