#!/usr/bin/env python3
"""复盘截图收集窗——复盘会话时由 skill 启动，贴完即关，非常驻。

用法：
  python screenshot_tray.py [--dir 收件目录]

操作：截图（Win+Shift+S 等）→ 本窗口置顶 → 填期数 → 点窗口/按 Ctrl+V 连续贴
      → 平台下拉标注 → 点"完成收集"退出。

保存结构（分平台分期数物理隔离，AI 后整理兜底）：
  <dir>/<期数>/<平台>/<时间戳>.png
  平台未标注时归 <期数>/未标平台/

依赖：Pillow（pip install pillow）。剪贴板无图时提示，不打断。
"""

import argparse
import datetime
import tkinter as tk
from pathlib import Path
from tkinter import ttk

try:
    from PIL import ImageGrab
except ImportError:
    raise SystemExit("缺依赖：pip install pillow")

PLATFORMS = ["未标平台", "抖音", "小红书", "B站"]


class Collector(tk.Tk):
    def __init__(self, target_dir: Path):
        super().__init__()
        self.target_dir = target_dir
        self.target_dir.mkdir(parents=True, exist_ok=True)
        self.count = 0

        self.title("复盘截图收集")
        self.attributes("-topmost", True)   # 置顶，方便贴图
        self.resizable(False, False)
        self.bind("<Control-v>", lambda e: self.paste())

        ttk.Label(self, text="截图后点本窗口按 Ctrl+V（可连续贴）").pack(padx=12, pady=(10, 4))

        row = ttk.Frame(self)
        row.pack(padx=12, pady=4, fill="x")
        ttk.Label(row, text="期数").pack(side="left")
        self.episode = ttk.Entry(row, width=10, font=("", 10))
        self.episode.insert(0, "第1期")
        self.episode.pack(side="left", padx=(4, 12))
        ttk.Label(row, text="平台").pack(side="left")
        self.platform = ttk.Combobox(row, values=PLATFORMS, state="readonly",
                                     width=10, font=("", 10))
        self.platform.current(0)
        self.platform.pack(side="left", padx=6)

        self.hint = tk.Label(self, text=self._hint_text(), fg="#555", font=("", 11, "bold"))
        self.hint.pack(padx=12, pady=6)

        ttk.Button(self, text="完成收集", command=self.destroy).pack(pady=(2, 12))

        # 置顶有时被别的置顶窗盖住，抢一下焦点
        self.focus_force()

    def _episode(self):
        """期数作为子目录名，清理路径脏字符；空则归'未分期'（AI 后整理兜底）。"""
        name = self.episode.get().strip().replace("/", "_").replace("\\", "_")
        return name or "未分期"

    def _hint_text(self):
        return f"已收集 {self.count} 张 → {self._episode()}/{self.platform.get()}/"

    def paste(self, _event=None):
        img = ImageGrab.grabclipboard()
        if img is None:
            self.hint.config(text="剪贴板里没有图片——先截图（Win+Shift+S）再按 Ctrl+V",
                             fg="#c0392b")
            self.after(2500, lambda: self.hint.config(text=self._hint_text(), fg="#555"))
            return
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        # 分期数+分平台双级目录：切换平台下拉即切目录，不混
        plat_dir = self.target_dir / self._episode() / self.platform.get()
        plat_dir.mkdir(parents=True, exist_ok=True)
        target = plat_dir / f"{ts}.png"
        i = 1
        while target.exists():
            target = plat_dir / f"{ts}-{i}.png"
            i += 1
        img.save(target)
        self.count += 1
        self.hint.config(text=self._hint_text(), fg="#27ae60")


def main():
    ap = argparse.ArgumentParser(description="复盘截图收集窗")
    ap.add_argument("--dir", required=True, help="截图落盘目录（vault 侧 _截图收件）")
    args = ap.parse_args()
    Collector(Path(args.dir)).mainloop()


if __name__ == "__main__":
    main()
