"""
test_settings_io.py
测试 core/settings_io.py（模型配置读写：GUI 编辑 manual_settings.py 的专属后端）
要点：全部用例操作【临时副本】，绝不触碰真实 manual_settings.py；
覆盖：读解析（含 api_key_env 提取）/ 写回环 / 运行参数 / 坏输入拒绝（原文件不动）/ 备份 / 注释保留
"""
import os
import shutil
import tempfile

from core.settings_io import read_settings, save_settings, default_path

# 建临时目录 + 复制一份 manual_settings.py 副本（测试只改副本）
TEST_DIR = tempfile.mkdtemp(prefix="test_settings_io_")
TMP_PATH = os.path.join(TEST_DIR, "manual_settings.py")
shutil.copy2(default_path(), TMP_PATH)


def _clean_llm_env():
    """备份并临时移除 LLM 相关环境变量，防止 pytest 全量运行时被其他测试文件的
    mock 环境变量（如 LLM_BASE_URL）污染本测试对 base_url 值的断言。
    返回恢复函数。"""
    saved = {}
    for k in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_REASONING_API_KEY", "LLM_MODELS"):
        if k in os.environ:
            saved[k] = os.environ.pop(k)
    def restore():
        for k, v in saved.items():
            os.environ[k] = v
    return restore


def _backup_origin() -> str:
    """备份临时副本当前内容（供断言"坏输入后原文件不动"）"""
    with open(TMP_PATH, "r", encoding="utf-8") as f:
        return f.read()


def test_read_settings():
    print("=" * 60)
    print("【测试：读配置（模型档位/运行参数/env 引用提取）】")
    print("=" * 60)
    data = read_settings(TMP_PATH)
    names = [m["name"] for m in data["models"]]
    assert "router" in names and "standard" in names and "reasoning" in names, f"应含默认三档: {names}"
    by_name = {m["name"]: m for m in data["models"]}
    assert by_name["router"]["model"], "router 模型名不能为空"
    assert by_name["router"]["api_key_env"] == "LLM_API_KEY", "router 应引用全局 LLM_API_KEY"
    assert by_name["reasoning"]["api_key_env"] == "LLM_REASONING_API_KEY", "reasoning 应引用专属 env"
    assert "api_key" not in by_name["router"], "读取结果严禁携带真实密钥值"
    assert data["run_params"]["llm_timeout"] == 90, "超时默认 90"
    assert data["run_params"]["detail_log_enabled"] is True, "详细日志默认开"
    print(f"✅ 读取 {len(data['models'])} 档：{names}")
    print(f"✅ env 引用：router→{by_name['router']['api_key_env']}、reasoning→{by_name['reasoning']['api_key_env']}（不含密钥值）")
    print(f"✅ 运行参数：超时={data['run_params']['llm_timeout']} 重试={data['run_params']['llm_max_retries']} 日志={data['run_params']['detail_log_enabled']}")
    print("✅ 读配置测试通过\n")


def test_save_roundtrip():
    print("=" * 60)
    print("【测试：写回环（改模型/价格 + 新增档位 → 重读验证）】")
    print("=" * 60)
    restore = _clean_llm_env()
    try:
        data = read_settings(TMP_PATH)
        models = data["models"]
        std = next(m for m in models if m["name"] == "standard")
        std["model"] = "providerX/new-model"
        std["input_price"] = 1.5
        std["output_price"] = 3.5
        std["role"] = "改后用途"
        std["capabilities"] = ["text", "long_context", "vision"]
        models.append({
            "name": "fast", "model": "providerY/fast-model", "base_url": "http://provider-y",
            "role": "新增档位", "capabilities": ["text"], "input_price": 0.5, "output_price": 1.0,
        })
        rp = dict(data["run_params"]); rp["llm_timeout"] = 60; rp["detail_log_enabled"] = False
        res = save_settings(models, rp, TMP_PATH)
        assert res["models_count"] == 4, f"应 4 档: {res}"
        data2 = read_settings(TMP_PATH)
        by_name = {m["name"]: m for m in data2["models"]}
        assert by_name["standard"]["model"] == "providerX/new-model", "model 应更新"
        assert by_name["standard"]["input_price"] == 1.5, "价格应更新"
        assert by_name["standard"]["capabilities"] == ["text", "long_context", "vision"], "能力应更新"
        assert by_name["fast"]["base_url"], "新档位 base_url 应有值（env 引用或兜底）"
        assert by_name["fast"]["base_url_env"] == "LLM_BASE_URL", "新档位应默认全局 env 引用"
        # 注：base_url 实际值可能被 .env 的 LLM_BASE_URL 覆盖（契约=env 优先），故只断言"有值+env 引用存在"
        assert by_name["router"]["api_key_env"] == "LLM_API_KEY", "旧档位 env 引用应保留"
        assert data2["run_params"]["llm_timeout"] == 60 and data2["run_params"]["detail_log_enabled"] is False, "运行参数应更新"
        print("✅ 写回环：4 档（含新增 fast）/ model+价格+能力+base_url+运行参数全部正确")
        print("✅ 旧档位 env 引用保留；新档位默认全局 env 引用（base_url 值可被 .env 覆盖=契约）")
        print("✅ 写回环测试通过\n")
    finally:
        restore()


def test_save_invalid():
    print("=" * 60)
    print("【测试：坏输入拒绝（原文件不动）】")
    print("=" * 60)
    data = read_settings(TMP_PATH)
    origin = _backup_origin()
    # 1. 空模型名
    models = [dict(m) for m in data["models"]]
    models[0]["model"] = "   "
    try:
        save_settings(models, {}, TMP_PATH)
        assert False, "空模型名应被拒绝"
    except ValueError as e:
        print(f"  ✅ 空模型名被拒：{e}")
    # 2. 非法档位名
    models = [dict(m) for m in data["models"]]
    models[0]["name"] = "bad-name!"
    try:
        save_settings(models, {}, TMP_PATH)
        assert False, "非法档位名应被拒绝"
    except ValueError as e:
        print(f"  ✅ 非法档位名被拒：{e}")
    # 3. 坏价格
    models = [dict(m) for m in data["models"]]
    models[0]["input_price"] = "abc"
    try:
        save_settings(models, {}, TMP_PATH)
        assert False, "坏价格应被拒绝"
    except ValueError as e:
        print(f"  ✅ 坏价格被拒：{e}")
    # 4. 空列表
    try:
        save_settings([], {}, TMP_PATH)
        assert False, "空列表应被拒绝"
    except ValueError as e:
        print(f"  ✅ 空列表被拒：{e}")
    # 原文件必须一字未动
    assert _backup_origin() == origin, "坏输入后原文件必须保持不变"
    print("✅ 坏输入全部拒绝且原文件未改动\n")


def test_backup_and_comments():
    print("=" * 60)
    print("【测试：备份生成 + 文件头注释保留】")
    print("=" * 60)
    data = read_settings(TMP_PATH)
    models = [dict(m) for m in data["models"]]
    save_settings(models, {}, TMP_PATH)
    assert os.path.exists(TMP_PATH + ".bak"), ".bak 备份应生成"
    with open(TMP_PATH + ".bak", "r", encoding="utf-8") as f:
        bak = f.read()
    assert "[模块] manual_settings.py" in bak, "备份应为保存前版本（含头注释）"
    with open(TMP_PATH, "r", encoding="utf-8") as f:
        cur = f.read()
    assert "[模块] manual_settings.py" in cur, "保存后文件头注释必须保留"
    assert "MODELS = {" in cur and "LLM_TIMEOUT = " in cur, "MODELS/运行参数仍在"
    print("✅ .bak 备份生成（内容=保存前版本）")
    print("✅ 文件头注释保留、MODELS/运行参数结构完整")
    print("✅ 备份与注释测试通过\n")


if __name__ == "__main__":
    test_read_settings()
    test_save_roundtrip()
    test_save_invalid()
    test_backup_and_comments()
    shutil.rmtree(TEST_DIR, ignore_errors=True)
    print("🎉 全部 settings_io 测试通过")
