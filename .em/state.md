# state.md — 项目当前状态（rec 默认只读这个）

> ⚡ ≤50 行单一恢复源；详细历史按需查 features/、decisions.md、problem-log.md

## Meta
- **项目**: media-review（自媒体 skill /media 门面：cut/post/review/benchmark/cards/aigen/workbench/draft/shoot）
- **类型**: general
- **当前步骤**: S6-publish 🔄（A~D 交付：骨架+dry-run 三平台全通+471 绿+装位同步；E 真发待用户在场）∥ S5 ✅ ∥ S4 ✅ ∥ S3-cover ✅
- **更新时间**: 2026-11-08
- **会话**: sess-20261105-001

## 下一步动作
1. S6-E 首次真实发布（用户在场）：给一期成片+cover 三画幅 → 确认单（声明默认 AI 生成）→ 你说「发」→ 三平台真发 → 发布记录落 `<成片>.publish.json` → /em verify s6
2. S5 验收（真实流线）：批注三区视图（点 R01）→ 素材区提要求 ✂️剪这个 → 暂存区验收 ✓认可 → 口播段素材卡「✓进成果区」→ 九条齐 🎬生成剪映草稿 → 剪映删掉不好的 → 📖读回草稿拼回暂存 → 再加工再认可
3. 旧数据迁移：现有项目 deliverables（4 条小样/成品段）缺 zone=暂存——面板批注里逐条认可即可，无需脚本
4. S3 验收：E2E 封面 `%TEMP%\cover_e2e`；P1a 阈值标定（R02 跑 `--weld-gap 2.0` vs 0 对比）
5. 功能候选：读回报告面板化（外来素材逐条点名）/ 加工单模板库 / AI 直改接缝

## 最近 3 条关键决策
- [2026-11-08] S6 实锤三件：①ego 权限弹窗（定位/通知）= Preferences 手术可根治但**必须强杀全部 ego 进程再重启**（优雅关不净=老进程带旧配置还活着）②创作声明下拉只认真人事件序列，自动化点不开就 handOff 人工选（B站措辞=含AI生成内容/抖音=内容由AI生成，用户口径声明默认 AI）③话题必须联想点选成芯片（xhs anchor/douyin 联想行），留 #文字 不算挂
- [2026-11-07] S6-publish 定音：方案A agent 直驾 ego-browser+SOP 教材化（social-auto-upload 等调研项目只抄知识不抄运行时，避 CSS 选择器腐烂死穴）；验证=dry-run 停「发布」按钮前截图（用户仅一期真视频）；ego 主号 profile 与 benchmark B站小号隔离
- [2026-11-07] S5 三区定音（R0 四问）：选 R 后三组（素材/暂存/成果）；认可可退回（草稿前都留活口）；读回=掐段重组拼回暂存；草稿纯成果区（没认可的 R 缺槽列出）。识别点=源文件路径（隐形删不掉，Rxx 标签降级纯导航）；zone 是面板专属写，agent 追加禁带（自认 approved 拒收）；同 ann 单槽位，认可自动退旧；S2 选用素材粗拼语义退役，拼装核不建（草稿即整期载体）
- [2026-11-07] S5 技术实锤：ffmpeg 抽段 `-t` 必须放**输出侧**（输入侧 -t 对 seek 后抽段不生效，产物=全长，真渲断言抓的）；读回 mount 复用粗拼小样家底（sha 拦截+consume=False）；API_VERSION→8（MIN 同步抬，旧页面三区功能不可用即重启）
- [2026-11-07] S3 cover 交付定音：基线取上游 tarball 最新；分析双模式同一把 ARK key；Seedream 候选链首开即用；Seedream 数值串泄漏坑（prompt 禁 CSS 值）；旧 oil-cover 保留不删（用户改判）

## 阻塞项 / 待办
- [ ] P1a 条目边界切字（未修，见 problem-log.md）
- [ ] 8790 长驻服务是 v7 旧进程——重启换 v8 血（页面会自己提示）

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
| S5 三区+读回 计划 | `features/S5-three-zone-workbench/plan.md` |
