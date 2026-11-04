"use strict";
/* draft 审阅工作台前端 — 零依赖单页（不用 CDN，环境铁律）
 *
 * 数据流：/api/open → S.blocks + S.review → 块渲染（contenteditable 按块隔离）
 *   → blur 时 raw/hash 回写 + 批注自动跟锚 → 选中文字浮动条打批注（旁车落盘）
 *   → 保存整档块数组写回 md（round-trip 保真由后端单测保证）
 * 锚点一致性：块 hash = md5(type+"\x00"+raw)[:10]，必须与后端 hashlib 完全对齐。
 */

/* ================= md5（RFC 1321，字节版，供块锚点用） ================= */
function md5Bytes(input) {
  const S = [7,12,17,22,7,12,17,22,7,12,17,22,7,12,17,22,
             5, 9,14,20,5, 9,14,20,5, 9,14,20,5, 9,14,20,
             4,11,16,23,4,11,16,23,4,11,16,23,4,11,16,23,
             6,10,15,21,6,10,15,21,6,10,15,21,6,10,15,21];
  const K = new Int32Array(64);
  for (let i = 0; i < 64; i++)
    K[i] = Math.floor(Math.abs(Math.sin(i + 1)) * 4294967296) | 0;
  const len = input.length;
  const total = (((len + 8) >> 6) + 1) << 6;
  const msg = new Uint8Array(total);
  msg.set(input);
  msg[len] = 0x80;
  const dv = new DataView(msg.buffer);
  const bitLen = len * 8;
  dv.setUint32(total - 8, bitLen >>> 0, true);
  dv.setUint32(total - 4, Math.floor(bitLen / 4294967296), true);
  let a0 = 0x67452301, b0 = 0xefcdab89, c0 = 0x98badcfe, d0 = 0x10325476;
  const M = new Int32Array(16);
  for (let off = 0; off < total; off += 64) {
    for (let j = 0; j < 16; j++) M[j] = dv.getInt32(off + j * 4, true);
    let A = a0, B = b0, C = c0, D = d0;
    for (let i = 0; i < 64; i++) {
      let F, g;
      if (i < 16)      { F = (B & C) | (~B & D); g = i; }
      else if (i < 32) { F = (D & B) | (~D & C); g = (5 * i + 1) % 16; }
      else if (i < 48) { F = B ^ C ^ D;          g = (3 * i + 5) % 16; }
      else             { F = C ^ (B | ~D);       g = (7 * i) % 16; }
      F = (F + A + K[i] + M[g]) | 0;
      A = D; D = C; C = B;
      B = (B + ((F << S[i]) | (F >>> (32 - S[i])))) | 0;
    }
    a0 = (a0 + A) | 0; b0 = (b0 + B) | 0;
    c0 = (c0 + C) | 0; d0 = (d0 + D) | 0;
  }
  const out = new Uint8Array(16);
  const odv = new DataView(out.buffer);
  odv.setInt32(0, a0, true); odv.setInt32(4, b0, true);
  odv.setInt32(8, c0, true); odv.setInt32(12, d0, true);
  return out;
}
function blockHash(type, raw) {
  const bytes = new TextEncoder().encode(type + "\x00" + raw);
  return Array.from(md5Bytes(bytes), b => b.toString(16).padStart(2, "0"))
    .join("").slice(0, 10);
}

/* ================= 状态 ================= */
const $ = s => document.querySelector(s);
const S = {
  path: null, sha256: null,
  blocks: [],                       // [{hash,type,raw,gap,level,eol,line}]
  review: { version: 1, comments: [] },
  anchors: new Map(),               // cid -> blockIndex | null(orphan)
  dirty: false,
  reanchorCid: null,                // 重锚模式：等待用户点块
};
const EDITABLE = new Set(["heading", "paragraph", "list_item", "quote",
                          "code", "table", "frontmatter", "blank"]);
const TY_NAME = { comment: "评论", delete: "删除", replace: "替换",
                  highlight: "高亮" };
const TY_ACT  = { comment: "意见", delete: "删除该句", replace: "改为",
                  highlight: "强调" };

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

const esc = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;")
                  .replace(/>/g, "&gt;").replace(/"/g, "&quot;");

function setStatus(text, dirty) {
  const el = $("#status");
  el.textContent = text;
  el.classList.toggle("dirty", !!dirty);
}
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
function markDirty() {
  S.dirty = true;
  setStatus(S.path ? "未保存" : "", true);
  $("#btnSave").disabled = !S.path;
}

/* ================= 锚定 ================= */
function matchAll() {
  const byHash = new Map();
  S.blocks.forEach((b, i) => { if (!byHash.has(b.hash)) byHash.set(b.hash, i); });
  for (const c of S.review.comments) {
    let idx = byHash.get(c.block_hash);
    let how = "hash";
    if (idx === undefined && c.quote) {
      idx = S.blocks.findIndex(b => (b.raw || "").includes(c.quote));
      how = "quote";
    }
    if (idx === undefined || idx < 0) { idx = null; how = "orphan"; }
    S.anchors.set(c.id, idx);
    c._anchor = how;
  }
}

/* ================= 渲染：块 ================= */
function commentsFor(idx) {
  return S.review.comments.filter(
    c => c.status === "open" && c.quote && S.anchors.get(c.id) === idx);
}
function markTitle(c) {
  let t = TY_NAME[c.type] || c.type;
  if (c.type === "replace" && c.suggestion) t += " → " + c.suggestion;
  if (c.note) t += "（" + c.note + "）";
  return t;
}
function blockInnerHTML(b, idx) {
  const cs = commentsFor(idx);
  if (!cs.length) return esc(b.raw);
  const hits = [];
  for (const c of cs) {
    const p = (b.raw || "").indexOf(c.quote);
    if (p >= 0) hits.push({ p, len: c.quote.length, c });
  }
  hits.sort((x, y) => x.p - y.p);
  let out = "", pos = 0;
  for (const h of hits) {
    if (h.p < pos) continue;                       // 重叠的批注只画第一个
    out += esc(b.raw.slice(pos, h.p))
        + `<span class="mk mk-${h.c.type}" data-cid="${h.c.id}" `
        + `title="${esc(markTitle(h.c))}">`
        + esc(b.raw.substr(h.p, h.len)) + "</span>";
    pos = h.p + h.len;
  }
  return out + esc(b.raw.slice(pos));
}

function renderDoc() {
  const doc = $("#doc");
  doc.innerHTML = "";
  if (!S.path) {
    doc.innerHTML = '<div class="empty-tip">输入路径打开一篇 md（AI 初稿大纲/脚本），<br>逐块编辑、选中文字打批注，✨ 一键复制修改清单喂给 AI。</div>';
    return;
  }
  S.blocks.forEach((b, i) => doc.appendChild(buildBlockEl(b, i)));
}

function buildBlockEl(b, idx) {
  const el = document.createElement("div");
  el.className = "blk t-" + b.type
    + (b.type === "heading" ? " h" + b.level : "")
    + (b.type === "list_item" ? " lv" + Math.min(b.level || 0, 3) : "");
  el.dataset.idx = idx;
  el.dataset.hash = b.hash;

  if (b.type === "hr") {
    el.innerHTML = '<div class="hrline"></div>';
  } else {
    if (EDITABLE.has(b.type)) {
      try { el.contentEditable = "plaintext-only"; }
      catch (e) { el.contentEditable = "true"; }   // 兜底：粘贴事件再洗
      el.addEventListener("paste", e => {
        e.preventDefault();
        document.execCommand("insertText", false,
          e.clipboardData.getData("text/plain"));
      });
    } else {
      el.contentEditable = "false";
    }
    const cs = commentsFor(idx);
    if (cs.length && el.contentEditable !== "true") {
      el.innerHTML = blockInnerHTML(b, idx);
      el.dataset.marked = "1";
    } else {
      el.textContent = b.raw;
    }
    // 聚焦 = 进编辑态：摘掉标记，露出纯原文
    el.addEventListener("focus", () => {
      if (el.dataset.marked) {
        el.textContent = b.raw;
        delete el.dataset.marked;
      }
    });
    // 失焦 = 出编辑态：回写 raw/hash，批注自动跟锚，重画标记
    el.addEventListener("blur", () => commitBlockEdit(el, idx));
  }

  el.appendChild(buildBlockTools(idx));
  // 块内一律禁拖（含文本拖拽）：触控板微拖把选区拖走曾致空 dataTransfer 走
  // 进 drop 处理器，+"" === 0 绕过 NaN 守卫，moveBlock(0,…) 直接搬走首块。
  // 排序改由 ↑↓ 按钮确定性完成，拖拽通道整体关死。
  el.addEventListener("dragstart", e => e.preventDefault());
  el.addEventListener("click", () => {           // 重锚模式：点块即重锚
    if (S.reanchorCid !== null) doReanchor(idx);
  });
  return el;
}

function buildBlockTools(idx) {
  const bar = document.createElement("div");
  bar.className = "blktools";
  const mk = (txt, title, fn) => {
    const btn = document.createElement("button");
    btn.textContent = txt; btn.title = title;
    btn.addEventListener("mousedown", e => e.preventDefault()); // 不抢选区
    btn.addEventListener("click", e => { e.stopPropagation(); fn(); });
    bar.appendChild(btn);
  };
  mk("↑", "上移", () => moveBlock(idx, idx - 1));
  mk("↓", "下移", () => moveBlock(idx, idx + 1));
  mk("✚", "在下方插入空块", () => insertBlockAfter(idx));
  mk("🗑", "删除此块", () => { if (confirm("删除此块？（可在 📜 历史回滚找回）")) removeBlock(idx); });
  mk("💬", "整块评论", () => { addComment(idx, "comment", { quote: "" }); });
  return bar;
}

function blockText(el) {
  /* 读块纯文本：工具条是块的子元素，必须剔除。
     plaintext-only 路径用 textContent（clone 后摘工具条——textContent 无视
     display:none，直接读会混入按钮字）；兜底路径用活元素 innerText
     （display:none 的工具条天然不进 innerText）。 */
  if (el.contentEditable !== "plaintext-only") return el.innerText;
  const clone = el.cloneNode(true);
  const tools = clone.querySelector(".blktools");
  if (tools) tools.remove();
  return clone.textContent;
}

function commitBlockEdit(el, idx) {
  const b = S.blocks[idx];
  if (!b || b.type === "hr") return;
  const raw = blockText(el);
  if (raw === b.raw) { refreshBlockEl(idx); return; }
  const oldHash = b.hash;
  b.raw = raw;
  b.hash = blockHash(b.type, b.raw);
  // 本块上的批注自动跟锚（它们此刻就贴在这个块上）
  for (const c of S.review.comments)
    if (c.block_hash === oldHash) c.block_hash = b.hash;
  markDirty();
  matchAll();
  refreshBlockEl(idx);
  renderPanel();
  saveReviewDebounced();
}

function refreshBlockEl(idx) {
  const old = document.querySelector(`.blk[data-idx="${idx}"]`);
  if (!old) return;
  const parent = old.parentElement;
  const next = old.nextSibling;
  parent.replaceChild(buildBlockEl(S.blocks[idx], idx), old);
  if (next && next !== old) parent.insertBefore(next, old.nextSibling);
}
function flashBlock(idx) {
  const el = document.querySelector(`.blk[data-idx="${idx}"]`);
  if (!el) return;
  el.scrollIntoView({ block: "center", behavior: "smooth" });
  el.classList.remove("flash");
  void el.offsetWidth;
  el.classList.add("flash");
}

/* ================= 块操作 ================= */
function moveBlock(from, to) {
  if (to < 0 || to >= S.blocks.length || from === to) return;
  const gaps = S.blocks.map(b => b.gap);          // gap 属于位置不属于块
  const [b] = S.blocks.splice(from, 1);
  S.blocks.splice(to, 0, b);
  S.blocks.forEach((blk, i) => { blk.gap = gaps[i]; });
  markDirty(); renderDoc(); matchAll(); renderPanel();
}
function insertBlockAfter(idx) {
  const nb = { hash: blockHash("paragraph", ""), type: "paragraph",
               raw: "", gap: 1, level: 0, eol: S.blocks[idx].eol || "lf" };
  S.blocks.splice(idx + 1, 0, nb);
  markDirty(); renderDoc();
  const el = document.querySelector(`.blk[data-idx="${idx + 1}"]`);
  if (el) { el.focus(); }
}
function removeBlock(idx) {
  if (S.blocks.length <= 1) return;
  if (idx === S.blocks.length - 1) {              // 末块：文末换行转移（镜像后端 delete_block）
    S.blocks[idx - 1].gap = S.blocks[idx].gap;
  }
  S.blocks.splice(idx, 1);
  markDirty(); renderDoc(); matchAll(); renderPanel();
  saveReviewDebounced();
}

/* ================= 选中文字 → 批注四件套 ================= */
let selCtx = null;                                 // {idx, quote}
function selectionInfo() {
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || !S.path) return null;
  const anchorEl = sel.anchorNode && sel.anchorNode.parentElement;
  const focusEl = sel.focusNode && sel.focusNode.parentElement;
  const aBlk = anchorEl && anchorEl.closest(".blk");
  const fBlk = focusEl && focusEl.closest(".blk");
  if (!aBlk || aBlk !== fBlk) return null;        // 跨块选区不批
  const idx = +aBlk.dataset.idx;
  const b = S.blocks[idx];
  if (!b || !EDITABLE.has(b.type)) return null;
  const quote = sel.toString();
  if (!quote || !b.raw.includes(quote)) return null;
  return { idx, quote, rect: sel.getRangeAt(0).getBoundingClientRect() };
}
document.addEventListener("mouseup", e => {
  // 浮动条内部的 mouseup（点按钮）会清空正文选区，不能拿来重判，否则条自己把自己藏了
  if (e.target && e.target.closest && e.target.closest("#selbar")) return;
  setTimeout(() => {
    if (S.reanchorCid !== null) return;
    const info = selectionInfo();
    const bar = $("#selbar");
    if (!info) { bar.classList.remove("on"); selCtx = null; return; }
    selCtx = { idx: info.idx, quote: info.quote };
    bar.classList.add("on");
    bar.classList.remove("inputing");
    const top = info.rect.bottom + window.scrollY + 6;
    const left = Math.max(8, info.rect.left + window.scrollX
                          - bar.offsetWidth / 2 + info.rect.width / 2);
    bar.style.top = top + "px";
    bar.style.left = left + "px";
  }, 10);
});
$("#selbar").addEventListener("click", e => {
  const btn = e.target.closest("button[data-act]");
  if (!btn || !selCtx) return;
  const act = btn.dataset.act;
  if (act === "delete" || act === "highlight") {
    addComment(selCtx.idx, act, { quote: selCtx.quote });
    hideSelbar();
  } else {                                        // replace/comment：要输入
    pendingAct = act;
    const bar = $("#selbar");
    bar.classList.add("inputing");
    const inp = $("#selInput");
    inp.placeholder = act === "replace" ? "改成什么？（回车确认）" : "你的意见（回车确认）";
    inp.value = ""; inp.focus();
  }
});
let pendingAct = null;
$("#selInput").addEventListener("keydown", e => {
  if (e.key !== "Enter") return;
  e.preventDefault();
  const v = $("#selInput").value.trim();
  if (pendingAct && selCtx && v) {
    addComment(selCtx.idx, pendingAct, pendingAct === "replace"
      ? { quote: selCtx.quote, suggestion: v }
      : { quote: selCtx.quote, note: v });
  }
  pendingAct = null;
  hideSelbar();
});
function hideSelbar() {
  $("#selbar").classList.remove("on", "inputing");
  window.getSelection().removeAllRanges();
  selCtx = null;
}

function addComment(idx, type, fields) {
  const b = S.blocks[idx];
  const c = {
    id: "c" + Date.now().toString(36) + Math.floor(Math.random() * 1e4),
    block_hash: b.hash,
    quote: fields.quote || "",
    type, suggestion: fields.suggestion || "",
    note: fields.note || "", status: "open",
  };
  S.review.comments.push(c);
  matchAll();
  refreshBlockEl(idx);
  renderPanel();
  saveReviewDebounced();
  flashBlock(idx);
  markDirty();
}

/* ================= 批注面板 ================= */
function renderPanel() {
  const wrap = $("#cmtList");
  wrap.innerHTML = "";
  const cs = S.review.comments;
  const openCnt = cs.filter(c => c.status === "open").length;
  $("#cmtCnt").textContent = cs.length
    ? `（待处理 ${openCnt}/${cs.length}）` : "";
  const orphans = cs.filter(c => c._anchor === "orphan");
  const normal = cs.filter(c => c._anchor !== "orphan");
  const card = c => {
    const div = document.createElement("div");
    div.className = "ccard ty-" + c.type
      + (c.status === "resolved" ? " resolved" : "")
      + (c._anchor === "orphan" ? " orphan" : "");
    const idx = S.anchors.get(c.id);
    const loc = idx === null ? "未锚定" : `[B${idx}] ` +
      (S.blocks[idx] ? S.blocks[idx].raw.slice(0, 18) : "");
    div.innerHTML =
      `<div class="chead"><span class="cbadge">${TY_NAME[c.type] || c.type}</span>`
      + `<span class="cloc">${esc(loc)}</span>`
      + `<span class="cloc">${c._anchor === "hash" ? "" : c._anchor === "quote" ? "·文本找回" : "·失锚"}</span></div>`
      + (c.quote ? `<div class="cquote">${esc(c.quote)}</div>` : "")
      + (c.type === "replace" && c.suggestion ? `<div class="cnote"><b>改为:</b> ${esc(c.suggestion)}</div>` : "")
      + (c.note ? `<div class="cnote">${esc(c.note)}</div>` : "")
      + '<div class="cacts"></div>';
    const acts = div.querySelector(".cacts");
    const mkBtn = (txt, fn) => {
      const b = document.createElement("button");
      b.textContent = txt; b.addEventListener("click", fn); acts.appendChild(b);
    };
    if (c._anchor === "orphan") {
      mkBtn("📍 重锚", () => startReanchor(c.id));
    } else {
      mkBtn("↗ 跳转", () => flashBlock(idx));
    }
    mkBtn(c.status === "open" ? "✓ 已处理" : "↩ 重开", () => {
      c.status = c.status === "open" ? "resolved" : "open";
      markDirty(); matchAll(); renderDoc(); renderPanel(); saveReviewDebounced();
    });
    mkBtn("🗑", () => {
      const k = S.review.comments.indexOf(c);
      S.review.comments.splice(k, 1);
      markDirty(); matchAll(); renderDoc(); renderPanel(); saveReviewDebounced();
    });
    return div;
  };
  if (!cs.length) wrap.innerHTML = '<div class="btip">还没有批注——选中正文文字试试浮动条</div>';
  if (normal.length) normal.forEach(c => wrap.appendChild(card(c)));
  if (orphans.length) {
    const h = document.createElement("div");
    h.className = "orphan-head";
    h.textContent = `⚠ 失锚批注 ${orphans.length} 条（原稿变了，点重锚再点目标块）`;
    wrap.prepend(h);
    orphans.forEach(c => wrap.appendChild(card(c)));
  }
}

function startReanchor(cid) {
  S.reanchorCid = cid;
  document.body.classList.add("reanchoring");
  setStatus("重锚模式：点击目标块完成锚定（Esc 取消）");
}
function doReanchor(idx) {
  const c = S.review.comments.find(x => x.id === S.reanchorCid);
  S.reanchorCid = null;
  document.body.classList.remove("reanchoring");
  if (!c) { renderPanel(); return; }
  c.block_hash = S.blocks[idx].hash;
  if (c.quote && !S.blocks[idx].raw.includes(c.quote)) c.quote = ""; // 换锚后旧引文未必还在
  markDirty();
  matchAll(); renderDoc(); renderPanel(); saveReviewDebounced();
  setStatus("已重锚到 [B" + idx + "]");
  flashBlock(idx);
}
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && S.reanchorCid !== null) {
    S.reanchorCid = null;
    document.body.classList.remove("reanchoring");
    setStatus("已取消重锚");
  }
});

$("#btnResolveAll").addEventListener("click", () => {
  if (!S.review.comments.some(c => c.status === "open")) return;
  if (!confirm("把全部批注标为已处理？（AI 改完回贴新稿后用）")) return;
  S.review.comments.forEach(c => { c.status = "resolved"; });
  markDirty(); matchAll(); renderDoc(); renderPanel(); saveReviewDebounced();
});

/* ================= 保存 / 旁车 ================= */
let reviewTimer = null;
function saveReviewDebounced() {
  clearTimeout(reviewTimer);
  reviewTimer = setTimeout(() => {
    if (!S.path) return;
    api("/api/review", { path: S.path, review: S.review })
      .catch(e => setStatus("批注落盘失败: " + e.message));
  }, 400);
}

async function save(force) {
  if (!S.path) return;
  try {
    const r = await api("/api/save", {
      path: S.path, base_sha256: S.sha256,
      blocks: S.blocks, review: S.review, force: !!force,
    });
    S.sha256 = r.sha256;
    S.dirty = false;
    setStatus("已保存 " + new Date().toLocaleTimeString() + "（" + r.bytes + "B）");
  } catch (e) {
    if (e.status === 409 && confirm("文件已被外部修改（可能被别的程序动过）。\n强制覆盖？")) {
      return save(true);
    }
    toast("保存失败：" + e.message, true);
  }
}
$("#btnSave").addEventListener("click", () => save());
document.addEventListener("keydown", e => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
    e.preventDefault(); save();
  }
});
window.addEventListener("beforeunload", e => {
  if (S.dirty) { e.preventDefault(); e.returnValue = ""; }
});

/* ================= ✨ 复制给 AI ================= */
function buildAiList() {
  const open = S.review.comments.filter(
    c => c.status === "open" && S.anchors.get(c.id) !== null);
  const L = [];
  L.push("你是视频文稿编辑。下面是一篇 md 稿件（按块编号 [B#]）和逐条修改意见。");
  L.push("请严格按意见修改并输出修改后的完整 md 正文：不要解释、不要加代码围栏，未提及的内容保持原样。");
  L.push("", "# 稿件", "");
  S.blocks.forEach((b, i) => {
    if (b.type === "blank") return;
    L.push(`[B${i}] (${b.type})`);
    L.push(b.raw);
    L.push("");
  });
  if (!open.length) {
    L.push("# 修改意见", "（无未处理意见——稿件无需修改，原样输出即可）");
  } else {
    L.push("# 修改意见", "");
    open.forEach((c, k) => {
      const idx = S.anchors.get(c.id);
      const whole = !c.quote || (S.blocks[idx] && S.blocks[idx].raw === c.quote);
      let l = `${k + 1}. [B${idx}] ${TY_ACT[c.type] || c.type}`;
      if (!whole) l += ` 原文:「${c.quote}」`;
      if (c.type === "replace") l += ` 改为:「${c.suggestion}」`;
      if (c.note) l += ` 意见:「${c.note}」`;
      L.push(l);
    });
  }
  return L.join("\n");
}
$("#btnAI").addEventListener("click", async () => {
  const text = buildAiList();
  const openCnt = S.review.comments.filter(
    c => c.status === "open" && S.anchors.get(c.id) !== null).length;
  try {
    await navigator.clipboard.writeText(text);
    setStatus(`已复制修改清单（${openCnt} 条意见）→ 去对话粘贴即可`);
  } catch (e) {
    setStatus("复制失败: " + e.message);
  }
});

/* ================= 打开 / 浏览 ================= */
function addRecent(p) {
  const list = JSON.parse(localStorage.getItem("draft_recent") || "[]")
    .filter(x => x !== p);
  list.unshift(p);
  localStorage.setItem("draft_recent", JSON.stringify(list.slice(0, 12)));
  renderRecent();
}
function renderRecent() {
  $("#recentList").innerHTML = JSON.parse(
    localStorage.getItem("draft_recent") || "[]")
    .map(p => `<option value="${esc(p)}">`).join("");
}

async function openPath(p) {
  p = cleanPath(p);
  if (!p) return;
  try {
    const d = await api("/api/open", { path: p });
    S.path = d.path; S.sha256 = d.sha256;
    S.blocks = d.blocks; S.review = d.review;
    if (!S.review.comments) S.review.comments = [];
    matchAll();
    renderDoc(); renderPanel(); addRecent(d.path);
    $("#pathInput").value = d.path;
    $("#btnSave").disabled = false; $("#btnAI").disabled = false;
    $("#btnHist").disabled = false;
    S.dirty = false;
    setStatus("已打开（" + S.blocks.length + " 块，批注 " + S.review.comments.length + " 条）");
  } catch (e) {
    toast("打开失败：" + e.message + "（检查路径是否正确）", true);
  }
}
$("#btnOpen").addEventListener("click", () => openPath($("#pathInput").value));
$("#pathInput").addEventListener("keydown", e => {
  if (e.key === "Enter") openPath($("#pathInput").value);
});

const browser = $("#browser"), overlay = $("#overlay");
function showBrowser() {
  browser.classList.add("on"); overlay.classList.add("on");
  listDir($("#dirInput").value);
}
function hideBrowser() { browser.classList.remove("on"); overlay.classList.remove("on"); }
$("#btnBrowse").addEventListener("click", showBrowser);
$("#btnCloseBrowser").addEventListener("click", hideBrowser);
overlay.addEventListener("click", hideBrowser);
function parentDir(p) {
  p = p.replace(/[\\/]+$/, "");
  const i = Math.max(p.lastIndexOf("\\"), p.lastIndexOf("/"));
  return i > 3 ? p.slice(0, i) : p;
}
$("#btnUp").addEventListener("click", () => {
  const d = parentDir($("#dirInput").value);
  $("#dirInput").value = d; listDir(d);
});
$("#btnGoDir").addEventListener("click", () => listDir($("#dirInput").value));
$("#dirInput").addEventListener("keydown", e => {
  if (e.key === "Enter") listDir($("#dirInput").value);
});
async function listDir(d) {
  const wrap = $("#filelist");
  wrap.innerHTML = '<div class="btip">读取中…</div>';
  try {
    const r = await api("/api/list?dir=" + encodeURIComponent(d));
    $("#dirInput").value = r.dir;
    wrap.innerHTML = "";
    if (!r.files.length) wrap.innerHTML = '<div class="btip">此目录下没有 md 文件</div>';
    for (const f of r.files) {
      const row = document.createElement("div");
      row.className = "frow";
      const dt = new Date(f.mtime * 1000);
      row.innerHTML = `<span class="fn">${esc(f.path)}</span>`
        + `<span class="fm">${(f.size / 1024).toFixed(1)}KB · ${dt.toLocaleString()}</span>`;
      row.addEventListener("click", () => { hideBrowser(); openPath(f.path); });
      wrap.appendChild(row);
    }
  } catch (e) {
    wrap.innerHTML = `<div class="btip">读取失败: ${esc(e.message)}</div>`;
  }
}

/* ================= 📜 版本历史（快照/行级 diff/回滚） ================= */
const histModal = $("#histModal");
let histSel = null;

function currentText() {
  return S.blocks.map(b => (b.raw || "") + "\n".repeat(b.gap || 1)).join("");
}

function lineDiff(oldText, newText) {
  /* 行级 LCS diff——审阅稿都是几百行内，O(n·m) 直接上；超 600 行退化为纯展示 */
  const a = oldText.split("\n"), b = newText.split("\n");
  if (a.length > 600 || b.length > 600) {
    return a.map(l => `<span class="dl-ctx">${esc(l)}</span>`).join("\n");
  }
  const n = a.length, m = b.length;
  const dp = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1));
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--)
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1
                               : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const out = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) { out.push(`<span class="dl-ctx">  ${esc(a[i])}</span>`); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { out.push(`<span class="dl-del">- ${esc(a[i])}</span>`); i++; }
    else { out.push(`<span class="dl-add">+ ${esc(b[j])}</span>`); j++; }
  }
  while (i < n) { out.push(`<span class="dl-del">- ${esc(a[i])}</span>`); i++; }
  while (j < m) { out.push(`<span class="dl-add">+ ${esc(b[j])}</span>`); j++; }
  return out.join("\n");
}

function fmtSnap(name) {
  const m = name.match(/^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})(?:_(\d+))?\.md$/);
  if (!m) return name;
  return `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}:${m[6]}`
    + (m[7] ? ` (#${m[7]})` : "");
}

async function showHistory() {
  if (!S.path) { toast("先打开文件"); return; }
  histModal.classList.add("on"); overlay.classList.add("on");
  histSel = null;
  $("#btnRollback").disabled = true;
  $("#histDiff").classList.remove("on");
  const wrap = $("#histList");
  wrap.innerHTML = '<div class="btip">读取中…</div>';
  try {
    const r = await api("/api/history?path=" + encodeURIComponent(S.path));
    $("#histTitle").textContent = `📜 历史版本（${r.files.length}）`;
    if (!r.files.length) {
      wrap.innerHTML = '<div class="btip">还没有历史——每次保存会自动快照改动前的版本</div>';
      return;
    }
    wrap.innerHTML = "";
    for (const f of r.files) {
      const row = document.createElement("div");
      row.className = "frow";
      row.dataset.name = f.name;
      row.innerHTML = `<span class="fn">🕐 ${esc(fmtSnap(f.name))}（改动前的版本）</span>`
        + `<span class="fm">${(f.size / 1024).toFixed(1)}KB</span>`;
      row.addEventListener("click", () => loadSnapshot(f.name, row));
      wrap.appendChild(row);
    }
  } catch (e) {
    wrap.innerHTML = `<div class="btip">读取失败: ${esc(e.message)}</div>`;
  }
}

async function loadSnapshot(name, row) {
  histSel = name;
  [...$("#histList").querySelectorAll(".frow")].forEach(x => x.classList.remove("sel"));
  row.classList.add("sel");
  try {
    const r = await api("/api/history_get?path=" + encodeURIComponent(S.path)
      + "&name=" + encodeURIComponent(name));
    $("#histDiff").innerHTML =
      `<span class="dl-ctx">快照 ${fmtSnap(name)} vs 当前 —— 红=这版有/现在没了，绿=现在有/这版没有</span>\n`
      + lineDiff(r.content, currentText());
    $("#histDiff").classList.add("on");
    $("#histDiff").classList.remove("hidden");
    $("#btnRollback").disabled = false;
  } catch (e) {
    toast("读快照失败：" + e.message, true);
  }
}

$("#btnHist").addEventListener("click", showHistory);
$("#btnHistClose").addEventListener("click", () => {
  histModal.classList.remove("on"); overlay.classList.remove("on");
});
$("#btnRollback").addEventListener("click", async () => {
  if (!histSel) return;
  if (!confirm(`把稿子回滚到 ${fmtSnap(histSel)}？\n（当前版本会先自动快照，随时能滚回来）`)) return;
  try {
    await api("/api/rollback", { path: S.path, name: histSel });
    toast("已回滚，正在重新加载…");
    histModal.classList.remove("on"); overlay.classList.remove("on");
    await openPath(S.path);
  } catch (e) {
    toast("回滚失败：" + e.message, true);
  }
});

/* ================= 批注悬停卡片（自绘，即时显示） ================= */
const mktip = $("#mktip");
function hideMktip() { mktip.classList.remove("on"); }
document.addEventListener("mouseover", e => {
  const mk = e.target && e.target.closest && e.target.closest(".mk");
  if (!mk) { hideMktip(); return; }
  const c = S.review.comments.find(x => x.id === mk.dataset.cid);
  if (!c) { hideMktip(); return; }
  mktip.innerHTML =
    `<div class="tt-head"><span class="cbadge ty-${c.type}">${TY_NAME[c.type] || c.type}</span></div>`
    + (c.quote ? `<div class="tt-quote">「${esc(c.quote)}」</div>` : "")
    + (c.type === "replace" && c.suggestion ? `<div class="tt-sug">改为：${esc(c.suggestion)}</div>` : "")
    + (c.note ? `<div class="tt-note">${esc(c.note)}</div>` : "");
  mktip.classList.add("on");
  const r = mk.getBoundingClientRect();
  mktip.style.top = Math.max(6, r.top - mktip.offsetHeight - 8) + "px";
  mktip.style.left =
    Math.min(window.innerWidth - mktip.offsetWidth - 8,
             Math.max(8, r.left)) + "px";
});
window.addEventListener("scroll", hideMktip, true);

/* ================= 启动 ================= */
(async function init() {
  renderRecent();
  try {
    const cfg = await api("/api/config");
    if (cfg.default_dir) $("#dirInput").value = cfg.default_dir;
  } catch (e) { /* 服务端旧版无所谓 */ }
  setStatus("待打开文件");
})();
