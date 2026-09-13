"""
[模块] memory/profiles/humanities.py — 价值观框架：人文类主题
[职责] 人文/社会/文化类主题的行为标准：尊重多元、关怀个体、有温度
[设计思想] topic 类框架：关键词命中自动加载；面向价值、伦理、社会文化场景
[关键约定] 关键词覆盖人文常见表述；values 键名与 Agent consumes 对应
[被谁调用] memory_registry 自动匹配（如"城市文化变迁"→humanities）
[修改注意] 增加框架维度键时同步各 Agent 的 consumes 声明
"""
PROFILE_META = {
    "name": "humanities",
    "dimension": "topic",
    "category_keywords": ["人文", "文化", "历史", "伦理", "社会", "艺术", "哲学", "教育",
                          "心理", "城市", "乡村", "民生", "公益", "文学", "影视"],
    "description": "人文类主题：尊重多元价值、关怀个体处境、有洞察有温度",
    "values": {
        "stance": "尊重多元价值，关怀个体处境，避免单一标准评判",
        "evidence": "兼顾史实/文献与一手叙述，注明材料性质",
        "style": "有温度、有洞察，避免冷漠堆砌与空泛抒情",
        "critique": "反思价值预设、权力结构与社会影响",
    },
}
