# media-review

自媒体全流程 Claude Code skill：**一个 `/media` 入口，管一条内容从素材到复盘的完整生命周期**。嵌入式自媒体人（B站/抖音/小红书三平台）实测驱动的开源工作流。

```
skill/media/
├── SKILL.md      门面：按意图路由
├── cut/          子技能 · 剪辑提效（发前）：三层漏斗粗剪
└── review/       子技能 · 数据复盘（发后）：三平台合参归因
```

- **cut · 剪辑提效**——教程类长素材（60:1 压缩率）的三层漏斗粗剪：
  ① 静音压缩：`silence_trim.py` 自动砍冷场（实测 75 分钟 → 19.5 分钟，砍 74%）
  ② FunASR 转录 + AI 初选：`asr_funasr.py` 转录出从句级 SRT（CPU 16 倍实时，热词支持），AI 按内容大纲删句修错；句首口头禅（"然后"）按**字级时间戳词级跳剪**自动抠掉
  ③ 剪映草稿直出：`jy_draft.py` 生成拼好的剪映草稿——保留段引用原素材**零重编码**，附字幕轨 + 红色标注轨（口吃/重说提示），剪切点在剪映里仍是可拖的分割线
- **review · 数据复盘**——B站自动取数为轴（创作中心接口，Cookie 鉴权），抖音/小红书截图收件箱，按"爆款 = 选题 × 素材 × 内容"三要素归因，改进点跨期跟踪验证回写知识库

```
3h 素材 ──cut──▶ 剪映草稿（主轨+字幕+标注）──精剪发布──▶ review ──▶ 复盘报告 ──▶ 写回/改进实验
                    │                                      ▲
                    └── 逐字稿归档 vault，review 直接取（发前喂发后闭环）
```

## 实测数据（第2期 ESP32 环境搭建素材）

| 环节 | 结果 |
|---|---|
| ① 静音压缩 | 75:33 → 19:28（砍 74%），录屏段 67-86%，产物时长逐秒对齐 |
| ② 转录 | 9:48 音频 49 秒转完（RTF 0.06，纯 CPU）；标点/中文/热词中文词全对 |
| ② AI 初选 | 整句只删铁废料（整段重复/纯语气词/乱码）15%；修错 58 条 |
| ② 词级跳剪 | 38 个句首"然后"按字级时间戳精确抠掉，字幕同步剥字 |
| ③ 草稿直出 | 主轨 79 段零重编码，剪映 11.x 实测可开；静音细剪再挤 12s |

## 安装

要求：Windows + Python 3.10+ + 剪映专业版（可选，草稿直出用）。

```powershell
git clone https://github.com/zjqjy/media-review.git
cd media-review
.\install.ps1
```

install.ps1 装 skill 到 `~/.claude/skills/media/` 并检查全部 Python 依赖：

| 依赖 | 用途 | 说明 |
|---|---|---|
| Pillow / qrcode | review 截图收集窗 / 扫码登录 | 轻量 |
| imageio-ffmpeg（或 PATH ffmpeg） | cut 全部剪切脚本 | 随包二进制，无需全局安装 |
| pyJianYingDraft | cut 草稿直出 | 轻量 |
| funasr + torch + torchaudio | cut 转录 | torch 级重依赖；**装包开 VPN，转录下模型（ModelScope ~1.2G）关 VPN 直连** |

**B站登录**（review 用，二选一）：

- 扫码（推荐）：`python skill/media/review/scripts/fetch_bili.py login --config "<vault>\20_自媒体\复盘\_config_local.json"`，二维码自动弹出，B站 App 扫一下即写入
- 手动：F12 → Application → Cookies → 复制 SESSDATA 到 `_config_local.json`（该文件 gitignore，不入库）

## 使用

在 Claude Code 里喊 `/media`，门面按意图路由：

**要剪素材**（"粗剪 / 砍静音 / 转录选段"）→ cut：

1. 静音压缩挂机跑，报砍掉比例
2. 转录（口头禅自动剥成 `.cuts.json`）→ AI 按大纲初选（只删铁废料：整段重复/纯语气词/乱码；口吃假起头保留并标注）→ 你复核剪切稿
3. 剪映草稿直出 → 你在剪映精剪（红色标注就是 to-do list），导出前删标注轨

**发完视频**（"复盘 / 看数据"）→ review：清算到期观察点（D+3/D+7/D+30）→ 三平台合参 → 三要素归因 + 下条改动（最多 3 条）→ 确认后写回选题池/复用片段/对标。

## 设计原则

- **AI 不替用户拍板**：初选结果复核后才剪切；复盘写回确认制；品味判断是人
- **只碰自己的数据**：B站仅创作中心接口读自己账号；抖音/小红书数据来自官方创作中心的人工截图，无任何自动化访问；cut 只处理用户自己的素材
- **诊断在 SKILL（Claude 推理），Python 只管取数/解析/剪切**，不写死评分规则

## Roadmap

- [ ] **重复检测增强**：音频级重复检测（当前"整段重复"靠转录文本比对，同义改写测不出）
- [ ] **口头禅扩展**：句中"然后"（非句首）词级跳剪；音频级口吃检测（当前标注按文本叠词，字幕修错后会漏标）
- [ ] **粗剪效果复核闭环**：粗剪版本发布后，用 review 的 CTR/完播/留存曲线回查初选删句是否伤节奏、词级挖洞是否切字，回流修正初选规则
- [ ] **抖音/小红书数据自动获取**：已调研并否决"AI 浏览器自动化打开创作中心截图"路线——平台协议明确运营数据归平台所有，自动化访问（即使只读自己数据）违反用户协议且 AI 风控（如小红书阿瑞斯）可致限流封号，风险与低频复盘的收益不成比例；合规路线为官方 API（抖音开放平台视频数据接口 / 小红书专业号数据接口），接入前保持人工截图
- [ ] 账号周期复盘（月度报告）；FunClip LLM 选段对照

## 项目结构

```
skill/media/SKILL.md                门面（意图路由）
skill/media/cut/SKILL.md            cut 子技能（三层漏斗规程）
skill/media/cut/scripts/silence_trim.py   ①静音压缩（ffmpeg silencedetect）
skill/media/cut/scripts/asr_funasr.py     ②FunASR 转录（分句对齐/热词/口头禅剥离）
skill/media/cut/scripts/srt_cut.py        ②SRT 删行剪切（重编码出粗片，fallback）
skill/media/cut/scripts/jy_draft.py       ③剪映草稿直出（pyJianYingDraft）
skill/media/review/SKILL.md         review 子技能（按期复盘规程）
skill/media/review/scripts/fetch_bili.py  B站取数（纯标准库）
skill/media/review/scripts/screenshot_tray.py  截图收集窗（tkinter+Pillow）
install.ps1                         安装 skill + 全部依赖
tests/                              unittest + fixtures
docs/design.md                      复盘系统设计文档
```

方法论出处（个人知识库沉淀，不开源）：三层漏斗与复盘闭环的完整推理见作者 vault 的《剪辑提效工作流》《自媒体方法论体系》。

## 合规声明

- 只通过 B站创作中心接口读取**自己账号**的数据（Cookie 鉴权，与浏览器登录同源），不爬取任何他人内容
- 抖音/小红书数据来自**官方创作中心的截图**，人工手动提供；刻意不做自动化访问（原因见 Roadmap 调研结论）
- Cookie 保存在本地 gitignore 文件中，不出现在任何入库文件和网络传输（仅发往 B站官方接口）
- cut 只处理用户自己的素材；不提供任何下载/爬取他人视频的能力

## License

[MIT](LICENSE)
