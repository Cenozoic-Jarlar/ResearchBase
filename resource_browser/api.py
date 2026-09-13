"""
[模块] resource_browser/api.py — 资源浏览器 Blueprint（Flask 路由薄壳 + 页面）
[职责] REST API：/api/resources/sections｜<key>/tree｜<key>/read｜<key>/write；
       页面：/resource-browser（三 Tab 单页）
[设计思想] 路由只做参数解析/异常转换，逻辑全部在 service.py（可脱离 Flask 测试）；
           页面与主 GUI 前端独立（本包 static/），挂载后互不干扰
[关键约定] ★ 写接口仅接受 JSON body {path, content}；只读分区返回 403；
           ★ read 支持 ?max= 覆盖截断长度；错误统一 {ok:false, error}；
           ★ 挂载方式：主 GUI app.register_blueprint(resource_browser.blueprint)；
             独立入口见 run.py
[被谁调用] 主 GUI（web_gui/app.py）、独立入口（resource_browser/run.py）、浏览器
[修改注意] 新增路由同步 service.py 与前端 app.js
"""
from flask import Blueprint, jsonify, request, send_from_directory

from resource_browser import service

blueprint = Blueprint(
    "resource_browser",
    __name__,
    static_folder="static",
    static_url_path="/static/resource_browser",
)


@blueprint.route("/resource-browser")
def index():
    return send_from_directory(blueprint.static_folder, "index.html")


@blueprint.route("/api/resources/sections")
def sections():
    return jsonify({"ok": True, "sections": service.list_sections()})


@blueprint.route("/api/resources/<key>/tree")
def tree(key):
    try:
        return jsonify({"ok": True, "entries": service.tree_for_section(key)})
    except KeyError as e:
        return jsonify({"ok": False, "error": str(e)}), 404


@blueprint.route("/api/resources/<key>/read")
def read(key):
    rel_path = (request.args.get("path") or "").strip()
    try:
        max_chars = int(request.args.get("max") or 0) or service.MAX_READ_CHARS
    except ValueError:
        max_chars = service.MAX_READ_CHARS
    try:
        data = service.read_entry(key, rel_path, max_chars)
        return jsonify({"ok": True, **data})
    except (KeyError, ValueError, FileNotFoundError) as e:
        return jsonify({"ok": False, "error": str(e)}), 404 if isinstance(e, (FileNotFoundError, KeyError)) else 400


@blueprint.route("/api/resources/<key>/write", methods=["POST"])
def write(key):
    body = request.get_json(silent=True) or {}
    rel_path = (body.get("path") or "").strip()
    content = body.get("content") or ""
    try:
        data = service.write_entry(key, rel_path, content)
        return jsonify({"ok": True, **data})
    except KeyError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except PermissionError as e:
        return jsonify({"ok": False, "error": str(e)}), 403
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
