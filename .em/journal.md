
## [2026-11-05] 会话: S1 用户试用反馈四连修复 + R4 复验通过
- 产出: P2 闭环（打开净化/拖拽手柄化/版本快照+diff+回滚/hover 批注卡片），65 单测过，ego R4 全过
- 下一步: 真实一期试用 → AI 直改接缝

## [2026-11-05] 会话: P3 点点点乱序二次修复（拖拽通道整体拆除）
- 产出: 块内禁拖+drop处理器删除+只留↑↓，ego R5 四断言全过；P2 修复不彻底的教训：修「误操作类」bug 要关死整条通道，不是堵单个入口
- 下一步: 用户继续逐字稿_v1.md 审稿轮

## [2026-11-05] 会话: S2 shoot-pipeline 重档 5 阶段讨论完，方案落盘
- 产出: features/S2-shoot-pipeline/{plan,split,requirements}.md+README+status.json；四子系统（呈现批注/素材关联/剪辑编排/agent协议）拆 S2-A~E
- 关键决策: 用户点名不要 workbench（素材关联自立新子技能 shoot）；素材归位混合模式（命名约定优先+AI兜底+人工确认）；quote 锚定复用 S1 回落；单旁车 shoot.json 分节+agent 回写限状态字段；③只做编排不造剪机
- 下一步: S2-A 开发 → /em verify s2

## [2026-11-05] 会话: P4 工具条压字二次返工（竖排装订沟）
- 产出: 竖排 left:100% 锁进沟内+🗑确认，几何断言改在显示态量；教训=E2E 布局断言必须强制显示后量
- 下一步: 用户恢复顺序后继续审稿

## [2026-11-05] 会话: P5 真凶=refreshBlockEl 补位逻辑把下一块甩到文档末尾
- 产出: replaceWith 一行修；R7 按真实用户流全过；盘上数据复核无损；教训=显示层与数据层分开断言、用户流要含失焦重绘
- 下一步: 用户刷新继续审稿（稿子数据无损，刷新即恢复正确顺序）

## [2026-11-05] 会话: S2 shoot-pipeline 开发完成（多 agent 并行）+ P1a 闭环 + E2E 关账
- 产出: 五子流程全交付（draft 呈现批注/定稿锁/清单导出 + shoot 子技能 + AGENT_PROTOCOL.md/shoot_validate）；289 单测绿；ego 全链路 E2E 判定可用（沙箱=用户 20261101_ego 期素材只读复制）；跨 agent 回写实测通过（外部 agent 仅凭协议卡领 t01 card→产卡→白名单回写→自检 0）
- E2E 揪出修复: 面板挂接 match 不升 manual / 呈现批注 id 删后可复用 / 缺拍口径混入 AI 批注；集成修补: shoot_io 类型守卫（E 侧 fuzz 发现）/ emit 覆盖分支漏发校验器 / 校验器 --root 统一项目根锚点
- 顺带闭环: P1a 条目切字（srt_cut VAD 焊回+三处接线，阈值待真实素材标定）；新增 P6（cut/scripts/select.py 遮蔽标准库地雷）
- 教训: 并行 agent 上限 2；任务书要文件域互斥+schema 冻结；「已覆盖」分支也要走资源发射（首写分支独有逻辑是经典漏洞）
- 下一步: 真实一期试用新链路；P1a 阈值标定

## [2026-11-05] 会话: P7 僵尸服务吞保存闭环（Windows 双绑定）+ 用户真实试用首战
- 现象链: 8791 孤儿页签「点添加没反应」→ 8765 双进程监听 → 保存显示成功但历史 0
- 根因: allow_reuse_address=1 在 Windows 允许双绑定同端口，爬位+1 永不触发，旧代码僵尸进程吃掉保存
- 修复: DraftServer/ShootServer 关 reuse（爬位实测 8877→8878）+ 历史空态文案 + tests/test_server_port_climb.py；292 全绿；装位同步
- 下一步: 用户重启 draft 服务后继续逐字稿审稿；从下一次改字保存起历史开始积累

## [2026-11-05] 会话: P8 手动添加素材闭环（用户真实项目试用 shoot 面板）
- 反馈: 素材面板空态只指 CLI——素材不按 R 命名约定时人被流程卡死
- 修复: /api/footage/add（登记+挂接+幂等+根外拒收）+ /api/browse + 面板「＋添加素材」浏览弹层；素材回收降级为批量提效路径；SKILL 同步；294 全绿；装位同步
- 教训: 提效路径和兜底路径都要一等公民——用户素材永远不按你的约定来

## [2026-11-05] 会话: P9 剪辑批注可再编辑 + 任务区工具挂靠（用户真实项目试用）
- 反馈: ✂️批注确定后想再改无入口（黄条是死区）；任务看不出归哪个工具做
- 修复: 黄条点击即编辑（与按钮同入口）+ 任务行 🔧 工具徽标（cards/vibe-motion/aigen/人工）+ 任务区常驻图例（05_剪辑交接→cut→post）；294 绿；装位同步
- 教训: 展示态本身也要是编辑入口，死区=功能不存在

## [2026-11-05] 会话: P10 旧进程 unknown endpoint 闭环（API 版本握手）
- 反馈: 「＋添加素材」弹层报 unknown endpoint——页面新（静态现读盘）进程旧（路由启动时冻结）
- 修复: 服务端 API_VERSION=2 随 /api/project 下发 + 前端 MIN_API_VERSION 比对（旧进程状态栏+toast 明示重启）+ api() 把 unknown endpoint 翻译成人话；294 绿；装位同步
- 教训: 能力握手一开始就要设计——「页面新进程旧」已砸三次（P7/孤儿页签/本案）

## [2026-11-05] 会话: P11 工作区素材池（用户真实项目试用反馈）
- 反馈: 点批注右列被过滤得只剩已挂素材，工作区其余全被藏住——误以为不能重复挂
- 事实: 多对多本就支持（f08 同挂 R01/R08）；坏在 UX 把素材池藏起来了
- 修复: 点批注默认仍显全部素材（已挂所选的高亮描边+chip 加粗），筛选器三档（全部/已挂所选/未挂，带计数）+ 空态指引切回全部；294 绿；装位同步
- 教训: 过滤器不该牺牲全局视野——「看局部」应是主动选择不是默认惩罚

## [2026-11-05] 会话: P12 素材预览（用户真实项目试用反馈）
- 交付: GET /media（Range/206 分块流式，3G 大文件不爆内存，路径限项目根内）+ 面板预览弹层（▶预览/点文件名，video/img 直连，←/→ 或按钮在当前筛选内连续看，Esc 关）；API_VERSION→3；测试 +1 类（200/206/尾切片/416/400/404），295 绿；装位同步+服务换血重启（8790 v3 实测 R04 画面A 79.5MB Range 正常）
- 注: 预览列表口径=当前筛选（配合 P11 工作区池，挑素材连续看）

## [2026-11-06] 会话: 剪映粗拼草稿直出（shoot 链路终点，用户需求）
- 需求: 选用满意后直接做成剪映草稿方便精细剪辑
- 交付: shoot/scripts/剪映草稿.py（build_plan 编排纯函数：批注数值序/跨批注共用只落首条/孤儿追加尾部/缺盘跳过告警；generate 复用 jy_draft 家底[resolve_draft_root/防覆盖盖戳/root_meta 登记Registers/fps 收敛]，懒加载+select 地雷防护）+ /api/jy_draft（API_VERSION→4）+ 面板「🎬生成剪映草稿」按钮；Rxx 2 秒导航标签每段开头；被改过的同名稿自动落 v2 绝不覆盖
- 分工写死: cut/jy_draft=转录剪切稿 AI 粗剪；shoot/剪映草稿=选用素材表人挑粗拼；editNotes 是参考不自动截段
- 测试: +10（编排纯函数/dry-run 零写盘/错误路径/真 mp4 全链路[imageio_ffmpeg 造彩条→临时草稿根→登记断言]）305 绿；装位同步；8790 换血 v4，真实项目 dry-run 编排 7 段正常

## [2026-11-07] 会话: 用户 /em result 报 shoot 链路试用反馈五连（P13 开放）
- 反馈: ①交付全量——Rxx 全部剪辑要求一锅端，只剪部分得在对话里口头强调 ②拍摄任务分 AI 制作/本人拍摄，应支持并行 ③素材回收 AI 自动扫描挂接费时，要求去掉、面板手动挂优先 ④剪辑成果不自动挂回工作台 ⑤缺「工作台→AI 对话→回到工作台」闭环
- 动作: 记录 problem-log P13（开放）；候选升 S3 特性，/em new 澄清后定方案
- 下一步: /em new 开 S3 交付/回收闭环

## [2026-11-07] 会话: S3 cover-skill（封面子技能）方案落盘
- 产出: features/S3-cover-skill/{plan.md,README.md,status.json}；五子步骤 S3-A~E（上游基线/脚本换血/SKILL+路由/单测/验收退役）
- 关键决策: 方案 A 原地改造取上游 GitHub 最新基线（选帧 know-how 保真+LICENSE 保留）；分析双模式同一把 ARK key（agent 默认零成本/api=doubao 视觉回退，跑不动明说不静默）；生图 Seedream+参考帧；ZenMux/credential-ui 整层退役；精简移植+旧 skill 验证后删 ~/.agents/skills/oil-cover；cover 占 S3，P13 立项编 S4
- 下一步: S3-A 开发 → /em verify s3-a

## [2026-11-07] 会话: S4 delivery-loop 澄清定稿+中档落盘，开工（与 S3-cover 并行会话同日）
- 编号: 原拟 S3，让位并行会话的 cover-skill（上方 journal 在案），P13 立项改 S4
- 澄清: 逐个 Rxx 剪是常态全剪是例外；用户否决面板直达渲染（执行者必须是对话 AI）；成果=粗拼小样 mp4 批注上直接预览
- 产出: features/S4-delivery-loop/plan.md；拆 S4-A~E（A schema v2+校验器 / B 粗拼小样核 / C 面板闭环 / D 剧本协议+--only / E 回归装位）
- 关键决策: 桥=shoot.json 新增 cutQueue（面板专属写）/deliverables（agent 只许追加）两节；小样含跨批注共用素材（预览要看全）；素材回收 AI 兜底从剧本删除
- 下一步: S4-A 开发

## [2026-11-07] 会话: S4 delivery-loop 开发完成（当日立项当日交付，356 绿）
- 交付: schema v2（cutQueue/deliverables，读端兼容 v1，双校验器对拍）+ 粗拼小样.py 渲染核（720p 快渲/无音轨补静音/图片展帧/挂回+消化队列/sha 拒写）+ /api/cut_queue（API_VERSION→5）+ 面板闭环（✂️剪这个/待剪栏+复制指令/▶小样预览复用 P12 弹层/任务分组/到位率提示）+ SKILL 去 AI 兜底+剪待剪剧本+挂成果规则 + AGENT_PROTOCOL v2（deliverables 追加白名单/cutQueue 只读）+ 剪映草稿 --only
- 真项目 dry-run 揪出潜伏 bug: 剪映草稿 generate 不传 state 时 find_sidecar 元组未解包（服务端恒传 state 掩盖）；+51 测试全过；装位同步
- 编号事故: 立项时与并行会话（S3-cover-skill）撞号，让位改 S4——journal 先说话再动盘的教训
- 下一步: 用户面板点「✂️剪这个」+ 对话跑 --queue 真渲一个小样验收；8790 旧进程（v4）需重启换血 v5

## [2026-11-07] 会话: S3 cover-skill 开发交付（A~E 全子步骤，与 S4 同日双交付）
- 交付: skill/media/cover/（SKILL.md agent SOP+api 回退+红线；generate_cover.py Ark 化——双模式分析/--prompt-file/--prescan/候选链降级/错误人话/`.cover` 工作目录；上游 tarball 最新基线含 gemini-3.8 时代 prompt 演进+references 更新）+ media 门面路由（cover 行+触发词）+ tests/test_cover_skill.py 20 测，全仓 376 绿；装位同步 diff 一致
- E2E（真实一期 R04_分屏并行_v2）: prescan 8 帧零 API → agent 读 cover-rules 挑 candidate_02 写 prompt → Seedream 5-0-flash-260915 三画幅直出 → 3x4/4x3 返工一次（CSS 数值被 Seedream 当文字渲染，旧图成套归档 v1-css-leak/）→ 全验收；产物 %TEMP%\cover_e2e
- E2E 揪出三坑并闭环: ①Seedream 数值串泄漏——prompt/backfill 全面去 CSS 值 ②本机无 ffprobe——ffmpeg stderr Duration 行兜底 ③ffmpeg 不在 PATH——imageio_ffmpeg 二进制回落；旧 ~/.agents/skills/oil-cover 保留不删（用户改判：留着不影响）
- 教训: 上游 prompt 骨架是给 gpt-image 系调的，换生图模型必须真渲验收再定稿；移植技能的第一性是"切成宿主能跑的"，本机依赖探测要进门就做
- 下一步: 用户看 E2E 封面验收；真实项目直接 /media cover
