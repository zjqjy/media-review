#!/usr/bin/env python3
"""待粗剪工作区归位——管线产物按阶段分目录（跑完管线执行一次）。

阶段约定：
  1_原始/        <名>.mp4
  2_静音压缩/    <名>_trimmed.mp4 + <名>.silence.json
  3_转录初选/    <名>_trimmed.srt + <名>_trimmed.cuts.json + <名>_剪切稿.srt + 初选日志.json
  _工具/         *.py *.md（匹配器/选择器/报告）

用法：python organize.py [工作区目录]（缺省当前目录）
"""
import shutil
import sys
from pathlib import Path

RULES = [  # (文件名模式, 目标目录)
    ("1_原始", lambda n: n.endswith(".mp4") and "_trimmed" not in n),
    ("2_静音压缩", lambda n: "_trimmed.mp4" in n or n.endswith(".silence.json")),
    ("3_转录初选", lambda n: (n.endswith(".srt") or n.endswith(".cuts.json")
                          or n.endswith(".json")) and "_trimmed" in n
                          or n.endswith("_剪切稿.srt") or n == "初选日志.json"),
    ("_工具", lambda n: n.endswith((".py", ".md"))),
]


def classify(name):
    for dst, test in RULES:
        if test(name):
            return dst
    return None


def main(root):
    root = Path(root)
    moved, locked = 0, []
    for f in sorted(root.iterdir()):
        if not f.is_file():
            continue
        dst = classify(f.name)
        if dst is None:
            continue
        d = root / dst
        d.mkdir(exist_ok=True)
        target = d / f.name
        if target.exists():
            print(f"  跳过（已存在）: {dst}/{f.name}")
            continue
        try:
            shutil.move(str(f), str(target))
            moved += 1
        except PermissionError:
            locked.append(f.name)
    for d in sorted(p.name for p in root.iterdir() if p.is_dir()):
        n = len(list((root / d).iterdir()))
        print(f"  {d}/: {n} 个")
    if locked:
        print(f"[organize] {len(locked)} 个文件被占用未动（关掉占用程序后重跑）: {locked}")
    print(f"[organize] 归位 {moved} 个文件")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
