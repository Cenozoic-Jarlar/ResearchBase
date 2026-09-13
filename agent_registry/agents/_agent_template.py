"""
[模块] agent_registry/agents/_agent_template.py — Agent 标准模板（复制即用）
[职责] 定义新 Agent 的最小骨架：run(state)->dict + AGENT_META
[设计思想] 插件式注册：文件放入 agent_registry/agents/ 即被 registry 自动加载，
           无需修改任何调度器；AGENT_META.description 是给"规划导演 LLM"看的，
           决定该角色何时被动态规划选用——描述质量直接影响编排效果；
           AGENT_META.tier 是 Agent↔模型档位的对应关系（写在属性里），
           新建 Agent 必须指定，注册器加载时会校验
[关键约定] ★ AGENT_META 的 key 名不可改（注册器按名读取）；
           name 唯一（小写下划线）；可选 engines 限定适用引擎（不写=全部）；
           ★ tier 必填（"router"/"standard"/"reasoning" 三选一）；
             若确实想跟随任务难度映射（simple→router、complex→standard），
             可写 "" 或不写，但必须注释说明原因（仅调研/轻量角色适用）
[被谁调用] 仅作模板，文件名以 _ 开头不会注册
[修改注意] 新建 Agent 时：改 run 逻辑 + AGENT_META（含 tier）+ 文件头注释；放入目录即生效
"""
from state_model import State
from llm_config import get_llm, resolve_tier

def run(state: State) -> dict:
    """
    角色执行入口
    :param state: 全局共享状态
    :return dict: 需要合并更新到state的键值对，不需要更新的字段不用返回
    """
    # ========== 在这里写你的角色业务逻辑 ==========
    # 读取state里需要的数据
    topic = state["topic"]

    # 做任务、调用LLM / 工具（必须经 get_llm，保持日志与统计）
    # 档位决策：任务指定 > 本 Agent 声明 tier > 难度映射 > standard 默认
    llm = get_llm(resolve_tier(state, AGENT_META.get("tier")))
    result_text = f"模板角色处理主题：{topic}"

    # 返回要写入state的数据
    return {
        "some_output_field": result_text
    }
    # ==============================================

# 角色元数据（注册器自动读取！！不要修改key名称）
AGENT_META = {
    "name": "template_agent",       # 唯一英文名称，小写下划线，不能重复
    "display_name": "模板角色",      # 中文显示名，便于阅读
    "description": "【角色简介】给规划导演看，用来判断什么时候调用这个角色",
    "tier": "standard",             # ★ 必填：模型档位 router/standard/reasoning（见文件头注释）
    "run": run,
    # "engines": ["dynamic", "static"]  # 可选：限定适用引擎；不写默认全部引擎可用
}
