"use strict";
/* shoot 素材关联面板前端 — 零依赖单页（不用 CDN，环境铁律）
 *
 * 数据流：/api/project（打开项目）→ /api/state + /api/probe →
 *   左列呈现批注（点它过滤右列）｜右列素材卡（+关联 挂批注，多对多）
 *   → 勾选批量确认（高置信预勾选）POST /api/footage → 旁车 shoot.json 落盘
 *   → 缺拍清单 = 有呈现批注、无素材关联的行（弹层表格 + 一键复制 markdown）
 * S2-D：素材卡「✂️批注」写剪辑批注（POST /api/editnote，同素材覆盖）→
 *   任务区「生成补制任务」（POST /api/tasks/generate，幂等）+
 *   「编译剪辑交接」（POST /api/handoff/compile → 05_剪辑交接/，cut 的输入）
 * 状态全在旁车 shoot.json，前端不持久化任何东西（md 本体纯净铁律）。
 */

/* ================= 状态 ================= */
const $ = s => document.querySelector(s);
const S = {
  project: null,                    // 项目根（服务端内存态，重启即失）
  state: null,                      // shoot.json 全量
  probe: new Map(),                 // file -> {exists, duration}
  selAnn: null,                     // 左列点中的批注 id（过滤右列）
  checked: new Set(),               // 勾选的 footage id（批量确认用）
  linkFid: null,                    // 正在挂接的 footage id
};
const KIND_ICON = { manual: "🎬", ai: "🤖" };
const KIND_NAME = { manual: "人工拍摄", ai: "AI 制作" };
const TASK_ICON = { reshoot: "🎥", card: "🃏", motion: "✨", aigen: "🖼" };
const TASK_TOOL = {
  card: "cards 子技能（HTML 卡）",
  motion: "vibe-motion（Remotion 动效）",
  aigen: "aigen 子技能（Seedream 生图）",
  reshoot: "人工补拍",
};

async function api(path, body) {
  const opt = body !== undefined
    ? { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body) } : {};
  const r = await fetch(path, opt);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const e = new Error(data.error || ("HTTP " + r.status));
    e.status = r.status; throw e;
  }
  return data;
}

const esc = s => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;")
                  .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
function setStatus(text) { $("#status").textContent = text; }
let toastTimer = null;
function toast(msg, isErr) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.toggle("err", !!isErr);
  el.classList.add("on");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("on"), isErr ? 4200 : 2600);
}
function cleanPath(p) {
  /* Windows「复制文件地址」自带引号、手敲常有首尾空白——剥掉再给服务端 */
  return (p || "").trim()
    .replace(/^["'\u201c\u2018\u300c]+/, "")
    .replace(/["'\u201d\u2019\u300d]+$/, "")
    .trim();
}

/* ================= 徽标 / 小工具 ================= */
function aiConf(f) {
  return (typeof f.match === "string" && f.match.startsWith("ai:"))
    ? parseFloat(f.match.slice(3)) : null;
}
function isHighConf(f) {
  /* 高置信 = 文件名精确命中，或 AI 建议置信度 ≥0.75（批量确认预勾选线） */
  if (f.match === "filename") return true;
  const c = aiConf(f);
  return c !== null && !isNaN(c) && c >= 0.75;
}
function matchBadge(f) {
  if (f.match === "filename")
    return '<span class="badge b-file">filename</span>';
  const c = aiConf(f);
  if (c !== null && !isNaN(c))
    return `<span class="badge ${c >= 0.75 ? "b-ai-hi" : "b-ai-lo"}">`
      + `ai:${c.toFixed(2)}</span>`;
  if (f.match === "manual")
    return '<span class="badge b-manual">manual</span>';
  return `<span class="badge">${esc(String(f.match || "-"))}</span>`;
}
function stateBadge(st) {
  return st === "selected"
    ? '<span class="badge b-sel">选用</span>'
    : '<span class="badge b-cand">候选</span>';
}
function fmtDur(sec) {
  if (sec == null || isNaN(sec)) return "";
  const s = Math.round(sec);
  const m = Math.floor(s / 60);
  return m ? `${m}分${s % 60}秒` : `${s}秒`;
}
function annById(id) {
  return (S.state?.annotations || []).find(a => a.id === id) || null;
}
function linkedFootage(aid) {
  return (S.state?.footage || []).filter(f => (f.ann_ids || []).includes(aid));
}
function editNoteFor(fid) {
  /* 剪辑批注（S2-D）：一条素材一条批注——同 footage_id 服务端已覆盖收敛 */
  return (S.state?.editNotes || []).find(e => e.footage_id === fid) || null;
}
function taskStateBadge(st) {
  if (st === "done") return '<span class="badge b-sel">完成</span>';
  if (st === "doing") return '<span class="badge b-ai-lo">进行中</span>';
  return '<span class="badge b-cand">待做</span>';
}

/* ================= 打开项目 ================= */
async function openProject(p) {
  p = cleanPath(p);
  if (!p) return;
  try {
    const d = await api("/api/project", { project: p });
    S.project = d.project_root;
    S.state = d.state;
    S.selAnn = null; S.checked.clear();
    $("#projInput").value = d.project_root;
    await loadProbe();
    initChecked();
    renderAll();
    setStatus(`已打开（批注 ${(S.state.annotations || []).length}，素材 `
      + `${(S.state.footage || []).length}${d.sha_ok ? "" : "，⚠ 定稿指纹不符"}）`);
  } catch (e) {
    toast("打开失败：" + e.message, true);
  }
}
$("#btnOpen").addEventListener("click", () => openProject($("#projInput").value));
$("#projInput").addEventListener("keydown", e => {
  if (e.key === "Enter") openProject($("#projInput").value);
});

async function loadProbe() {
  /* 素材在盘状态 + 视频时长（服务端 ffprobe/ffmpeg 探测，进程内缓存） */
  S.probe.clear();
  if (!S.project) return;
  try {
    const d = await api("/api/probe");
    for (const it of d.items || []) S.probe.set(it.file, it);
  } catch (e) { /* 探测失败不挡主流程，卡片只少个时长 */ }
}

function initChecked() {
  /* 高置信候选预勾选（filename / ai≥0.75），人工确认收尾 */
  S.checked.clear();
  for (const f of S.state?.footage || [])
    if (f.state === "candidate" && isHighConf(f)) S.checked.add(f.id);
}

/* ================= 写回 ================= */
async function postUpdates(updates, okMsg) {
  try {
    const r = await api("/api/footage", { updates });
    S.state = r.state;
    for (const u of updates)               // 已选用的不再留在勾选集里
      if (u.state === "selected") S.checked.delete(u.footage_id);
    renderAnn(); renderFootage();
    if (okMsg) setStatus(okMsg);
  } catch (e) {
    if (e.status === 409)
      toast("写回被拒：" + e.message, true);
    else
      toast("更新失败：" + e.message, true);
  }
}

/* 剪辑批注（S2-D）：一条素材怎么进成片——截哪段/什么效果/接在哪。
 * upsert 语义（同 footage_id 覆盖），sha 拦截时服务端 409。 */
async function postEditNote(fid, note) {
  try {
    const r = await api("/api/editnote", { footage_id: fid, note });
    S.state = r.state;
    renderFootage();
    setStatus(`✂️ ${fid} 剪辑批注已存`);
  } catch (e) {
    toast((e.status === 409 ? "写回被拒：" : "剪辑批注保存失败：")
      + e.message, true);
  }
}

/* ================= 左列：呈现批注 ================= */
function renderAnn() {
  const wrap = $("#annList");
  const anns = S.state?.annotations || [];
  const linkedSet = new Set((S.state?.footage || [])
    .flatMap(f => f.ann_ids || []));
  let missing = 0;
  for (const a of anns) if (!linkedSet.has(a.id)) missing++;
  $("#annCnt").textContent = anns.length
    ? `（缺素材 ${missing}/${anns.length}）` : "";
  if (!anns.length) {
    wrap.innerHTML = '<div class="btip">'
      + (S.project ? "旁车里还没有呈现批注——先去 draft 定稿版打批注"
                   : "先在顶部输入项目根打开") + "</div>";
    return;
  }
  wrap.innerHTML = "";
  for (const a of anns) {
    const n = linkedFootage(a.id).length;
    const row = document.createElement("div");
    row.className = "arow"
      + (S.selAnn === a.id ? " sel" : "")
      + (n ? "" : " lacking");
    row.innerHTML =
      `<div class="ahead"><span class="aid">${KIND_ICON[a.kind] || "🎬"} `
      + `${esc(a.id)}</span>`
      + `<span class="acnt">${n ? `已挂 ${n}` : "缺"}</span></div>`
      + (a.quote ? `<div class="aquote">「${esc(a.quote)}」</div>` : "")
      + (a.kind === "ai"
          ? (a.ai_type ? `<div class="ahint">类型：${esc(a.ai_type)}</div>` : "")
            + (a.ai_brief ? `<div class="ahint">${esc(a.ai_brief)}</div>` : "")
          : (a.shoot_hint ? `<div class="ahint">${esc(a.shoot_hint)}</div>` : ""));
    row.addEventListener("click", () => {
      S.selAnn = S.selAnn === a.id ? null : a.id;
      renderAnn(); renderFootage();
    });
    wrap.appendChild(row);
  }
}

/* ================= 右列：素材卡 ================= */
function renderFootage() {
  const grid = $("#footGrid");
  const all = S.state?.footage || [];
  const list = S.selAnn
    ? all.filter(f => (f.ann_ids || []).includes(S.selAnn)) : all;
  $("#footCnt").textContent = all.length
    ? `素材 ${list.length === all.length ? all.length : `${list.length}/${all.length}`}`
    : "";
  $("#chkCnt").textContent = S.checked.size ? `已勾选 ${S.checked.size}` : "";
  $("#btnConfirm").disabled = !S.checked.size;
  if (!all.length) {
    grid.innerHTML = '<div class="empty-tip">'
      + (S.project
          ? "旁车里还没有素材——点上方「＋添加素材」手动登记，<br>素材按命名约定拍回来时也可批量匹配：<code>python 素材回收.py &lt;项目根&gt;</code>"
          : "打开项目后，这里显示素材卡")
      + "</div>";
    return;
  }
  if (!list.length) {
    grid.innerHTML = '<div class="empty-tip">这条批注还没挂任何素材——点素材卡的「+关联」挂过来</div>';
    return;
  }
  grid.innerHTML = "";
  for (const f of list) grid.appendChild(footCard(f));
}

function footCard(f) {
  const pr = S.probe.get(f.file) || {};
  const dir = f.file.includes("/") ? f.file.slice(0, f.file.lastIndexOf("/")) : "";
  const base = f.file.split("/").pop();
  const en = editNoteFor(f.id);   // 剪辑批注（S2-D）：已有就直接显示在卡上
  const card = document.createElement("div");
  card.className = "fcard"
    + (f.state === "selected" ? " is-sel" : "")
    + (pr.exists === false ? " is-missing" : "");
  card.innerHTML =
    '<div class="fhead">'
    + `<input type="checkbox" class="fchk" data-fid="${esc(f.id)}"`
    +   (S.checked.has(f.id) ? " checked" : "") + ' title="勾选后批量确认选用">'
    + `<span class="fname" title="${esc(f.file)}">${esc(base)}</span>`
    + "</div>"
    + (dir ? `<div class="fdir">${esc(dir)}/</div>` : '<div class="fdir"></div>')
    + '<div class="fbadges">'
    +   (pr.duration != null ? `<span class="fdur">${esc(fmtDur(pr.duration))}</span>` : "")
    +   (pr.exists === false ? '<span class="badge b-warn">⚠ 文件缺失</span>' : "")
    +   matchBadge(f) + stateBadge(f.state)
    + "</div>"
    + '<div class="fchips"></div>'
    + '<div class="facts">'
    +   '<button class="act-link" title="挂到呈现批注（多对多）">+关联</button>'
    +   `<button class="act-state" title="候选 / 选用切换">${f.state === "selected" ? "↩ 退回候选" : "✓ 选用"}</button>`
    +   '<button class="act-enote" title="剪辑批注：这段素材怎么进成片——截哪段 / 什么效果 / 接在哪">✂️批注</button>'
    + "</div>"
    + `<div class="enote${en ? " has" : ""}">${en ? "✂️ " + esc(en.note) : ""}</div>`
    + `<input class="enote-in" placeholder="剪辑批注：截哪段 / 什么效果 / 接在哪…" value="${esc(en ? en.note : "")}" spellcheck="false">`
    + `<input class="fnote" placeholder="备注（素材收货情况、拍摄质量等）" value="${esc(f.note || "")}" spellcheck="false">`;

  card.querySelector(".fchk").addEventListener("change", e => {
    if (e.target.checked) S.checked.add(f.id); else S.checked.delete(f.id);
    $("#chkCnt").textContent = S.checked.size ? `已勾选 ${S.checked.size}` : "";
    $("#btnConfirm").disabled = !S.checked.size;
  });
  card.querySelector(".act-link").addEventListener("click", () => openLink(f.id));
  card.querySelector(".act-state").addEventListener("click", () => {
    postUpdates([{ footage_id: f.id,
      state: f.state === "selected" ? "candidate" : "selected" }],
      `${f.id} → ${f.state === "selected" ? "候选" : "选用"}`);
  });
  const ebtn = card.querySelector(".act-enote");
  const ein = card.querySelector(".enote-in");
  const ediv = card.querySelector(".enote");
  const openEnote = () => {
    if (ein.classList.toggle("on")) { ein.focus(); ein.select(); }
  };
  // 批注条本身就是编辑入口（P9：保存后想再改，点黄条即可，不用找小按钮）
  ebtn.addEventListener("click", openEnote);
  if (en) {
    ediv.title = "点它修改剪辑批注";
    ediv.addEventListener("click", openEnote);
  }
  ein.addEventListener("change", () => {
    ein.classList.remove("on");
    if (ein.value === (en ? en.note : "")) return;
    postEditNote(f.id, ein.value);       // upsert：同 footage_id 覆盖
  });
  ein.addEventListener("keydown", e => {
    if (e.key === "Enter") ein.blur();
    if (e.key === "Escape") {
      ein.value = en ? en.note : "";
      ein.classList.remove("on");
    }
  });
  const note = card.querySelector(".fnote");
  note.addEventListener("change", () => {
    if (note.value === (f.note || "")) return;
    postUpdates([{ footage_id: f.id, note: note.value }], `${f.id} 备注已存`);
  });
  const chips = card.querySelector(".fchips");
  for (const aid of f.ann_ids || []) {
    const chip = document.createElement("button");
    chip.className = "chip";
    chip.textContent = aid;
    chip.title = "点它过滤看这条批注";
    chip.addEventListener("click", () => {
      S.selAnn = aid; renderAnn(); renderFootage();
    });
    chips.appendChild(chip);
  }
  if (!(f.ann_ids || []).length) {
    const tip = document.createElement("span");
    tip.className = "chip none";
    tip.textContent = "未挂批注";
    chips.appendChild(tip);
  }
  return card;
}

/* ================= 批量确认 ================= */
$("#btnConfirm").addEventListener("click", () => {
  if (!S.checked.size) return;
  const updates = [...S.checked].map(fid => ({ footage_id: fid, state: "selected" }));
  postUpdates(updates, `已确认 ${updates.length} 段素材为选用`);
});
$("#btnClearChk").addEventListener("click", () => {
  S.checked.clear();
  document.querySelectorAll(".fchk").forEach(c => { c.checked = false; });
  $("#chkCnt").textContent = "";
  $("#btnConfirm").disabled = true;
});
$("#chkAll").addEventListener("change", e => {
  /* 全选只作用于当前筛选可见的候选卡（选用的已定，不重复动） */
  const on = e.target.checked;
  document.querySelectorAll(".fcard").forEach(el => {
    const chk = el.querySelector(".fchk");
    if (!chk || chk.disabled) return;
    chk.checked = on;
    const fid = chk.dataset.fid;
    if (on) S.checked.add(fid); else S.checked.delete(fid);
  });
  $("#chkCnt").textContent = S.checked.size ? `已勾选 ${S.checked.size}` : "";
  $("#btnConfirm").disabled = !S.checked.size;
});

/* ================= 挂接弹层（多对多） ================= */
const overlay = $("#overlay"), linkModal = $("#linkModal");
function openLink(fid) {
  const f = (S.state?.footage || []).find(x => x.id === fid);
  if (!f) return;
  S.linkFid = fid;
  $("#linkTitle").textContent = `关联批注 — ${f.file.split("/").pop()}`;
  const wrap = $("#linkList");
  wrap.innerHTML = "";
  const anns = S.state?.annotations || [];
  if (!anns.length) {
    wrap.innerHTML = '<div class="btip">旁车里还没有呈现批注</div>';
  }
  for (const a of anns) {
    const row = document.createElement("label");
    row.className = "lrow";
    const on = (f.ann_ids || []).includes(a.id);
    row.innerHTML =
      `<input type="checkbox" value="${esc(a.id)}"` + (on ? " checked" : "") + ">"
      + `<span class="aid">${KIND_ICON[a.kind] || "🎬"} ${esc(a.id)}</span>`
      + `<span class="ltext">${a.quote ? `「${esc(a.quote)}」` : ""}`
      + `<i>${esc(a.kind === "ai" ? (a.ai_brief || a.ai_type || "AI 制作") : (a.shoot_hint || "人工拍摄"))}</i></span>`;
    wrap.appendChild(row);
  }
  linkModal.classList.add("on"); overlay.classList.add("on");
}
function closeLink() {
  linkModal.classList.remove("on"); overlay.classList.remove("on");
  S.linkFid = null;
}
$("#btnLinkClose").addEventListener("click", closeLink);
overlay.addEventListener("click", () => { closeLink(); closeAdd(); });
$("#btnLinkSave").addEventListener("click", () => {
  if (!S.linkFid) return closeLink();
  const ids = [...$("#linkList").querySelectorAll("input:checked")]
    .map(x => x.value);
  postUpdates([{ footage_id: S.linkFid, ann_ids: ids, match: "manual" }],
    `已保存关联（${ids.length} 条批注）`);
  closeLink();
});

/* ================= 手动添加素材（P8）：浏览项目目录勾文件登记 =================
 * 素材没按命名约定拍回来时，人直接在面板里添加——不必跑素材回收.py。
 * 登记即进素材表（match=manual 候选），可顺手挂批注；重复文件幂等跳过。 */
const addModal = $("#addModal");
let addCur = null;                     // 当前浏览目录（服务端返回的规范路径）

function joinPath(dir, name) {
  return dir.replace(/[\\/]+$/, "") + "/" + name;
}
function addChips() {
  /* 挂接目标批注：默认勾当前筛选中的那条 */
  const wrap = $("#addAnns");
  const anns = S.state?.annotations || [];
  if (!anns.length) { wrap.textContent = "（旁车还没有呈现批注）"; return; }
  wrap.innerHTML = "";
  for (const a of anns) {
    const lb = document.createElement("label");
    lb.innerHTML = `<input type="checkbox" value="${esc(a.id)}"`
      + (a.id === S.selAnn ? " checked" : "") + `>${KIND_ICON[a.kind] || "🎬"} ${esc(a.id)}`;
    wrap.appendChild(lb);
  }
}
async function browseAdd(dir) {
  $("#addList").innerHTML = '<div class="btip">读取中…</div>';
  try {
    const d = await api("/api/browse" + (dir ? "?dir=" + encodeURIComponent(dir) : ""));
    addCur = d.cur;
    $("#addDir").value = d.cur;
    const wrap = $("#addList");
    wrap.innerHTML = "";
    if (d.parent) {
      const up = document.createElement("div");
      up.className = "dirrow";
      up.textContent = "📁 ..（上一级）";
      up.addEventListener("click", () => browseAdd(d.parent));
      wrap.appendChild(up);
    }
    for (const name of d.dirs) {
      const row = document.createElement("div");
      row.className = "dirrow";
      row.textContent = "📁 " + name;
      row.addEventListener("click", () => browseAdd(joinPath(d.cur, name)));
      wrap.appendChild(row);
    }
    for (const f of d.files) {
      const row = document.createElement("label");
      row.className = "frow";
      row.innerHTML = `<input type="checkbox" value="${esc(f.name)}">`
        + `<span class="fname">${esc(f.name)}</span>`
        + `<span class="fsize">${(f.size / 1048576).toFixed(1)} MB</span>`;
      wrap.appendChild(row);
    }
    if (!d.files.length && !d.dirs.length) {
      wrap.innerHTML = '<div class="btip">这个目录没有素材文件'
        + '（mp4/mov/avi/mkv/jpg/jpeg/png/webp）</div>';
    }
  } catch (e) {
    $("#addList").innerHTML = `<div class="btip">读取失败: ${esc(e.message)}</div>`;
  }
}
async function openAdd() {
  if (!S.project) { toast("先打开项目"); return; }
  addModal.classList.add("on"); overlay.classList.add("on");
  addChips();
  browseAdd(S.project);
}
function closeAdd() {
  addModal.classList.remove("on"); overlay.classList.remove("on");
}
$("#btnAddFoot").addEventListener("click", openAdd);
$("#btnAddClose").addEventListener("click", closeAdd);
$("#btnAddGo").addEventListener("click", () => browseAdd($("#addDir").value));
$("#addDir").addEventListener("keydown", e => {
  if (e.key === "Enter") browseAdd($("#addDir").value);
});
$("#btnAddUp").addEventListener("click", () => {
  if (!addCur) return;
  const i = Math.max(addCur.lastIndexOf("\\"), addCur.lastIndexOf("/"));
  if (i > 3) browseAdd(addCur.slice(0, i));
});
$("#btnAddSave").addEventListener("click", async () => {
  const names = [...$("#addList").querySelectorAll("input:checked")]
    .map(x => x.value);
  if (!names.length) { toast("先勾选素材文件"); return; }
  const annIds = [...$("#addAnns").querySelectorAll("input:checked")]
    .map(x => x.value);
  const files = names.map(n => joinPath(addCur, n));
  try {
    const r = await api("/api/footage/add", { files, ann_ids: annIds });
    S.state = r.state;
    closeAdd();
    await loadProbe();
    renderAnn(); renderFootage();
    const skip = (r.skipped || []).map(s => `${s.file}（${s.reason}）`).join("、");
    if (r.added.length)
      toast(`已添加 ${r.added.length} 段素材` + (skip ? "；跳过: " + skip : ""));
    else if (skip)
      toast("没有新增——" + skip, true);
    else
      toast("没有可添加的文件", true);
  } catch (e) {
    toast((e.status === 409 ? "写回被拒：" : "添加失败：") + e.message, true);
  }
});

/* ================= 缺拍清单 ================= */
const missingModal = $("#missingModal");
async function showMissing() {
  if (!S.project) { toast("先打开项目"); return; }
  missingModal.classList.add("on"); overlay.classList.add("on");
  $("#missingBody").innerHTML = '<div class="btip">读取中…</div>';
  try {
    const d = await api("/api/missing");
    $("#missingTitle").textContent =
      `缺拍清单（${d.missing_count}/${d.total_annotations}）`;
    if (!d.missing_count) {
      $("#missingBody").innerHTML =
        '<div class="btip">不缺——每条呈现批注都有素材关联 🎉</div>';
      return;
    }
    const tb = document.createElement("table");
    tb.innerHTML = "<thead><tr><th>id</th><th>类型</th><th>引文/要求</th></tr></thead><tbody></tbody>";
    const body = tb.querySelector("tbody");
    for (const m of d.missing) {
      const tr = document.createElement("tr");
      tr.innerHTML =
        `<td class="aid">${KIND_ICON[m.kind] || "🎬"} ${esc(m.id)}</td>`
        + `<td>${esc(m.kind === "ai" ? `AI·${m.ai_type || "?"}` : "人工")}</td>`
        + `<td>${m.quote ? `「${esc(m.quote)}」` : ""}`
        + `${esc(m.kind === "ai" ? (m.ai_brief || "") : (m.shoot_hint || ""))}</td>`;
      body.appendChild(tr);
    }
    const wrap = $("#missingBody");
    wrap.innerHTML = "";
    wrap.appendChild(tb);
    wrap.dataset.md = buildMissingMd(d.missing);   // 复制按钮取这份
  } catch (e) {
    $("#missingBody").innerHTML = `<div class="btip">读取失败: ${esc(e.message)}</div>`;
  }
}
function buildMissingMd(miss) {
  const L = ["# 缺拍清单", "",
    `> 有呈现批注、无素材关联的 ${miss.length} 条——照此补拍/补制，`,
    "> 素材命名带上批注 id（如 R03_开机仰角.mp4）回来跑 素材回收.py 即自动挂接。", ""];
  for (const m of miss) {
    let l = `- **${m.id}**（${m.kind === "ai" ? `AI 制作·${m.ai_type || "其他"}` : "人工拍摄"}）`;
    if (m.quote) l += `「${m.quote}」`;
    if (m.kind === "ai" && m.ai_brief) l += ` 指令：${m.ai_brief}`;
    if (m.kind === "manual" && m.shoot_hint) l += ` 拍什么：${m.shoot_hint}`;
    L.push(l);
  }
  return L.join("\n");
}
$("#btnMissing").addEventListener("click", showMissing);
$("#btnMissingClose").addEventListener("click", () => {
  missingModal.classList.remove("on"); overlay.classList.remove("on");
});
$("#btnCopyMissing").addEventListener("click", async () => {
  const md = $("#missingBody").dataset.md || "";
  if (!md) { toast("没有可复制的缺拍清单"); return; }
  try {
    await navigator.clipboard.writeText(md);
    setStatus("缺拍清单已复制 → 去对话粘贴给 AI / 带去拍摄");
  } catch (e) {
    toast("复制失败: " + e.message, true);
  }
});

/* ================= 任务区（S2-D）：补制任务 + 剪辑交接 ================= */
function renderTasks() {
  const tasks = S.state?.tasks || [];
  $("#taskCnt").textContent = tasks.length ? `${tasks.length} 条` : "";
  const wrap = $("#taskList");
  if (!S.project) {
    wrap.innerHTML = '<div class="ttip">先打开项目，再点「生成补制任务」</div>';
    return;
  }
  if (!tasks.length) {
    wrap.innerHTML = '<div class="ttip">还没有补制任务——点「生成补制任务」'
      + "按呈现批注生成（AI 批注→对应工具；没挂素材的人工批注→补拍）</div>";
    return;
  }
  wrap.innerHTML = "";
  for (const t of tasks) {
    const row = document.createElement("div");
    row.className = "trow" + (t.state === "done" ? " done" : "");
    row.innerHTML =
      `<span class="ticon" title="${esc(t.type)}">${TASK_ICON[t.type] || "❓"}</span>`
      + `<span class="tref" title="对应呈现批注">${esc(t.ref)}</span>`
      + `<span class="ttype">${esc(t.type)}</span>`
      + `<span class="ttool" title="工具挂靠——这个任务由 media 技能栈的哪个工具执行">🔧 `
      + esc(TASK_TOOL[t.type] || "按指令自选工具") + "</span>"
      + taskStateBadge(t.state)
      + (t.output
          ? `<span class="tout" title="产物相对路径">${esc(t.output)}</span>`
          : '<span class="tout none">产物未回填</span>')
      + (t.note ? `<span class="tnote" title="备注">${esc(t.note)}</span>` : "");
    wrap.appendChild(row);
  }
}

$("#btnGenTasks").addEventListener("click", async () => {
  if (!S.project) { toast("先打开项目"); return; }
  try {
    const r = await api("/api/tasks/generate", {});
    S.state = r.state;
    renderTasks(); renderAnn();
    toast(r.added_count
      ? `新增 ${r.added_count} 条补制任务（共 ${r.tasks.length} 条）`
      : "无新增——补制任务已全部生成过（幂等）");
  } catch (e) {
    toast((e.status === 409 ? "写回被拒：" : "生成失败：") + e.message, true);
  }
});

$("#btnCompile").addEventListener("click", async () => {
  if (!S.project) { toast("先打开项目"); return; }
  try {
    const r = await api("/api/handoff/compile", {});
    toast(`已编译剪辑交接 → ${r.dir}（复制素材 ${(r.copied || []).length} 段 · `
      + `缺口 ${r.missing_count} 条）`);
  } catch (e) {
    toast((e.status === 409 ? "编译被拒：" : "编译失败：") + e.message, true);
  }
});

/* ================= 渲染总入口 / 启动 ================= */
function renderAll() { renderAnn(); renderFootage(); renderTasks(); }

(async function init() {
  /* 服务端内存里若还留着上次打开的项目，静默接回来 */
  try {
    const d = await api("/api/project");
    if (d.project_root) {
      $("#projInput").value = d.project_root;
      await openProject(d.project_root);
    }
  } catch (e) { /* 服务端没项目就停在空态 */ }
})();
