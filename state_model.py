"""
[模块] state_model.py — 【全项目唯一】全局统一状态模型
[职责] 定义所有 Agent / 两套引擎共用的 State（TypedDict）
[设计思想] 单一 State + 增量合并：每个 Agent 只读所需字段、只返回要更新的字段，
           由执行器合并——保证职责解耦、无全局污染
[关键约定] total=False：运行期允许 Agent 按任务需要动态新增字段（state 随任务自动更新）；
           【禁止】在别处重复定义 State（曾有 agent_registry/state.py 冗余已删）
[被谁调用] 全部 Agent、动态执行器、静态流程 build()、web_gui/task_manager
[修改注意] 新增固定字段时同步更新：各 Agent 返回、main.py/task_manager 的 make_init_state
"""
from typing import TypedDict, Optional

class State(TypedDict, total=False):
    """
    全局统一状态池（两套引擎、所有 Agent 共用同一份定义）
    - 固定核心字段：任务主题、任务等级、调研素材、人工补充、最终输出
    - 思考/归档/价值观/过程记录字段：静态引擎（LangGraph）**只保留本文件声明的键**，
      未声明的键会被静默丢弃（本次测试暴露：critical_review 等曾丢失）——新增字段必须在此登记
    - total=False + 普通 dict 合并语义：动态引擎中 state 是普通 dict，新增键无约束；
      静态引擎受 TypedDict 声明约束，两引擎共用时字段声明要齐全
    """
    topic: str
    task_level: Optional[str]
    research_material: Optional[str]
    human_supplement: Optional[str]
    final_article: Optional[str]
    # 主题域（任务级隔离单元）：None/"general"=通用层；具体域名 → domains/<域>/ 私有读写。
    # 由 make_init_state 注入（CLI/GUI 创建任务时选定），全程跟着任务走，禁止用全局变量
    domain: Optional[str]
    # 模型档位（任务级指定）：router/standard/reasoning（空=自动按难度映射，见 llm_config.TIER_MAP）；
    # 由 make_init_state 注入（GUI 下拉/CLI 环境变量 MODEL_TIER），Agent 经 resolve_tier 决策取模型
    model_tier: Optional[str]
    # 事实审核（fact_checker 角色 + 有界修订循环）
    fact_check_issues: Optional[str]
    fact_check_passed: Optional[bool]
    fact_check_count: Optional[int]
    # 思考型角色产出（批判/科学/人文，供 writer 聚合）
    critical_review: Optional[str]
    scientific_analysis: Optional[str]
    humanities_perspective: Optional[str]
    # 归档 / 采集 / 记忆顾问
    archive_result: Optional[str]
    collect_result: Optional[str]
    advisor_note: Optional[str]
    value_profiles: Optional[list]
    # 显式指定的价值观框架名清单（空=自动匹配；make_init_state 写入，供 memory_advisor 等
    # 后续选择逻辑读取——防"启动已注入的框架被再次自动匹配覆盖"）
    profiles: Optional[list]
    # 过程记录（动态引擎写入，供过程封存/任务回放）
    exec_plan: Optional[list]
