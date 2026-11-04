#!/usr/bin/env python3
"""素材回收.py — 拍摄素材回收匹配器（纯标准库 CLI，零依赖；ffmpeg/ffprobe 只经 subprocess 调外部二进制）

职责：拍摄素材回来后，把素材目录里的视频/图片按「文件名含批注 id」精确匹配
到定稿旁车 shoot.json 的 annotations 上：
  - 命中      → footage 新条目：match="filename"、state="candidate"、ann_ids=[命中的 id...]
  - 一条素材文件名含多个 id → ann_ids 挂多个（多对多）
  - 一条 id 命中多个文件   → 全部挂为候选
  - 未命中的文件 → 进 Markdown 报告「未匹配素材」表（建议列留空给 AI 填）
幂等：同相对路径的素材已在 footage 里就跳过，重跑不重复挂接。

匹配宽容度：大小写不敏感 + 全半角等价（unicodedata NFKC，Ｒ０３ ≡ R03）；
后随 ASCII 数字不算命中（防 R01 吃进 R010），前随字符不设限（R01R03双命中.mp4 两头都命中）。

用法：
    python 素材回收.py <项目根> [--footage-dir 相对目录] [--dry-run] [--md 定稿md路径]
参数：
    项目根         定稿 md + 旁车 shoot.json + 素材都在这棵目录树下
    --footage-dir  只扫这个相对目录（缺省扫整个项目根，跳隐藏目录）
    --dry-run      只打印报告，不写旁车、不落报告文件
    --md           项目根下有多份 *.shoot.json 时用它指定定稿 md 消歧

红线：素材本体文件绝不移动/重命名——只把相对路径记进旁车；annotation id 定稿后永不变。
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

# 素材扩展名（小写比较）：视频 + 图片
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
FOOTAGE_EXTS = VIDEO_EXTS | IMAGE_EXTS

# 递归扫描时跳过的目录（隐藏目录一律跳过）
SKIP_DIRS = {"__pycache__", "node_modules"}

REPORT_NAME = "素材回收报告.md"


# ---------------------------------------------------------------- 匹配内核


def norm(s):
    """匹配归一化：NFKC 折叠全半角（Ｒ０３→R03、＿→_）+ casefold 大小写。"""
    return unicodedata.normalize("NFKC", s).casefold()


def id_in_name(ann_id, filename):
    """批注 id 是否命中文件名。规则：
    - 双方都过 norm()（大小写 + 全半角宽容）
    - 命中位置的下一个字符不是 ASCII 数字（防 R01 匹配进 R010_a.mp4）
    - 命中位置的前一个字符不设限（R01R03双命中.mp4 → R01、R03 都命中）
    """
    hay = norm(filename)
    needle = norm(ann_id)
    if not needle:
        return False
    start = 0
    while True:
        i = hay.find(needle, start)
        if i < 0:
            return False
        end = i + len(needle)
        nxt = hay[end] if end < len(hay) else ""
        if not (nxt.isascii() and nxt.isdigit()):
            return True
        start = i + 1  # 这个位置被数字挡住，从下一位再找
    return False


def match_file_to_anns(filename, ann_ids):
    """一个文件名对全部批注 id 求命中（保持旁车里的批注顺序）。"""
    return [aid for aid in ann_ids if id_in_name(aid, filename)]


# ---------------------------------------------------------------- 定位旁车


def find_sidecar(root, md_hint=""):
    """定位定稿旁车 <定稿md同名>.shoot.json。
    优先级：--md 指定 > 项目根顶层唯一的 *.shoot.json > 递归找到的唯一一个。
    找到多个 → 抛 ValueError 列出清单让用户用 --md 消歧。
    返回 (md_path, sidecar_path)，均为 Path；找不到抛 ValueError。
    """
    root = Path(root)
    if md_hint:
        md = Path(md_hint)
        if not md.is_absolute():
            md = root / md
        if not md.is_file():
            raise ValueError(f"--md 指定的定稿不存在: {md}")
        side = Path(str(md) + ".shoot.json")
        if not side.is_file():
            raise ValueError(f"定稿旁车不存在: {side}")
        return md, side

    tops = sorted(root.glob("*.shoot.json"))
    if len(tops) == 1:
        side = tops[0]
        return Path(str(side)[: -len(".shoot.json")]), side
    if len(tops) > 1:
        raise ValueError(
            "项目根顶层有多份 shoot.json 旁车，用 --md 指定定稿消歧:\n  "
            + "\n  ".join(str(p) for p in tops))

    # 顶层没有 → 递归找（跳隐藏目录），找到唯一才认
    deep = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and d not in SKIP_DIRS]
        for name in filenames:
            if name.endswith(".shoot.json"):
                deep.append(Path(dirpath) / name)
    if not deep:
        raise ValueError(f"项目根下找不到 *.shoot.json 旁车: {root}")
    if len(deep) > 1:
        raise ValueError(
            "找到多份 shoot.json 旁车，用 --md 指定定稿消歧:\n  "
            + "\n  ".join(str(p) for p in sorted(deep)))
    side = deep[0]
    return Path(str(side)[: -len(".shoot.json")]), side


# ---------------------------------------------------------------- 旁车读写


def sha256_file(path):
    """文件字节级 sha256（hex），与 draft_server 对 md 的指纹算法一致。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json_atomic(path, obj):
    """原子写旁车：tmp + os.replace，避免写一半崩掉毁旁车。"""
    tmp = str(path) + ".tmp"
    with open(tmp, "wb") as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8"))
    os.replace(tmp, str(path))


def next_footage_id(state):
    """下一个 footage 条目 id（f01、f02…；已占用的编号往后顺延）。"""
    mx = 0
    for f in state.get("footage", []):
        m = re.fullmatch(r"f(\d+)", str(f.get("id", "")))
        if m:
            mx = max(mx, int(m.group(1)))
    return "f%02d" % (mx + 1)


# ---------------------------------------------------------------- 扫描


def scan_footage(root, footage_dir=""):
    """扫描素材文件，返回相对项目根的 posix 路径列表（排序稳定）。
    footage_dir 为空扫整个项目根；给相对目录则只扫它（目录不存在抛 ValueError）。
    """
    root = Path(root).resolve()
    base = (root / footage_dir) if footage_dir else root
    if not base.is_dir():
        raise ValueError(f"素材目录不存在: {base}")
    if root not in base.resolve().parents and base.resolve() != root:
        raise ValueError(f"素材目录必须落在项目根内: {base}")
    out = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and d not in SKIP_DIRS]
        for name in filenames:
            if Path(name).suffix.lower() in FOOTAGE_EXTS:
                rel = (Path(dirpath) / name).relative_to(root)
                out.append(rel.as_posix())  # 旁车里一律 posix 分隔，跨 agent 可读
    out.sort()
    return out


def reconcile(state, files):
    """把扫描结果挂进 state["footage"]（就地修改）。
    幂等：同相对路径已存在的条目跳过（大小写按平台：Windows 不分大小写）。
    只挂「文件名命中批注 id」的文件；未匹配的进报告，不进 footage。
    返回 (新增条目列表, 跳过数, 未匹配相对路径列表)。
    """
    ann_ids = [str(a.get("id", "")) for a in state.get("annotations", [])
               if a.get("id")]
    footage = state.setdefault("footage", [])
    seen = set()
    for f in footage:
        key = str(f.get("file", ""))
        seen.add(key.casefold() if os.name == "nt" else key)
    added, skipped, unmatched = [], 0, []
    for rel in files:  # files 已排序 → 新条目顺序稳定
        key = rel.casefold() if os.name == "nt" else rel
        if key in seen:
            skipped += 1
            continue
        hits = match_file_to_anns(Path(rel).name, ann_ids)
        if not hits:
            unmatched.append(rel)  # 未匹配：不挂接，留给报告
            continue
        entry = {"id": next_footage_id({"footage": footage + added}),
                 "file": rel, "ann_ids": hits,
                 "state": "candidate", "match": "filename", "note": ""}
        footage.append(entry)
        added.append(entry)
        seen.add(key)
    return added, skipped, unmatched


# ---------------------------------------------------------------- 时长探测
# ffprobe 可得则用 ffprobe；否则退回解析 `ffmpeg -i` 的 stderr（imageio_ffmpeg
# 自带的二进制只有 ffmpeg 没有 ffprobe——剪辑机器常见配置，见 silence_trim.py）。


def parse_ffmpeg_duration(stderr_text):
    """从 `ffmpeg -i` 输出里抠 Duration: HH:MM:SS.ms → 秒（float）；解析失败 None。"""
    m = re.search(r"Duration:\s*(\d+):(\d{2}):(\d{2}(?:\.\d+)?)", stderr_text)
    if not m:
        return None
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


_PROBE_BIN = None  # (ffprobe路径 或 None, ffmpeg路径 或 None)，进程内只发现一次


def _discover_probe_bins():
    global _PROBE_BIN
    if _PROBE_BIN is not None:
        return _PROBE_BIN
    ffprobe = shutil.which("ffprobe")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        try:  # imageio_ffmpeg 兜底（与 cut/scripts/silence_trim.py 同模式）
            import imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:  # noqa: BLE001 —— 没装也行，时长列留空而已
            ffmpeg = None
    if not ffprobe and ffmpeg:
        cand = Path(ffmpeg).with_name(
            "ffprobe.exe" if os.name == "nt" else "ffprobe")
        if cand.is_file():
            ffprobe = str(cand)
    _PROBE_BIN = (ffprobe, ffmpeg)
    return _PROBE_BIN


def probe_duration(path):
    """视频时长（秒）；图片/探测失败/无 ffmpeg 返回 None。外部二进制只经 subprocess。"""
    ffprobe, ffmpeg = _discover_probe_bins()
    if not (ffprobe or ffmpeg):
        return None
    try:
        if ffprobe:
            p = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=nw=1:nk=1", str(path)],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=15)
            if p.returncode == 0:
                try:
                    return float(p.stdout.strip())
                except ValueError:
                    return None
            return None
        p = subprocess.run([ffmpeg, "-i", str(path)], capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=15)
        return parse_ffmpeg_duration(p.stderr)
    except Exception:  # noqa: BLE001 —— 时长是锦上添花，任何失败都静默降级
        return None


# ---------------------------------------------------------------- 报告


def fmt_size(n):
    if n >= 1 << 20:
        return f"{n / (1 << 20):.1f} MB"
    if n >= 1 << 10:
        return f"{n / (1 << 10):.1f} KB"
    return f"{n} B"


def build_report(root, md_path, files, added, skipped, unmatched,
                 dry_run=False):
    """Markdown 回收报告：汇总 + 已挂接 + 未匹配素材表（建议列留给 AI 填）。"""
    lines = []
    lines.append("# 素材回收报告")
    lines.append("")
    lines.append(f"- 项目根：`{Path(root).resolve()}`")
    lines.append(f"- 定稿：`{Path(md_path).name}`")
    lines.append(f"- 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                 + ("（--dry-run 预览，未写任何文件）" if dry_run else ""))
    lines.append(f"- 汇总：素材 {len(files)} 个"
                 f"（新挂接 {len(added)} · 已存在跳过 {skipped}"
                 f" · 未匹配 {len(unmatched)}）")
    lines.append("")
    if added:
        lines.append("## 本次已挂接（文件名精确匹配）")
        lines.append("")
        lines.append("| 批注 | 素材 | 匹配 |")
        lines.append("| --- | --- | --- |")
        for e in added:
            lines.append(f"| {'、'.join(e['ann_ids'])} | `{e['file']}` "
                         f"| {e['match']} |")
        lines.append("")
    if unmatched:
        lines.append("## 未匹配素材（「建议」列留给 AI 填：抽帧看画面/读 transcripts"
                     "对口播后写 `建议文件名→批注id，ai:置信度`）")
        lines.append("")
        lines.append("| 素材 | 大小 | 时长 | 建议 |")
        lines.append("| --- | --- | --- | --- |")
        for rel in unmatched:
            fp = Path(root) / rel
            try:
                size = fmt_size(fp.stat().st_size)
            except OSError:
                size = "-"
            dur = "-"
            if Path(rel).suffix.lower() in VIDEO_EXTS:
                secs = probe_duration(fp)
                if secs is not None:
                    dur = f"{secs:.1f}s"
            lines.append(f"| `{rel}` | {size} | {dur} |  |")
        lines.append("")
    else:
        lines.append("## 未匹配素材")
        lines.append("")
        lines.append("（无——所有素材都按文件名挂上了批注）")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------- 入口


def run(root, footage_dir="", dry_run=False, md_hint="", out=sys.stdout):
    """跑一遍回收匹配。返回退出码（0 成功 / 1 失败）。"""
    root = Path(root)
    if not root.is_dir():
        print(f"[素材回收] 项目根不存在: {root}", file=sys.stderr)
        return 1
    try:
        md_path, sidecar_path = find_sidecar(root, md_hint)
    except ValueError as e:
        print(f"[素材回收] {e}", file=sys.stderr)
        return 1

    state = json.loads(Path(sidecar_path).read_text(encoding="utf-8"))
    if not isinstance(state, dict) or state.get("version") != 1:
        print(f"[素材回收] 旁车不是 version 1 schema，拒收: {sidecar_path}",
              file=sys.stderr)
        return 1

    # 定稿指纹校验：md 被外部动过就拒写（--dry-run 只看不动，放行）
    src_sha = str(state.get("source_sha256", ""))
    cur_sha = sha256_file(md_path)
    if src_sha and cur_sha != src_sha and not dry_run:
        print(f"[素材回收] 定稿 md 与旁车指纹不符（md 可能被外部改动），拒写。\n"
              f"  旁车 source_sha256 = {src_sha}\n"
              f"  当前 md sha256     = {cur_sha}", file=sys.stderr)
        return 1
    if not src_sha:
        print("[素材回收] 警告：旁车缺 source_sha256，跳过指纹校验", out)

    try:
        files = scan_footage(root, footage_dir)
    except ValueError as e:
        print(f"[素材回收] {e}", file=sys.stderr)
        return 1
    added, skipped, unmatched = reconcile(state, files)

    report = build_report(root, md_path, files, added, skipped, unmatched,
                          dry_run)

    print(f"[素材回收] 旁车: {sidecar_path}", out)
    print(f"[素材回收] 扫描素材 {len(files)} 个"
          f"（目录: {footage_dir or '整个项目根'}）"
          f"→ 新挂接 {len(added)} · 跳过 {skipped} · 未匹配 {len(unmatched)}",
          out)

    if dry_run:
        print(report, out)
        print("[素材回收] --dry-run 结束（未写任何文件）", out)
        return 0

    if added:
        write_json_atomic(sidecar_path, state)
    report_path = root / REPORT_NAME
    with open(report_path, "wb") as f:
        f.write(report.encode("utf-8"))
    print(f"[素材回收] 报告: {report_path}", out)
    return 0


def main(argv=None):
    if os.name == "nt":
        try:  # Windows 控制台中文不炸
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description="拍摄素材回收匹配器（文件名精确匹配 → 旁车 footage）")
    ap.add_argument("项目根", help="定稿 md + shoot.json + 素材所在目录树")
    ap.add_argument("--footage-dir", default="",
                    help="只扫这个相对目录（缺省扫整个项目根）")
    ap.add_argument("--dry-run", action="store_true",
                    help="只打印报告，不写旁车、不落报告文件")
    ap.add_argument("--md", default="",
                    help="多份 *.shoot.json 时指定定稿 md 消歧")
    args = ap.parse_args(argv)
    return run(args.项目根, args.footage_dir, args.dry_run, args.md)


if __name__ == "__main__":
    sys.exit(main())
