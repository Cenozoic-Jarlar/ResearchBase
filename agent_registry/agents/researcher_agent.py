"""
[模块] agent_registry/agents/researcher_agent.py — Agent：调研员
[职责] 按主题检索本地资料库并整理结构化研究素材：概览选主题 → 摘要（短文件含全文）→ 按需读全文
[设计思想] token 分级读取：list_topics(概览) → LLM 选相关主题 → read_topic_summary(摘要+短全文)
           → 仅当 LLM 判定需要时才 read_topic_file(全文)，避免无关资料占用 token；
           写入时已由 write 端维护 AI 摘要，读取零重复提炼
[关键约定] 写入字段 research_material；模型档位=resolve_tier(state)（任务指定 > 难度映射：
           simple→router 档、complex→standard 档）；【故意不声明 AGENT_META.tier——
           调研档位需跟随任务难度：simple 任务用 router 档省 token，complex 才升 standard】；
           simple 模式只做"选主题+摘要整理"两步（不读全文），减少调用轮次；
           遵循 value_profiles 的 evidence 维度（调研侧重）
[依赖] llm_config（get_llm/resolve_tier）、skills（list_topics/read_topic_summary/read_topic_file）
[被谁调用] 动态/静态流程的调研环节
[修改注意] 三级读取顺序与 JSON 输出契约（{"material","need_full"}）改动需同步 prompt 与解析
"""
import json
import re

from state_model import State
from llm_config import get_llm, resolve_tier
from skills.skill_registry import skill_registry
from memory.memory_registry import format_values_for

# 本角色消费的价值观维度
VP_DIMS = ["evidence"]


def run(state: State) -> dict:
    topic = state["topic"]
    task_level = state.get("task_level", "complex")
    # 主题域：任务创建时注入 state；读取顺序 = 域内库 + 通用层（list_topics 合并）
    domain = state.get("domain")
    # 模型档位：任务指定(model_tier) > 难度映射（simple→router，complex→standard）> standard 默认
    llm = get_llm(resolve_tier(state))
    values_text = format_values_for(state.get("value_profiles"), VP_DIMS)
    values_block = f"【本次任务价值观框架（证据要求）】\n{values_text}\n" if values_text else ""

    # ---- 第1步：主题库概览（低 token，域内+通用合并） ----
    overview = skill_registry.get_run_func("list_topics")(domain)

    # ---- 第2步：LLM 判断相关主题库 ----
    sel_prompt = f"""
你是研究调研员。请先根据主题库概览判断：哪些主题库与当前研究主题相关。
当前研究主题：{topic}
主题库概览：
{overview}
只输出JSON数组，列出相关主题库的【目录名】（如不存在相关主题库则输出空数组 []）。不要多余文字。
"""
    resp = llm.invoke(sel_prompt)
    topics = _parse_json_list(resp.content)

    # ---- 第3步：读取相关主题摘要（短文件自动含全文；域内优先、通用兜底） ----
    summary_parts = []
    for t in topics:
        text = skill_registry.get_run_func("read_topic_summary")(t, domain)
        summary_parts.append(text)
    summary_text = "\n\n".join(summary_parts) if summary_parts else "（没有相关主题库资料）"

    # ---- 第4步：LLM 基于摘要整理素材；complex 模式可声明需全文文件 ----
    need_full_instruction = (
        "如需阅读某文件全文，在 need_full 数组中列出，格式为\"主题库目录名::文件名\"（无需则输出空数组）。"
        if task_level == "complex" else
        "直接基于以上资料整理素材，不要申请全文。"
    )
    material_prompt = f"""
你是研究调研员。
研究主题：{topic}
{values_block}本地资料库参考资料（摘要+短文件全文）：
{summary_text}
任务：基于以上资料，整理结构化研究素材，提炼关键观点、事实，为后续写文章做准备。
整理时遵循上述证据要求。
输出JSON：{{"material": "整理后的素材正文", "need_full": []}}
{need_full_instruction}
只输出JSON，不要多余文字。
"""
    resp2 = llm.invoke(material_prompt)
    parsed = _parse_json_object(resp2.content)
    material = parsed.get("material", "")
    need_full = parsed.get("need_full", []) if isinstance(parsed, dict) else []
    if not material:
        material = str(getattr(resp2, "content", resp2))

    # ---- 第5步：按需读取全文并整合（仅 complex） ----
    if need_full and task_level == "complex":
        full_parts = []
        for item in need_full:
            if "::" not in str(item):
                continue
            t, fname = str(item).split("::", 1)
            full_parts.append(f"【{t}/{fname} 全文】\n" + skill_registry.get_run_func("read_topic_file")(t.strip(), fname.strip(), domain))
        if full_parts:
            final_prompt = f"""
你是研究调研员。以下是基于摘要整理的素材初稿，以及补充的文件全文。
研究主题：{topic}
【素材初稿】
{material}
【补充全文】
{chr(10).join(full_parts)}
任务：把补充全文中有价值的信息融入素材，输出最终结构化研究素材。
"""
            resp3 = llm.invoke(final_prompt)
            material = str(getattr(resp3, "content", resp3))

    return {"research_material": material}


def _parse_json_list(text) -> list:
    """容错解析 JSON 数组（去 markdown 代码块/杂文本）"""
    text = str(text).strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1).strip()
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end > start:
        text = text[start:end + 1]
    try:
        val = json.loads(text)
        return val if isinstance(val, list) else []
    except Exception:
        return []


def _parse_json_object(text) -> dict:
    """容错解析 JSON 对象"""
    text = str(text).strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        text = text[start:end + 1]
    try:
        val = json.loads(text)
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


AGENT_META = {
    "name": "researcher",
    "display_name": "调研员",
    "description": "调研角色，按主题检索本地资料库（概览→摘要→按需全文），整理主题相关研究素材，根据任务难度自动选用模型",
    "persona": {"name": "小研", "tone": "好奇求知、条理清晰", "tags": ["严谨", "好奇"]},
    "consumes": ["evidence"],
    "run": run
}
