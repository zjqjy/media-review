# media-review

自媒体 skill（Claude Code）：**一个 `/media` 入口，管一条内容的发前和发后**。

```
skill/media/
├── SKILL.md      门面：按意图路由
├── cut/          子技能 · 剪辑提效（发前）
└── review/       子技能 · 数据复盘（发后）
```

- **cut · 剪辑提效**：教程类长素材三层漏斗粗剪——①静音压缩（自研 silence_trim.py，ffmpeg silencedetect，全自动）→ ②FunASR 转录（自研 asr_funasr.py，中文识别强、热词可加）+ AI 初选（删句子 = 剪视频）→ ③精剪交接剪映/PR。副产物 SRT 字幕 + 逐字稿
- **review · 数据复盘**：B站全自动取数，抖音/小红书截图收件箱，按"爆款公式"（选题×素材×内容）归因回写 Obsidian 知识库

```
3h 素材 ──cut──▶ 粗片 + SRT + 逐字稿（归档 vault 复盘/逐字稿/）
                     │ 发布
                     ▼
                  review ──▶ 复盘报告 ──确认──▶ 写回选题池/复用片段/对标
                     ▲                                 │
                     └──── 下条改动进改进实验，下期复盘先核对 ────┘
```

## 为什么

**剪辑**：60:1 的素材压缩率（3 小时素材 → 5 分钟成片），最费时的不是精剪，是看素材选段——无声素材没有时间索引，只能人眼过。三层漏斗让机器先吃掉"确定没用的大段"（静音冷场），人只处理剩下的；转录之后"删句子 = 剪视频"。

**复盘**：视频发出去之后没有系统复盘：不知道哪条行、为什么行、下条改什么。review 把复盘变成一个固定动作，改进点跨期跟踪验证，有效方法沉淀进知识库。

## 安装

```powershell
git clone https://github.com/zjqjy/media-review.git
cd media-review
.\install.ps1
```

装完一个 skill 在 `~/.claude/skills/media/`（旧版拆装的 media-review / media-cut 目录会自动清理）。然后按提示配置 B站登录——二选一：

- **扫码（推荐）**：`python skill/media/review/scripts/fetch_bili.py login --config "<vault>\20_自媒体\复盘\_config_local.json"`，二维码自动弹出，B站 App 扫一下即自动写入
- **手动**：把 `_config_local.example.json` 复制为 `_config_local.json`，B站网页 F12 → Application → Cookies → 复制 SESSDATA 粘进去

## 使用

在 Claude Code 里喊 `/media`，门面按意图自动路由：

**要剪素材**（说"粗剪 / 砍静音 / 转录选段"）→ cut：

1. 静音压缩：`silence_trim.py` 自动砍 >2s 冷场（3h → ~1h，挂机）
2. 文本粗剪：`asr_funasr.py` 转录出带时间戳的 SRT（技术词可加热词），Claude 按内容大纲标保留/删/收紧，你复核后 `srt_cut.py` 一句命令剪出粗片
3. 精剪交接：粗片 + SRT + 收紧清单丢进剪映/PR

**发完视频**（说"复盘 / 看数据"）→ review：

1. 清算所有"今天到期"的观察点（D+3/D+7/D+30）；B站自动拉数据，抖音/小红书贴收集窗截图
2. 输出三要素归因 + 下条可执行改动（最多 3 条）
3. 给出"建议写回"清单，你确认后才写入选题池/复用片段/对标笔记

## 合规说明

- 只通过 B站创作中心接口读取**自己账号**的数据（Cookie 鉴权，与浏览器登录同源），不爬取任何他人内容
- 抖音/小红书数据来自**官方创作中心的截图**，人工手动提供，无任何自动化访问
- Cookie 保存在本地 gitignore 文件中，不出现在任何入库文件和网络传输（仅发往 B站官方接口）
- cut 只处理用户自己的素材；重依赖（torch 级：funasr/AutoCut）安装必须用户点头
