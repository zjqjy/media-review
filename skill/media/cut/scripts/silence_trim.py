#!/usr/bin/env python3
"""静音废段自动压缩——口播素材的第一层粗剪（零依赖，仅需 ffmpeg）。

原理：silencedetect 检测超过阈值的无人声段，视频/音频同步剪掉（保留短停顿，
只砍"长冷场"）。输出压缩版视频 + 切割报告。

用法：
  python silence_trim.py 素材.mp4                    # 输出 素材_trimmed.mp4
  python silence_trim.py 素材.mp4 -o out.mp4
  参数：
    --db -35        静音判定阈值 dB（环境噪大调到 -30，录音好可 -40）
    --min 2.0       连续静音超过 N 秒才剪（保留自然停顿，默认 2 秒）
    --pad 0.3       每段两头各保留 N 秒缓冲，避免切字
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path


def find_ffmpeg():
    """PATH 优先，其次 imageio_ffmpeg 自带的二进制（剪辑机器常见）。"""
    p = shutil.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        sys.exit("找不到 ffmpeg：装一个（winget install ffmpeg）"
                 "或 pip install imageio-ffmpeg")


FFMPEG = find_ffmpeg()


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        print(p.stderr[-2000:], file=sys.stderr)
        sys.exit(f"命令失败：{' '.join(cmd[:4])}...")
    return p.stderr  # silencedetect 的输出在 stderr


def detect_silences(video, db, min_s):
    """返回 [(start, end)] 静音段列表（秒）。"""
    out = run([FFMPEG, "-i", video, "-af",
               f"silencedetect=noise={db}dB:d={min_s}", "-f", "null", "-"])
    starts = [float(m) for m in re.findall(r"silence_start:\s*([\d.]+)", out)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*([\d.]+)", out)]
    # silence_start/end 成对出现；末尾可能缺 end（素材以静音结束）→ 用时长补
    dur = duration_of(video)
    if len(ends) < len(starts):
        ends.append(dur)
    return list(zip(starts, ends)), dur


def duration_of(video):
    """不依赖 ffprobe：解析 ffmpeg -i 的 Duration 行。"""
    p = subprocess.run([FFMPEG, "-i", video], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", p.stderr)
    if not m:
        sys.exit("读不到视频时长——文件损坏或不是媒体文件")
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def fmt(t):
    m, s = divmod(int(t), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def build_filter(silences, dur, pad):
    """删除静音段：视频 select 与音频 aselect 用同一条件，保证音画同步。
    返回 (vf, af, 砍掉总秒数)。"""
    spans = []
    for s, e in silences:
        s, e = max(0, s + pad), min(dur, e - pad)
        if e - s <= 0.2:  # 加 pad 后没剩多少，不砍
            continue
        if spans and s <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], e))
        else:
            spans.append((s, e))
    if not spans:
        return None, None, 0.0

    removed = sum(e - s for s, e in spans)
    conds = "+".join(f"between(t,{s:.2f},{e:.2f})" for s, e in spans)
    vf = f"select='not({conds})',setpts=N/FRAME_RATE/TB"
    af = f"aselect='not({conds})',asetpts=N/SR/TB"
    return vf, af, removed


def main():
    ap = argparse.ArgumentParser(description="静音废段自动压缩")
    ap.add_argument("video")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--db", type=float, default=-35)
    ap.add_argument("--min", type=float, default=2.0, dest="min_s")
    ap.add_argument("--pad", type=float, default=0.3)
    args = ap.parse_args()

    video = Path(args.video)
    out = Path(args.out) if args.out else \
        video.with_name(f"{video.stem}_trimmed{video.suffix}")

    silences, dur = detect_silences(video, args.db, args.min_s)
    if not silences:
        print("没有检测到超过阈值的静音段，无需压缩")
        return
    vf, af, removed = build_filter(silences, dur, args.pad)
    if not vf:
        print("静音段加缓冲后已无可砍内容")
        return

    cmd = [FFMPEG, "-y", "-i", str(video),
           "-vf", vf, "-af", af,
           "-c:v", "libx264", "-preset", "fast", "-crf", "20",
           "-c:a", "aac", "-b:a", "160k", str(out)]
    print(f"[silence_trim] {fmt(dur)} 的素材，检测到 {len(silences)} 段静音，"
          f"共 {fmt(removed)}——处理中（重编码，挂机等）...")
    run(cmd)

    kept = dur - removed
    print(f"[silence_trim] 完成 → {out}")
    print(f"  原始 {fmt(dur)} → 压缩后约 {fmt(kept)}（砍掉 {removed/dur:.0%}）")
    print("  下一步：asr_funasr.py 转录 → AI 初选删行 → srt_cut.py 剪出粗片")


if __name__ == "__main__":
    main()
