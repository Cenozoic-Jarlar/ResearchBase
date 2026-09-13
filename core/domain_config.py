"""
[模块] core/domain_config.py — 域配置与域管理（新建/重命名/统计/配置解析）
[职责] 解析域自描述配置 _domain.md；提供建域（骨架+模板）、重命名、概览统计等管理函数
[设计思想] 域 = 数据隔离单元，配置 = 可选增强（与主题库 _repo.md 同构：目录即注册，配置只影响表现）；
           域默认价值观让"选域即选风格"：任务未显式选价值观时，用域默认 → 再回退关键词自动匹配/general；
           配置格式为极简键值行（"键：值"），零依赖、人工/AI 均可读
[关键约定] ★ 配置文件名与保留名校验在 core/paths.py（DOMAIN_CONFIG_FILE / is_reserved_domain_name）；
           ★ "默认价值观"行：逗号/顿号/空白分隔的价值观框架名列表（可空）；框架不存在时由
             memory_registry.select_profiles 静默跳过并回退，不在此校验（保持低耦合）；
           ★ 新建域 = 目录骨架 + 写 _domain.md 模板（已存在则不覆盖，保护人工修改）；
           ★ 重命名 = 移动目录；校验目标名非保留、不存在；不影响已快照 domain 的运行中任务
[被谁调用] web_gui/app.py（/api/domains 路由）、main.py / task_manager.make_init_state（域默认价值观）、
           测试 test_domain_system.py
[修改注意] 改 _domain.md 解析格式需同步模板（domains/_模板域/_domain.md）与测试；
           域名大小写不敏感（统一小写），改名/建域前先 _norm_domain 归一化
"""
import os
import re

from core.paths import (LOCAL_DB, DOMAINS_ROOT, DOMAIN_CONFIG_FILE, DEFAULT_DOMAIN,
                        list_domains, ensure_domain_dirs, is_reserved_domain_name)

# 域内主题库统计：主题库 = 含 _repo.md 的子目录（与 skills.list_topics 同一判定规则）
REPO_META = "_repo.md"


def _domain_dir(domain: str) -> str:
    """域名目录（不做存在性检查，供调用方自行判断）"""
    return os.path.join(DOMAINS_ROOT, str(domain).strip().lower())


def _config_path(domain: str) -> str:
    return os.path.join(_domain_dir(domain), DOMAIN_CONFIG_FILE)


# ---------- 配置解析 ----------

def read_domain_config(domain: str) -> dict:
    """
    读取域配置（_domain.md）为 dict；无文件/异常返回空 dict。
    :return: {"intro": str, "default_profiles": list, "style": str}
    """
    cfg = {"intro": "", "default_profiles": [], "style": ""}
    path = _config_path(domain)
    if not os.path.exists(path):
        return cfg
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "：" in line and not line.startswith(("#", "-", "---")):
                    key, _, val = line.partition("：")
                    key = key.strip()
                    val = val.strip()
                    if key == "域简介":
                        cfg["intro"] = val
                    elif key == "默认价值观":
                        cfg["default_profiles"] = _split_profiles(val)
                    elif key == "风格偏好":
                        cfg["style"] = val
    except Exception:
        pass
    return cfg


def _split_profiles(val: str) -> list:
    """把"默认价值观"行拆成框架名列表（逗号/顿号/空白分隔，去空）"""
    return [p for p in re.split(r"[,，、\s]+", val) if p]


def default_profiles_for(domain: str) -> list:
    """域默认价值观框架名列表（无配置/未填写返回空列表）"""
    if not domain:
        return []
    return read_domain_config(domain).get("default_profiles", [])


# ---------- 域管理 ----------

def create_domain(domain: str, intro: str = "") -> str:
    """
    新建域：目录骨架 + _domain.md 模板（已存在不覆盖）。
    :param domain: 域名（自动小写归一化）
    :return: 提示文本（成功/已存在）
    """
    d = str(domain or "").strip().lower()
    if not d:
        return "❌ 域名不能为空"
    if is_reserved_domain_name(d):
        return f"❌ 域名「{d}」为保留名（通用层或下划线开头），请换一个"
    if os.path.isdir(_domain_dir(d)):
        return f"✅ 域「{d}」已存在（未重复创建）"
    dpath = ensure_domain_dirs(d)
    _write_config_template(dpath, d, intro)
    return f"✅ 已创建域「{d}」：{dpath}（含 _domain.md 配置模板与 资料/输出/档案 骨架）"


def rename_domain(old: str, new: str) -> tuple:
    """
    重命名域：移动目录。
    :return: (ok: bool, msg: str)
    """
    old_d = str(old or "").strip().lower()
    new_d = str(new or "").strip().lower()
    if not old_d or not new_d:
        return False, "旧域名与新域名都不能为空"
    if old_d == new_d:
        return False, "新旧域名相同，无需重命名"
    old_path = _domain_dir(old_d)
    if not os.path.isdir(old_path):
        return False, f"域「{old_d}」不存在"
    if is_reserved_domain_name(new_d):
        return False, f"新域名「{new_d}」为保留名（通用层或下划线开头），请换一个"
    new_path = _domain_dir(new_d)
    if os.path.exists(new_path):
        return False, f"新域名「{new_d}」已存在，请换一个"
    os.rename(old_path, new_path)
    return True, f"✅ 域已重命名：「{old_d}」→「{new_d}」（资源浏览器路径已随之变化）"


def list_domains_with_stats() -> dict:
    """
    域概览统计：{域名: {"topics": 主题库数, "files": 资料文件数}}（通用层 general 单独计入）
    """
    stats = {}
    stats[DEFAULT_DOMAIN] = _count_topics(LOCAL_DB)
    for d in list_domains():
        stats[d] = _count_topics(os.path.join(_domain_dir(d), "LocalDataBase"))
    return stats


def _count_topics(root: str) -> dict:
    """统计一个资料库根下的主题库数与资料文件数（根不存在返回 0/0）"""
    if not os.path.isdir(root):
        return {"topics": 0, "files": 0}
    topics = files = 0
    for name in os.listdir(root):
        sub = os.path.join(root, name)
        if os.path.isdir(sub) and os.path.exists(os.path.join(sub, REPO_META)):
            topics += 1
            files += len([f for f in os.listdir(sub)
                          if f.endswith((".md", ".txt")) and not f.startswith("_")])
    return {"topics": topics, "files": files}


def _write_config_template(dpath: str, domain: str, intro: str = "") -> None:
    """写 _domain.md 模板（不存在才写，保护人工已有修改）"""
    path = os.path.join(dpath, DOMAIN_CONFIG_FILE)
    if os.path.exists(path):
        return
    intro_line = f"域简介：{intro}" if intro else "域简介："
    content = f"""# 域配置：{domain}

{intro_line}
默认价值观：
风格偏好：

---
说明：本文件是域的可选自描述配置（与主题库 _repo.md 同构，人工/AI 均可读）。
「默认价值观」填价值观框架名（逗号分隔，可留空），如：policy, technology。
任务在该域运行时：未显式选择价值观 → 自动用域默认 → 再回退关键词自动匹配 / general。
框架库在 memory/profiles/（全局单份，不按域复制）。
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
