#!/usr/bin/env python3
"""frame_pick.py — 按 blog_plan.json 的 frames 清单从成片抽帧落站点图片目录 + 出人兜底预览页。

选帧口径（S7 R0-3 定音）：AI 全自动选帧，人兜底——agent 读逐字稿+srt 时间轴在 plan 里写
frames 清单 → 本脚本抽帧+出预览 → 用户看预览说「第 N 张换到 xx 处 / 删掉」→ 改 plan 重抽。

ffmpeg 定位：PATH 优先，退 imageio_ffmpeg（与 cut/post 同一套逻辑）。
抽帧 `-ss <t>` 放输入侧（重编码单帧，seek 精度按现代 ffmpeg 是帧级）；
`-vf scale='min(1600,iw)':-2` 长边收到 1600px 宽以内（站点正文图足够，省体积）；
`-q:v 3` 高质量 JPEG。
"""
from __future__ import annotations

import argparse
import html
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blog_plan import frame_filename, plan_from_file, validate_plan  # noqa: E402

MAX_WIDTH = 1600


def find_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg  # type: ignore
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise SystemExit("FAIL 找不到 ffmpeg（PATH 无，imageio_ffmpeg 也没装）")


def ffprobe_duration(video: Path) -> float | None:
    """成片时长（秒）；ffprobe 不可用返回 None（跳过越界检查）。"""
    probe = shutil.which("ffprobe")
    if not probe:
        return None
    r = subprocess.run(
        [probe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
        capture_output=True, text=True, timeout=60)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def extract_frames(plan: dict, out_dir: Path, force: bool = False) -> list[Path]:
    """逐帧抽取，返回落盘文件清单（顺序与 plan.frames 一致）。"""
    ffmpeg = find_ffmpeg()
    video = Path(plan["video"])
    if not video.is_file():
        raise SystemExit(f"FAIL 成片不存在: {video}")
    dur = ffprobe_duration(video)

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for i, f in enumerate(plan.get("frames", []), start=1):
        t = float(f["t"])
        if dur is not None and t > dur:
            raise SystemExit(f"FAIL frames[{i-1}].t={t}s 超出成片时长 {dur:.1f}s")
        dst = out_dir / frame_filename(i, f["name"])
        if dst.exists() and not force:
            written.append(dst)
            continue
        cmd = [ffmpeg, "-y", "-loglevel", "error",
               "-ss", f"{t:.3f}", "-i", str(video),
               "-frames:v", "1",
               "-vf", f"scale='min({MAX_WIDTH},iw)':-2",
               "-q:v", "3", str(dst)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode != 0 or not dst.is_file():
            raise SystemExit(f"FAIL 抽帧 {dst.name}: {r.stderr.strip()[:300]}")
        written.append(dst)
    return written


def build_preview(plan: dict, frames_dir: Path, preview_dir: Path) -> Path:
    """人兜底预览页：帧图+时间点+alt+所属节+兜底操作说明，自包含单 HTML。

    预览页落成片目录（plan 旁车旁），绝不进站点 source/（Hexo 会原样发布出去）。"""
    slug = plan["slug"]
    out = preview_dir / f"{slug}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, f in enumerate(plan.get("frames", []), start=1):
        fn = frame_filename(i, f["name"])
        src = (frames_dir / fn).resolve().as_uri()
        caption = html.escape(f.get("caption") or "")
        section = html.escape(f.get("section") or "")
        alt = html.escape(f.get("alt") or fn)
        rows.append(f"""
  <div class="card" id="f{i}">
    <img src="{src}" alt="{alt}" onerror="this.replaceWith('(抽帧文件缺失: {fn})')">
    <div class="meta">
      <b>#{i}</b> · {fn} · t={f['t']}s {('· '+section) if section else ''}
      <div class="cap">{caption}</div>
      <div class="alt">alt: {alt}</div>
    </div>
  </div>""")
    n = len(rows)
    page = f"""<!doctype html>
<html lang="zh"><meta charset="utf-8">
<title>选帧预览 · {html.escape(slug)}（{n} 帧）</title>
<style>
 body{{font-family:system-ui,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;background:#fafafa}}
 h1{{font-size:20px}} .tip{{background:#fff3cd;padding:10px 14px;border-radius:8px;font-size:14px}}
 .grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px}}
 .card{{background:#fff;border:1px solid #e5e5e5;border-radius:10px;overflow:hidden}}
 .card img{{width:100%;display:block;background:#111;min-height:80px}}
 .meta{{padding:8px 12px;font-size:13px;color:#333}} .cap{{color:#666;margin-top:2px}}
 .alt{{color:#999;font-size:12px;margin-top:2px}}
</style>
<h1>选帧预览 · {html.escape(slug)}（{n} 帧）</h1>
<div class="tip">人兜底三件事，改完让 agent 改 plan 重抽：<b>①换帧</b>「第 N 张换到 mm:ss」
<b>②删图</b>「删第 N 张」 <b>③改文案</b>「第 N 张 alt/caption 改成 …」。
时间轴 = 成片（{html.escape(str(plan.get('video','')))}）。</div>
<div class="grid">{''.join(rows)}</div>
"""
    out.write_text(page, encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="按 plan 抽帧落站点 + 出预览")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--site-root", help="站点仓库根（输出 source/images/<slug>/）；不传则只出预览")
    ap.add_argument("--out-dir", help="显式输出目录（dry-run 用，覆盖 site-root 推导）")
    ap.add_argument("--force", action="store_true", help="覆盖已存在帧图")
    ap.add_argument("--preview-only", action="store_true", help="只出预览页不抽帧")
    a = ap.parse_args(argv)

    plan = plan_from_file(a.plan)
    errors = validate_plan(plan)
    if errors:
        print("\n".join(f"FAIL {x}" for x in errors))
        return 1

    slug = plan["slug"]
    if a.out_dir:
        frames_dir = Path(a.out_dir)
    elif a.site_root:
        frames_dir = Path(a.site_root) / "source" / "images" / slug
    else:
        frames_dir = None

    if not a.preview_only:
        if frames_dir is None:
            print("FAIL 需要 --site-root 或 --out-dir（或 --preview-only）")
            return 2
        written = extract_frames(plan, frames_dir, force=a.force)
        for w in written:
            print(f"帧 {w}")
    # 预览页默认落 plan 旁车同目录（成片目录）；dry-run 的 --out-dir 场景落输出目录旁
    preview_base = Path(a.plan).resolve().parent if not a.out_dir else Path(a.out_dir)
    preview = build_preview(plan, frames_dir or preview_base,
                            preview_base / "blog_preview")
    print(f"预览 {preview}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
