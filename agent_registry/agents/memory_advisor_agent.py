"""
[模块] agent_registry/agents/memory_advisor_agent.py — Agent：记忆顾问
[职责] 按主题/显式指定选择价值观框架 + 加载长期记忆（用户偏好），注入 state["value_profiles"]
[设计思想] 价值观注入点：任务启动时自动执行（main.py / task_manager / StaticWorkflowDirector 的
           init_state 钩子），也可被动态规划选用（如用户要求"按XX风格分析"时）；
           选择逻辑全部在 memory/memory_registry.select_profiles，本 Agent 只做协议包装；
           【防覆盖】若 state["value_profiles"] 已存在非 user_prefs 框架（启动钩子已注入），
           直接保留不重新选择——否则动态计划里的 memory_advisor 会用主题自动匹配覆盖显式指定的风格
[关键约定] 写入字段 value_profiles（list[dict]，供各 Agent 按 consumes 维度消费）；
           显式指定来源：state["profiles"]（GUI 多选 / CLI 环境变量 / 任务参数）
[依赖] memory.memory_registry（select_profiles / read_user_prefs）
[被谁调用] 任务启动注入钩子；动态规划按需选用
[修改注意] 选择优先级改动在 memory_registry.select_profiles；本文件保持薄包装
"""
from state_model import State
from memory.memory_registry import select_profiles, read_user_prefs


def run(state: State) -> dict:
    existing = [p for p in (state.get("value_profiles") or [])
                if isinstance(p, dict) and p.get("name") != "user_prefs"]
    if existing:
        # 启动钩子（或先前步骤）已注入 → 保留，不重新自动匹配（防显式风格被主题匹配覆盖）
        profiles = existing
        note = "已注入价值观框架（保留，不重复选择）：" + "、".join(p.get("name", "") for p in existing)
    else:
        explicit = state.get("profiles")
        profiles = select_profiles(state.get("topic", ""), explicit)
        note = "本次任务价值观框架：" + "、".join(p.get("name", "") for p in profiles)
    prefs = read_user_prefs()
    if prefs and not any(p.get("name") == "user_prefs" for p in profiles):
        profiles = [*profiles, {"name": "user_prefs", "dimension": "memory",
                                "description": "用户长期偏好", "values": {"user_prefs": prefs}}]
    return {"value_profiles": profiles, "advisor_note": note}


AGENT_META = {
    "name": "memory_advisor",
    "display_name": "记忆顾问",
    "description": "记忆与价值观顾问：任务启动时按主题/显式指定加载价值观框架与长期记忆（用户偏好），"
                   "注入 value_profiles 供各角色遵循；适合需要按特定价值观/风格处理任务的场景",
    "persona": {"name": "先知", "tone": "全局视野、周到理性", "tags": ["周到", "理性"]},
    "consumes": [],
    "run": run
}
