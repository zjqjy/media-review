#!/usr/bin/env python3
"""site_check.py — 站点发文规范校验（S7-C 核心）：发文前把 PersonalWebsite 的硬规矩过一遍。

站点规矩（来源：vault 维护手册卡 + 站点仓库实践）：
  - 文件名只用英文/数字/连字符（URL=/年/月/日/文件名/，中文名出乱码 URL）
  - frontmatter：title/date(YYYY-MM-DD)/categories 恰好 1 个/tags ≥1；description 可选
  - 下载链接不贴裸 URL：正文用 {% link "key" %}，key 须已注册在 source/_data/links.yml
  - 图片引用 /images/<slug>/x.jpg 须真实存在于 source/images/<slug>/
  - 网盘裸链（pan.baidu/lanzou/123pan 等）→ 警告（--strict 升级为失败）
  - images 目录孤儿文件（有图没引用）→ 警告
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml  # type: ignore
    _HAS_YAML = True
except Exception:  # pragma: no cover
    _HAS_YAML = False

SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LINK_TAG_RE = re.compile(r'\{%\s*link\s+"([^"]+)"\s*%\}')
IMG_RE = re.compile(r"(?:!\[[^\]]*\]\(|<img[^>]*src=\")(/images/[A-Za-z0-9-]+/[^\"))\s]+)")
PAN_RE = re.compile(r"(pan\.baidu\.com|lanzou|123pan|alipan\.com|quark\.cn)")

FM_KEYS = ("title", "date", "categories", "tags")


def split_frontmatter(md_text: str) -> tuple[dict, str]:
    """拆 frontmatter（--- 围栏）与正文。有 pyyaml 用 yaml，否则极简解析（title/date 纯量+块列表）。"""
    if not md_text.startswith("---"):
        raise SystemExit("FAIL 文章缺 frontmatter（须以 --- 开头）")
    end = md_text.find("\n---", 3)
    if end < 0:
        raise SystemExit("FAIL frontmatter 未闭合")
    fm_text = md_text[3:end].strip("\n")
    body = md_text[end + 4:].lstrip("\n")
    if _HAS_YAML:
        data = yaml.safe_load(fm_text)
        if not isinstance(data, dict):
            raise SystemExit("FAIL frontmatter 解析结果不是映射")
        return data, body
    # 极简兜底：key: value / key: 块列表（- item）
    data: dict = {}
    cur_list: list | None = None
    for line in fm_text.splitlines():
        if re.match(r"^\s*-\s+", line) and cur_list is not None:
            cur_list.append(line.strip()[2:].strip())
            continue
        m = re.match(r"^([A-Za-z_]+)\s*:\s*(.*)$", line)
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        if v == "":
            cur_list = []
            data[k] = cur_list
        else:
            cur_list = None
            if v.startswith("[") and v.endswith("]"):
                data[k] = [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
            else:
                data[k] = v.strip("'\"")
    return data, body


def load_link_keys(site_root: Path) -> set[str] | None:
    """links.yml 全量 key 集合；解析不了返回 None（调用方转警告）。"""
    p = site_root / "source" / "_data" / "links.yml"
    if not p.is_file():
        return None
    text = p.read_text(encoding="utf-8")
    if _HAS_YAML:
        data = yaml.safe_load(text)
        keys: set[str] = set()
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict) and item.get("key"):
                            keys.add(str(item["key"]))
                elif isinstance(v, dict) and v.get("key"):
                    keys.add(str(v["key"]))
        return keys
    # 极简兜底：抓所有 "- key: xxx" 行
    return {m.group(1) for m in re.finditer(r"-\s+key:\s*([A-Za-z0-9_-]+)", text)}


def check_post(post: Path, site_root: Path, strict: bool = False) -> int:
    fails: list[str] = []
    warns: list[str] = []
    slug = post.stem
    if not SLUG_RE.match(slug):
        fails.append(f"文件名非法（只许英文/数字/连字符，中文出乱码 URL）: {slug}")
    text = post.read_text(encoding="utf-8")
    fm, body = split_frontmatter(text)

    for k in FM_KEYS:
        if k not in fm or fm[k] in (None, "", []):
            fails.append(f"frontmatter 缺 {k}")
    date = fm.get("date")
    if date is not None and not DATE_RE.match(str(date)):
        fails.append(f"date 格式须 YYYY-MM-DD: {date!r}")
    cats = fm.get("categories")
    if isinstance(cats, list) and len(cats) != 1:
        fails.append(f"categories 恰好 1 个: {cats!r}")
    if isinstance(fm.get("tags"), list) and not fm["tags"]:
        fails.append("tags 为空")
    if len(re.sub(r"\s", "", body)) < 200:
        fails.append(f"正文过短（去空白后 {len(re.sub(chr(92)+'s','',body))} 字符 <200）")

    link_keys = load_link_keys(site_root)
    used_links = set(LINK_TAG_RE.findall(body))
    if link_keys is None:
        warns.append("links.yml 解析不了（无 pyyaml 且兜底失败），{% link %} key 未校验")
    else:
        for k in used_links:
            if k not in link_keys:
                fails.append(f'{{% link "{k}" %}} 未注册在 links.yml')

    slug_dir = site_root / "source" / "images" / slug
    referenced: set[str] = set()
    for m in IMG_RE.finditer(text):
        rel = m.group(1)  # /images/<slug>/x.jpg
        parts = rel.strip("/").split("/", 2)  # [images, <slug>, <file>]
        if len(parts) != 3 or parts[0] != "images" or parts[1] != slug:
            fails.append(f"图片引用跨文章目录（应 /images/{slug}/…）: {rel}")
            continue
        referenced.add(parts[2])
        if not (site_root / "source" / "images" / parts[1] / parts[2]).is_file():
            fails.append(f"图片不存在: {rel}")
    if slug_dir.is_dir():
        for f in slug_dir.iterdir():
            if f.is_file() and f.name not in referenced:
                warns.append(f"孤儿图（未被正文引用）: /images/{slug}/{f.name}")

    for line_no, line in enumerate(body.splitlines(), start=1):
        if PAN_RE.search(line) and "{% link" not in line:
            warns.append(f"正文疑似裸网盘链（应走 links.yml {{% link %}}）: L{line_no}")

    for w in warns:
        print(f"WARN {w}")
    if fails:
        print("\n".join(f"FAIL {x}" for x in fails))
        return 1
    if strict and warns:
        print("FAIL --strict 模式下警告视为失败")
        return 1
    print(f"OK {post.name} 规范通过（{len(warns)} 警告）")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="站点发文规范校验")
    ap.add_argument("--post", required=True, help="source/_posts/<slug>.md 路径")
    ap.add_argument("--site-root", required=True, help="PersonalWebsite 仓库根")
    ap.add_argument("--strict", action="store_true", help="警告也判失败")
    a = ap.parse_args(argv)
    post = Path(a.post)
    if not post.is_file():
        print(f"FAIL 文章不存在: {post}")
        return 2
    return check_post(post, Path(a.site_root), strict=a.strict)


if __name__ == "__main__":
    sys.exit(main())
