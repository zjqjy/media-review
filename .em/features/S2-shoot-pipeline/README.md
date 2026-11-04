# S2 shoot-pipeline（定稿后拍摄计划链路）

> 状态：✅ 开发+E2E 验收完成（HVR 见 hvr.md）· 落点：draft 扩展 + 新子技能 shoot · 2026-11-05

| 子流程 | 内容 | 状态 |
|--------|------|------|
| S2-A | shoot.json schema + 呈现批注（draft）+ 定稿锁定 | ✅ 交付（shoot_io 412L+服务5路由+前端呈现批注/圈句/锁定） |
| S2-B | 拍摄计划清单导出 + ✨AI 制作任务清单 | ✅ 交付（shoot_export 260L+/api/shoot_export/双按钮） |
| S2-C | 素材关联（shoot 子技能：匹配器+批量确认+缺拍清单） | ✅ 交付（SKILL+匹配器+服务+web 三件套） |
| S2-D | 剪辑批注 + 补制任务 + cut 输入编译 | ✅ 交付（剪辑交接 374L+4路由+任务区） |
| S2-E | AGENT_PROTOCOL.md + 回写校验 + 跨 agent E2E | ✅ 交付（协议卡+shoot_validate 484L；跨 agent 回写 E2E 走外部 agent 实测） |

**集成**：全量单测 288 绿；shoot_io 类型守卫补丁；jy_draft/qa_backfill 焊回接线；门面/draft/CLAUDE.md 路由同步；P1a 顺带闭环（VAD 焊回，阈值待真实素材标定）。

文件：[plan.md](plan.md) · [split.md](split.md) · [requirements.md](requirements.md) · [hvr.md](hvr.md) · status.json
