
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

## [2026-11-07] 会话: 用户 /em result 判 S4 失败 → 工作台 R0 重定义（P14+P15）
- 判定: S4 管道闭环跑通（排队→对话→挂回→预览），但执行语义错位——「剪这个」产出=选用素材硬拼预览，用户要的是真剪（P14）；更深一层：工作台定位错位，该是「人机交替制作枢纽」不是素材面板+执行按钮（P15）
- 用户给的流程模型: 素材三类型（口播声音/无声画面/录屏含口播）×不同流线（口播先 cut 粗剪→剪映人工精简→人工导入工作台→AI 按要求组合剪辑→挂回；录屏线→AI 画面优化→挂回）；AI+人交替，交互全靠工作台；素材可组合剪辑、会越积越乱要整理
- 决定: S4 转返工，进 R0 澄清（一次一问）；cutQueue/deliverables 桥+挂回协议+预览弹层保留复用
- 下一步: R0 第一问——口播是不是成片主轴（画面配口播 vs 平等组合）

## [2026-11-07] 会话: S4 返工 R0 六问定音，工作台 2.0 plan v2 落盘
- 六问结论（decisions.md D3）: ①口播主轴 ②逐条 Rxx 主轴段 ③AI 产出成品段 mp4 干到能用 ④人出主轴 AI 只加工+cut 工具挂载进面板 ⑤AI 加工=视觉强化+插卡标注+段标准件（不碰删废节奏）⑥工具挂靠扩展到剪辑线（粗剪→cut/强化合成→加工核/插卡标准件→cards）
- 关键设计: 加工单（AI 出 JSON 决策）→加工核（确定性渲染）——判断在对话执行在脚本，可复跑可改单重渲；shoot.json v3 增 footage mtype/stage/role 纯增量
- 落盘: features/S4-delivery-loop/plan.md v2（W1 schema → W2 面板组织∥W3 cut 挂载 → W4 加工单+加工核 → W5 剧本协议 → W6 回归试用）
- 下一步: W1 开工

## [2026-11-07] 会话: S4 工作台 2.0 开发完成（W1~W6 当日交付，400 绿）
- 交付: schema v3（footage 三维 mtype/stage/role+deliverables kind=segment，读端兼容 1/2/3 双校验器对拍）+ 面板组织（类型/阶段徽标点改[猜虚线/标实线]、类型×阶段筛选 chips、成果区横排、剪这个=AI 加工语义、🔧剪辑线工具挂靠图例、🎥粗剪指令生成）+ 加工核 剪辑加工.py（加工单 JSON 契约：spine/visual 铺画面/effects zoom+speed/cards 插卡/standard 标准件；判断在对话执行在脚本，分阶段 ffmpeg 管线可复跑；drawtext 盘符冒号转义坑；挂回 kind=segment+消化队列）+ shoot SKILL 重写三剧本（A 回收/B 加工/C 粗剪挂载）+ AGENT_PROTOCOL v3 增补 + media 门面路由
- 踩坑: filtergraph 路径盘符冒号必须转义（C\:/）否则 drawtext 引号配对全乱；apply_standard 漏传 ws；mount kind/note 参数化（粗拼小样与加工核共用）
- 收尾: 400 绿×2、装位同步 14 文件、8790 换血 v6（probe guessed 真项目验证：04_成片→screen/final/spine ✓）、加工单真项目 dry-run 通过；用户已挪动素材（R04_画面A 缺失正确标 ⚠，新 R04_口播.m4a 印证流线 A）
- 下一步: 用户走真实流线验收（粗剪→精简导入→剪这个加工→成果区验收）

## [2026-11-07] 会话: 剪辑批注附图（工作台 2.0 追加，用户点名）
- 需求: 剪辑要求配截图——「这里还是有品牌标」这种问题，文字说不清位置，贴图 AI 才看得懂
- 交付: schema editNotes[].imgs（可选字符串数组，双校验器+附图实况警告）+ /api/note_img（base64 上传存 07_批注图/，png/jpg/webp ≤10MB，API_VERSION→7）+ 面板（批注输入框截图 Ctrl+V 直贴/📎选文件/缩略图✕立即移除/点图看大图，只刷单卡不打断输入）+ SKILL 剧本 B「先逐张看图再出加工单」（错位→zoom 避开/瑕疵→卡遮盖/多余→speed 跳过）
- 踩坑: urllib 对 /media 图片字节流 json.loads 炸（测试按原始字节验 PNG magic）
- 追加（同日用户点名「从剪贴板贴图」）: 全局兜底粘贴（批注编辑开着，焦点在哪都贴得上；没开给指路 toast）+ 预览播放器「📸截此帧」（canvas 抓当前帧→PNG→立即落盘为该素材批注附图，视频专用、成果/附图预览不显示）——uploadNoteImg 加 autosave 参数（贴字流不自动存、截帧即存）
- 收尾: 408 绿、装位同步、8790 换血 v7
- 下一步: 用户流线验收（现在可以截图框问题贴进批注）

## [2026-11-07] 会话: R01 真实加工第一单（剪指令闭环首战）+ 附图丢失修复 + crop/delogo 刀法
- 用户贴剪指令（R01 在队）→ 剧本 B 全流程：读旁车→抽帧定位→出加工单→dry-run→真渲→挂回 d03（kind=segment）→抽帧验货
- 加工核新增两把刀（用户真实需求驱动）：crop（裁品牌壳：浏览器标签栏/地址栏 110px + 任务栏 82px）+ delogo（区域去标：bili-review Agent 悬浮标 x700 y1000 w530 h140，时间窗 0~19.5s，抽 2/6/10/14/17/19/20s 帧实测定位；悬浮标会小幅移动，框盖活动区）；base/final 改 scale=-2:720 等比（裁壳后宽高比自己说了算，不再 cover 裁切变形）
- 修附图丢失 bug：只贴图不改文字时 change 条件判「文字没变」跳过保存→附图没落盘；修为文字或附图有变都存；用户丢的图从 07_批注图/ 孤儿文件挂回 f47
- 踩坑: ①终端 curl 发中文变 GBK 砸服务端 UTF-8 解析（HTTP 400）——改 python urllib 发 ②后台任务养的服务会静默死——PowerShell Start-Process 分离启动是本机正解 ③测试星号解包进 / 运算符是语法错
- 收尾: 410 绿（含 crop/delogo 校验+渲染测试）；装位同步；剪指令文案修正（--queue 从未实现，剧本本就是逐条 --ann/--plan）
- 下一步: 用户面板成果区 ▶看 R01 成品段验收；R02 起逐条复制工单

## [2026-11-07] 会话: R01 返工 v2——用户三条反馈修正（改单重渲闭环首秀）
- 反馈: ①章节卡「① 冷开场」是我自作主张塞的——用户没要，去掉 ②「B站没完全去掉」——品牌标指的是页面上的 bilibili 大 logo，不只是 Agent 悬浮标 ③成品要更改怎么办→答：改加工单重渲，同名覆盖+deliverables 追加，面板永远最新
- 返工: 抽 4/5/8/9/10s 左上区域帧定位 logo（原生 x125 y205 175×95，首页场景 4~7.5s 在屏，8s 随页面滚动消失）→ 加工单 v2 去卡+logo delogo 4~7.5s → 重渲 d04（d03 成历史）→ 5s 帧验货 logo 已抹平
- 教训: 加工单铁律「只写用户点名的项」这次自己破了——AI 好心加的导航卡在用户眼里是脏东西；skill 里的规矩要用到自己头上才长记性
- 下一步: 用户验收 v2；若要「整段无 B 站元素」需另议（页面内容是演示主体，delogo 撒不动）

## [2026-11-07] 会话: 服务静默死之谜破案 + 双面板 pythonw 重启
- 谜底（用户点破）: v5/v6/v7 服务「静默死」= 用户电脑关机了，不是进程玄学
- 处置: 8790 剪辑工作台 + 8765 draft 双面板改 pythonw（无控制台进程）重启，双 HTTP 200；draft 曾误起（用户要的是剪辑工作台不是审稿台）
- 遗留: 关机后服务不自启——如需开机自启（计划任务/启动项一键脚本）用户点名再做
- 下一步: 用户继续 R02 起的逐条加工

## [2026-11-07] 会话: S5 三区工作台+草稿读回交付（R0 四问 → 一口气全链路）
- 起点（用户验收 S4 实景暴露）: 成果区只有 ▶看 没有采纳；🎬剪映草稿只吃选用素材表对成品段无感；成果按批注折叠历史被顶掉（4 条只显 1 卡）
- R0 定音: 选 R 后三组（素材/暂存/成果）｜认可可退回｜读回=掐段重组「拼回到一起按RX，识别点不要让我删除了」｜草稿纯成果区
- 交付: schema v4（deliverables[].zone staged/approved，双校验器对拍，agent 追加禁带 zone）；面板三区视图+认可/退回/✓进成果区+成果条只显认可+📖读回草稿；build_plan 纯成果区换血（S2 粗拼语义退役）；读回草稿.py（parse_draft/map 三级映射/plan/真渲 mount，识别点=源路径，Rxx 标签降级纯导航）；服务端 3 路由 API_VERSION→8
- 技术实锤: ffmpeg 抽段 -t 放输出侧（输入侧不生效产物=全长）；读回 mount 的 md 路径必须真解（Path('')='.'读盘炸）；probe 失败判未动防版本噪音
- 测试: +30（test_three_zone.py 21 含真渲读回 E2E + schema v4 对拍/口径翻新）全仓 435 绿×4 连跑（Windows 临时目录清理竞态→清理重试加固）
- 状态: 装位同步待做；8790 是 v7 旧进程待重启换血

## [2026-11-07] 会话: S6 publish 子技能立项（R0 四问 → 方案A 定音）
- R0 定音: 发前一次确认标题简介（agent 按各平台字数出三份草稿，可逐平台改）｜ego 持久 profile 登录态（失效人工扫码，主号与 benchmark B站小号隔离）｜素材=对话附件+指定路径都收不猜文件（视频=剪映导出整片，封面=cover 三画幅按平台选）｜验证=dry-run 停「发布」按钮前截图（用户仅一期真视频，不烧测试内容，首跑真发在场盯）
- 默认口径: 确认单含 B站分区+标签/话题；三平台顺序发+随机间隔不同时发；不做数据回收/定时排期/多账号矩阵；人机验证 handOff 交人（模拟人类≠反风控攻击）；素材不加工
- 调研: social-auto-upload 13.7k★（Playwright 模拟人工，抖音/小红书/B站/快手/视频号全覆盖）+ auto-publish（Chrome 扩展填表+人工确认，同理念）+ omnipost——共同死穴 CSS 选择器腐烂（页面改版即坏等上游修），只抄知识不抄运行时
- 定音: 方案A agent 直驾 ego-browser + SOP 教材化（现场 snapshot 认路抗改版；setInputFiles 传视频/handOff 扫码/screenshot 存证）；方案B/C 因 cookie 两套皮+黑盒直发否决
- 拆分: S6-A 知识提取+platforms.json → S6-B 子技能骨架（SKILL.md+确认单脚本+门面路由+单测）→ S6-C 小红书 dry-run（试点）→ S6-D B站+抖音 dry-run → S6-E 首次真发 E2E
- 竞态提醒: 落盘时撞 S5 会话同刻更新 state.md/总表（编辑报 modified since read），重读后合入未覆盖——多会话纪律第三次生效

## [2026-11-07] 会话续: S5-H 看板版三区定音（用户挑方案 H）+ 暂存卡提要求
- 布局三轮定音: v1 三组竖排被否 → mockup 三方案（A横带/B下双栏/C轨道）全不满意 → v2 按流转规则画 D时间线/F横带改良/H看板 → 用户拍板 H（三竖列瘦行卡列内滚动）
- 流转规则立住（用户确认口径）: 素材区─✂️▶暂存区(版本堆)─✓认可─▶成果区(一R一定稿)─🎬▶剪映；回程 ↩退回 + 📖读回
- 新能力: 暂存卡 ✂️提要求（deliverables[].req 可选字段+存时自动排 cutQueue，剪指令自动带上逐条 req）；三区增删（素材区＋挂素材/✕移出本R；暂存/成果＋登记成果 kind=asset zone 可指定/✕移除删登记不删盘）
- schema: v4 增 req 可选字符串；agent 追加 zone/req 都拒（用户验收权+用户指令权）；API_VERSION→9
- 测试 450 绿（+15：req/remove/register 纯函数+路由+校验器对拍）；装位同步+8790 v9 换血实测

## [2026-11-07] 会话续2: 读回真项目 E2E 打通——剪映6+加密草稿解密落地
- 用户真实点击读回炸出三层真问题，逐一实锤修复：
  1) 剪映 6+/11.x 把 draft_content.json 存成密文——移植 aoguai/pyJianYingDraft 的 videoeditor.dll ctypes 解密（隔离子进程防 ABI 崩服务）；DLL 定位 JY_INSTALL_DIR > config.env > 本机安装位；实锤 11.7.0 的 DLL 空输出、11.4.2 稳定→成功者置顶保留全部候选轮换
  2) 剪映零值键省略：target.start=0（首段）没 start 键被当坏段吞掉（R01 凭空被删）；source.start=0 误取时间轴位置串成链越过源末尾（R04-R09 抽段空流）——缺省一律 0
  3) 自动找稿误选：post 成片稿/旧稿都比宽口径命中——收窄为本管线命名约定 <项目名>_粗拼*（兜底=引用认可成果的稿）
- 真实读回结果：v5 草稿解密成功，R01（保留18.5s）/R03（保留73s）重拼挂暂存，R04-R09 未动不制造版本；重复 d09 人工清理
- 测试 +21 至 471 绿（零值省略回归/密文无DLL人话/H版API/req字段等）

## [2026-11-08] 会话: S6 publish 子技能 A~D 交付（三平台 dry-run 全通，E 真发待用户）
- 交付: platforms.json 常量表（入口/字数/声明选项/坑位，实测校准 verified 打标）+ 调研笔记 + SKILL.md agent SOP（收料→草拟→确认单→dry-run 停按钮→真发四步）+ publish_plan.py（字数校验/确认单/发布记录纯函数）+ 门面路由 /media publish；19 单测全仓 471 绿；装位 diff 一致
- dry-run 实通（测试片，全停「发布」前）: 小红书（登录扫码 handOff→上传→标题/正文→话题芯片 #软件测试）+ B站（上传→标题/简介/分区科技数码/标签/创作声明=含AI生成内容）+ 抖音（上传→标题/简介→话题芯片 #测试→自主声明=内容由AI生成）
- 字数实锤（计数器）: xhs 简介 1000、bili 标题 80·简介 2000、douyin 标题 30·简介 1000；xhs 标题 20 待标定
- 用户口径: 创作声明一般选「AI 生成」（已写 declare_default + 项目记忆）；确认单新增 topics/original/declare/collection 四字段（话题芯片/原创声明/内容类型声明/合集）
- 权限根治: ego Preferences 手术（geo+notifications 四域 block）——坑①优雅 taskkill 杀不干净，老进程带旧配置活着，必须 /F 强杀全家再重启②B站通知弹窗来自 www.bilibili.com 非 member 域③声明下拉只认真人事件，handOff 人工选是正解
- 其他坑: xhs 正文编辑区被 <xhs-publish-btn> 浮层拦 pointer→focus()+keyboard 绕；fill 撞内嵌滚动区→scrollIntoView；ego 强杀丢 space 日志（按名字重建）；字符串 evaluate 是表达式不是函数
- 待办: S6-E 首次真发（用户给成片+封面，确认单→真发→发布记录）→ /em verify s6 收尾；ego lite 有新版 0.6.2.8→升级待用户点头

## [2026-11-08] 会话: S7-blog-gzh 立项（R0 五问 → R1 选 B → R2 五步拆分 → R3 落盘）
- R0 实锤：博客现状=一次性手搓 AI 对话（输入 srt+个人网站知识库）；样例 ego-browser-tutorial 文风 OK（STYLE.md 产物）但正文零配图（7 个 img 全是站点挂件）；/em ask 命中维护手册卡（embedai.top=Hexo 8+Butterfly，发文五步，备案关站期只写不发）+反哺记录（STYLE.md+humanize 文风体系已有，images/<slug>/ 惯例）
- 定音：方案 B 开源拼装优先（调研先行能引则引缺件自研）；选帧 AI 全自动人兜底；公众号止步存草稿群发人工点；文风调研升专门子步骤
- 拆分：S7-A 三线调研评估卡 → B 博客图文管线（文风红线：外部引擎与 STYLE.md 冲突即 fallback）→ C 站点验收+装位同步 → D 公众号排版+ego 草稿驱动器（开源只进排版层）→ E 真一期 E2E
- 边界：不 hexo deploy（备案期）、不公众号群发（人工点）、文风不重造轮子（STYLE.md+humanize 是终检底盘）

## [2026-11-08] 会话: S8-video-shotcraft-test 立项（R0 两问 → R1 选 C 两段式 → R2 四步 → R3 落盘）
- 调研: video-shotcraft 17.7k★ Remotion 代码动画（124 镜头卡/剪映导出/Motion Workbench），非生成模型每帧代码绘制；win untested（剪映导出）是最大风险；姊妹 talkcraft 顺带一眼不深评
- R0: D 先不定集成（实测出结论、集成留下一步立项）+ C 两级测试（demo 冒烟+真素材）
- R1: A 纯手动/B 技能化先行/C 两段式（手动冒烟清环境坑+技能化验集成体感）✅；退化预案=SKILL.md 在 zcode 跑不通即降手动并记录差距（本身就是报告证据）
- R2: A 克隆摸底(S)→B Demo 冒烟(M)→C 真素材技能化(M-L，ego R06 文案)→D 报告+集成建议(S)
- 边界: 不装全局不进 media/不接 shoot/产物只落测试目录/Upload-Post 不测；S7 号被占顺延改 S8（分配前重读总表纪律）

## [2026-11-08] 会话: S7-blog-gzh A~C 交付 + D 构建（dry-run 待扫码，E 待终审）
- S7-A 调研：三线结论用户全认可（①文风引擎全实验级弃引+ai_score.py 加签 ②引入 jiji262 html_converter+15 主题 MIT ③公众号 API 线死路实锤（草稿箱 API 需认证，个人主体无法认证）→ego 自研）评估卡 research-S7-A.md
- S7-B/C 交付：blog 子技能（SKILL.md+5 脚本+vendor 11py/15 主题）+ tests/test_blog_pipeline.py 19 绿（全仓 492 绿）+ 真一期 dry-run：第5期点亮屏幕 → plan 旁车+5 帧实抽实核（逐帧 Read 肉眼验）+文章 esp32-lcd-ai-driver.md（ai_score 15.6/45 PASS）→ 站点 build+e2e 220 绿 → 定点 commit d637213（文章+帧图+契约）+装位 diff 一致
- 实锤坑：①ego stdin vm 对非 async 箭头里的 await 直接 SyntaxError 无行号（bili 惯用法别混入）②站点数量契约：新文章顶红 pages.spec 工程笔记 6→7（follow-up 修契约），About 批红=并行负载抖动（单跑 9/9，维护手册有案）③站点 preview 页绝不进 source/（Hexo 原样发布）④ai_score --json 依赖 article_meta（闭包要收全）
- S7-D：gzh_pack 三件套已产（标题 30/64、5 图 5 占位）+ drivers/gzh.mjs v1 跑通到登录闸门（掉登录 handOff JSON 零 blocker）；**dry-run 到存草稿卡扫码=用户门**
- S7-E：真一期全链终审待用户（预览页 blog_preview/esp32-lcd-ai-driver.html + 文章 + 公众号草稿三处肉眼过）

## [2026-11-08] 会话续: S8 A~D 一口气全交付（两级实测全过，报告落盘）
- S8-A: 克隆 97M（直连挂死→7890 代理）+依赖摸底（node22/Chrome156/系统无 ffmpeg→Remotion 自带+imageio_ffmpeg 兜底）
- S8-B: 模板 AiflPromo 36.22s 1080p 渲染 3.5min 三帧验优；剪映冒烟=仓库 smoke_test.py 是 Mac 专属→自写 win_smoke.py 平替 windows_draft.install，**三查全过=官方 win untested 风险实锤剪掉**（用户肉眼验收）
- 坑#4 根治: Remotion 内置浏览器下载器不走代理（25MB 爬 25min≈16KB/s）且缓存按项目隔离无全局——代理 curl 拉 zip 118MB/11.7s（600 倍差）+place_headless.py 落位双层嵌套目录+VERSION，ensure 验证零下载；变通=--browser-executable 系统 Chrome
- S8-C: 技能化走通（扫卡→读卡命门→移植 demo 源码），三卡 flying-words/list-reveal/before-after 适配 R06 文案 15s 一次渲通；中文两坑实踩（词表字号下调/角标宽度穿帮左移修复）
- S8-D: 实测报告落 features/S8-video-shotcraft-test/；方向性发现=**video-talkcraft 才是口播正解**（节拍钉人声），shotcraft 卡库+aesthetic-rules 作共享资产；集成建议「只抽资产不改内核」留 S9 先实测 talkcraft
- 产物位: 测试根 video-shotcraft-test/{video-shotcraft,r06-motion,scripts,pitfalls-win.md,chrome-headless-shell-win64.zip}；真素材 r06-motion/out/r06.mp4

## [2026-11-08] 会话续2: S9-talkcraft-test 一口气交付（真素材核心链路全通）
- 范围: 用户「talkcraft 实测」直接确认 S8 报告建议（轻档记账，不重走 R0）；克隆 66M 同构仓库
- S9-A 摸底: Python3.14 雷区实锤——faster-whisper 1.2.1 × av15+ 不兼容（metadata_errors 移除，av14 无 cp314 wheel）→ run_tc.py monkeypatch shim 根治；zhconv/pypinyin 补装，faster-whisper/numpy/soundfile 本机已有；系统 ffmpeg 缺 → imageio 二进制顶 tools/bin（ffprobe 残留，gyan 两次超时）；junction 配方（ln -s 在 Git Bash=复制，workbench 占位文件先删再链）
- S9-B: runtime 292 包一份依赖 + place_headless 复用（两库同需 chrome 149）+ workbench junction → 单帧冒烟 PASS
- S9-C 真素材: 00_口播 73s 录音（只覆盖第1拍 3 句+含 v1.5 改稿痕迹，R06 无独立音频故弃）→ voice_trim 预剪 17 段 −23.46s（报告细到 skip:extra「一个免费的AI浏览器」）→ whisper 字级时间戳（match 0.84/0.89/0.97，听错字/幻觉段按设计标待人工）→ remotion 工程 junction runtime → 素排字幕+花字 EGO LITE 字级钉帧渲 49.8s 3.3MB；两轮修复（FlowerWord 无淡出多朵同位叠穿帮→只留一朵）
- S9-D: 报告落 features/S9-talkcraft-test/；对比表+集成建议=motion 子技能内核定 talkcraft 方向（透明通道接 shoot 暂存区最短路径）；**许可红线 PolyForm Noncommercial 商用需授权，挂用户拍板**
- 用户门: 看两支片（r06.mp4 / talks3.mp4）→ verify s8 s9 → 许可拍板 → S10 立项

## [2026-11-08] 会话: S7-D 公众号驱动器攻坚（正文自动全通，插图转人工兜底）
- 交付: drivers/gzh.mjs v2.5——登录→新建图文→标题/作者/摘要→正文原生粘贴→（SKIP_IMAGES=true 出干净占位符草稿 38.6s / false=自动插图）→存草稿→截图存证→自关窗；草稿箱可见草稿多轮实证，群发按钮全程未碰（S7-D 验证门达成，图片人工兜底）
- 机制实锤（全部带痛换来）: ①ego 窗口标题=空间名（如 blog-gzh-459763）→win_window.ps1 v2 按标题作用域 restore/minimize/close(WM_CLOSE)，杀进程从流程移除（并行会话保护，用户点名批评后改的）②CDP page.cdp(method,params) 直调 Browser.setWindowBounds 还原/最小化自己窗口；强杀会留「ego 未正确关闭」崩溃弹窗③mp 编辑器=顶层 ProseMirror 非 ueditor iframe；PM 注入必须 ego keyboard.paste({text,html}) 原生粘贴（合成 ClipboardEvent 只进 8 字=placeholder widget 的字数，pms[last] 会抓到 widget，真 body 按 contenteditable!=false 过滤）④appmsg 直连必须带 token；登录判据=URL token+「新的创作」（后台首页也含「扫码登录」字样，文本判据假阴性害跑三轮）⑤插图：工具栏图片菜单的 input[type=file][accept*=gif] 直 setInputFiles 可落图+CDN 自动上传，但光标落位撕占位符留残渣+每图双份未解→人工兜底 ⑥ego 窗口一被最小化 Windows 冻结渲染：真鼠标/chooser/截图全死，DOM 级免疫（S6 契约复证）
- 流程卫生: 驱动器 page.close 自关窗+取消取消残留=预清场用 WM_CLOSE 温和关（title 作用域）；草稿箱校准期攒 7+ 测试稿待用户批删
- S7-E 待用户三处终审: ①选帧预览（换帧/删图兜底）②文章（已 commit d637213）③公众号草稿（blog-gzh-231904 传 5 图后终审）
