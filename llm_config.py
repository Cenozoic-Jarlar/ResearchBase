"""
[模块] llm_config.py — 大模型配置与日志包装（模型注册表 + 统一取用 + 按模型计价）
[职责] 模型注册表（档位→模型，配置在 manual_settings.py 人工全局设置）+ 档位决策
       + LoggingLLM 自动记录交互日志 + 任务级用量统计（按模型分桶计价）
[设计思想] 配置分层：manual_settings.py=人工/ AI 全局设置（可版本化，人工与 AI 都可维护）；
           .env=纯密钥（不进 git）；运行读取=环境变量优先（LLM_MODELS 旧 JSON 可临时覆盖/测试用）；
           档位设计：router（路由判断/简单问答，便宜快）/ standard（日常调研/写作/审阅主体）/
           reasoning（复杂推理深度分析，人工指定）——档位=用途，不=难度；
           难度(simple/complex)由 task_router 输出，决定工作深度，经 TIER_MAP 映射到默认档位；
           任务级可人工覆盖（state.model_tier：GUI 下拉/CLI 环境变量/域默认）；
           决策链：人工指定档位 > Agent 声明 tier > 难度映射 > 默认 standard；
           LoggingLLM 是透明包装器：保持 invoke(prompt)→含 .content 的响应对象，调用前后写详细日志，
           所有 Agent 经 get_llm 取用即自动获得审计与统计；
           超时实现=重建底层 client（LLM 无状态，重建零副作用；重建时同步 model_name 防计价分桶错位）；
           token 统计从响应 usage_metadata 真实读取，按模型分桶，费用=Σ(每模型 tokens×该模型单价)
[关键约定] ★ 全项目 LLM 调用必须经 get_llm()（唯一入口），禁止直接 new ChatOpenAI（失去日志与统计）；
           ★ 计价分桶键=API 模型名（model 字段），改模型后需重启或重建（set_timeout 会同步）；
           ★ 用量统计生命周期：reset_llm_stats / set_llm_stats / get_llm_stats；
           ★ 模型档位注册表唯一来源=manual_settings.MODELS（旧格式 LLM_MODELS 仅测试/临时覆盖）
[被谁调用] 全部 Agent、planner/dynamic_planner.py、web_gui/services/task_manager.py（统计+档位）、
           main.py（统计汇总+CLI 档位）、web_gui/app.py（模型列表展示/配置保存后 reset_model_registry）
[修改注意] 新增档位=manual_settings.MODELS 加一个 key + GUI 下拉自动出现；
           改 TIER_MAP 需同步 manual_settings 注释说明；兼容旧格式 LLM_MODELS 仅测试用，勿删解析分支；
           mock 测试 patch 到使用方模块的 get_llm 绑定名（如 agent_registry.agents.writer_agent.get_llm）
"""
import os
import threading
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from core.logger import get_detail_logger
import manual_settings

load_dotenv()

detail_logger = get_detail_logger()

# 超时/重试默认值（manual_settings 默认，环境变量可覆盖；GUI 任务级 timeout 可覆盖）
DEFAULT_TIMEOUT = float(os.getenv("LLM_TIMEOUT", str(manual_settings.LLM_TIMEOUT)))
DEFAULT_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", str(manual_settings.LLM_MAX_RETRIES)))

# ---------- 全局默认单价（元/百万 tokens） ----------
# 按模型单价见 manual_settings.MODELS 每档 input_price/output_price（更精确）；此处仅作未配置模型的回退
PRICE_INPUT_PER_M = float(os.getenv("LLM_PRICE_INPUT", str(manual_settings.PRICE_INPUT_PER_M)))
PRICE_OUTPUT_PER_M = float(os.getenv("LLM_PRICE_OUTPUT", str(manual_settings.PRICE_OUTPUT_PER_M)))

# ---------- 档位映射（难度→默认档位；reasoning 仅人工指定） ----------
# 与 manual_settings 注释中的说明保持一致：simple→router，complex→standard
TIER_MAP = {"simple": "router", "complex": "standard"}
DEFAULT_TIER = "standard"


def _parse_price(value) -> float:
    """解析价格（元/百万 tokens）；空/非法返回 None（计价时回退全局默认）"""
    if value is None or not str(value).strip():
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _load_model_registry() -> dict:
    """构建模型注册表（优先级：环境变量 LLM_MODELS 旧 JSON（测试/临时覆盖）> manual_settings.MODELS（人工全局设置）> 旧式两档）。
    注册表项：{name(档位名), model(API 模型名), role, capabilities, base_url, api_key,
              input_price, output_price}
    - manual_settings 每档字段：model 必填；base_url/api_key 已在人工设置里用 getenv 引用
      （省略则兜底全局 LLM_BASE_URL/LLM_API_KEY）；价格省略→None 计价回退全局默认
    - LLM_MODELS 旧 JSON 兼容格式（仅测试/临时覆盖用）：每项
      {name,model,base_url?,api_key?,role?,capabilities?,input_price?,output_price?}
    """
    # —— 1. 旧格式 LLM_MODELS 单行 JSON（测试/临时覆盖优先；运行时 .env 已不使用）——
    raw = os.getenv("LLM_MODELS")
    if raw and raw.strip():
        try:
            import json
            items = json.loads(raw)
            reg = {}
            for it in items:
                name = it.get("name")
                if not name or not it.get("model"):
                    continue
                reg[name] = {
                    "name": name,
                    "model": it["model"],
                    "role": it.get("role") or "",
                    "capabilities": it.get("capabilities") or [],
                    "base_url": it.get("base_url") or os.getenv("LLM_BASE_URL"),
                    "api_key": it.get("api_key") or os.getenv("LLM_API_KEY"),
                    "input_price": _parse_price(it.get("input_price")),
                    "output_price": _parse_price(it.get("output_price")),
                }
            if reg:
                return reg
        except Exception as e:
            detail_logger.error(f"LLM_MODELS 解析失败（回退 manual_settings）：{e}")
    # —— 2. 人工全局设置 manual_settings.MODELS（唯一运行时来源）——
    reg = {}
    for name, cfg in manual_settings.MODELS.items():
        model = (cfg.get("model") or "").strip()
        if not name or not model:
            continue  # 空档位名/空模型名跳过
        reg[name] = {
            "name": name,
            "model": model,
            "role": cfg.get("role") or "",
            "capabilities": cfg.get("capabilities") or [],
            "base_url": cfg.get("base_url") or os.getenv("LLM_BASE_URL"),
            "api_key": cfg.get("api_key") or os.getenv("LLM_API_KEY"),
            "input_price": _parse_price(cfg.get("input_price")),
            "output_price": _parse_price(cfg.get("output_price")),
        }
    if reg:
        return reg
    # —— 3. 旧式两档（向后兼容）：LLM_MODEL_COMPLEX→standard，LLM_MODEL_SIMPLE→router ——
    return {
        "standard": {"name": "standard", "model": os.getenv("LLM_MODEL_COMPLEX"),
                     "role": "日常任务主模型（旧式 complex 档迁移）", "capabilities": ["text"],
                     "base_url": os.getenv("LLM_BASE_URL"), "api_key": os.getenv("LLM_API_KEY"),
                     "input_price": None, "output_price": None},
        "router": {"name": "router", "model": os.getenv("LLM_MODEL_SIMPLE"),
                   "role": "路由判断/简单问答（旧式 simple 档迁移）", "capabilities": ["text"],
                   "base_url": os.getenv("LLM_BASE_URL"), "api_key": os.getenv("LLM_API_KEY"),
                   "input_price": None, "output_price": None},
    }


MODEL_REGISTRY = _load_model_registry()

# 按 API 模型名索引的价格表 {model: (input_price, output_price)}（元/百万；None=回退全局默认）
MODEL_PRICES = {}
for _cfg in MODEL_REGISTRY.values():
    if _cfg["model"] and (_cfg["input_price"] is not None or _cfg["output_price"] is not None):
        MODEL_PRICES[_cfg["model"]] = (_cfg["input_price"], _cfg["output_price"])


def get_model_price(model_name: str):
    """返回某 API 模型 (input, output) 单价；未配置该模型价格时回退全局默认"""
    if model_name in MODEL_PRICES:
        ip, op = MODEL_PRICES[model_name]
        return (ip if ip is not None else PRICE_INPUT_PER_M,
                op if op is not None else PRICE_OUTPUT_PER_M)
    return PRICE_INPUT_PER_M, PRICE_OUTPUT_PER_M


def list_models() -> list:
    """模型档位列表（供 GUI 下拉/展示）：name + role + capabilities + 价格"""
    out = []
    for cfg in MODEL_REGISTRY.values():
        ip, op = get_model_price(cfg["model"]) if cfg["model"] else (None, None)
        out.append({"name": cfg["name"], "role": cfg["role"],
                    "capabilities": cfg["capabilities"], "model": cfg["model"],
                    "input_price": ip, "output_price": op})
    return out


def resolve_tier(state: dict, agent_tier: str = None) -> str:
    """档位决策：任务指定(model_tier) > Agent 声明档位(agent_tier) > 难度映射(task_level) > 默认 standard；
    非法档位（未注册）静默回退下一步，防止脏值让任务崩溃。
    agent_tier=AGENT_META.tier（Agent 自身固定档位；省略/None=走难度映射——调研类角色适用）"""
    if isinstance(state, dict):
        tier = (state.get("model_tier") or "").strip()
        if tier in MODEL_REGISTRY:
            return tier
    at = (agent_tier or "").strip() if agent_tier else ""
    if at in MODEL_REGISTRY:
        return at
    level = state.get("task_level") if isinstance(state, dict) else None
    if level in TIER_MAP:
        return TIER_MAP[level]
    return DEFAULT_TIER


# ---------- 任务级用量统计（轮次 / tokens / 按模型费用） ----------
_tlocal = threading.local()


def _new_stats() -> dict:
    """新建统计对象：总轮次/总tokens（兼容旧格式）+ by_model 分桶（键=API 模型名）"""
    return {"calls": 0, "input_tokens": 0, "output_tokens": 0, "by_model": {}}


def _current_stats() -> dict:
    stats = getattr(_tlocal, "llm_stats", None)
    if stats is None:
        stats = _new_stats()
        _tlocal.llm_stats = stats
    return stats


def reset_llm_stats() -> dict:
    """任务开始时重置当前线程统计，返回新统计对象（上层应绑定到任务，供 done 汇总）"""
    stats = _new_stats()
    _tlocal.llm_stats = stats
    return stats


def set_llm_stats(stats: dict):
    """把统计对象绑定到当前线程（断点恢复时继续累计到原任务统计，防统计丢失）"""
    _tlocal.llm_stats = stats


def get_llm_stats() -> dict:
    """当前线程统计快照（无统计时返回全零，不报错）"""
    return dict(_current_stats())


def estimate_cost(stats: dict) -> float:
    """费用估算（元）：优先按模型分桶单价（Σ 每模型 tokens×该模型单价）；
    旧统计对象（无 by_model 分桶）用全局默认单价；无 tokens 返回 0"""
    by_model = stats.get("by_model")
    if isinstance(by_model, dict) and by_model:
        total = 0.0
        for mname, mstats in by_model.items():
            ip, op = get_model_price(mname)
            total += (mstats.get("input_tokens", 0) * ip
                      + mstats.get("output_tokens", 0) * op) / 1_000_000
        return total
    return (stats.get("input_tokens", 0) * PRICE_INPUT_PER_M
            + stats.get("output_tokens", 0) * PRICE_OUTPUT_PER_M) / 1_000_000


def cost_by_model(stats: dict) -> dict:
    """各模型费用明细 {模型名: 费用}（供 GUI 事件/日志按模型展示）；无分桶返回空"""
    out = {}
    by_model = stats.get("by_model")
    if not isinstance(by_model, dict) or not by_model:
        return out
    for mname, mstats in by_model.items():
        ip, op = get_model_price(mname)
        out[mname] = (mstats.get("input_tokens", 0) * ip
                      + mstats.get("output_tokens", 0) * op) / 1_000_000
    return out


def _extract_usage(resp) -> dict:
    """从 LLM 响应提取 tokens 用量，兼容两种元数据形态；无用量信息返回空（不估算）"""
    um = getattr(resp, "usage_metadata", None)  # langchain 1.x 标准形态
    if isinstance(um, dict) and (um.get("input_tokens") or um.get("output_tokens")):
        return {"input_tokens": um.get("input_tokens", 0), "output_tokens": um.get("output_tokens", 0)}
    rm = getattr(resp, "response_metadata", None) or {}
    tu = rm.get("token_usage") if isinstance(rm, dict) else None  # OpenAI 风格
    if isinstance(tu, dict) and (tu.get("prompt_tokens") or tu.get("completion_tokens")):
        return {"input_tokens": tu.get("prompt_tokens", 0), "output_tokens": tu.get("completion_tokens", 0)}
    return {}


def _classify_llm_error(exc: Exception, label: str) -> str:
    """把 LLM 调用异常翻译成用户能看懂的人话。

    设计原则：
    - 不依赖 openai SDK 的具体类名（版本会变），靠异常链上的类型名/消息特征分类
    - 保留原始异常摘要在末尾，方便排障
    - 所有提示都带档位名，方便用户定位是哪个模型配错了
    """
    # 遍历异常链（__cause__ / __context__），把所有类型名+消息拼一起做关键词匹配
    chain_parts = []
    seen = set()
    cur = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        chain_parts.append(f"{type(cur).__name__}: {cur}")
        cur = getattr(cur, "__cause__", None) or getattr(cur, "__context__", None)
    chain_text = " || ".join(chain_parts)
    low = chain_text.lower()

    def hit(*keys):
        return any(k in chain_text or k.lower() in low for k in keys)

    # 1) 无法连接（代理/网络/DNS）
    if hit("APIConnectionError", "ConnectError", "ConnectionError", "NewConnectionError",
           "NameResolutionError", "getaddrinfo failed", "Failed to establish",
           "Connection refused", "ConnectionResetError", "Connection reset", "无法连接"):
        return (f"无法连接到 LLM 服务（档位={label}）。"
                f"请检查：① 是否需要代理/VPN ② .env 里 LLM_BASE_URL 是否正确 ③ 网络是否稳定。"
                f"\n原始错误：{str(exc)[:200]}")
    # 2) 超时
    if hit("APITimeoutError", "TimeoutError", "ReadTimeout", "Timeout"):
        return (f"LLM 调用超时（档位={label}）。"
                f"可在 GUI 任务表单调大「LLM超时(秒)」，或在 manual_settings.py 调大 LLM_TIMEOUT。"
                f"\n原始错误：{str(exc)[:200]}")
    # 3) 认证失败（401/403）
    if hit("AuthenticationError", "PermissionDeniedError", "Invalid API Key",
           "Incorrect API key", "invalid_api_key", "Unauthorized", "403"):
        return (f"LLM 认证失败（档位={label}）：API key 无效、过期或无权限。"
                f"请检查 .env 中对应 api_key 是否正确（注意多余空格/换行）。"
                f"\n原始错误：{str(exc)[:200]}")
    # 4) 模型不存在 / 不支持
    if hit("ModelNotFound", "model_not_found", "does not exist", "model `", "404"):
        return (f"模型不存在或该提供商不支持（档位={label}）。"
                f"请核对 manual_settings.py 里该档的 model 名与 base_url 是否匹配同一提供商。"
                f"\n原始错误：{str(exc)[:200]}")
    # 5) 余额/额度不足
    if hit("InsufficientQuota", "insufficient_quota", "insufficient quota", "quota_exceeded",
           "Insufficient balance", "余额不足", "Payment Required", "402"):
        return (f"账户余额/额度不足（档位={label}）。请充值或更换模型提供商。"
                f"\n原始错误：{str(exc)[:200]}")
    # 6) 速率限制
    if hit("RateLimit", "rate_limit", "rate limit", "Too Many Requests", "429"):
        return (f"触发速率限制（档位={label}）。请稍后重试，或降低并发/减少调用频率。"
                f"\n原始错误：{str(exc)[:200]}")
    # 其他：保留原始信息，标注未分类
    return f"LLM 调用失败（档位={label}），未识别错误类型。原始错误：{str(exc)[:300]}"


class LoggingLLM:
    """ChatOpenAI 包装器：调用时记录交互输入输出 + 累计任务级用量统计（按模型分桶）"""

    def __init__(self, llm, label: str, model_name: str = None):
        self._llm = llm
        self._label = label          # 注册表档位名（router/standard/reasoning/...）
        self._model_name = model_name or getattr(llm, "model_name", None) or label  # API 模型名（计价分桶键）
        self._timeout = None         # None=沿用 client 构造时的默认值
        self._max_retries = None

    def invoke(self, prompt, **kwargs):
        detail_logger.info(f"[LLM交互][{self._label}] <<输入>> {prompt}")
        try:
            resp = self._llm.invoke(prompt, **kwargs)
        except Exception as e:
            friendly = _classify_llm_error(e, self._label)
            detail_logger.error(f"[LLM交互][{self._label}] 调用异常: {friendly}")
            raise RuntimeError(friendly) from e
        content = getattr(resp, "content", str(resp))
        detail_logger.info(f"[LLM交互][{self._label}] >>输出<< {content}")
        # 任务级用量统计：轮次=每次调用；tokens 从响应真实读取，缺失时仅计轮次
        stats = _current_stats()
        stats["calls"] += 1
        bm = stats.setdefault("by_model", {})
        ms = bm.setdefault(self._model_name, {"calls": 0, "input_tokens": 0, "output_tokens": 0})
        ms["calls"] += 1
        usage = _extract_usage(resp)
        if usage:
            stats["input_tokens"] += usage["input_tokens"]
            stats["output_tokens"] += usage["output_tokens"]
            ms["input_tokens"] += usage["input_tokens"]
            ms["output_tokens"] += usage["output_tokens"]
        return resp

    def set_timeout(self, timeout: float, max_retries: int = None):
        """运行时重建底层 client（LLM 无状态，安全）：应用新超时/重试配置，None=保持现值；
        模型/base_url/api_key 从注册表取（支持多提供商与多档位）；
        【修复】重建时同步 _model_name——否则 .env 换模型后费用会记到旧模型名下"""
        self._timeout = timeout if timeout is not None else self._timeout
        self._max_retries = max_retries if max_retries is not None else self._max_retries
        cfg = MODEL_REGISTRY.get(self._label, {})
        new_model = cfg.get("model")
        if new_model:
            self._model_name = new_model  # 同步计价键
        self._llm = ChatOpenAI(
            model=new_model or os.getenv("LLM_MODEL_COMPLEX"),
            openai_api_key=cfg.get("api_key") or os.getenv("LLM_API_KEY"),
            openai_api_base=cfg.get("base_url") or os.getenv("LLM_BASE_URL"),
            temperature=0.3,
            request_timeout=self._timeout if self._timeout is not None else DEFAULT_TIMEOUT,
            max_retries=self._max_retries if self._max_retries is not None else DEFAULT_MAX_RETRIES,
        )

    # 透传其余常用属性（如需要）
    def __getattr__(self, item):
        return getattr(self._llm, item)


def _build_llm(name: str) -> LoggingLLM:
    """按注册表构造一档 LoggingLLM（超时/重试来自默认值）；model_name=API 模型名（计价分桶键）"""
    cfg = MODEL_REGISTRY[name]
    api_key = (cfg.get("api_key") or "").strip()
    base_url = (cfg.get("base_url") or "").strip()
    # 防御：api_key 必须是 ASCII（Bearer token 走 HTTP header）。
    # 若还是 manual_settings 里的中文占位符（如 "sk-请填入..."），httpx 会抛出晦涩的
    # "'ascii' codec can't encode characters..."，用户完全看不懂。这里提前拦截，给出人话错误。
    try:
        api_key.encode("ascii")
    except (UnicodeEncodeError, UnicodeDecodeError):
        raise RuntimeError(
            f"模型档位 [{name}] 的 API key 未配置真实密钥（当前是占位符）。\n"
            f"请在 .env 中设置 LLM_{name.upper()}_API_KEY=sk-你的真实key；"
            f"或在 manual_settings.py 的 MODELS['{name}']['api_key'] 改为引用已配置的环境变量。"
        )
    # 防御：base_url 同样必须是 ASCII（URL 走网络层）
    try:
        base_url.encode("ascii")
    except (UnicodeEncodeError, UnicodeDecodeError):
        raise RuntimeError(
            f"模型档位 [{name}] 的 base_url 含非 ASCII 字符（疑似占位符）。\n"
            f"请在 .env 中设置 LLM_{name.upper()}_BASE_URL=https://api.你的提供商.com 或全局 LLM_BASE_URL。"
        )
    return LoggingLLM(
        ChatOpenAI(
            model=cfg["model"],
            openai_api_key=api_key,
            openai_api_base=cfg["base_url"],
            temperature=0.3,
            request_timeout=DEFAULT_TIMEOUT,
            max_retries=DEFAULT_MAX_RETRIES,
        ),
        name,
        model_name=cfg["model"],
    )


# 惰性构建缓存（get_llm 唯一入口；首次取用时构建）
_llm_cache = {}


def get_llm(name: str = DEFAULT_TIER):
    """按注册表档位名取 LLM（唯一取用入口，已缓存；未注册回退默认档位）。
    所有 Agent 一律经此取模型，换模型=改 .env，Agent 零改动"""
    if name not in MODEL_REGISTRY:
        name = DEFAULT_TIER
    if name not in _llm_cache:
        _llm_cache[name] = _build_llm(name)
    return _llm_cache[name]


def configure_llms(timeout: float = None, max_retries: int = None):
    """应用任务级 LLM 配置（超时/重试）：None=保持当前值；作用于已实例化的所有档位。
    全局生效（当前单任务执行模型）；GUI 任务启动时按表单 timeout 调用"""
    if timeout is None and max_retries is None:
        return
    for llm in list(_llm_cache.values()):
        llm.set_timeout(timeout, max_retries)


def reset_model_registry():
    """模型配置变更后重载注册表（GUI 保存 manual_settings.py 后调用）：
    reload manual_settings → 重建 MODEL_REGISTRY/MODEL_PRICES → 清空 LLM 缓存
    （下次 get_llm 按新配置重建 client；运行中任务用旧 client 不受影响）"""
    global MODEL_REGISTRY, MODEL_PRICES
    import importlib
    import manual_settings
    importlib.reload(manual_settings)
    MODEL_REGISTRY = _load_model_registry()
    MODEL_PRICES = {}
    for _cfg in MODEL_REGISTRY.values():
        if _cfg["model"] and (_cfg["input_price"] is not None or _cfg["output_price"] is not None):
            MODEL_PRICES[_cfg["model"]] = (_cfg["input_price"], _cfg["output_price"])
    _llm_cache.clear()
