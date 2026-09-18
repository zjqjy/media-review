#!/usr/bin/env python3
"""SRT 删行剪切——第②层"删句子 = 剪视频"的落地（零依赖，复用 silence_trim 的 ffmpeg 通道）。

输入：视频 + 编辑后的 SRT（AI 初选/人工删过行的，只保留要的句子）。
原理：把保留行的时间戳合成连续区间，视频 select 与音频 aselect 同条件保留，
音画同步。与 silence_trim 同一套 select/aselect 过滤器，方向相反（保 spans 而非砍 spans）。

用法：
  python srt_cut.py 素材.mp4 剪切稿.srt              # 输出 素材_cut.mp4
  python srt_cut.py 素材.mp4 剪切稿.srt -o out.mp4
  参数：
    --pad 0.2    每个保留段两头各扩 N 秒，防切字（字幕时间戳通常贴着语音）
    --gap 0.4    相邻保留行间隔小于 N 秒就并成一段，避免碎片化微剪
"""

import argparse
import re
import sys
from pathlib import Path

from silence_trim import FFMPEG, duration_of, fmt, run  # 同目录，同一套已验证逻辑


def parse_srt(path):
    """返回 [(start_s, end_s, text)]，按文件顺序。"""
    text = Path(path).read_text(encoding="utf-8-sig")
    blocks = re.split(r"\n\s*\n", text.strip())
    out = []
    tc = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")
    for b in blocks:
        lines = b.splitlines()
        m = None
        for i, line in enumerate(lines):
            m = tc.search(line)
            if m:
                break
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        body = "\n".join(lines[i + 1:]).strip()
        out.append((start, end, body))
    if not out:
        sys.exit("SRT 里没解析到时间戳条目——确认是标准 srt 格式且保留了行")
    return out


def build_spans(entries, dur, pad, gap):
    """保留行 → 合并后的保留区间 [(s,e)]，clamp 到素材时长。"""
    spans = []
    for s, e, _ in sorted(entries):
        s, e = max(0, s - pad), min(dur, e + pad)
        if spans and s <= spans[-1][1] + gap:
            spans[-1] = (spans[-1][0], max(spans[-1][1], e))
        else:
            spans.append((s, e))
    return spans


def subtract_intervals(spans, cuts, keep=0.0, min_cut=0.15, pre_roll=0.0):
    """从保留区间里挖洞（口头禅词级跳剪/区间内静音细剪共用）。

    cuts: [(s,e)] 待挖区间；min_cut 以下的不挖。
    pre_roll：洞起点向前多咬 N 秒——ASR 条目/词级时间戳普遍滞后实际发声
    （实测 ~0.3s），不预咬会把口误句的第一个字留在成片里。
    keep：挖洞后保留侧再回退 N 秒（pad 伸进洞口的兜底）。
    """
    fine = []
    for s, e in spans:
        cur = s
        for cs, ce in sorted(cuts):
            cs, ce = max(cs - pre_roll, s), min(ce, e)
            if ce - cs < min_cut:
                continue
            if cs > cur:
                fine.append((cur, max(cur, cs - keep)))
                cur = ce
            elif ce > cur:
                cur = ce
        if e > cur:
            fine.append((cur, e))
    return fine


def load_cuts(path):
    """asr_funasr 产出的 .cuts.json → [(s,e)] 秒。

    兼容两种格式：旧版裸列表（口头禅洞）；新版 {fillers:[], retake_pairs:[]}
    ——retake 对的前遍也在 fillers 里（word=🔁重录），直接合并。
    """
    import json
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [(c["start"] / 1000, c["end"] / 1000) for c in data]
    return [(c["start"] / 1000, c["end"] / 1000) for c in data.get("fillers", [])]


def main():
    ap = argparse.ArgumentParser(description="SRT 删行剪切（删句子 = 剪视频）")
    ap.add_argument("video")
    ap.add_argument("srt")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--pad", type=float, default=0.2)
    ap.add_argument("--gap", type=float, default=0.4)
    ap.add_argument("--cuts", default=None,
                    help="asr_funasr 产出的 .cuts.json（句首口头禅词级跳剪），默认自动找与视频同名的")
    args = ap.parse_args()

    video = Path(args.video)
    out = Path(args.out) if args.out else \
        video.with_name(f"{video.stem}_cut{video.suffix}")

    entries = parse_srt(args.srt)
    dur = duration_of(video)
    spans = build_spans(entries, dur, args.pad, args.gap)

    # cuts.json 查找顺序：显式指定 → 视频同目录 → srt 同目录（剪切稿常带"_剪切稿"
    # 后缀，转录稿名 = 剪切稿名去后缀；两种都对得上才找得到）
    cuts_path = Path(args.cuts) if args.cuts else None
    if cuts_path is None:
        srt_p = Path(args.srt)
        stems = [srt_p.stem, srt_p.stem.removesuffix("_剪切稿")]
        cands = [video.with_name(video.stem + ".cuts.json")]
        cands += [srt_p.with_name(st + ".cuts.json") for st in stems]
        cands += [p for p in sorted(srt_p.parent.glob("*.cuts.json"))
                  if p.stem.startswith(stems[0].split("_trimmed")[0])]  # 同目录兜底需同素材前缀
        for cand in cands:
            if cand.exists():
                cuts_path = cand
                break
    if cuts_path:
        holes = load_cuts(cuts_path)
        n_before = len(spans)
        spans = subtract_intervals(spans, holes, pre_roll=0.3, keep=0.1)
        t0 = sum(e - s for s, e in spans)
        print(f"[srt_cut] 词级跳剪：从 {cuts_path.name} 挖掉 {len(holes)} 个口头禅"
              f"（{n_before} 段 → {len(spans)} 段）")
    kept = sum(e - s for s, e in spans)

    conds = "+".join(f"between(t,{s:.2f},{e:.2f})" for s, e in spans)
    vf = f"select='{conds}',setpts=N/FRAME_RATE/TB"
    af = f"aselect='{conds}',asetpts=N/SR/TB"

    print(f"[srt_cut] 保留 {len(entries)} 句 → {len(spans)} 段，共 {fmt(kept)} / 原始 {fmt(dur)}"
          f"（砍 {1 - kept / dur:.0%}）——处理中（重编码，挂机等）...")
    run([FFMPEG, "-y", "-i", str(video),
         "-vf", vf, "-af", af,
         "-c:v", "libx264", "-preset", "fast", "-crf", "20",
         "-c:a", "aac", "-b:a", "160k", str(out)])
    print(f"[srt_cut] 完成 → {out}")


if __name__ == "__main__":
    main()
