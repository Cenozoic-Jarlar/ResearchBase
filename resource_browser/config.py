"""
[模块] resource_browser/config.py — 资源浏览器分区配置（写死，无需注册表）
[职责] 定义三个分区（资产/档案/日志）各自锁定的目录、读写权限、扩展名白名单
[设计思想] 固定项目结构 → 配置写死比动态注册更简单更安全（"锁死"）；
           权限为分区级：下级目录自动继承上级目录权限，不做逐文件控制；
           目录以白名单形式列明，天然排除 .env/venv/.git 等敏感内容
[关键约定] ★ 三档权限：assets=只读 / archives=可编辑（写前自动备份 .bak）/ logs=只读；
           ★ roots 内 path 可为目录（整树）或单文件（根级模块直接展示）；
           ★ 新增资产类型 = 在对应分区 roots 加一项，不改其他代码
[被谁调用] service.py（全部逻辑）、api.py（分区清单）、前端（Tab 展示）
[修改注意] 改目录/权限影响前端显示与安全边界，需同步测试
"""
import os

from core.paths import PROJECT_ROOT, LOCAL_DB, OUTPUT_DIR, ARCHIVE_DIR

LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")


def _root(*parts):
    return os.path.join(PROJECT_ROOT, *parts)


# 三个分区（顺序即前端 Tab 顺序）
# root.prefix：树条目路径前缀（消除多 root 同名歧义）；目录 root=目录名，单文件 root=文件名
RESOURCE_SECTIONS = [
    {
        "key": "assets",
        "label": "资产展示",
        "readonly": True,
        "ext": {".py", ".md", ".txt"},
        "roots": [
            {"label": "Agent 代码", "prefix": "agent_registry", "path": _root("agent_registry")},
            {"label": "流程与调度", "prefix": "planner", "path": _root("planner")},
            {"label": "Skill 工具", "prefix": "skills", "path": _root("skills")},
            {"label": "内部功能", "prefix": "tools", "path": _root("tools")},
            {"label": "价值观与记忆", "prefix": "memory", "path": _root("memory")},
            {"label": "核心框架", "prefix": "core", "path": _root("core")},
            {"label": "根级模块", "prefix": "llm_config.py", "path": _root("llm_config.py")},
            {"label": "状态模型", "prefix": "state_model.py", "path": _root("state_model.py")},
            {"label": "命令行入口", "prefix": "main.py", "path": _root("main.py")},
            {"label": "Web 入口", "prefix": "gui_web.py", "path": _root("gui_web.py")},
            {"label": "转换工具", "prefix": "md2docx.py", "path": _root("md2docx.py")},
        ],
    },
    {
        "key": "archives",
        "label": "档案管理",
        "readonly": False,
        "ext": {".md", ".txt"},
        "roots": [
            {"label": "主题资料库", "prefix": "LocalDataBase", "path": LOCAL_DB},
            {"label": "输出文章", "prefix": "output", "path": OUTPUT_DIR},
            {"label": "主题域（domains）", "prefix": "domains", "path": os.path.join(PROJECT_ROOT, "domains")},
        ],
    },
    {
        "key": "logs",
        "label": "日志功能",
        "readonly": True,
        "ext": {".log", ".md"},
        "roots": [
            {"label": "运行日志", "prefix": "logs", "path": LOGS_DIR},
            {"label": "研究档案", "prefix": "archives", "path": ARCHIVE_DIR},
        ],
    },
]

# 树遍历时跳过的目录名（任意层级）
SKIP_DIRS = {"__pycache__", ".git", ".idea", "venv", ".venv", "node_modules"}
