"""
[模块] resource_browser/__init__.py — 资源浏览器插件包
[职责] 三个分区（资产展示=只读代码 / 档案管理=可编辑资料 / 日志功能=只读记录）
       的本地文件浏览、查看、编辑能力；自包含，可独立运行也可挂载主 GUI
[设计思想] 一个组件覆盖"看代码/看资料/改资料/看日志"四类需求；
           分区权限写死在 config.py，下级目录继承上级权限，不做逐文件控制
[被谁调用] 主 GUI（web_gui/app.py 挂载 blueprint）、独立入口（python -m resource_browser）
[修改注意] 改分区/目录/权限只改 config.py；改业务逻辑只改 service.py；路由只改 api.py
"""
from resource_browser.api import blueprint

__all__ = ["blueprint"]
