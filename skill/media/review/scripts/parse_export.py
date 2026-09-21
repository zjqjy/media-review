#!/usr/bin/env python3
"""抖音创作中心导出 xlsx → AI 友好文本（md 表格），供复盘直接读取。

用法：
  python parse_export.py <xlsx路径或目录> [--config xxx]

处理 <目录> 时递归找 *.xlsx，逐个转换，在同目录生成同名 .md（已存在且比 xlsx 新则跳过）。
识别两类导出文件（按表头特征，不按文件名——用户改过名也能认）：
  - 作品列表导出（含"作品名称"列）→ 每作品一行，字段归一成复盘快照口径
  - 全量指标导出（含"日期"列）→ 按天汇总表
零第三方依赖：xlsx 是 zip+xml，标准库解。openpyxl 不需要。
"""
import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def col_letters(cell_ref):
    return re.match(r"([A-Z]+)", cell_ref).group(1)


def col_index(letters):
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_xlsx(path):
    """返回 rows: list[list[str]]，空单元格补 ''。零依赖解析 sheet1 + sharedStrings。"""
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", NS):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
        sheet_name = next(n for n in z.namelist() if re.fullmatch(r"xl/worksheets/sheet1?\.xml", n))
        root = ET.fromstring(z.read(sheet_name))
        rows = []
        for row in root.iter(f"{{{NS['m']}}}row"):
            cells = []
            for c in row.findall("m:c", NS):
                idx = col_index(col_letters(c.get("r", "A1")))
                while len(cells) < idx:
                    cells.append("")
                t = c.get("t")
                if t == "s":
                    v = c.find("m:v", NS)
                    val = shared[int(v.text)] if v is not None and v.text else ""
                elif t == "inlineStr":
                    val = "".join(tt.text or "" for tt in c.iter(f"{{{NS['m']}}}t"))
                else:
                    v = c.find("m:v", NS)
                    val = v.text if v is not None and v.text else ""
                cells.append(val)
            rows.append(cells)
        width = max(len(r) for r in rows)
        return [r + [""] * (width - len(r)) for r in rows]


# 数值列 → 复盘快照口径的归一化标签
WORK_COLS = {
    "作品名称": "标题", "发布时间": "发布时间", "播放量": "播放",
    "点赞量": "点赞", "分享量": "分享", "评论量": "评论",
    "收藏量": "收藏", "主页访问量": "主页访问", "粉丝增量": "涨粉",
    "完播率": "完播率", "5s完播率": "5s完播率", "2s跳出率": "2s跳出率",
    "封面点击率": "封面点击率", "平均播放时长": "平均播放时长",
}


def pct(v):
    """裸小数 0.010798 → '1.08%'；已是百分号串原样；'-' 保留。"""
    v = v.strip()
    if not v or v == "-":
        return v or "-"
    try:
        return f"{float(v) * 100:.2f}%"
    except ValueError:
        return v


def title_short(s, n=40):
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[:n] + "…"


def fmt_worklist(rows):
    header, out = rows[0], ["## 作品列表导出（单作品全指标）", ""]
    keep = [(i, WORK_COLS[h]) for i, h in enumerate(header) if h in WORK_COLS]
    body = [[lab for _, lab in keep]]
    for r in rows[1:]:
        if not any(c.strip() for c in r):
            continue
        rec = {lab: r[i] for i, lab in keep}
        for k in ("完播率", "5s完播率", "2s跳出率", "封面点击率"):
            if k in rec:
                rec[k] = pct(rec[k])
        if "平均播放时长" in rec:
            v = rec["平均播放时长"]
            if re.fullmatch(r"\d+(\.\d+)?", v):
                rec["平均播放时长"] = f"{float(v):.1f}s"
        body.append([title_short(rec.get(lab, ""), 36) if lab == "标题" else rec.get(lab, "-") or "-" for _, lab in keep])
    out.append(md_table(body))
    out += ["", "> 裸数字经归一：比率已转百分数，'-' 为平台未提供"]
    return "\n".join(out)


def fmt_daily(rows):
    header, out = rows[0], ["## 全量指标导出（按天汇总）", ""]
    idx_pct = {i for i, h in enumerate(header) if ("率" in h)}
    body = [header]
    for r in rows[1:]:
        if not any(c.strip() for c in r):
            continue
        body.append([pct(c) if i in idx_pct else c for i, c in enumerate(r)])
    out.append(md_table(body))
    return "\n".join(out)


def md_table(rows):
    rows = [[c.replace("|", "\\|").replace("\n", " ") for c in r] for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * len(rows[0])]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(out)


def convert(xlsx_path):
    rows = read_xlsx(xlsx_path)
    if not rows:
        return None
    header = rows[0]
    if "作品名称" in header:
        return fmt_worklist(rows)
    if "日期" in header:
        return fmt_daily(rows)
    return None  # 不认识的导出格式，留给 AI 直接读


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="xlsx 文件或目录")
    ap.add_argument("--config", help=argparse.SUPPRESS)
    ap.add_argument("--stdout", action="store_true", help="打印到 stdout 不落盘")
    args = ap.parse_args()

    p = Path(args.target)
    files = sorted(p.rglob("*.xlsx")) if p.is_dir() else [p]
    if not files:
        print(f"没找到 xlsx：{p}", file=sys.stderr)
        return 1
    for f in files:
        if f.name.startswith("~$"):
            continue
        text = convert(f)
        md = f.with_suffix(".md")
        if text is None:
            print(f"跳过（不认识的表头）：{f}")
            continue
        if md.exists() and md.stat().st_mtime >= f.stat().st_mtime:
            print(f"跳过（已是最新）：{md.name}")
            continue
        if args.stdout:
            print(f"===== {f.name} =====")
            print(text)
        else:
            md.write_text(text, encoding="utf-8")
            print(f"已生成：{md}")


if __name__ == "__main__":
    sys.exit(main() or 0)
