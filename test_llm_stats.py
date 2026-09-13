"""
[测试] test_llm_stats.py — LLM 用量统计（轮次/tokens/费用估算/线程隔离）+ 3 档位决策 + 注册表解析
[运行] venv\\Scripts\\python.exe test_llm_stats.py
[约定] 纯离线：mock ChatOpenAI 与响应对象；不调真实 LLM、不写文件
"""
import os
from types import SimpleNamespace
from unittest.mock import Mock

os.environ["LLM_API_KEY"] = "fake_test_key"
os.environ["LLM_BASE_URL"] = "https://mock.api.test"
os.environ["LLM_MODELS"] = ('[{"name":"router","model":"mock-r","role":"路由判断，便宜快","capabilities":["text"],'
                            '"input_price":1,"output_price":4},'
                            '{"name":"standard","model":"mock-s","role":"日常主模型","capabilities":["text","long_context"],'
                            '"input_price":2,"output_price":8},'
                            '{"name":"reasoning","model":"mock-m","role":"复杂推理","capabilities":["text","long_context"]}]')

import langchain_openai
langchain_openai.ChatOpenAI = Mock()

import llm_config as lc


def _reset():
    return lc.reset_llm_stats()


def test_usage_extract():
    print("=" * 60)
    print("【测试：tokens 用量提取（两种元数据形态）】")
    print("=" * 60)
    # langchain 1.x usage_metadata
    r1 = SimpleNamespace(usage_metadata={"input_tokens": 100, "output_tokens": 50}, content="x")
    u1 = lc._extract_usage(r1)
    assert u1 == {"input_tokens": 100, "output_tokens": 50}, u1
    # OpenAI 风格 response_metadata.token_usage
    r2 = SimpleNamespace(usage_metadata=None,
                         response_metadata={"token_usage": {"prompt_tokens": 30, "completion_tokens": 20}})
    u2 = lc._extract_usage(r2)
    assert u2 == {"input_tokens": 30, "output_tokens": 20}, u2
    # 无用量信息 → 空（仅计轮次，不估算）
    r3 = SimpleNamespace(usage_metadata=None, response_metadata={})
    assert lc._extract_usage(r3) == {}
    print("✅ usage_metadata / token_usage / 缺失 三种形态全部正确处理\n")


def test_invoke_accumulate():
    print("=" * 60)
    print("【测试：LoggingLLM.invoke 累计轮次与 tokens】")
    print("=" * 60)
    _reset()
    fake_llm = Mock()
    fake_llm.invoke = Mock(return_value=SimpleNamespace(
        content="hi", usage_metadata={"input_tokens": 200, "output_tokens": 80}))
    wrapped = lc.LoggingLLM(fake_llm, "test")
    wrapped.invoke("q1")
    wrapped.invoke("q2")
    stats = lc.get_llm_stats()
    assert stats["calls"] == 2, f"轮次应累计 2: {stats}"
    assert stats["input_tokens"] == 400 and stats["output_tokens"] == 160, stats
    print(f"✅ 2 次调用累计：轮次 2 / 上传 400 / 下载 160")
    # 无 usage 的响应只计轮次
    fake_llm.invoke = Mock(return_value=SimpleNamespace(content="x", usage_metadata=None))
    wrapped.invoke("q3")
    stats = lc.get_llm_stats()
    assert stats["calls"] == 3 and stats["input_tokens"] == 400, stats
    print("✅ 无用量响应仅计轮次（tokens 不虚增）")
    print("✅ 累计统计测试通过\n")


def test_invoke_by_model_bucket():
    print("=" * 60)
    print("【测试：按模型分桶（by_model 键=API 模型名）】")
    print("=" * 60)
    _reset()
    fake = Mock()
    fake.invoke = Mock(return_value=SimpleNamespace(
        content="x", usage_metadata={"input_tokens": 100, "output_tokens": 50}))
    w1 = lc.LoggingLLM(fake, "llm_complex", model_name="model-AA")
    w2 = lc.LoggingLLM(fake, "llm_simple", model_name="model-BB")
    w1.invoke("q")
    w2.invoke("q")
    w2.invoke("q")
    stats = lc.get_llm_stats()
    bm = stats["by_model"]
    assert bm["model-AA"] == {"calls": 1, "input_tokens": 100, "output_tokens": 50}, bm
    assert bm["model-BB"] == {"calls": 2, "input_tokens": 200, "output_tokens": 100}, bm
    assert stats["calls"] == 3 and stats["input_tokens"] == 300, stats
    print(f"✅ 分桶正确：{bm}（总 3 轮 / 300 输入）")
    print("✅ 按模型分桶测试通过\n")


def test_model_registry_parse():
    print("=" * 60)
    print("【测试：旧格式 LLM_MODELS JSON 兼容解析（3 档位/多提供商/role+capabilities/价格）】")
    print("=" * 60)
    import json
    import os
    # 现场保存：扁平变量（.env load_dotenv 注入，新格式优先，需先清掉才能测旧格式） + LLM_MODELS
    flat_keys = [k for k in os.environ if k.startswith("LLM_") and k.endswith("_MODEL")]
    flat_saved = {k: os.environ[k] for k in flat_keys}
    for k in flat_keys:
        os.environ.pop(k)
    old = os.environ.get("LLM_MODELS")
    os.environ["LLM_MODELS"] = json.dumps([
        {"name": "router", "model": "providerA/model-1",
         "role": "路由判断", "capabilities": ["text"],
         "base_url": "http://provider-a", "api_key": "key-a",
         "input_price": 1, "output_price": 4},
        {"name": "standard", "model": "providerB/model-2",
         "role": "日常主模型", "capabilities": ["text", "long_context"],
         "input_price": 2, "output_price": 8},  # 省略 base_url/api_key → 继承全局
        {"name": "reasoning", "model": "providerA/model-3",
         "role": "复杂推理", "capabilities": ["text"]},  # 省略价格 → None
        {"name": "", "model": "bad"}  # 无效项应跳过
    ])
    try:
        reg = lc._load_model_registry()
        assert set(reg) == {"router", "standard", "reasoning"}, f"无效项应跳过: {list(reg)}"
        assert reg["router"]["base_url"] == "http://provider-a", "多提供商 base_url 应独立"
        assert reg["router"]["api_key"] == "key-a", "多提供商 api_key 应独立"
        assert reg["router"]["role"] == "路由判断" and reg["router"]["capabilities"] == ["text"], "role/capabilities 应解析"
        assert reg["standard"]["base_url"] == os.environ["LLM_BASE_URL"], "省略应继承全局 base_url"
        assert reg["reasoning"]["input_price"] is None, "省略价格应为 None"
        # 解析失败容错：回退 manual_settings 人工全局设置（非旧式两档）
        os.environ["LLM_MODELS"] = "{bad json"
        import manual_settings
        reg2 = lc._load_model_registry()
        assert set(reg2) == set(manual_settings.MODELS), \
            f"坏 JSON 应回退 manual_settings: {list(reg2)}"
        print("✅ 旧格式兼容：3 档位/多提供商/省略继承/无效项跳过/role+capabilities/坏 JSON 回退 manual_settings 全部正确")
    finally:
        if old is None:
            os.environ.pop("LLM_MODELS", None)
        else:
            os.environ["LLM_MODELS"] = old
        for k, v in flat_saved.items():
            os.environ[k] = v
    print("✅ 旧格式 JSON 兼容解析测试通过\n")


def test_manual_settings_registry_parse():
    print("=" * 60)
    print("【测试：manual_settings 人工全局设置解析（档位/多提供商/省略继承/价格/空项跳过）】")
    print("=" * 60)
    import manual_settings
    saved = manual_settings.MODELS
    saved_llm_models = os.environ.pop("LLM_MODELS", None)  # 隔离：先清掉旧格式环境变量（manual_settings 才生效）
    try:
        manual_settings.MODELS = {
            # 档1 router：显式 base_url/api_key（多提供商）
            "router": {
                "model": "providerA/model-1",
                "base_url": "http://provider-a",
                "api_key": "key-a",
                "role": "路由判断",
                "capabilities": ["text"],
                "input_price": 1,
                "output_price": 4,
            },
            # 档2 standard：省略 base_url/api_key → 继承全局环境变量
            "standard": {
                "model": "providerB/model-2",
                "role": "日常主模型",
                "capabilities": ["text", "long_context"],
                "input_price": 2,
                "output_price": 8,
            },
            # 档3 reasoning：省略价格 → None
            "reasoning": {
                "model": "providerA/model-3",
                "role": "复杂推理",
                "capabilities": ["text"],
            },
            "": {"model": "bad"},        # 空档位名 → 跳过
            "bad_tier": {"model": " "},  # 空模型名 → 跳过
        }
        reg = lc._load_model_registry()
        assert set(reg) == {"router", "standard", "reasoning"}, f"空项应跳过: {list(reg)}"
        assert reg["router"]["model"] == "providerA/model-1"
        assert reg["router"]["base_url"] == "http://provider-a", "显式 base_url 应保留"
        assert reg["router"]["api_key"] == "key-a", "显式 api_key 应保留"
        assert reg["router"]["role"] == "路由判断" and reg["router"]["capabilities"] == ["text"], "role/capabilities 应解析"
        assert reg["router"]["input_price"] == 1.0 and reg["router"]["output_price"] == 4.0, "价格应解析"
        assert reg["standard"]["base_url"] == os.environ["LLM_BASE_URL"], "省略应继承全局 base_url"
        assert reg["standard"]["api_key"] == os.environ["LLM_API_KEY"], "省略应继承全局 api_key"
        assert reg["standard"]["input_price"] == 2.0, "显式价格应保留"
        assert reg["reasoning"]["input_price"] is None, "省略价格应为 None"
        assert reg["reasoning"]["base_url"] == os.environ["LLM_BASE_URL"], "reasoning 省略应继承全局"
        print("✅ manual_settings 解析：档位/多提供商/省略继承/空项跳过/role+capabilities+价格全部正确")

        # manual_settings 与旧格式 LLM_MODELS 同时存在 → 环境变量旧格式优先（测试/临时覆盖）
        os.environ["LLM_MODELS"] = '[{"name":"router","model":"mock-r","role":"r","capabilities":["text"]}]'
        reg2 = lc._load_model_registry()
        assert reg2["router"]["model"] == "mock-r", "LLM_MODELS 环境变量应优先（临时覆盖）"
        print("✅ 环境变量 LLM_MODELS 优先于 manual_settings（临时覆盖/测试兼容）")
    finally:
        manual_settings.MODELS = saved
        os.environ.pop("LLM_MODELS", None)
        if saved_llm_models is not None:
            os.environ["LLM_MODELS"] = saved_llm_models
    print("✅ manual_settings 注册表解析测试通过\n")


def test_tier_resolution():
    print("=" * 60)
    print("【测试：档位决策链 resolve_tier（人工指定 > 难度映射 > 默认 standard）】")
    print("=" * 60)
    # 默认（无 task_level、无 model_tier）→ standard
    assert lc.resolve_tier({}) == "standard", "无任何指示应回退默认档位"
    assert lc.resolve_tier(None) == "standard", "state 为 None 也应回退默认"
    # 难度映射：simple→router，complex→standard
    assert lc.resolve_tier({"task_level": "simple"}) == "router", "simple 应映射到 router 档"
    assert lc.resolve_tier({"task_level": "complex"}) == "standard", "complex 应映射到 standard 档"
    # 人工指定优先于难度映射（reasoning 档仅人工可用）
    assert lc.resolve_tier({"model_tier": "reasoning", "task_level": "simple"}) == "reasoning", "人工指定应优先"
    assert lc.resolve_tier({"model_tier": "reasoning", "task_level": "complex"}) == "reasoning", "人工指定应覆盖难度映射"
    # 非法档位回退难度映射
    assert lc.resolve_tier({"model_tier": "not_exist", "task_level": "simple"}) == "router", "非法档位应回退映射"
    # Agent 声明档位（AGENT_META.tier）：任务指定 > Agent tier > 难度映射
    assert lc.resolve_tier({}, "router") == "router", "Agent 声明 tier 应生效"
    assert lc.resolve_tier({}, "standard") == "standard", "Agent 声明 tier 应生效"
    assert lc.resolve_tier({"task_level": "simple"}, "standard") == "standard", "Agent tier 优先于难度映射"
    assert lc.resolve_tier({"model_tier": "reasoning"}, "router") == "reasoning", "任务指定优先于 Agent tier"
    assert lc.resolve_tier({"model_tier": "bad_tier"}, "router") == "router", "非法任务档位回退 Agent tier"
    assert lc.resolve_tier(None, None) == "standard", "全部为空回退默认"
    print(f"✅ 决策链：默认={lc.resolve_tier({})} / simple→{lc.resolve_tier({'task_level':'simple'})}"
          f" / complex→{lc.resolve_tier({'task_level':'complex'})}"
          f" / 人工reasoning→{lc.resolve_tier({'model_tier':'reasoning'})}"
          f" / Agent router→{lc.resolve_tier({}, 'router')}"
          f" / 任务指定覆盖Agent→{lc.resolve_tier({'model_tier':'reasoning'}, 'router')}")
    print("✅ 档位决策测试通过（含 Agent 声明 tier 优先级）\n")


def test_by_model_cost():
    print("=" * 60)
    print("【测试：按模型分桶计价（不同模型不同单价）】")
    print("=" * 60)
    # 手动注入两个模型价格（模型A 1/4，模型B 2/8 元每百万）
    lc.MODEL_PRICES["model-AA"] = (1.0, 4.0)
    lc.MODEL_PRICES["model-BB"] = (2.0, 8.0)
    try:
        stats = {
            "calls": 2, "input_tokens": 3_000_000, "output_tokens": 0,
            "by_model": {
                "model-AA": {"calls": 1, "input_tokens": 1_000_000, "output_tokens": 0},
                "model-BB": {"calls": 1, "input_tokens": 2_000_000, "output_tokens": 0},
            }
        }
        cost = lc.estimate_cost(stats)
        # model-AA: 1M*1 = 1 元；model-BB: 2M*2 = 4 元 → 合计 5 元
        assert abs(cost - 5.0) < 1e-9, f"按模型计价应 5 元: {cost}"
        cd = lc.cost_by_model(stats)
        assert abs(cd["model-AA"] - 1.0) < 1e-9 and abs(cd["model-BB"] - 4.0) < 1e-9, cd
        # 旧统计对象（无 by_model）→ 全局默认单价回退
        cost_old = lc.estimate_cost({"calls": 1, "input_tokens": 1_000_000, "output_tokens": 0})
        assert abs(cost_old - lc.PRICE_INPUT_PER_M) < 1e-9, cost_old
        print(f"✅ 分模型计价：AA ¥1.0 + BB ¥4.0 = ¥{cost:.1f}；旧格式回退全局默认正确")
    finally:
        lc.MODEL_PRICES.pop("model-AA", None)
        lc.MODEL_PRICES.pop("model-BB", None)
    print("✅ 按模型计价测试通过\n")


def test_reset_and_thread_isolation():
    print("=" * 60)
    print("【测试：reset/set 与线程隔离（GUI 多任务不串扰）】")
    print("=" * 60)
    s1 = _reset()
    assert lc.get_llm_stats()["calls"] == 0, "reset 后应为空统计"

    # 模拟任务线程统计
    def worker(stats, results):
        lc.set_llm_stats(stats)
        st = lc._current_stats()
        st["calls"] += 1
        st["input_tokens"] += 10
        results.append(lc.get_llm_stats())

    results = []
    import threading
    t1 = threading.Thread(target=worker, args=(s1, results))
    t2 = threading.Thread(target=worker, args=({"calls": 0, "input_tokens": 0, "output_tokens": 0, "by_model": {}}, results))
    t1.start(); t2.start(); t1.join(); t2.join()
    assert results[0]["calls"] == 1 and results[1]["calls"] == 1, f"两线程互不串扰: {results}"
    # 主线程仍是 reset 后的 s1；t1 显式 set 复用 s1（断点恢复续累计语义）→ s1 被 +1；
    # 但 t2 的独立对象不得串入 s1（input_tokens 应只是 t1 的 10，而非 20）
    st_main = lc._current_stats()
    assert st_main is s1, "主线程统计对象应为 s1"
    assert st_main["calls"] == 1 and st_main["input_tokens"] == 10, \
        f"t2 独立对象不应串入 s1（恢复续累计只对显式 set 的对象生效）: {st_main}"
    print("✅ 线程隔离正确（独立对象互不串扰；显式 set 复用=断点续累计语义）")
    print("✅ 线程隔离测试通过\n")


def test_cost_estimate():
    print("=" * 60)
    print("【测试：费用估算（全局默认单价回退）】")
    print("=" * 60)
    # 用默认单价：输入2元/百万，输出8元/百万 → 100万输入 + 100万输出 = 10元
    cost = lc.estimate_cost({"input_tokens": 1_000_000, "output_tokens": 1_000_000})
    assert abs(cost - 10.0) < 1e-9, f"费用应 10 元: {cost}"
    cost0 = lc.estimate_cost({})
    assert cost0 == 0.0, "空统计费用应为 0"
    print(f"✅ 费用估算正确（{lc.PRICE_INPUT_PER_M}/{lc.PRICE_OUTPUT_PER_M} 元/百万，示例 10 元）")
    print("✅ 费用估算测试通过\n")


if __name__ == "__main__":
    test_usage_extract()
    test_invoke_accumulate()
    test_invoke_by_model_bucket()
    test_model_registry_parse()
    test_manual_settings_registry_parse()
    test_tier_resolution()
    test_by_model_cost()
    test_reset_and_thread_isolation()
    test_cost_estimate()
