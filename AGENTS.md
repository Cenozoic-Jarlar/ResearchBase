# ResearchBase（研库）— 项目上下文与设计文档（供 AI 优化代码时阅读）

> 本文档是项目的**单一事实来源**：设计思想、程序架构、接口约定、已知约束。
> 优化代码前通读本文档 + 关键源码文件，避免破坏架构约定。

## 1. 项目概述

- **定位**：轻量、可插拔、双引擎、人可干预的多 Agent 研究流水线框架（Python）
- **第一阶段目标**：文本输入主题 → 多 Agent 协作研究 → 输出研究文章
- **技术栈**：Python 3.11 + LangChain + LangGraph + Flask（GUI）
- **虚拟环境**：`venv/`（所有命令用 `venv\Scripts\python.exe` 运行）
- **运行入口**：`main.py`（命令行）、`gui_web.py`（Web 可视化，自动开浏览器）

## 2. 核心设计思想

1. **双调度引擎**（本项目最大特色）：
   - **动态规划引擎**（`planner/dynamic_planner.py`，纯 Python）：LLM 根据用户目标动态生成 JSON 任务计划 → 人可提修改意见 → LLM 重新生成 → 顺序执行
   - **静态工作流引擎**（`planner/static_workflow_director.py`，基于 LangGraph）：固定拓扑、interrupt 断点、状态快照恢复
2. **可插拔体系**：Agent / Skill / 静态流程 三大类全部**目录自动扫描注册**，新增无需改任何调度器代码
3. **全局统一状态**：所有 Agent 读写同一份 State，增量合并
4. **人在回路对称**：动态引擎=执行前计划审阅+执行中 human_input 断点；静态引擎=执行中 interrupt 断点
5. **独立分层**：核心层（agent_registry/planner/skills）与表现层（web_gui）完全解耦
6. **记忆与价值观体系**：长期记忆池 + 价值观框架库（memory/ 自动注册）；
   "选角（AGENT_META.description）与表现（价值观框架）分离"，二者通过维度标签
   （values 键：stance/evidence/style/critique）松耦合连接
7. **主题域隔离（domain）**：人工可维护内容（资料/输出/档案）按 `domains/<域>/` 分隔，
   根目录=通用层（跨域共享）；域是**任务参数**（state.domain，创建时快照），非全局变量；
   读取顺序=域内→通用，写默认进当前域

## 3. 目录结构（当前实际）

```
ResearchBase/（实际目录名仍为 RresearchSystem，仅显示层改名，未动目录/venv/git）
├─ main.py                      # 命令行入口（三模式；可选主题域，环境变量 DOMAIN 或交互输入）
├─ gui_web.py                   # Web 可视化入口（Flask + 自动开浏览器，默认端口5178）
├─ md2docx.py                   # Markdown→Word 转换入口（独立小工具，缺省转换 output/ 全部 md）
├─ state_model.py               # 【唯一】全局状态 State（TypedDict, total=False 支持动态字段；含 domain 字段）
├─ manual_settings.py            # ★人工/ AI 全局设置（模型注册表+运行参数：改模型/加提供商/调价格/修格式都改这；★密钥只放 .env，key 一律 getenv 引用）
├─ llm_config.py                # 模型档位注册表（读 manual_settings.MODELS，3 档多提供商/按模型计价）
│                              #   + get_llm 唯一取用入口 + resolve_tier 档位决策 + LoggingLLM（交互日志+分桶用量统计）
├─ core/
│  ├─ logger.py                 # 双日志：简单(run_*.log) + 详细(detail_run_*.log，含LLM交互)
│  ├─ paths.py                  # 全局路径与资料仓库规范常量（唯一事实来源）+ 主题域路径函数
│  ├─ settings_io.py            # 模型配置读写（GUI 编辑 manual_settings.py 的后端：ast 定位块替换+compile 校验+.bak 备份；密钥只读展示 env 引用）
│  └─ domain_config.py          # 域配置解析（_domain.md）+ 域管理（新建/重命名/概览统计）
├─ domains/                     # 【主题域隔离单元】domains/<域>/ 下含 LocalDataBase/output/archives；
│  │                            #   域=任务级参数（state.domain），与根目录（通用层）隔离；
│  │                            #   目录即注册（非 "_" 开头）；"_模板域"=建域模板（隐藏，可复制改名）
│  ├─ README.md                 #   人工阅读说明（域内个人资料默认不入 git）
│  └─ _模板域/                  #   建域模板：_domain.md 配置模板 + 骨架（复制改名即新域）
├─ agent_registry/
│  ├─ registry.py               # Agent 自动注册器（扫描 agents/*.py 的 AGENT_META）
│  └─ agents/                   # 每个 Agent 一个 py 文件
│     ├─ task_router_agent.py   #   任务路由员：输出 simple/complex
│     ├─ researcher_agent.py    #   调研员：读资料库 Skill + LLM 整理素材
│     ├─ human_review_agent.py  #   人工审阅员：仅 static 引擎（依赖 LangGraph interrupt）
│     ├─ writer_agent.py        #   撰稿员：整合全部字段写文章
│     ├─ critical_reviewer_agent.py  # 批判性审阅员
│     ├─ scientific_thinker_agent.py # 科学思维分析师
│     ├─ humanities_thinker_agent.py # 人文思考者
│     ├─ archivist_agent.py     #   归档员：成稿→LLM提炼要点摘要→写资料库（全文不入库）
│     ├─ collector_agent.py     #  资料采集员：URL/本地文件/文本 → 整理 → 主题归一 → 合并决策 → 入库
│     ├─ memory_advisor_agent.py #  记忆顾问：按主题/显式指定选价值观框架 → 注入 value_profiles
│     ├─ fact_checker_agent.py   #   事实审核员：核查成稿事实/来源/幻觉 → 通过判定（触发修订循环）
│     └─ _agent_template.py     #   Agent 标准模板（复制即用）
├─ planner/
│  ├─ dynamic_planner.py        # 动态规划器（静态方法，含 human_input 断点协议）
│  ├─ plan_renderer.py          # 计划文本渲染
│  ├─ flow_registry.py          # 静态流程自动注册器（扫描 flows/*.py 的 FLOW_META）
│  ├─ static_workflow_director.py  # 静态调度器（多流程按名运行 + 断点恢复）
│  └─ flows/                    # 每个静态流程一个 py 文件
│     ├─ article_generation_flow.py      # 路由→调研→人工断点→写作
│     ├─ quick_article_flow.py           # 路由→调研→写作（快速）
│     ├─ critical_article_flow.py        # 路由→调研→批判→写作
│     ├─ comprehensive_research_flow.py  # 路由→调研→批判→科学→人文→写作
│     ├─ knowledge_archiving_flow.py     # 路由→调研→写作→归档员
│     ├─ material_import_flow.py         # 人审来源断点 → 采集员 → 入库
│     ├─ fact_check_article_flow.py      # 路由→调研→写作→事实审核（有界修订循环）
│     └─ _flow_template.py     #   流程标准模板
├─ skills/                      # Skill 工具层（给 LLM/Agent 调用的标准工具）
│  ├─ skill_registry.py         # Skill 自动注册器（扫描 SKILL_META）
│  ├─ list_topics.py            #   主题库概览（L1：名称+简介+文件数）
│  ├─ read_topic_summary.py     #   主题摘要（L2：摘要+短文件自动含全文）
│  ├─ read_topic_file.py        #   单文件全文（L3：按需）
│  ├─ write_local_database.py   #   写主题库（自动建库/编号/AI摘要索引）
│  ├─ fetch_url_content.py      #   网络 URL 抓取 → 正文提取（requests+bs4）
│  └─ read_local_file.py        #   本地 txt/md 文件读取（大小限制）
├─ memory/                      # 记忆与价值观体系（自动加载，见 §4.6）
│  ├─ memory_registry.py        #   框架注册器 + 选择/注入/维度格式化公共函数
│  ├─ profiles/                 #   价值观框架库（general/policy/technology/humanities/personal_style_demo/cute_style）
│  └─ memories/                 #   长期记忆（user_prefs.md / task_history.md）
├─ tools/                       # 【非 Skill】程序内部功能模块（不被 LLM 调用）
│  ├─ document_output.py        #   打印/保存文章到 output/（生成时间+主题命名）
│  ├─ archive_process.py        #   研究过程封存：计划+各角色产出+最终文章 → archives/（结构化档案）
│  └─ md2docx.py                #   Markdown→Word（md→HTML→docx，纯 pip；PDF 由 Word 另存为）
├─ logs/                        # 日志输出目录（自动生成）
├─ output/                      # 文章输出目录（自动生成，暂不分类）
├─ archives/                    # 研究过程档案目录（自动生成，gitignore，见 §5.5）
├─ LocalDataBase/               # 本地资料库（按主题子目录存放，见 §4.5）
├─ resource_browser/            # 资源浏览器插件（自包含，独立/挂载双入口，见 §5.6）
│  ├─ config.py                 #   三分区写死配置：资产(只读)/档案(可编辑)/日志(只读)
│  ├─ service.py                #   纯逻辑：树/读/写/路径校验/备份（不依赖 Flask）
│  ├─ api.py                    #   Blueprint（/resource-browser 页面 + /api/resources/*）
│  ├─ run.py / __main__.py      #   独立入口（python -m resource_browser，端口5179）
│  └─ static/                   #   三 Tab 单页前端（树+内容+编辑，零依赖）
├─ web_gui/                     # Web 可视化层（独立于核心）
│  ├─ app.py                    #   Flask + API（/api/info /api/task /feedback /cancel）
│  ├─ services/task_manager.py  #   任务状态机 + 后台线程执行器 + 事件流
│  └─ static/                   #   单页前端（SVG 流程图 + 实时日志 + 交互区）
└─ test_*.py                    # 每模块独立测试（全部 mock LLM，不调真实模型）
```

## 3.5 文件注释规范（AI 可读注释体系）

所有核心 py 文件头部使用统一六段式注释（无内容的段可省略）：

```
[模块] 路径 + 一句话定位
[职责] 做什么
[设计思想] 为什么这么做（架构取舍 / 协作闭环）
[关键约定] ★ 不可违反的约束（如：human_input 是协议不是 Agent）
[被谁调用] 影响面（改这里会影响谁）
[修改注意] 改这里必须同步什么
```

- 注释写**意图与边界**（why），不写实现复述（what）
- **改代码必同步注释**：AI 维护时不更新注释视为破坏文档契约
- AGENTS.md=总纲，文件注释=细目，二者索引呼应

## 4. 三大注册体系与接口约定（扩展代码必读）

### 4.1 Agent（放 `agent_registry/agents/`，文件名以 `_` 开头被忽略）
```python
from state_model import State

def run(state: State) -> dict:
    """读 state 所需字段 → 业务逻辑（可调 LLM/Skill）→ 返回要更新的字段"""
    return {"字段名": 值}   # 增量合并进全局 State

AGENT_META = {
    "name": "agent_name",        # 唯一英文名（小写下划线）
    "display_name": "中文职位名",
    "description": "给规划导演（LLM）看的简介，决定何时调用",
    "persona": {"name": "昵称", "tone": "语气", "tags": ["性格标签"]},  # 可选：人设（仅展示，不注入prompt）
    "consumes": ["stance", "evidence"],  # 可选：消费的价值观维度（与框架 values 键对应）
    "tier": "standard",   # ★ 必填：模型档位 router/standard/reasoning（Agent↔档位对应关系写在属性里）
                          #   任务级 model_tier 指定时以任务为准；留空/不写=跟随任务难度映射（仅调研/轻量角色适用，需注释说明）
    "run": run,
    # "engines": ["dynamic", "static"]  # 可选：限定引擎；不写=全部可用
}
```

### 4.2 Skill（放 `skills/`，文件名以 `_` 开头被忽略）
```python
def run(*args, **kwargs):
    """实际功能实现"""
    ...

SKILL_META = {
    "name": "skill_name",
    "description": "【写给 LLM 看】功能说明 + 参数 + 返回值",
    "run": run,
}
```
- Agent 调用方式：`skill_registry.get_run_func("skill_name")(参数)`

### 4.3 静态流程（放 `planner/flows/`，文件名以 `_` 开头被忽略）
```python
def build():
    """组装 LangGraph 图：StateGraph(State) → add_node/add_edge → compile(checkpointer=MemorySaver())"""
    ...

FLOW_META = {"name": "flow_name", "description": "流程说明", "build": build}
```

### 4.4 状态模型（`state_model.py`）
核心字段：`topic`（主题）、`task_level`、`research_material`、`human_supplement`、`final_article`
思考型字段：`critical_review`、`scientific_analysis`、`humanities_perspective`；归档：`archive_result`
事实审核字段：`fact_check_issues`（问题清单）、`fact_check_passed`（通过判定 bool）、`fact_check_count`（审核次数，fact_checker 自增，供有界循环上限判断）
过程记录字段：`exec_plan`（实际执行的计划列表；动态引擎 _execute 写入 plan，静态模式由 task_manager
在 done 时用 `_static_exec_plan` 从 LangGraph 图节点提取节点序列写入，两引擎均入档供封存/回放）
价值观字段：`value_profiles`（list[dict]，任务启动由注入钩子写入）、`advisor_note`、`collect_result`、
`profiles`（显式框架名清单，make_init_state 写入，供 memory_advisor 读取防覆盖）
域字段：`domain`（任务级主题域，None="general"=通用层；make_init_state 注入，全程跟随任务）
模型档位字段：`model_tier`（任务级指定 router/standard/reasoning，空=按难度自动映射；
make_init_state 注入，Agent 经 llm_config.resolve_tier 决策取模型，见 §6 模型档位体系）
`total=False`：运行期允许 Agent 按需新增字段（state 随任务动态更新）
**【静态引擎字段约束】LangGraph 只保留 State 中声明的键，未声明键静默丢弃**（本次真实测试暴露：思考字段曾全部丢失、价值观注入失效）——
所有 Agent 返回的新字段、注入钩子写入的字段必须先在 `state_model.py` 登记，否则静态流程下静默丢失

### 4.6 记忆与价值观体系（`memory/`，自动注册）
- **价值观框架**（`memory/profiles/*.py` 的 `PROFILE_META`）：
  `{name, dimension, category_keywords, description, values}`
  - `dimension="topic"` → 参与关键词自动匹配（keywords 命中主题即选中）；`dimension="style"` → 仅显式加载
  - `values` 可留空 {}：照样注册（占位，可显式指定），但自动匹配自动跳过
  - values 键 = 维度标签：`stance`(立场) / `evidence`(证据) / `style`(风格) / `critique`(批判侧重)，可增删
- **加载优先级**：显式指定（`profiles` 参数，可多个叠加）> 域默认（`_domain.md` 的「默认价值观」，见 §4.5 域配置）> 关键词自动匹配 > 通用默认（general 兜底）；域默认由 make_init_state 在 profiles 为空时用 `default_profiles_for(domain)` 作为显式传入实现
- **注入钩子**：`memory.memory_registry.inject_value_profiles(init_state, explicit)` 在
  main.py / task_manager.make_init_state / StaticWorkflowDirector.run_workflow 三处调用（任务启动自动注入）；
  make_init_state 同时把显式框架名写入 `state["profiles"]`；
  **memory_advisor 防覆盖**：若 value_profiles 已有非 user_prefs 框架（启动已注入）→ 保留不重新自动匹配
  （否则动态计划里的 memory_advisor 会用主题匹配覆盖显式指定的风格，如 cute_style 被 humanities 覆盖——真实用例踩过坑）
- **长期记忆**：`memory/memories/user_prefs.md`（用户偏好，注入时自动附加为 user_prefs 条目）；
  `task_history.md` 沉淀任务记录（`sediment_task_memory`，**纯程序拼接不调 LLM**：时间/主题/域/价值观/引擎/成稿，
  上限 TASK_HISTORY_MAX_LINES=500 行；只沉淀不自动注入防 prompt 膨胀；接入 task_manager._archive_done 与 main.py）
- **维度消费**：Agent 在 `run` 内用 `format_values_for(state["value_profiles"], 本角色维度)` 聚合
  价值观 → 注入自身 prompt；未声明维度自动忽略（如 task_router 不消费）
- **persona（人设）**：AGENT_META.persona = {name,tone,tags}，仅展示/日志用，不注入 prompt（松耦合，
  后续边用边深化）

### 4.5 资料仓库规范（本地知识库，规范常量在 `core/paths.py`）
- **结构**：`LocalDataBase/<主题库>/`；主题库 = 含 `_repo.md` 的子目录（自动注册依据）；
  **主题域**：通用层=根 `LocalDataBase/`（GUI 显示名「公共知识库（跨域共享）」，跨域共享资料），
  域私有=`domains/<域>/LocalDataBase/`（路径一律经
  `local_db_root(domain)` / `output_root(domain)` / `archive_root(domain)` 函数解析，禁止直接拼路径；
  domain=None/"general"=通用层）
- **命名**：主题库与资料文件均 `NN-主题短语`（中英文均可，编号保证排序、人工/AI 可读）；输出文件 `生成时间_主题短语.md`（`tools.document_output.save_article` 的 `fmt` 参数可切 "txt"/"md"，默认 md）
- **`_repo.md`**：仓库自描述 + 文件摘要索引（写入时 AI 提炼一句话，维护在 write 端）
- **注册器 file 字段**：Agent/Skill/流程/价值观注册器加载时自动注入 `file`（相对项目根路径，
  与资源浏览器 assets 区 path 格式一致），/api/info 的 topics 条目含 `path`（通用层指向
  `LocalDataBase/<主题>/_repo.md`，域内指向 `domains/<域>/LocalDataBase/<主题>/_repo.md`）；
  GUI 分类徽章跳转依赖这些字段
- **三级读取**：`list_topics`(L1 概览) → `read_topic_summary`(L2 摘要) → `read_topic_file`(L3 全文)；
  三个读 Skill 均支持 `domain` 参数：list_topics 返回域内+通用合并（标注来源），
  summary/file 先查域内库、未命中回退通用层
- **短文件策略**：文件 ≤ `SHORT_FILE_THRESHOLD`（2000 字符）时，L2 摘要读取直接附全文，减少会话轮次
- **写端契约**：`write_local_database(filename, content, topic, mode, summary, domain=None)` — 自动建库（尊重自带编号，否则自动编号）、自动文件编号、AI 提炼摘要（可传 summary 覆盖）、更新 `_repo.md` 索引；domain=None 写通用层，具体域写域私有库
- **读端策略**：researcher 按「概览→LLM 选主题→摘要→按需全文」执行，token 分级；
  读全部带 `state["domain"]`（域内+通用合并）
- **域配置 `_domain.md`**（可选自描述，与 _repo.md 同构）：`域简介 / 默认价值观 / 风格偏好` 键值行；
  解析与域管理（建域=骨架+模板、重命名=移动目录+保留名校验、统计=list_domains_with_stats）在 `core/domain_config.py`；
  保留域名=general 与 "_" 开头（隐藏）；`domains/_模板域/` 为建域模板（复制改名即新域）

## 5. 双引擎与人在回路（关键机制）

### 5.1 动态引擎（`DynamicPlanner`，全部静态方法）
- `generate_raw_plan(goal, previous_plan=None, user_feedback="")` → LLM 生成/重生成 JSON 计划
- `parse_plan(json_str)` → 容错解析（去 markdown 代码块/杂文本）
- `auto_run` / `human_review_plan_run`（命令行交互）
- `_execute(plan, state, human_input_fn=None)` → 顺序执行，`human_input_fn` 默认为 `input()`

### 5.2 human_input 断点协议（动态引擎执行中断点）
- LLM 计划步骤中可出现 `{"agent": "human_input", "note": "提问内容"}`
- 执行到该步骤：暂停 → 等人工输入 → 写入 `state["human_supplement"]` → 续跑
- **不是真实 Agent**（不在 registry），`_execute` 与 task_manager 内置识别
- 命令行默认 `input()`；GUI 通过 task_manager 暂停/恢复实现异步输入

### 5.2b fact_checker 回溯协议（动态引擎执行中有界循环）
- 计划中出现 `{"agent": "fact_checker", ...}`（真实 Agent，注册于 registry）时执行正常；
  执行后 `_execute` 检查 `state["fact_check_passed"]`：
  - 不通过 且 `fact_check_count < FACT_CHECK_MAX_RETRIES`（2）→ 自动把"最近的 writer 步骤 + 本次 fact_checker 步骤"追加到计划尾部回溯修订
  - 不通过 且已达上限 → 强制通过并记 warning（有界，防死循环）
- 计划中无 writer 步骤时只记录判定不回溯

### 5.3 静态引擎（`StaticWorkflowDirector`）
- `list_flows()` / `build_graph(flow_name)` / `run_workflow(topic, flow_name, thread_id)`（执行到 interrupt 返回 graph,config）/ `resume_workflow(graph, config, resume_value)`
- `human_review` Agent 是 static-only（`engines=["static"]`），其 `run` 里 `interrupt()` 只能在 LangGraph 图内调用
- 有界循环用 LangGraph 条件边实现：`fact_check_article` 流程中 `writer → fact_checker → route_fact_check`（通过或达上限 → END，否则回 writer）

### 5.4 Web GUI 任务状态机（`web_gui/services/task_manager.py`）
```
created → planning → waiting_feedback(动态人审,可反复反馈重生成)
                   → executing → waiting_input(动态 human_input 断点 / 静态 interrupt 断点)
                             → done / failed / cancelled
```
- 事件流：`plan / step_start / agent_done / field_update / waiting / info / error / done`
- 恢复：`resume_input(task, content)` 按模式分发（static→interrupt，dynamic→续跑）
- 所有 done 路径统一走 `_archive_done`（静态无断点/静态恢复/动态完成三处）：
  **① 最终文章 → output/（与 CLI 对齐，GUI 跑完也能拿干净成稿）→ ② 过程封存 archives/ → ③ 长期记忆沉淀**，
  三者失败均仅 info 事件不阻断
- **资料入库也是任务**：`mode="import"`（`_run_import`）——POST /api/import_materials 创建异步任务，
  后台线程逐条经 collector 入库（单条失败隔离记 error 事件继续），左侧任务区实时显示进度
  （流程图=每个来源一个节点「来源N」，事件【来源N】着色）；done 仅 `_log_usage` 统计，
  **不触发** _archive_done（无文章/归档/记忆）；前端 renderResult 对 import 任务 done/failed
  更新资料入库容器提示 + 刷新主题库徽章
- **GUI 布局（Tab 双表单）**：左侧边栏=主题域管理（公共，两 Tab 共用）+ Tab「研究任务/资料入库」切换；
  域输入默认「公共知识库（跨域共享）」=通用层（`selectedDomain()` 归一为空，其余=具体域），
  入库提交时域为空则前端拦截提示（必须显式选择去向）；资料入库表单=目标话题
  （`importTopicSelect`：AI 自动提炼(空)/现有话题(库名)/手动新话题(`__new__`+`importTopicNew`)，
  现有话题按所选域精确过滤 info.topics） + 写入方式 radio（auto/new/merge，默认 auto）
- **资源概览徽章区**（header）：按 Agent/Skill/流程/模型/主题库/价值观 六类分组可点击，
  展开条目列表（名称+描述），点击条目以新标签跳转资源浏览器对应文件
  `#<section>/<path>`（agents/skills/flows/profiles→assets，topics→archives；**models=只读展示
  「档位｜模型名+用途+价格」不跳转不显示密钥**，其 drop 内附「⚙️ 管理模型」按钮打开配置编辑面板）；
  header 另有"📂 资源浏览器"直达链接；跳转依赖各注册器注入的 `file` 字段与 /api/info 的 topics.path
- **模型配置编辑面板**（轻量，`/api/models_config` GET/POST）：只编辑非密钥字段（档位名/模型/base_url/
  用途/能力/价格）+ 运行参数（超时/重试/日志开关/价格兜底）；api_key 只读展示 env 引用名（如
  LLM_API_KEY，值去 .env 改）；保存=core/settings_io.py 块替换 + compile 语法校验 + .bak 备份 +
  llm_config.reset_model_registry() 重载注册表（同进程立即生效，无需重启）；坏输入（空模型/非法档位名/
  坏价格/空列表）拒绝且原文件不动

### 5.4b 三目录职责定位（务必遵守，勿混放）
- **output/ 输出目录** = 最终交付物（干净成稿区，`生成时间_主题.md`）；CLI 与 GUI done 路径都会写
- **archives/ 研究档案** = 研究过程资产（元信息+执行计划+中间产出+最终文章），供追溯/回放/复用；独立于资料库（不入 list_topics）
- **LocalDataBase 资料库** = 研究输入 + 可复用知识片段：放原始/整理资料与**成果要点摘要**；
  **成稿全文不得写入资料库**（archivist 提炼要点入库，防 researcher 把历史成稿误当参考资料读入）

### 5.5 研究过程封存（`tools/archive_process.py`）
- **封存内容**：元信息（引擎/模式/流程/任务等级/价值观框架）+ 执行计划 + 各角色中间产出（素材/审阅/人工补充等，缺失跳过）+ 事实审核结果 + 最终文章全文 → 生成时间_主题.md
- **存放**：`archives/` 独立目录（gitignore，不入主题库体系——避免被 list_topics 当调研资料读入）；与 detail 日志分工：日志=排障（LLM 交互全文），档案=知识沉淀（结构化产出）
- **接入点**：main.py（三模式跑完后）+ task_manager（done 路径）；无 final_article 不落盘（返回 None）
- **用途**：研究过程可追溯/可复用；是 §11"任务历史回放"的地基（回放读 archives/ 即可）

### 5.6 资源浏览器插件（`resource_browser/`，三分区，配置写死）
- **三个分区**（顺序即前端 Tab）：`assets` 资产展示=**只读**（Agent/流程/Skill/工具/价值观/核心框架代码）｜
  `archives` 档案管理=**可编辑**（主题资料库 LocalDataBase/ + 输出库 output/）｜
  `logs` 日志功能=**只读**（logs/ 运行日志 + archives/ 研究档案）
- **配置写死**：`config.py` 的 `RESOURCE_SECTIONS` 直接锁定每分区 roots（目录或单文件）与扩展名白名单；
  **权限为分区级，下级目录自动继承上级权限**；无动态注册表，新增资产类型=加一项配置
- **路径前缀约定**：树条目 path = `"prefix/相对路径"`（prefix 见 config，消除多 root 同名歧义；
  单文件 root 的 path 即文件名）；前端/调用方必须传带前缀的 path
- **安全三关（写）**：分区 readonly 拒绝 → 路径解析后二次校验落在 root 内（防目录穿越）→ 扩展名白名单；
  写入前自动备份 `.bak`（保留最近一版）；roots 白名单天然排除 .env/venv/.git
- **读取**：同样走路径/扩展名校验；单次最大 200_000 字符（`MAX_READ_CHARS`），超长截断并返回 truncated/total
- **树形展示**：tree 返回平铺 dir/file 条目（父目录在前、同级目录先于文件）；前端组装嵌套树，
  顶级 root 目录默认展开、子目录默认收起（点击 ▸/▾ 折叠）；大目录树面板自带滚动条
- **档案编辑交互**：可编辑分区默认只读展示（pre），点击「✏️ 修改」才进入 textarea 编辑
  （保存/取消；保存前自动备份 .bak）；**截断显示的大文件禁止编辑**（防保存丢失后半部分）
- **运行**：独立 `python -m resource_browser`（RES_PORT，默认 5179）；挂载=web_gui/app.py 一行
  `app.register_blueprint(resource_browser)`（页面 /resource-browser）
- **hash 定位协议**：`/resource-browser#<section_key>/<path>` 打开时自动切对应分区、
  在树中定位并打开目标文件（主 GUI 分类徽章即用此跳转）；路径须 URL 编码
- **主题库编辑提示**：档案区编辑非 `_repo.md` 文件时前端提示"摘要索引可能需刷新"

## 6. 日志体系

- **简单日志** `logs/run_*.log`：流程级审计（任务、Agent、工具调用）
- **详细日志** `logs/detail_run_*.log`：+ 与各模型的交互（输入 prompt 全文 / 输出全文）
- **详细日志全局开关**：`manual_settings.DETAIL_LOG_ENABLED=false` 可关闭（完全静默，不落盘不打印），默认 `true`；`.env` 的 `DETAIL_LOG_ENABLED` 可临时覆盖；简单日志不受影响
- 实现：`core/logger.py`（`get_logger` / `get_detail_logger`，后者按开关决定是否挂文件 handler）+ `llm_config.LoggingLLM` 包装（所有 `llm_*.invoke()` 自动记录，零侵入）
- **LLM 超时与重试**：`manual_settings.LLM_TIMEOUT`（秒，默认90）/ `LLM_MAX_RETRIES`（默认1），`.env` 可覆盖；GUI 任务表单可填「LLM超时(秒)」
  任务级覆盖 → task_manager.start 调 `llm_config.configure_llms`（**运行时重建 client**，LLM 无状态零副作用）；
  超时/异常由 LoggingLLM 记 error 并抛出，**不再无限等待**
- **Agent 执行耗时**：dynamic_planner._execute 记录每步耗时（`Agent完成: x, 耗时 Ns`）；
  Agent 抛异常 → 记 error 堆栈并转 RuntimeError（含角色名与原因），main/task_manager 上层转 failed 状态推送前端
- **任务用量统计**：LoggingLLM 从响应 usage_metadata 真实读取 tokens（非估算），thread-local 累计到当前任务
  （GUI 每任务一线程互不串扰；断点恢复用 set_llm_stats 续累计）；**按模型分桶计价**：stats["by_model"]
  键=API 模型名，费用=Σ(每模型 tokens×该模型单价)；单价来源=manual_settings.MODELS 每档 input_price/output_price（旧格式 LLM_MODELS JSON 兼容）
  （元/百万，缺省回退 .env `LLM_PRICE_INPUT`/`LLM_PRICE_OUTPUT` 全局默认）；
  done 时写简单日志一行（含「按模型：m ¥x」明细）+ GUI「📊」事件；CLI main.py 打印任务用量统计
- **模型档位体系（3 档位：router/standard/reasoning，配置在 manual_settings.py 人工/ AI 全局设置）**：
  每个档位一个块（几行，带注释）：model（API 模型名，计价分桶键）/ base_url / api_key（★一律
  os.getenv("LLM_<档位大写>_API_KEY", "占位符") 引用——真实密钥只在 .env，本文件不存秘密，可安全进 git；
  **人工和 AI 都可维护本文件**：改模型/加提供商/调价格/修格式直接改，改完重启生效）/
  role（GUI 下拉用途说明）/ capabilities（能力标签）/ input_price/output_price（元/百万）；
  密钥匹配规则：LLM_<档位大写>_API_KEY（如 LLM_REASONING_API_KEY）优先，省略则用全局 LLM_API_KEY；
  解析优先级：环境变量 LLM_MODELS 旧 JSON（仅测试/临时覆盖）> manual_settings.MODELS（运行时唯一来源）> 旧式两档
  （LLM_MODEL_COMPLEX/SIMPLE→standard/router）；
  - **三层配置职责（各管一层，不重复不冲突）**：① manual_settings.py=档位→模型（基础设施，换模型/加价格/换提供商都在此）；
    ② AGENT_META.tier=Agent→档位（角色默认，新建 Agent 模板强制）；③ GUI 下拉/CLI MODEL_TIER=任务→档位（整单强制，留空=自动）
  - **档位=用途**：router（路由判断/简单问答，最便宜快）/ standard（日常调研/写作/审阅主体）/ reasoning（复杂推理深度分析，仅人工指定）；
    难度(simple/complex)由 task_router 输出，只决定工作深度，经 TIER_MAP 映射到默认档位（simple→router、complex→standard），二者解耦
  - **档位决策链**：任务指定（state.model_tier：GUI 下拉/CLI 环境变量 MODEL_TIER/域默认）> Agent 声明档位
    （AGENT_META.tier，写在 Agent 属性里，新建 Agent 模板强制）> 难度映射（simple→router、complex→standard）> 默认 standard；
    llm_config.resolve_tier(state, agent_tier) 是唯一决策入口（Agent 内 get_llm(resolve_tier(state, AGENT_META.get("tier")))），
    非法档位静默回退下一步；registry 加载对未声明 tier 的 Agent 打 ⚠️ 提醒（researcher 故意不声明=跟随难度映射省 token，已在文件注释说明）
  - base_url/api_key 省略继承全局（manual_settings 每档已用 getenv 引用，.env 里 LLM_API_KEY/LLM_BASE_URL 是全局兜底）；
    role/capabilities 进 GUI 下拉展示；capabilities 只标模型自身能力（text/vision/long_context），**搜索/读库是 Skill 能力，不注册在模型上**
  - **取用唯一入口 get_llm(name)**（惰性缓存）：所有 Agent/Skill/planner 一律经它取模型，禁止直接 new ChatOpenAI；
    换模型=改 manual_settings.MODELS 对应档位 model 行，Agent 零改动；新增档位=MODELS 加一个 key + GUI 下拉自动出现
  - 未配 manual_settings.MODELS 与 LLM_MODELS 回退旧式两档 env（LLM_MODEL_COMPLEX→standard、LLM_MODEL_SIMPLE→router），向后兼容- LLM 调用统一走 `get_llm(...)`，返回对象含 `.content`

## 7. 关键约束与坑（务必遵守）

1. **human_review 只能用静态引擎**：动态引擎规划时已通过 `registry.get_agent_list(engine="dynamic")` 自动排除
2. **human_input 是协议不是 Agent**：不要把它注册成 Agent；动态断点由执行器识别
3. **tools/ 与 skills/ 区别**：skills=给 LLM 调用的注册工具；tools=程序内部功能（不进 LLM 工具清单）。不要混用
4. **不要新增重复 State 定义**：全局只有 `state_model.py` 一个（曾有 `agent_registry/state.py` 冗余已删）
5. **静态流程必须用 `MemorySaver` checkpointer**（interrupt 断点依赖）
6. **资料库读写必须走主题库体系**：不得绕开 list_topics/read_topic_summary/read_topic_file 直接扫目录拼全文（会破坏 token 分级与索引）；写资料必须传 topic 走 write_local_database（维护编号与摘要索引）
7. **venv 已装**：langchain 1.x / langgraph / langchain-openai / python-dotenv / flask
8. **LLM 配置分层**：`manual_settings.py`=模型注册表+运行参数（人工/ AI 都可维护，AI 改模型/加提供商/调价格/修格式都允许，★唯一边界=密钥只放 .env）；`.env`=纯密钥（LLM_API_KEY/LLM_BASE_URL 全局兜底 + LLM_<档位大写>_API_KEY 专属）；日志开关 `DETAIL_LOG_ENABLED`（见 §6）
9. **测试不得调用真实 LLM**：文件顶部 mock 环境变量 + `langchain_openai.ChatOpenAI`；mock LLM 时注意 patch 目标（如 `planner.dynamic_planner.get_llm`、`agent_registry.agents.researcher_agent.get_llm`——Agent 内 get_llm 是绑定名，patch 用 return_value= 返回 fake）
10. **资料采集约定**：来源解析在 collector_agent（URL 判断 / os.path.exists 文件 / 其余按文本；支持逗号换行分隔多来源，**每条来源独立处理**）；获取走 Skill（fetch_url_content / read_local_file，失败返回【提示】开头文本不抛异常）；整理走 LLM（standard 档）；**主题归一**（router 档）：对照 list_topics 概览做同义匹配——主题留空则自动提炼主题短语，显式填了也做归一（除非用户/资料明确要求"独立/分开/新建"），同义 → 复用现有库名并提示；**写入模式 write_mode**（state 传入，GUI 三选一）：auto=AI 自主决策（默认，兼容 CLI/旧调用）、new=强制新建文件（跳过合并决策）、merge=尽量合并（仍由 LLM 选目标文件，无合适文件降级新建）；**合并决策**（router 档）：读目标库 read_topic_summary 摘要，LLM 判定 merge/new，解析失败或目标文件缺失→保守新建；**合并写入**（standard 档）：备份原文件为 `_bak_` 前缀（读端自动忽略）后 原内容+新内容清洗合并覆盖原文件；原文件 > `MERGE_MAX_CHARS`（8000）强制新建（防膨胀）；新建文件名=主题-来源短标签（不同来源自然不同文件）；任何一步失败降级新建，**绝不误覆盖原文件**
11. **价值观注入**：任务启动统一注入（main.py / task_manager / StaticWorkflowDirector 三处钩子），不要在单个 Agent 内自行选择框架；新框架新增到 memory/profiles/ 即自动注册，改选择规则只改 memory_registry
12. **事实审核有界循环**：fact_checker 判定契约=末行【判定】通过/不通过；`fact_check_count` 由 fact_checker 自增；上限常量 `core.paths.FACT_CHECK_MAX_RETRIES`（默认 2，两引擎共用）；静态引擎在 flow 内用条件边循环，动态引擎在 `_execute` 内置回溯分支（均不得改为无限循环）
13. **主题域（domain）约束**：域是**任务参数**（state.domain），任务创建时快照，运行中禁止切域（防多任务串域）；
    路径一律走 `core.paths` 的 `local_db_root/output_root/archive_root` 函数（唯一入口），禁止写死路径或模块级域全局变量；
    list_topics 返回"域内+通用"合并、read 系列"域内优先→通用回退"；写通用层须 domain=None/不传；
    域内与通用层同名主题库**域内优先**；`.gitignore` 排除 `domains/*`（README 与 `_模板域` 例外入库）；
    域管理一律走 `core/domain_config.py`（禁止手写路径拼凑）；GUI 域控件=datalist（可选已有+输入新建），
    新建/重命名调 POST /api/domains，重命名/建域前必须过 is_reserved_domain_name 校验
14. **LLM 超时**：修改超时走 `manual_settings.LLM_TIMEOUT`（默认）/ `.env` 覆盖 / GUI 任务表单，禁止在 Agent 内自行 new ChatOpenAI；
    Agent 异常统一转 RuntimeError（勿静默吞掉，否则卡住无反馈）
14b. **Agent 必须声明档位**：新建 Agent 的 AGENT_META 必须带 `tier`（router/standard/reasoning，模板强制）；
    不声明=跟随任务难度映射（simple→router、complex→standard），仅调研/轻量角色适用并需注释说明；
    决策链=任务指定 > Agent tier > 难度映射 > standard 默认，改动须同步 llm_config.resolve_tier 与 §6
15. **资料入库 API（异步任务）**：`POST /api/import_materials`（body: {topic(库名/新话题名，空=AI 自动提炼),
    domain(空=公共知识库/通用层，具体域=专用域), write_mode(auto|new|merge，默认 auto),
    items:[{type:url|text|file, name, content}]}）
    → 创建 `mode="import"` 任务返回 {task_id, count}，前端轮询 /api/task/<id> 看左侧进度
    （流程图=每来源一节点；逐条经 collector_agent 整理入库，单来源独立防爆 token、单条失败隔离记 error 事件）；
    topic 留空=collector 自动提炼主题并归一（勿再默认"00-默认资料"）；
    GUI 资料入库容器=多 URL textarea + 文件多选/文件夹（webkitdirectory）+ 直接文本，前端读文件内容（单文件≤100KB）；
    GUI 提交流程=域必选（前端拦截空）→ 话题三选一（AI 提炼/现有话题/新话题）→ 写入方式三选一（默认 AI 决策）
16. **三目录职责**（见 §5.4b）：output=最终成稿（GUI/CLI 均写）、archives=过程档案、资料库=输入+成果要点；
    archivist 只写要点摘要不写全文；GUI 任务完成事件含「📄 文章已保存」
17. **用量统计**：LLM 统计生命周期=reset（任务线程入口）→ 累计（LoggingLLM 自动）→ set（断点恢复续累计）→
    汇总（done 写日志+事件）；统计对象建议绑定 task._stats；勿在 Agent 内绕过 LoggingLLM 直调模型（丢日志丢统计）；
    计价按 API 模型名查 manual_settings.MODELS 每档 input/output_price 单价，改价格只改 manual_settings 不碰代码
18. **显式风格**：CLI 用 `$env:PROFILES="cute_style,policy"`；GUI 传 profiles；make_init_state 写入 state["profiles"]
    防 memory_advisor 覆盖；新风格框架=复制 personal_style_demo 模式放 memory/profiles/ 即自动注册
19. **已知坑-修订循环复核不彻底**（2026-09-12 真实用例暴露，待优化）：fact_checker 第一轮抓到
    "管道昇为元初人"的朝代错误并判不通过 → writer 回溯修订时未采纳该修正 → 第二轮 fact_checker 却放行通过；
    即"第二轮通过 ≠ 问题已全部修正"，LLM 审核对同一错误两次判定不一致。
    待改方向（未定）：修订后 fact_checker 必须逐条对照第一轮问题清单确认已改，或 writer 修订时强制
    携带上一轮问题清单。当前仅记录，勿作为已完成能力宣传
17. 历史遗留：`main.py.正确能跑通的_备份`（引用旧 tools.py，已失效，仅存档）；旧平铺资料已迁入 `00-测试资料` 主题库

## 8. 扩展指南

- **新增 Agent**：复制 `_agent_template.py` → 改 run + AGENT_META（**必须含 tier 档位**，可加 persona/consumes）→ 放入 agents/ → 重启即注册；动态规划 LLM 会自动按 description 选用
- **新增 Skill**：复制 read_local_database 模式 → 写 run + SKILL_META（description 必须写给 LLM 看）→ 放入 skills/
- **新增价值观框架**：复制 `memory/profiles/_profile_template.py` → 改 PROFILE_META → 放入 profiles/ → 重启即注册；topic 类填 keywords、style 类留空
- **新增静态流程**：复制 `_flow_template.py` → 定义节点拓扑 build() + FLOW_META → 放入 flows/ → GUI 下拉与 StaticWorkflowDirector 自动可用
- **修改 LLM 调用**：必须经 `llm_config.get_llm(档位)`（保持日志与统计）；新增档位=manual_settings.MODELS 加一个 key（含价格）+ GUI 下拉自动出现，Agent 零改动

## 9. 测试体系（每模块独立测试，全部可离线运行）

| 文件 | 覆盖 |
|---|---|
| `test_agent_system-ok.py` | Agent 注册加载 + 计划渲染 |
| `test_planner_system.py` | 引擎过滤 + 动态计划生成/容错解析 + 静态调度器接口 + _execute 异常捕获/耗时 |
| `test_flow_system.py` | 流程注册 + 全部流程 build 图 |
| `test_skills_system.py` | Skill 注册 + 主题库读写回环（编号/索引/摘要/三级读取）+ 调研员读策略 + 归档员要点摘要入库（全文不入库/失败降级） |
| `test_collector_system.py` | 采集链路：URL 抓取/正文提取（mock）+ 本地读取 + 采集员 本地→整理→主题归一→新建入库 + 同义归一复用现有库 + 合并写入与备份 + 超阈值强制新建 + 写入模式 write_mode（new 强制新建/merge 合并/空库降级）+ 资料入库 API（异步任务：进度事件/write_mode 透传/空来源400/单条失败隔离） |
| `test_memory_system.py` | 价值观框架注册/选择（显式>自动>通用）/注入/维度格式化 + 记忆顾问（含防覆盖）+ 长期记忆沉淀（写入/追加/上限/容错） |
| `test_fact_check_system.py` | 事实审核角色判定 + 静态流程有界循环（修订/上限）+ 动态引擎回溯（修订/上限） |
| `test_archive_system.py` | 过程封存：完整档案/缺失字段跳过/无最终文章不落盘/命名规范 |
| `test_md2docx_system.py` | Markdown→Word：结构保留/自定义输出路径/文件不存在报错 |
| `test_domain_system.py` | 主题域：路径/隔离读写/通用回退/调研员传递/模板隐藏/配置解析/建域重命名/域默认价值观注入 |
| `test_web_gui.py` | 任务状态机：全自动/人审/静态断点/动态断点（done 路径 mock 沉淀与文章保存，不写真实记忆/output） || `test_resource_browser_system.py` | 资源浏览器：分区权限/树遍历/只读拒绝写/写入备份/目录穿越/扩展名白名单/大文件截断 |
| `test_settings_io.py` | 模型配置读写（settings_io）：读解析（env 引用提取/不含密钥）/写回环（改模型价格新增档位）/坏输入拒绝（原文件不动）/备份与注释保留（全部操作临时副本，不碰真实 manual_settings.py） |
| `test_llm_stats.py` | LLM 用量统计：usage 提取/累计/线程隔离/按模型分桶/注册表解析（多提供商/回退）/按模型计价 |

运行：`venv\Scripts\python.exe test_*.py`（逐个）

### 测试文件维护约定（强制）
- **正式测试文件是资产，不得删除**：`test_*.py` 是 AI 维护代码的安全网，任何情况不清理
- **测试逻辑变更 = 新文件整体替换旧文件**：不保留废弃版本、不留新旧并存
- **一次性临时脚本（如 `_tmp_*.py`）用完即删**：只保留正式测试文件在项目中

## 10. 运行方式

```powershell
# 命令行（三模式：动态全自动 / 动态人审 / 静态工作流；可输主题域，回车=通用层）
venv\Scripts\python.exe main.py

# 非交互指定域（跳过命令行询问）
$env:DOMAIN="工作A"; venv\Scripts\python.exe main.py

# Web 可视化（自动开浏览器 http://127.0.0.1:5178）
venv\Scripts\python.exe gui_web.py

# Markdown → Word（指定文件/目录；缺省转换 output/ 全部 md；PDF 用 Word/WPS 另存为）
venv\Scripts\python.exe md2docx.py [文件或目录]

# 资源浏览器（独立模式，默认端口5179；也可在主 GUI 内访问 /resource-browser）
venv\Scripts\python.exe -m resource_browser
```

## 10.5 版本管理（本地 git，main 分支）

- **工作流**：每次功能修改前后 commit（改动前 commit 当前状态 → 修改 → 验证 → commit），AI 维护出错可 revert
- **提交描述（强制）**：每个 commit message 必须写清**改了什么 + 为什么**，按变更点逐条列出（如"新增 X Skill：…"、"修复 Y 缺陷：…"），禁止空泛描述（如"更新代码"）
- **排除规则（.gitignore）**：venv/、__pycache__/、.env（含 API Key 严禁入库）、logs/、output/、LocalDataBase/（个人资料库）、历史备份文件
- 首次提交：`275e255 初始提交`（58 文件 / 4041 行）
- 本地仓库，无远程推送

## 11. 已规划/未完成方向

- 任务历史记录与回放（**地基已就绪**：过程封存 §5.5 已落地，回放读 archives/ 档案即可；task_manager 内存态可加文件持久化）
- 中间过程回合保存、断点重新执行（动态断点已有 _exec_progress，静态依赖 LangGraph 快照，待持久化到磁盘）
- 状态日志与执行痕迹的审计展示
- 轻量关联层（备选，暂不做）：资料量上来后，可在入库时让 LLM 产出"主题/文件关联+关键词+关系标注"（JSON），供 researcher 跨主题导航与 GUI 关系网展示；不引图数据库，真知识图谱（实体抽取/图查询）明确不做
- fact_checker 修订循环复核机制（见 §7 第19条）：修订后逐条对照首轮问题清单确认
