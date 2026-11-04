# state.md — 项目当前状态（rec 默认只读这个）

> ⚡ ≤50 行单一恢复源；详细历史按需查 features/、decisions.md、problem-log.md

## Meta
- **项目**: media-review（自媒体 skill /media 门面：cut/post/review/benchmark/cards/aigen/workbench/draft/shoot）
- **类型**: general
- **当前步骤**: S2-shoot-pipeline ✅（五子流程+P1a 交付，289 单测绿，ego E2E 可用，跨 agent 回写实测通过，装位已同步）
- **更新时间**: 2026-11-05
- **会话**: sess-20261105-001

## 下一步动作
1. 拿真实一期走新链路：`/media draft` 定稿锁+呈现批注 → 导出拍摄清单 → 拍摄 → `/media shoot` 素材回收 → 剪辑交接给 cut；新反馈另开条目
2. P1a 阈值标定：R02 素材+剪切稿 srt 跑 `--weld-gap 2.0` vs `0` 对比（problem-log P1a）
3. 功能候选：B 导出的 AI 任务「产物建议路径」双基准观察 / AI 直改接缝

## 最近 3 条关键决策
- [2026-11-05] S2 交付定音：agent 回写白名单 tasks[].state/output+footage[].state/note；项目根=素材目录层（校验器 --root 与 footage.file 同基准）；缺拍清单收敛人工拍摄口径；呈现批注 id 烧录池含 footage/tasks 引用（删后不复用）
- [2026-11-05] 多 agent 并行开发模式验证：2 并发为上限，任务书文件域互斥+schema 冻结做共同契约；外部 agent 仅凭 AGENT_PROTOCOL.md 完成领任务-产卡-回写-自检全流程
- [2026-11-05] P1a 修法=build_spans VAD 焊回（WELD_GAP=2.0/VAD_BRIDGE_TOL=0.2，VAD 缺失自动降级）；S1 选方案 A 自研块编辑器（D2）

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
