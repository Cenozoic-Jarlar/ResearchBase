"""
[模块] skills/read_local_file.py — Skill：本地文件读取（txt/md）
[职责] 读取本地文件文本内容，供资料整理入库（支持 .txt/.md，带大小限制）
[设计思想] 本地资料入库的原子能力：覆盖"已有本地文件→整理→入库"场景；
           不解析 docx/pdf（避免重依赖），需要时由 collector 提示用户转 txt
[关键约定] ★ 只读 .txt/.md；上限 MAX_SIZE（防大文件撑爆上下文）；失败返回提示文本不抛异常
[被谁调用] collector_agent（资料采集员）
[修改注意] 新增格式支持时在此扩展，并同步更新 SKILL_META 描述
"""
import os

MAX_SIZE = 2 * 1024 * 1024  # 2MB


def run(path: str) -> str:
    """
    读取本地文本文件。
    :param path: 本地文件绝对/相对路径
    :return: str 文件文本；失败返回【提示】开头的问题说明
    """
    path = str(path).strip().strip('"').strip("'")
    if not os.path.exists(path):
        return f"【提示】本地文件不存在：{path}"
    if not os.path.isfile(path):
        return f"【提示】不是文件：{path}"
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".txt", ".md", ".text"):
        return f"【提示】暂不支持该格式（{ext}），请提供 .txt/.md 文件"
    if os.path.getsize(path) > MAX_SIZE:
        return f"【提示】文件过大（>{MAX_SIZE // 1024 // 1024}MB），请拆分后入库"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        try:
            with open(path, "r", encoding="gbk") as f:
                return f.read()
        except Exception as e:
            return f"【提示】文件读取失败（编码不识别）：{e}"
    except Exception as e:
        return f"【提示】文件读取失败：{e}"


SKILL_META = {
    "name": "read_local_file",
    "description": "【本地文件读取】读取本地 .txt/.md 文本文件内容。"
                   "参数：path(文件路径)。返回：文件文本；失败返回【提示】开头的问题说明。"
                   "用于从本地已有文件获取资料。",
    "run": run
}
