"""
[模块] memory/profiles/general.py — 价值观框架：通用默认（兜底）
[职责] 任何任务至少有一套价值观可循；无显式指定且关键词未命中时加载
[设计思想] keywords 留空 → 永不参与自动匹配（避免误命中），仅作 select_profiles 兜底
[关键约定] name="general" 是兜底约定名，select_profiles 兜底逻辑依赖它
[被谁调用] memory_registry.select_profiles（无匹配时兜底加载）
[修改注意] 通用框架只定义底线要求，不应过于具体（具体性交给主题类框架）
"""
PROFILE_META = {
    "name": "general",
    "dimension": "topic",
    "category_keywords": [],
    "description": "通用默认框架：任何任务的最低行为标准（无主题匹配/无显式指定时兜底）",
    "values": {
        "stance": "客观理性，多方平衡，不预设立场",
        "evidence": "信息需有据可查，区分事实与观点",
        "style": "清晰、结构完整、避免空话套话",
        "critique": "注意逻辑一致性与事实核实",
    },
}
