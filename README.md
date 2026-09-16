# media-review

自媒体发布后数据复盘的 Claude Code skill。B站全自动取数，抖音/小红书截图收件箱，复盘结论按"爆款公式"归因并回写 Obsidian 知识库。

## 为什么

视频发出去之后没有系统复盘：不知道哪条行、为什么行、下条改什么。人工看数据凭感觉，没有沉淀。media-review 把复盘变成一个固定动作：

```
/media-review
   │
   ├─ B站：创作中心接口自动拉数据（自己的账号，自己的 Cookie）
   ├─ 抖音/小红书：截图贴进收集窗，Claude 识图提取
   │
   ▼  三要素归因（爆款 = 选题 × 素材 × 内容）
   │
   └─ 复盘报告 → Obsidian vault → 确认后写回选题池/复用片段/对标
```

## 安装

```powershell
git clone https://github.com/zjqjy/media-review.git
cd media-review
.\install.ps1
```

然后按提示配置 B站登录——二选一：

- **扫码（推荐）**：`python skill/media-review/scripts/fetch_bili.py login --config "<vault>\20_自媒体\复盘\_config_local.json"`，二维码自动弹出，B站 App 扫一下即自动写入
- **手动**：把 `_config_local.example.json` 复制为 `_config_local.json`，B站网页 F12 → Application → Cookies → 复制 SESSDATA 粘进去

## 使用

在 Claude Code 里喊 `/media-review`，skill 会：

1. 清算所有"今天到期"的观察点（发布后 D+3 / D+7 / D+30）
2. B站视频自动拉取数据；抖音/小红书拉起截图收集窗，把创作中心截图贴进去即可
3. 输出三要素归因 + 下条可执行改动（最多 3 条）
4. 给出"建议写回"清单，你确认后才写入选题池/复用片段/对标笔记

## 合规说明

- 只通过 B站创作中心接口读取**自己账号**的数据（Cookie 鉴权，与浏览器登录同源），不爬取任何他人内容
- 抖音/小红书数据来自**官方创作中心的截图**，人工手动提供，无任何自动化访问
- Cookie 保存在本地 gitignore 文件中，不出现在任何入库文件和网络传输（仅发往 B站官方接口）
