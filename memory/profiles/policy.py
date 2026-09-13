"""
[模块] memory/profiles/policy.py — 价值观框架：政策类主题
[职责] 政策/法规/政务类主题的行为标准：客观中立、证据严谨
[设计思想] topic 类框架：category_keywords 命中主题即自动加载；维度标签供各 Agent 按需消费
[关键约定] 关键词覆盖政策常见表述；values 键名与 Agent 声明的 consumes 对应
[被谁调用] memory_registry 自动匹配（如"小升初政策"→policy）
[修改注意] 增加框架维度键时同步各 Agent 的 consumes 声明
"""
PROFILE_META = {
    "name": "policy",
    "dimension": "topic",
    "category_keywords": ["政策", "法规", "政务", "政府", "小升初", "中考", "高考", "公告", "制度", "监管", "条例"],
    "description": "政策类主题：客观中立、证据严谨、关注公平性与可执行性",
    "values": {
        "stance": "客观中立，不预设立场，正反观点都呈现",
        "evidence": "官方文件/权威来源优先，关键信息注明出处",
        "style": "严谨、条目化、克制，避免情绪化表达",
        "critique": "关注公平性、执行可行性、受影响群体",
    },
}
