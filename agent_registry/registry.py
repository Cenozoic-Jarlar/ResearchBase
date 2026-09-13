"""
[模块] agent_registry/registry.py — Agent 自动注册器（两类调度器共用）
[职责] 扫描 agent_registry/agents/*.py，加载每个文件里的 AGENT_META，实现插件式注册
[设计思想] 新增 Agent = 复制模板放入目录即自动注册，无需修改任何调度器代码；
           引擎过滤（get_agent_list(engine=...)）让动态规划只看到动态可用的角色
[关键约定] 文件名以 _ 开头被忽略；AGENT_META 必含 name/description/run；
           可选 engines=["dynamic","static"] 限定引擎，未定义=全部可用
[被谁调用] planner/dynamic_planner.py、main.py、web_gui/app.py、StaticWorkflowDirector
[修改注意] 不要在此硬编码 Agent 列表；改引擎过滤逻辑会同时影响动态规划与 GUI 清单
"""
import importlib
from pathlib import Path

AGENT_FOLDER = Path(__file__).parent / "agents"


class AgentRegistry:
    def __init__(self):
        self.agents = {}
        self.load_all_agents()

    def load_all_agents(self):
        for py_file in AGENT_FOLDER.glob("*.py"):
            fname = py_file.name
            if fname.startswith("_"):
                continue
            module_name = f"agent_registry.agents.{py_file.stem}"
            mod = importlib.import_module(module_name)
            if hasattr(mod, "AGENT_META"):
                meta = mod.AGENT_META
                # 注入文件路径（相对项目根，与资源浏览器 assets 区 path 格式一致，供 GUI 跳转定位）
                meta["file"] = f"agent_registry/agents/{py_file.name}"
                # tier 校验：仅对实际使用模型的 Agent 检查档位声明（模板强制；缺失=warning 提醒）
                # 纯规则/人工 Agent（不 import get_llm，如 human_review/memory_advisor）无需档位
                import inspect as _inspect
                uses_llm = "get_llm" in _inspect.getsource(mod)
                if uses_llm and not (meta.get("tier") or "").strip():
                    print(f"⚠️ Agent「{meta['name']}」未声明 AGENT_META.tier（模型档位），"
                          f"将按任务难度映射取模型；建议参照 _agent_template.py 补声明")
                self.agents[meta["name"]] = meta
        print(f"✅ 注册器加载 {len(self.agents)} 个Agent: {list(self.agents.keys())}")

    def get_agent_list(self, engine: str = None):
        """
        返回 Agent 清单（供 LLM 规划/人查看）。
        :param engine: 按适用引擎过滤，None=全部；"dynamic"=仅动态引擎可用；"static"=仅静态工作流可用。
                       Agent 元信息里可定义 "engines": ["dynamic", "static"]；未定义则默认全部引擎可用。
        """
        result = []
        for v in self.agents.values():
            engines = v.get("engines")
            if engine is None or engines is None or engine in engines:
                result.append({"name": v["name"], "desc": v["description"], "file": v.get("file"),
                               "tier": v.get("tier") or ""})
        return result

    def get_run_func(self, agent_name: str):
        return self.agents[agent_name]["run"]


registry = AgentRegistry()
