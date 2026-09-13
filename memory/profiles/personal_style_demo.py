"""
[模块] memory/profiles/personal_style_demo.py — 价值观框架：个人风格示例（口语化亲切风）
[职责] 风格类框架示例：表达方式的价值观，由用户/AI 显式指定时加载
[设计思想] dimension="style" + keywords 留空 → 永不参与自动匹配（不会被误加载），
           只能被显式指定（GUI 多选 / CLI 参数 / 动态计划指定）——符合"个人风格按需用"
[关键约定] ★ 风格类框架不与主题绑定，可叠加主题类框架同用（如 policy + personal_style_demo）
[被谁调用] 用户/AI 显式指定（GUI 下拉、任务参数）
[修改注意] 复制本文件改 name/values 即可创建自己的个人风格；本文件是"示例"可随时改名
"""
PROFILE_META = {
    "name": "personal_style_demo",
    "dimension": "style",
    "category_keywords": [],
    "description": "个人风格示例：口语化亲切风，像与朋友交谈（仅显式加载）",
    "values": {
        "style": "口语化、亲切，像与朋友交谈，少用书面套话",
        "stance": "坦诚、不端着，允许表达个人感受",
        "critique": "温和指出问题，不刻薄不嘲讽",
    },
}
