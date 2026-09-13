"""
[模块] planner/plan_renderer.py — 计划文本渲染（动态导演专用）
[职责] 把 JSON 任务计划渲染为人类可读的步骤清单文本
[设计思想] 渲染与执行分离：DynamicPlanner 先 render_plan 展示给用户（命令行/日志），再执行
[关键约定] 输入为 [{"agent","note"},...] 结构；纯函数无副作用
[被谁调用] planner/dynamic_planner.py、测试文件
[修改注意] 输出格式同时被命令行展示与测试断言依赖，改动需同步测试
"""
#计划可视化渲染（动态导演专用）
def render_plan(plan):
    lines = ["\n==== 📋 任务规划方案 ===="]
    for idx, step in enumerate(plan):
        lines.append(f"步骤{idx+1}｜角色: {step['agent']}｜说明: {step['note']}")
    lines.append("=========================")
    return "\n".join(lines)
