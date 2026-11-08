#!/usr/bin/env python3
"""gzh_pack.py — S7-D 公众号排版打包：文章 md → 内联样式 HTML + 图片清单（ego 草稿驱动器的输入）。

管线：剥 frontmatter → 正文里站点图片路径改写为占位符（`[图N]` 独立段落标记）→
调 vendor html_converter.py（jiji262 引入件，主题 JSON 内联样式）→ 出三个文件：
  gzh.html     粘贴稿：占位符段落 `⟦图N:NN-name⟧` 代替 <img>——图片由驱动器逐张
               （定位占位段→光标落位→删占位→编辑器图片按钮→setInputFiles→确认）插入，
               因为公众号编辑器不吃带本地/外链 src 的 img，只吃自己 CDN 的图
  images.json  有序图片清单 [{n, name, file, alt}]（driver 按序上传）
  report.txt   标题/摘要字数体检 + 图片清单摘要

字数红线：公众号标题 ≤64（GZH_TITLE_MAX），摘要 ≤120（GZH_DIGEST_MAX）。
主题缺省 minimal-mono（技术教程向，jiji262 主题表 tech 默认）。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blog_plan import (GZH_DIGEST_MAX, GZH_TITLE_MAX, plan_from_file,  # noqa: E402
                       validate_plan)
from site_check import split_frontmatter  # noqa: E402

VENDOR_CONVERTER = (Path(__file__).resolve().parent.parent / "vendor" /
                    "wechat-publisher" / "scripts" / "html_converter.py")
SITE_IMG_RE = re.compile(r"!\[([^\]]*)\]\(/images/([A-Za-z0-9-]+)/([^)]+)\)")
PLACEHOLDER = "⟦图{n}:{name}⟧"


def rewrite_images(body: str, frames_dir: Path, images: list[dict]) -> str:
    """md 图片语法 → 占位段落（独立成行，driver 定位用）；同时生成 images.json 清单。"""
    slug_dir = frames_dir

    def sub(m: re.Match) -> str:
        alt, slug, fname = m.group(1), m.group(2), m.group(3)
        n = len(images) + 1
        images.append({"n": n, "name": fname, "file": str(slug_dir / fname), "alt": alt})
        return f"\n\n{PLACEHOLDER.format(n=n, name=fname)}\n\n"

    return SITE_IMG_RE.sub(sub, body)


def run_converter(md_path: Path, theme: str, out_html: Path) -> None:
    if not VENDOR_CONVERTER.is_file():
        raise SystemExit(f"FAIL vendor 转换器缺失: {VENDOR_CONVERTER}（装位同步漏了？）")
    r = subprocess.run(
        [sys.executable, str(VENDOR_CONVERTER), str(md_path),
         "--theme", theme, "-o", str(out_html)],
        capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not out_html.is_file():
        raise SystemExit(f"FAIL html_converter 退出码 {r.returncode}: {(r.stderr or r.stdout)[:400]}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="md→公众号粘贴包（html+图片清单+体检）")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--post", required=True, help="站点 _posts/<slug>.md")
    ap.add_argument("--site-root", required=True, help="站点仓库根（定位图片实体）")
    ap.add_argument("--out", required=True, help="输出目录（建议 <成片目录>/gzh_pack/）")
    ap.add_argument("--theme", help="覆盖 plan.gzh.theme")
    a = ap.parse_args(argv)

    plan = plan_from_file(a.plan)
    errors = validate_plan(plan)
    if errors:
        print("\n".join(f"FAIL {x}" for x in errors))
        return 1
    slug = plan["slug"]
    theme = a.theme or (plan.get("gzh") or {}).get("theme", "minimal-mono")
    title = (plan.get("gzh") or {}).get("title") or plan["title"]
    digest = (plan.get("gzh") or {}).get("digest", "")
    author = (plan.get("gzh") or {}).get("author", "")

    post = Path(a.post)
    fm, body = split_frontmatter(post.read_text(encoding="utf-8"))
    frames_dir = Path(a.site_root) / "source" / "images" / slug
    images: list[dict] = []
    body_ph = rewrite_images(body, frames_dir, images)
    for img in images:
        if not Path(img["file"]).is_file():
            print(f"FAIL 图片实体不存在: {img['file']}")
            return 1

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    md_tmp = out / "_pack_source.md"
    md_tmp.write_text(body_ph, encoding="utf-8")
    html_out = out / "gzh.html"
    run_converter(md_tmp, theme, html_out)

    (out / "images.json").write_text(
        json.dumps(images, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"标题({len(title)}/{GZH_TITLE_MAX}): {title}",
        f"摘要({len(digest)}/{GZH_DIGEST_MAX}): {digest or '(空)'}",
        f"作者: {author or '(空)'}",
        f"主题: {theme}",
        f"图片 {len(images)} 张: " + ", ".join(i["name"] for i in images),
        f"占位符 {body_ph.count('⟦图')} 处（应与图片数一致）",
    ]
    if len(title) > GZH_TITLE_MAX:
        lines.append(f"FAIL 标题超 {GZH_TITLE_MAX} 字")
    if len(digest) > GZH_DIGEST_MAX:
        lines.append(f"FAIL 摘要超 {GZH_DIGEST_MAX} 字")
    report = "\n".join(lines)
    (out / "report.txt").write_text(report, encoding="utf-8")
    md_tmp.unlink(missing_ok=True)
    print(report)
    print(f"产物 {out}")
    return 0 if "FAIL" not in report else 1


if __name__ == "__main__":
    sys.exit(main())
