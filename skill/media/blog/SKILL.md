---
name: blog
description: media 子技能：发布后内容分发（S7）。由 media 门面路由进入——发布完的成片 → ①图文教程博客落个人网站（逐字稿+成片抽帧配图）②公众号排版到存草稿。定位：文章由 agent 本体按文风底盘写，脚本只管确定性工序（抽帧/校验/转换/验收/打包）。
---

# blog · 发布后内容分发（博客图文 + 公众号存草稿，S7）

发布完（publish 之后）一键两产：**图文教程版博客**（逐字稿+成片抽帧配图 → PersonalWebsite
`source/_posts/<slug>.md`，走站点验收到 commit，**不 deploy**）+ **公众号排版到存草稿**
（内联样式 HTML → ego 直驾，**群发人工点**）。执行者=对话 agent 本体：写文章、选帧决策、
预览兜底都是人活/agent 活；脚本只做机器能标准化的工序。

## 常量与知识源

- 站点仓库 `<SITE>`：根目录 `_config_local.json` 的 `site_path`（缺省 `D:\DeskTop\WorkSpace\Code\PersonalWebsite`）。
  站点规矩的单一事实源 = 站点仓库 `CLAUDE.md` + vault 维护手册卡（Hexo 8+Butterfly，
  发文五步，备案关站期只写到本地验收+commit）
- 逐字稿：vault `20_自媒体/复盘/逐字稿/第N期_*_逐字稿.md`（post 归档；frontmatter `sources`
  指着成片字幕 srt）
- 文风底盘（不可替换）：EM-SKILL `plugins/learning/STYLE.md` 硬规则（结论先行/标题即结论/
  禁拟人名词/类比≤1/坑写成表）+ em learn humanize 终检。**外部文风引擎一律不用**（S7-A
  调研结论：37 个候选全是实验级）；`ai_score.py` 只是**加签**——发布前机器体检，不重写不改稿
- 排版：vendor `wechat-publisher`（jiji262，MIT）`html_converter.py` + 15 套主题 JSON；
  技术教程默认 `minimal-mono`。发布线（官方 API）个人未认证号不可用，S7-A 实锤 → ego 自研
- 字数红线：公众号标题 ≤64、摘要 ≤120

## SOP（发布完一期 → 照表执行）

| 步 | 动作 | 预算 | 要点 |
|---|---|---|---|
| 1 收料核验 | 找齐三件：逐字稿/成片/字幕 srt | 1min | 逐字稿 vault transcripts 或用户给路径，**不自动猜**；成片+`<成片>_字幕.srt` 在 `embedai/视频/<期>/04_成片/`（逐字稿 frontmatter `sources` 指路）；缺哪件向用户要 |
| 2 写计划 | `blog_plan.json`（schema 见 `scripts/blog_plan.py` 模块注释） | 5min | 旁车落 `<成片>.blog_plan.json`；slug 只英文/数字/连字符；categories 恰 1 个；frames 4-8 张；跑 `python scripts/blog_plan.py --plan <f>` 校验过 |
| 3 选帧抽帧+人兜底 | `python scripts/frame_pick.py --plan <f> --site-root <SITE>` | 1min | 帧图落 `source/images/<slug>/NN-name.jpg` + 预览页 `<成片目录>/blog_preview/<slug>.html`；**把预览路径给用户过目**：换帧/删图/改 alt → 改 plan → `--force` 重抽 |
| 4 写文章 | `source/_posts/<slug>.md` | agent 主笔 | STYLE.md 硬规矩；图片 `![alt](/images/<slug>/NN-name.jpg)` 嵌在所属节尾；下载链接一律 `{% link "key" %}`（新 key 按 slug 嵌套段补进 `links.yml`，字段 key/label/url/extract_code/type/status/added） |
| 5 加签体检 | `python vendor/wechat-publisher/scripts/ai_score.py <post.md> --json` | 秒级 | 总分 ≥45 定点改（advisory 逐条过），改完重扫到过；低分≠像人，只是没踩已知坑 |
| 6 站点验收 | `python scripts/site_verify.py --post <md> --site-root <SITE> --commit "blog: <slug> 第N期图文版"` | 3-5min | 内部串 site_check（文件名/frontmatter/链接 key/图片存在）→ `npm run build` → `npm test` → **定点 add+commit**（只 add 本文章相关路径）。报错先看是不是动了首页类名/数量契约；改了 yml 页面没变=构建缓存，`npx hexo clean` |
| 7 公众号（点名才做） | 见「公众号节」 | 10min | gzh_pack 打包 → ego 驱动器存草稿 |

## 公众号节（S7-D：AI 干到存草稿，群发人工点）

1. 打包：`python scripts/gzh_pack.py --plan <f> --post <md> --site-root <SITE>
   --out <成片目录>/gzh_pack/` → `gzh.html`（占位符 `⟦图N:name⟧` 代替图）+ `images.json`
   （有序图片清单）+ `report.txt`（字数体检）
2. 驱动器：`ego-browser nodejs scripts/drivers/gzh.mjs`——头部 CONFIG 块按当期改
   （html/images.json/标题/作者/摘要/taskSpace 名 `blog-gzh-e<N>-<日期>`）；单进程跑完全程：
   登录态检查（扫码→handOff 交人）→ 新建图文 → 填标题/作者/摘要 → 粘贴正文富文本 →
   **逐张插图片**（定位占位段→删占位→编辑器图片按钮→setInputFiles→确认→等上传）→ 存草稿 →
   草稿箱确认可见 → 末尾必出 JSON（ok/elapsedSec/draftUrl/screenshots/blockers）+
   uncaughtException 兜底
3. 窗口契约同 publish：粘贴/上传图片阶段窗口需前台，其余随便最小化；动作间随机延时模拟人类
4. 用户手机预览草稿 → 用户自己点群发（**本技能终点=存草稿，绝不碰群发按钮**）

## 红线

- **不 `hexo deploy`**（备案关站期；上线动作用户手动）——验收终点=build+test 绿+commit
- **不点公众号群发**（存草稿是硬终点；群发不可撤回+每天限 1 次）
- 文风底盘不可替换：STYLE.md+humanize 是终检主体，ai_score.py 只是加签扫雷
- commit 只定点 add 本文章相关路径（`source/_posts/<slug>.md`+`source/images/<slug>/`+`links.yml`），
  **绝不 add -A**——站点仓库常有并行改动
- 文件名（文章 slug/帧图 name）只用英文/数字/连字符，中文出乱码 URL
- 收料不自动猜文件；验证码/异常弹窗 handOff 交人，不绕过不硬闯

## 产物约定（跟 publish 旁车惯例）

- `<成片>.blog_plan.json`：计划旁车，跟成片走
- `<成片目录>/blog_preview/<slug>.html`：选帧预览（人兜底界面）
- `<成片目录>/gzh_pack/{gzh.html,images.json,report.txt}`：公众号粘贴包
- `<SITE>/source/_posts/<slug>.md` + `<SITE>/source/images/<slug>/`：站点产物（commit 落库）
- `<SITE>` 仓库无 deploy 动作；公众号侧不留发布记录（草稿箱里躺着就是状态）

## 技术事实（避免重新踩坑）

- 选帧时间轴真源是 **`<成片>_字幕.srt`**（逐字稿 md 是拼好的纯文本无时间戳）；抽帧
  `-ss <t>` 放输入侧 + 单帧重编码 = 帧级精度；长边 1600px + `-q:v 3` 够正文图用
- vendor 目录结构**不可动**：html_converter 按 `parent.parent/assets/themes` 找主题；
  升级 vendor 按 `vendor/wechat-publisher/NOTICE.md` 清单重拷+跑冒烟测试
- 公众号编辑器不吃 md、不吃外链/本地 src 的 img（只吃自己 CDN）→ 内联样式 HTML + 逐张
  上传是唯一路；草稿箱 API 需认证公众号，**个人主体无法认证**（S7-A 实锤），别再试 API 线
- ai_score.py 是启发式 lint：advisory 是带行号的建议清单，处理完要在响应里说明改了什么
- 站点 e2e 红了先查首页类名/数量契约（`.post-card`×5、分类卡×4），不是内容问题就别乱改模板
