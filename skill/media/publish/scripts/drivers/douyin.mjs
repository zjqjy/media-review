// 抖音快发驱动器 v1 —— 单进程全程，STOP-BEFORE-PUBLISH
const T0 = Date.now();
const ts = (m) => console.log(`[${((Date.now() - T0) / 1000).toFixed(1)}s] ${m}`);
const VIDEO = "D:/DeskTop/WorkSpace/embedai/视频/20261101_ego浏览器/04_成片/20261101_ego浏览器_精简中_成片.mp4";
const COVER_43 = "D:/DeskTop/WorkSpace/embedai/视频/20261101_ego浏览器/04_成片/20261101_ego浏览器_精简中_4x3.png";
const COVER_34 = "D:/DeskTop/WorkSpace/embedai/视频/20261101_ego浏览器/04_成片/20261101_ego浏览器_精简中_3x4.png";
const TITLE = "AI替我上网打工！Agent浏览器实测";
const DESC_MAIN = "AI替我上网打工是什么体验？Agent 浏览器 ego lite 实测：安装到自动接任务全流程";
const TOPICS = ["AI", "Agent", "浏览器", "效率工具"];
const blockers = [];
const SPACE = `fast-douyin-${Date.now() % 1000000}`;
const task = await taskSpace(SPACE);
const page = task.page("p1");
await page.goto("https://creator.douyin.com/creator-micro/content/upload", { timeout: 90000 });
await page.waitForLoadState("load", { timeout: 30000 }).catch(() => {});
await page.waitForTimeout(4000);
let s = await page.snapshot();
if (s.includes("扫码登录")) { console.log(JSON.stringify({ platform: "douyin", ok: false, why: "掉登录", blockers })); process.exit(0); }
ts("页面就绪");
// 上传
const chP = page.waitForFileChooser({ timeout: 20000 });
await page.click('text=点击上传');
(await chP).setFiles(VIDEO);
ts("285MB 视频提交上传");
// 等表单（抖音：表单在上传完成后才渲染）
for (let k = 0; k < 130; k++) {
  await page.waitForTimeout(2000);
  s = await page.snapshot();
  if (s.includes("填写作品标题")) break;
}
if (!s.includes("填写作品标题")) { console.log(JSON.stringify({ platform: "douyin", ok: false, why: "表单未渲染", blockers })); process.exit(0); }
ts("表单出现");
// 标题
await page.fill('input[placeholder*="填写作品标题"]', TITLE);
ts("标题 ✓");
// 简介 + 话题芯片（入口文案多变：contenteditable 兜底，点不中就 focus）
let dOk = false;
try { await page.click('text=添加作品简介'); dOk = true; } catch (e) {}
if (!dOk) {
  dOk = await page.evaluate(
    "(() => { const els = Array.from(document.querySelectorAll('[contenteditable=true]')); const el = els.find(e => (e.textContent||'').includes('添加作品简介') || (e.textContent||'').includes('输入作品描述')) || els[0]; if (!el) return false; el.scrollIntoView({block:'center'}); el.focus(); return true; })()");
}
if (!dOk) blockers.push("简介编辑器没找到（文案又变了）");
await page.waitForTimeout(500);
await page.keyboard.type(DESC_MAIN + " ", { delay: 3 });
for (const t of TOPICS) {
  await page.keyboard.type("#", { delay: 60 });
  await page.waitForTimeout(1400);
  let hit = false;
  // 真坐标点击联想行（程序化 click 不被认）
  const rc = await page.evaluate(
    (w) => { const all = Array.from(document.querySelectorAll('*')).filter(n => n.children.length === 0 && (n.textContent.trim() === w || n.textContent.trim() === "#" + w)); if (!all.length) return null; const el = all[all.length - 1]; const r = el.getBoundingClientRect(); return [Math.round(r.x + r.width / 2), Math.round(r.y + r.height / 2)]; }, t);
  if (rc && rc[1] > 0 && rc[1] < 800) {
    await page.mouse.click(rc[0], rc[1], { label: "点话题联想行" });
    hit = true;
  } else {
    try { await page.click(`text="#${t}"`); hit = true; } catch (e) {}
  }
  if (!hit) { await page.keyboard.type(t, { delay: 20 }); blockers.push("话题[" + t + "]：联想没命中，已退化为正文文字"); }
  await page.waitForTimeout(700);
}
ts("简介+话题 ✓");
// 自主声明 = 内容由AI生成
try {
  await page.click('text="请选择自主声明"');
  await page.waitForTimeout(1000);
  await page.click('text="内容由AI生成"');
  await page.waitForTimeout(500);
  await page.click('text="确定"');
  await page.waitForTimeout(800);
  ts("声明=内容由AI生成 ✓");
} catch (e) { blockers.push("自主声明：" + String(e).slice(0, 50)); }
// 封面：编辑器一开管双比例（顶部 设置横封面/设置竖封面 页签 + 「+ 上传封面」按钮，无裸 file input）
try {
  const slot = await page.evaluate(
    "(() => { const all = Array.from(document.querySelectorAll('*')).filter(n => n.children.length===0 && n.textContent.trim()==='选择封面'); if (!all.length) return null; const el = all[0].parentElement; const r = el.getBoundingClientRect(); return [Math.round(r.x + r.width/2), Math.round(r.y + r.height/2)]; })()");
  if (!slot) throw new Error("没找到选择封面入口（默认抽帧兜底）");
  await page.keyboard.press("Escape");
  await page.waitForTimeout(1000);
  await page.mouse.click(slot[0], slot[1], { label: "开封面编辑器" });
  await page.waitForTimeout(3000);
  // 编辑器没开（浮层吃了点击）就重试两次
  for (let k = 0; k < 2; k++) {
    const open = await page.evaluate("(() => !!document.querySelector('[class*=dy-creator-content-modal-body]'))()");
    if (open) break;
    const rc2 = await page.evaluate(
      "(() => { const all = Array.from(document.querySelectorAll('*')).filter(n => n.children.length===0 && n.textContent.trim()==='选择封面'); if (!all.length) return null; const el = all[0].parentElement; el.scrollIntoView({block:'center'}); const r = el.getBoundingClientRect(); return [Math.round(r.x + r.width/2), Math.round(r.y + r.height/2)]; })()");
    if (!rc2) break;
    await page.mouse.click(rc2[0], rc2[1], { label: "重试开编辑器" });
    await page.waitForTimeout(3000);
  }
  // 编辑器内：切页签 → 点「+ 上传封面」→ 选择器 → 塞图
  async function uploadCoverTab(tabName, file) {
    try { await page.click(`text="${tabName}"`); await page.waitForTimeout(1500); } catch (e) {}
    let brc = null;
    for (let k = 0; k < 5 && !brc; k++) {
      await page.waitForTimeout(2000);
      brc = await page.evaluate(
        "(() => { const bs = Array.from(document.querySelectorAll('*')).filter(n => (n.textContent||'').replace(/\\s/g,'').includes('上传封面') && n.children.length <= 3).map(n => { const r = n.getBoundingClientRect(); return {r: [Math.round(r.x + r.width/2), Math.round(r.y + r.height/2)], area: r.width * r.height}; }).filter(x => x.area > 300 && x.area < 50000).sort((a,b) => a.area - b.area); return bs.length ? bs[0].r : null; })()");
    }
    if (!brc) throw new Error(tabName + "：上传封面按钮没找到");
    const chP = page.waitForFileChooser({ timeout: 15000 });
    await page.mouse.click(brc[0], brc[1], { label: "点上传封面" });
    const ch = await chP;
    await ch.setFiles(file);
    await page.waitForTimeout(2500);
  }
  await uploadCoverTab("设置横封面", COVER_43);
  ts("横封面 4:3 ✓");
  await uploadCoverTab("设置竖封面", COVER_34);
  ts("竖封面 3:4 ✓");
  await page.evaluate("(() => { const bs = Array.from(document.querySelectorAll('button')).filter(b => ['保存','完成','确定'].includes(b.textContent.trim())); const b = bs[bs.length-1]; if (b) { b.scrollIntoView({block:'center'}); b.click(); } return 1; })()");
  await page.waitForTimeout(2000);
  ts("封面已保存 ✓");
} catch (e) { blockers.push("封面：" + String(e).slice(0, 60)); }
process.on("uncaughtException", (e) => {
  console.log(JSON.stringify({ platform: "douyin", ok: false, elapsedSec: +((Date.now() - T0) / 1000).toFixed(1), why: String(e).slice(0, 120), blockers }));
  process.exit(0);
});
// STOP-BEFORE-PUBLISH
const shot = await page.screenshot({ path: "C:/Users/23393/ego/fast-douyin-e1-20261108/final.png" }).catch(() => null);
ts("STOP 在「发布」前");
console.log(JSON.stringify({
  platform: "douyin", ok: true, elapsedSec: +((Date.now() - T0) / 1000).toFixed(1),
  screenshot: shot || "shotFailed", blockers,
  publishButton: "发布（未点）",
}));
