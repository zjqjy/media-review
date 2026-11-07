# plan — S3-cover-skill（media 封面子技能，oil-cover 移植+火山 API 化）

## 方案

### 需求理解（R0，2026-11-07 确认）

- **目标**：`/media` 新增第 10 个子技能 **cover**（视频封面生成），移植 oil-cover 方法论与产物标准，API 层全部换成用户手上资源：分析默认 agent 本体做，生图走火山 Seedream；无多模态宿主可切 API 分析模式。
- **改造后形态**：

  ```
  ① 本地选帧  脚本保留（ffmpeg+PIL 全片预筛 8 候选，零 API）
  ② 视觉分析  双模式，同一把 ARK key：
     · mode=agent（默认）：agent 读候选帧+视觉规范 → 挑帧+标题断行+写 prompt，零成本
     · mode=api：脚本调 Ark doubao 视觉模型全自动一条龙（给没多模态的宿主用）
     · 配置设一次不问；agent 跑不动明说切 api，不静默失败
  ③ 生图     脚本调火山 /api/v3/images/generations，Seedream + 参考帧
  ④ 本地合成  Pillow 头像合成保留可选，默认不启用
  ```

- **边界（不做的事）**：ZenMux/credential-ui 代码不搬；docs 3.9M/tests 不搬；不做纯脚本无人值守一条龙（agent 模式②需要 agent 在场）；aigen（生成图片素材）与 cover（成片封面整图）职责分界不变。
- **验证方式**：脚本部分单测绿（选帧+Ark 分析/生图请求构造可 mock）+ 一期真实视频走全链路出三画幅封面（3:4/4:3/16:9 落视频旁）+ 装位同步（仓库↔`~/.zcode/skills/media/`）。
- **已确认约束（R0 Q→A）**：
  - Q: R0-1 API 切多深 → A: 分析=agent 本体零 API；生图=火山 Seedream（ARK_API_KEY/.ark_key）；ZenMux/credential-ui 整层退役
  - Q: R0-2 旧 skill 去留 → A: 精简移植进 `skill/media/cover/`，旧 `~/.agents/skills/oil-cover` **保留不删**（初判退役删除，2026-11-07 用户改判：留着不影响）
  - Q: R0-3 分析回退 → A: 双模式同一把 ARK key（agent 默认 / api 全自动），继承 oil-cover「跑不动明说两条路，不静默失败」
- **默认假设**：封面落视频旁（`<视频名>_4x3.png` 等），中间产物收 `<视频名>.cover/`；三画幅全保留；路由词「封面 / cover / 做封面 / 视频封面」；标题提炼职责归 agent（oil-cover 原设计），api 模式下归分析模型。

### 候选方案（R1）与选定理由

- **A. 原地改造原脚本 ✅**：拷 `generate_oil_cover.py`（1925 行）进 cover/scripts/ 原地动刀——剥 ZenMux/credential-ui/edits multipart，接 Ark 双分析+Seedream 生图+`--prompt-file` agent 入口。优点：选帧评分/分桶/retry/三画幅/sidecar 管理全是实战验证过的代码，保真度最高，行为基线=oil-cover 已验证形态。工作量 M。
- **B. 重写瘦脚本**（落选）：~500 行干净重写。风险=选帧评分阈值/分桶细节易抄漏，恰是画质稳定关键，重造轮子=重新踩坑。工作量 M~L。
- **C. 组装复用 aigen 家底**（落选）：生图调 gen_image.mjs。风险=node+py 跨语言编排丑；gen_image.mjs 无参考帧上传/三画幅并行/sidecar 管理；cover 反向依赖 aigen 脚本形成子技能耦合。工作量 M。
- **选定理由**：cover 价值核心=oil-cover 选帧+产物标准实战代码，原地改造保真度最高；Ark 接口格式 aigen 已趟平，改造点收敛在 API 层三处（base_url/模型/key）。
- **用户追加约束（2026-11-07）**：基线取上游 GitHub 最新版（https://github.com/oil-oil/oil-cover），先 clone diff 本地装位再动刀。

### 关键技术点

- Ark OpenAI 兼容接口：分析走 `/api/v3` chat/completions 传图（doubao 视觉，**模型 ID 必须带日期后缀**，aigen 已踩）；生图走 `/api/v3/images/generations` + image 参考帧参数（aigen gen_image.mjs 已趟平格式）
- key：环境变量 `ARK_API_KEY`（优先）或工作目录向上 `.ark_key` 文件（aigen 同款约定）；绝不进仓库
- agent 入口：`--prompt-file` 跳过分析直接生图；`--dry-run`/`--skip-generate` 排查参数保留
- mode 配置设一次不问（oil-cover 约定继承）；头像 Pillow 合成可选默认关，头像绝不进分析/生图参考图
- 开源合规：LICENSE/NOTICE 保留
- 编号说明：journal 曾预留 S3 给 P13（shoot 交付/回收闭环），本期 cover 先占 S3（以 features/README.md 总表为准）；P13 立项时编 S4

## 拆分（R2 确认稿）

| ID | 名称 | 依赖 | 验证方式 | 预估 |
|---|---|---|---|---|
| S3-A | 上游基线+骨架：clone 上游最新 diff 本地取新；建 `skill/media/cover/`（scripts/references/assets），references 精选（cover-rules/product-assets/impact-tech/agent-native-flow）+ assets 精选 + LICENSE/NOTICE | — | 目录结构齐，diff 记录本地落后项 | S |
| S3-B | 脚本换血：剥 ZenMux/credential/edits multipart；Ark 双分析（agent `--prompt-file` 入口 / api 调 doubao 视觉）+ Seedream 生图（images/generations+参考帧）；key 走 ARK_API_KEY/.ark_key；mode 设一次不问；`--dry-run`/`--skip-generate` 保留 | A | `--dry-run` 零 API 走通；Ark 请求构造 mock 单测过 | M |
| S3-C | SKILL.md 重写+门面路由：cover/SKILL.md 按 media 子技能风格（agent 默认流程/api 回退/红线继承 oil-cover 不可违反清单）；media/SKILL.md 路由表加行+description 扩触发词（封面/cover/做封面/视频封面） | B | 路由词齐，双模式说明自洽 | S |
| S3-D | 单测：选帧逻辑（合成视频 fixture）、Ark 分析/生图请求构造（mock）、编排（agent 喂 prompt 全链路不调 API）、缺 key 报错人话 | B | pytest 全绿（305+新增） | M |
| S3-E | 真实验收+收尾：一期真实视频 agent 模式全链路出三画幅落视频旁；仓库→装位 cp 同步；**旧 `~/.agents/skills/oil-cover` 保留不删**（2026-11-07 用户改判：不影响，留作参照） | B,C,D | 三画幅产物正确+装位一致 | S |

### 关键决策
- [2026-11-07] 方案 A 原地改造，基线取上游 GitHub 最新（非本地装位，可能落后）
- [2026-11-07] 分析双模式同一把 ARK key；mode 设一次不问；回退明说不静默
- [2026-11-07] 精简移植；旧装位保留不删（用户改判：留着不影响，可作对照）
