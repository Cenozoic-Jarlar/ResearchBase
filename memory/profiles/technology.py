"""
[模块] memory/profiles/technology.py — 价值观框架：科技类主题
[职责] 科技/技术类主题的行为标准：理性实证、概念清晰、界定边界
[设计思想] topic 类框架：关键词命中自动加载；面向实证分析场景
[关键约定] 关键词覆盖科技常见表述；values 键名与 Agent consumes 对应
[被谁调用] memory_registry 自动匹配（如"AI 原理"→technology）
[修改注意] 增加框架维度键时同步各 Agent 的 consumes 声明
"""
PROFILE_META = {
    "name": "technology",
    "dimension": "topic",
    "category_keywords": ["科技", "技术", "AI", "人工智能", "算法", "软件", "硬件", "编程", "代码",
                          "数据", "算力", "芯片", "大模型", "互联网", "数字化", "机器人"],
    "description": "科技类主题：理性实证、概念清晰、明确适用边界",
    "values": {
        "stance": "理性实证，技术中性，不夸大效果也不贬低风险",
        "evidence": "技术文档/实验数据/权威评测优先，注明数据来源",
        "style": "概念先界定、术语准确、结构分明",
        "critique": "关注可证伪性、局限性与适用边界",
    },
}
