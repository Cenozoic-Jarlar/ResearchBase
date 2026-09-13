"""
tools/ 目录定位说明：
本目录存放「程序内部非 Skill 功能模块」——即被编排层/main 直接调用、但不需要暴露给 LLM 作为可调用工具的能力。
与 skills/ 的区别：
- skills/：给 LLM/Agent 按需调用的标准工具（SKILL_META 自动注册，含写给 LLM 的注释）
- tools/：程序自身的辅助功能（文档输出、格式化、文件处理等），不在 LLM 工具清单中
"""
