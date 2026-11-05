# media-review 开发上下文

自媒体 skill：`/media` 一个入口，门面路由子技能——**cut**（发前剪辑提效）+ **post**（发前后处理）+ **review**（发后数据复盘）+ **benchmark**（找对标拆解模仿，B站公开接口+小号）+ **cards**（录屏用 HTML 卡片：插播信息卡/分步 PPT，oil-cover 视觉体系，空格分步对口播；纯动画代码直出归 Remotion 不归它）+ **aigen**（AI 生图素材：火山方舟 Seedream 按量生成表情包贴纸/插画/封面配图，提示词规范+角色一致性+去底；key 走 ARK_API_KEY/.ark_key 绝不进仓库）+ **draft**（大纲/脚本审阅修改工作台：AI 初稿 md 进网页逐块编辑+批注四件套，✨复制修改清单喂 AI，md 本体纯净写回，定稿锁定+呈现批注排拍摄计划）+ **shoot**（定稿后拍摄计划链路：素材回收关联呈现批注+候选/选用+缺拍清单+剪辑批注，编译 05_剪辑交接 给 cut；AGENT_PROTOCOL.md 让任意 agent 领任务回写）。设计文档：复盘系统以 vault `03_项目/自媒体复盘系统/设计文档.md` 为准（本仓 `docs/design.md` 是同步副本；vault 是作者个人知识库，不开源）；剪辑提效以 vault `30_方法论/剪辑提效工作流.md` 为准（方法论沉淀，skill 是其执行规程）。所有知识库路径走 `_config_local.json` 的 `paths` 配置（schema 见仓根 `config.example.json`），不硬编码个人目录结构。

## 这是什么

单个 skill（`skill/media/`），门面 SKILL.md 按用户意图分发到子技能目录：

- **cut**：三层漏斗粗剪——①静音压缩（`silence_trim.py`）→ ②FunASR 转录（`asr_funasr.py`，热词可加；AutoCut/Whisper 备选）+ AI 初选删行（人工复核后 `srt_cut.py` 剪切）→ ③精剪交接；逐字稿归档知识库 `transcripts` 配置目录，是 review 复盘的直接输入（发前喂发后闭环）
- **review**：清算到期观察点（D+3/D+7/D+30）→ B站自动取数（创作中心接口，Cookie 鉴权）→ 收集窗收抖音/小红书数据（后台导出 xlsx 优先，截图兜底） → 按爆款公式三要素（选题×素材×内容）归因 → 复盘报告写回 Obsidian vault → 半自动写回选题池/复用片段/对标
- **benchmark**：B站找对标（公开接口：搜索/详情/评论区，匿名可用）→ 小号（`bench_sessdata`，与大号隔离）拉 AI 字幕逐字稿 + yt-dlp 下载视频 → 按爆款公式拆解写对标笔记进 vault 对标目录 → 可模仿要素确认制写回选题池/下期规划；review 的"对标校准"直接读它的笔记
- **aigen**：AI 生图素材（火山方舟 Seedream 按量）——提示词按官方规范（自然语言完整句+双引号烤字+组图锁角色）→ 单张验画风再批量（`gen_image.mjs`，模型 ID 带日期后缀按序降级）→ 洪泛去底（`debg.py`）→ 产物落目标工程 `public/` 接渲染；key 走 `ARK_API_KEY`/`.ark_key` 绝不进仓库，未授权 IP 形象不当每期固定资产
- **draft**：大纲/脚本审阅修改工作台——AI 初稿 md 进网页（`draft_server.py` 起本地服务，纯标准库）逐块编辑+批注四件套（删/换/评/亮）→ ✨复制修改清单喂 AI 改稿 → md 本体纯净写回（round-trip 逐字节保真，批注存旁车 `.review.json`，锚定 hash→quote→orphan 三级回落）→ 定稿锁定（md 只读）+🎬呈现批注（人工拍摄/AI 制作+指令，旁车 `.md.shoot.json`）+📋拍摄清单导出
- **shoot**：定稿后拍摄计划链路——素材回收匹配（文件名含 Rxx 约定优先+AI 建议+人工确认面板，手动添加素材一等路径）→ 候选/选用+缺拍清单 → 补制任务（card/motion/aigen/reshoot，AGENT_PROTOCOL.md 供任意 agent 领取，白名单回写越权拒收）→ 剪辑批注 → 两条出口：编译 `05_剪辑交接/`（素材副本+剪辑说明.md）给 cut 规程，或 🎬选用素材按批注顺序粗拼直出剪映草稿（`剪映草稿.py`，pyJianYingDraft 懒加载，防覆盖自动 v2）精细剪辑

## 结构

```
skill/media/SKILL.md                门面（意图路由，唯一对外触发的 SKILL.md）
skill/media/cut/SKILL.md            cut 子技能（三层漏斗流程+初选规则）
skill/media/cut/scripts/silence_trim.py        静音压缩（零依赖，ffmpeg 自动发现）
skill/media/cut/scripts/asr_funasr.py          FunASR 转录出 SRT（funasr 重依赖，模型走 ModelScope 国内 CDN）
skill/media/cut/scripts/srt_cut.py             SRT 删行剪切（零依赖，复用 silence_trim 的 select/aselect 过滤器）
skill/media/review/SKILL.md         review 子技能（流程+诊断框架）
skill/media/review/scripts/fetch_bili.py       B站取数（纯标准库，仅取自己账号数据）
skill/media/review/scripts/screenshot_tray.py  截图收集窗（tkinter+Pillow，复盘时启动非常驻）
skill/media/benchmark/SKILL.md      benchmark 子技能（找对标→拉取→拆解→写回）
skill/media/benchmark/scripts/bili_bench.py    B站对标工具（公开接口匿名可用+小号登录，纯标准库）
skill/media/benchmark/templates/对标拆解模板.md  拆解笔记模板（爆款三要素+可模仿清单）
skill/media/aigen/SKILL.md          aigen 子技能（AI 生图素材：提示词规范+流程+坑表）
skill/media/aigen/scripts/gen_image.mjs        Seedream 生成（node ≥18 零依赖，组图/参考图/模型降级）
skill/media/aigen/scripts/debg.py              洪泛去底（PIL，边缘连通背景→透明）
skill/media/draft/SKILL.md          draft 子技能（审阅工作台：人工操作+AI 配合剧本+数据格式红线）
skill/media/draft/scripts/draft_blocks.py      md⇄块数组双向解析（round-trip 逐字节保真+批注锚定三级回落）
skill/media/draft/scripts/draft_server.py      本地服务（纯标准库：静态托管+open/save/review/list API）
skill/media/draft/scripts/shoot_io.py          定稿旁车 shoot.json 读写+schema 校验+agent 回写 diff（S2）
skill/media/draft/scripts/shoot_export.py      拍摄计划清单+AI制作任务导出（S2）
skill/media/draft/web/              前端三件套（原生 JS 自包含零 CDN：块编辑+批注面板+✨AI清单+🎬呈现批注）
skill/media/shoot/SKILL.md          shoot 子技能（素材回收关联+剪辑批注+cut 交接）
skill/media/shoot/scripts/素材回收.py           素材回收匹配器（文件名含 Rxx 约定优先，纯标准库）
skill/media/shoot/scripts/shoot_server.py      素材面板服务（纯标准库，只绑 127.0.0.1）
skill/media/shoot/scripts/剪辑交接.py           补制任务生成+05_剪辑交接编译（素材副本+剪辑说明.md）
skill/media/shoot/scripts/shoot_validate.py    agent 回写校验（白名单 diff，越权拒收）
skill/media/shoot/scripts/emit_protocol.py     AGENT_PROTOCOL.md 发射进项目目录
skill/media/shoot/AGENT_PROTOCOL.md   跨 agent 协作规程卡（zcode/claude code/codex 通用）
skill/media/shoot/web/              素材面板前端三件套（零 CDN 自包含）
install.ps1                         安装 media skill + 依赖（Pillow/qrcode/imageio-ffmpeg）+ 清理旧版目录
tests/                              unittest + fixtures（录制的接口响应结构）
docs/design.md                      复盘系统设计文档副本
```

## 红线

1. **数据接口只取自己账号的**——review/cut/post 所有接口都是创作中心（member.bilibili.com）+ 大号 Cookie。唯一例外 **benchmark 子技能**：仅限 B站**公开内容**（搜索/稿件详情/评论区/AI字幕/下载对标视频），个人学习拆解用；登录态只准小号 `bench_sessdata`（与大号 `sessdata` 物理隔离，大号绝不进这条链路），脚本内建限速、单次批量 ≤5 条，禁止批量爬取、禁止二传发布
2. Cookie 只从 vault 侧 `_config_local.json` 读（已 gitignore），禁止出现在任何入库文件里
3. 诊断逻辑写在 SKILL.md（Claude 推理），Python 只管取数和解析，不写死评分规则

## 开发约定

- 中文注释；接口字段注释对齐 bilibili-API-collect 文档
- 改完 `git add . && git commit -m "AI: <动作>"`
- fetch_bili.py 保持零第三方依赖（标准库 only），GUI 只允许 Pillow
- 测试：`python -m unittest discover tests -v`，fixtures 是手工构造的接口响应样本，不真连 B站
