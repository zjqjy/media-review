# publish · 三平台自动发布子技能（ego 直驾 + SOP 教材化，S6）

把剪辑链路的成品（剪映导出的整片）+ cover 子技能的封面，自动发布到小红书/B站/抖音。
执行者=对话 agent 本体，浏览器动作全部用 **ego-browser**（读 `ego-browser` skill 后再动手），
模拟人类操作节奏；**本子技能的脚本只管纸面（字数校验/确认单/发布记录），不碰浏览器**。

## 常量与知识源

- `platforms.json`（本目录）：三平台入口 URL、字数上限、必填字段、坑位。**`verified=false`
  的数值是待实测占位**——dry-run 时以页面 maxlength/计数器为准回写并置 `verified=true`。
- `research/2026-11-07-github-uploaders.md`：调研依据（social-auto-upload 等源码提取）。
- ego 能力对照：传文件 `setInputFiles`/`waitForFileChooser`；扫码 `handOff()`；
  认路 `snapshot()`（语义 ref 抗改版，选择器现场比对，不硬依赖 platforms.json 里的 hint）；
  存证 `screenshot()`。

## SOP

### 第 1 步 · 收料核验
- 视频：对话附件（已落盘路径）或用户给路径/目录；**不自动猜文件**。核验存在+可读，
  ffprobe 看时长（超平台上限[如小红书]要提醒）。
- 封面：cover 子技能产物三画幅，按平台映射（B站=16x9、小红书=3x4、抖音=竖版 9:16 优先）；
  缺对应画幅先问用户要不要用 cover 补，别拿别的画幅硬顶。
- 可选参考：定稿大纲 md / 逐字稿 / 用户点名的标题倾向——标题简介从这里提炼，别凭空编。

### 第 2 步 · 草拟三平台文案（发前确认的「确认」材料）
- 每平台一套：标题/简介/tags + 可选项：**话题（真芯片）/原创声明/内容类型声明/合集**
  （合集和声明用户点名才填，默认问一句；字段结构见 `scripts/publish_plan.py` 模块注释）。
- 字数严守 `platforms.json` 上限：短平台（小红书标题 20 字）从长版**压缩改写**，不硬截。
- 平台差异化：B站简介可长带章节；抖音简介短带话题；小红书标题抓眼球+正文带 emoji。
- 写 plan.json（结构见 `scripts/publish_plan.py` 模块注释），跑：
  `python scripts/publish_plan.py check --plan plan.json` → 非0=有问题先修。
- `confirm` 渲染确认单给用户。**改哪条听用户的，改完重新 check+confirm**。

### 第 3 步 · dry-run（默认必经，R0-4 定音）
用户看过确认单说「发」之后：
1. 逐平台建独立 taskSpace（`publish-<pid>-<日期>`），goto 入口页。
2. snapshot 判登录态：出现「扫码登录/登录」即未登录 → `handOff()` 请用户扫码，确认后 resume。
3. 传视频 `setInputFiles` → 等表单渲染（抖音要等视频传完，给足 120s）。
4. 按确认单填：标题 → 简介 → **话题挂芯片**（打 `#` 出联想下拉→点选目标话题成芯片锚点；
   只留 `#文字` 不算挂上）→ tags → 分区（B站）→ **创作声明三平台都默认 AI 生成口径**
   （B站「含AI生成内容」/抖音「内容由AI生成」/小红书在内容设置区选 AI 相关项，用户可改）
   → 合集（确认单里点名才动）→ 传封面 → 关浮层/弹窗。
   **标签被静默拒绝是常态**（B站重复标签配额不变且无报错）：加完对比配额行，没变就换词，
   死磕重试是 agent 卡死的第一大坑。带「合作/计划」标记的话题=要报名的商业活动，跳过换普通词。
5. **停在「发布」按钮前**：`screenshot` 存证 + snapshot 摘要表单状态，交用户过目。
6. 节奏：平台内动作间随机延时（模拟人类）；平台间可并行（子 agent 各管一个 taskSpace，见「并行子 agent 发布」）。

### 第 4 步 · 正式发布
用户看过 dry-run 截图、确认表单无误后：
1. 回到**同一个** taskSpace（round 文件续写，space id 沿用），点「发布」。
2. 等成功信号：跳转到内容页/成功提示（snapshot 确认），screenshot 存证。
3. 落档：`python scripts/publish_plan.py record --video 成片.mp4 --platform <pid>
   --title "…" --url <内容页链接>`。
4. 单平台失败：screenshot+人话汇报原因，**停下交人，不重试不乱点**；其余平台继续。

## 快发驱动器（scripts/drivers/，2026-11-08 3 分钟目标产物）

逐轮 snapshot 慢舞步只够 dry-run 摸路；真发用**单发驱动器**：`scripts/drivers/{bili,xhs,douyin}.mjs`
每个是一次 `ego-browser nodejs < driver.mjs` 跑完全程（上传→填表→声明→封面→**停发布按钮前**），
头部 CONFIG 块按当期 plan 改（视频/封面/文案/taskSpace 名），三平台三进程**并行**跑。

- 实测（285MB 真片，并行墙钟 **~45s**）：B站 24.8s 零 blocker｜抖音 ~50s｜小红书 ~41s
- 无人值守模式的已知残留（driver 三轮迭代后仍不稳，标准对策=driver 填完主 agent 30 秒补刀）：
  ①话题联想行程序化点击/坐标点击都不挂芯片（手动 text="#词" 真点击可行）→ 主 agent 补挂
  ②抖音竖封面 image input 时序抖动 ③xhs 封面缩略图渲染时长不定（driver 已带 30s 等待环）
- B站封面按用户口径只传 4x3（个人空间 16:9 平台派生）；抖音声明弹窗/封面编辑器在 driver 内 text= 坐标法可用
- driver 末尾必出 JSON（ok/elapsedSec/screenshot/blockers）+ uncaughtException 兜底，任何失败都留人话报告

## 并行子 agent 发布（默认启用，2026-11-08 用户点名）

确认单过审后，**主 agent 一口气派遣三个 general-purpose 子 agent**（小红书/B站/抖音各一）并行发布，不串行磨叽。**两阶段，同一 TaskSpace 复用**：

- **阶段1 dry-run**：子 agent 按 `briefs/subagent-brief.template.md`（填 {{PID}}/{{TASKSPACE}}/{{PLAN_JSON}}/{{DECLARE}} 等变量）把真实成片+文案填进表单，**停发布按钮前**截图回报
- **用户过目截图** → 说「发」→ **阶段2 真发**：主 agent（或复派子 agent）resume 同 space 点发布 → 等成功信号（跳转/成功提示）→ screenshot 存证
- 每个子 agent 只领**一个平台**：读 brief + `platforms.json` 对应平台节 + `ego-browser` skill，用**自己的 taskSpace**（`publish-<pid>-e<N>-<日期>`）
- 平台间并行无妨（互相看不见）；**平台内保持人类节奏**（动作间随机延时），同一平台绝不并发两个 agent
- 子 agent 不写发布记录：返回**三件套**——①JSON 结果（platform/成功与否/内容页 URL/截图路径/blockers）②**卡点清单**（实际踩到的坎，逐步人话）③**改进建议**（指名改 platforms.json/SKILL.md/brief 哪里）；主 agent 拿 ②③ **回写常量表与 SOP**（每次发布必须让技能更好一点），并统一落档 `publish_plan.py record`
- 子 agent 遇验证码/异常弹窗/掉登录：截图留证、停止、如实回报，不重试不乱点
- 登录态已在 ego profile（三平台都登录过）；子 agent 发现掉登录→回报主 agent，由主 agent handOff 请用户扫码

## 红线

- **确认单没过、用户没说「发」，绝不点发布**（dry-run 停按钮是硬闸门；首跑真发用户在场）。
- 验证码/人机验证/异常弹窗 → `handOff()` 交人处理，**不绕过不硬闯**——模拟人类是
  「正常操作不被误伤」，不是反风控对抗。
- 不碰账号设置/钱包/私信/直播页；只走发布链路。
- 内容与确认单不一致（平台表单回显被改、字数计数器对不上）→ 停下核对，不带病发布。
- 登录态只在 ego profile 里，不导出 cookie 不分享；主号 profile 与 benchmark 的 B站小号
  彻底隔离。
- 表单填一半失败 → 截图留证，报告「停在哪一步、看到了什么」，等用户指令。

## 产物约定

- `<成片>.publish.json`：发布记录（平台/标题/链接/时间/note），与成片同目录同名跟着素材走。
- 截图存证：`<成片目录>/publish_shots/<日期>/<pid>-dryrun.png`、`<pid>-published.png`。
- 校准回写：dry-run 发现 platforms.json 占位数值/流程与实际不符 → 当场回写常量表
  （verified 置 true）并在 journal 记一笔。
