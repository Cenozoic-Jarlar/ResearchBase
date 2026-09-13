# ResearchBase v0.1.0

**A lightweight, pluggable, dual-engine multi-agent research pipeline.**  
轻量、可插拔、双引擎的多 Agent 研究流水线：输入主题 → 多角色协作研究 → 输出成稿，全程人可干预、过程可封存。

## ✨ Highlights

- **Dual scheduling engines（双调度引擎）**
  - *Dynamic planner*：LLM 根据用户目标动态生成任务计划，支持人工修改意见后重新生成，顺序执行
  - *Static workflow (LangGraph)*：固定拓扑流程，原生 interrupt 人在回路断点，状态快照可恢复
- **Fully pluggable（完全可插拔）**：Agent / Skill / 静态流程 / 价值观框架四大类全部目录自动扫描注册，新增角色无需改任何调度器代码
- **Domain isolation（主题域隔离）**：资料/输出/档案按主题域分隔，域内优先、通用层兜底，多主题互不干扰
- **Memory & values（记忆与价值观体系）**：长期记忆池自动沉淀；价值观框架按主题关键词自动匹配 / 显式指定加载，Agent 按维度消费（stance/evidence/style/critique）
- **Human-in-the-loop（人在回路）**：动态引擎计划审阅 + 执行中 human_input 断点；静态引擎 interrupt 断点；GUI 异步输入
- **Bounded fact-check loop（有界事实审核）**：fact_checker 角色核查事实/来源/幻觉，不通过自动回溯修订，带轮次上限防死循环
- **Model tiering（模型三档）**：router / standard / reasoning 三档位，多提供商可配，按模型真实 token 计价统计（支持 deepseek、硅基流动等任意 OpenAI 兼容提供商）
- **Process archiving（过程封存）**：每次任务自动生成结构化研究档案（计划+各角色产出+成稿），可追溯可回放
- **Web GUI + Resource Browser**：可视化任务控制台（流程图实时进度），独立的资源浏览器插件（资产只读 / 档案可编辑 / 日志只读）
- **Auditable logging**：简单日志 + 详细日志（含 LLM 交互全文），全局可开关

## 🚀 Quick start

```bash
# Python 3.11
python -m venv venv
# Windows: venv\Scripts\activate | macOS/Linux: source venv/bin/activate
pip install -r requirements.txt

# 配置密钥（复制模板 → 填写 API Key）
cp .env.example .env

# 命令行入口（三模式）
python main.py

# Web GUI（自动打开 http://127.0.0.1:5178）
python gui_web.py

# 资源浏览器（可选，端口 5179）
python -m resource_browser
```

## 🧪 Tests

```bash
pip install -r requirements-dev.txt
pytest            # 74 用例全离线，LLM 全部 mock
pytest --cov=.    # 覆盖率 83%
```

CI（GitHub Actions）已配置，push 自动运行全量测试。

## 📦 Model configuration

模型注册表在 `manual_settings.py`（人工/AI 都可维护），密钥只放 `.env`（详见 `.env.example`）：

| Tier | 用途 | 示例 |
|---|---|---|
| `router` | 路由判断/简单问答（最便宜快） | deepseek-ai/DeepSeek-V4-Flash |
| `standard` | 日常调研/写作/审阅主体 | deepseek-ai/DeepSeek-V4-Pro |
| `reasoning` | 复杂推理/深度分析（人工指定） | deepseek-reasoner |

## 📚 Docs

- `README.zh-CN.md` — 中文版说明
- `AGENTS.md` — 设计契约 / AI 维护代码的单一事实来源
- `docs/` — GUI 截图等

## 🧭 Roadmap

- 任务历史回放（地基已就绪：过程封存已落地）
- 中间过程持久化、断点磁盘恢复
- 轻量关联层（入库时 LLM 产出主题/文件关联，供跨主题导航）
- fact_checker 修订循环复核机制完善

## 📄 License

MIT © 2026 ResearchBase Contributors
