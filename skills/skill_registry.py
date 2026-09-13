"""
[模块] skills/skill_registry.py — Skill 自动注册器（Agent / 动态导演 / 静态导演共用）
[职责] 扫描 skills/*.py 的 SKILL_META，提供给 Agent 调用的标准工具注册表
[设计思想] Skill = 写给 LLM/Agent 的标准工具：SKILL_META.description 即给 LLM 看的
           使用说明（功能+参数+返回值），保证工具与业务解耦、可被自动选用
[关键约定] 文件名以 _ 开头被忽略；SKILL_META 必含 name/description/run；
           Agent 调用方式：skill_registry.get_run_func("skill_name")(参数)；
           【与 tools/ 区别】skills/=LLM 可调用的注册工具；tools/=程序内部功能（不进 LLM 工具清单）
[被谁调用] 各 Agent（如 researcher→read_topic_summary、archivist→write_local_database）
[修改注意] 新增 Skill 复制现有文件模式；description 必须写清楚参数与返回值（LLM 靠它决定怎么调）
"""
import importlib
from pathlib import Path

SKILL_FOLDER = Path(__file__).parent


class SkillRegistry:
    def __init__(self):
        self.skills = {}
        self.load_all_skills()

    def load_all_skills(self):
        for py_file in SKILL_FOLDER.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            module_name = f"skills.{py_file.stem}"
            mod = importlib.import_module(module_name)
            if hasattr(mod, "SKILL_META"):
                meta = mod.SKILL_META
                # 注入文件路径（与资源浏览器 assets 区 path 格式一致，供 GUI 跳转定位）
                meta["file"] = f"skills/{py_file.name}"
                self.skills[meta["name"]] = meta
        print(f"✅ Skill注册器加载 {len(self.skills)} 个Skill: {list(self.skills.keys())}")

    def get_skill_list(self):
        """返回给 LLM 看的 skill 清单（名称 + 说明 + 文件路径）"""
        return [{"name": v["name"], "desc": v["description"], "file": v.get("file")} for v in self.skills.values()]

    def get_run_func(self, skill_name: str):
        return self.skills[skill_name]["run"]


# 模块级单例：全项目共用同一份注册结果
skill_registry = SkillRegistry()
