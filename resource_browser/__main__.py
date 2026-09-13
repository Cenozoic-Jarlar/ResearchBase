"""
[模块] resource_browser/__main__.py — 支持 python -m resource_browser 独立运行
[职责] 委托给 run.main()，等价于 python resource_browser/run.py
"""
from resource_browser.run import main

if __name__ == "__main__":
    main()
