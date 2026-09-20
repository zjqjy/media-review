#!/usr/bin/env python3
"""成片响度统一——EBU R128 loudnorm 两遍法，视频流零重编码。

  python loudnorm.py 成片.mp4              # 量测+应用，输出 成片_响度.mp4
  python loudnorm.py 成片.mp4 --measure    # 只量测出报告，不改文件
  python loudnorm.py a.mp4 b.mp4           # 批量
  python loudnorm.py 成片.mp4 -I -14       # 目标响度（缺省 -16 LUFS，抖音可 -14）

第一遍量测（input_I/TP/LRA/thresh），第二遍带实测值 linear=true 回写——
比单遍动态模式少一刀动态处理，人声更自然。**视频流 -c:v copy 不动**，
只重编码音轨（aac 192k），十几分钟的成片秒级完成。
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


def find_ffmpeg():
    """PATH 优先，其次 imageio_ffmpeg 自带二进制（剪辑机器常见，与 cut 一致）。"""
    p = shutil.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        sys.exit("loudnorm: 找不到 ffmpeg——pip install imageio-ffmpeg 或装 ffmpeg 进 PATH")


def run(cmd):
    r = subprocess.run([str(c) for c in cmd], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(r.stderr[-1500:])
        sys.exit(f"loudnorm: ffmpeg 失败（exit {r.returncode}）")
    return r.stderr


def measure(ffmpeg, video, target_i, target_tp, target_lra):
    """第一遍：量测实测响度。返回实测字典 + 探针信息（时长/分辨率）。"""
    err = run([ffmpeg, "-hide_banner", "-nostats", "-i", video,
               "-af", f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:print_format=json",
               "-f", "null", "-"])
    m = re.search(r"\{\s*\"input_i\".*?\}", err, re.S)
    if not m:
        sys.exit(f"loudnorm: 量测失败，stderr 里没有 loudnorm JSON：\n{err[-800:]}")
    stats = json.loads(m.group())
    info = {}
    for pat, key in [(r"Duration:\s*(\S+?),", "duration"),
                     (r"Stream.*Video.*?, (\d+x\d+)", "resolution")]:
        mm = re.search(pat, err)
        if mm:
            info[key] = mm.group(1)
    return stats, info


def apply(ffmpeg, video, out, stats, target_i, target_tp, target_lra):
    """第二遍：带实测值线性模式回写。视频流 copy，只动音轨。"""
    af = (f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}"
          f":measured_I={stats['input_i']}:measured_TP={stats['input_tp']}"
          f":measured_LRA={stats['input_lra']}:measured_thresh={stats['input_thresh']}"
          f":offset={stats['target_offset']}:linear=true:print_format=summary,"
          "aresample=48000")
    run([ffmpeg, "-y", "-hide_banner", "-nostats", "-i", video,
         "-c:v", "copy", "-af", af, "-c:a", "aac", "-b:a", "192k", out])


def process(video, args):
    ffmpeg = find_ffmpeg()
    video = Path(video)
    if not video.exists():
        sys.exit(f"loudnorm: 文件不存在：{video}")
    stats, info = measure(ffmpeg, video, args.i, args.tp, args.lra)
    print(f"[loudnorm] {video.name}: {info.get('duration', '?')} "
          f"{info.get('resolution', '?')}｜实测 {stats['input_i']} LUFS "
          f"(LRA {stats['input_lra']}, peak {stats['input_tp']} dBTP)")
    if args.measure:
        return
    out = Path(args.out) if args.out else video.with_name(f"{video.stem}_响度.mp4")
    apply(ffmpeg, video, out, stats, args.i, args.tp, args.lra)
    print(f"[loudnorm] 已统一到 {args.i} LUFS：{out}（视频流原样拷贝，零重编码）")


def main():
    ap = argparse.ArgumentParser(description="成片响度统一（EBU R128 两遍法，视频流零重编码）")
    ap.add_argument("videos", nargs="+", help="成片（可多个）")
    ap.add_argument("-o", "--out", default=None, help="输出路径（仅单文件模式）")
    ap.add_argument("-I", "--i", type=float, default=-16, help="目标响度 LUFS（缺省 -16）")
    ap.add_argument("--tp", type=float, default=-1.5, help="真峰值上限 dBTP（缺省 -1.5）")
    ap.add_argument("--lra", type=float, default=11, help="响度范围 LRA（缺省 11）")
    ap.add_argument("--measure", action="store_true", help="只量测出报告，不写文件")
    args = ap.parse_args()
    if args.out and len(args.videos) > 1:
        sys.exit("loudnorm: -o 只支持单文件")
    for v in args.videos:
        process(v, args)


if __name__ == "__main__":
    main()
