#!/usr/bin/env python3
"""剪映草稿直出——第③层交接形态升级：不是粗片文件，是一个拼好的剪映草稿。

主视频轨 = 剪切稿的全部保留区间（引用原素材 source_timerange，不重编码零损失，
剪切点在剪映里仍是可拖动的分割线）；文本轨 1 = 字幕（剪切稿 rebase 到成片时间轴）；
文本轨 2 = 标注（红字置顶：句首口头禅"然后"、句内叠词口吃——第②层删不掉、留给精剪的点）。

依赖：pip install pyJianYingDraft（轻量，含 pymediainfo）。
打开方式：剪映专业版 → 首页草稿列表直接出现（草稿写到剪映的草稿目录）。

用法：
  python jy_draft.py 素材.mp4 剪切稿.srt
  python jy_draft.py 素材.mp4 剪切稿.srt --draft-folder "C:/.../com.lveditor.draft" --name 第2期_环境搭建_粗剪
  参数：
    --pad 0.2 / --gap 0.4   与 srt_cut 相同的区间合并规则（两边草稿和粗片要对得上就别乱改）
"""

import argparse
import re
import sys
import tempfile
from pathlib import Path

from srt_cut import build_spans, parse_srt  # 同目录，同一套区间数学

DRAFT_ROOT = Path.home() / "AppData/Local/JianyingPro/User Data/Projects/com.lveditor.draft"
FILLER = "然后"  # 口头禅：句首匹配（用户点名要标）
RED = (1.0, 0.35, 0.35)


def make_annotations(entries):
    """从剪切稿条目自动出标注：[(start_s, end_s, 标签+摘句)]。

    规则（按需往这里加）：
    - 句首"然后" → [口头禅·然后]
    - 句内叠词（并将并将 / 等待一会儿等待一类） → [口吃·重说]
    """
    out = []
    for s, e, txt in entries:
        tags = []
        if txt.startswith(FILLER):
            tags.append(f"口头禅·{FILLER}")
        m = re.search(r"([\u4e00-\u9fff]{2})\1", txt)
        if m:
            tags.append(f"口吃·重说「{m.group(1)}」")
        if tags:
            brief = txt[:14] + ("…" if len(txt) > 14 else "")
            out.append((s, e, f"[{'|'.join(tags)}] {brief}"))
    return out


def rebase_srt(entries, spans, path):
    """源时间轴条目 → 成片时间轴 srt（按 spans 平移，与剪出来的粗片对齐）。"""
    def target_of(src_start):
        acc = 0.0
        for s, e in spans:
            if s - 0.001 <= src_start <= e + 0.001:
                return acc + (src_start - s)
            acc += e - s
        return None

    def fmt(t):
        ms = int(round(t * 1000))
        h, rem = divmod(ms, 3600000)
        m, rem = divmod(rem, 60000)
        s, ms2 = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms2:03d}"

    lines = []
    n = 0
    for s, e, txt in entries:
        a, b = target_of(s), target_of(e)
        if a is None or b is None:
            continue
        n += 1
        lines.append(f"{n}\n{fmt(a)} --> {fmt(b)}\n{txt}\n")
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    return n


def main():
    ap = argparse.ArgumentParser(description="剪映草稿直出（主轨保留段+字幕轨+标注轨）")
    ap.add_argument("video")
    ap.add_argument("cut_srt")
    ap.add_argument("--draft-folder", default=str(DRAFT_ROOT))
    ap.add_argument("--name", default=None)
    ap.add_argument("--pad", type=float, default=0.2)
    ap.add_argument("--gap", type=float, default=0.4)
    ap.add_argument("--fps", type=int, default=30)
    args = ap.parse_args()

    try:
        from pyJianYingDraft import (ClipSettings, DraftFolder, TextSegment,
                                     TextStyle, Timerange, TrackSpec, TrackType,
                                     VideoMaterial, VideoSegment)
    except ImportError:
        sys.exit("缺依赖：pip install pyJianYingDraft")

    video = Path(args.video)
    entries = parse_srt(args.cut_srt)

    material = VideoMaterial(str(video))
    total_us = material.duration
    spans = build_spans(entries, total_us / 1e6, args.pad, args.gap)

    folder = Path(args.draft_folder)
    if not folder.exists():
        sys.exit(f"剪映草稿目录不存在：{folder}（剪映全局设置→草稿位置 里看实际路径，用 --draft-folder 指定）")
    name = args.name or f"media_cut_{video.stem}_粗剪"

    script = DraftFolder(str(folder)).create_draft(
        name, material.width, material.height, fps=args.fps, allow_replace=True)
    script.append_track(TrackSpec(TrackType.video, name="主轨"))

    t = 0
    for s, e in spans:
        seg = VideoSegment(
            material,
            target_timerange=Timerange(t, int((e - s) * 1e6)),
            source_timerange=Timerange(int(s * 1e6), int((e - s) * 1e6)))
        script.add_segment(seg, track="主轨")
        t += int((e - s) * 1e6)

    with tempfile.TemporaryDirectory() as td:
        sub_srt = Path(td) / "sub.srt"
        n = rebase_srt(entries, spans, sub_srt)
        script.import_srt(str(sub_srt), "字幕")
        anno = make_annotations(entries)
        if anno:
            anno_srt = Path(td) / "anno.srt"
            na = rebase_srt(anno, spans, anno_srt)
            script.import_srt(str(anno_srt), "标注",
                              text_style=TextStyle(size=5, color=RED, bold=True, align=1),
                              clip_settings=ClipSettings(transform_y=0.8))
    script.save()

    kept = sum(e - s for s, e in spans)
    print(f"[jy_draft] 草稿已生成：{folder / name}")
    print(f"  主轨 {len(spans)} 段，成片约 {int(kept // 60)}:{int(kept % 60):02d}（源素材 {total_us / 6e7:.1f} 分钟）")
    print(f"  字幕轨 {n} 条；标注轨 {len(anno)} 条（口头禅/口吃，红色置顶，导出前删掉该轨即可）")
    print("  打开剪映专业版，草稿列表里直接可见")


if __name__ == "__main__":
    main()
