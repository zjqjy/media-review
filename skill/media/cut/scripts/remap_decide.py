#!/usr/bin/env python3
"""remap_decide——转录稿重跑后（呃挖洞/规则变化导致索引漂移），把既有决定碎片
整体重对位到新转录稿。

原理：旧剪切稿保留着"旧索引→原素材时间"的对应；新转录稿同轴。按条目中点时间
窗口映射 old_idx → new_idx，再重写决定里的全部索引（iron/repeat del/anchors/
keep_anchors/fixes）。锚字优先保留原文（多数仍在），对不上时取新条目文本前 8 字。

用法：python remap_decide.py <待粗剪> <段名> <旧剪切稿.srt> [--fragment X]
旧剪切稿 = 上一轮 select.py 产出的 <段>_剪切稿.srt（本轮 finish 失败未覆盖时仍在）。
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from srt_cut import parse_srt


def parse_with_idx(p):
    ents = {}
    for b in Path(p).read_text(encoding="utf-8-sig").split("\n\n"):
        L = b.strip().splitlines()
        if len(L) >= 3 and L[0].strip().isdigit():
            import re
            m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+) --> (\d+):(\d+):(\d+)[,.](\d+)", L[1])
            if not m:
                continue
            g = [int(x) for x in m.groups()]
            ents[int(L[0])] = (g[0] * 3600000 + g[1] * 60000 + g[2] * 1000 + g[3],
                               g[4] * 3600000 + g[5] * 60000 + g[6] * 1000 + g[7],
                               "\n".join(L[2:]))
    return ents


def main():
    ap = argparse.ArgumentParser(description="决定碎片重对位到新转录稿")
    ap.add_argument("ws")
    ap.add_argument("seg")
    ap.add_argument("old_cut_srt")
    ap.add_argument("--fragment", default=None)
    args = ap.parse_args()

    ws = Path(args.ws)
    tri = ws / "3_转录初选"
    old = parse_with_idx(args.old_cut_srt)
    new = parse_with_idx(tri / f"{args.seg}.srt")

    # old idx → new idx：优先锚字/旧文本检索（唯一命中），退化为时间就近
    def old_mid(idx):
        if idx in old:
            s, e, _ = old[idx]
            return (s + e) / 2 / 1000
        return None

    def to_new(idx, search_text=""):
        mid = old_mid(idx)
        if search_text:
            hits = [k for k, (ns, ne, nt) in new.items() if search_text in nt]
            if len(hits) == 1:
                return hits[0]
            if hits and mid is not None:
                return min(hits, key=lambda k: abs((new[k][0] + new[k][1]) / 2 / 1000 - mid))
        if mid is None:
            return None
        contain = [k for k, (ns, ne, _) in new.items() if ns / 1000 - 0.4 <= mid <= ne / 1000 + 0.4]
        if len(contain) == 1:
            return contain[0]
        best, best_d = None, 1.2
        for k, (ns, ne, _) in new.items():
            d = abs((ns + ne) / 2 / 1000 - mid)
            if d < best_d:
                best, best_d = k, d
        return best

    frag = ws / "_工具" / (args.fragment or f"初选决定_{args.seg}.json")
    if not frag.exists():
        for f in sorted((ws / "_工具").glob("初选决定_*.json")):
            try:
                if args.seg in json.loads(f.read_text(encoding="utf-8")):
                    frag = f
                    break
            except Exception:
                continue
    plan_all = json.loads(frag.read_text(encoding="utf-8"))
    sp = plan_all[args.seg]

    dropped, moved = [], 0

    def anchor_for(new_idx, want):
        txt = new[new_idx][2]
        return want if want and want in txt else txt[:8]

    def remap(idx_str, want="", search_text=None):
        """返回 (new_idx, anchor)；旧内容已不在新稿（纯填充声被挖）→ "DROP"；None=保留原样。"""
        nonlocal moved
        i = int(idx_str)
        old_txt = old.get(i, (0, 0, ""))[2].strip()
        n = to_new(i, search_text or old_txt)
        if n is None:
            if len(old_txt) <= 2 or not old_txt:
                return "DROP"  # 孤立语气词，新稿已被词级洞挖掉 → 删除项随之撤销
            dropped.append(f"#{i}「{old_txt[:12]}」")
            return None
        if n != i:
            moved += 1
        return n, anchor_for(n, want)

    # iron：锚字检索定位，检索不到且原条目是纯语气词 → 随词级洞撤销（DROP）
    new_iron = {}
    for k, want in (sp.get("iron") or {}).items():
        r = remap(k, want, search_text=want)
        if r == "DROP":
            continue
        if r is None:
            new_iron[str(int(k))] = want  # 保留原样，dry 会拦
        else:
            new_iron[str(r[0])] = r[1]
    sp["iron"] = new_iron

    # repeat：del 逐条重对位；anchors/keep_anchors 一律收敛成 dict（新索引+有效锚）
    for grp in sp.get("repeat") or []:
        new_dels, del_anchor_pairs = [], {}
        for i in grp.get("del", []):
            otxt = old.get(int(i), (0, 0, ""))[2] if int(i) in old else ""
            r = remap(str(i), "", search_text=otxt or None)
            if r == "DROP":
                continue
            if r is None:
                new_dels.append(int(i))
            else:
                new_dels.append(r[0])
                del_anchor_pairs[str(r[0])] = r[1] if isinstance(r[1], str) else ""
        grp["del"] = new_dels
        if del_anchor_pairs:
            grp["anchors"] = del_anchor_pairs
        ka = grp.get("keep_anchors") or {}
        new_k = {}
        if isinstance(ka, dict):
            items = [(int(k), v) for k, v in ka.items()]
        else:
            items = [(None, v) for v in ka]
        for i, v in items:
            if i is not None:
                r = remap(str(i), v, search_text=v)
                if r == "DROP" or r is None:
                    new_k[str(i)] = v
                    continue
                new_k[str(r[0])] = v
            else:
                hits = [k for k, (ns, ne, nt) in new.items()
                        if v in nt and k not in set(new_dels)]
                if not hits:  # 全被删或文本变了 → 放宽到不剔删除表再试
                    hits = [k for k, (ns, ne, nt) in new.items() if v in nt]
                if hits:
                    new_k[str(hits[0])] = v
                else:
                    print(f"  ! keep锚「{v[:16]}」新稿找不到，已丢弃")
        grp["keep_anchors"] = new_k

    # fixes：用旧错误子串检索定位新条目
    new_fix = {}
    for k, v in (sp.get("fixes") or {}).items():
        search = v[0][0] if v else ""
        r = remap(k, "", search_text=search or None)
        if r == "DROP":
            continue
        new_fix[str(r[0] if r else k)] = v
    sp["fixes"] = new_fix

    frag.write_text(json.dumps(plan_all, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[remap] {args.seg}: 移位 {moved} 条，纯填充声删除 {len(dropped)} 条：{dropped[:8]}")
    print(f"[remap] → {frag.name}（跑 select --dry 验证）")


if __name__ == "__main__":
    main()
