#!/usr/bin/env python3
"""blog_plan.py — blog 子技能计划文件（blog_plan.json）schema 与校验（纯函数，无副作用）。

blog_plan.json 是 /media blog 全链路的单一事实源：站点发文（S7-B/C）与公众号排版（S7-D）
都从它取期数/标题/slug/配图清单/链接/公众号元数据。落位约定（跟 publish 的旁车惯例）：
旁车放成片同目录 `<成片名>.blog_plan.json`，preview 放 `<成片目录>/blog_preview/`。

schema（模块内 PLAN_SCHEMA 同步维护）:
{
  "slug": "esp32-lcd-screen",          # 站点文件名 stem：^[a-z0-9][a-z0-9-]*$（URL 即 /年/月/日/slug/）
  "episode": "第5期",
  "title": "文章标题（=frontmatter title）",
  "date": "YYYY-MM-DD",
  "categories": ["AI工具"],            # 恰好 1 个（站点分类卡按单分类统计）
  "tags": ["ESP32", "AI"],
  "description": "一句话摘要（可选）",
  "video":  "成片.mp4 绝对路径",
  "srt":    "<成片>_字幕.srt 绝对路径（post final_sub 产物，选帧时间轴来源）",
  "transcript": "第N期_标题_逐字稿.md 绝对路径",
  "frames": [                          # AI 选帧清单（Q3 定音：AI 全自动，人兜底改这份再重抽）
    {"t": 63.5,                       # 秒（成片时间轴）
     "name": "install-wizard",         # 文件名段：^[a-z0-9][a-z0-9-]*$，全清单唯一；不带序号（落盘自动加 NN-）
     "alt": "安装引导界面",             # 必填（无障碍+图挂时占位）
     "caption": "双击安装包，跟着引导走完（可空）",
     "section": "第一步：安装 ego lite"}  # 所属小节标题（预览/排版定位用，可空）
  ],
  "links": [                           # 需新增进 links.yml 的条目（可空；已有 key 不重复加）
    {"key": "ego_lite_download", "label": "ego lite 官网下载",
     "url": "https://...", "type": "official"}
  ],
  "gzh": {                             # 公众号排版段（S7-D 用）
    "theme": "minimal-mono",           # vendor 主题名（assets/themes/<theme>.json）
    "author": "阿程",
    "digest": "摘要 ≤120 字"
  }
}
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
NAME_RE = SLUG_RE
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

GZH_TITLE_MAX = 64          # 公众号标题硬上限
GZH_DIGEST_MAX = 120        # 公众号摘要硬上限


def _err(errors: list[str], where: str, msg: str) -> None:
    errors.append(f"[{where}] {msg}")


def validate_plan(plan: dict) -> list[str]:
    """返回错误清单（空=通过）。只查 schema 语义，不查文件存在性（存在性归 frame_pick/site_check）。"""
    e: list[str] = []
    slug = plan.get("slug", "")
    if not SLUG_RE.match(slug):
        _err(e, "slug", f"非法（须 ^[a-z0-9][a-z0-9-]*$，中文会生成乱码 URL）: {slug!r}")
    if not plan.get("episode"):
        _err(e, "episode", "缺失（期数，如 第5期）")
    if not plan.get("title"):
        _err(e, "title", "缺失")
    date = plan.get("date", "")
    if not DATE_RE.match(date):
        _err(e, "date", f"格式须 YYYY-MM-DD: {date!r}")
    cats = plan.get("categories")
    if not isinstance(cats, list) or len(cats) != 1 or not cats[0]:
        _err(e, "categories", f"恰好 1 个（站点分类卡按单分类统计）: {cats!r}")
    tags = plan.get("tags")
    if not isinstance(tags, list) or not tags:
        _err(e, "tags", "至少 1 个")
    for k in ("video", "srt", "transcript"):
        if not plan.get(k):
            _err(e, k, "缺失（收料三件：成片/字幕 srt/逐字稿）")

    frames = plan.get("frames", [])
    if not isinstance(frames, list):
        _err(e, "frames", "须为清单")
        frames = []
    seen_names: set[str] = set()
    for i, f in enumerate(frames):
        w = f"frames[{i}]"
        try:
            t = float(f.get("t"))
        except (TypeError, ValueError):
            _err(e, w, f"t 须为秒数: {f.get('t')!r}")
            continue
        if t < 0:
            _err(e, w, f"t 不能为负: {t}")
        name = f.get("name", "")
        if not NAME_RE.match(name):
            _err(e, w, f"name 非法: {name!r}")
        elif name in seen_names:
            _err(e, w, f"name 重复: {name}")
        seen_names.add(name)
        if not f.get("alt"):
            _err(e, w, "alt 缺失（无障碍+挂图占位）")

    links = plan.get("links", [])
    if not isinstance(links, list):
        _err(e, "links", "须为清单")
        links = []
    seen_keys: set[str] = set()
    for i, lk in enumerate(links):
        w = f"links[{i}]"
        key = lk.get("key", "")
        if not KEY_RE.match(key):
            _err(e, w, f"key 非法（^[a-z0-9][a-z0-9_-]*$）: {key!r}")
        elif key in seen_keys:
            _err(e, w, f"key 重复: {key}")
        seen_keys.add(key)
        for req in ("label", "url"):
            if not lk.get(req):
                _err(e, w, f"{req} 缺失")

    gzh = plan.get("gzh")
    if gzh is not None:
        if not isinstance(gzh, dict):
            _err(e, "gzh", "须为对象")
        else:
            if not gzh.get("theme"):
                _err(e, "gzh.theme", "缺失（vendor 主题名）")
            digest = gzh.get("digest", "")
            if len(digest) > GZH_DIGEST_MAX:
                _err(e, "gzh.digest", f"超 {GZH_DIGEST_MAX} 字（现 {len(digest)}）")
    return e


def frame_filename(order: int, name: str) -> str:
    """站点图片文件名：NN-<name>.jpg（NN 两位序号，落 source/images/<slug>/）。"""
    return f"{order:02d}-{name}.jpg"


def plan_from_file(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="blog_plan.json 校验")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--quiet", action="store_true", help="通过时不输出")
    a = ap.parse_args(argv)
    try:
        plan = plan_from_file(a.plan)
    except Exception as exc:
        print(f"FAIL 读取计划: {exc}")
        return 2
    errors = validate_plan(plan)
    if errors:
        print("\n".join(f"FAIL {x}" for x in errors))
        return 1
    if not a.quiet:
        print(f"OK plan 合法：slug={plan.get('slug')} frames={len(plan.get('frames', []))} "
              f"links={len(plan.get('links', []))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
