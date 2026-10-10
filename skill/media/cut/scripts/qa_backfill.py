#!/usr/bin/env python3
"""qa_backfill——把成片复核(QA)发现的残留条目回补进初选决定。

原理：QA 转录稿的时间轴是"成片时间"，与剪切稿（原始素材时间轴）对不上；
文本又经过二次 ASR 噪声不可靠。本脚本按 srt_cut 同款参数重建裁剪区间
（剪切稿 spans → 词级洞 → 静音细剪），把成片时间反演回原素材时间，
落位到新转录稿条目，把删除项写进决定碎片（带锚字，dry 可验）。

用法：python qa_backfill.py <待粗剪目录> <段名> <QA成片稿.srt> <残留条目号...>
      [--fragment 初选决定_<段名>.json]
例：  python qa_backfill.py 长/待粗剪 环境搭建 长/待粗剪/_QA/环境搭建_粗剪.srt 4 5 6 10 15
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from srt_cut import (build_spans, detect_silences, find_cuts_json, load_cuts,
                     parse_srt as parse_srt_plain, subtract_intervals)
import re


def parse_srt_with_idx(p):
    """(idx, start_ms, end_ms, text)——QA 稿按条目号定位，要带序号的解析。"""
    ents = []
    for b in Path(p).read_text(encoding="utf-8-sig").split("\n\n"):
        L = b.strip().splitlines()
        if len(L) >= 3 and L[0].strip().isdigit():
            m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+) --> (\d+):(\d+):(\d+)[,.](\d+)", L[1])
            if not m:
                continue
            g = [int(x) for x in m.groups()]
            ents.append((int(L[0]),
                         g[0] * 3600000 + g[1] * 60000 + g[2] * 1000 + g[3],
                         g[4] * 3600000 + g[5] * 60000 + g[6] * 1000 + g[7],
                         "\n".join(L[2:])))
    return ents


def find_fragment(ws: Path, seg: str, explicit: str | None) -> Path:
    """碎片定位：显式指定 → 含该段键的任意 初选决定_*.json。"""
    tool = ws / "_工具"
    if explicit:
        p = tool / explicit
        if not p.exists():
            sys.exit(f"qa_backfill: 碎片不存在 {p}")
        return p
    for f in sorted(tool.glob("初选决定_*.json")):
        try:
            if seg in json.loads(f.read_text(encoding="utf-8")):
                return f
        except Exception:
            continue
    sys.exit(f"qa_backfill: {tool} 下没有含段「{seg}」的碎片")


def cut_to_source_map(ws: Path, seg: str):
    """重建该段的成片区间，返回 [(cut_start, cut_end, src_start, src_end)]。"""
    video = ws / "1_原始" / f"{seg}.mp4"
    cut_srt = ws / "3_转录初选" / f"{seg}_剪切稿.srt"
    entries = parse_srt_plain(str(cut_srt))
    from silence_trim import duration_of
    dur = duration_of(video)
    spans = build_spans(entries, dur, 0.2, 0.4)
    cuts_path = find_cuts_json(video, cut_srt)
    if cuts_path:
        spans = subtract_intervals(spans, load_cuts(cuts_path), pre_roll=0.3, keep=0.1)
    silences, _ = detect_silences(str(video), None, 0.8)  # 与 srt_cut 同款智能模式，成片区间映射才对得上
    spans = subtract_intervals(spans, silences, keep=0.2, min_cut=0.5)
    out, acc = [], 0.0
    for s, e in spans:
        out.append((acc, acc + (e - s), s, e))
        acc += e - s
    return out


def main():
    ap = argparse.ArgumentParser(description="QA 残留条目回补进初选决定")
    ap.add_argument("ws")
    ap.add_argument("seg")
    ap.add_argument("qa_srt")
    ap.add_argument("ids", nargs="+", type=int)
    ap.add_argument("--fragment", default=None)
    args = ap.parse_args()

    ws = Path(args.ws)
    tri = ws / "3_转录初选"
    seg_map = cut_to_source_map(ws, args.seg)
    qa = parse_srt_with_idx(args.qa_srt)
    new = parse_srt_with_idx(tri / f"{args.seg}.srt")
    frag = find_fragment(ws, args.seg, args.fragment)
    plan = json.loads(frag.read_text(encoding="utf-8"))
    sp = plan.setdefault(args.seg, {})
    sp.setdefault("src", f"../3_转录初选/{args.seg}.srt")
    iron = sp.setdefault("iron", {})

    added, missed = [], []
    for i in args.ids:
        e = next((x for x in qa if x[0] == i), None)
        if e is None:
            missed.append(f"#{i}:QA稿无此条")
            continue
        mid = (e[1] + e[2]) / 2 / 1000  # QA 稿时间是毫秒，区间是秒
        src = next((m for m in seg_map if m[0] - 0.01 <= mid <= m[1] + 0.01), None)
        if src is None:
            missed.append(f"#{i}:成片时间 {mid:.1f}s 不在任何裁剪区间")
            continue
        src_t = src[2] + (mid - src[0])
        tgt = [n for n in new if n[1] / 1000 - 0.4 <= src_t <= n[2] / 1000 + 0.4]
        if len(tgt) != 1:
            missed.append(f"#{i}:原素材时间 {src_t:.1f}s 命中新稿 {len(tgt)} 条")
            continue
        n = tgt[0]
        if str(n[0]) in iron:
            missed.append(f"#{i}:已在决定里（新稿 #{n[0]}）")
            continue
        iron[str(n[0])] = n[3][:8]
        added.append(f"新稿#{n[0]}「{n[3][:16]}」←QA#{i}「{e[3][:14]}」")

    frag.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    for a in added:
        print("  +", a)
    for m in missed:
        print("  !", m)
    print(f"[qa_backfill] {args.seg}: 回补 {len(added)}，未定位 {len(missed)} → {frag.name}")


if __name__ == "__main__":
    main()
