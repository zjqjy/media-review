# 调研笔记：GitHub 三平台自动上传参考项目（S6-A）

> 日期：2026-11-07 · 结论喂 `../platforms.json` · 上游仓库不入库（临时克隆 %TEMP%/sau-ref-20261107）

## 检索结论

| 项目 | 路线 | 借了什么 | 不借什么 |
|------|------|---------|---------|
| [dreammis/social-auto-upload](https://github.com/dreammis/social-auto-upload) 13.7k★ | 抖音/快手=B 站部分=Playwright 表单流；B站=外挂 biliup CLI API 直传；小红书=API 签名链 | 抖音表单全知识（入口/选择器/字数/坑）、B站字段口径（title/desc/tid/tag/cover）、登录判定 | 它的 Playwright 运行时、storage_state cookie 两套皮、API 直传与签名链 |
| [xiaoliangliang/auto-publish](https://github.com/xiaoliangliang/auto-publish) | Chrome 扩展本地工作台，填表+人工确认发布 | 「填完人工确认再发」人机分工（与本项目 R0-1 选型不谋而合） | 扩展形态 |
| [rehatRot/omnipost](https://github.com/rehatRobot/omnipost) | 10+ 平台一键发布 | 佐证浏览器模拟是主流路线 | 全部 |

## 共同死穴 → 本技能的对策

CSS 选择器腐烂：页面改版即坏，修复等上游。对策=agent 现场 `snapshot()` 认路、选择器现场比对（platforms.json 里只是 selector_hint），SOP 写流程顺序不写死选择器。

## 从 sau 源码提取的硬知识（证据行号）

- 抖音入口 `creator.douyin.com/creator-micro/content/upload`（main.py:125）；扫码登录、URL 进 creator-micro 即成功（main.py:211-241）
- 上传控件 `input.upload-btn-input`，视频传完才渲染表单，等待给 120s，页面有 v1/v2 两版（main.py:994-1021）
- 标题 30 字硬截断 `title[:30]`（main.py:381）；描述 `div.zone-container[contenteditable]`（main.py:383，2026-06 DOM 注释）
- 封面必设弹窗、「完成」按钮关不掉弹窗要点别处（main.py:879 注释=用户 F12 实测根因）
- 身份验证组件只认整套原生事件序列，裸 click 不认（main.py:50-80）→ ego 真实鼠标路径天然满足
- B站走 biliup：`--title/--desc/--tid/--tag/--cover`，分区 tid 必填（sau_commands/bilibili.py:30-106）
- 小红书 API 签名链 `window._webmsxyw` 出 x-s/x-t + a1 cookie，失败重试 10 次（xhs_uploader/main.py:15-43）→ 反证 API 路线脆弱，我们走表单

## 字数上限口径

- 抖音标题 30（源码实锤）；其余（抖音简介 1000/B站标题 80·简介 2000/小红书标题 20·简介 1000）为待实测占位——**dry-run 时以页面 maxlength/计数器为准回写 platforms.json 并置 verified=true**
- B站分区树 tid 表：dry-run 时从投稿页面分区树采集常用子区回写

## 与 ego-browser 的能力对拍（2026-11-07 `ego-browser skill` v2.2.0）

| 需求 | ego API |
|------|---------|
| 传视频/封面文件 | `page.setInputFiles()` / `waitForFileChooser()` |
| 人工扫码 | `task.handOff()` 交人，确认后 resume 同 space |
| 页面认路（抗改版） | `page.snapshot()` 语义 ref |
| dry-run 存证 | `page.screenshot({ path })` |
| 富文本简介/人类输入 | `keyboard.type()` / `keyboard.paste({ text })` |
| 防自动化检测 | 页面 console 对站点隐藏；不 import Playwright，不起第二个浏览器 |
