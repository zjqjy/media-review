# plan — S2 shoot-pipeline（定稿后拍摄计划链路）

> 档位：重 · 日期：2026-11-05 · R0 追问 + 5 阶段讨论确认后统一落盘
> 讨论ID: 20261105-shoot-pipeline

## 方案

### 需求理解（R0 Q→A）

| # | 问题 | 结论 |
|---|------|------|
| Q1 | 批注粒度（R0-1，默认采纳后确认） | 块级为主+可圈句：默认整块一标注，需要时块内圈句单独标 |
| Q2 | AI 制作批注结构（R0-2，默认采纳后确认） | 类型枚举（cards/vibe-motion/aigen/其他）+ 自由指令文本；类型保证路由确定性，指令保灵活性 |
| Q3 | 数据宿主（R0-3） | 定稿旁新旁车文件 `定稿.md.shoot.json`，与 S1 `.review.json` 同模式、互不干扰 |
| Q4 | 素材归位（R0-4，用户点名） | **混合模式**：命名约定优先（拍摄清单预置建议文件名）+ AI 画面/声音匹配兜底 + 工作台人工确认收尾 |
| Q5 | 映射关系（R0-5） | 多对多 + 素材状态（候选/选用）；一行可挂 N 段候选 |
| Q6 | 剪辑批注宿主（R0-6） | 挂在素材表条目上（该段素材怎么进成片：截哪段/效果/接哪） |
| Q7 | 画面补制触发（R0-7） | 按①呈现批注**显式生成补制任务**，剪辑 AI 只消费不自作主张 |
| Q8 | 协议形态（R0-8） | markdown 人读清单 + JSON 旁车机器读；agent 回写状态字段（文件即状态） |

### 目标一句话

定稿 md 之后搭一条「呈现批注 → 拍摄 → 素材关联 → 剪辑批注 → AI 执行」的流水线：人只做批注决策和拍摄，匹配/清单/编排/执行交给 AI，全链路产物跨 agent（zcode / claude code / codex）可消费。

### 链路总图

```
定稿md ──①呈现批注(draft网页)──▶ 拍摄计划清单+AI制作任务
         ④agent协议贯穿（shoot.json + AGENT_PROTOCOL.md）
实拍素材 ──②素材关联(shoot面板)──> 素材表(候选/选用)
缺的画面 ──③补制任务(cards/vibe-motion/aigen)──> 画面
素材表+剪辑批注 ──③cut输入编译──▶ cut粗剪 ──post──▶ 定稿
```

### 关键决策（头脑风暴 5 难点选定）

| # | 难点 | 选定 | 否决项与理由 |
|---|------|------|------|
| 1 | 句级批注锚定 | **quote 锚定**（blockHash+句子文本+序号），复用 S1 三级回落机制 | 偏移量锚定：两套锚逻辑并存，工程量翻倍；定稿 md 不变 → quote 锚足够稳 |
| 2 | 素材匹配落地 | **AI 只出建议+置信度，全部人工确认才落「已关联」**，高置信度预勾选+批量确认 UI | 高置信自动挂接：错挂静默污染下游剪辑，返工更贵 |
| 3 | 状态宿主 | **单旁车 shoot.json 分节**（annotations/plan/footage/editNotes/tasks），素材本体在项目目录、json 只存相对路径+状态 | 按阶段拆多文件：跨文件引用同步翻倍 |
| 4 | 跨 agent 参与 | **项目目录内置 AGENT_PROTOCOL.md 规程卡**（目录约定+schema+领取/回写规则），任何 agent 读卡即接入 | 只靠 ZCode 转译：跨 agent 名存实亡 |
| 5 | ③与 cut 边界 | **③只做编排+输入准备**（编译 cut 认的输入），剪辑本体走 cut 规程，post 照旧；不够用给 cut 提扩展脚本 | ③自造剪辑执行层：重造轮子 |

### shoot.json 骨架（S2-A 细化定稿）

```json
{
  "version": 1,
  "source_sha256": "定稿 md 指纹（定稿后不变，外部改动即拒收）",
  "annotations": [{ "id": "p1", "block_hash": "...", "quote": "句级时非空",
                    "kind": "manual | ai",           // 人工拍摄 / AI 制作
                    "shoot_hint": "人工：拍什么/场景提示",
                    "ai_type": "card | motion | aigen | other", "ai_brief": "给 AI 的制作指令" }],
  "plan":       { "checklist_md": "拍摄计划清单路径", "ai_tasks": "AI 制作任务清单路径" },
  "footage":    [{ "id": "f1", "file": "03_实拍/相对路径", "ann_ids": ["p1"],
                   "state": "candidate | selected", "match": "filename | ai:0.87 | manual" }],
  "editNotes":  [{ "id": "e1", "footage_id": "f1", "note": "截 0:03-0:07，接 R05 卡片后" }],
  "tasks":      [{ "id": "t1", "type": "reshoot | card | motion | aigen", "ref": "p1", "state": "open | done", "output": "产物相对路径" }]
}
```

**agent 回写契约**：只许改 `footage[].state`、`tasks[].state/output` 等状态/产物字段；schema 校验脚本拒收非法写；文件即状态，不依赖任何 agent 在线。

### 边界（不做的事）

- 不做时间轴级精细剪辑 UI，剪辑执行归 cut 现有规程
- **不动 workbench 子技能**（用户明确排除，素材关联自立门户）
- 不做移动端/拍摄现场工具，命名约定以清单形式随身带
- AI 制作类型枚举先收敛到已有工具（cards/vibe-motion/aigen），结构可扩展

### 验证方式（提议）

schema/round-trip 单测 + ego 浏览器 E2E 全链路（S1 同款）+ 一期真实素材小规模试用 + 跨 agent 回写 E2E（claude code 或 codex 真跑一个任务）。

## 拆分

| 子流程 | 内容 | 前置 | 验证 | 优先级 |
|--------|------|------|------|--------|
| S2-A | shoot.json schema+校验脚本；draft 工作台呈现批注（人工/AI 制作+quote 圈句）；定稿锁定（只读） | 无 | schema/round-trip 单测 + ego E2E 批注落盘 | 1 |
| S2-B | 拍摄计划清单导出（建议文件名+提示，手机可看）；✨复制 AI 制作任务清单 | S2-A | 清单编译单测 + 真实定稿试用 | 2 |
| S2-C | 素材关联（新子技能 `shoot`）：回收匹配器（文件名精确→AI 建议→人工批量确认）；多对多+候选/选用；缺拍清单 | S2-A | 假素材集匹配单测 + ego E2E 确认流 | 2 |
| S2-D | 剪辑批注（挂素材条目）；补制任务显式生成（路由 cards/vibe-motion/aigen）；cut 输入编译 | S2-C | 编译单测 + 一期真实素材跑通 cut 输入 | 3 |
| S2-E | AGENT_PROTOCOL.md 规程卡；回写校验（schema+只许改状态字段）；跨 agent E2E | S2-A（可并行） | 非 ZCode agent 真实回写通过校验 | 收官 |

**落点**：①进 draft 子技能（S1 底座），②③④新开 `shoot` 子技能——不碰 workbench。
**执行顺序**：A → B∥C → D → E。
