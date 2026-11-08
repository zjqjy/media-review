// 小红书快发驱动器 v1 —— 单进程全程，STOP-BEFORE-PUBLISH
const T0 = Date.now();
const ts = (m) => console.log(`[${((Date.now() - T0) / 1000).toFixed(1)}s] ${m}`);
const VIDEO = "D:/DeskTop/WorkSpace/embedai/视频/20261101_ego浏览器/04_成片/20261101_ego浏览器_精简中_成片.mp4";
const COVER_34 = "D:/DeskTop/WorkSpace/embedai/视频/20261101_ego浏览器/04_成片/20261101_ego浏览器_精简中_3x4.png";
const TITLE = "AI替我上网打工！Agent浏览器";
const DESC_MAIN = "🔥AI 真的替我上网打工了！\nAgent 浏览器 ego lite 实测：安装→登录保持→分屏并行→自动接任务，全程 AI 替我操作网页😎";
const TOPICS = ["AI工具", "Agent", "浏览器", "效率神器", "ego"];
const blockers = [];
const topicsAttached = [];
const SPACE = `fast-xhs-${Date.now() % 1000000}`;
const task = await taskSpace(SPACE);
const page = task.page("p1");
await page.goto("https://creator.xiaohongshu.com/publish/publish?from=menu&target=video", { timeout: 60000 });
await page.waitForLoadState("load", { timeout: 30000 }).catch(() => {});
// 窗口可见性闸门：最小化=渲染冻结，真点击/文件弹窗全部失效
{
  const vis = await page.evaluate("(() => ({w: window.innerWidth, h: window.innerHeight}))()");
  if (vis.w === 0 || vis.h === 0) {
    console.log(JSON.stringify({ platform: "xhs", ok: false, why: "ego 窗口最小化中——请还原窗口保持可见后再跑（渲染冻结会让点击/弹窗/截图全部失效）" }));
    process.exit(0);
  }
}
await page.waitForTimeout(2500);
if ((await page.url()).includes("/login")) { console.log(JSON.stringify({ platform: "xhs", ok: false, why: "掉登录", blockers })); process.exit(0); }
ts("页面就绪");
// 上传：找「上传视频」按钮量坐标→真鼠标点→选择器
const rc = await page.evaluate(
  "(() => { const bs = Array.from(document.querySelectorAll('button')).filter(b => b.textContent.trim()==='上传视频'); if (!bs.length) return null; const r = bs[bs.length-1].getBoundingClientRect(); return [Math.round(r.x + r.width/2), Math.round(r.y + r.height/2)]; })()");
if (!rc) { console.log(JSON.stringify({ platform: "xhs", ok: false, why: "上传按钮没找到", blockers })); process.exit(0); }
const chP = page.waitForFileChooser({ timeout: 20000 });
await page.mouse.click(rc[0], rc[1], { label: "上传视频" });
(await chP).setFiles(VIDEO);
ts("285MB 视频提交上传");
// 等表单（标题框出现=进入发布表单）
await page.waitForSelector('input[placeholder*="填写标题"]', { timeout: 600000 });
ts("表单出现");
// 标题
await page.fill('input[placeholder*="填写标题"]', TITLE);
ts("标题 ✓");
// 正文（浮层拦 pointer → focus+keyboard）
await page.evaluate(
  "(() => { const els = Array.from(document.querySelectorAll('[contenteditable=true]')); const el = els.find(e => (e.textContent||'').includes('输入正文描述')) || els[els.length-1]; if (!el) return 'nf'; el.scrollIntoView({block:'center'}); el.focus(); return 'ok'; })()");
await page.waitForTimeout(400);
await page.keyboard.type(DESC_MAIN + " ", { delay: 3 });
for (const t of TOPICS) {
  await page.keyboard.type("#", { delay: 60 });
  await page.waitForTimeout(1800);
  // 重试环：联想行没渲染就再等 2s 重查（最小化渲染抖动）
  // 联想策略：精确项优先，没有就点第一条推荐（模糊挂比不挂强），记录实际挂上的话题
  let hit = null;
  for (let k = 0; k < 2 && !hit; k++) {
    if (k > 0) await page.waitForTimeout(2000);
    hit = await page.evaluate(
    (w) => { const rows = Array.from(document.querySelectorAll('*')).filter(n => n.children.length === 0 && /^#[^#\s]{1,20}$/.test(n.textContent.trim()) && !n.closest('[contenteditable]') && n.getBoundingClientRect().width > 30); const exact = rows.find(n => n.textContent.trim() === "#" + w); const target = exact || rows[0]; if (!target) return null; target.click(); return target.textContent.trim(); }, t);
    if (hit && hit.area === undefined) hit = String(hit);
    if (hit) { topicsAttached.push(typeof hit === "string" ? hit : hit.txt); }
    else { hit = null; }
  }
  if (hit) { /* attached */ }
  else { await page.keyboard.type(t + " ", { delay: 15 }); blockers.push("话题[" + t + "]：联想行没渲染，退化为文字"); }
  await page.waitForTimeout(700);
}
await page.keyboard.press("Escape");
ts("正文+话题 ✓");
// 声明 DOM-only（最小化免疫）：原创声明开关 + 内容类型声明=笔记含AI合成内容（用户口径）
try {
  await page.evaluate(
    "(() => { const all = Array.from(document.querySelectorAll('*')).filter(n => n.children.length===0 && n.textContent.trim()==='原创声明'); if (!all.length) return; const tgl = all[all.length-1].parentElement.querySelector('[class*=switch],[role=switch],input[type=checkbox]'); if (tgl) tgl.click(); return 1; })()");
  await page.waitForTimeout(600);
  await page.evaluate(
    "(() => { const all = Array.from(document.querySelectorAll('*')).filter(n => (n.textContent||'').includes('内容类型声明')); if (!all.length) return; const el = all[all.length-1]; el.click(); return 1; })()");
  await page.waitForTimeout(1200);
  const opt = await page.evaluate(
    "(() => { const all = Array.from(document.querySelectorAll('*')).filter(n => n.children.length===0 && n.textContent.trim()==='笔记含AI合成内容'); if (!all.length) return 'no-opt'; const el = all[all.length-1]; el.click(); return 'ok'; })()");
  if (opt === "ok") ts("声明=笔记含AI合成内容 ✓");
  else blockers.push("内容类型声明选项没找到（" + opt + "）");
} catch (e) { blockers.push("声明：" + String(e).slice(0, 50)); }
// 封面（最小化免疫·实测通）：点 ai-cover-recommend 容器本体直接开编辑器（无需 hover/胶囊）
try {
  await page.evaluate(
    "(() => { const all = Array.from(document.querySelectorAll('*')).filter(n => n.children.length===0 && n.textContent.trim()==='设置封面'); if (all.length) { let sec = all[0].parentElement; for (let d = 0; d < 5; d++) sec = sec.parentElement; sec.scrollIntoView({block:'center'}); } return 1; })()");
  await page.waitForTimeout(1000);
  // 视频处理中时容器点了没反应：点-等-查重试环（最多 ~35s）
  let ed = "closed";
  for (let k = 0; k < 20 && ed !== "open"; k++) {
    await page.waitForTimeout(6000);
    const st = await page.evaluate(
      "(() => { const el = document.querySelector('[class*=ai-cover-recommend]'); if (!el) return {rc: null, state: '容器不在'}; const r = el.getBoundingClientRect(); if (r.y < 0 || r.y > 700) return {rc: null, state: '在视口外 y=' + Math.round(r.y)}; const generating = el.textContent.includes('生成中'); return {rc: [Math.round(r.x + r.width/2), Math.round(r.y + r.height/2)], state: generating ? '生成中' : '就绪'}; })()");
    console.log(`[封面] 第${k + 1}次: ${st.state}`);
    if (!st.rc) continue;
    if (st.state === "生成中") continue;
    await page.mouse.click(st.rc[0], st.rc[1], { label: "点封面容器开编辑器" });
    await page.waitForTimeout(2500);
    ed = await page.evaluate("(() => document.querySelector('input[aria-label=\"上传封面图片\"]') ? 'open' : 'closed')");
  }
  if (ed !== "open") throw new Error("编辑器120s没开（生成中/入口变化）");
  await page.setInputFiles('input[aria-label="上传封面图片"]', [COVER_34]);
  await page.waitForTimeout(3000);
  await page.evaluate("(() => { const bs = Array.from(document.querySelectorAll('button')).filter(b => b.textContent.trim()==='完成' && b.offsetWidth > 0); const b = bs[bs.length-1]; if (b) { const rk = Object.keys(b).find(k => k.startsWith('__reactProps')); if (rk && typeof b[rk].onClick === 'function') b[rk].onClick({preventDefault(){},stopPropagation(){}}); else b.click(); } return 1; })()");
  await page.waitForTimeout(2500);
  const vfy = await page.evaluate(
    "(() => { const all = Array.from(document.querySelectorAll('*')).filter(n => n.children.length===0 && n.textContent.trim()==='设置封面'); let sec = all[0].parentElement; for (let d = 0; d < 5; d++) sec = sec.parentElement; const big = Array.from(sec.querySelectorAll('img')).map(i => (i.src||'')).sort((a,b) => b.length - a.length)[0]; return big.startsWith('http'); })()");
  if (vfy) ts("封面 3x4 ✓（缩略图已换 CDN 图，最小化全程可用）");
  else blockers.push("封面：塞了但缩略图未确认换成 CDN 图");
} catch (e) { blockers.push("封面：" + String(e).slice(0, 60) + "（默认首帧兜底）"); }
// STOP-BEFORE-PUBLISH
const shot = await page.screenshot({ path: "C:/Users/23393/ego/fast-xhs-e1-20261108/final.png" }).catch(() => null);
ts("STOP 在「发布」前");
console.log(JSON.stringify({
  platform: "xhs", ok: true, elapsedSec: +((Date.now() - T0) / 1000).toFixed(1),
  screenshot: shot || "shotFailed", blockers,
  publishButton: "发布（未点）", topicsAttached,
}));
