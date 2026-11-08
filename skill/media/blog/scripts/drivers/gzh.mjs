// 公众号草稿驱动器 v1.2 —— 两档契约（S6 口径）：DOM/CDP 步骤免前台，真鼠标/文件弹窗需前台。
// 路线：登录→新建图文→填标题/作者/摘要→注入正文（占位符）→逐张插图（工具栏 JS 点击+input[type=file]）
//      →存草稿→截图存证（尽力）。终点=存草稿（绝不碰群发按钮）。
// 用法: ego-browser nodejs（stdin 喂本文件）  头部 CONFIG 按当期改（gzh_pack 产物）
// 实锤: ①后台首页也含「扫码登录」字样，登录判据必须看 URL token+「新的创作」
//       ②非 async 箭头里写 await = SyntaxError 无行号 ③appmsg 直连必须带 token
const fs = await import("node:fs");
const T0 = Date.now();
const ts = (m) => console.log(`[${((Date.now() - T0) / 1000).toFixed(1)}s] ${m}`);

// ================= CONFIG（当期必改） =================
const GZH_HTML = "D:/DeskTop/WorkSpace/embedai/视频/2026_0930_点亮屏幕/04_成片/gzh_pack/gzh.html";
const IMAGES_JSON = "D:/DeskTop/WorkSpace/embedai/视频/2026_0930_点亮屏幕/04_成片/gzh_pack/images.json";
const TITLE = "AI 写嵌入式驱动靠谱吗：我让它三步点亮一块 LCD 触摸屏";
const AUTHOR = "阿程";
const DIGEST = "全程 AI 写的 LCD 触摸屏驱动：三步走+两个坑的解法，嵌入式怎么用 AI 提效这篇讲透。";
const CLIP_PS1 = "D:/DeskTop/WorkSpace/Code/media-review/skill/media/blog/scripts/drivers/set_clip_image.ps1"; // 图片写 OS 剪贴板
const SKIP_IMAGES = true; // true=只到占位符草稿（图片人工兜底：按 images.json 清单在草稿箱传）
// ======================================================
const { execSync } = await import("node:child_process");
const blockers = [];
const SPACE = `blog-gzh-${Date.now() % 1000000}`;
const SHOT_DIR = `C:/Users/23393/ego/${SPACE}`;

const task = await taskSpace(SPACE);
const page = task.page("p1");
// 窗口程序化还原/收回（CDP Browser.setWindowBounds）——最小化不再是一票否决
const setWinState = async (state) => {
  try {
    const w = await page.cdp("Browser.getWindowForTarget");
    const windowId = w.windowId;
    await page.cdp("Browser.setWindowBounds", { windowId, bounds: { windowState: state } });
    return true;
  } catch (e) { blockers.push(`窗口${state === "normal" ? "还原" : "收回"}失败：` + String(e).slice(0, 60)); return false; }
};
await setWinState("normal");
await page.goto("https://mp.weixin.qq.com/", { timeout: 60000 });
// 登录闸门：URL token + 「新的创作」（首页含「扫码登录」字样，文本判据假阴性）
let loginOk = false;
for (let k = 0; k < 10 && !loginOk; k++) {
  await page.waitForTimeout(3000);
  loginOk = await page.evaluate(
    "(() => { const all = Array.from(document.querySelectorAll('*')).filter(n => n.children.length===0); return /token=|cgi-bin\\/(home|appmsg)/.test(location.href) || all.some(n => /新的创作/.test(n.textContent)); })()");
}
if (!loginOk) {
  console.log(JSON.stringify({ platform: "gzh", ok: false, why: "掉登录——handOff 请用户扫码后 resume", blockers }));
  process.exit(0);
}
ts("后台已登录");
// 新建图文：先试页面「写图文」入口，兜底带 token 直连编辑器 URL
let inEditor = (await page.url()).includes("appmsg");
if (!inEditor) {
  const clicked = await page.evaluate(
    "(() => { const all = Array.from(document.querySelectorAll('*')).filter(n => n.children.length===0 && /^(写图文|图文)$/.test(n.textContent.trim()) && n.offsetWidth>=0); if (!all.length) return false; (all.find(n => n.textContent.trim()==='写图文') || all[all.length-1]).click(); return true; })()");
  await page.waitForTimeout(4000);
  inEditor = (await page.url()).includes("appmsg");
  if (!inEditor) {
    const tok = ((await page.url()).match(/token=(\d+)/) || [])[1] || "";
    await page.goto(`https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit&type=77&token=${tok}&lang=zh_CN`, { timeout: 60000 }).catch(() => {});
    inEditor = (await page.url()).includes("appmsg");
  }
  if (!clicked && !inEditor) blockers.push("「写图文」入口没点到，走了 URL 直连");
}
if (!inEditor) {
  console.log(JSON.stringify({ platform: "gzh", ok: false, elapsedSec: +((Date.now() - T0) / 1000).toFixed(1), why: "进不去图文编辑器", blockers }));
  process.exit(0);
}
ts("编辑器就绪");
await page.waitForTimeout(3000);
// 标题/作者/摘要（全 DOM 填法，免前台）
const fillDom = (selJs, value, tag) => page.evaluate(
  `((sel, v) => { const el = document.querySelector(sel); if (!el) return false; el.focus(); el.value = v; el.dispatchEvent(new Event('input', {bubbles:true})); return true; })(${selJs}, ${JSON.stringify(value)})`)
  .then(ok => { if (ok) ts(tag + " ✓"); else blockers.push(tag + "：输入框没找到"); })
  .catch(e => blockers.push(tag + "：" + String(e).slice(0, 60)));
await page.waitForSelector(".ProseMirror", { timeout: 30000 }).catch(() => {});
// 新版编辑器=顶层 ProseMirror：标题（data-placeholder 含「标题」的 PM）+ 正文（最后一个 PM）
// 注入走 paste 事件（PM 原生消化 text/html），直接 innerHTML 会被 PM 状态回滚
const pmPaste = (pmIdxSel, payloadHtml, plainText, tag) => page.evaluate(
  `((sel, h, plain) => {
    const pms = Array.from(document.querySelectorAll('.ProseMirror')).filter(p => p.getAttribute('contenteditable') !== 'false');
    if (!pms.length) return 'no-pm';
    const el = sel === 'title' ? pms.find(p => (p.getAttribute('data-placeholder') || p.getAttribute('data-ph') || '').includes('标题')) : pms.find(p => !(p.getAttribute('data-placeholder') || p.getAttribute('data-ph') || '').includes('标题'));
    if (!el) return 'no-target';
    el.focus();
    const dt = new DataTransfer();
    if (h) dt.setData('text/html', h);
    if (plain) dt.setData('text/plain', plain);
    el.dispatchEvent(new ClipboardEvent('paste', { bubbles: true, cancelable: true, clipboardData: dt }));
    return el.textContent.length;
  })(${JSON.stringify(pmIdxSel)}, ${JSON.stringify(payloadHtml)}, ${JSON.stringify(plainText)})`)
  .then(n => { if (typeof n === 'number' && n > 0) ts(tag + ` ✓（${n} 字）`); else blockers.push(tag + `：注入返回 ${n}`); })
  .catch(e => blockers.push(tag + "：" + String(e).slice(0, 60)));
await pmPaste("title", "", TITLE, "标题(PM)");
await fillDom("'#author, input[placeholder*=\\'作者\\']'", AUTHOR, "作者");
await page.waitForTimeout(500);
await fillDom("'textarea[placeholder*=\\'摘要\\'], input[placeholder*=\\'摘要\\'], #digest'", DIGEST, "摘要");
// 正文注入：样式化 HTML + 占位符段落（⟦图N⟧ 供插图定位）
const html = fs.readFileSync(GZH_HTML, "utf-8");
const images = JSON.parse(fs.readFileSync(IMAGES_JSON, "utf-8"));
await page.waitForTimeout(500);
await pmPaste("body", html, "", `正文注入（${images.length} 占位符）`);
if (SKIP_IMAGES) {
  // 图片人工兜底：直接存草稿（正文含 ⟦图N⟧ 标记，人按 images.json 清单替换）
  let saved0 = false;
  for (let k = 0; k < 3 && !saved0; k++) {
    saved0 = await page.evaluate(
      "(() => { const all = Array.from(document.querySelectorAll('*')).filter(n => n.children.length===0 && /^(保存为草稿|保存)$/.test(n.textContent.trim()) && n.offsetWidth>0); if (!all.length) return false; all[all.length-1].click(); return true; })()") && await (async () => {
      await page.waitForTimeout(2500);
      return page.evaluate("(() => { const all = Array.from(document.querySelectorAll('*')).filter(n => n.children.length===0); return all.some(n => /已保存|保存成功/.test(n.textContent)); })()");
    })();
  }
  await setWinState("normal");
  const shot = await page.screenshot({ path: `${SHOT_DIR}/draft-placeholders.png` }).catch(() => null);
  await setWinState("minimized");
  await page.close().catch(() => {});
  console.log(JSON.stringify({
    platform: "gzh", ok: saved0, mode: "placeholders-manual-images",
    elapsedSec: +((Date.now() - T0) / 1000).toFixed(1),
    screenshot: shot || "failed", spaceName: SPACE,
    imagesJson: IMAGES_JSON,
    manualSteps: "草稿箱打开本草稿：逐个 ⟦图N⟧ 标记行→删标记→工具栏图片→按 images.json 顺序选文件→存草稿",
    stopPoint: "存草稿（终点；群发按钮绝不碰，交用户手动）",
  }));
  process.exit(0);
}
// 诊断回读：正文 PM 若没吃进内容（合成 paste 可能被 PM 拒），换原生 keyboard.paste（前台路线）
const bodyState = await page.evaluate(
  "(() => { const pms = Array.from(document.querySelectorAll('.ProseMirror')); const el = pms[pms.length - 1]; return el ? { len: el.textContent.length, imgs: el.querySelectorAll('img').length, head: el.innerHTML.slice(0, 120) } : null; })()");
ts("正文回读 " + JSON.stringify(bodyState));
if (!bodyState || bodyState.len < 200) {
  await page.evaluate("(() => { const pms = Array.from(document.querySelectorAll('.ProseMirror')); const el = pms[pms.length - 1]; el.focus(); return 1; })()");
  await page.waitForTimeout(500);
  const plain = html.replace(/<[^>]+>/g, "").replace(/\n{2,}/g, "\n").trim();
  await page.keyboard.paste({ text: plain, html: html });
  await page.waitForTimeout(1500);
  const bodyState2 = await page.evaluate(
    "(() => { const pms = Array.from(document.querySelectorAll('.ProseMirror')); const el = pms[pms.length - 1]; return el ? { len: el.textContent.length, imgs: el.querySelectorAll('img').length } : null; })()");
  ts("原生 paste 回读 " + JSON.stringify(bodyState2));
  if (!bodyState2 || bodyState2.len < 200) blockers.push("正文两条路线都没吃满（合成 paste " + (bodyState ? bodyState.len : "?") + " 字 / 原生 paste " + (bodyState2 ? bodyState2.len : "?") + " 字）");
}
// 逐张插图（v1.7 数据 URL paste 路线）：真鼠标点占位段落光标 → Home/Shift+End 选段 →
// keyboard.paste({html: <img data:URL>}) → mp 编辑器自动上传转 CDN。上传对话框路线已废弃
// （诊断 files:1/fileVis:1 但从不落位）。窗口由 win_window.ps1 restore/minimize 管理
const winVis = async () => {
  const v = await page.evaluate("(() => ({w: window.innerWidth, h: window.innerHeight}))()");
  return v.w > 0 && v.h > 0;
};
for (const img of images) {
  try {
    const ph = `⟦图${img.n}:${img.name}⟧`;
    // 定位正文 PM 里的占位段并选中（顶层 DOM Selection，PM 会映射到自己的光标）
    const located = await page.evaluate(
      `(fn => {
        const pms = Array.from(document.querySelectorAll('.ProseMirror')).filter(p => p.getAttribute('contenteditable') !== 'false' && !(p.getAttribute('data-placeholder') || '').includes('标题'));
        const el = pms[pms.length - 1];
        if (!el) return 'no-pm';
        const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); let node;
        while ((node = w.nextNode())) { const i = node.textContent.indexOf(fn); if (i >= 0) { const r = document.createRange(); r.setStart(node, i); r.setEnd(node, i + fn.length); const s = window.getSelection(); s.removeAllRanges(); s.addRange(r); el.focus(); return true; } }
        return false;
      })(${JSON.stringify(ph)})`);
    if (located !== true) throw new Error(`占位符没找到: ${ph} (${located})`);
    // 主路线：真鼠标点占位段落位（PM 认真实点击的光标）→ Home/Shift+End 选段 → 原生 paste
    // <img data:URL>（mp 编辑器自动上传转 CDN），全程绕开上传对话框
    // 两段式落位：先瞬时滚动（平滑滚动会让 rect 测量过期），等稳了再取新 rect 真点击
    await page.evaluate(
      `(fn => {
        const pms = Array.from(document.querySelectorAll('.ProseMirror')).filter(p => p.getAttribute('contenteditable') !== 'false' && !(p.getAttribute('data-placeholder') || '').includes('标题'));
        const el = pms[pms.length - 1];
        const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); let node;
        while ((node = w.nextNode())) { const i = node.textContent.indexOf(fn); if (i >= 0) { node.parentElement.scrollIntoView({ block: 'center', behavior: 'instant' }); return true; } }
        return false;
      })(${JSON.stringify(ph)})`);
    await page.waitForTimeout(700);
    const rc = await page.evaluate(
      `(fn => {
        const pms = Array.from(document.querySelectorAll('.ProseMirror')).filter(p => p.getAttribute('contenteditable') !== 'false' && !(p.getAttribute('data-placeholder') || '').includes('标题'));
        const el = pms[pms.length - 1];
        const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); let node;
        while ((node = w.nextNode())) { const i = node.textContent.indexOf(fn); if (i >= 0) { const r = document.createRange(); r.setStart(node, i); r.setEnd(node, i + fn.length); const rect = r.getBoundingClientRect(); return { x: Math.round(rect.x + Math.max(3, Math.min(10, rect.width / 2))), y: Math.round(rect.y + rect.height / 2) }; } }
        return null;
      })(${JSON.stringify(ph)})`);
    if (!rc) throw new Error(`占位段坐标没拿到: ${ph}`);
    await page.mouse.click(rc.x, rc.y, { label: `落位图${img.n}占位段` });
    await page.waitForTimeout(600);
    // 选中占位整行（Home + Shift+End）：插图时选区被图片整体替换，占位符零残渣
    await page.keyboard.press("Home");
    await page.keyboard.press("Shift+End");
    await page.waitForTimeout(300);
    const before = await page.evaluate(
      "(() => { const pms = Array.from(document.querySelectorAll('.ProseMirror')).filter(p => p.getAttribute('contenteditable') !== 'false' && !(p.getAttribute('data-placeholder') || '').includes('标题')); const el = pms[pms.length - 1]; return el ? el.querySelectorAll('img').length : -1; })()");
    // v2.1 路线（probe_img2 实锤）：JS 点工具栏「图片」→ 直 setInputFiles
    // gif-accept 唯一选择器即落图（光标=上面真鼠标点出的 PM 位置）。
    // 中间不许插任何诊断 evaluate（抢焦点会收起下拉菜单、摘掉 input）。
    await page.evaluate(
      "(() => { const all = Array.from(document.querySelectorAll('*')).filter(n => n.children.length===0 && n.textContent.trim()==='图片' && n.offsetWidth>0); if (all.length) all[all.length-1].click(); return all.length; })()");
    await page.waitForTimeout(2000);
    await page.setInputFiles('input[type=file][accept*="gif"]', [img.file]);
    // mp 后台上传转 CDN，轮询占位符消失 + img 数 +1
    let inserted = false;
    for (let k = 0; k < 12 && !inserted; k++) {
      await page.waitForTimeout(3000);
      inserted = await page.evaluate(
        `(fn => { const pms = Array.from(document.querySelectorAll('.ProseMirror')).filter(p => p.getAttribute('contenteditable') !== 'false' && !(p.getAttribute('data-placeholder') || '').includes('标题')); const el = pms[pms.length - 1]; return el ? !el.innerHTML.includes(fn) && el.querySelectorAll('img').length > ${before} : false; })(${JSON.stringify(ph)})`);
    }
    if (inserted) ts(`图${img.n} ${img.name} ✓`);
    else {
      const st = await page.evaluate(
        "(() => { const pms = Array.from(document.querySelectorAll('.ProseMirror')).filter(p => p.getAttribute('contenteditable') !== 'false' && !(p.getAttribute('data-placeholder') || '').includes('标题')); const el = pms[pms.length - 1]; return el ? { imgs: el.querySelectorAll('img').length, phLeft: (el.innerHTML.match(/⟦图\\d/g) || []).length, tail: el.innerHTML.slice(-120) } : null; })()");
      ts(`图${img.n} 状态 ` + JSON.stringify(st));
    }
    // 收尾关浮层：上传菜单的设置面板会盖住正文拦鼠标，每轮 Escape + 点空白收掉
    await page.keyboard.press("Escape");
    await page.waitForTimeout(500);
    if (!inserted) throw new Error("set 后 36s 未见图片落位");
  } catch (e) { blockers.push(`图${img.n} ${img.name}：` + String(e).slice(0, 60)); }
}
// 存草稿：「保存为草稿/保存」JS 点击 + 重试环
let saved = false;
for (let k = 0; k < 3 && !saved; k++) {
  saved = await page.evaluate(
    "(() => { const all = Array.from(document.querySelectorAll('*')).filter(n => n.children.length===0 && /^(保存为草稿|保存)$/.test(n.textContent.trim()) && n.offsetWidth>0); if (!all.length) return false; all[all.length-1].click(); return true; })()") && await (async () => {
    await page.waitForTimeout(2500);
    return page.evaluate("(() => { const all = Array.from(document.querySelectorAll('*')).filter(n => n.children.length===0); return all.some(n => /已保存|保存成功/.test(n.textContent)); })()");
  })();
}
const shot = (await setWinState("normal")) ? await page.screenshot({ path: `${SHOT_DIR}/draft.png` }).catch(() => null) : null;
if (!shot) blockers.push("截图存证失败（还原后仍拍不上）");
if (!saved) blockers.push("存草稿按钮没点到/没看到保存成功提示——截图留证交人确认");
await setWinState("minimized"); // 跑完自动收回，不占前台
await page.close().catch(() => {}); // 关掉自己的窗口，不留窗海
console.log(JSON.stringify({
  platform: "gzh", ok: saved, elapsedSec: +((Date.now() - T0) / 1000).toFixed(1),
  screenshot: shot || "skipped-or-failed", blockers, spaceName: SPACE,
  stopPoint: "存草稿（终点；群发按钮绝不碰，交用户手动）",
}));
process.on("uncaughtException", (e) => {
  console.log(JSON.stringify({ platform: "gzh", ok: false, elapsedSec: +((Date.now() - T0) / 1000).toFixed(1), why: String(e).slice(0, 120), blockers }));
  try { page.close(); } catch (_) {}
  process.exit(0);
});
