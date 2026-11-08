# state.md — 项目当前状态（rec 默认只读这个）

> ⚡ ≤50 行单一恢复源；详细历史按需查 features/、decisions.md、problem-log.md

## Meta
- **项目**: media-review（自媒体 skill /media 门面：cut/post/review/benchmark/cards/aigen/workbench/draft/shoot）
- **类型**: general
- **当前步骤**: S9-talkcraft-test ✅（真素材 73s 录音全链通：预剪 −23.5s+字级时间戳+49.8s 成片 talks3.mp4，待用户看片+商用许可拍板）∥ S8-shotcraft-test ✅（两级实测全过+剪映 Win 实锤+报告落盘，待看片验收）∥ S7-blog-gzh 🔄（A~D 交付：blog 子技能+19/492 绿+真一期 dry-run 全通+站点 220 e2e 绿+commit d637213+装位同步；公众号驱动器正文自动全通、插图人工兜底、群发未碰；E 终审待用户）∥ S6-publish 🔄（A~D 交付：骨架+dry-run 三平台全通+471 绿+装位同步；E 真发待用户在场）∥ S5 ✅ ∥ S4 ✅ ∥ S3-cover ✅
- **更新时间**: 2026-11-08
- **会话**: sess-20261105-001

## 下一步动作
1. S7 收尾（用户）：草稿箱打开 `blog-gzh-231904`（正文全带 ⟦图N⟧ 标记）→ 按 `gzh_pack/images.json` 清单逐个删标记传 5 图 → 存草稿；批删校准期 7+ 个测试草稿；三处终审（①选帧预览 `blog_preview/esp32-lcd-ai-driver.html` ②文章 preview ③公众号草稿）→ /em verify s7
2. S6-E 首次真实发布（用户在场）：给一期成片+cover 三画幅 → 确认单（声明默认 AI 生成）→ 你说「发」→ 三平台真发 → 发布记录落 `<成片>.publish.json` → /em verify s6
3. S5 验收（真实流线）：批注三区视图（点 R01）→ 素材区提要求 ✂️剪这个 → 暂存区验收 ✓认可 → 口播段素材卡「✓进成果区」→ 九条齐 🎬生成剪映草稿 → 剪映删掉不好的 → 📖读回草稿拼回暂存 → 再加工再认可
4. 旧数据迁移：现有项目 deliverables（4 条小样/成品段）缺 zone=暂存——面板批注里逐条认可即可，无需脚本
5. S3 验收：E2E 封面 `%TEMP%\cover_e2e`；P1a 阈值标定（R02 跑 `--weld-gap 2.0` vs 0 对比）
6. 功能候选：读回报告面板化（外来素材逐条点名）/ 加工单模板库 / AI 直改接缝
7. S8+S9 验收（用户）：看 `video-shotcraft-test\r06-motion\out\r06.mp4`（15s）和 `talk-s3\remotion\out\talks3.mp4`（49.8s 真人口播+字级同步字幕）→ 认可后 /em verify s8、s9；**商用拍板**：talkcraft 是 PolyForm Noncommercial，频道有变现需先邮件作者授权 → 过了就 S10 立项 motion 子技能（talkcraft 内核+透明通道接 shoot 暂存区）

## 最近 3 条关键决策
- [2026-11-08] S7-D 驱动器实锤：①ego 窗口标题=空间名→win_window.ps1 v2 按标题作用域（WM_CLOSE 温和关残留），杀进程移出流程（并行会话保护）②CDP setWinBounds 还原/最小化己窗；强杀留崩溃弹窗③mp 编辑器=顶层 ProseMirror：正文注入必须 keyboard.paste({text,html}) 原生粘贴（合成事件只进 8 字=palceholder widget 字数，真 body 按 contenteditable!=false 过滤）④登录判据=URL token+「新的创作」（首页含「扫码登录」字样=文本判据假阴性）⑤插图 setInputFiles 落图+CDN 自动上传但撕占位符+每图双份→人工兜底（SKIP_IMAGES=true 出占位符草稿）
- [2026-11-08] S9 实测定音：talkcraft 真素材全链通（预剪 17 段 −23.5s 报告细到对出 v1.5 改稿痕迹；whisper 后端 match 0.84–0.97，生产换 FireRed）；字级同步实锤；5 新 Win 坑全解（av shim/junction/ffmpeg shim/稿音匹配）；**许可红线 PolyForm Noncommercial 挂用户拍板**，过了即 S10 建 motion 子技能（透明通道接 shoot 暂存区）
- [2026-11-08] S8 实测定音：两级测试全过（模板 36s 渲染画质优+剪映导出 Win 实锤三查过，官方 win untested 风险剪掉）；坑#4 Remotion 浏览器下载器不走代理（16KB/s）→ 代理 curl+place_headless.py 根治（新项目通吃）；方向性发现=口播正解是姊妹项目 video-talkcraft（节拍钉人声），shotcraft 卡库+aesthetic-rules 作共享资产，集成形态「只抽资产不改内核」留 S9
- [2026-11-08] S7 交付实锤：①ego stdin vm 对非 async 箭头里的 await 直接 SyntaxError 无行号 ②站点数量契约：新文章顶红 pages.spec 工程笔记 6→7（发文=改契约，跟进修 spec）；About 批红=并行负载抖动（单跑 9/9 有案）③站点 preview 页绝不进 source/（Hexo 原样发布）④ai_score --json 依赖 article_meta，vendor 闭包要收全
- [2026-11-08] S7-blog-gzh 定音：方案 B 开源拼装优先（调研先行能引则引缺件自研）；文风红线=外部引擎只定初稿，与 STYLE.md 冲突即 fallback STYLE.md+humanize 终检；公众号开源只进排版层、后台操作层 ego 自研（复用 S6「只抄知识不抄运行时」）；边界=不 deploy（备案期）不群发（人工点）
- [2026-11-08] S6 实锤三件：①ego 权限弹窗（定位/通知）= Preferences 手术可根治但**必须强杀全部 ego 进程再重启**（优雅关不净=老进程带旧配置还活着）②创作声明下拉只认真人事件序列，自动化点不开就 handOff 人工选（B站措辞=含AI生成内容/抖音=内容由AI生成，用户口径声明默认 AI）③话题必须联想点选成芯片（xhs anchor/douyin 联想行），留 #文字 不算挂
- [2026-11-07] S6-publish 定音：方案A agent 直驾 ego-browser+SOP 教材化（social-auto-upload 等调研项目只抄知识不抄运行时，避 CSS 选择器腐烂死穴）；验证=dry-run 停「发布」按钮前截图（用户仅一期真视频）；ego 主号 profile 与 benchmark B站小号隔离
- [2026-11-07] S5 三区定音（R0 四问）：选 R 后三组（素材/暂存/成果）；认可可退回（草稿前都留活口）；读回=掐段重组拼回暂存；草稿纯成果区（没认可的 R 缺槽列出）。识别点=源文件路径（隐形删不掉，Rxx 标签降级纯导航）；zone 是面板专属写，agent 追加禁带（自认 approved 拒收）；同 ann 单槽位，认可自动退旧；S2 选用素材粗拼语义退役，拼装核不建（草稿即整期载体）
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
| S7 blog-gzh 计划 | `features/S7-blog-gzh/plan.md` |
| S8 shotcraft-test 计划 | `features/S8-video-shotcraft-test/plan.md` |
