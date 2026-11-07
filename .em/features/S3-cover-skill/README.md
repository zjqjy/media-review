# S3-cover-skill — media 封面子技能（oil-cover 移植+火山 API 化）

> 状态卡：feature 目录的入口，`/em pi` 与 `/em stat -v` 扫描本行

| 字段 | 值 |
|------|-----|
| 状态 | ✅ 完成（2026-11-07） |
| 档位 | 中 |
| 日期 | 2026-11-07 |
| HVR | `hvr.md`（verify 后存在） |

## 一句话目标
/media 第 10 个子技能 cover：视频封面三画幅直出——选帧脚本零 API，分析默认 agent 本体（可切 api 全自动），生图走火山 Seedream，ZenMux 凭据层退役。

## 关键决策（≤3 条）
- [2026-11-07] 方案 A 原地改造：基线取上游 GitHub 最新（非本地装位），选帧 know-how 保真移植，LICENSE/NOTICE 保留
- [2026-11-07] 分析双模式同一把 ARK key：agent 本体（默认零成本）/ Ark doubao 视觉全自动（无多模态宿主回退），跑不动明说不静默
- [2026-11-07] 精简移植：references/assets 精选，ZenMux/credential-ui/docs/tests 不搬；旧 ~/.agents/skills/oil-cover **保留不删**（用户改判：不影响，留作参照）

## 产物清单
- `plan.md` — 方案 + 拆分
- `hvr.md` — 验证请求与结果（verify 后存在）
- `skill/media/cover/` — SKILL.md（agent SOP/api 回退/红线）+ scripts/generate_cover.py（Ark 化 1964 行）+ references 4 篇（上游最新）+ assets product-logos png + LICENSE/NOTICE
- `tests/test_cover_skill.py` — 20 测（key/错码人话/候选链降级/agent prompt 解析/标题锁/守卫回填/假 Ark 生图/prescan 真链路/agent 守门/--help），全仓 376 绿
- E2E：真实一期 R04_分屏并行_v2.mp4 → prescan 8 帧 → agent 挑 candidate_02 写 prompt → Seedream 5-0-flash 三画幅 → 3x4/4x3 各返工一次（CSS 数值泄漏）→ 全验收；产物在 `%TEMP%\cover_e2e\`
