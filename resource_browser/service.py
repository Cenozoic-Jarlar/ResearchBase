"""
[模块] resource_browser/service.py — 资源浏览器纯逻辑（不依赖 Flask，可独立测试）
[职责] 分区清单 / 目录树 / 文件读取（大文件截断）/ 文件写入（备份 + 安全校验）
[设计思想] 权限由分区配置决定（下级继承上级）；路径用"相对分区根的相对路径"传参，
           后端拼装后再二次校验，杜绝目录穿越；扩展名走分区白名单
[关键约定] ★ 写操作三关：分区 readonly 拒绝 → 路径必须落在分区某 root 内 → 扩展名必须在白名单；
           ★ 写入前自动备份 .bak（保留最近一版）；只读分区永不产生写副作用；
           ★ 读取同样校验路径与扩展名（防越权读取敏感文件）
[被谁调用] api.py 路由（薄壳）、test_resource_browser_system.py
[修改注意] 安全校验逻辑改动必须同步测试；新增分区类型需同步 config.py
"""
import os
import shutil

from resource_browser.config import RESOURCE_SECTIONS, SKIP_DIRS

# 单次读取最大字符数，超出截断（详细日志可能很大）
MAX_READ_CHARS = 200_000


def list_sections() -> list:
    """返回分区清单（供前端 Tab 与权限展示，不暴露物理路径）"""
    return [{"key": s["key"], "label": s["label"], "readonly": s["readonly"]} for s in RESOURCE_SECTIONS]


def _find_section(key: str) -> dict:
    for s in RESOURCE_SECTIONS:
        if s["key"] == key:
            return s
    raise KeyError(f"未知分区：{key}")


def _resolve(section: dict, rel_path: str) -> str:
    """
    把"prefix/相对路径"解析为绝对路径，并校验落在分区某 root 内（防目录穿越）。
    单文件 root 只允许匹配该文件名；目录 root 允许其下任意相对路径。
    """
    if not rel_path or ".." in rel_path.replace("\\", "/").split("/"):
        raise ValueError("非法路径")
    rel_path = rel_path.replace("\\", "/").strip("/")
    for r in section["roots"]:
        prefix = r["prefix"]
        root = os.path.abspath(r["path"])
        if os.path.isfile(root):
            # 单文件 root：path 必须恰好等于 prefix（即文件名）
            if rel_path == prefix:
                return root
            continue
        # 目录 root：path 必须以 "prefix/" 开头
        if rel_path == prefix:
            return root
        if rel_path.startswith(prefix + "/"):
            cand = os.path.abspath(os.path.join(root, rel_path[len(prefix) + 1:]))
            if os.path.commonpath([cand, root]) == root:
                return cand
    raise ValueError("路径不在允许范围内")


def _check_ext(section: dict, abs_path: str):
    ext = os.path.splitext(abs_path)[1].lower()
    if ext not in section["ext"]:
        raise ValueError(f"扩展名 {ext or '（无）'} 不在分区白名单内")


def tree_for_section(key: str) -> list:
    """
    返回分区目录树：平铺条目 [{path, name, type}]，type ∈ dir|file；
    path 为"prefix/相对路径"（消除多 root 同名歧义）；目录节点也输出（供前端树形折叠渲染）。
    排序保证：父目录在前、同级目录先于文件、同层按路径字典序。
    """
    section = _find_section(key)
    entries = []
    for r in section["roots"]:
        root = os.path.abspath(r["path"])
        prefix = r["prefix"]
        if os.path.isfile(root):
            name = os.path.basename(root)
            if os.path.splitext(name)[1].lower() in section["ext"]:
                entries.append({"path": prefix, "name": name, "type": "file"})
            continue
        if not os.path.isdir(root):
            continue
        dirs = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            rel_dir = os.path.relpath(dirpath, root)
            if rel_dir != ".":
                dirs.append({
                    "path": f"{prefix}/{rel_dir.replace(os.sep, '/')}",
                    "name": os.path.basename(dirpath),
                    "type": "dir",
                })
            for fn in sorted(filenames):
                if os.path.splitext(fn)[1].lower() not in section["ext"]:
                    continue
                abs_path = os.path.join(dirpath, fn)
                rel = os.path.relpath(abs_path, root).replace("\\", "/")
                entries.append({"path": f"{prefix}/{rel}", "name": fn, "type": "file"})
        entries.extend(dirs)
    # 父目录在前（深度升序），同级目录先于文件，同深度按路径排序
    entries.sort(key=lambda e: (e["path"].count("/"), 0 if e["type"] == "dir" else 1, e["path"]))
    return entries


def read_entry(key: str, rel_path: str, max_chars: int = MAX_READ_CHARS) -> dict:
    """读取文件内容；超长截断并返回 truncated/total"""
    section = _find_section(key)
    abs_path = _resolve(section, rel_path)
    _check_ext(section, abs_path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"文件不存在：{rel_path}")
    with open(abs_path, encoding="utf-8", errors="replace") as f:
        content = f.read()
    truncated = len(content) > max_chars
    return {
        "content": content[:max_chars],
        "truncated": truncated,
        "total": len(content),
    }


def write_entry(key: str, rel_path: str, content: str) -> dict:
    """写入文件：只读分区拒绝；写前备份 .bak；返回备份路径"""
    section = _find_section(key)
    if section["readonly"]:
        raise PermissionError(f"分区【{section['label']}】为只读，禁止修改")
    abs_path = _resolve(section, rel_path)
    _check_ext(section, abs_path)

    backup_path = None
    if os.path.isfile(abs_path):
        backup_path = abs_path + ".bak"
        shutil.copy2(abs_path, backup_path)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(content)
    return {"ok": True, "path": rel_path, "backup": backup_path}
