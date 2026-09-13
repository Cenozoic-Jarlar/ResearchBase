"""
[模块] memory/ — 记忆与价值观体系（自动加载，与核心解耦）
[职责] 承载长期记忆池与价值观框架库：
       - profiles/ 价值观框架（topic 类可自动匹配，style 类仅显式加载）
       - memories/ 长期记忆（用户偏好、任务历史）
[设计思想] 价值观 = 任务级"行为标准"（立场/证据/风格/批判侧重），与 Agent 通过
           "维度标签"（values 键）松耦合连接；自动注册（空/有内容一视同仁）
[关键约定] ★ 加载优先级：显式指定 > 自动匹配 > 通用默认；可叠加（topic+style 多框架同用）
[被谁调用] memory_advisor Agent、main.py / task_manager / StaticWorkflowDirector（注入钩子）
[修改注意] 新增框架复制 profiles/_profile_template.py；规范常量在 memory_registry.py
"""
