#!/usr/bin/env node
// 火山方舟 Seedream 图片生成（零依赖，node ≥18）
//
// 用法:
//   node gen_image.mjs -o out.png "<提示词>"
//   node gen_image.mjs -o out.png --style "<角色/风格前缀>" "情绪或场景描述"
//   node gen_image.mjs -o set.png --group 4 --size 2K "生成一套4张……第一张…；第二张…"
//
// 参数:
//   -o <路径>        输出 png（--group 时自动加 _01.._N 后缀）
//   --style <文本>   风格/角色前缀，拼在提示词前（角色一致性用，配合 --seed 固定）
//   --seed <N>       随机种子（默认 20261；同前缀+同 seed 出同一角色）
//   --size <S>       1024x1024（默认）| 2K | 4K | 竖版 1024x2304 等，见官方文档
//   --group <N>      组图数量（>1 时 sequential_image_generation=auto，角色最稳）
//   --model <id>     指定单个模型；默认按下方列表降级尝试（需在方舟控制台开通）
//   --watermark      加水印（默认关）
//
// key: 环境变量 ARK_API_KEY 优先；否则从当前目录向上找 .ark_key（一行明文）。
//      key 绝不写进本文件或任何 git 跟踪文件。
import fs from 'node:fs';
import path from 'node:path';

const MODELS = [
  'doubao-seedream-5-0-flash-260915',
  'doubao-seedream-5-0-pro-260628',
  'doubao-seedream-4-5-251128',
  'doubao-seedream-4-0-250828',
  'doubao-seedream-5-0-lite-260128',
];

// ---------- 参数 ----------
const argv = process.argv.slice(2);
const argOf = (flag, def = undefined) => {
  const i = argv.indexOf(flag);
  return i >= 0 ? argv[i + 1] : def;
};
const has = (flag) => argv.includes(flag);

const out = argOf('-o');
const style = argOf('--style', '');
const seed = Number(argOf('--seed', '20261'));
const size = argOf('--size', '1024x1024');
const group = Math.max(1, Number(argOf('--group', '1')));
const modelArg = argOf('--model');
const watermark = has('--watermark');
// 提示词 = 第一个既不是 flag 也不是 flag 值的参数
const consumed = new Set();
for (let i = 0; i < argv.length; i++) {
  if (argv[i].startsWith('-')) { consumed.add(i); if (argv[i + 1] && !argv[i + 1].startsWith('-')) consumed.add(i + 1); }
}
const promptParts = argv.filter((a, i) => !consumed.has(i) && !(i > 0 && argv[i - 1] === '-o'));
const prompt = promptParts.join(' ');
if (!out || !prompt) {
  console.error('用法: node gen_image.mjs -o <输出.png> "<提示词>" [--style 前缀] [--seed N] [--size S] [--group N] [--model id]');
  process.exit(1);
}

// ---------- key ----------
function findKey() {
  if (process.env.ARK_API_KEY) return process.env.ARK_API_KEY.trim();
  let dir = process.cwd();
  for (let i = 0; i < 8; i++) {
    const p = path.join(dir, '.ark_key');
    if (fs.existsSync(p)) return fs.readFileSync(p, 'utf8').trim();
    const up = path.dirname(dir);
    if (up === dir) break;
    dir = up;
  }
  throw new Error('找不到 key：设 ARK_API_KEY 环境变量，或在工作目录/其上级放 .ark_key（一行明文）');
}
const KEY = findKey();

// ---------- 生成 ----------
async function gen(model) {
  const body = {
    model,
    prompt: style ? `${style}${prompt}` : prompt,
    size,
    response_format: 'url',
    watermark,
    seed,
  };
  if (group > 1) body.sequential_image_generation = 'auto';
  const res = await fetch('https://ark.cn-beijing.volces.com/api/v3/images/generations', {
    method: 'POST',
    headers: {'Content-Type': 'application/json', Authorization: `Bearer ${KEY}`},
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(300000),
  });
  const text = await res.text();
  if (!res.ok) return {ok: false, detail: `${res.status} ${text.slice(0, 300)}`};
  const json = JSON.parse(text);
  const items = json?.data ?? [];
  if (!items.length) return {ok: false, detail: `无图片数据: ${text.slice(0, 300)}`};
  const imgs = [];
  for (const item of items) {
    if (item.b64_json) imgs.push(Buffer.from(item.b64_json, 'base64'));
    else if (item.url) {
      const r = await fetch(item.url, {signal: AbortSignal.timeout(120000)});
      imgs.push(Buffer.from(await r.arrayBuffer()));
    }
  }
  return {ok: true, model, imgs};
}

let done = null;
for (const model of modelArg ? [modelArg] : MODELS) {
  process.stdout.write(`尝试 ${model} … `);
  try {
    const r = await gen(model);
    if (r.ok) { console.log('成功'); done = r; break; }
    console.log(`失败（${r.detail}）`);
  } catch (e) {
    console.log(`失败（${e.message}）`);
  }
}
if (!done) { console.error('全部模型失败（排查顺序：401 key不完整 → 404 没开通/ID错 → 429 安全体验模式限额）'); process.exit(1); }

// ---------- 落盘（fileURLToPath 防中文路径 %E8 编码炸 ENOENT） ----------
const outPath = path.resolve(out);
fs.mkdirSync(path.dirname(outPath), {recursive: true});
const ext = path.extname(outPath) || '.png';
const base = outPath.slice(0, outPath.length - ext.length);
if (done.imgs.length === 1) {
  fs.writeFileSync(outPath, done.imgs[0]);
  console.log(`模型: ${done.model} → ${outPath} (${done.imgs[0].length} bytes)`);
} else {
  done.imgs.forEach((buf, i) => {
    const p = `${base}_${String(i + 1).padStart(2, '0')}${ext}`;
    fs.writeFileSync(p, buf);
    console.log(`模型: ${done.model} → ${p} (${buf.length} bytes)`);
  });
}
