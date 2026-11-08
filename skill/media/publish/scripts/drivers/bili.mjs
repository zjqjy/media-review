// B站快发驱动器 v1 —— 单进程全程，STOP-BEFORE-PUBLISH
const T0 = Date.now();
const ts = (m) => console.log(`[${((Date.now() - T0) / 1000).toFixed(1)}s] ${m}`);
const VIDEO = "D:/DeskTop/WorkSpace/embedai/视频/20261101_ego浏览器/04_成片/20261101_ego浏览器_精简中_成片.mp4";
const COVER_43 = "D:/DeskTop/WorkSpace/embedai/视频/20261101_ego浏览器/04_成片/20261101_ego浏览器_精简中_4x3.png";
const COVER_169 = "D:/DeskTop/WorkSpace/embedai/视频/20261101_ego浏览器/04_成片/20261101_ego浏览器_精简中_16x9.png";
const TITLE = "AI替我上网打工！当下最好用的 Agent 浏览器：ego lite 实测";
const DESC = "ego lite 是当下最好用的 Agent 浏览器：给浏览器装上手脚，让 Codex / ChatGPT / Claude Code 直接替你上网干活。本期实测：安装与登录保持、分屏并行干活、官方数据看板、还有让它自己去接「大肥鱼」任务的完整流程。搭配 ego-browser skill，AI 替你把网页上的活全干了。";
const TAGS = ["ego", "Agent浏览器", "AI工具", "效率工具"];
const blockers = [];
const SPACE = `fast-bili-${Date.now() % 1000000}`;
const task = await taskSpace(SPACE);
const page = task.page("p1");
await page.goto("https://member.bilibili.com/platform/upload/video/frame", { timeout: 60000 });
await page.waitForLoadState("load", { timeout: 30000 }).catch(() => {});
if ((await page.url()).includes("passport")) {
  console.log(JSON.stringify({ platform: "bilibili", ok: false, why: "掉登录", blockers }));
  process.exit(0);
}
ts("页面就绪");
// 上传：量上传区坐标 → 真鼠标点 → 选择器塞片
const rc = await page.evaluate(
  "(() => { const all = Array.from(document.querySelectorAll('*')).filter(n => n.children.length===0 && (n.textContent.trim()==='点击上传或将视频拖拽到此区域'||n.textContent.trim()==='上传视频')); if (!all.length) return null; const r = all[0].getBoundingClientRect(); return [Math.round(r.x + r.width/2), Math.round(r.y + r.height/2)]; })()");
if (!rc) { console.log(JSON.stringify({ platform: "bilibili", ok: false, elapsedSec: +((Date.now() - T0) / 1000).toFixed(1), why: "上传区没找到（页面状态不对）", blockers })); process.exit(0); }
const chP = page.waitForFileChooser({ timeout: 20000 });
await page.mouse.click(rc[0], rc[1], { label: "上传区" });
(await chP).setFiles(VIDEO);
ts("285MB 视频提交上传（边传边填）");
// 表单出现即开始填（不必等上传完）
await page.waitForSelector('input[placeholder="请输入稿件标题"]', { timeout: 600000 });
ts("表单出现");
// 标题
await page.evaluate("(() => { const el = document.querySelector('input[placeholder=\"请输入稿件标题\"]'); el.scrollIntoView({block:'center'}); el.focus(); return 1; })()");
await page.waitForTimeout(400);
await page.fill('input[placeholder="请输入稿件标题"]', TITLE);
ts("标题 ✓");
// 简介（contenteditable）
await page.evaluate(
  "(() => { const els = Array.from(document.querySelectorAll('[contenteditable=true]')); const el = els.find(e => (e.getAttribute('placeholder')||'').includes('填写更全面') || (e.textContent||'').includes('填写更全面')) || els[0]; if (!el) return 'nf'; el.scrollIntoView({block:'center'}); el.focus(); return 'ok'; })()");
await page.waitForTimeout(400);
await page.keyboard.type(DESC, { delay: 5 });
ts("简介 ✓");
// 标签（注意：重复=静默忽略，逐个回车后看配额）
await page.evaluate("(() => { const el = document.querySelector('input[placeholder=\"按回车键Enter创建标签\"]'); if (el) el.scrollIntoView({block:'center'}); return 1; })()");
await page.waitForTimeout(300);
for (const t of TAGS) {
  try { await page.fill('input[placeholder="按回车键Enter创建标签"]', t); await page.keyboard.press("Enter"); await page.waitForTimeout(400); } catch (e) { blockers.push("标签[" + t + "]：" + String(e).slice(0, 40)); }
}
ts("标签 ✓");
// 分区：若为空选科技数码（表单可能已默认）
try {
  const cat = await page.evaluate(
    "(() => { const all = Array.from(document.querySelectorAll('*')).filter(n => n.children.length===0 && n.textContent.trim()==='分区'); if (!all.length) return 'none'; const sec = all[0].parentElement.parentElement.textContent; return sec.includes('科技数码') ? 'has' : 'empty'; })()");
  if (cat === "empty") blockers.push("分区未默认科技数码，需手选（阶段2前人工确认）");
} catch (e) { blockers.push("分区检测：" + String(e).slice(0, 40)); }
// 创作声明（下拉只认真人事件，先试原生，失败记 blocker 不硬闯）
try {
  await page.evaluate("(() => { const el = document.querySelector('input[placeholder*=\"创作声明\"]'); if (el) { el.scrollIntoView({block:'center'}); el.click(); } return 1; })()");
  await page.waitForTimeout(1200);
  const opt = await page.evaluate(
    "(() => { const all = Array.from(document.querySelectorAll('*')).filter(n => n.children.length===0 && n.textContent.trim()==='含AI生成内容'); if (!all.length) return null; const el = all[all.length-1]; el.click(); return 'clicked'; })()");
  if (opt === "clicked") ts("声明=含AI生成内容 ✓");
  else blockers.push("创作声明下拉未展开（known：只认真人事件），阶段2前人工选");
} catch (e) { blockers.push("创作声明：" + String(e).slice(0, 40)); }
// 封面双比例（4:3 首页推荐 + 16:9 个人空间）
try {
  await page.evaluate("(() => { const all = Array.from(document.querySelectorAll('*')).filter(n => n.children.length===0 && n.textContent.trim()==='添加封面'); const el = all[all.length-1].parentElement; el.scrollIntoView({block:'center'}); return 1; })()");
  await page.waitForTimeout(500);
  const rc2 = await page.evaluate(
    "(() => { const all = Array.from(document.querySelectorAll('*')).filter(n => n.children.length===0 && n.textContent.trim()==='添加封面'); const el = all[all.length-1].parentElement; const r = el.getBoundingClientRect(); return [Math.round(r.x + r.width/2), Math.round(r.y + r.height/2)]; })()");
  await page.mouse.click(rc2[0], rc2[1], { label: "添加封面" });
  await page.waitForTimeout(2000);
  await page.setInputFiles('input[type="file"][accept^="image"]', [COVER_43]);
  await page.waitForTimeout(2000);
  ts("4:3 封面 ✓（用户口径：只传 4:3，16:9 平台派生）");
  await page.evaluate("(() => { const bs = Array.from(document.querySelectorAll('button')).filter(b => b.textContent.trim()==='完成'); const b = bs[bs.length-1]; if (b) b.click(); return 1; })()");
  await page.waitForTimeout(1500);
  ts("封面编辑器已关");
} catch (e) { blockers.push("封面双比例：" + String(e).slice(0, 60)); }
// STOP-BEFORE-PUBLISH
const shot = await page.screenshot({ path: "C:/Users/23393/ego/fast-bili-e1-20261108/final.png" }).catch(() => null);
ts("STOP 在「立即投稿」前");
console.log(JSON.stringify({
  platform: "bilibili", ok: true, elapsedSec: +((Date.now() - T0) / 1000).toFixed(1),
  screenshot: shot || "shotFailed", blockers, spaceName: SPACE,
  publishButton: "立即投稿（未点）",
}));
process.on("uncaughtException", (e) => {
  console.log(JSON.stringify({ platform: "bilibili", ok: false, elapsedSec: +((Date.now() - T0) / 1000).toFixed(1), why: String(e).slice(0, 120), blockers }));
  process.exit(0);
});
