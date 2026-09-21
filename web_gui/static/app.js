/*
 * [模块] web_gui/static/app.js — 可视化控制台前端逻辑（原生 JS，零依赖）
 * [职责] 单页交互：任务创建、轮询状态、SVG 流程图着色、日志流、人审/断点交互
 * [设计思想] 后端轮询模式（POLL_MS=1500）：Flask 无长连接，前端定时拉取任务状态；
 *            节点状态机 pending/running/done/waiting/failed 由后端事件流推导着色
 * [关键约定] 与后端 API 契约：/api/info、/api/task、/api/task/<id>、
 *            /api/task/<id>/feedback（action: plan_feedback|start|resume）、/cancel；
 *            状态：created/planning/waiting_feedback/executing/waiting_input/done/failed/cancelled
 * [被谁调用] 浏览器加载 index.html 后运行
 * [修改注意] 新增后端动作时同步改 sendFeedback 的分支；事件类型与 task_manager 约定一致
 */
"use strict";

const $ = (id) => document.getElementById(id);
const POLL_MS = 1500;

let info = { agents: [], skills: [], flows: [], profiles: [], domains: [] };
let currentTaskId = null;
let pollTimer = null;
let renderedEventCount = 0;
let nodeStatus = {};   // agentId -> pending/running/done/waiting/failed

/* ---------- 初始化 ---------- */
async function loadInfo() {
  try {
    const res = await fetch("/api/info");
    info = await res.json();
    renderBadges();
    fillFlowSelect();
    fillProfileSelect();
    fillModelTierSelect();
    fillDomainList();
    restoreLastDomain();
    renderDomainStats();
    fillTopicSelect();
    applyLang();
    const importSel = $("importTopicSelect");
    if (importSel) importSel.addEventListener("change", syncImportTopicInput);
  } catch (e) {
    $("badges").innerHTML = '<span class="badge">后端未连接</span>';
  }
}

function renderBadges() {
  // 分类概览：每类一个可点击徽章 → 展开条目列表（Agent/Skill/流程/主题库/价值观可跳资源浏览器；
  // 模型=只读展示配置（档位|模型名+用途+价格），不含密钥、不跳转——配置在 manual_settings.py 人工维护）
  const cats = [
    { key: "agents",   label: "Agent",   section: "assets",   icon: "🤖" },
    { key: "skills",   label: "Skill",   section: "assets",   icon: "🔧" },
    { key: "flows",    label: t("badges.flows"),     section: "assets",   icon: "🔄" },
    { key: "models",   label: t("badges.models"),     section: null,       icon: "🧠" },
    { key: "topics",   label: t("badges.topics"),   section: "archives", icon: "🗂" },
    { key: "profiles", label: t("badges.profiles"),   section: "assets",   icon: "🧭" },
  ];
  const box = $("badges");
  box.innerHTML = cats.map(c => {
    const list = info[c.key] || [];
    return `<div class="cat-wrap">
      <button class="badge cat-btn" data-key="${c.key}">${c.icon} ${c.label}(${list.length}) ▾</button>
      <div class="cat-drop" id="drop-${c.key}" style="display:none">
        ${list.map(item => {
          if (c.key === "models") {
            // 模型：只读展示（档位｜模型名 + 用途 + 价格），不跳转、不显示密钥
            const price = (item.input_price != null) ? `¥${item.input_price}/${item.output_price} 每百万` : "";
            return `<div class="cat-item" title="${escapeHtml(item.role || "")}">
                      <span class="ci-name">${escapeHtml(item.name)}｜${escapeHtml(item.model)}</span>
                      <span class="ci-sub">${escapeHtml(item.role || "")}${price ? " · " + price : ""}</span>
                    </div>`;
          }
          const path = item.file || item.path;
          const subRaw = item.desc || item.display_name || item.dimension || "";
          const sub = subRaw + (item.domain ? ` · 域:${item.domain}` : "");
          const dimTag = item.dimension === "style" ? "·风格" : (item.has_values === false ? "·空占位" : "");
          const tierTag = (c.key === "agents" && item.tier) ? ` · <b>档位:${escapeHtml(item.tier)}</b>` : "";
          return `<a class="cat-item" href="/resource-browser#${c.section}/${encodeURIComponent(path)}"
                    target="_blank" title="${escapeHtml(sub)}">
                    <span class="ci-name">${escapeHtml(item.name)}</span>
                    <span class="ci-sub">${escapeHtml(shorten(sub, 24))}${dimTag}${tierTag}</span>
                  </a>`;
        }).join("") || ('<div class="cat-item empty">' + t("badges.empty") + '</div>')}
        ${c.key === "models" ? `<div class="cat-item manage-models"><button class="badge" onclick="openModelsModal()">${t("badges.manage")}</button></div>` : ""}
      </div>
    </div>`;
  }).join("");
  // 点击徽章切换展开/收起；点击空白处收起全部
  box.querySelectorAll(".cat-btn").forEach(btn =>
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const key = btn.dataset.key;
      const drop = $("drop-" + key);
      const isOpen = drop.style.display === "block";
      box.querySelectorAll(".cat-drop").forEach(d => d.style.display = "none");
      drop.style.display = isOpen ? "none" : "block";
    }));
  document.addEventListener("click", () => {
    box.querySelectorAll(".cat-drop").forEach(d => d.style.display = "none");
  });
}

function fillFlowSelect() {
  const sel = $("flowSelect");
  // 研究任务 Tab 只显示研究类流程；material_import（资料入库）不在这里出现（资料入库 Tab 自己处理）
  const researchFlows = (info.flows || []).filter(f => f.name !== "material_import");
  sel.innerHTML = researchFlows.map(f => `<option value="${f.name}">${f.name} — ${f.desc}</option>`).join("");
}

function fillProfileSelect() {
  const box = $("profileChecklist");
  const profiles = info.profiles || [];
  // 第一个固定项：自动匹配（默认勾选；勾选时忽略其他选择）
  let html = `<label class="checkbox-item">
    <input type="checkbox" id="profileAuto" checked>
    <span>🤖 自动匹配（默认，按主题关键词选最合适的框架）</span>
  </label>`;
  html += profiles.map(p =>
    `<label class="checkbox-item">
      <input type="checkbox" class="profile-opt" value="${p.name}">
      <span>${p.name}${p.has_values ? "" : "（空占位）"}${p.dimension === "style" ? "·风格" : "·主题"} — ${escapeHtml(p.desc || "")}</span>
    </label>`
  ).join("");
  box.innerHTML = html;
  // 勾"自动匹配"时取消其他；勾具体框架时取消"自动匹配"
  $("profileAuto").addEventListener("change", function() {
    if (this.checked) {
      box.querySelectorAll(".profile-opt").forEach(c => c.checked = false);
    }
  });
  box.querySelectorAll(".profile-opt").forEach(cb => {
    cb.addEventListener("change", function() {
      if (this.checked) $("profileAuto").checked = false;
      // 如果全取消，自动勾回"自动匹配"
      const anyChecked = Array.from(box.querySelectorAll(".profile-opt")).some(c => c.checked);
      if (!anyChecked) $("profileAuto").checked = true;
    });
  });
}

function selectedProfiles() {
  // 勾"自动匹配"=返回空数组（后端自动匹配）；否则返回勾选的具体框架名
  if ($("profileAuto").checked) return [];
  return Array.from(document.querySelectorAll(".profile-opt:checked")).map(c => c.value);
}

function fillModelTierSelect() {
  // 模型档位下拉：空选项=自动（按难度映射）；每档显示「档位｜模型名 — 用途（价格）」
  const sel = $("modelTierSelect");
  sel.title = "档位决策链：任务指定 > Agent 声明档位 > 难度自动映射 > 默认 standard。留空=自动：各 Agent 用自己的声明档位（如路由员=router、撰稿=standard），未声明的按任务难度（简单→router、复杂→standard）";
  const models = info.models || [];
  const options = ['<option value="">' + t("models.autoOption") + '</option>']
    .concat(models.map(m =>
      `<option value="${m.name}">${m.name}｜${escapeHtml(m.model)} — ${escapeHtml(m.role || "")}（¥${m.input_price}/${m.output_price} 每百万）</option>`
    ));
  sel.innerHTML = options.join("");
}

/* ---------- 主题域：datalist（可选已有 + 输入新建）+ 新建/重命名 + 记住上次 ---------- */
const DOMAIN_STORAGE_KEY = "researchbase_last_domain";

function fillDomainList() {
  const dl = $("domainList");
  if (!dl) return;
  dl.innerHTML = "";
  // 第一项：公共知识库（跨域共享）= 通用层；value 用特殊标记，selectedDomain() 归一为空
  const opt0 = document.createElement("option");
  opt0.value = "公共知识库（跨域共享）";
  dl.appendChild(opt0);
  (info.domains || []).forEach(d => {
    if (!d) return;  // 通用层由第一项表达
    const opt = document.createElement("option");
    opt.value = d;
    dl.appendChild(opt);
  });
}

const PUBLIC_KB_LABEL = "公共知识库（跨域共享）";

function selectedDomain() {
  // 归一：公共知识库（跨域共享）= 通用层（空）；其余原样返回（具体域）
  const v = ($("domainInput") ? $("domainInput").value : "").trim();
  return v === PUBLIC_KB_LABEL ? "" : v;
}

function restoreLastDomain() {
  const last = localStorage.getItem(DOMAIN_STORAGE_KEY);
  if (!last || last === PUBLIC_KB_LABEL) {
    $("domainInput").value = PUBLIC_KB_LABEL;  // 首次/无记忆：默认公共知识库（跨域共享，显式可见）
    return;
  }
  const known = new Set((info.domains || []).filter(Boolean));
  if (known.has(last)) $("domainInput").value = last;  // 仅回填仍存在的域
  else $("domainInput").value = PUBLIC_KB_LABEL;
}

function rememberDomain() {
  const d = selectedDomain();
  if (d) localStorage.setItem(DOMAIN_STORAGE_KEY, d);
}

function renderDomainStats() {
  const el = $("domainStats");
  if (!el) return;
  const stats = info.domain_stats || {};
  const parts = [];
  const general = stats.general || {};
  parts.push(`公共知识库(${general.topics || 0}库/${general.files || 0}文)`);
  (info.domains || []).forEach(d => {
    if (!d) return;
    const s = stats[d] || {};
    parts.push(`${d}(${s.topics || 0}库/${s.files || 0}文)`);
  });
  el.textContent = "域概览：" + parts.join(" · ");
}

async function apiDomain(action, payload) {
  const res = await fetch(action, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}

function bindDomainActions() {
  const btnNew = $("btnNewDomain");
  const btnRename = $("btnRenameDomain");
  if (btnNew) btnNew.addEventListener("click", async () => {
    const name = selectedDomain();
    if (!name) { alert("请先在输入框输入新域名"); return; }
    const data = await apiDomain("/api/domains", { name, intro: "" });
    alert(data.message || (data.ok ? "创建成功" : "创建失败"));
    if (data.ok) {
      await loadInfo();
      $("domainInput").value = name;
      rememberDomain();
    }
  });
  if (btnRename) btnRename.addEventListener("click", async () => {
    const old = selectedDomain();
    if (!old) { alert("请先选择（输入）要重命名的域"); return; }
    const known = new Set((info.domains || []).filter(Boolean));
    if (!known.has(old)) { alert("只能重命名已有域（模板域/通用层不可重命名）"); return; }
    const next = prompt(`将域「${old}」重命名为：`, old);
    if (!next || next === old) return;
    const data = await apiDomain(`/api/domains/${encodeURIComponent(old)}/rename`, { new_name: next });
    alert(data.message || (data.ok ? "重命名成功" : "重命名失败"));
    if (data.ok) {
      await loadInfo();
      $("domainInput").value = next;
      rememberDomain();
    }
  });
  // 记住上次用的域 + 刷新资料入库话题下拉（随域联动）
  const input = $("domainInput");
  if (input) input.addEventListener("change", () => { rememberDomain(); fillTopicSelect(); });

  // ---- combobox：点 ▾ 展开全部域列表（datalist 只做输入联想，不承担"看全部"） ----
  const ddBtn = $("domainDropdownBtn");
  const ddBox = $("domainDropdown");
  function renderDomainDropdown() {
    if (!ddBox) return;
    const items = [PUBLIC_KB_LABEL].concat((info.domains || []).filter(Boolean));
    const cur = input ? input.value : "";
    ddBox.innerHTML = items.map(name =>
      `<div class="dd-item${name === cur ? " selected" : ""}" data-val="${escapeHtml(name)}">${escapeHtml(name)}</div>`
    ).join("");
    ddBox.querySelectorAll(".dd-item").forEach(el => {
      el.addEventListener("mousedown", (e) => {
        e.preventDefault();  // 防止 input 失焦
        if (input) input.value = el.dataset.val;
        hideDropdown();
        rememberDomain();
        fillTopicSelect();
      });
    });
  }
  function showDropdown() { renderDomainDropdown(); ddBox.style.display = "block"; }
  function hideDropdown() { if (ddBox) ddBox.style.display = "none"; }
  if (ddBtn) ddBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    if (ddBox.style.display === "block") hideDropdown(); else showDropdown();
  });
  if (input) {
    input.addEventListener("focus", hideDropdown);   // 聚焦走 datalist 联想
    input.addEventListener("input", hideDropdown);
  }
  document.addEventListener("click", (e) => {
    if (ddBox && ddBox.style.display === "block" &&
        !ddBox.contains(e.target) && e.target !== ddBtn) hideDropdown();
  });
}

bindDomainActions();

/* ---------- Tab 切换（研究任务 / 资料入库，共用上方域选择） ---------- */
function bindTabs() {
  document.querySelectorAll(".tab-btn").forEach(btn =>
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      const pane = $("pane-" + btn.dataset.tab);
      if (pane) pane.classList.add("active");
    }));
}

/* ---------- 资料入库：话题选择（AI提炼/现有话题/新话题，随域联动） ---------- */
function fillTopicSelect() {
  const sel = $("importTopicSelect");
  if (!sel) return;
  const domain = selectedDomain();
  const prev = sel.value;
  sel.innerHTML = "";
  const optAi = document.createElement("option");
  optAi.value = "";
  optAi.textContent = "🤖 AI 自动提炼（默认，自动匹配现有话题防碎片化）";
  sel.appendChild(optAi);
  const optNew = document.createElement("option");
  optNew.value = "__new__";
  optNew.textContent = "✍️ 手动输入新话题…";
  sel.appendChild(optNew);
  // 该域现有话题（info.topics 按 domain 精确匹配：具体域=仅域内，公共知识库=domain 空）
  const existing = (info.topics || []).filter(t => (domain ? t.domain === domain : !t.domain));
  [...new Set(existing.map(t => t.name))].sort().forEach(name => {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = "📂 " + name;
    sel.appendChild(opt);
  });
  if (prev && [...sel.options].some(o => o.value === prev)) sel.value = prev;  // 尽量保留用户选择
  syncImportTopicInput();
}

function syncImportTopicInput() {
  const sel = $("importTopicSelect");
  const input = $("importTopicNew");
  if (!sel || !input) return;
  input.style.display = sel.value === "__new__" ? "block" : "none";
}

bindTabs();

function agentLabel(id) {
  const a = info.agents.find(x => x.name === id);
  return a ? (a.display_name || a.name) : id;
}

/* ---------- 模式切换 ---------- */
document.querySelectorAll('input[name="mode"]').forEach(r => {
  r.addEventListener("change", () => {
    const isStatic = document.querySelector('input[name="mode"]:checked').value === "static";
    $("flowSelect").style.display = isStatic ? "block" : "none";
    $("flowLabel").style.display = isStatic ? "block" : "none";
  });
});

/* ---------- 任务控制 ---------- */
function showTask(taskId) {
  // 通用：把任意任务（研究任务 / 资料入库任务）接入左侧任务区展示与轮询
  currentTaskId = taskId;
  renderedEventCount = 0;
  nodeStatus = {};
  $("result").style.display = "none";
  $("interact").style.display = "none";
  _lastInteractKey = null;
  $("logBox").innerHTML = "";
  $("graphBox").innerHTML = '<div class="placeholder">' + t("graph.generating") + '</div>';
  $("btnStart").disabled = true;
  $("btnCancel").disabled = false;
  $("taskMeta").textContent = `任务ID：${currentTaskId}`;
  startPolling();
}

async function startTask() {
  const topic = $("topic").value.trim();
  if (!topic) { alert("请输入研究主题"); return; }
  const mode = document.querySelector('input[name="mode"]:checked').value;
  const flow_name = mode === "static" ? $("flowSelect").value : "";

  const res = await fetch("/api/task", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      topic, mode, flow_name,
      profiles: selectedProfiles(),
      domain: selectedDomain(),
      model_tier: $("modelTierSelect").value || null,  // 模型档位（留空=按难度自动映射）
      timeout: $("llmTimeout").value ? Number($("llmTimeout").value) : null,
      auto_archive: $("autoArchive").checked,  // 跑完自动归档要点到资料库
    }),
  });
  const data = await res.json();
  if (!data.ok) { alert(data.error || "启动失败"); return; }
  showTask(data.task_id);
}

async function cancelTask() {
  if (!currentTaskId) return;
  await fetch(`/api/task/${currentTaskId}/cancel`, { method: "POST" });
}

async function archiveArticle(taskId, btn) {
  btn.disabled = true;
  btn.textContent = "📥 归档中（多一次 LLM 调用）...";
  try {
    const res = await fetch(`/api/task/${taskId}/archive`, { method: "POST" });
    const data = await res.json();
    $("archiveMsg").textContent = data.ok ? (" ✅ " + data.message) : (" ❌ " + (data.error || "失败"));
    if (data.ok) btn.textContent = "✅ 已归档";
    else btn.textContent = "📥 保存要点到资料库";
  } catch (e) {
    $("archiveMsg").textContent = " ❌ 请求失败：" + e;
    btn.textContent = "📥 保存要点到资料库";
    btn.disabled = false;
  }
}

$("btnStart").addEventListener("click", startTask);
$("btnCancel").addEventListener("click", cancelTask);

/* ---------- 资料入库（多 URL / 多文件 / 文件夹 / 直接文本） ---------- */
let importFiles = [];                 // {name, content, skipped?}
const IMPORT_MAX_BYTES = 100000;      // 单文件超过 100KB 跳过（collector 整理上限约 8000 字符）
const IMPORT_TEXT_EXTS = [".txt", ".md", ".text"];  // 仅支持文本格式（docx/pdf 等二进制读成乱码，直接拦截提示）

function readFilesAsText(fileList) {
  const files = Array.from(fileList || []);
  return Promise.all(files.map(f => new Promise(resolve => {
    const dot = f.name.lastIndexOf(".");
    const ext = dot > 0 ? f.name.slice(dot + 1).toLowerCase() : "";  // 无扩展名→空，按文本尝试读取
    if (ext && !IMPORT_TEXT_EXTS.includes("." + ext)) {
      resolve({ name: f.name, skipped: `非文本格式（仅支持 ${IMPORT_TEXT_EXTS.join("/")}），请转成文本或直接粘贴内容` });
      return;
    }
    if (f.size > IMPORT_MAX_BYTES) {
      resolve({ name: f.name, skipped: `超 ${Math.round(IMPORT_MAX_BYTES / 1024)}KB 已跳过` });
      return;
    }
    const reader = new FileReader();
    reader.onload = () => resolve({ name: f.name, content: String(reader.result || "") });
    reader.onerror = () => resolve({ name: f.name, skipped: "读取失败" });
    reader.readAsText(f);
  })));
}

function renderImportList() {
  const el = $("importFileList");
  if (!el) return;
  const ok = importFiles.filter(f => !f.skipped);
  const bad = importFiles.filter(f => f.skipped);
  el.textContent = [
    ok.length ? `已选 ${ok.length} 个文件：` + ok.map(f => f.name).join("、") : "",
    bad.length ? bad.map(f => `${f.name}（${f.skipped}）`).join("、") : "",
  ].filter(Boolean).join("；") || "";
}

function bindImportActions() {
  const pickFiles = $("btnPickFiles"), pickFolder = $("btnPickFolder");
  if (pickFiles) pickFiles.addEventListener("click", () => $("importFiles").click());
  if (pickFolder) pickFolder.addEventListener("click", () => $("importFolder").click());
  ["importFiles", "importFolder"].forEach(id => {
    const input = $(id);
    if (!input) return;
    input.addEventListener("change", async e => {
      const loaded = await readFilesAsText(e.target.files);
      importFiles = importFiles.filter(f => !f.skipped).concat(loaded);
      renderImportList();
      e.target.value = "";  // 允许重复选同一文件
    });
  });
  const btnImport = $("btnImport");
  if (btnImport) btnImport.addEventListener("click", importMaterials);
  const btnNewTopic = $("btnNewTopic");
  if (btnNewTopic) btnNewTopic.addEventListener("click", createTopic);
}

async function createTopic() {
  const name = prompt("输入新话题名（中英文均可，如：宋代山水画美学）：");
  if (!name || !name.trim()) return;
  const domain = selectedDomain();  // 空=公共知识库
  try {
    const res = await fetch("/api/topics", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic: name.trim(), domain }),
    });
    const data = await res.json();
    if (data.ok) {
      alert("✅ " + data.message);
      loadInfo();  // 刷新主题库徽章和话题下拉
    } else {
      alert("❌ " + (data.error || "失败"));
    }
  } catch (e) {
    alert("❌ 请求失败：" + e);
  }
}

async function importMaterials() {
  // 域必选校验：公共知识库（跨域共享）或某专用域，二选一显式指定
  const domain = selectedDomain();
  const domainRaw = $("domainInput").value.trim();
  if (!domainRaw) { alert("请先选择入库目标域：公共知识库（跨域共享）或某专用域（左侧顶部）"); return; }
  // 话题组装：AI 自动提炼（空）/ 现有话题（库名）/ 手动新话题（输入框值）
  const topicMode = $("importTopicSelect").value;
  let topic = "";
  if (topicMode === "__new__") {
    topic = $("importTopicNew").value.trim();
    if (!topic) { alert("请填写新话题名"); return; }
  } else {
    topic = topicMode;  // "" = AI 自动提炼；其余 = 现有话题库名
  }
  const writeMode = document.querySelector('input[name="writeMode"]:checked').value;
  const urls = $("importUrls").value.split("\n").map(s => s.trim()).filter(Boolean);
  const text = $("importText").value.trim();
  const files = importFiles.filter(f => !f.skipped && f.content);
  if (!urls.length && !text && !files.length) { alert("请至少提供 URL / 文本 / 文件之一"); return; }
  const items = [];
  urls.forEach(u => items.push({ type: "url", name: u, content: u }));
  if (text) items.push({ type: "text", name: "直接文本", content: text });
  files.forEach(f => items.push({ type: "file", name: f.name, content: f.content }));

  const btnImport = $("btnImport");
  btnImport.disabled = true;
  const dest = domainRaw === PUBLIC_KB_LABEL ? "公共知识库（跨域共享）" : `域「${domainRaw}」`;
  $("importResult").textContent = `已提交入库任务（写入 ${dest}），进度展示在左侧任务流程区...`;
  try {
    const res = await fetch("/api/import_materials", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic, domain, write_mode: writeMode, items }),
    });
    const data = await res.json();
    if (!data.ok) { $("importResult").textContent = "入库失败：" + (data.error || ""); return; }
    // 接入左侧任务流程区（流程图=每个来源一个节点，日志实时滚动）
    showTask(data.task_id);
    $("importResult").textContent = `✅ 已提交 ${data.count} 个来源入库 → ${dest}（话题：${topic || "AI 自动提炼"}｜方式：${writeMode === "auto" ? "AI 决策" : writeMode === "new" ? "新建文件" : "追加合并"}），进度见左侧任务流程区`;
    importFiles = [];
    renderImportList();
    $("importUrls").value = "";
    $("importText").value = "";
  } catch (err) {
    $("importResult").textContent = "入库请求失败：" + err;
  } finally {
    btnImport.disabled = false;
  }
}

bindImportActions();

/* ---------- 轮询 ---------- */
function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(poll, POLL_MS);
  poll();
}

async function poll() {
  if (!currentTaskId) return;
  const res = await fetch(`/api/task/${currentTaskId}`);
  const data = await res.json();
  if (!data.ok) return;
  const task = data.task;

  renderLog(task.events);
  renderGraph(task.graph, task);
  renderInteract(task);
  renderResult(task);

  if (["done", "failed", "cancelled"].includes(task.status)) {
    clearInterval(pollTimer);
    pollTimer = null;
    $("btnStart").disabled = false;
    $("btnCancel").disabled = true;
  }
}

/* ---------- 日志 ---------- */
function renderLog(events) {
  const box = $("logBox");
  for (let i = renderedEventCount; i < events.length; i++) {
    const ev = events[i];
    const cls = ev.type === "error" ? "log-error"
      : ev.type === "plan" ? "log-plan"
      : ev.type === "step_start" ? "log-step"
      : ev.type === "done" ? "log-done"
      : ev.type === "waiting" ? "log-wait"
      : ev.type === "info" ? "log-info" : "";
    const div = document.createElement("div");
    div.className = "log-line " + cls;
    div.innerHTML = `<span class="ts">${ev.ts}</span>${escapeHtml(ev.content)}`;
    box.appendChild(div);
  }
  renderedEventCount = events.length;
  box.scrollTop = box.scrollHeight;
}

/* ---------- 流程图（SVG） ---------- */
function computeNodeStatus(task) {
  // 依据事件流推导节点状态
  const st = {};
  task.events.forEach(ev => {
    if (ev.type === "step_start") {
      const m = ev.content.match(/【(.+?)】/);
      if (m) st[m[1]] = "running";
    } else if (ev.type === "agent_done") {
      const m = ev.content.match(/【(.+?)】/);
      if (m) st[m[1]] = "done";
    } else if (ev.type === "error") {
      const m = ev.content.match(/【(.+?)】/);
      if (m) st[m[1]] = "failed";
    }
  });
  if (task.status === "waiting_input") {
    // 标记最后一个 running 为 waiting
    for (const k in st) if (st[k] === "running") st[k] = "waiting";
  }
  if (task.status === "waiting_feedback") {
    for (const k in st) if (st[k] === "running") st[k] = "waiting";
  }
  return st;
}

function renderGraph(graph, task) {
  const box = $("graphBox");
  if (!graph || !graph.nodes || !graph.nodes.length) return;
  nodeStatus = computeNodeStatus(task);

  // 计算层（拓扑分层）
  const nodeSet = new Set(graph.nodes.map(n => n.id));
  const edges = graph.edges.filter(e => nodeSet.has(e.source) && nodeSet.has(e.target));
  const layer = {};
  const indeg = {};
  graph.nodes.forEach(n => { layer[n.id] = 0; indeg[n.id] = 0; });
  edges.forEach(e => { indeg[e.target]++; });

  let changed = true;
  while (changed) {
    changed = false;
    edges.forEach(e => {
      if (layer[e.target] < layer[e.source] + 1) {
        layer[e.target] = layer[e.source] + 1;
        changed = true;
      }
    });
  }

  const byLayer = {};
  graph.nodes.forEach(n => {
    (byLayer[layer[n.id]] = byLayer[layer[n.id]] || []).push(n.id);
  });
  const maxLayer = Math.max(0, ...Object.keys(byLayer).map(Number));

  const NODE_W = 150, NODE_H = 54, GAP_X = 70, GAP_Y = 36;
  const MARGIN = 30;
  const width = MARGIN * 2 + (maxLayer + 1) * NODE_W + maxLayer * GAP_X;
  let maxNodesInLayer = 1;
  Object.values(byLayer).forEach(arr => { maxNodesInLayer = Math.max(maxNodesInLayer, arr.length); });
  const height = Math.max(180, MARGIN * 2 + maxNodesInLayer * NODE_H + (maxNodesInLayer - 1) * GAP_Y);

  const pos = {};
  Object.entries(byLayer).forEach(([l, ids]) => {
    const x = MARGIN + Number(l) * (NODE_W + GAP_X);
    const totalH = ids.length * NODE_H + (ids.length - 1) * GAP_Y;
    let y = (height - totalH) / 2;
    ids.forEach(id => { pos[id] = { x, y: y, w: NODE_W, h: NODE_H }; y += NODE_H + GAP_Y; });
  });

  let svg = `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`;

  // 边
  edges.forEach(e => {
    const s = pos[e.source], t = pos[e.target];
    const x1 = s.x + s.w, y1 = s.y + s.h / 2;
    const x2 = t.x, y2 = t.y + t.h / 2;
    const mx = (x1 + x2) / 2;
    svg += `<path class="edge" d="M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}"/>`;
    // 箭头
    svg += `<path class="edge" d="M ${x2 - 6} ${y2 - 5} L ${x2} ${y2} L ${x2 - 6} ${y2 + 5}"/>`;
  });

  // 节点
  graph.nodes.forEach(n => {
    const p = pos[n.id];
    const st = nodeStatus[n.id] || "pending";
    const label = agentLabel(n.id);
    const note = n.note || "";
    const cy = p.y + p.h / 2;
    svg += `<g class="node state-${st}">
      <rect x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}"/>
      <text x="${p.x + p.w / 2}" y="${note ? cy - 6 : cy + 4}">${escapeHtml(label)}</text>
      ${note ? `<text class="note" x="${p.x + p.w / 2}" y="${cy + 14}">${escapeHtml(shorten(note, 12))}</text>` : ""}
    </g>`;
  });

  svg += "</svg>";
  box.innerHTML = svg;
}

function shorten(s, n) { return s.length > n ? s.slice(0, n) + "…" : s; }

/* ---------- 交互区 ---------- */
// 状态记忆：同状态不重建 innerHTML（否则轮询会把正在打字的 textarea 重建，焦点丢失+内容清空）
let _lastInteractKey = null;

function renderInteract(task) {
  const box = $("interact");
  if (task.status === "waiting_feedback") {
    const planHtml = (task.plan || []).map((s, i) =>
      `<div class="plan-list"><b>步骤${i + 1}</b>｜${agentLabel(s.agent)}｜${escapeHtml(s.note || "")}</div>`).join("");
    const key = "feedback|" + (task.plan || []).map(s => s.agent + s.note).join("|");
    box.style.display = "block";
    if (key !== _lastInteractKey) {
      box.innerHTML = `
        <h3>✏️ 人工审阅任务计划（动态规划-人审模式）</h3>
        <div>当前计划：</div>${planHtml}
        <label>修改意见（提交后返回 LLM 重新生成计划）</label>
        <textarea id="feedbackText" placeholder="例如：增加批判性审阅环节，先调研再写作，压缩为3个步骤"></textarea>
        <div class="actions">
          <button class="primary" id="btnFeedback">🔄 重新生成计划</button>
          <button id="btnExecPlan">▶ 按当前计划执行</button>
        </div>`;
      $("btnFeedback").addEventListener("click", () => sendFeedback("plan_feedback"));
      $("btnExecPlan").addEventListener("click", () => sendFeedback("start"));
      _lastInteractKey = key;
    }
  } else if (task.status === "waiting_input") {
    const waitEv = [...task.events].reverse().find(e => e.type === "waiting");
    const hint = waitEv ? waitEv.content : "流程暂停，等待人工输入";
    const key = "input|" + hint;
    box.style.display = "block";
    if (key !== _lastInteractKey) {
      box.innerHTML = `
        <h3>⏸ 流程暂停：等待人工输入</h3>
        <p style="font-size:13px;color:#6b7280">${escapeHtml(hint)}</p>
        <textarea id="resumeText" placeholder="补充信息或修改意见（无补充输入【无】）"></textarea>
        <div class="actions"><button class="primary" id="btnResume">▶ 提交并继续</button></div>`;
      $("btnResume").addEventListener("click", () => sendFeedback("resume"));
      _lastInteractKey = key;
    }
  } else {
    box.style.display = "none";
    _lastInteractKey = null;  // 下次重新进入时重建
  }
}

async function sendFeedback(action) {
  const content = action === "resume" ? $("resumeText").value
    : action === "plan_feedback" ? $("feedbackText").value : "";
  if (action !== "start" && !content.trim()) { alert("请输入内容"); return; }
  const res = await fetch(`/api/task/${currentTaskId}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, content }),
  });
  const data = await res.json();
  if (!data.ok) { alert(data.message || "操作失败"); return; }
  renderedEventCount = 0;
  $("logBox").innerHTML = "";
  $("interact").style.display = "none";
  _lastInteractKey = null;
  poll();
}

/* ---------- 结果区 ---------- */
function renderResult(task) {
  if (task.status === "done" && task.mode === "import") {
    // 资料入库完成：提示 + 刷新主题库徽章（新库/新文件已生成）
    $("importResult").textContent = "✅ 资料入库任务完成（详见左侧日志与流程图）";
    loadInfo();
  } else if (task.status === "failed" && task.mode === "import") {
    $("importResult").textContent = "❌ 资料入库失败：" + (task.error || "未知错误");
  } else if (task.status === "done" && task.final_state && task.final_state.final_article) {
    $("result").style.display = "block";
    $("resultBody").textContent = task.final_state.final_article;
    $("resultMeta").innerHTML = `主题：${escapeHtml(task.topic)}｜模式：${escapeHtml(task.mode)}｜完成：${escapeHtml(task.created_at)}
      <button id="btnArchiveNow" class="primary" style="margin-top:8px">📥 保存要点到资料库</button>
      <span id="archiveMsg" class="hint"></span>`;
    const btn = $("btnArchiveNow");
    if (btn) btn.addEventListener("click", () => archiveArticle(task.id, btn));
  } else if (task.status === "failed") {
    $("result").style.display = "block";
    $("resultBody").textContent = `任务失败：${task.error || "未知错误"}`;
  }
}

/* ---------- 工具 ---------- */
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

/* ---------- 模型配置编辑面板（轻量：非密钥字段 + 运行参数；密钥去 .env 改） ---------- */
function openModelsModal() {
  $("modelsModal").style.display = "flex";
  $("modelsSaveMsg").textContent = "";
  loadModelsConfig();
}

function closeModelsModal() {
  $("modelsModal").style.display = "none";
}

function modelRowHtml(m) {
  m = m || {};
  return `<tr>
    <td><input class="inp-name" value="${escapeHtml(m.name || "")}" placeholder="档位名"></td>
    <td><input class="inp-model" value="${escapeHtml(m.model || "")}" placeholder="如 deepseek-ai/DeepSeek-V4-Pro"></td>
    <td><input class="inp-baseurl" value="${escapeHtml(m.base_url || "")}" placeholder="留空=全局 LLM_BASE_URL"></td>
    <td><input class="inp-role" value="${escapeHtml(m.role || "")}" placeholder="用途说明"></td>
    <td><input class="inp-caps" value="${escapeHtml((m.capabilities || []).join(", "))}" placeholder="text, long_context"></td>
    <td><input class="inp-pin" type="number" step="0.1" min="0" value="${m.input_price != null ? m.input_price : ""}" placeholder="元/百万"></td>
    <td><input class="inp-pout" type="number" step="0.1" min="0" value="${m.output_price != null ? m.output_price : ""}" placeholder="元/百万"></td>
    <td class="key-ref" title="密钥值在 .env 修改，此字段只读">${escapeHtml(m.api_key_env || "LLM_API_KEY")}</td>
    <td><button type="button" class="row-del" onclick="removeModelRow(this)">🗑</button></td>
  </tr>`;
}

function addModelRow() {
  const tbody = $("modelsRows");
  const tr = document.createElement("tr");
  tr.innerHTML = modelRowHtml({ capabilities: ["text"] });
  tbody.appendChild(tr);
}

function removeModelRow(btn) {
  const tbody = $("modelsRows");
  if (tbody.rows.length <= 1) { alert("至少保留一个档位"); return; }
  btn.closest("tr").remove();
}

async function loadModelsConfig() {
  try {
    const res = await fetch("/api/models_config");
    const data = await res.json();
    if (data.ok === false) { $("modelsSaveMsg").textContent = "❌ " + (data.error || "读取失败"); return; }
    $("modelsRows").innerHTML = (data.models || []).map(modelRowHtml).join("");
    const rp = data.run_params || {};
    $("rp_timeout").value = rp.llm_timeout != null ? rp.llm_timeout : "";
    $("rp_retries").value = rp.llm_max_retries != null ? rp.llm_max_retries : "";
    $("rp_detail").checked = !!rp.detail_log_enabled;
    $("rp_price_in").value = rp.price_input_per_m != null ? rp.price_input_per_m : "";
    $("rp_price_out").value = rp.price_output_per_m != null ? rp.price_output_per_m : "";
  } catch (e) {
    $("modelsSaveMsg").textContent = "❌ 读取配置失败：" + e;
  }
}

function collectModelsRows() {
  return Array.from(document.querySelectorAll("#modelsRows tr")).map(tr => ({
    name: (tr.querySelector(".inp-name").value || "").trim(),
    model: (tr.querySelector(".inp-model").value || "").trim(),
    base_url: (tr.querySelector(".inp-baseurl").value || "").trim(),
    role: (tr.querySelector(".inp-role").value || "").trim(),
    capabilities: (tr.querySelector(".inp-caps").value || "").split(",").map(s => s.trim()).filter(Boolean),
    input_price: tr.querySelector(".inp-pin").value === "" ? null : tr.querySelector(".inp-pin").value,
    output_price: tr.querySelector(".inp-pout").value === "" ? null : tr.querySelector(".inp-pout").value,
  }));
}

async function saveModelsConfig() {
  const models = collectModelsRows();
  if (!models.length) { alert("至少保留一个档位"); return; }
  if (models.some(m => !m.name || !m.model)) { alert("档位名与模型名不能为空"); return; }
  const run_params = { detail_log_enabled: $("rp_detail").checked };
  if ($("rp_timeout").value !== "") run_params.llm_timeout = $("rp_timeout").value;
  if ($("rp_retries").value !== "") run_params.llm_max_retries = $("rp_retries").value;
  if ($("rp_price_in").value !== "") run_params.price_input_per_m = $("rp_price_in").value;
  if ($("rp_price_out").value !== "") run_params.price_output_per_m = $("rp_price_out").value;
  try {
    const res = await fetch("/api/models_config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ models, run_params }),
    });
    const data = await res.json();
    $("modelsSaveMsg").textContent = data.ok ? ("✅ " + data.message) : ("❌ " + (data.error || "保存失败"));
    if (data.ok) { loadInfo(); }  // 刷新徽章/档位下拉（注册表已重载，同进程立即生效）
  } catch (e) {
    $("modelsSaveMsg").textContent = "❌ 保存请求失败：" + e;
  }
}

loadInfo();
