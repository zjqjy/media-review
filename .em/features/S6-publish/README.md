# S6-publish — 三平台自动发布子技能（ego 直驾 + SOP 教材化）

> 状态卡：feature 目录的入口，`/em pi` 与 `/em stat -v` 扫描本行
> 模板：templates/feature-README.md（S17-D）

| 字段 | 值 |
|------|-----|
| 状态 | 🔄 开发中（A~D 交付：骨架+dry-run 三平台全通+471 绿；E 真发待用户在场） |
| 档位 | 中 |
| 日期 | 2026-11-07（A~D 完成 2026-11-08） |
| HVR | `hvr.md`（verify 后存在） |

## 一句话目标
给成片视频 + 封面，确认一次标题简介后，agent 用 ego-browser 模拟人类操作自动发布小红书/B站/抖音，链条 cut→工作台→cover→publish 闭环。

## 关键决策（≤3 条）
- [2026-11-07] 方案A 定音：agent 直驾 ego-browser + SOP 教材化——调研项目只抄知识不抄运行时，避 CSS 选择器腐烂死穴
- [2026-11-07] 验证=dry-run 停「发布」按钮前截图（用户仅一期真视频，不烧测试内容）；首跑真发用户在场
- [2026-11-07] 登录态=ego 持久 profile 每平台独立，失效 handOff 人工扫码；主号与 benchmark B站小号隔离

## 产物清单
- `plan.md` — 需求理解（R0 四问）+ 方案对比 + 拆分（S6-A~E）
- `hvr.md` — 验证请求与结果

<!-- feature 完成时：整个目录由 /em result 提示 mv 到 history/（LIFECYCLE #8） -->
