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

from srt_cut import build_spans, load_cuts, parse_srt, subtract_intervals
from silence_trim import detect_silences  # 区间内静音细剪用同一套检测

DRAFT_ROOT = Path.home() / "AppData/Local/JianyingPro/User Data/Projects/com.lveditor.draft"
RED = (1.0, 0.35, 0.35)


def make_annotations(entries):
    """从剪切稿条目自动出标注：[(start_s, end_s, 标签+摘句)]。

    规则（按需往这里加）：
    - 句内叠词（并将并将 / 等待一会儿等待一类） → [口吃·重说]
    （句首口头禅"然后"已由转录时词级剥离，不再进句子）
    """
    out = []
    for s, e, txt in entries:
        tags = []
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
        best, best_d = None, 1.0
        acc = 0.0
        for s, e in spans:
            if s - 0.001 <= src_start <= e + 0.001:
                return acc + (src_start - s)
            acc += e - s
        # 精确匹配失败（句首落在被细剪的静音里）→ 取最近区间，距离超 1s 才丢
        acc = 0.0
        for s, e in spans:
            d = min(abs(src_start - s), abs(src_start - e))
            if src_start > s and src_start < e:
                d = 0.0
            if d < best_d:
                best_d = d
                best = acc + min(max(src_start - s, 0), e - s)
            acc += e - s
        return best

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
    if n < len(entries):
        print(f"[jy_draft] 提示：{len(entries) - n} 条字幕因时间戳落在细剪区外被跳过")
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
    ap.add_argument("--min-inner", type=float, default=0.8,
                    help="区间内静音细剪阈值（秒），0=关闭细剪")
    ap.add_argument("--db", type=float, default=-35, help="静音判定阈值 dB")
    ap.add_argument("--cuts", default=None,
                    help="口头禅洞 .cuts.json，默认自动找与视频同名的")
    ap.add_argument("--no-cuts", action="store_true", help="不做词级口头禅跳剪")
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
    n_coarse = len(spans)

    # 词级跳剪：句首口头禅洞（转录自动产出，与视频同名 .cuts.json）
    cuts_path = Path(args.cuts) if args.cuts else \
        video.with_name(video.stem + ".cuts.json")
    if (args.no_cuts or not cuts_path.exists()) and args.cuts is None:
        cuts_path = None
    if cuts_path:
        holes = load_cuts(cuts_path)
        spans = subtract_intervals(spans, holes)
        print(f"[jy_draft] 词级跳剪：挖掉 {len(holes)} 个口头禅"
              f"（{cuts_path.name}）")

    if args.min_inner > 0:
        silences, _ = detect_silences(str(video), args.db, args.min_inner)
        spans = subtract_intervals(spans, silences, keep=0.2, min_cut=0.5)
        print(f"[jy_draft] 区间内静音细剪：{n_coarse} 段 → {len(spans)} 段"
              f"（阈值 {args.min_inner}s/{args.db}dB）")

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

    # pyJianYingDraft 模板的 draft_id 是固定值，多个草稿同 ID 会干扰剪映的草稿定位——逐个随机化
    meta_path = folder / name / "draft_meta_info.json"
    import json
    import uuid
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["draft_id"] = str(uuid.uuid4()).upper()
    meta["draft_name"] = name
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=4), encoding="utf-8")

    kept = sum(e - s for s, e in spans)
    print(f"[jy_draft] 草稿已生成：{folder / name}")
    print(f"  主轨 {len(spans)} 段，成片约 {int(kept // 60)}:{int(kept % 60):02d}（源素材 {total_us / 6e7:.1f} 分钟）")
    print(f"  字幕轨 {n} 条；标注轨 {len(anno)} 条（口头禅/口吃，红色置顶，导出前删掉该轨即可）")
    print("  打开剪映专业版，草稿列表里直接可见")


if __name__ == "__main__":
    main()
