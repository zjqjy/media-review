#!/usr/bin/env python3
"""剪映草稿直出——第③层交接形态：不是粗片文件，是一个拼好的剪映草稿。

支持单段或多段：多段时按传入顺序把各素材的保留区间依次接在一条主轨上
（段间硬切，段内做词级挖洞+静音细剪）。字幕/标注 rebase 到全片时间轴。

阅读顺序规矩：素材文件名带序号（01_xx / 02_xx…），草稿按序号顺序加入；
无序号时按命令行传入顺序。

依赖：pip install pyJianYingDraft。
用法（单段）：
  python jy_draft.py 素材.mp4 剪切稿.srt --name 第N期_粗剪
用法（多段按序）：
  python jy_draft.py --seq "01素材.mp4=01剪切稿.srt" "02素材.mp4=02剪切稿.srt" --name 第N期_粗剪
"""

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

from srt_cut import build_spans, load_cuts, parse_srt, subtract_intervals
from silence_trim import detect_silences  # 区间内静音细剪用同一套检测

DRAFT_ROOT = Path.home() / "AppData/Local/JianyingPro/User Data/Projects/com.lveditor.draft"
RED = (1.0, 0.35, 0.35)


def make_annotations(entries, retakes=None):
    """从剪切稿条目自动出标注：[(start_s, end_s, 标签+摘句)]。

    规则（按需往这里加）：
    - 句内叠词（并将并将 / 等待一会儿等待一类） → [口吃·重说]
    - 重录对（retake_pairs）：已按用户规则保末遍挖前遍；标注保留供复核推翻
    （句首口头禅"然后"已由转录时词级剥离，不再进句子）
    """
    out = []
    for s, e, txt in entries:
        m = re.search(r"([\u4e00-\u9fff]{2})\1", txt)
        if m:
            brief = txt[:14] + ("…" if len(txt) > 14 else "")
            out.append((s, e, f"[口吃·重说「{m.group(1)}」] {brief}"))
    for p in (retakes or []):
        out.append((p["a_start"], p["a_start"] + 0.1,
                    f"🔁重录对已保B删A（sim={p['sim']}）B:{p['text_b'][:16]}——听错可换回"))
    return out


def rebase_srt(entries, spans, path):
    """源时间轴条目 → 成片时间轴 srt（按 spans 平移，与草稿主轨对齐）。

    精确匹配失败（句首落在被挖的洞里）→ 取最近区间端点（距离超 1s 丢弃并计数）。
    """
    def target_of(src_start):
        acc = 0.0
        for s, e in spans:
            if s - 0.001 <= src_start <= e + 0.001:
                return acc + (src_start - s)
            acc += e - s
        best, best_d = None, 1.0
        acc = 0.0
        for s, e in spans:
            if s <= src_start <= e:
                d = 0.0
                pos = acc + (src_start - s)
            else:
                d = min(abs(src_start - s), abs(src_start - e))
                pos = acc + min(max(src_start - s, 0), e - s)
            if d < best_d:
                best_d, best = d, pos
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
    dropped = 0
    for s, e, txt in entries:
        a, b = target_of(s), target_of(e)
        if a is None or b is None or b <= a:
            # 字幕落在被挖的洞里（短洞/口头禅）：钳到洞后最近保留点，不整条丢
            a2, b2 = target_of(e), target_of(e + 0.5)
            if a2 is None or b2 is None or b2 <= a2:
                dropped += 1
                continue
            a, b = a2, b2
        n += 1
        lines.append(f"{n}\n{fmt(a)} --> {fmt(b)}\n{txt}\n")
    if dropped:
        print(f"[jy_draft] 提示：{dropped} 条字幕完全落在挖洞区被跳过")
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    return n


def find_cuts_json(video: Path, srt: Path, explicit=None):
    """cuts.json 查找：显式 → 视频同目录 → srt 同目录（词干剥离 _剪切稿 后缀）
    → srt 同目录同素材前缀兜底。找不到返回 None 并警告（不静默）。"""
    if explicit:
        p = Path(explicit)
        return p if p.exists() else None
    srt_p = Path(srt)
    stems = [srt_p.stem, srt_p.stem.removesuffix("_剪切稿")]
    cands = [video.with_name(video.stem + ".cuts.json")]
    cands += [srt_p.with_name(st + ".cuts.json") for st in stems]
    cands += [p for p in sorted(srt_p.parent.glob("*.cuts.json"))
              if p.stem.startswith(stems[0].split("_trimmed")[0])]
    for cand in cands:
        if cand.exists():
            return cand
    return None


def process_segment(video: Path, cut_srt: Path, args, anno_offset=0.0):
    """单段处理：剪切稿 → 保留区间（挖洞+细剪）+ 源时间轴标注。

    返回 (material, spans, sub_entries, anno_entries)。
    依赖调用方已导入 pyJianYingDraft（VideoMaterial 为 main 注入的全局）。
    """
    entries = parse_srt(str(cut_srt))
    material = globals()["VideoMaterial"](str(video))
    total_s = material.duration / 1e6
    spans = build_spans(entries, total_s, args.pad, args.gap)
    n_coarse = len(spans)

    holes_total = 0
    retake_holes = []
    cuts_path = find_cuts_json(video, cut_srt, args.cuts if anno_offset == 0 else None)
    if args.no_cuts:
        cuts_path = None
    if cuts_path is None:
        print(f"[jy_draft] 警告：{video.name} 没找到 .cuts.json——词级洞（口头禅/重录前遍）不挖！"
              f"（查找过 视频同目录 和 {cut_srt.parent}）")
    else:
        holes = load_cuts(cuts_path)
        raw = json.loads(cuts_path.read_text(encoding="utf-8-sig"))
        retake_holes = [c for c in raw.get("fillers", [])
                        if isinstance(raw, dict) and c.get("word") == "🔁重录"]
        spans = subtract_intervals(spans, holes, pre_roll=0.3, keep=0.1)
        holes_total = len(holes)
        print(f"[jy_draft] {video.name}: 词级洞 {holes_total} 个")

    if args.min_inner > 0:
        silences, _ = detect_silences(str(video), args.db, args.min_inner)
        spans = subtract_intervals(spans, silences, keep=0.2, min_cut=0.5)
        print(f"[jy_draft] {video.name}: 静音细剪 {n_coarse} → {len(spans)} 段")

    # 字幕/标注 rebase 到本段成片时间轴（调用方再加段偏移）
    with tempfile.TemporaryDirectory() as td:
        sub = Path(td) / "sub.srt"
        n_sub = rebase_srt(entries, spans, sub)
        sub_entries = parse_srt(str(sub)) if n_sub else []
        anno = make_annotations(entries)  # 叠词类标注（源时间轴）
        for h in retake_holes:
            anno.append((h["start"] / 1000, h["start"] / 1000 + 0.1,
                         f"🔁重录对已保B删A B:{h.get('retake_of', '')[:16]}"))
        anno_entries = []
        if anno:
            ann = Path(td) / "anno.srt"
            n_anno = rebase_srt(anno, spans, ann)
            if n_anno:
                anno_entries = parse_srt(str(ann))

    return material, spans, sub_entries, anno_entries, {"holes": holes_total}


def main():
    ap = argparse.ArgumentParser(description="剪映草稿直出（主轨保留段+字幕轨+标注轨，支持多段按序）")
    ap.add_argument("video", nargs="?", default=None, help="单段模式：视频")
    ap.add_argument("cut_srt", nargs="?", default=None, help="单段模式：剪切稿 srt")
    ap.add_argument("--seq", nargs="*", default=None,
                    help='多段模式：按顺序 "视频=剪切稿" 列表（素材按序号命名，草稿按序拼）')
    ap.add_argument("--draft-folder", default=str(DRAFT_ROOT))
    ap.add_argument("--name", default=None)
    ap.add_argument("--pad", type=float, default=0.2)
    ap.add_argument("--gap", type=float, default=0.4)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--min-inner", type=float, default=0.8,
                    help="区间内静音细剪阈值（秒），0=关闭细剪")
    ap.add_argument("--db", type=float, default=-35, help="静音判定阈值 dB")
    ap.add_argument("--cuts", default=None, help="口头禅洞 .cuts.json（单段模式）")
    ap.add_argument("--no-cuts", action="store_true", help="不做词级跳剪")
    args = ap.parse_args()

    # 组装段列表 [(video, cut_srt)]
    segs = []
    if args.seq:
        for item in args.seq:
            if "=" not in item:
                sys.exit(f"--seq 格式应为 视频=剪切稿：{item}")
            v, s = item.split("=", 1)
            segs.append((Path(v), Path(s)))
    else:
        if not args.video or not args.cut_srt:
            sys.exit("需要 video cut_srt 或 --seq")
        segs.append((Path(args.video), Path(args.cut_srt)))
    # 顺序规矩：严格按命令行传入顺序拼轨（素材文件建议带序号命名，由调用方负责顺序）
    try:
        from pyJianYingDraft import (ClipSettings, DraftFolder, TextStyle,
                                     Timerange, TrackSpec, TrackType,
                                     VideoMaterial, VideoSegment)
        globals()["VideoMaterial"] = VideoMaterial
    except ImportError:
        sys.exit("缺依赖：pip install pyJianYingDraft")

    first_video = segs[0][0]
    folder = Path(args.draft_folder)
    if not folder.exists():
        sys.exit(f"剪映草稿目录不存在：{folder}（剪映全局设置→草稿位置，用 --draft-folder 指定）")
    name = args.name or f"media_cut_{first_video.stem}_粗剪"

    probe = VideoMaterial(str(first_video))
    script = DraftFolder(str(folder)).create_draft(
        name, probe.width, probe.height, fps=args.fps, allow_replace=True)
    script.append_track(TrackSpec(TrackType.video, name="主轨"))

    t_us = 0
    all_sub, all_anno = [], []
    for video, cut_srt in segs:
        if not video.exists():
            sys.exit(f"素材不存在：{video}")
        if not cut_srt.exists():
            sys.exit(f"剪切稿不存在：{cut_srt}")
        material, spans, sub_entries, anno_entries, info = process_segment(video, cut_srt, args)
        print(f"[jy_draft] {video.name}: 主轨 {len(spans)} 段，字幕 {len(sub_entries)}，标注 {len(anno_entries)}")
        seg_start_us = t_us
        for s, e in spans:
            seg = VideoSegment(
                material,
                target_timerange=Timerange(t_us, int((e - s) * 1e6)),
                source_timerange=Timerange(int(s * 1e6), int((e - s) * 1e6)))
            script.add_segment(seg, track="主轨")
            t_us += int((e - s) * 1e6)
        seg_off = seg_start_us / 1e6
        all_sub += [(a + seg_off, b + seg_off, txt) for a, b, txt in sub_entries]
        all_anno += [(a + seg_off, b + seg_off, txt) for a, b, txt in anno_entries]

    # 多段拼接边界处相邻字幕可能交叠（剪映文本轨不允许），全局按时间排序+去重叠
    def dedup(entries_list):
        out = []
        for a, b, txt in sorted(entries_list, key=lambda x: x[0]):
            if out and a < out[-1][1]:
                a = out[-1][1] + 0.001
                if b <= a:
                    continue
            out.append((a, b, txt))
        return out

    all_sub, all_anno = dedup(all_sub), dedup(all_anno)

    if not all_sub:
        sys.exit("所有段的字幕 rebase 后为空——检查剪切稿时间戳是否与素材匹配")

    with tempfile.TemporaryDirectory() as td:
        def write_srt(entries, path):
            def fmt(t):
                ms = int(round(t * 1000))
                h, rem = divmod(ms, 3600000)
                m, rem = divmod(rem, 60000)
                s, ms2 = divmod(rem, 1000)
                return f"{h:02d}:{m:02d}:{s:02d},{ms2:03d}"
            lines = []
            for i, (a, b, txt) in enumerate(entries, 1):
                lines.append(f"{i}\n{fmt(a)} --> {fmt(b)}\n{txt}\n")
            Path(path).write_text("\n".join(lines), encoding="utf-8")

        write_srt(all_sub, Path(td) / "sub.srt")
        script.import_srt(str(Path(td) / "sub.srt"), "字幕")
        if all_anno:
            write_srt(all_anno, Path(td) / "anno.srt")
            script.import_srt(str(Path(td) / "anno.srt"), "标注",
                              text_style=TextStyle(size=5, color=RED, bold=True, align=1),
                              clip_settings=ClipSettings(transform_y=0.8))
    script.save()

    # pyJianYingDraft 模板 draft_id 固定，多草稿同 ID 会干扰剪映定位——随机化
    meta_path = folder / name / "draft_meta_info.json"
    import uuid
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["draft_id"] = str(uuid.uuid4()).upper()
    meta["draft_name"] = name
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=4), encoding="utf-8")

    kept = t_us / 1e6
    print(f"[jy_draft] 草稿已生成：{folder / name}")
    print(f"  {len(segs)} 段素材按序拼接，主轨总时长 {int(kept // 60)}:{int(kept % 60):02d}")
    print(f"  字幕轨 {len(all_sub)} 条；标注轨 {len(all_anno)} 条（红色置顶，导出前删掉该轨）")
    print("  打开剪映专业版，草稿列表里直接可见")


if __name__ == "__main__":
    main()
