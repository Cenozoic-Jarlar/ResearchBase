"""
[模块] web_gui/app.py — Flask 可视化控制台后端
[职责] 提供 REST API：任务创建/查询/反馈/取消 + 注册清单；承载单页前端
[设计思想] 表现层与核心层解耦：本文件只做 HTTP 路由，业务状态机全部在
           web_gui/services/task_manager.py；核心代码零改动即可复用
[关键约定] API 契约：POST /api/task {topic,mode,flow_name,profiles}（profiles=显式价值观框架名列表，可空）；
           POST /api/task/<id>/feedback {action: plan_feedback|start|resume, content}；
           mode ∈ auto|human_review|static；
           GET/POST /api/models_config（模型配置读写，见 core/settings_io.py；密钥不进出前端）
[被谁调用] gui_web.py（入口）、浏览器前端 static/app.js（轮询/交互）
[修改注意] 新增动作需同时改 task_manager 对应方法与前端 app.js
"""
from flask import Flask, jsonify, request, send_from_directory

from agent_registry.registry import registry
from skills.skill_registry import skill_registry
from planner.flow_registry import flow_registry
from memory.memory_registry import memory_registry
from web_gui.services.task_manager import task_manager

# 资源浏览器插件：三个分区（资产展示/档案管理/日志功能）本地文件浏览编辑；
# 自包含包，可独立运行（python -m resource_browser），这里挂载一行进入主 GUI
from resource_browser import blueprint as resource_browser_blueprint

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.register_blueprint(resource_browser_blueprint)


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/info")
def info():
    from skills.list_topics import list_topic_names
    from core.paths import list_domains
    from core.domain_config import list_domains_with_stats
    from llm_config import list_models  # 模型档位列表（name+role+capabilities+价格），供任务表单下拉
    # topics 跳转目标 = 主题库 _repo.md（资源浏览器 archives 区路径：通用层 prefix=LocalDataBase，
    # 域内 prefix=domains/<域>/LocalDataBase）；agents/skills/flows/profiles 的 file 字段由各注册器注入
    topics = [{"name": n, "path": f"LocalDataBase/{n}/_repo.md", "domain": None} for n in list_topic_names()]
    for d in list_domains():
        for n in list_topic_names(d, include_general=False):
            topics.append({"name": n, "path": f"domains/{d}/LocalDataBase/{n}/_repo.md", "domain": d})
    return jsonify({
        "agents": registry.get_agent_list(),
        "skills": skill_registry.get_skill_list(),
        "flows": flow_registry.get_flow_list(),
        "topics": topics,
        "profiles": memory_registry.get_profile_list(),
        "models": list_models(),  # 模型档位（留空=按难度自动映射）
        "domains": [None] + list_domains(),  # 域下拉选项：None=通用层（默认），其余=具体域（_ 开头隐藏）
        "domain_stats": list_domains_with_stats(),  # 各域主题库数/文件数概览（key: general/域名）
    })


@app.route("/api/models_config", methods=["GET"])
def get_models_config_api():
    """读取模型配置（GUI 编辑面板用）：模型注册表（api_key 只读展示 env 引用名，不返回真实密钥）+ 运行参数"""
    from core.settings_io import read_settings
    try:
        return jsonify(read_settings())
    except Exception as e:
        return jsonify({"ok": False, "error": f"读取配置失败：{e}"}), 400


@app.route("/api/models_config", methods=["POST"])
def save_models_config_api():
    """保存模型配置到 manual_settings.py：非密钥字段编辑 + 语法校验 + .bak 备份；
    成功后重载模型注册表（同进程立即生效，无需重启）"""
    from core.settings_io import save_settings
    from llm_config import reset_model_registry
    data = request.get_json(silent=True) or {}
    try:
        result = save_settings(data.get("models"), data.get("run_params"))
        reset_model_registry()  # 重载注册表+清 LLM 缓存，下次任务取用新配置
        return jsonify({"ok": True, "message": f"已保存 {result['models_count']} 个档位（已备份 .bak，注册表已重载）"})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": f"保存失败：{e}"}), 500


@app.route("/api/domains", methods=["POST"])
def create_domain_api():
    """新建域：目录骨架 + _domain.md 模板（幂等：已存在不覆盖）"""
    from core.domain_config import create_domain
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    intro = (data.get("intro") or "").strip()
    if not name:
        return jsonify({"ok": False, "message": "域名不能为空"}), 400
    msg = create_domain(name, intro)
    return jsonify({"ok": msg.startswith("✅"), "message": msg})


@app.route("/api/domains/<name>/rename", methods=["POST"])
def rename_domain_api(name):
    """重命名域：移动目录（校验保留名/重名）"""
    from core.domain_config import rename_domain
    data = request.get_json(silent=True) or {}
    new_name = (data.get("new_name") or "").strip()
    if not new_name:
        return jsonify({"ok": False, "message": "新域名不能为空"}), 400
    ok, msg = rename_domain(name, new_name)
    return jsonify({"ok": ok, "message": msg})


@app.route("/api/import_materials", methods=["POST"])
def import_materials_api():
    """资料入库（异步任务，进度展示在左侧任务流程区）：
    创建 mode=import 任务 → 后台线程逐条经 collector 整理入库。
    body: {topic(目标话题：库名/新话题名，空=AI 自动提炼), domain(必选：空=公共知识库/通用层，
           具体域=专用域), write_mode(auto|new|merge, 默认 auto), items: [{type, name, content}]}
    每个来源独立整理（避免单 prompt 爆 token）；单条失败隔离不阻断后续；
    返回 {ok, task_id, count}，前端轮询 /api/task/<task_id> 获取进度"""
    data = request.get_json(silent=True) or {}
    topic = (data.get("topic") or "").strip()  # 空=交给 collector 自动提炼主题并归一
    domain = (data.get("domain") or "").strip().lower() or None
    write_mode = (data.get("write_mode") or "auto").strip().lower()
    if write_mode not in ("new", "merge"):
        write_mode = "auto"
    items = data.get("items") or []
    if not items:
        return jsonify({"ok": False, "error": "未提供任何资料来源（URL/文本/文件）"}), 400
    valid = [it for it in items if str(it.get("content") or "").strip()]
    if not valid:
        return jsonify({"ok": False, "error": "来源内容均为空"}), 400
    task = task_manager.create(topic or "资料入库（自动提炼主题）", "import", items=valid, domain=domain,
                               raw_topic=topic, write_mode=write_mode)  # raw_topic 保留用户原始输入（空=AI 提炼），topic 仅作展示名
    task_manager.start(task)
    return jsonify({"ok": True, "task_id": task.id, "count": len(valid)})


@app.route("/api/topics", methods=["POST"])
def create_topic():
    """新建空话题库（不挂来源，只建目录+_repo.md）。
    body: {topic: 话题名, domain: 空=公共知识库/通用层, 具体域=专用域}"""
    data = request.get_json(silent=True) or {}
    topic = (data.get("topic") or "").strip()
    domain = (data.get("domain") or "").strip().lower() or None
    if not topic:
        return jsonify({"ok": False, "error": "话题名不能为空"}), 400
    try:
        from core.paths import local_db_root
        from skills.write_local_database import _ensure_topic_dir, _init_repo_meta
        root = local_db_root(domain)
        os.makedirs(root, exist_ok=True)
        repo_dir = _ensure_topic_dir(topic, root)
        _init_repo_meta(repo_dir, os.path.basename(repo_dir))
        return jsonify({"ok": True, "topic_dir": os.path.basename(repo_dir),
                        "message": f"话题库已建：{os.path.basename(repo_dir)}"})
    except Exception as e:
        return jsonify({"ok": False, "error": f"建库失败：{e}"}), 500


@app.route("/api/task", methods=["POST"])
def create_task():
    data = request.get_json(silent=True) or {}
    topic = (data.get("topic") or "").strip()
    mode = data.get("mode") or "auto"
    flow_name = data.get("flow_name") or ""
    profiles = data.get("profiles") or []
    domain = (data.get("domain") or "").strip().lower() or None  # None=通用层
    model_tier = (data.get("model_tier") or "").strip() or None  # 模型档位（None=按难度自动映射）
    timeout = data.get("timeout")  # LLM 超时秒数（None=用 .env 默认）
    auto_archive = bool(data.get("auto_archive", False))  # 跑完自动归档要点到资料库
    try:
        timeout = float(timeout) if timeout else None
        if timeout is not None and not (10 <= timeout <= 600):
            return jsonify({"ok": False, "error": "LLM 超时需在 10~600 秒之间"}), 400
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "LLM 超时必须是数字（秒）"}), 400
    if not topic:
        return jsonify({"ok": False, "error": "主题不能为空"}), 400
    if mode not in ("auto", "human_review", "static"):
        return jsonify({"ok": False, "error": f"未知模式：{mode}"}), 400
    if mode == "static":
        available = {f["name"] for f in flow_registry.get_flow_list()}
        if flow_name not in available:
            return jsonify({"ok": False, "error": f"未知静态流程：{flow_name}，可选 {sorted(available)}"}), 400

    # 校验模型档位为已注册档位名（非法值回退 None=自动映射，不阻断任务）
    if model_tier:
        from llm_config import MODEL_REGISTRY
        if model_tier not in MODEL_REGISTRY:
            return jsonify({"ok": False, "error": f"未知模型档位：{model_tier}，可选 {sorted(MODEL_REGISTRY)}"}), 400

    task = task_manager.create(topic, mode, flow_name, profiles, domain, timeout, model_tier,
                               auto_archive=auto_archive)
    task_manager.start(task)
    return jsonify({"ok": True, "task_id": task.id})


@app.route("/api/task/<task_id>")
def get_task(task_id):
    task = task_manager.get(task_id)
    if not task:
        return jsonify({"ok": False, "error": "任务不存在"}), 404
    return jsonify({"ok": True, "task": task.to_dict()})


@app.route("/api/task/<task_id>/feedback", methods=["POST"])
def task_feedback(task_id):
    task = task_manager.get(task_id)
    if not task:
        return jsonify({"ok": False, "error": "任务不存在"}), 404
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    content = (data.get("content") or "").strip()

    if action == "plan_feedback":
        ok, msg = task_manager.feedback_plan(task, content)
    elif action == "start":
        ok, msg = task_manager.start_execute(task)
    elif action == "resume":
        ok, msg = task_manager.resume_input(task, content)
    else:
        return jsonify({"ok": False, "error": f"未知动作：{action}"}), 400
    return jsonify({"ok": ok, "message": msg})


@app.route("/api/task/<task_id>/cancel", methods=["POST"])
def cancel_task(task_id):
    task = task_manager.get(task_id)
    if not task:
        return jsonify({"ok": False, "error": "任务不存在"}), 404
    ok = task_manager.cancel(task_id)
    return jsonify({"ok": ok, "message": "已发送取消请求" if ok else "当前状态不可取消"})


@app.route("/api/task/<task_id>/archive", methods=["POST"])
def archive_task_api(task_id):
    """手动归档：把已完成任务的 final_article 经 archivist 写入资料库（多一次 LLM 调用）"""
    task = task_manager.get(task_id)
    if not task:
        return jsonify({"ok": False, "error": "任务不存在"}), 404
    try:
        result = task_manager.archive_task(task)
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "error": f"归档失败：{e}"}), 500


def create_app() -> Flask:
    return app
