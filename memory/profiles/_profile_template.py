"""
[模块] memory/profiles/_profile_template.py — 价值观框架标准模板
[职责] 定义一个价值观框架（复制本文件改 PROFILE_META 即自动注册）
[设计思想] 价值观框架 = 任务级"行为标准"配置，与 Agent 通过维度标签（values 键）连接：
           stance=立场 / evidence=证据要求 / style=风格 / critique=批判侧重（可按需增删键）
[关键约定] ★ dimension="topic" → 参与关键词自动匹配（category_keywords 必填，命中主题即选中）
           ★ dimension="style" → 仅显式加载（category_keywords 留空，不会被自动误匹配）
           ★ values 可留空 {}：照样注册（占位，可被显式指定），但自动匹配自动跳过
[被谁调用] memory_registry（自动注册）
[修改注意] 新增框架 = 复制本文件 → 改名/改关键词/改 values → 放入 profiles/ → 重启即注册
"""
PROFILE_META = {
    "name": "template_profile",        # 唯一英文名（小写下划线），不能重复
    "dimension": "topic",              # topic=可自动匹配 / style=仅显式加载
    "category_keywords": ["示例关键词"],  # topic 类必填；style 类留空 []
    "description": "给用户/AI 看的框架说明",
    "values": {
        "stance": "立场要求：…",
        "evidence": "证据要求：…",
        "style": "风格要求：…",
        "critique": "批判侧重：…",
    },
}
