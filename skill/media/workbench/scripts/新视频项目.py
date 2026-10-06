#!/usr/bin/env python3
"""新视频项目.py — 建视频项目规范目录树
用法: python 新视频项目.py <项目路径>
"""
import os
import sys

DIRS = ["00_口播", "01_字幕卡_HTML", "02_动效视频", "03_实拍素材", "04_成片"]

def main():
    if len(sys.argv) < 2:
        raise SystemExit("用法: python 新视频项目.py <项目路径>")
    root = sys.argv[1]
    os.makedirs(root, exist_ok=True)
    for d in DIRS:
        os.makedirs(os.path.join(root, d), exist_ok=True)
    print("项目已建:", root)
    for d in DIRS:
        print("  ", d + "/")
    print("下一步: 口播脚本 md 放进 00_口播/，然后运行 工作台.py 生成面板")

if __name__ == "__main__":
    main()
