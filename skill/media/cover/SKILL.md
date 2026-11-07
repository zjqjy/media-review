---
name: cover
description: media 子技能：视频封面生成（oil-cover 移植 + 火山 Ark 化）。由 media 门面路由进入——成片/视频的发布封面整图，三画幅直出（小红书 3:4 / B站首页主封面 4:3 / 个人空间 16:9）。链路=本地选帧（ffmpeg+PIL 预筛，零 API）→ 视觉分析双模式（agent 本体默认零成本；api 模式调 Ark doubao 视觉全自动，给无多模态宿主用）→ Seedream 生图（参考帧上传）→ 可选 Pillow 头像合成。生成贴纸/插画/表情包/氛围素材归 aigen，这里是"成片封面整图"这一步。
---

# cover · 视频封面（oil-cover 移植，火山 Ark 化）

为视频生成稳定、清楚、干净、精致的三画幅封面。上游 https://github.com/oil-oil/oil-cover （MIT；`LICENSE`/`NOTICE` 在本目录，product-logos 是第三方商标仅作视觉参考资产）。

## 什么时候用我 / 不用我

| 用 | 不用（换方案） |
| --- | --- |
| 成片/视频的发布封面整图（标题排版+屏幕证据+点缀一体） | 生成贴纸/插画/表情包/氛围素材 → aigen |
| 已有截图/关键帧直接做封面（`--image`） | 信息卡/图表 → cards；跟口播节拍的动画 → Remotion |
| 单独重跑某一画幅（`--aspect 3x4`） | 剪映封面模板贴字 → 人工 |

## 执行模式（设一次，以后不问）

用户配置 `~/.media-cover/config.json`（env `COVER_CONFIG` 可改）：

```json
{
  "mode": "agent",
  "creator_name": "可选，讲解人称谓",
  "creator_portrait": {"enabled": false, "path": "透明底头像.png"},
  "api_key_file": "可选，key 文件路径",
  "image_model": "可选，Seedream 模型 ID",
  "analysis_model": "可选，视觉分析模型 ID"
}
```

每次触发按序决定：① 读配置 `mode`；② 已设 `agent`/`api` → 直接按该模式执行不再问；③ 未设置 → 问用户一次（一次性设置），拿到答案合并写回配置（保留其他键）；④ 用户随时可口头「本次用 api」单次覆盖（`--mode api`），不改默认。**前提与回退**：mode=agent 但当前宿主没有多模态（看不了图）→ 明说给两条路——换具备视觉的宿主，或本次 `--mode api`——不静默失败，不擅自改默认。

## agent 模式 SOP（默认，照表执行）

| 步 | 动作 | 要点 |
|---|---|---|
| 0 | 标题提炼（你的职责，生图前完成） | 用户已指定 → 锁定原文只做断行；未指定 → 有 `.srt/.ass/.txt` 字幕或文稿先通读，优先借用口播原话强词（「目前最强」「指哪打哪」），忠于内容不夸大；都没有才退回视频标题克制精简。**上游标题规则**：主标题默认 `2 行 × 3–5 字`（最佳 4+4，空格分隔，如「后台设计 更有质感」）；长英文品牌名/Skill 名不塞进主标题行内（防字号缩水），拆成标题上方独立品牌小标；标题脱离文件名和正文也要让人一眼懂「对象+结果」，不单独用依赖上下文的反转短语 |
| 1 | 本地选帧（零 API） | `python scripts/generate_cover.py --video <视频> --title "<主标题>" [--subtitle <纯文本字幕>] --prescan` → 8 张候选帧落 `<视频名>.cover/frames/`（已硬过滤黑屏/纯色/模糊，分桶取最清晰） |
| 2 | 视觉分析（你做，零成本） | 读 `references/cover-rules.md`（视觉规范）+ 候选帧 → 挑最能代表主题的一帧 → 写**最终生图 prompt** 存成文件。prompt 即最终指令：自包含、不自我矛盾、不堆砌——一次说清截图蒸馏（留 2-3 个关键 UI 信号）、一glance 主体、屏幕溢出裁切、标题字级（3:4 每行占安全区宽 90-96%；横版 cap height 16-22%、严格 2 短行）、短线避雷清单 |
| 3 | 喂回生图 | `python scripts/generate_cover.py --video <视频> --title "<主标题>" --prompt-file <prompt.txt> [--frame candidate_03] [--aspect all]`。脚本仍守门：标题逐字锁定 + 硬规则回填（画幅/背景/色彩纪律/溢出/阴影/Logo 守卫）+ 三画幅并行 + sidecar 落盘。`--prompt-file` 也接受带 `prompts` 字段的 analysis.json（可手编逐画幅 prompt） |
| 4 | 验收交付 | 三画幅 `<视频名>_3x4/_4x3/_16x9.png` 落视频旁；只看封面做一次独立理解检查（说不清主题就改标题重出）；返工前区分事实/交付错误与审美偏好，只重做失败画幅（`--aspect 3x4`） |

## api 模式（全自动回退）

```bash
python scripts/generate_cover.py --video <视频> --title "<主标题>" [--subtitle ...] --mode api
```

脚本调 Ark 视觉模型分析（挑帧+写 prompt）+ Seedream 生图一条龙。排查参数：`--dry-run`（零 API 只备料）/ `--skip-generate`（只分析写 prompt 不生图）/ `--candidate-seconds 1,8,24.5`（手动指定取帧跳过预筛）。

## 配置与凭据（红线：key 绝不进任何 git 跟踪文件）

- key 三级：环境变量 `ARK_API_KEY`（优先）→ 当前目录向上 8 级找 `.ark_key`（一行明文）→ `--api-key-file` / 配置 `api_key_file`（aigen 子技能同款约定）
- ⚠️ 控制台列表里的 `apikey-xxxx` 是**脱敏显示**，要用「查看/复制」拿完整串；**模型 ID 必须带日期后缀**；404 `NotFound` = 未开通或 ID 错（Ark 对未开通模型也报 NotFound）；429 `SetLimitExceeded` = 安全体验模式限额——脚本已把这些翻译成人话，模型候选链内置自动降级

## 产物

- 最终封面：`<视频名>_3x4.png`（小红书）、`_4x3.png`（B站首页主封面）、`_16x9.png`（B站个人空间，独立上传该槽），落视频旁边
- 中间产物：`<视频名>.cover/`——`frames/` 候选帧、`analysis.json`、`<画幅>.prompt.md` sidecar、`manifest.final.json`（含实际用到的模型 `image_models_used`）、各画幅 `.response.json`
- 头像（可选默认关）：配置 `creator_portrait.enabled+path` 后，生图完由 Pillow 按固定布局合成右下角；头像**绝不**作为分析/生图参考图上传

## 不可违反（继承上游）

1. 生图模型一次性生成完整无人物底图（真实屏幕证据+标题+产品标识+点缀+风格化）；本地后处理只允许头像合成一项——不贴字、不贴 Logo、不拼图、不裁切改版、不视觉修补
2. 无人物：截图、重建 UI、底图不出现人脸/头像/摄像头气泡/吉祥物；配置启用头像时唯一例外是那张代码合成的头像
3. 绝不把历史案例的产品名/模型名/关键词/品牌色/点缀带入当前封面——外层文字与点缀只来自当前视频/标题/字幕/截图/用户补充；外置 Logo 必须对应主标题或显式传入，缺可信资产就不放（不发明近似标识）
4. 标题逐字锁定：断行必须逐字拼回用户原题，不在英文标识或版本号内部断开；统一替换完整标题指令只保留一套标题与断行
5. 每次生图保存 `.prompt.md` sidecar；保留 `cover_plan.md` 与 manifest；不伪造工具记录
6. 返工只重做失败画幅；替换最终图前把仍可用旧图+sidecar 成套留存（可回退）；文档只写当前最终状态，不写修改历史/changelog
7. 修改已有风格（用户嫌字号/留白/局部排版）：只调对应问题，保留字体气质、配色体系、透视、装饰、主体表达；未要求换风格不全盘重写
8. key 不进提示词/sidecar/日志/最终回复/任何 git 跟踪文件

## 技术事实（坑已趟，别再踩）

- **Seedream 会把具体数值/CSS 串当字面文字画进图**：prompt 里反引号包的阴影值（如 `0 18px 44px rgba(...)`）被原样渲染成图片文字+标注引线（S3 E2E 实锤，两画幅返工）。写阴影/间距一律用描述性语言（soft/large-blur/low-opacity），并在 Avoid 里禁 rendered code text；脚本的硬规则回填已同步去数值化
- Ark 兼容 OpenAI 格式：分析 `/api/v3/chat/completions` 传图（data URI）；生图 `/api/v3/images/generations` + `image` 参数传参考帧（data URI），无独立 edits 端点
- 内置模型候选链：分析 `doubao-seed-1-6-flash-250615 → seed-1-6 → 1-5-vision-pro`；生图 `doubao-seedream-5-0-flash-260915 → 5-0-pro-260628 → 4-5-251128 → 4-0-250828`（第一个已开通的胜出；`--analysis-model/--image-model` 指定则只试那个）
- 三画幅默认 2K 级：3:4=`1536x2048`、4:3=`2048x1536`、16:9=`2048x1152`（`--portrait-size/--landscape-size/--bilibili-size` 可改）
- 本地依赖：Python 3.10+、numpy+Pillow（评分/头像）；ffmpeg 选帧——PATH 没有时自动回落 imageio_ffmpeg 自带二进制（本机常态，与 cut 同款思路）；ffprobe 可选，缺了用 ffmpeg 读时长
- mode=agent 且无 `--prompt-file` 直接跑 → 脚本人话报错指路，不会偷偷调 API
