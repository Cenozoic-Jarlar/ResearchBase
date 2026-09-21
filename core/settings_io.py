"""
[模块] core/settings_io.py — 模型配置读写（GUI 编辑 manual_settings.py 的专属后端）
[职责] 读取 manual_settings.py 的模型注册表（含环境变量引用信息）与运行参数；
       按前端提交数据重建 MODELS 块与运行参数行（保留文件头注释）；写前语法校验 + .bak 备份
[设计思想] 读写分离：
           读 = 源码 ast 解析（拿 MODELS 块与每档位的 env 引用名）+ exec 源码到临时命名空间
               （拿运行时值；exec 拿到的 api_key 是真实 key，因此**永不返回前端**）；
           写 = ast 定位目标赋值节点行范围 → 文本块替换（不碰注释）→ compile() 校验 →
               备份后落盘；密钥边界=api_key 只读展示 env 引用名，前端不可编辑；
               base_url 可编辑值、但保留其 env 引用语义（无 env 引用则存纯字符串，留空=继承全局）；
           保存成功后需调 llm_config.reset_model_registry() 让运行中进程立即生效
[关键约定] ★ api_key 只读（前端不可编辑、不返回真实值）；base_url 保留 env 引用语义；
           ★ 写前必须 compile 校验，失败拒绝且不动原文件；
           ★ 写前备份 .bak（保留最近一版）；档位名必须是合法 Python 标识符且 model 非空；
           ★ 运行参数（LLM_TIMEOUT 等）单行替换；MODELS 整块替换，文件头注释原样保留
[被谁调用] web_gui/app.py（GET/POST /api/models_config）；测试 test_settings_io.py
[修改注意] 与 manual_settings.py 的 MODELS 字段结构强绑定；改字段名需同步此模块、前端与 AGENTS.md §6
"""
import ast
import os
import shutil

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_path() -> str:
    """manual_settings.py 默认路径（项目根）"""
    return os.path.join(PROJECT_ROOT, "manual_settings.py")


# ---------- 读 ----------

def _exec_ns(path: str) -> dict:
    """把 manual_settings.py 源码 exec 到隔离命名空间，返回其全局变量（不污染 import 缓存）。

    注意：manual_settings.py 内部会调用 load_dotenv() 加载 .env（幂等）——这会把 .env 的值
    注入 os.environ。这里在 exec 结束后**恢复宿主环境**，避免读取配置这一动作产生副作用
    （否则后续任何模块读到的环境变量都会被悄悄改写）。"""
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    ns = {"os": os, "load_dotenv": __import__("dotenv").load_dotenv, "__name__": "manual_settings_io"}
    before = dict(os.environ)
    try:
        exec(compile(src, path, "exec"), ns)
    finally:
        # 恢复 exec 期间被 load_dotenv 新增/改写的环境变量，保持宿主环境不变
        for k in set(os.environ) - set(before):
            os.environ.pop(k, None)
        for k, v in before.items():
            os.environ[k] = v
    return ns


def _getenv_info(text: str, field: str) -> str:
    """从源码片段提取某字段的 env 变量名；兼容两种写法：
    - os.getenv("LLM_XXX", "默认值")  （旧格式）
    - resolve_key("LLM_XXX")          （新格式，推荐：无占位符）
    非 env 引用返回 None"""
    import re
    # 先试新格式 resolve_key("XXX")
    m = re.search(field + r'\s*"?\s*:\s*resolve_key\(\s*"([A-Za-z_][A-Za-z0-9_]*)"', text)
    if m:
        return m.group(1)
    # 回退旧格式 os.getenv("XXX", "...")
    m = re.search(field + r'\s*"?\s*:\s*os\.getenv\(\s*"([A-Za-z_][A-Za-z0-9_]*)"', text)
    return m.group(1) if m else None


def _models_blocks(src: str) -> dict:
    """解析 MODELS 字典，返回 {档位名: 该档位 dict 的源码文本}（含注释前文；用于按档位提取 env 引用）"""
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "MODELS" for t in node.targets):
            if isinstance(node.value, ast.Dict):
                lines = src.split("\n")
                out = {}
                for k, v in zip(node.value.keys, node.value.values):
                    if isinstance(k, ast.Constant) and isinstance(v, ast.Dict):
                        out[k.value] = "\n".join(lines[v.lineno - 1:v.end_lineno])
                return out
    return {}


def read_settings(path: str = None) -> dict:
    """
    读取模型配置（GUI 用）：
    {
      models: [{name, model, base_url, base_url_env, api_key_env, role,
                capabilities[list], input_price, output_price}],  # 不含真实密钥
      run_params: {llm_timeout, llm_max_retries, detail_log_enabled, price_input_per_m, price_output_per_m}
    }
    """
    path = path or default_path()
    if not os.path.exists(path):
        raise FileNotFoundError(f"配置文件不存在：{path}")
    ns = _exec_ns(path)
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    blocks = _models_blocks(src)
    models_out = []
    raw_models = ns.get("MODELS") or {}
    for name, cfg in raw_models.items():
        block = blocks.get(name, "")
        models_out.append({
            "name": name,
            "model": (cfg.get("model") or ""),
            "base_url": (cfg.get("base_url") or ""),
            "base_url_env": _getenv_info(block, "base_url"),
            "api_key_env": _getenv_info(block, "api_key"),
            "role": (cfg.get("role") or ""),
            "capabilities": list(cfg.get("capabilities") or []),
            "input_price": cfg.get("input_price"),
            "output_price": cfg.get("output_price"),
        })
    return {
        "models": models_out,
        "run_params": {
            "llm_timeout": ns.get("LLM_TIMEOUT", 90),
            "llm_max_retries": ns.get("LLM_MAX_RETRIES", 1),
            "detail_log_enabled": bool(ns.get("DETAIL_LOG_ENABLED", True)),
            "price_input_per_m": ns.get("PRICE_INPUT_PER_M", 2.0),
            "price_output_per_m": ns.get("PRICE_OUTPUT_PER_M", 8.0),
        },
    }


# ---------- 写 ----------

def _to_price(value):
    """价格转 float/None；非法抛 ValueError"""
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        raise ValueError(f"价格必须为数字，收到：{value!r}")


def _validate_name(name: str) -> str:
    name = (name or "").strip()
    if not name.isidentifier():
        raise ValueError(f"档位名必须为合法 Python 标识符（字母/数字/下划线，数字不能开头）：{name!r}")
    return name


def _render_models(models: list, old_env: dict) -> str:
    """
    生成 MODELS = {...} 块文本。
    models: [{name, model, base_url, role, capabilities, input_price, output_price}]
    old_env: {旧档位名: {"base_url_env": str|None, "api_key_env": str|None}}——保留原 env 引用；
             新档位名默认 base_url_env=LLM_BASE_URL、api_key_env=LLM_API_KEY
    """
    lines = ["MODELS = {"]
    for i, m in enumerate(models):
        name = _validate_name(m.get("name"))
        model = (m.get("model") or "").strip()
        if not model:
            raise ValueError(f"档位 {name or '?'} 的模型名不能为空")
        role = (m.get("role") or "").strip()
        caps = [c.strip() for c in (m.get("capabilities") or []) if c and str(c).strip()]
        ip = _to_price(m.get("input_price"))
        op = _to_price(m.get("output_price"))
        env = old_env.get(name)  # None=新档位；dict=旧档位（可能 base_url_env=None=纯字符串）
        if env is not None:
            bu_env = env.get("base_url_env") or ""   # 旧档位：None 保持纯字符串，非 None 保留原 env
            ak_env = env.get("api_key_env") or "LLM_API_KEY"
        else:
            bu_env = "LLM_BASE_URL"                  # 新档位：默认全局 env 引用（.env 可覆盖）
            ak_env = "LLM_API_KEY"
        base_url = (m.get("base_url") or "").strip()
        if base_url:
            if bu_env:
                base_url_expr = f'os.getenv("{bu_env}", "{base_url}")'
            else:
                base_url_expr = f'"{base_url}"'      # 旧档位纯字符串语义保留（不套 env）
        else:
            base_url_expr = None  # 省略=继承全局 LLM_BASE_URL
        lines.append(f"    # ── 档位{i+1} {name}：{role or '未填写用途'} ──")
        lines.append(f'    "{name}": {{')
        lines.append(f'        "model": "{model}",')
        if base_url_expr:
            lines.append(f"        \"base_url\": {base_url_expr},")
        lines.append(f'        "api_key": resolve_key("{ak_env}"),  # ★ key 在 .env：{ak_env}=sk-...')
        lines.append(f'        "role": "{role}",')
        if caps:
            lines.append('        "capabilities": [' + ", ".join(f'"{c}"' for c in caps) + "],")
        if ip is not None:
            lines.append(f"        \"input_price\": {ip},")
        if op is not None:
            lines.append(f"        \"output_price\": {op},")
        lines.append("    },")
    lines.append("}")
    return "\n".join(lines)


def _render_run_params(run_params: dict) -> dict:
    """运行参数 → {变量名: 新值文本}（按变量名替换对应行）"""
    out = {}
    if "llm_timeout" in run_params:
        v = run_params.get("llm_timeout")
        if v is None or str(v).strip() == "":
            raise ValueError("LLM 超时不能为空")
        try:
            out["LLM_TIMEOUT"] = str(int(float(str(v).strip())))
        except ValueError:
            raise ValueError(f"LLM 超时必须为数字：{v!r}")
    if "llm_max_retries" in run_params:
        v = run_params.get("llm_max_retries")
        try:
            out["LLM_MAX_RETRIES"] = str(int(str(v).strip()))
        except (ValueError, AttributeError):
            raise ValueError(f"LLM 重试次数必须为整数：{v!r}")
    if "detail_log_enabled" in run_params:
        out["DETAIL_LOG_ENABLED"] = "True" if run_params.get("detail_log_enabled") else "False"
    if "price_input_per_m" in run_params:
        out["PRICE_INPUT_PER_M"] = repr(_to_price(run_params.get("price_input_per_m")))
    if "price_output_per_m" in run_params:
        out["PRICE_OUTPUT_PER_M"] = repr(_to_price(run_params.get("price_output_per_m")))
    return out


def save_settings(models: list, run_params: dict = None, path: str = None) -> dict:
    """
    校验并保存模型配置到 manual_settings.py（保留文件头注释）：
    1. 收集旧档位的 env 引用（保留 base_url/api_key 的 os.getenv 语义）
    2. ast 定位 MODELS 块与运行参数行 → 文本替换
    3. compile() 语法校验 → 备份 .bak → 落盘
    返回 {ok, path, models_count}；失败抛 ValueError/IOError（原文件不动）
    """
    path = path or default_path()
    if not os.path.exists(path):
        raise FileNotFoundError(f"配置文件不存在：{path}")
    if not models or not isinstance(models, list):
        raise ValueError("模型列表不能为空")
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    # 旧 env 引用映射
    old = read_settings(path)
    old_env = {m["name"]: {"base_url_env": m["base_url_env"], "api_key_env": m["api_key_env"]} for m in old["models"]}
    new_models = _render_models(models, old_env)
    run_lines = _render_run_params(run_params or {})

    # 用 ast 精确定位替换区间（处理字符串/注释中的括号，比括号计数稳）
    # replaces = {起始行(1-based): (结束行, 新文本)}，从后往前应用避免行号错位
    tree = ast.parse(src)
    lines = src.split("\n")
    replaces = {}
    found_models = False
    for node in tree.body:
        if isinstance(node, ast.Assign):
            name = None
            for t in node.targets:
                if isinstance(t, ast.Name):
                    name = t.id
                    break
            if name == "MODELS":
                found_models = True
                replaces[node.lineno] = (node.end_lineno, new_models)
            elif name in run_lines:
                replaces[node.lineno] = (node.end_lineno, f"{name} = {run_lines[name]}")
    if not found_models:
        raise ValueError("manual_settings.py 中找不到 MODELS 定义，拒绝改写")

    # 从后往前应用替换（行号从大到小）
    for lineno in sorted(replaces.keys(), reverse=True):
        end, new_text = replaces[lineno]
        lines[lineno - 1:end] = new_text.split("\n")
    new_src = "\n".join(lines)
    # 语法校验
    try:
        compile(new_src, path, "exec")
    except SyntaxError as e:
        raise ValueError(f"生成的配置语法错误，已拒绝保存（原文件未改动）：{e}")
    # 备份 + 落盘
    if os.path.exists(path + ".bak"):
        os.remove(path + ".bak")
    shutil.copy2(path, path + ".bak")
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_src)
    return {"ok": True, "path": path, "models_count": len(models)}
