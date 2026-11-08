# vendor: wechat-publisher（jiji262）引入件

- 上游: https://github.com/jiji262/wechat-publisher
- 引入 commit: 24358951c467410df34a822fdab19a80005841ce（2026-11-08 浅克隆）
- 许可: 上游 README 声明 MIT（仓库内无独立 LICENSE 文件，以 README 声明为准）
- 引入范围: `scripts/` 11 个 py + `_humanizer_lexicon.json`（ai_score.py 依赖闭包，含 --json
  分支的 article_meta.py）+ `assets/themes/` 15 套公众号主题 JSON（html_converter.py 按
  `parent.parent/assets/themes` 解析，目录结构不可动）
- 用途: ①`html_converter.py` md→公众号内联样式 HTML（S7-D 排版层）②`ai_score.py` AI 味
  lint 加签器（S7-B 文章终检加签，threshold 45，只扫雷不改稿）
- 未引入: 自动创作/发布线（publish.py 等走官方 API，个人未认证号不可用——见 research-S7-A.md）
- 升级方式: 重克隆上游→按本清单范围重新拷贝→跑 tests/test_blog_pipeline.py 的 vendor 冒烟
