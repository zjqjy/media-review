# S7-A 三线调研评估卡（2026-11-08）

> 检索面：GitHub Search API（transcript→blog 线 37 结果全扫）+ WebSearch 补查（L3 命中 6 项目）
> + core API 实锤 12 仓库（星数/维护度/机制关键词）+ jiji262 全 README 精读。
> 限流备注：Search API 限流严重（共享 IP），L1 中文词组搜索未跑成，EN 全量已足以下结论。

## 线① 文风/逐字稿→教程引擎 → **放弃引入引擎，借鉴 ai_score.py 加签**

| 候选 | 实锤 | 判定 |
|------|------|------|
| royshil/video-transcript-helper | ★12，archived | 弃 |
| shirleyisdoingrightthings/youtube-transcript-scraper-and-summary | ★2，2026-11-06 | 弃（agent 实验品） |
| sadaqatyar/YouTube-Video-to-Blog-Pipeline / dibishks/youtube-to-blog 等 | ★1~2，共 37 个全是 weekend 级 | 弃 |

- **结论**：逐字稿→图文教程是「提示词管线」问题不是「包」问题，无成熟开源。本项目已有 post 逐字稿归档 + STYLE.md 硬规则 + em learn humanize 终检——引入外部文风引擎必与红线冲突（R1 已钉死）。
- **借鉴点**：[jiji262/wechat-publisher](https://github.com/jiji262/wechat-publisher) 的 `ai_score.py`（AI 味 6 维加权 + 确定性伪影罚分 + advisory 清单）+ `references/anti-ai-checklist.md`——可作为博客终检的**加签器**（MIT，python，依赖仅 requests/pyyaml，可提取）。终检主体仍是 STYLE.md+humanize（红线不动）。

## 线② md→公众号排版 → **引入 jiji262 转换器+主题，doocs/wenyan 列备选**

| 项目 | ★ | push | 机制 | 判定 |
|------|---|------|------|------|
| [jiji262/wechat-publisher](https://github.com/jiji262/wechat-publisher) | 293 | 2026-10-30 | `html_converter.py` + 15 套主题 JSON（`assets/themes/*.json`，纯内联样式无外部依赖，正文 ~15.5px/行高 1.85），deps=requests/pyyaml，MIT | ✅ **引入**（抽排版转换器+主题，不引自动创作线） |
| [doocs/md](https://github.com/doocs/md) | 13516 | 2026-11-03 | pnpm monorepo React **编辑器应用**，非可复用库 | 备选（抽渲染核成本高） |
| [caol64/wenyan](https://github.com/caol64/wenyan) / [wenyan-mcp](https://github.com/caol64/wenyan-mcp) | 1092 / 1357 | 活跃 | Swift mac 排版 app / npm MCP（发布段走 API 线） | 备选（MCP 发布段不适用，排版可参考） |
| mdnice/markdown-nice | 4679 | **2023-10 停更** | 编辑器，135 open issues | 弃 |

- **引入方式**：`html_converter.py` + 主题 JSON 进 `skill/media/blog/`（注明 MIT 出处），供 S7-D 排版层用；不符合本项目风格时 fallback 自研（主题表抄 jiji262）。

## 线③ 公众号自动发布 → **放弃引入，ego 自研直驾（S6 预案转正）**

- **API 线死路实锤**：[jiji262/wechat-publisher](https://github.com/jiji262/wechat-publisher)（AppID/AppSecret+IP 白名单+access_token）、[k7airos/wx-publish-studio](https://github.com/k7airos/wx-publish-studio)（★47）、[QuantumHW/PubAgent_WeChat](https://github.com/QuantumHW/PubAgent_WeChat)（★1）、KevinLby/wechat-ai-publisher（★1）——草稿箱 API 需**认证**公众号，个人主体无法微信认证 → 全线不可用。
- **浏览器自动化线**：无成熟开源项目（仅 smartchainark 的 [MCP+Playwright SOP 文档](https://github.com/smartchainark/ai-web3-blueprint/blob/main/zh/sops/014-wechat-mp-auto-publish-mcp-playwright.md) 可抄知识）；wechatsync 类插件形态与 ego 直驾架构不合。
- **结论**：ego 自研驱动器到「存草稿」（S6「只抄知识不抄运行时」结论直接复用，Playwright SOP 文档进参考清单）。jiji262 的 API 坑位表（40164 IP 白名单/40001 token/45166 内容合规）标注「API 线参考」，对本线不适用；45166 敏感词提醒对草稿内容仍有参考价值。

## 对后续子步骤的影响

- **S7-B**：选帧无现成开源 → fallback 自研（ffmpeg+srt 时间轴对齐）**转正为主案**；文风=STYLE.md+humanize 终检，`ai_score.py` 提取为加签器（引入）
- **S7-D**：排版层=引入 jiji262 `html_converter.py`+主题 JSON；后台操作层=ego 自研驱动器（不变）
