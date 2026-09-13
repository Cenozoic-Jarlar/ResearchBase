/*
 * [模块] resource_browser/static/app.js — 资源浏览器前端（原生 JS，零依赖）
 * [职责] 三 Tab（资产/档案/日志）切换 → 树形目录（可折叠） → 文件内容查看/编辑保存
 * [设计思想] 分区权限由后端配置决定；树形：后端输出平铺 dir/file 条目，前端组装嵌套树，
 *            顶级 root 目录默认展开、子目录默认收起（资源多时可点击 + 号展开）；
 *            档案分区默认只读展示，点击「✏️ 修改」才进入编辑（防误改）
 * [关键约定] API：/api/resources/sections｜<key>/tree｜<key>/read?path=&max=｜<key>/write(POST)
 *            ★ 截断显示的大文件（truncated=true）禁止编辑（避免保存时丢失后半部分）；
 *            写成功后重新读取展示最新；hash 定位自动展开目标文件的所有祖先目录
 * [被谁调用] 浏览器加载 index.html 后运行
 * [修改注意] 与 service.py 的错误格式 {ok,error} 对齐；新增交互时保持零依赖
 */
"use strict";

const $ = (id) => document.getElementById(id);

let sections = [];
let currentKey = null;
let currentPath = null;
let currentReadonly = true;
let currentTree = null;      // 当前分区嵌套树（用于重渲染/折叠）
let currentTruncated = false;
let currentEditing = false;
let pendingTarget = null;    // 来自 URL hash 的定位目标 {key, path}

/* ---------- 初始化 ---------- */
function parseHashTarget() {
  const h = location.hash.replace(/^#/, "");
  const i = h.indexOf("/");
  if (i <= 0) return null;
  return { key: h.slice(0, i), path: decodeURIComponent(h.slice(i + 1)) };
}

async function loadSections() {
  try {
    const res = await fetch("/api/resources/sections");
    const data = await res.json();
    sections = data.sections || [];
    pendingTarget = parseHashTarget();
    renderTabs();
  } catch (e) {
    $("tabs").innerHTML = '<span class="badge">后端未连接</span>';
  }
}

function renderTabs() {
  const tabs = $("tabs");
  tabs.innerHTML = sections.map(s =>
    `<button class="tab ${s.key === currentKey ? "active" : ""}" data-key="${s.key}">
       ${s.label} <span class="perm">${s.readonly ? "🔒" : "✏️"}</span>
     </button>`).join("");
  tabs.querySelectorAll(".tab").forEach(b =>
    b.addEventListener("click", () => selectSection(b.dataset.key)));
  if (!currentKey && sections.length) {
    selectSection(pendingTarget && pendingTarget.key ? pendingTarget.key : sections[0].key);
  }
}

/* ---------- 树：平铺 entries → 嵌套树 → 渲染 ---------- */
function buildTree(entries) {
  const root = { name: "", path: "", type: "root", dir: true, children: [] };
  entries.forEach(e => {
    const parts = e.path.split("/");
    let node = root;
    let cur = "";
    parts.forEach((seg, i) => {
      cur = cur ? cur + "/" + seg : seg;
      let child = node.children.find(c => c.path === cur);
      if (!child) {
        child = {
          name: seg, path: cur,
          dir: i < parts.length - 1 || e.type === "dir",
          children: [],
        };
        node.children.push(child);
      }
      node = child;
    });
  });
  const sortNodes = (arr) => {
    arr.sort((a, b) => {
      if (a.dir !== b.dir) return a.dir ? -1 : 1;
      return a.name.localeCompare(b.name, "zh");
    });
    arr.forEach(n => sortNodes(n.children));
  };
  sortNodes(root.children);
  return root;
}

function findTreeNode(node, path) {
  if (node.path === path) return node;
  for (const c of node.children) {
    const r = findTreeNode(c, path);
    if (r) return r;
  }
  return null;
}

function expandAncestors(tree, targetPath) {
  const parts = targetPath.split("/");
  let cur = "";
  for (let i = 0; i < parts.length - 1; i++) {
    cur = cur ? cur + "/" + parts[i] : parts[i];
    const n = findTreeNode(tree, cur);
    if (n) n.expanded = true;
  }
}

function renderTree(entries, tree) {
  const box = $("treeBox");
  if (tree) {
    currentTree = tree;               // 重渲染：保留树实例（展开状态不丢）
  } else if (entries) {
    currentTree = buildTree(entries); // 首次/切换分区：重建树
  }
  if (!currentTree || !currentTree.children.length) {
    box.innerHTML = '<div class="placeholder">（空目录）</div>';
    return;
  }
  // 顶级 root 目录默认展开；子目录由各自 expanded 状态决定（默认收起）
  box.innerHTML = currentTree.children.map(c => renderNode(c, 0, true)).join("");
  box.querySelectorAll(".tree-item.dir").forEach(el =>
    el.addEventListener("click", () => {
      const node = findTreeNode(currentTree, el.dataset.path);
      if (!node) return;
      node.expanded = !(node.expanded === true);
      renderTree(null, currentTree);
      // 重渲染后恢复当前选中文件高亮
      if (currentPath) {
        const hit = findTreeEl(currentPath);
        if (hit) hit.classList.add("active");
      }
    }));
  box.querySelectorAll(".tree-item.file").forEach(el =>
    el.addEventListener("click", () => openFile(el.dataset.path, el)));
}

function renderNode(node, depth, defaultExpand) {
  const indent = depth * 16;
  if (node.dir) {
    const expanded = node.expanded === undefined ? defaultExpand : node.expanded;
    const kidsHtml = expanded ? node.children.map(c => renderNode(c, depth + 1, false)).join("") : "";
    return `<div class="tree-item dir" data-path="${escapeHtml(node.path)}" style="padding-left:${indent}px">
      <span class="twist">${expanded ? "▾" : "▸"}</span><span class="dir-icon">📁</span>${escapeHtml(node.name)}
    </div>${kidsHtml}`;
  }
  return `<div class="tree-item file" data-path="${escapeHtml(node.path)}" style="padding-left:${indent}px">
    <span class="file-icon">📄</span>${escapeHtml(node.name)}
  </div>`;
}

function findTreeEl(path) {
  const items = $("treeBox").querySelectorAll(".tree-item");
  for (const it of items) if (it.dataset.path === path) return it;
  return null;
}

async function selectSection(key) {
  currentKey = key;
  currentPath = null;
  currentTree = null;
  renderTabs();
  const box = $("treeBox");
  box.innerHTML = '<div class="placeholder">加载目录树…</div>';
  $("contentBox").innerHTML = '<div class="placeholder">从左侧选择文件查看内容</div>';
  try {
    const res = await fetch(`/api/resources/${key}/tree`);
    const data = await res.json();
    if (!data.ok) throw new Error(data.error);
    renderTree(data.entries);
    // hash 定位：切到目标分区后展开祖先目录并打开目标文件
    if (pendingTarget && pendingTarget.key === key) {
      const t = pendingTarget;
      pendingTarget = null;
      const hit = data.entries.find(e => e.path === t.path && e.type === "file");
      if (hit) {
        expandAncestors(currentTree, t.path);
        renderTree(null, currentTree);
        const el = findTreeEl(t.path);
        openFile(t.path, el);
        if (el) el.scrollIntoView({ block: "nearest" });
      } else {
        $("contentBox").innerHTML = `<div class="placeholder">未找到目标文件：${escapeHtml(t.path)}<br>（可能已被移动或删除）</div>`;
      }
    }
  } catch (e) {
    box.innerHTML = `<div class="placeholder">目录树加载失败：${escapeHtml(e.message)}</div>`;
  }
}

/* ---------- 文件内容：默认只读，可编辑分区点「修改」进入编辑 ---------- */
async function openFile(path, el) {
  currentPath = path;
  currentEditing = false;
  currentReadonly = sections.find(s => s.key === currentKey).readonly;
  $("treeBox").querySelectorAll(".tree-item").forEach(i => i.classList.remove("active"));
  if (el) el.classList.add("active");
  const box = $("contentBox");
  box.innerHTML = '<div class="placeholder">读取内容…</div>';
  try {
    const res = await fetch(`/api/resources/${currentKey}/read?path=${encodeURIComponent(path)}`);
    const data = await res.json();
    if (!data.ok) throw new Error(data.error);
    renderContent(data);
  } catch (e) {
    box.innerHTML = `<div class="placeholder">读取失败：${escapeHtml(e.message)}</div>`;
  }
}

function renderContent(data) {
  const box = $("contentBox");
  currentTruncated = data.truncated;
  const truncHint = data.truncated
    ? `<div class="trunc-hint">⚠ 文件较大（共 ${data.total} 字符），已截断显示前 ${data.content.length} 字符${currentReadonly ? "" : "；大文件不可编辑"}</div>` : "";
  const permHint = currentReadonly
    ? '<div class="perm-hint">🔒 只读分区，仅可查看</div>'
    : '<div class="perm-hint edit">✏️ 可编辑分区：点击「修改」后编辑，保存前自动备份 .bak</div>';
  const bodyHtml = (currentReadonly || !currentEditing)
    ? `<pre id="contentBody" class="content-body">${escapeHtml(data.content)}</pre>`
    : `<textarea id="contentBody" class="content-body edit" spellcheck="false">${escapeHtml(data.content)}</textarea>`;
  box.innerHTML = `
    <div class="content-head">
      <span class="path">${escapeHtml(currentPath)}</span>${permHint}
    </div>
    ${truncHint}
    ${bodyHtml}`;
  if (!currentReadonly) {
    const bar = document.createElement("div");
    bar.className = "content-actions";
    if (!currentEditing) {
      const editBtn = document.createElement("button");
      editBtn.className = "primary";
      editBtn.textContent = "✏️ 修改";
      editBtn.disabled = !!currentTruncated;
      editBtn.title = currentTruncated ? "文件过大（已截断），为避免保存丢失内容，禁止编辑" : "";
      editBtn.addEventListener("click", enterEditMode);
      bar.appendChild(editBtn);
    } else {
      const saveBtn = document.createElement("button");
      saveBtn.className = "primary save-btn";
      saveBtn.textContent = "💾 保存修改";
      saveBtn.addEventListener("click", saveFile);
      const cancelBtn = document.createElement("button");
      cancelBtn.textContent = "取消";
      cancelBtn.addEventListener("click", () => openFile(currentPath));
      bar.appendChild(saveBtn);
      bar.appendChild(cancelBtn);
    }
    box.appendChild(bar);
  }
}

function enterEditMode() {
  currentEditing = true;
  renderContent({ content: $("contentBody").textContent, truncated: currentTruncated });
}

async function saveFile() {
  const ta = $("contentBody");
  if (!ta) return;
  const btn = document.querySelector(".save-btn");
  btn.disabled = true;
  btn.textContent = "保存中…";
  try {
    const res = await fetch(`/api/resources/${currentKey}/write`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: currentPath, content: ta.value }),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error);
    const bakNote = data.backup
      ? `（原文件已备份：${data.backup.split(/[\\/]/).pop()}）` : "（新文件，无备份）";
    alert(`✅ 保存成功 ${bakNote}`);
    if (currentKey === "archives" && !currentPath.endsWith("_repo.md")) {
      alert("提示：若修改的是主题库资料，_repo.md 摘要索引可能需刷新（可在下次入库时自动更新）");
    }
    openFile(currentPath);
  } catch (e) {
    alert(`保存失败：${e.message}`);
    btn.disabled = false;
    btn.textContent = "💾 保存修改";
  }
}

/* ---------- 工具 ---------- */
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// 同页手动修改 hash 时重新定位（主流程=新标签打开，此监听覆盖地址栏改 URL 场景）
window.addEventListener("hashchange", () => {
  const t = parseHashTarget();
  if (t && (t.key !== currentKey || t.path !== currentPath)) {
    pendingTarget = t;
    selectSection(t.key);
  }
});

loadSections();
