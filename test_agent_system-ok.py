"""
[测试] test_agent_system-ok.py — Agent 注册加载 + 计划渲染
[运行] venv/Scripts/python.exe test_agent_system-ok.py（或 pytest test_agent_system-ok.py）
[约定] 静态测试：只加载 Agent 元信息、不执行 run；文件顶部 mock 环境变量骗过 LLM 初始化
"""
# ========= 必须放在文件最开头！！优先执行 =========
import os
# 伪造环境变量，防止llm_config读取得到None，触发pydantic报错
os.environ["LLM_API_KEY"] = "fake_test_key"
os.environ["LLM_BASE_URL"] = "https://mock.api.test"
os.environ["LLM_MODELS"] = '[{"name":"router","model":"mock-r","role":"r","capabilities":["text"]},{"name":"standard","model":"mock-s","role":"s","capabilities":["text"]},{"name":"reasoning","model":"mock-m","role":"m","capabilities":["text"]}]'
# ================================================

from agent_registry.registry import registry
from planner.plan_renderer import render_plan

def test_agent_registry_static():
    """静态测试：只加载、校验所有注册Agent角色，不执行任何agent逻辑"""
    print("="*60)
    print("【静态测试：Agent角色注册加载测试】")
    print("="*60)
    agent_list = registry.get_agent_list()
    print(f"✅ 成功加载角色总数：{len(agent_list)}")
    for idx, agent_info in enumerate(agent_list):
        print(f"\n角色 {idx+1}:")
        print(f"  name: {agent_info['name']}")
        print(f"  description: {agent_info['desc']}")
        run_func = registry.get_run_func(agent_info["name"])
        print(f"  ✅ run函数存在: {run_func.__name__}")
    print("\n✅ 静态加载测试全部通过！所有角色注册正常\n")


def test_render_plan_mock():
    """Mock预演：硬编码任务计划，只测试可视化渲染，完全不调用LLM、不执行Agent"""
    print("="*60)
    print("【Mock预演：测试计划渲染，不调用LLM、不执行Agent】")
    print("="*60)
    mock_plan = [
        {"agent":"task_router", "note":"评估任务难度，选择模型"},
        {"agent":"researcher", "note":"读取知识库整理素材"},
        {"agent":"human_review", "note":"人工审阅素材，补充意见"},
        {"agent":"writer", "note":"整合素材，撰写最终文章"}
    ]
    plan_text = render_plan(mock_plan)
    print(plan_text)
    print("\n✅ 计划渲染测试完成！")


if __name__ == "__main__":
    test_agent_registry_static()
    test_render_plan_mock()
