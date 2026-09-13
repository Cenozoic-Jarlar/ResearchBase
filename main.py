"""
[模块] main.py — 命令行主入口
[职责] 交互式运行三模式任务：动态全自动 / 动态人审 / 静态工作流，完成后展示并保存文章
[设计思想] 仅做编排（收集主题→选模式→调度→展示结果），不承载业务逻辑；
           三种模式分别委托 DynamicPlanner（纯 Python 动态编排）与
           StaticWorkflowDirector（LangGraph 固定拓扑），体现"核心逻辑与入口解耦"
[关键约定] 静态模式执行到 human_review 的 interrupt 断点后，此处用 input() 恢复；
           结果保存走 tools.document_output（tools/=程序内部功能，非 LLM Skill）；
           任务完成后走 tools.archive_process 封存研究过程档案（archives/，结构化过程资产）；
           主题域（domain）：命令行询问或环境变量 DOMAIN 指定，回车=通用层（默认）
[被谁调用] 直接运行：venv\\Scripts\\python.exe main.py
[修改注意] 新增运行模式在此注册即可；不要在此写 Agent 业务逻辑
"""
import os

from langgraph.types import Command

from agent_registry.registry import registry
from skills.skill_registry import skill_registry
from planner.flow_registry import flow_registry
from planner.dynamic_planner import DynamicPlanner
from planner.static_workflow_director import StaticWorkflowDirector
from tools.document_output import save_article, print_article
from tools.archive_process import archive_research
from memory.memory_registry import inject_value_profiles
from core.domain_config import default_profiles_for


def make_init_state(topic: str, profiles=None, domain: str = None, model_tier: str = None) -> dict:
    """构造初始状态并注入价值观框架。
    优先级：显式 profiles > 域默认（_domain.md）> 关键词自动匹配 > general 兜底；
    domain=主题域（None=通用层），写入 state 供全程 Agent/Skill 读取（域是任务参数，非全局变量）；
    model_tier=模型档位（router/standard/reasoning，空=按难度自动映射，见 llm_config.TIER_MAP）；
    profiles 同时写入 state["profiles"]（显式指定来源，供 memory_advisor 等后续选择逻辑读取，防覆盖）"""
    state = {
        "topic": topic,
        "task_level": None,
        "research_material": None,
        "human_supplement": None,
        "final_article": None,
        "domain": domain,
        "model_tier": (model_tier or "").strip() or None,
        "profiles": list(profiles or []),  # 显式框架名清单（空=自动匹配；写入 state 防后续覆盖）
    }
    if not profiles:
        profiles = default_profiles_for(domain)  # 域默认价值观（未显式选择时生效）
    return inject_value_profiles(state, profiles)


def show_result(final_state: dict, topic: str, domain: str = None):
    """打印最终文章，并保存到输出目录（按主题域落盘，None=通用层 output/）"""
    article = (final_state or {}).get("final_article", "")
    if not article:
        print("（未生成 final_article，请检查执行过程）")
        return

    print_article(article, topic)
    fpath = save_article(article, topic, domain=domain)
    print(f"\n✅ 结果已保存：{fpath}")
    print(f"💡 如需 Word 版：python md2docx.py {fpath}")


def run_dynamic(topic: str, mode: str, domain: str = None, profiles: list = None, model_tier: str = None):
    init_state = make_init_state(topic, profiles=profiles, domain=domain, model_tier=model_tier)
    if mode == "1":
        print("\n" + "=" * 30 + " 动态规划-全自动 " + "=" * 30)
        final_state = DynamicPlanner.auto_run(topic, init_state)
    else:
        print("\n" + "=" * 30 + " 动态规划-人审计划 " + "=" * 30)
        final_state = DynamicPlanner.human_review_plan_run(topic, init_state)
    print("\n✅ 任务完成，最终状态字段：", list(final_state.keys()))
    return final_state


def run_static(topic: str, domain: str = None, profiles: list = None, model_tier: str = None):
    print("\n" + "=" * 30 + " 静态工作流（LangGraph） " + "=" * 30)
    graph, config = StaticWorkflowDirector.run_workflow(topic, init_state=make_init_state(topic, profiles=profiles, domain=domain, model_tier=model_tier))
    # 执行到 interrupt 断点，恢复执行
    user_input = input("\n⏸ 流程暂停于人工审阅，请输入补充信息/修改意见（无补充输入【无】）：").strip()
    final_state = StaticWorkflowDirector.resume_workflow(graph, config, user_input)
    print("\n✅ 任务完成，最终状态字段：", list(final_state.keys()))
    return final_state


def print_usage_summary():
    """打印本次任务的 LLM 用量统计（对话轮次/上传下载 tokens/费用估算，按模型分桶计价）并写简单日志"""
    from llm_config import get_llm_stats, estimate_cost, cost_by_model
    stats = get_llm_stats()
    calls = stats.get("calls", 0)
    if not calls:
        return
    cost = estimate_cost(stats)
    summary = (f"对话轮次 {calls} 次 · 上传 {stats['input_tokens']} tokens · "
               f"下载 {stats['output_tokens']} tokens · 费用估算 ¥{cost:.4f}")
    detail = "；".join(f"{m} ¥{c:.4f}" for m, c in cost_by_model(stats).items())
    if detail:
        summary += f"（按模型：{detail}）"
    print(f"\n📊 任务用量统计：{summary}")
    from core.logger import get_logger
    get_logger().info(f"任务统计: {summary}")


def main():
    print("=" * 50)
    print(" ResearchBase（研库）多Agent研究系统")
    print("=" * 50)
    print(f"已注册Agent: {[a['name'] for a in registry.get_agent_list()]}")
    print(f"已注册Skill: {[s['name'] for s in skill_registry.get_skill_list()]}")
    print(f"已注册静态流程: {[f['name'] for f in flow_registry.get_flow_list()]}")

    topic = input("\n请输入研究主题：").strip()
    if not topic:
        print("主题不能为空，退出。")
        return

    # 主题域：回车=通用层（默认，跨域共享）；也可用环境变量 DOMAIN 预设（非交互场景）
    from core.paths import list_domains
    domain = (os.getenv("DOMAIN") or input("\n主题域（回车=通用层；现有域：" + ("、".join(list_domains()) or "无") + "）：").strip() or None)
    if domain:
        print(f"📁 本次任务使用主题域：{domain}（资料/输出/档案写入 domains/{domain}/）")

    # 显式价值观框架：环境变量 PROFILES（逗号分隔，如 "cute_style,policy"；空=自动匹配/域默认）
    profiles = [p.strip() for p in os.getenv("PROFILES", "").split(",") if p.strip()] or None
    if profiles:
        print(f"🎭 显式价值观框架：{'、'.join(profiles)}")

    # 模型档位：环境变量 MODEL_TIER（router/standard/reasoning；空=按难度自动映射，见 manual_settings.py 人工全局设置）
    model_tier = (os.getenv("MODEL_TIER") or "").strip() or None
    if model_tier:
        print(f"🤖 模型档位：{model_tier}（留空=按难度自动映射）")

    print("\n选择运行模式：")
    print("  1. 动态规划-全自动")
    print("  2. 动态规划-人审计划（修改意见返回LLM重新生成）")
    print("  3. 静态工作流（LangGraph，人工断点补充）")
    choice = input("输入 1/2/3：").strip()

    final_state = None
    meta = {"engine": "dynamic", "mode": "auto", "domain": domain or None, "model_tier": model_tier}
    if choice in ("1", "2"):
        meta["mode"] = "auto" if choice == "1" else "human_review"
        final_state = run_dynamic(topic, choice, domain, profiles, model_tier)
    else:
        meta = {"engine": "static", "mode": "static", "flow_name": "article_generation", "domain": domain or None, "model_tier": model_tier}
        final_state = run_static(topic, domain, profiles, model_tier)

    # 展示并保存最终文章（按域落盘）
    show_result(final_state, topic, domain)

    # 封存研究过程档案（结构化过程资产，供追溯/复用；按域落盘）
    archive_path = archive_research(final_state, meta, domain=domain)
    if archive_path:
        print(f"📦 研究过程已封存：{archive_path}")

    # 沉淀长期记忆（结构化一行记录，纯拼接不调 LLM）
    from memory.memory_registry import sediment_task_memory
    line = sediment_task_memory(final_state, meta)
    if line:
        print("🧠 长期记忆已沉淀一条任务记录")

    # 用量统计汇总（轮次/tokens/费用估算）→ 终端 + 简单日志
    print_usage_summary()


if __name__ == "__main__":
    from llm_config import reset_llm_stats
    reset_llm_stats()  # 任务开始前重置用量统计（CLI 单线程）
    main()
