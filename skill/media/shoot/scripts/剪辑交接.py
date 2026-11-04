#!/usr/bin/env python3
"""剪辑交接.py — 补制任务生成 + cut 输入编译器（S2-D；纯标准库 CLI，零依赖）

职责边界（头脑风暴难点5选定方案）：**只做编排 + 输入准备**，把 shoot 旁车里
人工确认过的成果编译成 cut 认的输入；剪辑本体一律走 cut 现有规程，本模块绝不
碰 cut 脚本、不改定稿 md、不改素材本体（复制副本，shutil.copy2——素材可能被
用户继续整理，不能用硬链接绑死原件）。

两件事：
  1. generate_tasks(state)  → 按呈现批注**幂等**生成补制任务（显式生成，
     剪辑 AI 只消费不自作主张，R0-7）：
       - kind=ai 且 tasks 无同 ref 条目 → type=ai_type 原样（card/motion/aigen；
         other 映射为 reshoot，note 写「other 需人工定工具」）
       - kind=manual 且无任何 footage 关联 → type=reshoot（缺拍回摄任务）
       - 已存在的 ref 不重复生成；返回 (新增清单, 全部任务)
  2. compile_handoff(...)   → cut 输入编译：`<项目根>/05_剪辑交接/`
       - `素材/` 放 selected 素材的**复制**，命名 {ann_id}_{footage_id}_{原文件名}
         （同 ann 多段全放；一段素材挂多条批注时只复制一份，owner=批注顺序最前者）
       - `剪辑说明.md`：标题+生成时间+定稿名 → 「## 逐段清单」按批注顺序逐条
         （批注 → 已选素材+剪辑批注原文 → 补制任务引用）；无选用素材的批注
         归「## 缺口」段；尾部「## 给 cut 的输入说明」

定稿指纹纪律与素材回收一致：旁车 source_sha256 与当前 md 对不上就拒编译
（--dry-run 只看不动，放行）；旁车缺指纹只警告不拦死。

用法：
    python 剪辑交接.py <项目根> [--md 定稿md] [--dry-run]
    --md 缺省时自动找项目根下唯一含 .shoot.json 旁车的定稿 md（复用素材回收定位）
"""

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from 素材回收 import find_sidecar, sha256_file  # noqa: E402 —— 复用旁车定位/指纹

# 交接目录约定（cut 只吃这个目录，不回读定稿与旁车）
HANDOFF_DIRNAME = "05_剪辑交接"
FOOTAGE_SUBDIR = "素材"
HANDOFF_MD_NAME = "剪辑说明.md"

KIND_ICON = {"manual": "🎬", "ai": "🤖"}
TASK_ICON = {"reshoot": "🎥", "card": "🃏", "motion": "✨", "aigen": "🖼"}
KNOWN_AI_TYPES = ("card", "motion", "aigen")
OTHER_NOTE = "other 需人工定工具"

_ID_PAT = {"t": re.compile(r"^t(\d+)$"), "e": re.compile(r"^e(\d+)$")}


# ---------------------------------------------------------------- 任务生成


def next_id(items, prefix="t"):
    """下一个 {prefix}XX 编号 id（t01、e01…；已占用的编号往后顺延，不缩号不复用）。

    任务 id（t）与剪辑批注 id（e）共用这套顺延规则（shoot_server 的
    editnote upsert 也从这里拿 e 编号，保证两处语义一致）。
    """
    pat = _ID_PAT[prefix]
    mx = 0
    for it in items:
        m = pat.match(str(it.get("id", "")))
        if m:
            mx = max(mx, int(m.group(1)))
    return "%s%02d" % (prefix, mx + 1)


def _ai_task_type(ann):
    """AI 批注 → 任务 (type, note)。ai_type 原样透传；other/未知兜成 reshoot。"""
    ai_type = str(ann.get("ai_type", "") or "")
    if ai_type in KNOWN_AI_TYPES:
        return ai_type, ""
    return "reshoot", OTHER_NOTE


def generate_tasks(state):
    """按呈现批注幂等生成补制任务（就地追加进 state["tasks"]）。

    返回 (新增清单, 全部任务)。幂等：任一批注的 ref 已在 tasks 里就跳过——
    重跑一遍结果不变，绝不重复开单。
    """
    anns = state.get("annotations", [])
    tasks = state.setdefault("tasks", [])
    existing_refs = {str(t.get("ref", "")) for t in tasks}
    linked_anns = set()
    for f in state.get("footage", []):
        linked_anns.update(f.get("ann_ids", []) or [])

    added = []
    for a in anns:
        aid = str(a.get("id", ""))
        if not aid or aid in existing_refs:
            continue  # 已有任务（或没有 id）——幂等跳过
        if a.get("kind") == "ai":
            ttype, note = _ai_task_type(a)
        elif a.get("kind") == "manual" and aid not in linked_anns:
            ttype, note = "reshoot", ""  # 缺拍：回摄任务
        else:
            continue  # manual 且已有素材关联 → 不需要任务
        task = {"id": next_id(tasks + added, "t"), "type": ttype, "ref": aid,
                "state": "open", "output": ""}
        if note:
            task["note"] = note
        tasks.append(task)
        added.append(task)
    return added, tasks


# ---------------------------------------------------------------- 剪辑批注查找


def note_for_footage(state, footage_id):
    """某段素材的剪辑批注原文（同 footage_id 多条时取第一条；没有 → 空串）。"""
    for en in state.get("editNotes", []):
        if str(en.get("footage_id", "")) == str(footage_id):
            return str(en.get("note", ""))
    return ""


# ---------------------------------------------------------------- cut 输入编译


def _ann_headline(ann):
    """批注一行标题：quote 优先，没有就退整块提示（manual=拍什么 / ai=制作指令）。"""
    icon = KIND_ICON.get(str(ann.get("kind", "manual")), "🎬")
    quote = str(ann.get("quote", "") or "")
    if quote:
        return f"{ann.get('id')} {icon} 「{quote}」"
    if ann.get("kind") == "ai":
        brief = str(ann.get("ai_brief", "") or "") or "（无制作指令）"
        return f"{ann.get('id')} {icon} AI·{ann.get('ai_type', '?')}：{brief}"
    hint = str(ann.get("shoot_hint", "") or "") or "（无拍摄提示）"
    return f"{ann.get('id')} {icon} {hint}"


def _task_line(task):
    """补制任务引用一行：类型图标 + id · type · state · 产物。"""
    if not task:
        return ""
    out = str(task.get("output", "") or "") or "（产物未回填）"
    line = (f"{TASK_ICON.get(task.get('type', ''), '❓')} "
            f"补制任务 {task.get('id')} · {task.get('type')} · "
            f"{task.get('state', 'open')} · 产物：{out}")
    if task.get("note"):
        line += f"（{task['note']}）"
    return line


def build_handoff_md(md_name, anns, sel_by_ann, copied_by_fid, tasks_by_ref,
                     loose, missing_ids, mat_dir_abs, now_str):
    """编译剪辑说明.md 全文（纯函数，dry-run 与实跑共用同一份内容）。

    tasks_by_ref: {批注id → 任务dict}，逐段清单与缺口里引用补制任务用。
    """
    n_copied = sum(1 for c in copied_by_fid.values() if c["exists"])
    n_lost = len(copied_by_fid) - n_copied

    L = ["# 剪辑说明", "",
         f"- 定稿：{md_name}",
         f"- 生成时间：{now_str}",
         f"- 汇总：逐段 {len(anns) - len(missing_ids)} · "
         f"缺口 {len(missing_ids)} · 已复制素材 {n_copied} 段"
         + (f"（另有 {n_lost} 段选用素材源文件缺失，未复制）" if n_lost else ""),
         ""]

    # —— 逐段清单：按批注顺序，只放有选用素材的行 ——
    L += ["## 逐段清单", ""]
    for a in anns:
        aid = str(a.get("id", ""))
        if aid in missing_ids:
            continue
        L.append(f"### {_ann_headline(a)}")
        L.append("")
        for f in sel_by_ann[aid]:
            c = copied_by_fid[str(f.get("id"))]
            src = c["src_rel"]
            if c["exists"]:
                L.append(f"- 素材 `{c['copy_name']}`（源：{src}）")
            else:
                L.append(f"- ⚠ 素材 `{c['copy_name']}`（源：{src}）——"
                         "源文件缺失，未复制")
            note = c["note"]
            L.append(f"  - 剪辑批注：{note if note else '（未写——截哪段/效果/接哪待补）'}")
        tl = _task_line(tasks_by_ref.get(aid))
        if tl:
            L.append(f"- {tl}")
        L.append("")

    # —— 缺口：没有选用素材的批注 ——
    L += ["## 缺口", ""]
    if missing_ids:
        L.append(f"（以下 {len(missing_ids)} 条呈现批注没有选用素材——"
                 "等补制任务完成或人工补拍后，回来重新确认选用并重跑编译）")
        L.append("")
        for a in anns:
            aid = str(a.get("id", ""))
            if aid not in missing_ids:
                continue
            row = f"- {_ann_headline(a)}"
            tl = _task_line(tasks_by_ref.get(aid))
            if tl:
                row += f" · {tl}"
            L.append(row)
        L.append("")
    else:
        L.append("（无——每条呈现批注都有选用素材）")
        L.append("")

    # —— 给 cut 的输入说明 ——
    L += ["## 给 cut 的输入说明", "",
          f"- 素材目录：`{mat_dir_abs}`"
          f"（{n_copied} 段选用素材的复制副本，文件名 = 批注id_素材id_原名）"]
    if loose:
        L.append(f"- 注意：另有 {len(loose)} 段选用素材未挂任何呈现批注，"
                 "未纳入本清单（回面板挂接后重编译）")
    L += ["- 本清单用法：按「逐段清单」的批注顺序组织段落；每条批注下的素材文件"
          "即该段唯一输入，「剪辑批注」写明截哪段/什么效果/接在哪；"
          "「补制任务」行标出 AI 产物到位情况（open/doing 的先留位或跳过）。",
          "- 「缺口」里的批注本清单不提供素材——对应段先用占位或等回补后重跑 "
          "`python 剪辑交接.py <项目根>` 重编译。",
          "- cut 只吃本目录（素材/ + 本说明），不回读定稿 md 与旁车 shoot.json。"]
    return "\n".join(L) + "\n"


def compile_handoff(project_root, md_path, dry_run=False, out=sys.stdout):
    """cut 输入编译。返回 dict：
      {dir, md, copied:[{copy_name,src_rel,ann_id,exists}], loose, missing:[id],
       missing_count, dry_run}

    dry_run=True 只返回内容不写盘（连 05_剪辑交接 目录都不建）。
    写盘一律复制（shutil.copy2），素材本体不动；md 本体/旁车不写。
    指纹对不上抛 ValueError（--dry-run 放行，只看不动）。
    """
    root = Path(project_root)
    sidecar = Path(str(md_path) + ".shoot.json")
    state = json.loads(sidecar.read_text(encoding="utf-8"))
    if not isinstance(state, dict) or state.get("version") != 1:
        raise ValueError(f"旁车不是 version 1 schema: {sidecar}")

    src_sha = str(state.get("source_sha256", ""))
    if src_sha and not dry_run:
        cur_sha = sha256_file(md_path)
        if cur_sha != src_sha:
            raise ValueError(
                "定稿 md 与旁车指纹不符（md 可能被外部改动），拒编译。\n"
                f"  旁车 source_sha256 = {src_sha}\n"
                f"  当前 md sha256     = {cur_sha}")
    if not src_sha:
        print("[剪辑交接] 警告：旁车缺 source_sha256，跳过指纹校验", out)

    anns = state.get("annotations", [])
    ann_order = {str(a.get("id")): i for i, a in enumerate(anns)}

    # 每条批注的选用素材（保持 footage 顺序；一段素材挂多条批注时各段都列）
    sel_by_ann = {aid: [] for aid in ann_order}
    loose = []  # 选用但没挂批注 → 不进逐段清单，只在尾部提醒
    for f in state.get("footage", []):
        if f.get("state") != "selected":
            continue
        ids = [x for x in (f.get("ann_ids") or []) if x in ann_order]
        if not ids:
            loose.append(f)
            continue
        for aid in ids:
            sel_by_ann[aid].append(f)

    # 复制副本：一段素材只复制一份，owner=批注顺序最前者（防重复占盘）
    mat_dir = root / HANDOFF_DIRNAME / FOOTAGE_SUBDIR
    copied_by_fid = {}
    if not dry_run:
        mat_dir.mkdir(parents=True, exist_ok=True)
    for f in state.get("footage", []):
        if f.get("state") != "selected":
            continue
        ids = [x for x in (f.get("ann_ids") or []) if x in ann_order]
        if not ids:
            continue
        owner = min(ids, key=lambda x: ann_order[x])
        rel = str(f.get("file", ""))
        src = root / rel.replace("/", os.sep)
        copy_name = f"{owner}_{f.get('id')}_{Path(rel).name}"
        exists = src.is_file()
        if exists and not dry_run:
            shutil.copy2(src, mat_dir / copy_name)  # 复制不移动，素材本体不动
        copied_by_fid[str(f.get("id"))] = {
            "copy_name": copy_name, "src_rel": rel, "ann_id": owner,
            "exists": exists,
            "note": note_for_footage(state, f.get("id"))}

    missing_ids = [str(a.get("id")) for a in anns
                   if str(a.get("id")) and not sel_by_ann[str(a.get("id"))]]

    tasks_by_ref = {}
    for t in state.get("tasks", []):
        tasks_by_ref.setdefault(str(t.get("ref", "")), t)
    md_text = build_handoff_md(
        Path(md_path).name, anns, sel_by_ann, copied_by_fid, tasks_by_ref,
        loose, missing_ids, str(mat_dir.resolve()),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    if not dry_run:
        md_path_out = root / HANDOFF_DIRNAME / HANDOFF_MD_NAME
        with open(md_path_out, "wb") as fh:
            fh.write(md_text.encode("utf-8"))
        print(f"[剪辑交接] 旁车: {sidecar}", out)
        print(f"[剪辑交接] 素材: 复制 "
              f"{sum(1 for c in copied_by_fid.values() if c['exists'])} 段"
              f"（缺口 {len(missing_ids)} 条"
              + (f"，缺失源文件 {len(copied_by_fid) - sum(1 for c in copied_by_fid.values() if c['exists'])} 段"
                 if any(not c['exists'] for c in copied_by_fid.values()) else "")
              + f"）→ {mat_dir}", out)
        print(f"[剪辑交接] 说明: {root / HANDOFF_DIRNAME / HANDOFF_MD_NAME}",
              out)
    else:
        print(f"[剪辑交接] --dry-run：逐段 {len(anns) - len(missing_ids)} · "
              f"缺口 {len(missing_ids)} · 将复制 "
              f"{sum(1 for c in copied_by_fid.values() if c['exists'])} 段"
              "（未写任何文件）", out)

    return {"dir": str(root / HANDOFF_DIRNAME),
            "md": md_text,
            "copied": list(copied_by_fid.values()),
            "loose": [str(f.get("id")) for f in loose],
            "missing": missing_ids,
            "missing_count": len(missing_ids),
            "dry_run": dry_run}


# ---------------------------------------------------------------- 入口


def run(root, md_hint="", dry_run=False, out=sys.stdout):
    """跑一遍编译。返回退出码（0 成功 / 1 失败）。"""
    root = Path(root)
    if not root.is_dir():
        print(f"[剪辑交接] 项目根不存在: {root}", file=sys.stderr)
        return 1
    try:
        md_path, _sidecar = find_sidecar(root, md_hint)
        result = compile_handoff(root, md_path, dry_run=dry_run, out=out)
    except ValueError as e:
        print(f"[剪辑交接] {e}", file=sys.stderr)
        return 1
    if dry_run:
        print(result["md"], out)
    return 0


def main(argv=None):
    if os.name == "nt":
        try:  # Windows 控制台中文不炸
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(
        description="剪辑交接：补制任务生成 + cut 输入编译（05_剪辑交接/）")
    ap.add_argument("项目根", help="定稿 md + shoot.json + 素材所在目录树")
    ap.add_argument("--md", default="",
                    help="多份 *.shoot.json 时指定定稿 md 消歧")
    ap.add_argument("--dry-run", action="store_true",
                    help="只打印剪辑说明内容，不写盘")
    args = ap.parse_args(argv)
    return run(args.项目根, args.md, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
