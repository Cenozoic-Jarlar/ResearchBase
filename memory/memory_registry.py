"""
[模块] memory/memory_registry.py — 价值观框架自动注册器 + 选择/注入/格式化公共函数
[职责] 扫描 memory/profiles/*.py 的 PROFILE_META 自动注册；
       提供 主题匹配、显式选择、任务注入、按维度格式化 等公共函数
[设计思想] 与 skill_registry 同构：框架是"可插拔配置"，Agent 与框架只通过
           "维度标签"（values 的键）连接，互不知晓对方存在——
           新增框架/新增 Agent 均零改动对方
[关键约定] ★ PROFILE_META 结构：{name, dimension, category_keywords, description, values}
           dimension=topic → 参与自动匹配（keywords 命中主题）；dimension=style → 仅显式加载
           ★ values 为空 {} 的框架照样注册（占位），但自动匹配自动跳过
           ★ 加载优先级：显式指定(可多个叠加) > 关键词自动匹配 > 通用默认(general)
[被谁调用] memory_advisor_agent、main.py、web_gui/services/task_manager.py、StaticWorkflowDirector
[修改注意] 选择策略（优先级/叠加规则）改这里会同时影响所有注入点与 Agent
"""
import importlib
import os
from pathlib import Path

PROFILE_FOLDER = Path(__file__).parent / "profiles"
MEMORY_FOLDER = Path(__file__).parent / "memories"


class MemoryRegistry:
    def __init__(self):
        self.profiles = {}
        self.load_all_profiles()

    def load_all_profiles(self):
        for py_file in PROFILE_FOLDER.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            module_name = f"memory.profiles.{py_file.stem}"
            mod = importlib.import_module(module_name)
            if hasattr(mod, "PROFILE_META"):
                meta = mod.PROFILE_META
                # 注入文件路径（与资源浏览器 assets 区 path 格式一致，供 GUI 跳转定位）
                meta["file"] = f"memory/profiles/{py_file.name}"
                self.profiles[meta["name"]] = meta
        print(f"✅ 记忆注册器加载 {len(self.profiles)} 个价值观框架: {list(self.profiles.keys())}")

    def get_profile_list(self):
        """返回框架清单（GUI 下拉 / 展示用）"""
        return [{
            "name": v["name"],
            "dimension": v.get("dimension", "topic"),
            "desc": v.get("description", ""),
            "has_values": bool(v.get("values")),
            "file": v.get("file"),
        } for v in self.profiles.values()]

    def get_profile(self, name: str):
        return self.profiles.get(name)

    def match_by_keywords(self, topic: str):
        """关键词自动匹配：只匹配有内容、dimension=topic 的框架；无命中返回 None"""
        topic = str(topic or "")
        best = None
        for meta in self.profiles.values():
            if meta.get("dimension", "topic") != "topic":
                continue
            if not meta.get("values"):
                continue  # 空框架不参与自动匹配（占位用）
            keywords = meta.get("category_keywords") or []
            if any(k and k in topic for k in keywords):
                if best is None or len(keywords) > len(best.get("category_keywords") or []):
                    best = meta  # 关键词越多越具体，优先
        return best


memory_registry = MemoryRegistry()


def select_profiles(topic: str, explicit=None):
    """
    按优先级选择价值观框架（可叠加多个）：
    1. 显式指定（profiles 参数，多个=叠加，如 [topic框架, style框架]）
    2. 关键词自动匹配（topic 维度）
    3. 通用默认（general，保证任何任务都有价值观可循）
    """
    profiles = []
    if explicit:
        names = [str(n).strip() for n in explicit if str(n).strip()]
        for n in names:
            meta = memory_registry.get_profile(n)
            if meta:
                profiles.append(meta)
    if not profiles:
        matched = memory_registry.match_by_keywords(topic)
        if matched:
            profiles.append(matched)
    if not profiles:
        general = memory_registry.get_profile("general")
        if general:
            profiles.append(general)
    return profiles


def read_user_prefs() -> str:
    """读取长期记忆：用户偏好（不存在返回空串）"""
    path = MEMORY_FOLDER / "user_prefs.md"
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return ""
    return ""


def inject_value_profiles(init_state: dict, explicit_profiles=None) -> dict:
    """任务启动注入钩子：把选中的价值观 + 用户偏好写入 init_state['value_profiles']"""
    profiles = select_profiles(init_state.get("topic", ""), explicit_profiles)
    prefs = read_user_prefs()
    if prefs:
        profiles = [*profiles, {"name": "user_prefs", "dimension": "memory",
                                "description": "用户长期偏好", "values": {"user_prefs": prefs}}]
    init_state["value_profiles"] = profiles
    return init_state


def format_values_for(profiles, dims) -> str:
    """按维度标签格式化价值观文本（供 Agent 注入 prompt）：
    只取本 Agent 声明消费的维度，未声明维度自动忽略"""
    if not profiles or not dims:
        return ""
    lines = []
    for p in profiles:
        values = p.get("values") or {}
        parts = [f"{d}:{values[d]}" for d in dims if values.get(d)]
        if parts:
            lines.append(f"- {p.get('name', '')}：{'；'.join(parts)}")
    return "\n".join(lines)


# 任务历史沉淀上限（保留最近记录条数，防止无限膨胀）
TASK_HISTORY_MAX_LINES = 500


def sediment_task_memory(state: dict, meta: dict = None) -> str:
    """
    任务完成时沉淀一行结构化记录到 task_history.md（长期记忆池）。
    【刻意设计】纯程序拼接 state 元数据，**不调 LLM**：零额度消耗、零卡死风险、不随
    任务完成引入新的模型依赖；只沉淀、不自动注入（防 prompt 膨胀），后续如需"经验摘要"
    再以独立精简注入实现。
    :param state: 任务最终状态（topic/domain/value_profiles/final_article 等）
    :param meta: 附加元信息（engine/mode/flow_name），来自编排层（可空）
    :return: 写入的行文本（失败返回空串，不阻断任务）
    """
    from datetime import datetime
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        topic = str(state.get("topic") or "")[:40] or "-"
        domain = state.get("domain") or "general"
        profiles = ",".join(
            p.get("name", "") for p in (state.get("value_profiles") or [])
            if p.get("name") and p.get("name") != "user_prefs"
        ) or "auto"
        article = "是" if state.get("final_article") else "否"
        meta = meta or {}
        line = (f"- {now} 主题：{topic} | 域：{domain} | 价值观：{profiles} "
                f"| 引擎：{meta.get('engine', '')} | 流程：{meta.get('flow_name', '')} | 成稿：{article}")
        path = MEMORY_FOLDER / "task_history.md"
        lines = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
        lines.append(line)
        if len(lines) > TASK_HISTORY_MAX_LINES:
            lines = lines[-TASK_HISTORY_MAX_LINES:]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return line
    except Exception:
        return ""
