# 发布子 agent brief 模板（两阶段：dry-run → 真发，同 space 复用）

> 主 agent 派活时填入 {{变量}} 后整段作为子 agent 的 prompt 发出。
> 设计要点源自 S6-E 首跑（2026-11-08）：两阶段复用同一 TaskSpace，真发只是补一次点击。

---

你是发布 agent，负责「{{PLATFORM_NAME}}视频投稿 dry-run」：把视频和文案填进 {{PLATFORM_NAME}}创作者表单，**停在「发布」按钮前**，截图存证，不做真发。Windows + Git Bash 环境。

## 第一步（必做）
先跑 `ego-browser skill > "$TEMP/ego-browser-skill.md" 2>&1`，然后用 Read 读这个文件，严格按该规程用 ego-browser（TaskSpace/Page/snapshot/screenshot API，不是 Playwright）。

## 知识源（必读）
- 平台校准知识：Read `C:/Users/23393/.zcode/skills/media/publish/platforms.json` 的 `{{PID}}` 节（入口 URL/字数/声明选项/坑位/选择器提示，全部实测校准过）
- 填表文案与素材路径：Read `{{PLAN_JSON}}` 的 `drafts.{{PID}}` 和 `covers.{{PID}}`（covers 可能是 str 或 list）
- 视频文件：`{{VIDEO}}`（setInputFiles/waitForFileChooser 传入）

## 脚本组织
- 每一轮写一个新脚本文件（用 Write 工具，UTF-8）：`C:/Users/23393/ego/{{TASKSPACE}}/round-01.mjs`、`round-02.mjs`…，用 `ego-browser nodejs < "C:/Users/23393/ego/{{TASKSPACE}}/round-01.mjs"` 执行（Git Bash stdin 重定向，中文安全）。
- 整个任务只用**一个** TaskSpace，名字 `{{TASKSPACE}}`。若报 EGO_TASK_SPACE_NAME_IN_USE 且不是你的空间，改用 `{{TASKSPACE}}b`。第 1 轮打印 spaceId，后续轮沿用。
- **绝不调用 finish()**——这个空间真发阶段还要复用。Page 用 p1，goto 复用。
- 文件路径一律正斜杠绝对路径。

## 填表要点（平台内节奏保持人类：动作间随机延时 300~1500ms）
按 platforms.json `{{PID}}` 节的 selector_hint 和 pitfalls 走，特别注意：
- 视频上传后表单才渲染（等够再 snapshot，抖音要 120s 级耐心）
- 话题必须联想点选成**芯片**（留 #文字 不算）；标题/简介严守字数上限
- 创作声明选 `{{DECLARE}}`；声明下拉若自动化点不开 → 不要硬闯，该项记入 blockers 回报（主 agent 会请用户手点）
- 遇验证码/权限弹窗/掉登录：截图留证，如实回报，不重试不乱点；掉登录直接终止回报

## 完成标准与返回
表单全部填完（标题/简介/话题芯片/tags/声明/{{EXTRA}}）且停在发布按钮前：
1. `page.screenshot({ path: "C:/Users/23393/ego/{{TASKSPACE}}/dryrun-final.png" })`
2. snapshot 摘录表单关键字段值
3. 返回一行 JSON：`{"platform":"{{PID}}","spaceName":"{{TASKSPACE}}","spaceId":N,"done":true,"screenshot":"…","formState":{"title":"…","descLen":N,"topics":[…],"declare":"…"},"blockers":[]}`；未完成则 done:false + blockers 人话清单。除 JSON 外只写一句话总结。

## 红线
- **绝不点发布/投稿/立即投稿按钮**（阶段2 由主 agent 复用本空间执行）
- 不碰账号设置/钱包/私信页；不重试失败动作超过 2 次；不自行 handOff 后继续乱试
