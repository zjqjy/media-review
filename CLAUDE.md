# media-review 开发上下文

自媒体 skill：`/media` 一个入口，门面路由两个子技能——**cut**（发前剪辑提效）+ **review**（发后数据复盘）。设计文档：复盘系统以 vault `03_项目/自媒体复盘系统/设计文档.md` 为准（本仓 `docs/design.md` 是同步副本；vault 是作者个人知识库，不开源）；剪辑提效以 vault `30_方法论/剪辑提效工作流.md` 为准（方法论沉淀，skill 是其执行规程）。所有知识库路径走 `_config_local.json` 的 `paths` 配置（schema 见仓根 `config.example.json`），不硬编码个人目录结构。

## 这是什么

单个 skill（`skill/media/`），门面 SKILL.md 按用户意图分发到子技能目录：

- **cut**：三层漏斗粗剪——①静音压缩（`silence_trim.py`）→ ②FunASR 转录（`asr_funasr.py`，热词可加；AutoCut/Whisper 备选）+ AI 初选删行（人工复核后 `srt_cut.py` 剪切）→ ③精剪交接；逐字稿归档知识库 `transcripts` 配置目录，是 review 复盘的直接输入（发前喂发后闭环）
- **review**：清算到期观察点（D+3/D+7/D+30）→ B站自动取数（创作中心接口，Cookie 鉴权）→ 收集窗贴抖音/小红书截图 → 按爆款公式三要素（选题×素材×内容）归因 → 复盘报告写回 Obsidian vault → 半自动写回选题池/复用片段/对标

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
install.ps1                         安装 media skill + 依赖（Pillow/qrcode/imageio-ffmpeg）+ 清理旧版目录
tests/                              unittest + fixtures（录制的接口响应结构）
docs/design.md                      复盘系统设计文档副本
```

## 红线

1. **只取自己账号的数据**——所有接口都是创作中心（member.bilibili.com）+ 自己 Cookie，禁止加任何爬取他人内容的功能
2. Cookie 只从 vault 侧 `_config_local.json` 读（已 gitignore），禁止出现在任何入库文件里
3. 诊断逻辑写在 SKILL.md（Claude 推理），Python 只管取数和解析，不写死评分规则

## 开发约定

- 中文注释；接口字段注释对齐 bilibili-API-collect 文档
- 改完 `git add . && git commit -m "AI: <动作>"`
- fetch_bili.py 保持零第三方依赖（标准库 only），GUI 只允许 Pillow
- 测试：`python -m unittest discover tests -v`，fixtures 是手工构造的接口响应样本，不真连 B站
