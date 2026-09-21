/*
[模块] web_gui/static/i18n.js — GUI 静态 UI 双语（轻量版：仅静态框架文案，动态日志/alert 保持中文）
[职责] 提供 t(key) 翻译函数 + applyLang() 应用到 HTML + toggleLang() 顶部切换
[设计思想] 轻量版原则：只双语化"用户进页面就看到的静态框架"（标题/按钮/label/tab/placeholder）；
           运行时动态产生的日志、事件消息、alert 提示保持中文（与后端解耦，零改造）
           语言选择存 localStorage('ui_lang')，默认 zh；刷新后记忆
[关键约定] HTML 静态元素加 data-i18n="key"（textContent）/ data-i18n-ph="key"（placeholder）/
           data-i18n-tt="key"（title）；JS 动态生成的静态文案（徽章分类、下拉项）直接调 t(key)
[被谁调用] index.html 在 app.js 之前加载；app.js 的 initBadges / renderModelTiers 等渲染函数
           需在切换语言后重新调用（applyLang 完成后由 toggleLang 触发重渲染）
[修改注意] 新增静态 UI 文案时：① I18N.zh/en 加键 ② HTML 加 data-i18n 或 JS 里 t(key)；
           动态运行时消息（日志/alert）不要进这里，保持后端中文即可
*/
const I18N = {
  zh: {
    "app.title": "🧠 ResearchBase（研库）可视化控制台",
    "app.resourceBrowser": "📂 资源浏览器",
    "app.langToggle": "🌐 EN",
    "domain.title": "主题域管理",
    "domain.hint": "写入/研究域（公共知识库 = 跨域共享资料，所有域可读）",
    "domain.ph": "公共知识库（跨域共享）· 可选已有域或输入新域名",
    "domain.new": "＋ 新建域",
    "domain.rename": "✎ 重命名域",
    "tab.research": "🔬 研究任务",
    "tab.import": "📥 资料入库",
    "research.topic": "研究主题",
    "research.topicPh": "输入研究主题，例如：人工智能发展简史 / 宋代文人的审美趣味 / 远程办公对组织架构的影响",
    "research.mode": "运行模式",
    "research.modeAuto": "动态-全自动",
    "research.modeHuman": "动态-人审计划",
    "research.modeStatic": "静态工作流",
    "research.flow": "静态流程",
    "research.profiles": "价值观框架（可多选，留空=自动匹配）",
    "research.tier": "模型档位（留空=自动：按 Agent 声明档位，未声明者按难度映射）",
    "research.timeout": "LLM 超时（秒，留空=用 .env 默认 90）",
    "research.start": "▶ 开始任务",
    "research.cancel": "⏹ 取消",
    "import.topic": "目标话题（入库去向：AI 提炼 / 选现有话题 / 输入新话题）",
    "import.topicNewPh": "输入新话题名（如：宋代山水画美学）",
    "import.writeMode": "写入方式",
    "import.writeAuto": "🤖 AI 自主决策",
    "import.writeNew": "📄 新建文件",
    "import.writeMerge": "➕ 追加到现有文件",
    "import.urls": "网络来源（URL，每行一个，可多个）",
    "import.urlsPh": "https://...（每行一个 URL，自动抓取正文）",
    "import.files": "本地文件 / 文件夹（支持多选，也可整文件夹）",
    "import.pickFiles": "📄 选择文件",
    "import.pickFolder": "📁 选择文件夹",
    "import.paste": "直接粘贴文本（可选）",
    "import.pastePh": "或把要整理的文本直接粘贴到这里，随上面来源一并入库",
    "import.submit": "📥 整理入库",
    "main.flowTitle": "流程可视化",
    "main.flowPh": "启动任务后显示流程拓扑",
    "main.logTitle": "执行日志",
    "result.title": "最终研究结果",
    "modal.title": "⚙️ 模型配置（manual_settings.py 人工/ AI 全局设置）",
    "modal.hint": "保存时自动语法校验 + 备份 .bak；密钥不在界面中，去 .env 修改。改完立即生效，无需重启。",
    "modal.thTier": "档位名",
    "modal.thModel": "模型名",
    "modal.thBaseUrl": "Base URL（留空=全局）",
    "modal.thRole": "用途",
    "modal.thCaps": "能力",
    "modal.thPriceIn": "输入价",
    "modal.thPriceOut": "输出价",
    "modal.thKey": "密钥引用",
    "modal.add": "＋ 添加档位",
    "modal.tierHint": "档位名（router/standard/reasoning…）是全局契约：Agent 的 tier / 任务下拉都按它工作",
    "modal.runParams": "运行参数",
    "modal.timeout": "LLM 超时（秒）",
    "modal.retries": "重试次数",
    "modal.detail": "详细日志",
    "modal.priceIn": "默认输入价（元/百万）",
    "modal.priceOut": "默认输出价（元/百万）",
    "modal.cancel": "取消",
    "modal.save": "💾 保存配置",
    "badges.agents": "Agent",
    "badges.skills": "Skill",
    "badges.flows": "流程",
    "badges.models": "模型",
    "badges.topics": "主题库",
    "badges.profiles": "价值观",
    "badges.manage": "⚙️ 管理模型",
    "badges.empty": "（空）",
    "models.autoOption": "自动（Agent 档位/难度映射）",
    "graph.generating": "正在生成流程...请稍候",
    "graph.startPlaceholder": "启动任务后显示流程拓扑"
  },
  en: {
    "app.title": "🧠 ResearchBase Console",
    "app.resourceBrowser": "📂 Resource Browser",
    "app.langToggle": "🌐 中文",
    "domain.title": "Domains",
    "domain.hint": "Target domain (public = shared across all domains, readable by everyone)",
    "domain.ph": "Public KB (shared) · pick existing or type a new domain",
    "domain.new": "＋ New domain",
    "domain.rename": "✎ Rename",
    "tab.research": "🔬 Research",
    "tab.import": "📥 Ingest",
    "research.topic": "Research topic",
    "research.topicPh": "Enter a topic, e.g. A brief history of AI / Aesthetic taste of Song literati / Impact of remote work on org structure",
    "research.mode": "Run mode",
    "research.modeAuto": "Dynamic - fully auto",
    "research.modeHuman": "Dynamic - plan review",
    "research.modeStatic": "Static workflow",
    "research.flow": "Static flow",
    "research.profiles": "Value frameworks (multi-select, empty=auto match)",
    "research.tier": "Model tier (empty=auto: agent declared tier, else by difficulty)",
    "research.timeout": "LLM timeout (sec, empty=default 90)",
    "research.start": "▶ Start task",
    "research.cancel": "⏹ Cancel",
    "import.topic": "Target topic (AI extract / pick existing / type new)",
    "import.topicNewPh": "New topic name (e.g. Song landscape aesthetics)",
    "import.writeMode": "Write mode",
    "import.writeAuto": "🤖 AI decides",
    "import.writeNew": "📄 New file",
    "import.writeMerge": "➕ Merge into existing",
    "import.urls": "Web sources (URL, one per line)",
    "import.urlsPh": "https://... (one URL per line, auto-fetch body)",
    "import.files": "Local files / folder (multi-select, or a whole folder)",
    "import.pickFiles": "📄 Pick files",
    "import.pickFolder": "📁 Pick folder",
    "import.paste": "Paste text directly (optional)",
    "import.pastePh": "Or paste text here to ingest along with the sources above",
    "import.submit": "📥 Ingest",
    "main.flowTitle": "Flow Graph",
    "main.flowPh": "Start a task to see the flow topology",
    "main.logTitle": "Execution Log",
    "result.title": "Final Result",
    "modal.title": "⚙️ Model Config (manual_settings.py)",
    "modal.hint": "Auto syntax-check + .bak backup on save. Keys stay in .env (not shown here). Changes take effect immediately.",
    "modal.thTier": "Tier",
    "modal.thModel": "Model",
    "modal.thBaseUrl": "Base URL (empty=global)",
    "modal.thRole": "Role",
    "modal.thCaps": "Caps",
    "modal.thPriceIn": "In price",
    "modal.thPriceOut": "Out price",
    "modal.thKey": "Key ref",
    "modal.add": "＋ Add tier",
    "modal.tierHint": "Tier names (router/standard/reasoning...) are global contracts: agent tier / task dropdown rely on them",
    "modal.runParams": "Runtime params",
    "modal.timeout": "LLM timeout (s)",
    "modal.retries": "Retries",
    "modal.detail": "Detail log",
    "modal.priceIn": "Default input price (per M)",
    "modal.priceOut": "Default output price (per M)",
    "modal.cancel": "Cancel",
    "modal.save": "💾 Save",
    "badges.agents": "Agent",
    "badges.skills": "Skill",
    "badges.flows": "Flows",
    "badges.models": "Models",
    "badges.topics": "Topics",
    "badges.profiles": "Values",
    "badges.manage": "⚙️ Manage models",
    "badges.empty": "(empty)",
    "models.autoOption": "Auto (agent tier / difficulty)",
    "graph.generating": "Generating flow... please wait",
    "graph.startPlaceholder": "Start a task to see the flow topology"
  }
};

let UI_LANG = localStorage.getItem("ui_lang") || "zh";

function t(key) {
  return (I18N[UI_LANG] && I18N[UI_LANG][key]) || I18N.zh[key] || key;
}

function applyLang() {
  document.documentElement.lang = UI_LANG === "zh" ? "zh-CN" : "en";
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.getAttribute("data-i18n");
    el.textContent = t(key);
  });
  document.querySelectorAll("[data-i18n-ph]").forEach(el => {
    const key = el.getAttribute("data-i18n-ph");
    el.placeholder = t(key);
  });
  document.querySelectorAll("[data-i18n-tt]").forEach(el => {
    const key = el.getAttribute("data-i18n-tt");
    el.title = t(key);
  });
  // 语言切换按钮自身文案
  const btn = document.getElementById("langToggle");
  if (btn) btn.textContent = t("app.langToggle");
}

function toggleLang() {
  UI_LANG = UI_LANG === "zh" ? "en" : "zh";
  localStorage.setItem("ui_lang", UI_LANG);
  applyLang();
  // 动态生成的静态文案（徽章/下拉/域统计）需要重新渲染
  if (typeof renderBadges === "function") renderBadges();
  if (typeof fillModelTierSelect === "function") fillModelTierSelect();
  if (typeof renderDomainStats === "function") renderDomainStats();
}
