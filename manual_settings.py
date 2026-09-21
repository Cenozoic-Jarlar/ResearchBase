"""
[模块] manual_settings.py — 人工/ AI 全局设置（模型注册表 + 运行参数）
[职责] 集中管理全局设置：模型注册表（档位→模型/提供商/价格）+ 运行参数（超时/日志/价格兜底）
[设计思想] 配置分层：本文件=可版本化的设置（进 git，带注释，**人工和 AI 都可维护**：
           改模型、加提供商、调价格、修格式错误都直接改这里，改完重启生效）；
           .env=纯密钥（不进 git，机器级）；core/paths.py=代码规范常量（不动）；
           运行时读取规则=环境变量优先（os.getenv 第一参数），本文件值只作默认/兜底
[关键约定] ★ 唯一不可破边界=**密钥只放 .env**：本文件 api_key 一律写
             os.getenv("LLM_xxx", "占位符") 形式（声明「从哪个环境变量取 + 默认占位符」），
             禁止在文件里写真实密钥（防止入 git 泄漏）；模型档位名（MODELS 的 key）是全局契约：
             AGENT_META.tier / GUI 下拉 / resolve_tier 都按它工作，新增档位=加一个 key（GUI 自动出现）
[被谁调用] llm_config.py（模型注册表+超时/重试/价格）、core/logger.py（详细日志开关）
[修改注意] 改动模型档位名需同步 AGENTS.md §6 与 Agent 的 tier 声明；
           AI 自动维护时：可改模型/价格/新增档位/修复格式，但密钥只允许引用 .env，不得写入本文件
"""
import os
from dotenv import load_dotenv

# 先加载 .env（幂等）：让下方 os.getenv 能读到密钥；重复 import 安全
load_dotenv()

# =====================================================================
# 一、模型注册表（档位 → 模型）
# ---------------------------------------------------------------------
# 字段说明：
#   model           API 模型名（也是费用分桶键，改模型=改这一行）
#   base_url        API 地址；非秘密可写死，也可 os.getenv 引用（.env 覆盖）
#   api_key         ★ 一律 os.getenv("LLM_<档位大写>_API_KEY", "占位符")
#                   ——真实密钥放 .env（LLM_API_KEY=全局兜底；档位专属=LLM_<档位>_API_KEY）
#   role            用途说明（GUI 档位下拉展示）
#   capabilities    模型能力标签（text/vision/long_context；搜索/读库是 Skill 能力，不写这里）
#   input/output_price  元/百万 tokens（按你的渠道合同价填）
# =====================================================================

MODELS = {
    # ── 档位1 router：硅基流动（便宜快，路由判断/简单问答）──
    "router": {
        "model": "deepseek-ai/DeepSeek-V4-Flash",
        "base_url": os.getenv("LLM_BASE_URL", "https://api.siliconflow.cn/v1"),
        "api_key": os.getenv("LLM_API_KEY", "sk-请填入你的硅基流动APIKey"),
        "role": "路由判断/简单问答，便宜快",
        "capabilities": ["text"],
        "input_price": 2,
        "output_price": 8,
    },
    # ── 档位2 standard：硅基流动（日常调研/写作/审阅主体）──
    "standard": {
        "model": "deepseek-ai/DeepSeek-V4-Pro",
        "base_url": os.getenv("LLM_BASE_URL", "https://api.siliconflow.cn/v1"),
        "api_key": os.getenv("LLM_API_KEY", "sk-请填入你的硅基流动APIKey"),
        "role": "日常调研/写作/审阅主模型",
        "capabilities": ["text", "long_context"],
        "input_price": 9,
        "output_price": 27,
    },
    # ── 档位3 reasoning：DeepSeek 官方（复杂推理，仅人工指定）──
    #    真实 key 放 .env：LLM_REASONING_API_KEY=sk-xxx（platform.deepseek.com 申请）
    "reasoning": {
        "model": "deepseek-reasoner",
        "base_url": os.getenv("LLM_REASONING_BASE_URL", "https://api.deepseek.com/v1"),
        "api_key": os.getenv("LLM_REASONING_API_KEY", "sk-请填入你的DeepSeek官方APIKey"),
        "role": "复杂推理/深度分析（人工指定）",
        "capabilities": ["text", "long_context"],
        "input_price": 9,
        "output_price": 27,
    },
    # ── 其他提供商示例（取消注释即可启用；key 放 .env 对应变量）──
    # "standard": {
    #     "model": "gpt-4o-mini",
    #     "base_url": os.getenv("LLM_OPENAI_BASE_URL", "https://api.openai.com/v1"),
    #     "api_key": os.getenv("LLM_OPENAI_API_KEY", "sk-请填入你的OpenAIAPIKey"),
    #     "role": "日常主模型（OpenAI）",
    #     "capabilities": ["text"],
    #     "input_price": 1.1,
    #     "output_price": 4.3,
    # },
}

# =====================================================================
# 二、运行参数（环境变量优先，此处为默认值）
# =====================================================================
LLM_TIMEOUT = 90              # 单次 LLM 调用超时（秒）；GUI 任务表单可临时覆盖
LLM_MAX_RETRIES = 1           # 调用失败重试次数
DETAIL_LOG_ENABLED = True     # 详细日志开关（false=完全静默不落盘；简单日志不受影响）
PRICE_INPUT_PER_M = 2.0       # 全局默认单价（元/百万 tokens）：未在 MODELS 标价的模型兜底用
PRICE_OUTPUT_PER_M = 8.0
LOG_RETENTION_DAYS = 30       # 日志自动清理：启动时删除 logs/ 下超过 N 天的 run_*.log / detail_run_*.log；设 0=不清理
