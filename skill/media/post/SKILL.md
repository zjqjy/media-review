---
name: post
description: media 子技能：发前后处理。由 media 门面路由进入——定稿成片 → 字幕 + 响度统一 + 发布前量测报告。粗剪归 cut，精剪归剪映，这里管导出成片之后的最后一步。
---

# post · 发前后处理

成片定稿（剪映导出 mp4）→ 字幕 + 响度统一 → 发布。定位：机器能标准化的都放这里，品味判断（BGM/花字/加速）留在精剪域。

## 标准流程（拿到定稿成片 → 照表执行）

| 步 | 动作 | 预算 | 要点 |
|---|---|---|---|
| 1 字幕 | `python scripts/final_sub.py 成片.mp4` | 转录约 1/10 成片时长 | 转录→自动套 asr_fixes 错拼表→`<成片>_字幕.srt`；技术词多加 `--hotword "词1 词2"`；剪映媒体面板导入 |
| 2 响度 | `python scripts/loudnorm.py 成片.mp4 [-I -14]` | 秒级（视频流 copy） | EBU R128 两遍法，实测值线性回写；缺省 -16 LUFS/TP -1.5，抖音竖版可 -14；输出 `<成片>_响度.mp4` |
| 3 字幕草稿 | `python scripts/draft_sub.py <成片>_响度.mp4 [--retire 粗剪草稿名]` | 秒级 | 想**回剪映继续编辑**就用这个：响度成片整段上主轨+字幕轨直接建好（样式同 cut 粗剪草稿）；不想回剪映就跳过，直接用 mp4+srt |

**草稿生命周期**（防草稿列表堆积，且有保险丝）：粗剪草稿**没人动过**（管线刚出、没在剪映里打开过）→ 可 `--retire` 退场，工作区剪切稿随时秒级重出；**精剪过的不退**——精剪操作全做在粗剪草稿里，且剪映打开即加密、管线读不回，动过的粗剪草稿是精剪成果的唯一载体。`--retire` 内建 draft_touched_by_user 检查，动过的自动跳过并提示。
| 4 量测 | `python scripts/loudnorm.py 成片.mp4 --measure` | 秒级 | 只出报告不改文件：时长/分辨率/实测 LUFS/LRA/真峰值——发布前体检用 |

## 技术事实（避免重新踩坑）

- **零重编码**：loudnorm `-c:v copy` 只动音轨（aac 192k），画质无损、速度快两个数量级——和 cut 的零重编码哲学一致
- **loudnorm 两遍法**：第一遍量测 input_I/TP/LRA/thresh，第二遍 linear=true 带实测值回写，比单遍动态模式少一刀动态处理
- **ffmpeg 定位**：PATH 优先，退 imageio_ffmpeg 自带二进制（与 cut 的 silence_trim 同一套逻辑）
- **字幕错拼**：asr_fixes.json 在 cut 目录，final_sub 从 select.py 借 load_global_fixes——新错拼沉淀仍写那份表
- 字幕样式不在这一步定：srt 导入剪映后由剪映排版（粗剪字幕轨的样式常量在 cut/jy_draft.py，导成片后要硬字幕就在剪映里调）

## 红线

- 只处理用户自己导出的成片，不加任何爬取/下载能力
- 不重编码视频流；不替用户做加 BGM/花字等品味判断
- 热词/错拼沉淀回 cut 的表，不在 post 另立一份
