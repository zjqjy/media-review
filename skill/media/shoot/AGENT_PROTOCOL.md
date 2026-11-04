# AGENT_PROTOCOL — 跨 agent 拍摄-剪辑任务板协作规程卡（S2-E）

> 读者：拿到本项目目录的外部 AI agent（claude code / codex / zcode / 任何能读写文件并运行
> python 的 agent）。本卡自包含：照做即可安全领取任务并回写状态。
> 违反 §3 回写规则的改动会被校验器逐项列出并拒收，拒收 = 任务未完成。

## 1. 这个目录是什么

一条视频的「拍摄-剪辑任务板」由两个文件构成（都在本项目目录里）：

| 文件 | 是什么 | 你能不能写 |
| --- | --- | --- |
| `<定稿>.md` | 视频定稿稿子（口播/分镜文案），它是全项目的"事实源" | **绝对只读，一个字不改** |
| `<定稿>.md.shoot.json` | 旁车任务板（JSON），与 md 同目录、同名，仅后缀多 `.shoot.json` | **你唯一可写的文件**（且只许改 §3 白名单字段） |

**项目根** = 放素材目录（`03_实拍素材/`、`05_剪辑交接/` 这类编号目录）的那一层，
**不一定**是定稿 md 所在目录（md 常在 `00_口播/` 子目录里）。`footage[].file` 与
`tasks[].output` 里的相对路径**一律相对项目根**解析，与 md 无关。

`<md>.shoot.json` 分五节：

- `annotations`：呈现批注（R01、R02…，定稿侧定下的拍摄/制作需求）。条目里 `kind`
  是 `manual`（人工实拍）或 `ai`（AI 制作）；`ai_type` 是 `card|motion|aigen|other`；
  `shoot_hint`（人工拍什么）/ `ai_brief`（给 AI 的制作指令）是任务内容本体。
- `footage`：素材表（已拍回/已生成的素材文件，`state: candidate|selected`）。
- `editNotes`：剪辑批注（这段素材怎么进成片）。
- `tasks`：**待办任务，你的工作来源**。条目 = `{id, type, ref, state, output}`，
  `ref` 指向 `annotations` 里对应的那条批注。
- `plan`：拍摄清单/AI 任务清单的宿主路径字段。

顶层还有 `version`（schema 版本，恒为 1）、`source_sha256`（定稿 md 的 sha256 指纹）、
`locked`（定稿锁）。`source_sha256` 对不上当前 md 实际指纹 = md 被人动过，一切回写被拒。

## 2. 领取任务

1. 读 `<md>.shoot.json` 的 `tasks` 数组；只考虑 `state == "open"` 的条目
   （`doing` = 别的 agent 认领中，`done` = 已完成，都跳过）。
2. 按 `type` 对照自己的能力：
   - `card` = HTML 字幕卡（静态图文卡，产物是 .html）
   - `motion` = Remotion 动效（产物是可渲染的 Remotion 工程/视频）
   - `aigen` = AI 生图（产物是图片文件）
   - `reshoot` = 人工实拍补拍。**这是给人做的活，agent 一律跳过——不许执行，
     也不许为它改任何状态。**
3. 能力匹配的 task：先看它 `ref` 指向的 annotations 条目，`ai_brief` / `shoot_hint`
   就是你的制作指令；产物按指令做出来，放进**项目根**下（路径基准见 §1；建议按产物
   类型建子目录——推荐对照：`03_实拍素材/` 实拍、`04_卡片/` HTML 卡、
   `05_剪辑交接/` cut 输入，沿用既有编号别自造新层）。
4. **开工第一步**：把该 task 的 `state` 改成 `"doing"`（这是认领标记，防止多个 agent
   重复做同一任务）。改之前先按 §4 拍快照。

## 3. 回写规则（硬约束，逐条遵守）

你**只许**改以下 4 类字段，且只限「既有条目」（不许增删任何数组条目）：

| 字段 | 允许的写法 |
| --- | --- |
| `tasks[].state` | 按状态机推进：`open → doing → done` |
| `tasks[].output` | 产物**相对项目根**的 posix 风格路径（如 `04_卡片/R01_卖点卡.html`） |
| `footage[].state` | `candidate` / `selected`（**仅当任务书明确要求**时才许动） |
| `footage[].note` | 字符串（**仅当任务书明确要求**时才许动） |

以下一律**只读**，动一个字段都算越权：

- `annotations` / `editNotes` / `plan`：整节只读；
- `source_sha256` / `version` / `locked`：整节只读；
- `<定稿>.md` 本体：只读（校验器会核对 sha256 指纹，改一个字节都会被拒收）；
- **不许新增、删除、重排任何数组条目**——`tasks` / `footage` 的新增由主控编排器负责，
  外部 agent 只许认领既有 task；
- **不许动 `tasks[].note`**——这是生成器的私有备案字段，不在你的白名单里；diff 里
  出现它的任何变化都视为绕过协议，拒收。

记住：文件即状态。你回写的就是普通 JSON 文件，没有服务器、没有锁——白名单 + 校验器
就是唯一的秩序。

## 4. 自检（做完必须跑，退出码 0 才算完成）

1. **改旁车之前**，先复制一份快照（放系统临时目录或项目外，别污染项目目录；
   这是本卡明文授权的动作——若运营指令说「只在项目内干活」，快照/临时文件豁免）：

   ```
   cp <定稿>.md.shoot.json /tmp/回写前快照.json
   ```

2. 用 JSON 原生方式改白名单字段（别手抖改到别的节）。
3. 跑校验器（`--root` 给项目根=素材目录所在层，§1；单目录项目可省）：

   ```
   python shoot/scripts/shoot_validate.py <定稿md> --root <项目根> --against /tmp/回写前快照.json
   ```

   - 退出码 **0** = 通过；非 0 = 拒收，按 stdout 的错误清单改到退出码 0 为止。
   - `[警告]` 行不挡退出码，但「产物不存在/空文件」的警告说明你还没真正做完。
   - 只想全量体检（不 diff）也可以：`python shoot/scripts/shoot_validate.py <定稿md> --root <项目根>`。
   - 校验器随本卡一起发在项目里（`shoot/scripts/shoot_validate.py`）；万一项目里缺失，
     找运营者要 media-review 工具库的
     `skill/media/shoot/scripts/shoot_validate.py`（同名同用法）。

## 5. 完成定义（三条缺一不可）

1. 该 task 的 `state == "done"`；
2. 它的 `output` 指向真实存在且**非空**的产物文件（相对项目根路径）；
3. §4 的校验退出码为 0。

三者齐了，你的回写才会被主控编排器采纳；任一不满足 = 任务未完成，继续改。

## 6. 出问题时

- 指纹不符（md 被改过）：停下别写，向用户/主控报告「定稿 md 已被外部改动」。
- 想领的 task 全被占了（没有 `open`）：不要等待不要轮询改状态，直接汇报无活可领。
- 校验器报「越权」：你多半改到了白名单外——从快照重新来，只碰 §3 白名单字段。
- 更完整的素材回收/匹配流程（主控侧）见 media-review 工具库
  `skill/media/shoot/SKILL.md`；本卡只管外部 agent 的领取与回写。
