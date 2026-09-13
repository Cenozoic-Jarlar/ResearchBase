"""
[模块] gui_web.py — Web 可视化控制台入口
[职责] 启动 Flask 服务并自动打开浏览器，提供与命令行 main.py 并行的可视化入口
[设计思想] 表现层与核心层解耦：本文件只负责起服务/开浏览器，实际逻辑在 web_gui/；
           不影响核心代码，两入口共用同一套 Agent/Skill/流程注册体系
[关键约定] 端口可用环境变量 GUI_PORT 覆盖（默认 5178）；
           debug=False、use_reloader=False（避免调试器/热重载干扰后台任务线程）
[被谁调用] 直接运行：venv\\Scripts\\python.exe gui_web.py
[修改注意] API 路由在 web_gui/app.py；任务状态机在 web_gui/services/task_manager.py
"""
import os
import threading
import webbrowser

from web_gui.app import app


def main():
    port = int(os.environ.get("GUI_PORT", "5178"))
    url = f"http://127.0.0.1:{port}"
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print("=" * 50)
    print(" 🧠 ResearchBase（研库）可视化控制台")
    print(f" 地址：{url}")
    print(" 按 Ctrl+C 退出服务（浏览器页面可关闭）")
    print("=" * 50)
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
