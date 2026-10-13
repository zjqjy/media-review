#!/usr/bin/env python3
# 洪泛填充去底：从图像边缘出发，把与角落背景色相连的连通区抠成透明。
# 只清边缘连通的同色区——主体内部的同色区和深色描边不受影响（区别于全图 colorkey）。
# 典型用途：屏幕资产 GIF 帧（黑底）、贴纸图（白底）转透明底，落彩色卡片/工程底色。
#
# 用法:
#   python debg.py <文件或目录...> [--tol 45] [--out 输出目录]
#   目录会递归处理其中的 png/jpg；不给 --out 就原地覆盖（RGBA png）
#
# 依赖: Pillow（media install.ps1 已装）
import argparse
import os
import sys
from collections import Counter, deque

from PIL import Image


def make_bg_transparent(path, tol=45, out_dir=None):
    im = Image.open(path).convert("RGBA")
    w, h = im.size
    px = im.load()
    # 背景色 = 四角最常见的颜色
    corners = [px[0, 0][:3], px[w - 1, 0][:3], px[0, h - 1][:3], px[w - 1, h - 1][:3]]
    bg = Counter(corners).most_common(1)[0][0]
    # 与纯白/纯黑很接近时按 248/8 处理（很多贴纸底是 248,248,248）
    seen = [[False] * w for _ in range(h)]
    q = deque()
    for x in range(w):
        q.append((x, 0))
        q.append((x, h - 1))
    for y in range(h):
        q.append((0, y))
        q.append((w - 1, y))
    cleared = 0
    while q:
        x, y = q.popleft()
        if x < 0 or y < 0 or x >= w or y >= h or seen[y][x]:
            continue
        r, g, b, _ = px[x, y]
        if abs(r - bg[0]) + abs(g - bg[1]) + abs(b - bg[2]) <= tol:
            seen[y][x] = True
            px[x, y] = (r, g, b, 0)
            cleared += 1
            q.extend([(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)])
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, os.path.basename(path))
        name, ext = os.path.splitext(out_path)
        out_path = name + ".png"
    else:
        out_path = os.path.splitext(path)[0] + ".png"
    im.save(out_path)
    return bg, cleared, out_path


def collect(inputs):
    files = []
    for p in inputs:
        if os.path.isdir(p):
            for root, _, names in os.walk(p):
                files.extend(os.path.join(root, n) for n in names if n.lower().endswith((".png", ".jpg", ".jpeg")))
        elif os.path.isfile(p):
            files.append(p)
    return files


def main():
    ap = argparse.ArgumentParser(description="洪泛填充去底（边缘连通背景→透明）")
    ap.add_argument("inputs", nargs="+", help="图片文件或目录（目录递归）")
    ap.add_argument("--tol", type=int, default=45, help="背景色容差（RGB 差值之和，默认 45）")
    ap.add_argument("--out", default=None, help="输出目录（默认原地覆盖为同名 png）")
    args = ap.parse_args()

    files = collect(args.inputs)
    if not files:
        print("没有找到图片文件", file=sys.stderr)
        sys.exit(1)
    for f in files:
        bg, cleared, out_path = make_bg_transparent(f, args.tol, args.out)
        print(f"{f}  bg={bg}  清除 {cleared}px  → {out_path}")


if __name__ == "__main__":
    main()
