# plan — S1 draft-workbench（大纲/脚本审阅修改工作台）

> 档位：中 · 日期：2026-11-03 · R0 追问 + R1/R2 对话确认后统一落盘

## 方案

### 需求理解（R0 Q→A）

| # | 问题 | 结论 |
|---|------|------|
| Q1 | AI 生成/修改走哪条链路？ | 用户：链路不用考虑，**输入是 md**，要装成可编辑+可点评的工作台；委托调研 GitHub 同类项目 |
| Q2 | 调研结论？ | easychen/markmark（macOS 独占，CriticMarkup 删/换/评/高亮四件套+✨复制给 AI）工作流同款但平台不可用→思路移植；BlockNote md 往返有损→否决；CodeMirror 6 源码式体验错位 |
| Q3 | 部署形态？ | 本地小服务+浏览器（Windows；md 源在 vault） |
| Q4 | 范围？ | 只做批注修改环节；AI 调用本期不做，✨复制给 AI=未来接缝 |

### 目标一句话

把 AI 出的 md 初稿装进网页工作台，逐块/逐句直接改+打批注，批注一键打包成修改指令喂 AI——替代「对话里来回描述哪里要改」。

### 候选方案与选定

- **A 自研块编辑器（vanilla JS + Python 零依赖服务）✅选定**：md 往返保真完全可控，零依赖零 CDN，块模型天然匹配逐条/逐句批注；代价：手感自建、行内语法编辑时显示 md 源码形式
- **B BlockNote/TipTap 重前端**：md 导入导出有损违反「纯净写回」硬约束，offline 依赖树巨大
- **C CodeMirror 6 源码式**：源码零损但体验像改代码不像审稿，交互上限低且省不了工

选定理由：唯一同时满足「md 保真写回 + 零依赖铁律 + 块级批注体验」。

### 关键技术点

- **块模型**：md→块数组（标题/段落/列表项/引用/代码块/表格整块），解析→重组 round-trip == 原文
- **数据格式（受用户委托约定）**：md 本体纯净、下游管线照吃 + 旁车 `<name>.review.json`：

```json
{
  "version": 1,
  "source_sha256": "打开时 md 指纹，检测外部改动",
  "comments": [{
    "id": "c1",
    "block_hash": "块内容 hash 锚定",
    "quote": "块内选中片段（整块批注省略）",
    "type": "comment | delete | replace | highlight",
    "suggestion": "replace 的新文本",
    "note": "意见",
    "status": "open | resolved"
  }]
}
```

- **漂移策略**：block_hash+quote 双匹配找回，找不到标 orphan 置顶面板手动重锚，绝不静默丢批注
- **高亮红线**：只活在 UI 层+review.json，绝不写进 md 本体
- **前端**：web/ 单页原生 JS 自包含，不从 CDN 拉任何资源（环境铁律：国内网络在线解析必挂）
- **后端**：draft_server.py 纯标准库 http.server；中文注释；unittest 进 tests/ 对齐仓库约定
- **落点**：skill/media/draft/（workbench 名已被素材工作台占用）；**改完 cp 同步安装位**（media skill 双拷贝）
- **链路位置**：选题 → AI 大纲 → **draft 审阅批注** → 定稿口播 md → workbench 素材生产 → cut

## 拆分

| ID | 子步骤 | 内容 | 验证 | 依赖 |
|---|---|---|---|---|
| S1-A | 后端块解析器 | draft_blocks.py：md→块数组+块 hash+重组写回 | round-trip 单测（中文/嵌套列表/表格） | — |
| S1-B | 本地服务+API | draft_server.py：打开 md/块读写/写回/review.json CRUD/AI 清单导出/静态托管 | curl 冒烟+改字落盘 | A |
| S1-C | 前端块编辑 | web/ 单页：块渲染/contenteditable/增删块/拖拽排序/保存 | 浏览器改字→md 正确变化 | B |
| S1-D | 批注四件套+面板 | 选中浮动条（删/换/评/高亮）、批注面板状态流转、orphan 重锚 | 打批注→json 落盘→重开锚位正确 | C |
| S1-E | 复制给 AI+收尾 | ✨清单导出进剪贴板、draft/SKILL.md 工作流剧本、CLAUDE.md 路由+双拷贝同步 | 真实一期大纲全链路手测 | D |

### 关键决策

1. 目录名 `draft`（workbench 已占用；定稿即 workbench 口播输入，链路顺）
2. 批注/高亮绝不进 md 本体（md 纯净红线）
3. 纯标准库+中文注释+unittest 对齐仓库开发约定
4. 改完 cp 同步安装位（media skill 双拷贝老坑）
