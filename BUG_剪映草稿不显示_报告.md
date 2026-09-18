# BUG 报告：jy_draft.py 生成的剪映草稿不出现在剪映草稿列表

> 日期：2026-09-19 ｜ 来源：media skill cut 第③层实际使用中暴露 ｜ 待修位置：本仓 `skill/media/cut/scripts/jy_draft.py`

## 一句话摘要

脚本把草稿目录写进了剪映草稿根目录，但新版剪映的草稿列表读的是根目录的 `root_meta_info.json` **注册表**——脚本只建目录、不登记索引，草稿就是"隐形"的。

## 环境事实

| 项 | 值 |
|---|---|
| 触发命令 | `python jy_draft.py 写代码_trimmed.mp4 写代码_剪切稿.srt --cuts ... --name media_cut_写代码点灯_粗剪 --fps 60`（退出码 0） |
| 脚本 | 本仓 `skill/media/cut/scripts/jy_draft.py`（已安装到 `C:\Users\23393\.zcode\skills\media\cut\scripts\`） |
| 依赖 | pyJianYingDraft **0.3.0**（`pip show pyjianyingdraft`） |
| 草稿根目录 | `C:\Users\23393\AppData\Local\JianyingPro\User Data\Projects\com.lveditor.draft`（脚本的 `DRAFT_ROOT` 默认值） |
| 生成的草稿 | `media_cut_写代码点灯_粗剪`：`draft_content.json`(352KB) + `draft_meta_info.json`。content 本身合法（new_version "110.0.0"、fps 60、duration 246241435µs = 4:06） |
| 剪映 | 新版（索引条目 draft_new_version "164.0.0"；会把自己打开过的草稿 meta 改写成自有混淆格式） |

## 复现步骤

1. 跑 `jy_draft.py` 生成草稿（脚本打印"草稿已生成"，磁盘上目录确实存在）
2. 打开剪映专业版看首页草稿列表
3. **看不到该草稿**（无任何报错）

## 证据 → 根因

1. 草稿根目录存在 `root_meta_info.json`，结构 `{all_draft_store: [条目...], draft_ids: 4, root_path: "..."}`，登记了 5 条：`media_cut_屏幕驱动开头_粗剪v5`、`9月15日`、`9月13日`、`9月10日`、`5月2日`——**不含**新生成的 `media_cut_写代码点灯_粗剪`
2. 草稿根目录里另有 4 个历史测试目录 `testdbg / testdbg3 / testdbg5 / testdbg7`，同样**不在索引里**——证明外部裸目录不会被剪映自动扫描登记（排除"重启剪映就会显示"的假设）
3. v5 在索引里所以能显示；它的 `draft_meta_info.json` 已被剪映改写成非 JSON 的混淆文本（开头 `f87a1VY27...`），目录下多出 `Timelines/`、`Resources/`、`draft_cover.jpg` 等——即它是**被剪映打开过一次后**由剪映登记并改写的
4. pyJianYingDraft 0.3.0 的 `script.save()` 只写草稿目录本身；`jy_draft.py` 手写 `draft_meta_info.json`（当前 `jy_draft.py:284-289`）后流程结束——**全程无人碰根索引**

**结论：新版剪映以 `root_meta_info.json` 为草稿注册表，不扫描目录。外部工具生成草稿必须主动登记。**

## 修复方案（改本仓 `jy_draft.py`，做成流程固定步骤，不是一次性补丁）

在 `script.save()` + 手写 `draft_meta_info.json` 之后（`jy_draft.py:281-289` 附近）新增"根索引登记"：

1. 读 `<DRAFT_ROOT>/root_meta_info.json`（utf-8）；**文件不存在则跳过登记**（老版剪映靠目录扫描，不需要登记）
2. 构造条目追加进 `all_draft_store`，字段以能正常显示的 v5 条目为模板（完整样例见附录 A）：
   - `draft_id`：取刚写出的 `draft_meta_info.json` 里的 `draft_id`，保持原大小写格式
   - `draft_fold_path`：`{root}/{name}`；`draft_json_file`：`{root}/{name}/draft_content.json`（样例里是正斜杠+末段反斜杠的混合，照抄即可）
   - `draft_root_path`：草稿根目录（反斜杠形式）
   - `draft_name`：草稿名；`draft_new_version`：取 `draft_content.json` 的 `new_version`
   - `tm_draft_create` / `tm_draft_modified`：**微秒级 Unix 时间戳**（样例 1789749910362100 ≈ 2026-09-19，注意不是毫秒）
   - `tm_duration`：微秒，取 `draft_content.json` 的 `duration`
   - `draft_timeline_materials_size`：引用素材字节数（信息性，估算即可）
   - 其余布尔/占位字段（`cloud_*`、`pippit_*`、`streaming_edit_draft_ready`、`tm_draft_cloud_*` 等）照附录 A 样例填默认值
   - `draft_cover`：v5 指向真实 jpg；脚本生成的草稿没有封面——先试空字符串，若列表不认则用 ffmpeg 从素材首帧抽一张存 `{root}/{name}/draft_cover.jpg`（兜底）
3. `draft_ids` 语义未确证（当前是数字 `4`，而 `all_draft_store` 有 5 条）——**别按"条数±1"猜着改**：保持原值不动，登记后用剪映实测；确证前不加逻辑
4. 顺带把刚手写的 `draft_meta_info.json` 里空着的 `draft_fold_path`、`draft_root_path` 回填（当前为 `""`）
5. 写回前把 `root_meta_info.json` 备份为 `.bak`；**只在剪映未运行时写**（剪映退出时会重写索引，运行中改会被覆盖）——检测 JianyingPro 进程，在则报警跳过并在输出里提示"关闭剪映后重跑"
6. 写回格式：utf-8 无 BOM，`ensure_ascii=False`，保持与现文件一致的可读性

## 修复期间的新证据（2026-09-19 手动登记时实测）

- 手动登记完成后实测：`draft_ids` 从 4 变 6（期间用户开/关过一次剪映，脚本未动该字段）——**剪映退出重写索引时会自己维护 `draft_ids` 并对齐条目数**，且此时会把磁盘上"结构完整的外部草稿目录"（有合法 draft_content.json + draft_meta_info.json）登记进去（testdbg* 仍被排除，推测因目录结构不完整）。修复方案里的登记步骤仍应保留：不能依赖"用户先开/关一轮剪映"才生效，主动登记才是确定性行为；但 `draft_ids` 可以放心在登记后同步 +1（实测剪映接受，未造成异常）
- 手动登记条目 + ffmpeg 抽帧封面后，草稿在剪映列表正常显示（本条即验收通过样例）

## 验收标准

1. 关闭剪映 → 跑 `jy_draft.py` → 打开剪映：草稿列表**直接可见**新草稿，零手动操作
2. 点开草稿：主轨段数/时长与脚本输出一致，字幕轨、红色标注轨完整，能播放
3. 既有 5 条索引记录完好，其余草稿不受影响（`draft_meta_info.json` 被剪映改写成混淆格式属正常，不算回归）
4. 本仓 `tests/` 加单测：fixture 造一个 `root_meta_info.json` + 假草稿目录，断言登记后字段完整、原条目未丢、`draft_ids` 未被误改

## 临时绕过（修脚本前的手动解法）

把附录 A 的条目模板补进 `root_meta_info.json` 的 `all_draft_store`（`draft_id`/路径/名称换成新草稿的值）即可。另一条路：若你的剪映版本首页有"本地草稿/导入草稿"入口，用它选中新草稿目录，导入后剪映会自己登记——但每次生成都要手动导，治标不治本。

## 附录 A：索引条目模板（来自能正常显示的 v5）

```json
{
 "cloud_draft_cover": false,
 "cloud_draft_sync": false,
 "draft_cloud_last_action_download": false,
 "draft_cloud_purchase_info": "",
 "draft_cloud_template_id": "",
 "draft_cloud_tutorial_info": "",
 "draft_cloud_videocut_purchase_info": "",
 "draft_cover": "<root>/<name>/draft_cover.jpg",
 "draft_fold_path": "<root>/<name>",
 "draft_id": "B7CADABF-FA72-462d-85D6-F19886518869",
 "draft_is_ai_shorts": false,
 "draft_is_cloud_temp_draft": false,
 "draft_is_infinite_canvas_draft": false,
 "draft_is_invisible": false,
 "draft_is_pippit_draft": false,
 "draft_is_web_article_video": false,
 "draft_json_file": "<root>/<name>/draft_content.json",
 "draft_name": "media_cut_屏幕驱动开头_粗剪v5",
 "draft_new_version": "164.0.0",
 "draft_root_path": "<root 反斜杠形式>",
 "draft_timeline_materials_size": 38480052,
 "draft_type": "",
 "draft_web_article_video_enter_from": "",
 "pippit_avatar_url": "",
 "pippit_extra_info": "",
 "pippit_id": "",
 "pippit_user_name": "",
 "streaming_edit_draft_ready": true,
 "tm_draft_cloud_completed": "",
 "tm_draft_cloud_entry_id": -1,
 "tm_draft_cloud_modified": 0,
 "tm_draft_cloud_parent_entry_id": -1,
 "tm_draft_cloud_space_id": -1,
 "tm_draft_cloud_user_id": -1,
 "tm_draft_create": 1789749910362100,
 "tm_draft_modified": 1789750113553446,
 "tm_draft_removed": 0,
 "tm_duration": 55166666
}
```

## 附录 B：本次涉事的具体值

- `<root>` = `C:\Users\23393\AppData\Local\JianyingPro\User Data\Projects\com.lveditor.draft`
- 待登记草稿：`media_cut_写代码点灯_粗剪`，`draft_id = 75915113-DE2E-4A1C-9815-5CBF7187868A`（取自其 `draft_meta_info.json`），`new_version = "110.0.0"`，`duration = 246241435`（µs，即 4:06.24）
- 脚本落盘代码位置：`jy_draft.py:281`（`script.save()`）与 `jy_draft.py:284-289`（手写 `draft_meta_info.json`），登记步骤应插在其后
- 素材引用：草稿主轨引用 `D:\DeskTop\WorkSpace\embedai\视频\20260913_ESP32环境搭建\写代码_trimmed.mp4`（44 段，77 字幕，5 标注）
