# HVR — S2 shoot-pipeline（定稿后拍摄计划链路）

> 2026-11-05 · 多 agent 并行开发（A/C/E → B/D 两波，并发上限 2）+ 集成收尾

## 需求（回指）

定稿 md 之后搭「呈现批注 → 拍摄 → 素材关联 → 剪辑批注 → AI 执行」流水线，人只做批注决策与拍摄；全链路产物跨 agent（zcode/claude code/codex）可消费。方案与拆分见 [plan.md](plan.md) / [split.md](split.md) / [requirements.md](requirements.md)。

## 验证（实际做了什么）

| 关卡 | 结果 |
|---|---|
| 全量单测 | **289 全绿**（基线 65 → 五子流程 +89、P1a +29、E2E 修复 +6 等；`python -m unittest discover tests`） |
| ego 浏览器全链路 E2E | **链路判定：可用**（独立验收 agent 真实浏览器驱动，沙箱项目=用户 20261101_ego 期素材只读复制）：呈现批注整块+圈句 → R 编号 → 🔒定稿锁（403/刷新持久）→ 清单导出 → 文件名匹配回收+unmatched → 面板候选/选用 → 缺拍 → 补制任务 → ✂️剪辑批注 → 05_剪辑交接编译 → shoot_validate 通过；定稿 md sha256 逐字节未变，旁车互不干扰 |
| 跨 agent 回写 E2E | **通过**：外部 agent 仅凭项目内 AGENT_PROTOCOL.md（零代码库上下文）领 t01 card 任务、正确跳过 reshoot、只改白名单两字段（state/output）、自检双模式退出码 0；协议质量反馈 3 条已消化（项目根锚点统一 +`--root`、快照豁免注明、目录对照表） |
| 集成修补 | E 侧 fuzz 揪出 shoot_io 非字符串 footage_id TypeError → 类型守卫；emit_protocol「已覆盖」分支漏发校验器 → 三路径统一发射；校验器+协议卡加 `--root`（项目根锚点=素材目录层，与 footage.file 同基准） |

## 结果

- 交付：draft 呈现批注/定稿锁/清单导出 + shoot 子技能（匹配器/面板/缺拍/补制任务/剪辑交接）+ AGENT_PROTOCOL.md 协议卡 + shoot_validate 回写校验（白名单：tasks[].state/output、footage[].state/note）
- E2E 揪出并修复 3 处：①面板挂接 match 不升 manual（白名单+前端补 match:"manual"，伪造机器来源拒收）②呈现批注 id 删除后可复用（nextAnnId 烧录池扩到 footage.ann_ids∪tasks.ref）③缺拍口径混入 AI 批注（missing_anns 收敛为人工拍摄口径）
- 顺带闭环 P1a（srt_cut VAD 焊回 + jy_draft/qa_backfill 接线）与 shoot_io 类型守卫；新增 P6（select.py 地雷）入 problem-log
- 门面/draft SKILL/CLAUDE.md 路由同步；装位已 cp 同步（sha256 抽检一致）

## 遗留（不挡关账）

1. **P1a 阈值待真实素材标定**：WELD_GAP=2.0 / VAD_BRIDGE_TOL=0.2 是启发式初值，需 R02 素材+剪切稿 srt 跑 `--weld-gap 2.0` vs `0` 对比听 1711s 附近（problem-log P1a 案卷）
2. B 导出的 AI 任务 md「产物建议路径」基准=md 同目录，与协议卡「output 相对项目根」并存双基准——真实一期试用时观察是否困扰，必要时统一
3. workbench 仍挂在门面路由（用户排除的是本链路，未要求下架）
