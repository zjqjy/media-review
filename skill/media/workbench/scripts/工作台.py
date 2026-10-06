#!/usr/bin/env python3
"""工作台.py — 口播脚本 → 素材生产工作台（单文件 HTML）

工作流（口播先行）:
1. 口播脚本先定稿（源头，分节表格）
2. 运行本脚本生成工作台：口播每行 = 一个生产任务，固定编号 R01/R02/…
3. 按行制作素材，产出文件名以行号开头（如 R07_字幕卡.html），放进对应目录
4. 网页里「📂 授权项目目录」→ 状态读写 workbench_state.json（落盘），
   ZCode / Claude Code 按同目录协议直接读写 —— 双向无缝
5. 全部行「完成」→ 进剪辑

用法: python 工作台.py <口播脚本.md> [项目根目录]
"""
import io
import json
import os
import re
import sys

def parse_md(path):
    sections = []
    cur = None
    for raw in io.open(path, encoding="utf-8"):
        line = raw.rstrip("\n")
        if line.startswith("## "):
            cur = {"title": line[3:].strip(), "rows": []}
            sections.append(cur)
            continue
        if cur is None or not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        if cells[0] in ("时间轴", "拍"):
            continue
        if re.fullmatch(r"[-—: ]*", cells[0]):
            continue
        if cells[0].startswith("时间轴") or cells[0].startswith("拍"):
            continue
        cur["rows"].append({"t": cells[0], "voice": cells[1], "visual": cells[2] if len(cells) > 2 else ""})
    no = 1
    for sec in sections:
        for r in sec["rows"]:
            r["no"] = "R%02d" % no
            no += 1
    return sections

def scan(root):
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in filenames:
            rel = os.path.relpath(os.path.join(dirpath, fn), root).replace("\\", "/")
            files.append(rel)
    return sorted(files)

TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>素材生产工作台 — __ROOT__</title>
<style>
  body { background:#0e1116; color:#e8eaed; font-family:"Microsoft YaHei",sans-serif; margin:0; display:flex; height:100vh; }
  #side { width:290px; background:#161a20; padding:14px; overflow:auto; border-right:1px solid #23282f; box-sizing:border-box; }
  #side h3 { font-size:13px; color:#9aa0a6; margin:14px 0 6px; }
  #side .f { font-size:12px; color:#c8cad0; padding:2px 4px; border-radius:4px; cursor:pointer; word-break:break-all; }
  #side .f:hover { background:#23282f; }
  #main { flex:1; padding:18px 22px; overflow:auto; box-sizing:border-box; }
  h1 { font-size:19px; margin:0 0 4px; }
  #meta { color:#9aa0a6; font-size:12px; margin-bottom:10px; display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
  #stats { color:#3ddc84; font-size:12px; }
  #q { background:#1f1f1f; border:1px solid #333; color:#e8eaed; padding:6px 10px; border-radius:8px; width:220px; font-size:13px; }
  .btn { cursor:pointer; background:#232030; color:#c8cad0; border:1px solid #4c4965; padding:5px 12px; border-radius:8px; font-size:12px; }
  .btn:hover { background:#2e2a3e; }
  #conn { font-size:12px; }
  h2 { font-size:15px; color:#6f8af6; margin:20px 0 8px; border-left:3px solid #6f8af6; padding-left:8px; }
  .row { background:#1a1e24; border-radius:10px; padding:10px 14px; margin:8px 0; }
  .row.todo { border:1px solid #4a3b3b; }
  .no { display:inline-block; background:#2a3140; color:#7ab3ff; font-size:11px; padding:1px 8px; border-radius:8px; margin-right:8px; font-family:Consolas,monospace; }
  .t { color:#9aa0a6; font-size:12px; margin-right:8px; }
  .voice { font-size:14px; margin:4px 0; }
  .visual { color:#9aa0a6; font-size:12px; margin:4px 0; }
  .need { display:flex; gap:6px; flex-wrap:wrap; margin:4px 0; }
  .ntag { font-size:11px; padding:1px 8px; border-radius:8px; background:#232030; color:#8b93ff; }
  .files { font-size:12px; margin:4px 0; }
  .files a { color:#7be382; text-decoration:none; margin-right:10px; }
  .none { color:#5a6470; font-size:12px; }
  .ops { margin-top:6px; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
  .chip { cursor:pointer; font-size:11px; padding:2px 10px; border-radius:10px; border:1px solid #444; color:#9aa0a6; }
  .chip.wip { color:#ffd54d; border-color:#6b5d1f; }
  .chip.done { color:#7be382; border-color:#2c5e37; }
  .hint { color:#5a6470; font-size:11px; margin-top:4px; font-family:Consolas,monospace; }
  #help { background:#161a20; border:1px solid #2a2f36; border-radius:10px; padding:12px 16px; margin-bottom:14px; font-size:13px; color:#c8cad0; }
  #help summary { cursor:pointer; color:#9aa0a6; }
  #help ol { margin:8px 0 0 18px; padding:0; }
  #help li { margin:4px 0; }
  #help code { color:#7ab3ff; }
</style></head><body>
<div id="side">
  <h3>项目文件</h3>
  <div style="margin:6px 0"><button id="authbtn" class="btn" style="width:100%">📂 授权项目目录</button></div>
  <div id="tree"></div>
</div>
<div id="main">
  <h1>素材生产工作台 — __ROOT__</h1>
  <div id="meta">口播(定稿): __SCRIPT__
    <button id="mdbtn" class="btn">📄 载入口播 md（知识库）</button>
    <input type="file" id="md" accept=".md,.txt" multiple style="display:none">
    <input type="text" id="q" placeholder="过滤口播/画面关键词…">
    <span id="conn"></span>
    <span id="stats"></span>
  </div>
  <details id="help">
    <summary>工作流 + AI 联动（点开）</summary>
    <ol>
      <li>口播脚本<b>先定稿</b>：每行 = 生产任务，编号 <code>R01/R02/…</code> 固定</li>
      <li>点「<b>📂 授权项目目录</b>」（Chrome/Edge，建议用 localhost 打开本页）→ 状态落盘到 <code>workbench_state.json</code></li>
      <li>按行制作素材：产出文件名以行号开头（<code>R07_字幕卡.html</code>），放对应目录（01/02/03），点重扫自动挂接；也可以直接让 <b>ZCode / Claude</b>：「把 R07 的字幕卡做了」——它按同目录协议产出并更新状态</li>
      <li>行状态: 未制作 → 已产出（文件挂上）→ 完成（人验收后点）。全部完成 = 进剪辑</li>
    </ol>
  </details>
  <div id="content"></div>
</div>
<script>
const DATA = __DATA__;
const STATE_FILE = "workbench_state.json";
const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;");

let dirHandle = null;                 // File System Access 句柄 (Chromium)
let files = DATA.files.slice();
let S = {};                           // 行状态 {R07: {st:"已产出"}}

/* ── IndexedDB: 持久化目录句柄 ── */
function idbOpen() {
  return new Promise((res, rej) => {
    const r = indexedDB.open("wb", 1);
    r.onupgradeneeded = () => r.result.createObjectStore("kv");
    r.onsuccess = () => res(r.result);
    r.onerror = () => rej(r.error);
  });
}
async function idbSet(k, v) {
  const db = await idbOpen();
  return new Promise((res, rej) => {
    const tx = db.transaction("kv", "readwrite");
    tx.objectStore("kv").put(v, k);
    tx.oncomplete = () => res();
    tx.onerror = () => rej(tx.error);
  });
}
async function idbGet(k) {
  const db = await idbOpen();
  return new Promise((res, rej) => {
    const tx = db.transaction("kv", "readonly");
    const q = tx.objectStore("kv").get(k);
    q.onsuccess = () => res(q.result);
    q.onerror = () => rej(q.error);
  });
}

/* ── 目录授权 / 扫描 / 状态落盘 ── */
$("#authbtn").onclick = async () => {
  if (!window.showDirectoryPicker) {
    alert("当前浏览器不支持目录授权（需 Chrome/Edge，且本页用 http://localhost:8765/ 打开）。退化为只读模式。");
    return;
  }
  try {
    dirHandle = await window.showDirectoryPicker({ mode: "readwrite" });
    await idbSet("dir", dirHandle);
    await syncFromDir();
  } catch (e) { /* 用户取消 */ }
};
async function syncFromDir() {
  files = [];
  for await (const entry of dirHandle.values()) {
    if (entry.kind === "file") files.push(entry.name);
    else if (entry.kind === "directory") {
      for await (const f of entry.values()) {
        if (f.kind === "file") files.push(entry.name + "/" + f.name);
      }
    }
  }
  files.sort();
  try {
    const fh = await dirHandle.getFileHandle(STATE_FILE);
    S = (JSON.parse(await (await fh.getFile()).text()).rows) || {};
  } catch (e) { S = S || {}; }
  $("#conn").textContent = "● 已连接: " + dirHandle.name;
  renderTree(); render($("#q").value);
}
let saveTimer = null;
async function saveState() {
  if (!dirHandle) return;
  const payload = { updated: new Date().toISOString(), rows: S };
  try {
    const fh = await dirHandle.getFileHandle(STATE_FILE, { create: true });
    const w = await fh.createWritable();
    await w.write(JSON.stringify(payload, null, 2));
    await w.close();
  } catch (e) { console.warn("state 写盘失败", e); }
}
function markDirty() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveState, 400);
}

/* ── 素材需求 → 类型目录 ── */
function needDirs(visual) {
  const t = [];
  if (/字幕卡|HTML|卡/.test(visual)) t.push("01_字幕卡_HTML");
  if (/动效|动画|Remotion|motion/i.test(visual)) t.push("02_动效视频");
  if (/实拍|真机|录屏|拍摄|照片/.test(visual)) t.push("03_实拍素材");
  if (/口播|录音/.test(visual)) t.push("00_口播");
  return t.length ? t : ["03_实拍素材"];
}
function tokens(s) {
  const out = new Set();
  (String(s).match(/[\u4e00-\u9fff]{2,}/g) || []).forEach(w => {
    for (let i = 0; i < w.length - 1; i++) out.add(w.slice(i, i + 2));
  });
  (String(s).match(/[A-Za-z0-9]+/g) || []).forEach(w => out.add(w.toLowerCase()));
  return out;
}
/* 行号优先挂接: 文件名以 R07 开头 → 归 R07; 否则目录兜底 */
function matchFiles(row) {
  const dirs = needDirs(row.visual);
  const prefix = row.no.toLowerCase();
  const hit = files.filter(f => {
    const base = f.split("/").pop().toLowerCase();
    return base.startsWith(prefix) && dirs.some(d => f.startsWith(d + "/"));
  });
  if (hit.length) return hit;
  const toks = tokens(row.voice + " " + row.visual);
  return files.filter(f => {
    if (!dirs.some(d => f.startsWith(d + "/"))) return false;
    const ft = tokens(f);
    let n = 0;
    toks.forEach(t => { if (ft.has(t) || f.includes(t)) n += 2; });
    return n >= 4;
  });
}
function rowState(row) {
  if (S[row.no] && S[row.no].st) return S[row.no].st;
  return matchFiles(row).length ? "已产出" : "未制作";
}
function rowKey(row) { return row.no; }

/* ── 文件树 ── */
function renderTree() {
  const tree = {};
  files.forEach(f => { const top = f.split("/")[0]; (tree[top] = tree[top] || []).push(f); });
  $("#tree").innerHTML = Object.keys(tree).sort().map(top =>
    `<h3>${top}/ (${tree[top].length})</h3>` +
    tree[top].map(f => `<div class="f" title="${f}">${f.split("/").pop()}</div>`).join("")
  ).join("");
}
renderTree();

/* ── 载入口播 md（知识库里的口播是源头，面板直接吃） ── */
function parseMd(text) {
  const sections = [];
  let cur = null;
  let no = 1;
  text.split(/\r?\n/).forEach(line => {
    line = line.replace(/\s+$/, "");
    if (line.startsWith("## ")) {
      cur = { title: line.slice(3).trim(), rows: [] };
      sections.push(cur);
      return;
    }
    if (!cur || !line.trim().startsWith("|")) return;
    const cells = line.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim());
    if (cells.length < 3) return;
    if (cells[0] === "时间轴" || cells[0] === "拍") return;
    if (/^[-—: ]*$/.test(cells[0])) return;
    if (cells[0].startsWith("时间轴") || cells[0].startsWith("拍")) return;
    cur.rows.push({ t: cells[0], voice: cells[1], visual: cells[2] || "", no: "R" + String(no).padStart(2, "0") });
    no++;
  });
  return sections;
}
$("#mdbtn").onclick = () => $("#md").click();
$("#md").onchange = async e => {
  const f = e.target.files[0];
  if (!f) return;
  const text = await f.text();
  DATA.sections = parseMd(text);
  DATA.script = f.name;
  const n = DATA.sections.reduce((a, s) => a + s.rows.length, 0);
  flash(`口播已载入: ${f.name}（${n} 行）`);
  render($("#q").value);
};

/* ── 渲染 ── */
const CHIP = { "未制作": "chip", "已产出": "chip wip", "制作中": "chip wip", "完成": "chip done" };
function render(q) {
  q = (q || "").trim();
  let done = 0, total = 0, todo = 0;
  let html = "";
  DATA.sections.forEach((sec, si) => {
    const rows = sec.rows.filter(r => !q || (r.voice + r.visual + r.t + sec.title).includes(q) || sec.title.includes(q));
    if (!rows.length) return;
    html += `<h2>${esc(sec.title)}</h2>`;
    rows.forEach(row => {
      total++;
      const st = rowState(row);
      if (st === "完成") done++;
      if (st === "未制作") todo++;
      const attached = matchFiles(row);
      const needs = needDirs(row.visual).map(d => `<span class="ntag">${d.split("_")[0]}</span>`).join("");
      const fileLine = attached.length
        ? `<div class="files">📎 ${attached.map(f => `<a href="#" data-f="${f}">${f.split("/").pop()}</a>`).join("")}</div>`
        : `<div class="none">未产出 — 命名以 <b>${row.no}_</b> 开头放 ${needDirs(row.visual)[0]}/</div>`;
      html += `<div class="row ${st === "未制作" ? "todo" : ""}">
        <span class="no">${row.no}</span><span class="t">${esc(row.t)}</span>
        <div class="voice">${esc(row.voice)}</div>
        ${row.visual ? `<div class="visual">素材需求: ${esc(row.visual)}</div>` : ""}
        <div class="need">${needs}</div>
        ${fileLine}
        <div class="ops">
          <span class="chip ${CHIP[st]}" data-no="${row.no}" data-cur="${st}">${st}</span>
          ${attached.length ? `<span class="btn" data-open="${attached[0]}">打开</span>` : ""}
        </div>
        <div class="hint">产出命名: ${row.no}_名称.扩展名 → ${needDirs(row.visual)[0]}/ · 或直接对 ZCode/Claude:「做 ${row.no}」</div>
      </div>`;
    });
  });
  $("#content").innerHTML = html;
  $("#stats").textContent = `${total} 行 · 完成 ${done} · 待做 ${todo}`;
  bind();
}

function flash(msg) {
  const el = document.getElementById("conn");
  const old = el.textContent;
  el.textContent = "● " + msg;
  setTimeout(() => { el.textContent = old; }, 1600);
}
function bind() {
  document.querySelectorAll(".chip").forEach(el => el.onclick = async () => {
    const no = el.dataset.no;
    const row = findRow(no);
    const next = { "未制作": "制作中", "已产出": "完成", "制作中": "完成", "完成": "未制作" }[el.dataset.cur];
    S[no] = { st: next };
    await saveState();
    render($("#q").value);
  });
  document.querySelectorAll("[data-open]").forEach(el => el.onclick = () => {
    const f = el.dataset.open;
    alert(files.includes(f) ? "文件: " + f : "未找到: " + f);
  });
  document.querySelectorAll(".files a").forEach(el => el.onclick = e => {
    e.preventDefault();
    alert("文件: " + el.dataset.f);
  });
}
function findRow(no) {
  for (const sec of DATA.sections) for (const r of sec.rows) if (r.no === no) return r;
  return null;
}

/* 启动: 恢复句柄 → 自动重连目录 */
(async () => {
  try {
    const h = await idbGet("dir");
    if (h) {
      const p = await h.queryPermission({ mode: "readwrite" });
      if (p === "granted") { dirHandle = h; await syncFromDir(); }
      else { $("#authbtn").textContent = "📂 重新授权项目目录"; }
    }
  } catch (e) { console.warn(e); }
})();
</script></body></html>"""

def main():
    if len(sys.argv) < 2:
        raise SystemExit("用法: python 工作台.py <口播脚本.md> [项目根目录]")
    md_path = sys.argv[1]
    root = sys.argv[2] if len(sys.argv) > 2 else os.getcwd()
    sections = parse_md(md_path)
    files = scan(root)
    rows = sum(len(s["rows"]) for s in sections)
    data = {
        "root": os.path.basename(os.path.abspath(root)),
        "script": os.path.basename(md_path),
        "sections": sections,
        "files": files,
    }
    html = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False)).replace("__ROOT__", data["root"])
    out = os.path.join(root, "workbench.html")
    io.open(out, "w", encoding="utf-8").write(html)
    print(f"工作台 → {out}")
    print(f"  口播已定稿: {len(sections)} 节 · {rows} 个生产任务 (R01~R{rows:02d}) · {len(files)} 个已有文件")
    print("  打开方式: 双击 workbench.html（file:// 下目录授权可用，建议 Chrome/Edge）")
    print("  AI 联动: 对 ZCode/Claude 说「做 R07」——协议见页面底部说明与 workbench SKILL.md")

if __name__ == "__main__":
    main()
