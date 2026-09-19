#!/usr/bin/env python3
"""SRT 删行剪切——"删句子 = 剪视频"的落地（零依赖，复用 silence_trim 的 ffmpeg 通道）。

输入：视频 + 编辑后的 SRT（AI 初选/人工删过行的，只保留要的句子）。
原理：把保留行的时间戳合成连续区间，视频 select 与音频 aselect 同条件保留，
音画同步。与 silence_trim 同一套 select/aselect 过滤器，方向相反（保 spans 而非砍 spans）。

两种用法：
  python srt_cut.py 素材.mp4 剪切稿.srt              # 单段：输出 素材_粗剪.mp4
  python srt_cut.py --seq "01素材.mp4=01剪切稿.srt" "02素材.mp4=02剪切稿.srt"
                                                    # 批量：一进一出，各素材独立出片不拼接
                                                     （输入1输出1——剪映草稿是拼接版，这里是每素材一个文件）
每个输出配一条 <名>_粗剪.srt（字幕 rebase 到成片时间轴，可直接外挂/导入抖音）。

参数：
  --pad 0.2       每个保留段两头各扩 N 秒，防切字
  --gap 0.4       相邻保留行间隔小于 N 秒就并成一段，避免碎片化微剪
  --min-inner 0.8 区间内静音细剪阈值（秒），0=关闭（与 jy_draft 同款，成片节奏一致）
  --db -35        静音判定阈值
  --out-dir DIR   输出目录（缺省输出到素材旁）
"""

import argparse
import re
import sys
from pathlib import Path

from silence_trim import FFMPEG, detect_silences, duration_of, fmt, run  # 同目录，同一套已验证逻辑


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


def find_cuts_json(video: Path, srt: Path):
    """cuts.json 查找：视频同目录 → srt 同目录（词干剥离 _剪切稿 后缀）
    → srt 同目录同素材前缀兜底。找不到返回 None。"""
    stems = [srt.stem, srt.stem.removesuffix("_剪切稿")]
    cands = [video.with_name(video.stem + ".cuts.json")]
    cands += [srt.with_name(st + ".cuts.json") for st in stems]
    cands += [p for p in sorted(srt.parent.glob("*.cuts.json"))
              if p.stem.startswith(stems[0].split("_trimmed")[0])]  # 同目录兜底需同素材前缀
    for cand in cands:
        if cand.exists():
            return cand
    return None


def rebase_srt(entries, spans, path):
    """源时间轴条目 → 成片时间轴 srt（按 spans 平移，与成片对齐）。

    jy_draft 与 srt_cut 共用；spans 元素可带速度 (s,e,speed)。
    精确匹配失败（句首落在被挖的洞里）→ 取最近区间端点（距离超 1s 丢弃并计数）。
    """
    def target_of(src_start):
        acc = 0.0
        for sp in spans:
            s, e = sp[0], sp[1]
            speed = sp[2] if len(sp) > 2 else 1.0
            if s - 0.001 <= src_start <= e + 0.001:
                return acc + (src_start - s) / speed
            acc += (e - s) / speed
        best, best_d = None, 1.0
        acc = 0.0
        for sp in spans:
            s, e = sp[0], sp[1]
            speed = sp[2] if len(sp) > 2 else 1.0
            if s <= src_start <= e:
                d = 0.0
                pos = acc + (src_start - s) / speed
            else:
                d = min(abs(src_start - s), abs(src_start - e))
                pos = acc + min(max(src_start - s, 0), e - s) / speed
            if d < best_d:
                best_d, best = d, pos
            acc += (e - s) / speed
        return best

    def fmt_ts(t):
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
        lines.append(f"{n}\n{fmt_ts(a)} --> {fmt_ts(b)}\n{txt}\n")
    if dropped:
        print(f"[srt_cut] 提示：{dropped} 条字幕完全落在挖洞区被跳过")
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    return n


def process_one(video: Path, srt_path: Path, args):
    """单素材处理：剪切稿 → 保留区间（挖洞+静音细剪）→ 粗剪 mp4 + 对齐 srt。"""
    entries = parse_srt(str(srt_path))
    dur = duration_of(video)
    spans = build_spans(entries, dur, args.pad, args.gap)

    cuts_path = find_cuts_json(video, srt_path)
    if cuts_path:
        holes = load_cuts(cuts_path)
        n_before = len(spans)
        spans = subtract_intervals(spans, holes, pre_roll=0.3, keep=0.1)
        print(f"[srt_cut] {video.name} 词级跳剪：从 {cuts_path.name} 挖掉 {len(holes)} 个"
              f"（{n_before} 段 → {len(spans)} 段）")
    else:
        print(f"[srt_cut] {video.name} 警告：没找到 .cuts.json——词级洞（口头禅/重录前遍）不挖")

    if args.min_inner > 0:
        silences, _ = detect_silences(str(video), args.db, args.min_inner)
        spans = subtract_intervals(spans, silences, keep=0.2, min_cut=0.5)
        print(f"[srt_cut] {video.name} 静音细剪 → {len(spans)} 段")

    out = (args.out_dir / f"{video.stem}_粗剪{video.suffix}") if args.out_dir \
        else video.with_name(f"{video.stem}_粗剪{video.suffix}")
    out.parent.mkdir(parents=True, exist_ok=True)

    # 字幕 rebase 到成片时间轴，与 mp4 同名同目录
    n_sub = rebase_srt(entries, spans, out.with_suffix(".srt"))

    kept = sum(e - s for s, e in spans)
    conds = "+".join(f"between(t,{s:.2f},{e:.2f})" for s, e in spans)
    vf = f"select='{conds}',setpts=N/FRAME_RATE/TB"
    af = f"aselect='{conds}',asetpts=N/SR/TB"

    print(f"[srt_cut] {video.name} 保留 {len(entries)} 句 → {len(spans)} 段，共 {fmt(kept)}"
          f" / 原始 {fmt(dur)}（砍 {1 - kept / dur:.0%}）——处理中（重编码，挂机等）...")
    run([FFMPEG, "-y", "-i", str(video),
         "-vf", vf, "-af", af,
         "-c:v", "libx264", "-preset", "fast", "-crf", "20",
         "-c:a", "aac", "-b:a", "160k", str(out)])
    print(f"[srt_cut] 完成 → {out}（字幕 {n_sub} 条 → {out.with_suffix('.srt').name}）")


def main():
    ap = argparse.ArgumentParser(description="SRT 删行剪切（删句子 = 剪视频；支持批量一进一出）")
    ap.add_argument("video", nargs="?", default=None, help="单段模式：视频")
    ap.add_argument("srt", nargs="?", default=None, help="单段模式：剪切稿 srt")
    ap.add_argument("--seq", nargs="*", default=None,
                    help='批量模式：按顺序 "视频=剪切稿" 列表，各素材独立出片不拼接')
    ap.add_argument("-o", "--out", default=None, help="输出路径（仅单段模式）")
    ap.add_argument("--out-dir", default=None, help="批量模式输出目录（缺省输出到各素材旁）")
    ap.add_argument("--pad", type=float, default=0.2)
    ap.add_argument("--gap", type=float, default=0.4)
    ap.add_argument("--min-inner", type=float, default=0.8,
                    help="区间内静音细剪阈值（秒），0=关闭")
    ap.add_argument("--db", type=float, default=-35, help="静音判定阈值 dB")
    args = ap.parse_args()
    args.out_dir = Path(args.out_dir) if args.out_dir else None

    segs = []
    if args.seq:
        for item in args.seq:
            if "=" not in item:
                sys.exit(f"--seq 格式应为 视频=剪切稿：{item}")
            v, s = item.split("=", 1)
            segs.append((Path(v), Path(s)))
    else:
        if not args.video or not args.srt:
            ap.error("需要 video srt 或 --seq")
        segs.append((Path(args.video), Path(args.srt)))
        if args.out:
            print("[srt_cut] 提示：-o 在批量模式无效，单段模式输出名固定 <素材>_粗剪.mp4")

    for video, srt_path in segs:
        if not video.exists():
            sys.exit(f"素材不存在：{video}")
        if not srt_path.exists():
            sys.exit(f"剪切稿不存在：{srt_path}")
        process_one(video, srt_path, args)


if __name__ == "__main__":
    main()
