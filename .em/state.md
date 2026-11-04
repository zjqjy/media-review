# state.md — 项目当前状态（rec 默认只读这个）

> ⚡ ≤50 行单一恢复源；详细历史按需查 features/、decisions.md、problem-log.md

## Meta
- **项目**: media-review（自媒体 skill /media 门面：cut/post/review/benchmark/cards/aigen/workbench/draft）
- **类型**: general
- **当前步骤**: S2-shoot-pipeline 📋（定稿后拍摄计划链路，5 阶段讨论完，方案落盘待开发）
- **更新时间**: 2026-11-05
- **会话**: sess-20261105-001

## 下一步动作
1. S2-A 开发：shoot.json schema+校验 → draft 工作台呈现批注（人工/AI制作+quote圈句）→ 定稿锁定；完成后 `/em verify s2`
2. 执行序：A → B∥C → D → E（E 跨 agent E2E 收官）；落点=draft 扩展 + 新子技能 shoot，不碰 workbench

## 最近 3 条关键决策
- [2026-11-05] S2 五难点选定：quote 锚定/素材全人工确认/单旁车 shoot.json 分节/AGENT_PROTOCOL.md 规程卡/③只做编排不造剪机
- [2026-11-05] 素材归位用混合模式（用户点名）：命名约定优先+AI 匹配兜底+人工确认收尾；workbench 不参与（用户排除）
- [2026-11-03] S1 选方案 A 自研块编辑器：md 本体纯净+旁车 review.json（D2）

## 阻塞项 / 待办
- [ ] P1a 条目边界切字（未修，见 problem-log.md；S2 圈句锚定与其相邻，开发 A 时评估一并修）

## 详细资料指针
| 内容 | 文件 |
|------|------|
| 步骤全表 | `features/README.md` |
| 决策全集 | `decisions.md` |
| 问题追踪 | `problem-log.md` |
| S1 计划 | `features/S1-draft-workbench/plan.md` |
| S2 计划 | `features/S2-shoot-pipeline/plan.md` |
