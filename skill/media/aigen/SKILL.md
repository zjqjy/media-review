---
name: aigen
description: media 子技能：AI 生图素材（火山方舟 Seedream 按量付费）。由 media 门面路由进入——为视频生成表情包贴纸/插画素材/封面配图，含提示词规范、角色一致性、去底处理、接入 Remotion 素材工程。纯 HTML 卡归 cards，纯动画直出归 Remotion/vibe-motion，这里是"生成图片素材"这一步。
---

# aigen · AI 生图素材（火山方舟 Seedream）

按量生成图片素材：表情包贴纸、插画、封面配图。链路=提示词（官方规范）→ 生成（单张/组图）→ 去底 → 落目标工程 `public/`（如 Remotion 贴纸工程）→ 渲染验收。一次生成成本约几毛钱，**先单张试画风再批量**。

## 什么时候用我 / 不用我

| 用 | 不用（换方案） |
| --- | --- |
| 表情包/贴纸（角色+情绪+梗短句一体）、插画素材 | 信息卡/图表 → cards（HTML 录屏） |
| 封面配图、氛围图、梗图二创 | 跟口播节拍的动画 → Remotion/vibe-motion |
| 角色一致性成套图（参考图锁形象） | 截屏/实拍能解决的 → 拍真实素材 |

## 配置与凭据（红线：key 绝不进任何 git 跟踪文件）

- **控制台**：https://console.volcengine.com/ark 开通模型 + 建 API Key（文档公开可读，**控制台才要登录**）
- key 两处放：环境变量 `ARK_API_KEY`（优先）或工作目录向上找 `.ark_key` 文件（一行明文）
- ⚠️ 控制台列表里的 `apikey-xxxx…-xxxx` 是**脱敏显示不是明文**，复制要用「查看/复制」拿完整串（新格式 `ark-` 前缀，2026-09-17 后创建）
- 常见卡点：`ModelNotOpen`=模型没开通（模型详情页点开通）；`429 SetLimitExceeded`=「安全体验模式」限额触发，去开通页关掉或调高

## 流程（照表执行）

| 步 | 动作 | 要点 |
|---|---|---|
| 0 | 单张试画风 | 一条提示词先出 1 张，人工看画风过关再批量——画风不对改提示词重出，几毛钱的事别心疼 |
| 1 | 批量/组图 | 角色一致性两条路：①固定**风格前缀+固定 seed** 多次调用；②组图一次出（提示词用"一套 N 张…"，`--group N`，角色锁定最稳） |
| 2 | 要烤进图的文字 | 按官方指南放**双引号**（如：图片下方一行大字："都2026年了！"，白色粗体黑描边）——Seedream 中文文字渲染是国内最强，表情包的梗短句直接烤进图 |
| 3 | 去底（可选） | `python scripts/debg.py <文件或目录...>` 洪泛填充抠背景（从边缘清连通同色区，保留描边），透明底落卡片色/工程底色 |
| 4 | 接工程 | 图片落目标工程 `public/`；Remotion 贴纸工程（本仓 skill 外的目标工程）在贴纸条目加 `src: '文件名.png'` 即上屏，`npm run render:preview` 验收 |
| 5 | 渲染注意 | Remotion 渲染遵循其工程规范（无头浏览器走本地 Edge、日志禁 tail 管道） |

## 提示词规范（官方指南浓缩，全文件夹 `seedream-prompt-guide` 链接见文末）

1. **自然语言完整句**：主体+行为+环境，再补风格/色彩/构图——不堆关键词
2. **写明用途**："设计一张表情包贴纸…"比"一张抽象图片…"稳
3. **要生成的文字放双引号**，并指定字色/描边/位置
4. **参考图生图**：`image` 字段传 URL 或 b64；提示词写清两部分——保留参考图什么（"参考图中的角色形象"）+ 生成什么（新情绪/新场景）
5. **组图**：提示词含"一套/组图/具体数字"触发，一次调用角色统一
6. **角色一致性模板**：风格前缀固定（如"圆滚滚的橘色虎斑猫大头特写，粗黑描边扁平插画，脸颊腮红"）+ 固定 seed，每次只换情绪描述段

## 脚本

```
scripts/gen_image.mjs   生成（node ≥18，零依赖）
scripts/debg.py         洪泛去底（PIL，install.ps1 已装）
```

```bash
# 单张
node scripts/gen_image.mjs -o out.png --style "<角色前缀>" "瞪圆双眼震惊……背景暖黄放射光芒。图片下方一行大字："都2026年了！"白色粗体黑描边"
# 一套 4 张组图（角色锁定）
node scripts/gen_image.mjs -o set.png --group 4 --size 2K "生成一套4张猫咪表情包……第一张：震惊；第二张：墨镜得意；第三张：戴奖章骄傲；第四张：星星眼欢呼"
# 去底（文件或目录递归）
python scripts/debg.py public/peach_look --tol 45
```

## 技术事实（踩过的坑，别再踩）

- **模型 ID 必须带日期后缀**：`doubao-seedream-5-0-flash-260915` / `5-0-pro-260628` / `5-0-lite-260128` / `4-5-251128` / `4-0-250828`——无日期别名 404
- 401 `AuthenticationError`=key 是脱敏串；404 `ModelNotOpen`=没开通；404 `InvalidEndpointOrModel.NotFound`=未开通或 ID 错（Ark 对未开通模型也报 NotFound）；429 `SetLimitExceeded`=安全体验模式限额
- 脚本内存路径用 `fileURLToPath`，别用 `new URL().pathname`（中文路径会 %E8 编码炸 ENOENT）
- 官方文档是 JS 渲染页，WebFetch 抓不到——用 control-browser 技能开页后 `evaluate` 取 innerText；文档不用登录
- 官方文档：接口 https://docs.volcengine.com/docs/ark/image-generation-api ；接入教程（含模型 ID 全表）https://docs.volcengine.com/docs/ark/seedream-4-0-5-0 ；提示词指南 https://docs.volcengine.com/docs/ark/seedream-4-0-5-0-prompt-guide

## 红线

1. **key 不进任何 git 跟踪文件**（环境变量或 .ark_key，且 .ark_key 不在仓库内）
2. **未授权 IP 形象不当固定资产**：蜜桃猫等现成 IP 只做过渡期素材/产品同款露出，每期固定的仪式位资产必须是自有 IP 或 AI 生成的自有角色
3. 云端生图不涉密：内部敏感数据（# sensitive）不进提示词
4. 批量生成前先单张验画风；单次批量 ≤8 张（按量付费防手滑）
