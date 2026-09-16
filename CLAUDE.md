# media-review 开发上下文

自媒体发布后数据复盘系统。设计文档（唯一真值）：vault `03_项目/自媒体复盘系统/设计文档.md`（本仓 `docs/design.md` 是同步副本，以 vault 为准）。

## 这是什么

Claude Code skill：手动喊 `/media-review` → 清算到期观察点（D+3/D+7/D+30）→ B站自动取数（创作中心接口，Cookie 鉴权）→ 收集窗贴抖音/小红书截图 → 按爆款公式三要素（选题×素材×内容）归因 → 复盘报告写回 Obsidian vault → 半自动写回选题池/复用片段/对标。

## 结构

```
skill/media-review/SKILL.md        主技能（流程+诊断框架，安装到 ~/.claude/skills/）
skill/media-review/scripts/fetch_bili.py   B站取数（纯标准库，仅取自己账号数据）
tools/screenshot_tray.py           截图收集窗（tkinter+Pillow，复盘时启动非常驻）
install.ps1                        安装 skill + 依赖
tests/                             unittest + fixtures（录制的接口响应结构）
docs/design.md                     设计文档副本
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
