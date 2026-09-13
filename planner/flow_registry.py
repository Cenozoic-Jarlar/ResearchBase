"""
[模块] planner/flow_registry.py — 静态流程自动注册器
[职责] 扫描 planner/flows/*.py 的 FLOW_META，实现多静态流程插件式注册
[设计思想] 与 Agent/Skill 注册器同一模式："一个文件一个功能，放入即注册"，
           调度器不感知具体流程，降低扩展成本
[关键约定] 文件名以 _ 开头被忽略；FLOW_META 必含 name/description/build；
           build() 返回已 compile 的 LangGraph 图；模块级单例 flow_registry 全项目共用
[被谁调用] StaticWorkflowDirector、main.py、web_gui/app.py（流程清单）
[修改注意] 新增流程放 planner/flows/，勿改本文件
"""
import importlib
from pathlib import Path

FLOW_FOLDER = Path(__file__).parent / "flows"


class FlowRegistry:
    def __init__(self):
        self.flows = {}
        self.load_all_flows()

    def load_all_flows(self):
        for py_file in FLOW_FOLDER.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            module_name = f"planner.flows.{py_file.stem}"
            mod = importlib.import_module(module_name)
            if hasattr(mod, "FLOW_META"):
                meta = mod.FLOW_META
                # 注入文件路径（与资源浏览器 assets 区 path 格式一致，供 GUI 跳转定位）
                meta["file"] = f"planner/flows/{py_file.name}"
                self.flows[meta["name"]] = meta
        print(f"✅ 流程注册器加载 {len(self.flows)} 个静态流程: {list(self.flows.keys())}")

    def get_flow_list(self):
        return [{"name": v["name"], "desc": v["description"], "file": v.get("file")} for v in self.flows.values()]

    def get_flow(self, flow_name: str):
        if flow_name not in self.flows:
            raise KeyError(f"静态流程不存在：{flow_name}，可选：{list(self.flows.keys())}")
        return self.flows[flow_name]

    def build(self, flow_name: str):
        """按名称构建 LangGraph 图"""
        return self.flows[flow_name]["build"]()


# 模块级单例：全项目共用同一份注册结果
flow_registry = FlowRegistry()
