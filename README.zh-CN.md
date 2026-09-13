# ResearchBase（研库）

> 轻量、可插拔、双引擎、人可干预的**多 Agent 研究流水线框架**（Python）。
> 输入一个主题 → 多个 Agent 协作研究 → 输出结构化文章——全程你都可以随时介入。

[English](README.md) · **中文**

ResearchBase 是一个个人知识整理与主题研究助手框架：**双调度引擎**（LLM 动态规划 + 固定 LangGraph 工作流）、**Agent / Skill / 流程全部目录自动注册**、**价值观框架与长期记忆体系**、**主题域隔离**的本地知识库，以及**零依赖 Web GUI**。代码设计为**AI 可维护**（六段式 AI 可读注释、`AGENTS.md` 作为单一事实来源），同时保持人工可读。

---

## 功能特性

- **双引擎，同一套 Agent 生态**
  - *动态规划引擎*：LLM 根据目标动态生成任务计划，执行前可人工审阅/修改/重新生成
  - *静态工作流引擎*：LangGraph 固定拓扑，原生支持 `interrupt` 断点、状态快照与恢复
- **全可插拔**：往 `agent_registry/agents/`、`skills/`、`planner/flows/`、`memory/profiles/` 放一个文件即自动注册，调度器零改动
- **人在回路对称**：动态引擎=计划审阅+执行中 human_input 断点；静态引擎=执行中 interrupt 暂停
- **主题域隔离**：资料/输出/档案按 `domains/<域>/` 分隔，另有跨域共享的通用层与域私有资料库
- **价值观与记忆体系**：可插拔价值观框架（立场/证据/风格/批判侧重），按主题自动匹配或显式指定；长期记忆自动沉淀
- **知识库管理**：主题索引化本地资料库，三级读取（概览→摘要→全文）省 token；支持 URL/本地文件/文本入库，含主题归一与智能合并
- **研究过程封存**：每次运行完整归档（计划+各角色产出+最终文章），可追溯、可回放
- **事实审核有界循环**：`fact_checker` 审核事实/幻觉，带修订上限（默认 2 轮），防死循环
- **Web GUI + 资源浏览器**：任务可视化控制（实时流程图+日志），内置资产/档案/日志三分区浏览器
- **用量与费用统计**：按模型真实统计 token、按档位单价计价，写入日志
- **AI 可维护代码库**：六段式 AI 可读头注释、AGENTS.md 设计契约

---

## 架构

```
┌────────────────────────────────────────────────────────────────┐
│                         入口                                    │
│   main.py (命令行)          gui_web.py (Web GUI :5178)          │
└───────────────┬───────────────────────────────┬────────────────┘
                │                               │
┌───────────────▼──────────────┐   ┌────────────▼────────────────┐
│   动态规划引擎                │   │  静态工作流 (LangGraph)     │
│   LLM 生成 JSON 任务计划      │   │  固定 DAG + interrupt       │
│   计划审阅 / 重新生成         │   │  检查点 / 恢复              │
└───────────────┬──────────────┘   └────────────┬────────────────┘
                │                               │
                └───────────────┬───────────────┘
                                ▼
              ┌──────────────────────────────────┐
              │   Agent 注册器（自动加载）       │
              │   任务路由 · 调研 · 撰稿 ·       │
              │   事实审核 · 归档 · …            │
              └───────────────┬──────────────────┘
                              ▼
              ┌──────────────────────────────────┐
              │   Skill 工具层（自动注册）       │
              │   读/写主题库 · 抓取 URL · …     │
              └───────────────┬──────────────────┘
                              ▼
              ┌──────────────────────────────────┐
              │   统一 State + 记忆/价值观       │
              │   主题域（隔离）                 │
              └──────────────────────────────────┘
```

核心设计原则：

- **一份 State，增量合并**——每个 Agent 只读自己需要的字段、只返回自己要更新的字段
- **选角与表现分离**——Agent 人设（是谁）与价值观框架（怎么做事）通过维度标签松耦合
- **域是任务参数**——任务创建时快照域，读取顺序=域内 → 通用层回退

---

## 快速开始

### 1. 环境要求

- **Python 3.11+**
- 可访问任意 OpenAI 兼容的大模型 API

### 2. 安装

```bash
git clone <你的仓库地址>
cd ResearchBase

# 创建虚拟环境
python -m venv venv

# Windows (PowerShell)
venv\Scripts\activate
# Linux / macOS
source venv/bin/activate

pip install -r requirements.txt          # 运行依赖
pip install -r requirements-dev.txt      # 开发/测试依赖（pytest、pytest-cov）
```

### 3. 配置

1. 复制 `.env.example` 为 `.env` 并填写密钥：

```bash
cp .env.example .env
```

2. 编辑 `.env`，至少填写：

```ini
# 全局兜底密钥/地址（未单独配置的档位继承）
LLM_API_KEY=sk-你的密钥
LLM_BASE_URL=https://api.openai.com/v1

# 可选：某档位专属密钥，例如推理档
LLM_REASONING_API_KEY=sk-你的推理密钥
```

3. （可选）编辑 `manual_settings.py`——人工/AI 全局设置，含**模型注册表**（档位→模型名/base_url/价格）与运行参数。**密钥只放 `.env`**；`manual_settings.py` 通过 `os.getenv(...)` 引用密钥，可安全提交到 git。

### 4. 运行

```bash
# 命令行——交互式（选择模式：动态全自动 / 动态人审 / 静态工作流）
python main.py

# 非交互指定域
DOMAIN="工作A" python main.py

# Web GUI（自动打开 http://127.0.0.1:5178）
python gui_web.py

# 资源浏览器（独立模式 :5179；主 GUI 内也可访问 /resource-browser）
python -m resource_browser

# Markdown → Word
python md2docx.py [文件或目录]
```

> 端口可覆盖：`GUI_PORT`、`RES_PORT`（默认 5178 / 5179）。

---

## 使用示例

```bash
# 研究一个主题并写文章
python main.py
# → 输入"北京市丰台区小升初政策2026年情况，以及与2025年相比的变化"
# → 选择模式 1（动态全自动）或 3（静态工作流）

# 强制指定价值观风格（CLI）
PROFILES="cute_style,policy" python main.py

# 任务级强制模型档位
MODEL_TIER="reasoning" python main.py
```

或用 Web GUI：选择域（或公共知识库/通用层）→ 输入主题 → 选择模式 → 实时观看流程图推进。GUI 还支持把资料（URL / 本地文件 / 粘贴文本）直接整理入库。

---

## 配置参考

| 文件 | 用途 | 谁可改 |
|---|---|---|
| `.env` | 仅密钥（gitignore） | 仅人工 |
| `.env.example` | 密钥模板（占位符，入库） | 人工/AI |
| `manual_settings.py` | 模型注册表（档位/模型/base_url/价格）+ 运行参数 | 人工 & AI |
| `AGENTS.md` | 设计契约 / AI 的单一事实来源 | 人工 & AI |
| `core/settings_io.py` | GUI 安全编辑 manual_settings.py 的后端（AST 块替换+语法校验+.bak 备份） | — |

### 模型三档

| 档位 | 用途 | 典型模型 |
|---|---|---|
| `router` | 路由判断/简单问答（最便宜快） | `deepseek-ai/DeepSeek-V4-Flash` |
| `standard` | 日常调研/写作/审阅主体 | `deepseek-ai/DeepSeek-V4-Pro` |
| `reasoning` | 复杂推理（仅人工指定） | `deepseek-reasoner` |

决策链：**任务指定档位（GUI/CLI）→ Agent 声明档位 → 难度映射（simple→router、complex→standard）→ 默认 standard**。

---

## 测试

14 个测试模块全部 mock LLM——**完全离线、零 API 费用**。

```bash
# 逐个运行
python test_agent_system-ok.py
python test_web_gui.py
...

# 或统一用 pytest
pytest -q
pytest --cov=. --cov-report=term-missing   # 覆盖率
```

覆盖范围：Agent/Skill/流程自动注册、双引擎、知识库读写、资料采集（归一/合并/写入模式）、记忆与价值观、事实审核有界循环、过程封存、主题域、Web GUI 任务状态机、资源浏览器权限、模型配置编辑、LLM 用量统计。

> 维护约定：测试文件是资产，不得删除；逻辑变更时整文件替换。

---

## 扩展指南

- **新增 Agent**：复制 `agent_registry/agents/_agent_template.py` → 实现 `run(state)` + `AGENT_META`（**必须声明 tier 档位**）→ 放入 `agents/` → 重启即注册；动态规划 LLM 会自动按 description 选用
- **新增 Skill**：复制现有 Skill → `run()` + `SKILL_META`（description 写给 LLM 看）→ 放入 `skills/`
- **新增价值观框架**：复制 `memory/profiles/_profile_template.py` → `PROFILE_META` → 放入 `profiles/`；按主题匹配或显式选择
- **新增静态流程**：复制 `planner/flows/_flow_template.py` → `build()` + `FLOW_META` → 放入 `flows/` → GUI 下拉自动出现
- **新增模型档位**：`manual_settings.MODELS` 加一个块（含价格）→ GUI 下拉零改动自动出现

---

## 目录结构

```
ResearchBase/
├─ main.py                  # 命令行入口（3 种模式）
├─ gui_web.py               # Web GUI 入口（Flask，:5178）
├─ md2docx.py               # Markdown → Word 工具
├─ manual_settings.py       # ★ 人工/AI 全局设置（模型注册表+运行参数）
├─ llm_config.py            # 档位注册表 + get_llm() + 交互日志与用量统计
├─ state_model.py           # 全局 State（唯一）
├─ AGENTS.md                # AI 维护用设计契约
├─ core/                    # logger / paths / settings_io / domain_config
├─ agent_registry/          # 自动注册的 Agent
├─ planner/                 # 动态规划器 + 静态流程（LangGraph）
├─ skills/                  # 自动注册的 LLM 可调工具
├─ memory/                  # 价值观框架 + 长期记忆
├─ tools/                   # 程序内部非 LLM 工具（输出/归档/docx）
├─ web_gui/                 # Flask 应用 + 任务状态机
├─ resource_browser/        # 独立资源浏览器插件
├─ domains/                 # 主题域隔离（资料/输出/档案）
├─ LocalDataBase/           # 主题索引化知识库（gitignore）
├─ archives/                # 研究过程档案（gitignore）
├─ logs/                    # 运行日志（gitignore）
├─ output/                  # 生成文章（gitignore）
└─ test_*.py                # 14 个离线测试模块
```

---

## 路线图与已知限制

- **已知问题**：事实审核修订循环的第二轮放行不一定逐条复核首轮问题清单（见 `AGENTS.md` §7），尚未完全修复
- 规划中：子问题并行研究、结果缓存、多轮对话式研究、对比分析流程、搜索引擎集成、任务历史回放 UI、跨平台验证

---

## 许可

[MIT](LICENSE) © 2026 ResearchBase Contributors
