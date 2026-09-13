"""
[模块] agent_registry/agents/archivist_agent.py — Agent：归档员
[职责] 把研究成稿提炼为「要点摘要」写入本地资料库（write_local_database Skill），沉淀可复用知识
[设计思想] 资料库=研究输入素材 + 可复用知识片段，**不放成稿全文**（全文归 output/ 与 archives/，
           避免 researcher 调研时把历史成稿误当参考资料读入、污染调研素材）；
           归档员只决定"写什么、写到哪个主题库"，摘要由 LLM 提炼（失败降级截取原文开头），
           写端（write_local_database）自动编号、维护索引
[关键约定] 主题库名=研究主题（自动编号，多次研究同主题复用同一库）；
           文件名=清洗后的主题短语+"-研究要点"（write 自动补 NN- 编号）；
           入库内容=结构化要点摘要（主题/核心结论/章节结构/关键发现），非全文；
           写入字段 archive_result；无 final_article 时返回提示不报错
[依赖] llm_config（get_llm/resolve_tier，run 取档位传入 _make_summary）、skills.write_local_database、
       tools.document_output.sanitize_filename
[被谁调用] knowledge_archiving 流程（writer 之后）；动态规划按需选用
[修改注意] 归档策略（全文 vs 摘要）改动只在本 Agent；摘要提炼失败必须降级，不得阻断流程
"""
from datetime import datetime

from state_model import State
from llm_config import get_llm, resolve_tier
from skills.skill_registry import skill_registry
from tools.document_output import sanitize_filename

# 提炼摘要时喂给 LLM 的成稿长度上限（字符；超长截断省 token，摘要质量足够）
SUMMARY_ARTICLE_LIMIT = 6000
# 提炼失败时的降级截取长度
SUMMARY_FALLBACK_LEN = 600


def _make_summary(topic: str, article: str, llm) -> str:
    """LLM 提炼研究要点摘要（结构化）；异常/无输出时降级为截取原文开头（不阻断流程）"""
    prompt = f"""你是研究归档助手。请把以下研究成稿提炼为「研究要点摘要」，用于入库沉淀。
要求（输出 Markdown，500 字以内，不要多余解释）：
- 研究主题：{topic}
- 核心结论（2-4 条要点）
- 章节结构（仅标题列表）
- 关键发现/要点（列表）

研究成稿：
{article[:SUMMARY_ARTICLE_LIMIT]}
"""
    try:
        resp = llm.invoke(prompt)
        text = str(getattr(resp, "content", "")).strip()
        if text:
            return text
    except Exception:
        pass
    cut = article[:SUMMARY_FALLBACK_LEN]
    suffix = "\n\n（摘要提炼失败，已截取原文开头）" if len(article) > SUMMARY_FALLBACK_LEN else ""
    return cut + suffix


def run(state: State) -> dict:
    topic = state["topic"]
    article = state.get("final_article", "")
    if not article:
        return {"archive_result": "无最终文章可归档"}

    llm = get_llm(resolve_tier(state, AGENT_META.get("tier")))  # 档位：任务指定 > 难度映射 > standard 默认
    summary = _make_summary(topic, article, llm)
    filename = f"{sanitize_filename(topic, 20)}-研究要点"
    content = f"研究主题：{topic}\n生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n{summary}"
    result = skill_registry.get_run_func("write_local_database")(
        filename=filename,
        content=content,
        topic=topic,
        mode="overwrite",
        summary=summary[:50],  # 索引摘要直接用要点开头，省一次 AI 提炼
        domain=state.get("domain"),
    )
    return {"archive_result": result}


AGENT_META = {
    "name": "archivist",
    "display_name": "归档员",
    "description": "归档角色：把研究成稿提炼为要点摘要写入本地资料库沉淀知识（全文不入库，防污染调研素材），适合需要保存研究产物的流程",
    "persona": {"name": "典藏", "tone": "细致整洁", "tags": ["可靠", "条理"]},
    "consumes": [],
    "tier": "router",  # 固定档位（任务级指定可覆盖）
    "run": run
}
