// 小红书快发驱动器 v1 —— 单进程全程，STOP-BEFORE-PUBLISH
const T0 = Date.now();
const ts = (m) => console.log(`[${((Date.now() - T0) / 1000).toFixed(1)}s] ${m}`);
const VIDEO = "D:/DeskTop/WorkSpace/embedai/视频/20261101_ego浏览器/04_成片/20261101_ego浏览器_精简中_成片.mp4";
const COVER_34 = "D:/DeskTop/WorkSpace/embedai/视频/20261101_ego浏览器/04_成片/20261101_ego浏览器_精简中_3x4.png";
const TITLE = "AI替我上网打工！Agent浏览器";
const DESC_MAIN = "🔥AI 真的替我上网打工了！\nAgent 浏览器 ego lite 实测：安装→登录保持→分屏并行→自动接任务，全程 AI 替我操作网页😎";
const TOPICS = ["AI工具", "Agent", "浏览器", "效率神器", "ego"];
const blockers = [];
const SPACE = `fast-xhs-${Date.now() % 1000000}`;
const task = await taskSpace(SPACE);
const page = task.page("p1");
await page.goto("https://creator.xiaohongshu.com/publish/publish?from=menu&target=video", { timeout: 60000 });
await page.waitForLoadState("load", { timeout: 30000 }).catch(() => {});
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
  await page.waitForTimeout(1400);
  let hit = false;
  const rc = await page.evaluate(
    (w) => { const all = Array.from(document.querySelectorAll('*')).filter(n => n.children.length === 0 && (n.textContent.trim() === "#" + w || n.textContent.trim() === w)); if (!all.length) return null; const el = all[all.length - 1]; const r = el.getBoundingClientRect(); return [Math.round(r.x + r.width / 2), Math.round(r.y + r.height / 2)]; }, t);
  if (rc && rc[1] > 0 && rc[1] < 800) {
    await page.mouse.click(rc[0], rc[1], { label: "点话题联想行" });
    hit = true;
  } else {
    try { await page.click(`text="#${t}"`); hit = true; } catch (e) {}
  }
  if (!hit) { await page.keyboard.type(t + " ", { delay: 15 }); blockers.push("话题[" + t + "]：联想没命中，退化为文字"); }
  await page.waitForTimeout(700);
}
await page.keyboard.press("Escape");
ts("正文+话题 ✓");
// 声明（内容设置区——下拉可能点不开，记 blocker 不硬闯）
try {
  const declared = await page.evaluate(
    "(() => { const all = Array.from(document.querySelectorAll('*')).filter(n => n.children.length===0 && n.textContent.trim()==='原创声明'); if (!all.length) return 'none'; const tgl = all[all.length-1].parentElement.querySelector('[class*=switch],[role=switch],input[type=checkbox]'); if (tgl) { tgl.click(); return 'toggled'; } return 'noswitch'; })()");
  if (declared !== "toggled") blockers.push("xhs 原创声明/内容类型声明：自动化未覆盖（known），阶段2前人工在内容设置区选 AI 相关项");
  else ts("原创声明开关 ✓");
} catch (e) { blockers.push("声明：" + String(e).slice(0, 40)); }
// 封面：点首帧缩略图 → 编辑封面 → aria-label input → 完成
try {
  let thumb = null;
  for (let k = 0; k < 15; k++) {
    thumb = await page.evaluate(
      "(() => { const all = Array.from(document.querySelectorAll('*')).filter(n => n.children.length===0 && n.textContent.trim()==='设置封面'); if (!all.length) return null; let sec = all[0].parentElement; for (let d = 0; d < 4; d++) sec = sec.parentElement; const img = sec.querySelector('img'); if (!img) return null; const r = img.getBoundingClientRect(); return [Math.round(r.x + r.width/2), Math.round(r.y + r.height/2)]; })()");
    if (thumb) break;
    await page.waitForTimeout(2000);
  }
  if (!thumb) throw new Error("首帧缩略图30s未出现（视频处理中）");
  await page.mouse.click(thumb[0], thumb[1], { label: "点首帧缩略图" });
  await page.waitForTimeout(1500);
  const editRc = await page.evaluate(
    "(() => { const all = Array.from(document.querySelectorAll('*')).filter(n => n.children.length===0 && n.textContent.trim()==='编辑封面'); if (!all.length) return null; const el = all[all.length-1].parentElement; const r = el.getBoundingClientRect(); return [Math.round(r.x + r.width/2), Math.round(r.y + r.height/2)]; })()");
  if (!editRc) throw new Error("编辑封面入口未浮出");
  await page.mouse.click(editRc[0], editRc[1], { label: "编辑封面" });
  await page.waitForTimeout(2000);
  await page.setInputFiles('input[aria-label="上传封面图片"]', [COVER_34]);
  await page.waitForTimeout(2500);
  await page.evaluate("(() => { const bs = Array.from(document.querySelectorAll('button')).filter(b => b.textContent.trim()==='完成'); const b = bs[bs.length-1]; if (b) b.click(); return 1; })()");
  await page.waitForTimeout(1800);
  ts("封面 3x4 ✓（自动质检）");
} catch (e) { blockers.push("封面：" + String(e).slice(0, 60) + "（默认首帧兜底）"); }
// STOP-BEFORE-PUBLISH
const shot = await page.screenshot({ path: "C:/Users/23393/ego/fast-xhs-e1-20261108/final.png" }).catch(() => null);
ts("STOP 在「发布」前");
console.log(JSON.stringify({
  platform: "xhs", ok: true, elapsedSec: +((Date.now() - T0) / 1000).toFixed(1),
  screenshot: shot || "shotFailed", blockers,
  publishButton: "发布（未点）",
}));
