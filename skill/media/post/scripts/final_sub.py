#!/usr/bin/env python3
"""成片定稿后出字幕——精剪与字幕解耦的最后一步。

配合 jy_draft.py --no-sub 使用：纯视频草稿里随便删（没有字幕轨可剪坏），
导出成片后跑本脚本重出字幕，剪映导入即可。

  python final_sub.py 成片.mp4                # 输出 成片_字幕.srt（同目录）
  python final_sub.py 成片.mp4 -o 成片.srt

流程：asr_funasr 转录成片（几分钟的成片转录很快）→ 自动套 asr_fixes.json
全局错拼表（转录端不套，剪辑域错拼在这里兜底）→ srt 落盘。
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
CUT_SCRIPTS = HERE.parent.parent / "cut" / "scripts"  # 转录器与错拼表都在 cut
sys.path.insert(0, str(CUT_SCRIPTS))
from select import load_global_fixes  # noqa: E402
from srt_cut import parse_srt as parse_srt_tuples  # noqa: E402


def apply_fixes(entries):
    if not entries:
        return entries, 0
    n = 0
    out = []
    for a, b, txt in entries:
        for old, new in load_global_fixes():
            if old in txt:
                txt = txt.replace(old, new)
                n += 1
        out.append((a, b, txt))
    return out, n


def main():
    ap = argparse.ArgumentParser(description="成片定稿后重出字幕（转录→套错拼表→srt）")
    ap.add_argument("video", help="定稿成片（mp4/音频均可）")
    ap.add_argument("-o", "--out", default=None, help="输出 srt 路径（缺省 <成片>_字幕.srt）")
    ap.add_argument("--hotword", default="",
                    help="热词，空格分隔（技术词塞这里准确率立涨）")
    args = ap.parse_args()

    video = Path(args.video)
    if not video.exists():
        sys.exit(f"final_sub: 成片不存在：{video}")
    out = Path(args.out) if args.out else video.with_name(f"{video.stem}_字幕.srt")

    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "raw.srt"
        cmd = [sys.executable, CUT_SCRIPTS / "asr_funasr.py", str(video), "-o", str(raw)]
        if args.hotword:
            cmd += ["--hotword", args.hotword]
        r = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0 or not raw.exists():
            sys.exit("final_sub: 转录失败，看上面 asr_funasr 输出")
        # 在临时目录存活期内解析进内存（出了 with raw.srt 就没了——实测踩坑）
        entries, n_fixed = apply_fixes(parse_srt_tuples(str(raw)))

    def _fmt(t):
        ms = int(round(t * 1000))
        h, rem = divmod(ms, 3600000)
        m, rem = divmod(rem, 60000)
        s, ms2 = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms2:03d}"

    lines = [f"{i}\n{_fmt(a)} --> {_fmt(b)}\n{txt}\n"
             for i, (a, b, txt) in enumerate(entries, 1)]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"[final_sub] 字幕已生成：{out}（{len(entries)} 条，套错拼 {n_fixed} 处）")
    print("  导入剪映：媒体面板→导入→选这个 srt（或素材库右键导入字幕），"
          "样式在剪映里调一次即可")


if __name__ == "__main__":
    main()
