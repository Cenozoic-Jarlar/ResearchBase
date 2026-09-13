"""
[模块] resource_browser/run.py — 资源浏览器独立入口（插件可独立运行）
[职责] 不依赖主 GUI，单独启动资源浏览器服务（默认端口 5179，RES_PORT 可覆盖）
[设计思想] 自包含包三入口：本文件（独立）、web_gui/app.py（挂载）、任意代码 import
[关键约定] debug=False、use_reloader=False（与主 GUI 一致，避免线程干扰）
[被谁调用] 直接运行：venv\\Scripts\\python.exe -m resource_browser
[修改注意] 端口常量与 gui_web.py 的 GUI_PORT 区分，避免撞端口
"""
import os
import threading
import webbrowser

from flask import Flask

from resource_browser.api import blueprint


def create_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(blueprint)
    return app


def main():
    port = int(os.environ.get("RES_PORT", "5179"))
    url = f"http://127.0.0.1:{port}/resource-browser"
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print("=" * 50)
    print(" 📂 ResearchBase 资源浏览器（独立模式）")
    print(f" 地址：{url}")
    print(" 按 Ctrl+C 退出服务")
    print("=" * 50)
    create_app().run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
