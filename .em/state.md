# state.md — 项目当前状态（rec 默认只读这个）

> ⚡ ≤50 行单一恢复源；详细历史按需查 features/、decisions.md、problem-log.md

## Meta
- **项目**: media-review（自媒体 skill /media 门面：cut/post/review/benchmark/cards/aigen/workbench/draft/shoot）
- **类型**: general
- **当前步骤**: S3-cover-skill ✅ 交付（376 全绿+真实一期 E2E 三画幅验收，旧 oil-cover 保留）∥ S4-delivery-loop ✅ 交付（356 绿+真项目 dry-run）
- **更新时间**: 2026-11-07
- **会话**: sess-20261105-001

## 下一步动作
1. S4 验收：重启 8790 旧服务（v4→v5）→ 面板点「✂️剪这个」→ 对话跑 `粗拼小样.py --queue` 真渲一个小样看效果；之后逐个 Rxx 用起来
2. S3 验收：看 E2E 封面 `C:\Users\23393\AppData\Local\Temp\cover_e2e\R04_分屏并行_v2_{3x4,4x3,16x9}.png`（R04 v2 真实成片段，临时沙箱）；满意后真实项目里直接 `/media cover` 用起来
3. 拿真实一期走新链路：`/media draft` 定稿锁+呈现批注 → 导出拍摄清单 → 拍摄 → `/media shoot` 素材回收 → 剪辑交接给 cut
4. P1a 阈值标定：R02 素材+剪切稿 srt 跑 `--weld-gap 2.0` vs `0` 对比（problem-log P1a）
5. 功能候选：B 导出的 AI 任务「产物建议路径」双基准观察 / AI 直改接缝

## 最近 3 条关键决策
- [2026-11-07] S3 cover 交付定音：基线取上游 tarball 最新（diff 同步了上游 gemini-3.8 时代更新）；分析双模式同一把 ARK key（agent 默认零分析 API / api=doubao 视觉回退）；Seedream 候选链首开即用（5-0-flash-260915）；E2E 揪出 Seedream 数值串泄漏坑（prompt 禁 CSS 值，backfill 已去数值化）；本机无 ffmpeg/ffprobe→脚本自动回落 imageio_ffmpeg；旧 oil-cover 保留不删（用户改判）
- [2026-11-07] S4（P13 立项，编号让位并行会话 cover-skill）定音：执行者必须是对话 AI（用户否决面板直达）；桥=shoot.json 新增 cutQueue（面板专属写）/deliverables（agent 只许追加）两节，version→2 增量兼容；小样=该批注全部选用素材整段硬切 720p 快渲
- [2026-11-05] S2 交付定音：agent 回写白名单 tasks[].state/output+footage[].state/note；项目根=素材目录层（校验器 --root 与 footage.file 同基准）；缺拍清单收敛人工拍摄口径；呈现批注 id 烧录池含 footage/tasks 引用（删后不复用）

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
| S3 cover-skill 计划 | `features/S3-cover-skill/plan.md` |
| S4 delivery-loop 计划 | `features/S4-delivery-loop/plan.md` |
