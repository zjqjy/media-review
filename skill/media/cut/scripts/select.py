#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 初选标准执行器——第②层b（决定.json 进 → 剪切稿+日志出，锚字核验内建）。

背景（2026-09-19 沉淀）：此前每期由 AI 现场手写初选脚本（删表/修错表/锚字核验），
写脚本+调试+dry-run 核对 ~5 分钟/期，且修错表（ESP32/Claude Code 等错拼模式）每期重打。
本脚本把"机械执行+核验"固化，AI 每期只产出一份决定.json：

  {
    "环境搭建": {
      "src": "环境搭建.srt",                              // 可省，默认 <段名>.srt
      "iron":   {"13": "我要看", "44": ""},               // 铁废料删条目→锚字（空串=跳过核验）
      "repeat": [                                          // 语义重复·删前留后（用户规则）
        {"del": [65, 99], "group": "B", "note": "新建工程讲两遍，删前留后",
         "anchors": {"65": "再讲解", "99": "嗯"},           // 也可用与 del 平行的锚字列表
         "keep_anchors": {"120": "演示一下ESP"}}            // 也可用纯锚字列表（全文检索唯一定位）
      ],
      "fixes":  {"46": [["这几个文具", "这几个源"]]}        // 条内修错（只修错拼，不改写口播）
    }
  }

全局修错表 asr_fixes.json（与本脚本同目录）自动套用所有条目，跨期沉淀不再重写；
新错拼模式热词治不了的，直接编辑该 json。

用法：
  python select.py --scan 稿.srt [稿2.srt ...]   # 初选辅助：铁废料候选+疑似重复组+口头禅统计
  python select.py --decide 决定.json --dry      # 核验+预览（删/修对照打印），不改盘
  python select.py --decide 决定.json --apply    # 落盘 <stem>_剪切稿.srt + 初选日志.json
锚字核验任何一条不过 → 全部不落盘，退出码 1（改完决定再跑）。
"""

import argparse
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

ASR_FIXES = Path(__file__).with_name("asr_fixes.json")

# 纯语气词条目候选（整条就这一个词，删）；写成正则避免把"好的我们开始"误伤
FILLER_ENTRY_RE = re.compile(
    r"^(?:嗯|呃|啊|哦|噢|哎|唉|对|好|行|ok|okay|好的|好啊|对吧|对不对|"
    r"嗯嗯|哎哟|诶|欸|然后|那么|就是|这个|那个)[啊吧呢吗嗯哦哟了的！!。.，,]?+$",
    re.IGNORECASE)


def parse_srt(path: Path):
    entries = []
    block = []
    for line in path.read_text(encoding="utf-8-sig").splitlines() + [""]:
        if line.strip() == "":
            if block:
                entries.append({"idx": int(block[0]), "time": block[1],
                                "text": "\n".join(block[2:])})
                block = []
        else:
            block.append(line.rstrip())
    return entries


def write_srt(path: Path, entries):
    out = []
    for i, e in enumerate(entries, 1):
        out.append(f"{i}\n{e['time']}\n{e['text']}\n")
    path.write_text("\n".join(out), encoding="utf-8")


def _norm(text):
    t = re.sub(r"[^\w\u3400-\u9fff]", "", text)
    return re.sub(r"([\u3400-\u9fff]{1,4})\1+", r"\1", t)


def load_global_fixes():
    if ASR_FIXES.exists():
        return [tuple(p) for p in json.loads(ASR_FIXES.read_text(encoding="utf-8"))]
    return []


def scan_srt(path: Path):
    """单稿扫描：铁废料候选 + 疑似重复组（窗口内链式）+ 口头禅统计。只报告不删改。"""
    entries = parse_srt(path)
    print(f"\n=== {path.name}：{len(entries)} 条 ===")

    fill = [e for e in entries if FILLER_ENTRY_RE.match(e["text"].strip())]
    if fill:
        print(f"\n-- 纯语气词候选 {len(fill)} 条（整条无实词，默认删）--")
        print("  " + " ".join(f"#{e['idx']}" for e in fill))

    # 疑似重复：归一化后互相覆盖 ≥55% 或相似度 ≥75%，窗口 ±8 条、间隔 ≤120s（比
    # asr_funasr 的重录对宽得多——那里管口误立即重说，这里管"这段我讲过一遍"）
    norm = [(e["idx"], e["time"][:8], _norm(e["text"]), e["text"]) for e in entries]

    def to_sec(t):
        h, m, s = t.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    pairs = []
    for j in range(len(norm)):
        _, tj, nb, _ = norm[j]
        if len(nb) < 6:
            continue
        for i in range(max(0, j - 8), j):
            _, ti, na, _ = norm[i]
            if not na or len(na) > 60 and len(nb) > 60 and abs(len(na) - len(nb)) > 40:
                continue
            sm = SequenceMatcher(None, na, nb)
            cov = sm.find_longest_match(0, len(na), 0, len(nb)).size / max(len(na), 1)
            if (cov >= 0.55 or sm.ratio() >= 0.75) and \
                    abs(to_sec(tj) - to_sec(ti)) <= 120:
                pairs.append((i, j, round(max(cov, sm.ratio()), 2)))
    # 链式成组
    parent = list(range(len(norm)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j, _ in pairs:
        parent[find(i)] = find(j)
    groups = {}
    for i in range(len(norm)):
        groups.setdefault(find(i), []).append(i)
    if groups:
        print("\n-- 疑似重复组（意思重复→默认删前留后；组内夹独有内容的先剔除再删）--")
        for g in sorted(groups.values(), key=len):
            if len(g) < 2:
                continue
            last = norm[g[-1]]
            print(f"  组（保最后 #{last[0]}）: " +
                  " | ".join(f"#{norm[i][0]}「{norm[i][3][:18]}」" for i in g))

    # 口头禅统计：下一轮转录 --strip-filler 该不该加料
    from collections import Counter
    starts = Counter()
    for _, _, _, t in norm:
        for w in ("然后", "那么", "就是", "这个", "那个", "首先", "接着"):
            if t.startswith(w):
                starts[w] += 1
    print("\n-- 分句首口头禅统计（已剥的'然后'不在稿里；量大的下次 --strip-filler 加料）--")
    print("  " + ("、".join(f"{w}×{n}" for w, n in starts.most_common()) or "无明显口头禅"))


def run_decide(decide_path: Path, dry: bool, log_dir: Path | None):
    decide = json.loads(decide_path.read_text(encoding="utf-8"))
    src_dir = decide_path.parent
    global_fixes = load_global_fixes()
    log = {"deleted": {}, "repeat": {}, "fixed": {}, "annotated": {}}
    problems = []
    made = []
    for name, plan in decide.items():
        src = src_dir / plan.get("src", f"{name}.srt")
        entries = parse_srt(src)
        by_idx = {e["idx"]: e for e in entries}

        del_set, del_anchor = set(), {}
        for k, v in (plan.get("iron") or {}).items():
            del_set.add(int(k))
            del_anchor[int(k)] = v
        for grp in plan.get("repeat") or []:
            dels = [int(i) for i in grp.get("del", [])]
            if not dels:
                continue  # 该组删除项已全部随词级洞/重转录撤销，无可删
            del_set.update(dels)
            av = grp.get("anchors") or {}
            if not av:
                pass  # 无锚=可选，不报错
            elif isinstance(av, dict):
                for k, v in av.items():
                    del_anchor[int(k)] = v
            elif isinstance(av, list):
                # 代理两种约定都收：与 del 平行的列表，或 [首锚, 尾锚]
                if not av:
                    pass  # 空列表=无锚，可选
                elif len(av) == len(dels):
                    for i, v in zip(dels, av):
                        del_anchor[i] = v
                elif len(av) >= 1 and dels:
                    del_anchor[dels[0]] = av[0]
                    del_anchor[dels[-1]] = av[-1]
                else:
                    problems.append(f"[{name}] repeat anchors 为空但 del 非空")
        # 锚字核验：删条目内容必须含锚（防转录重跑后索引漂移删错句子）
        for i, anchor in sorted(del_anchor.items()):
            e = by_idx.get(i)
            if e is None:
                problems.append(f"[{name} #{i}] 删除条目不存在（索引漂移？重对位）")
            elif anchor and anchor not in e["text"]:
                problems.append(f"[{name} #{i}] 删除锚字不符：预期含「{anchor}」，"
                                f"实为「{e['text']}」")
        # 保留边界锚：防范围删除删穿到独有内容。
        # 兼容 {条目号: 锚} 或纯锚字列表（后者按全文检索唯一定位条目）
        for grp in plan.get("repeat") or []:
            kv = grp.get("keep_anchors") or {}
            if isinstance(kv, dict):
                pairs = [(int(k), v) for k, v in kv.items()]
            else:
                pairs = []
                for v in kv:
                    hits = [e for e in entries if v in e["text"]]
                    kept = [e for e in hits if e["idx"] not in del_set]
                    # 同文重录对会让 keep 锚命中删/留两条——语义上要保护的是留下那条
                    if len(kept) == 1:
                        pairs.append((kept[0]["idx"], v))
                    else:
                        problems.append(f"[{name}] keep_anchors「{v[:24]}」命中 {len(hits)} 条"
                                        f"（剔除删除表后剩 {len(kept)}，需唯一）")
            for i, v in pairs:
                e = by_idx.get(i)
                if e is None:
                    problems.append(f"[{name} #{i}] 保留锚找不到条目")
                elif v not in e["text"]:
                    problems.append(f"[{name} #{i}] 保留锚不符：预期含「{v}」，"
                                    f"实为「{e['text']}」")
                elif i in del_set:
                    problems.append(f"[{name} #{i}] 保留锚条目竟在删除表里！")

        kept, deleted, fixes = [], [], []
        for e in entries:
            if e["idx"] in del_set:
                deleted.append(f"#{e['idx']} {e['time'][:11]}「{e['text']}」")
                continue
            t = e["text"]
            for old, new in global_fixes:
                if old in t:
                    t = t.replace(old, new)
            for old, new in (plan.get("fixes") or {}).get(str(e["idx"]), []):
                if old in t:
                    t = t.replace(old, new)
                elif old in e["text"]:
                    pass  # 全局修错表已先修掉同一处——条目级重复申报，跳过不算错
                else:
                    problems.append(f"[{name} #{e['idx']}] 修错表锚字不在稿里："
                                    f"「{old}」｜现文：「{e['text']}」")
            if t != e["text"]:
                fixes.append(f"#{e['idx']}「{e['text']}」→「{t}」")
            kept.append({**e, "text": t})

        log["deleted"][name] = deleted
        log["fixed"][name] = fixes
        reps = plan.get("repeat") or []
        if reps:
            log["repeat"][name] = [
                {"del": g.get("del", []), "group": g.get("group", ""),
                 "note": g.get("note", "")} for g in reps]
        # 人工提示标注（语义重复/逻辑混乱等 AI 拿不准、留给精剪判断的点）
        def _sec(time_str):
            m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)", time_str.strip())
            g = [int(x) for x in m.groups()]
            return g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000

        annotations = []
        for a in plan.get("annotate") or []:
            ids = [int(i) for i in a.get("ids", [])]
            texts = [by_idx[i] for i in ids if i in by_idx]
            if not texts:
                problems.append(f"[{name}] annotate ids {ids} 都不存在")
                continue
            start = min(_sec(t["time"].split(" --> ")[0]) for t in texts) - 0.2
            end = max(_sec(t["time"].split(" --> ")[1]) for t in texts) + 0.2
            note = a.get("note", "请精剪注意")
            annotations.append({"start": round(start, 3), "end": round(end, 3),
                                "note": f"⚠{note}：{texts[0]['text'][:14]}"})
        if annotations:
            log["annotated"][name] = annotations
        print(f"[{name}] {len(entries)} 条 → 剪切稿 {len(kept)} 条"
              f"（删 {len(deleted)}，修 {len(fixes)}，标注 {len(annotations)}）")
        if dry:
            for d in deleted:
                print(f"  删 {d}")
            for f in fixes:
                print(f"  修 {f}")
            for a in annotations:
                print(f"  标 {a['start']:.1f}-{a['end']:.1f}s {a['note']}")
        else:
            out = src.with_name(src.stem + "_剪切稿.srt")
            write_srt(out, kept)
            if annotations:
                side = src.with_name(src.stem + "_标注.json")
                side.write_text(json.dumps(annotations, ensure_ascii=False, indent=1),
                                encoding="utf-8")
                made.append(side)
            made.append(out)
    if problems:
        print("\n!!! 锚字核验未过，逐条人工核对（全部未落盘）：")
        for p in problems:
            print(" ", p)
        sys.exit(1)
    if dry:
        print("\n[dry-run] 核验通过；确认后加 --apply 落盘")
        return
    out_dir = log_dir or decide_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "初选日志.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    print("日志 →", out_dir / "初选日志.json")
    for m in made:
        print("剪切稿 →", m)


def main():
    ap = argparse.ArgumentParser(description="AI 初选标准执行器（决定.json→剪切稿，锚字核验内建）")
    ap.add_argument("--scan", nargs="+", metavar="稿.srt",
                    help="初选辅助扫描：铁废料候选/疑似重复组/口头禅统计")
    ap.add_argument("--decide", default=None, help="决定.json 路径")
    ap.add_argument("--dry", action="store_true", help="只核验+预览，不落盘")
    ap.add_argument("--apply", action="store_true", help="落盘剪切稿+日志")
    ap.add_argument("--log-dir", default=None, help="初选日志.json 目录（默认决定.json 旁）")
    args = ap.parse_args()

    if args.scan:
        for p in args.scan:
            scan_srt(Path(p))
        return
    if not args.decide:
        ap.error("需要 --scan 或 --decide")
    if args.dry == args.apply:
        ap.error("--dry / --apply 二选一")
    run_decide(Path(args.decide), dry=args.dry, log_dir=Path(args.log_dir) if args.log_dir else None)


if __name__ == "__main__":
    main()
