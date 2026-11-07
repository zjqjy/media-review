#!/usr/bin/env python3
"""publish_plan.py — 发布确认单 + 字数校验 + 发布记录（S6-B；纯标准库，零依赖，不碰浏览器）

职责边界：**只管发前的纸上功夫和发后的纸上落档**——浏览器里的实际发布由对话 agent
按 publish/SKILL.md 的 SOP 用 ego-browser 干，本模块绝不 import 任何浏览器库。

三件事：
  1. validate_draft / validate_plan → 按 platforms.json 常量表校验字数/必填/封面，
     超限给「人话错误清单」（超几字、怎么修），不上车硬截
  2. build_confirmation → 三平台确认单 markdown（✅/❌ 逐平台标注、字数计数/上限），
     用户逐平台改，全绿+用户说「发」才进浏览器阶段
  3. record_publish / load_records → 发布记录落 `<成片>.publish.json`（与成片同目录
     同名，跟着素材走不另立花名册；同平台多次发布=多条含时间戳）

plan.json 结构（agent 写、本模块读）：
    {
      "video":  "D:/…/成片.mp4",
      "covers": {"douyin": "…/cover_9x16.png", "bilibili": "…/cover_16x9.png",
                 "xhs": "…/cover_3x4.png"},
      "drafts": {"douyin": {"title": "…", "desc": "…", "tags": ["…"],
                 "topics": ["…"],         // 可选：真话题（表单里挂芯片，不是正文 # 文字）
                 "original": true,         // 可选：原创声明开关（缺省=不填，平台记默认）
                 "declare": "自制",        // 可选：内容类型声明（自制/转载…）
                 "collection": "合集名"},  // 可选：加入合集（有些视频要归合集）
                 …}
    }

字数口径：len()（中文一字=1）；platforms.json 里 verified=false 的上限是待实测占位，
校验照常生效（保守收紧），dry-run 实测后回写常量表并置 verified=true。

用法：
    python publish_plan.py check   --plan plan.json     # 校验；非0退出=有问题
    python publish_plan.py confirm --plan plan.json     # 渲染确认单 markdown
    python publish_plan.py record  --video 成片.mp4 --platform douyin
                        --title "…" [--url …] [--note …]   # 落一条发布记录
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

PLATFORMS_FILE = Path(__file__).resolve().parent.parent / "platforms.json"


def load_platforms(path: Path | None = None) -> dict:
    """读常量表 → {platform_id: 平台知识}；文件缺失给人话。"""
    p = Path(path) if path else PLATFORMS_FILE
    if not p.exists():
        raise FileNotFoundError(f"常量表缺失：{p}（publish 子技能不完整，查装位）")
    return json.loads(p.read_text(encoding="utf-8"))["platforms"]


def validate_draft(pid: str, draft: dict, platforms: dict | None = None) -> list[str]:
    """单平台草稿校验 → 人话错误清单（空清单=过）。"""
    plats = platforms if platforms is not None else load_platforms()
    if pid not in plats:
        return [f"未知平台 {pid}（常量表里有：{'/'.join(plats)}）"]
    p = plats[pid]
    errors: list[str] = []
    title = (draft.get("title") or "").strip()
    desc = (draft.get("desc") or "").strip()
    tags = draft.get("tags") or []
    if not title:
        errors.append(f"{p['name']}：标题不能为空")
    tmax = p.get("title", {}).get("max_chars")
    if tmax and title and len(title) > tmax:
        errors.append(
            f"{p['name']}：标题 {len(title)} 字超上限 {tmax}（超 {len(title) - tmax} 字，"
            f"压缩改写，别硬截断丢信息）")
    dmax = p.get("desc", {}).get("max_chars")
    if dmax and desc and len(desc) > dmax:
        errors.append(f"{p['name']}：简介 {len(desc)} 字超上限 {dmax}（超 {len(desc) - dmax} 字）")
    tmax_count = p.get("tags", {}).get("max_count")
    if tmax_count and len(tags) > tmax_count:
        errors.append(f"{p['name']}：标签 {len(tags)} 个超上限 {tmax_count} 个")
    return errors


def validate_plan(plan: dict, platforms: dict | None = None) -> dict[str, list[str]]:
    """整单校验 → {pid: [错误…]}（只含有问题的平台）；封面必设平台查文件真实存在。"""
    plats = platforms if platforms is not None else load_platforms()
    drafts = plan.get("drafts") or {}
    covers = plan.get("covers") or {}
    out: dict[str, list[str]] = {}
    for pid, p in plats.items():
        errs = validate_draft(pid, drafts.get(pid) or {}, plats)
        cover = covers.get(pid)
        if cover:
            if not Path(cover).exists():
                errs.append(f"{p['name']}：封面文件不存在：{cover}")
        elif p.get("cover_required"):
            errs.append(f"{p['name']}：封面必设（可用 cover 子技能产物，对应画幅见常量表 cover_hint）")
        if errs:
            out[pid] = errs
    return out


def build_confirmation(plan: dict, platforms: dict | None = None) -> str:
    """渲染三平台确认单 markdown：✅/❌ 标注 + 字数计数/上限 + 问题清单。"""
    plats = platforms if platforms is not None else load_platforms()
    errors = validate_plan(plan, plats)
    lines = ["# 📋 发布确认单", "", f"视频：`{plan.get('video', '?')}`", ""]
    for pid, p in plats.items():
        d = (plan.get("drafts") or {}).get(pid) or {}
        cover = (plan.get("covers") or {}).get(pid) or "（无）"
        errs = errors.get(pid) or []
        title = (d.get("title") or "").strip()
        desc = (d.get("desc") or "").strip()
        tags = d.get("tags") or []
        tmax = p.get("title", {}).get("max_chars")
        dmax = p.get("desc", {}).get("max_chars")
        tinfo = f"{len(title)}/{tmax}" if tmax else f"{len(title)}"
        dinfo = f"{len(desc)}/{dmax}" if dmax else f"{len(desc)}"
        lines += [
            f"## {'❌' if errs else '✅'} {p['name']}",
            f"- 标题（{tinfo} 字）：{title or '（空）'}",
            f"- 简介（{dinfo} 字）：{desc or '（空）'}",
        ]
        if d.get("topics"):
            lines.append(f"- 话题（挂芯片）：{'、'.join(d['topics'])}")
        if tags:
            lines.append(f"- 标签：{'、'.join(tags)}")
        if d.get("original") is not None:
            lines.append(f"- 原创声明：{'✅ 开' if d['original'] else '❌ 关'}")
        if d.get("declare"):
            lines.append(f"- 内容类型声明：{d['declare']}")
        if d.get("collection"):
            lines.append(f"- 合集：{d['collection']}")
        lines.append(f"- 封面：`{cover}`")
        lines.append(f"- 发布入口：{p.get('creator_entry', '?')}")
        if errs:
            lines.append("- **待修**：")
            lines += [f"  - {e}" for e in errs]
        lines.append("")
    lines.append("━━━ 改哪条直接说；三平台都 OK 请回复「发」━━━")
    return "\n".join(lines)


def record_path(video: str | Path) -> Path:
    """发布记录与成片同目录同名：<成片>.publish.json。"""
    return Path(video).with_suffix(".publish.json")


def record_publish(video: str | Path, pid: str, title: str, url: str | None = None,
                   note: str = "", *, now: str | None = None) -> Path:
    """追加一条发布记录；同平台多次发布=多条（平台改稿重发是正常事）。"""
    rp = record_path(video)
    if rp.exists():
        data = json.loads(rp.read_text(encoding="utf-8"))
    else:
        data = {"version": 1, "video": str(video), "records": []}
    data["records"].append({
        "platform": pid,
        "title": title,
        "url": url,
        "note": note,
        "time": now or time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    rp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rp


def load_records(video: str | Path) -> list[dict]:
    rp = record_path(video)
    if not rp.exists():
        return []
    return json.loads(rp.read_text(encoding="utf-8")).get("records", [])


def main(argv: list[str] | None = None) -> int:
    if os.name == "nt":
        try:  # Windows 控制台中文不炸
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description="publish：发布确认单/字数校验/发布记录")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="校验 plan.json（非0退出=有问题）")
    c.add_argument("--plan", required=True)
    f = sub.add_parser("confirm", help="渲染确认单 markdown")
    f.add_argument("--plan", required=True)
    r = sub.add_parser("record", help="落一条发布记录到 <成片>.publish.json")
    r.add_argument("--video", required=True)
    r.add_argument("--platform", required=True)
    r.add_argument("--title", required=True)
    r.add_argument("--url", default=None)
    r.add_argument("--note", default="")
    a = ap.parse_args(argv)
    if a.cmd in ("check", "confirm"):
        plan = json.loads(Path(a.plan).read_text(encoding="utf-8"))
        if a.cmd == "check":
            errs = validate_plan(plan)
            for pid, es in errs.items():
                for e in es:
                    print(f"❌ {e}")
            if errs:
                return 1
            print("✅ plan 校验全绿（字数/封面/必填全过）")
            return 0
        print(build_confirmation(plan))
        return 0
    rp = record_publish(a.video, a.platform, a.title, a.url, a.note)
    print(f"✅ 已记录 → {rp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
