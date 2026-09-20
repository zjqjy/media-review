#!/usr/bin/env python3
"""run_cut——cut 管线一键编排：把机器段压成一条命令，AI 只在初选判断处介入。

背景（2026-09-20 实测）：素材就位后管线计算只要 ~2 min，40+ min 大头是 AI 会话
轮次开销（六次独立调用 + 每次组织上下文）。本脚本把无决策依赖的段全并起来：

  python run_cut.py --init 素材目录... [--name 期名]
      建工作区(待粗剪/1_原始) → 全部素材**一次进程**批量转录（一次模型加载）
      → 转录稿归位 3_转录初选 → select --scan 逐段出 <段>.scan.txt
      → 打印初选交接单（每段条数/时长/scan 路径）——到此停下，等 AI 拍板

  python run_cut.py --finish 工作区(待粗剪)...
      收 _工具/初选决定*.json（碎片自动合并）→ select --dry 核验 → --apply
      → jy_draft --seq 出草稿（默认按文件名排序，非序号命名用 --order 强制）
      → organize 归位。每步失败即停，锚字核验不过不会落盘

AI 侧分工见 SKILL.md「多代理初选」：每段一个子代理并行读稿写决定，主线程只合并。
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent


def sh(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", **kw)
    if p.returncode != 0:
        print(p.stdout[-1500:], p.stderr[-1500:], sep="\n")
        sys.exit(f"run_cut: 步骤失败（ exit {p.returncode} ）—— {' '.join(str(c) for c in cmd[:3])}...")
    return p.stdout


def init_dirs(material_dirs):
    """建工作区、归位素材。返回 {工作区: [素材mp4...]}。"""
    layout = {}
    for d in material_dirs:
        d = Path(d)
        ws = d if d.name == "待粗剪" else d / "待粗剪"
        mp4s = sorted(d.glob("*.mp4"))
        if not mp4s and (ws / "1_原始").is_dir():  # 已归位过的工作区：素材在 1_原始 里
            mp4s = sorted((ws / "1_原始").glob("*.mp4"))
        raw = ws / "1_原始"
        raw.mkdir(parents=True, exist_ok=True)
        (ws / "3_转录初选").mkdir(exist_ok=True)
        (ws / "_工具").mkdir(exist_ok=True)
        moved = []
        for f in mp4s:
            tgt = raw / f.name
            if f.parent != raw:
                f.rename(tgt)
            moved.append(tgt)
        layout[ws] = moved
    return layout


def cmd_init(args):
    t0 = time.time()
    layout = init_dirs(args.dirs)
    all_mp4 = [m for ms in layout.values() for m in ms]
    print(f"[run_cut] {len(layout)} 个工作区，共 {len(all_mp4)} 段素材——单批转录（一次模型加载）")
    hot = ["--hotword", args.hotword] if args.hotword else []
    out = sh([sys.executable, HERE / "asr_funasr.py", *all_mp4, *hot])
    print(out[-2500:])
    n_moved = 0
    for ws, mp4s in layout.items():
        tri = ws / "3_转录初选"
        for m in mp4s:
            for suffix in (".srt", ".cuts.json"):
                src = m.with_name(m.stem + suffix)
                if src.exists():
                    src.rename(tri / src.name)
                    n_moved += 1
    # 逐段 scan 落文件，子代理直接读不用传大段文本
    for ws, mp4s in layout.items():
        tri = ws / "3_转录初选"
        for m in mp4s:
            srt = tri / (m.stem + ".srt")
            if srt.exists():
                out = sh([sys.executable, HERE / "select.py", "--scan", srt])
                (tri / f"{m.stem}.scan.txt").write_text(out, encoding="utf-8")
    print(f"\n[run_cut] init 完成（{time.time()-t0:.0f}s）。初选交接单：")
    for ws, mp4s in layout.items():
        tri = ws / "3_转录初选"
        print(f"  {ws}")
        for m in mp4s:
            srt = tri / (m.stem + ".srt")
            n = len(srt.read_text(encoding="utf-8-sig").split("\n\n")) if srt.exists() else 0
            print(f"    {m.stem}: {n} 条  scan→3_转录初选/{m.stem}.scan.txt")
    print("  → 下一步：每段一个子代理读稿写 _工具/初选决定_<段名>.json（规则见 SKILL.md 多代理初选）")


def merge_decides(ws):
    """碎片 初选决定_<段名>.json → 合并成 初选决定.json。碎片是唯一事实来源，
    有碎片时以碎片重建（此前手动维护的合并文件作废）。"""
    tool = ws / "_工具"
    frags = sorted(tool.glob("初选决定_*.json"))
    merged_path = tool / "初选决定.json"
    if frags:
        merged = {}
        for f in frags:
            data = json.loads(f.read_text(encoding="utf-8"))
            stem = f.stem.removeprefix("初选决定_")
            if set(data) == {stem} and isinstance(data[stem], dict):
                merged[stem] = data[stem]  # 单段碎片：{"段名": {...}}
            elif all(isinstance(v, dict) for v in data.values()):
                merged.update(data)        # 多段碎片：{"段名": {...}, ...}
            else:
                sys.exit(f"run_cut: 碎片 {f.name} 结构不认识（段值应为对象）")
            print(f"[run_cut] 合并碎片 {f.name}")
    elif merged_path.exists():
        merged = json.loads(merged_path.read_text(encoding="utf-8"))
    else:
        sys.exit(f"run_cut: {tool} 里没有初选决定（或碎片）——先让子代理写完")
    merged_path.write_text(json.dumps(merged, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    return merged_path


def cmd_finish(args):
    t0 = time.time()
    for ws in args.workspaces:
        ws = Path(ws)
        decide = merge_decides(ws)
        tri = ws / "3_转录初选"
        # dry 核验 → apply（锚字不过会退出码 1，整批不落盘）
        sh([sys.executable, HERE / "select.py", "--decide", decide, "--dry"])
        sh([sys.executable, HERE / "select.py", "--decide", decide, "--apply"])
        # 草稿：按 --order 或文件名排序拼 --seq
        raw = ws / "1_原始"
        names = [p.stem for p in sorted(raw.glob("*.mp4"))]
        if args.order:
            names = [n.strip() for n in args.order.split(",")]
        missing = [n for n in names if not (raw / f"{n}.mp4").exists()]
        if missing:
            sys.exit(f"run_cut: --order 里的段在 1_原始 不存在: {missing}")
        if not args.order and not any(n[:2].isdigit() for n in names):
            print(f"[run_cut] 警告：素材名不带序号，按文件名排序拼轨：{names}；"
                  f"顺序不对请用 --order 重跑")
        seq = [f"{raw / n}.mp4={tri / n}_剪切稿.srt" for n in names]
        sh([sys.executable, HERE / "jy_draft.py", "--seq", *seq,
            "--name", args.draft_name or f"{ws.parent.name}_粗剪"])
        sh([sys.executable, HERE / "organize.py", ws])
        print(f"[run_cut] {ws} 完成（{time.time()-t0:.0f}s）")
    print("[run_cut] 全部工作区交付完毕。粗片文件可选：srt_cut.py --seq ... 后台跑")


def cmd_qa(args):
    """成片复核闭环：音频快剪 → 重转录 → 口癖/重复残留审计（2026-09-20 用户要求：
    剪辑结果出来后转录复核一遍）。产物在 待粗剪/_QA/，报告打 stdout。"""
    t0 = time.time()
    for ws in args.workspaces:
        ws = Path(ws)
        raw = ws / "1_原始"
        tri = ws / "3_转录初选"
        qa_dir = ws / "_QA"
        qa_dir.mkdir(exist_ok=True)
        names = [p.stem for p in sorted(raw.glob("*.mp4"))]
        if args.order:
            names = [n.strip() for n in args.order.split(",")]
        seq = [f"{raw / n}.mp4={tri / n}_剪切稿.srt" for n in names
               if (tri / f"{n}_剪切稿.srt").exists()]
        if not seq:
            sys.exit(f"run_cut: {tri} 里没有剪切稿——先跑 --finish")
        sh([sys.executable, HERE / "srt_cut.py", "--seq", *seq,
            "--out-dir", qa_dir, "--audio-only"])
        audio = sorted(qa_dir.glob("*.m4a"))
        hot = ["--hotword", args.hotword] if args.hotword else []
        sh([sys.executable, HERE / "asr_funasr.py", *audio, *hot])
        print(f"\n===== 成片复核报告 · {ws.parent.name}（{time.time()-t0:.0f}s）=====")
        for a in audio:
            srt = a.with_suffix(".srt")
            if not srt.exists():
                continue
            out = sh([sys.executable, HERE / "select.py", "--scan", srt])
            txt = Path(srt).read_text(encoding="utf-8-sig")
            import re as _re
            from collections import Counter
            body = "\n".join(l for l in txt.splitlines()
                             if l and "-->" not in l and not l.strip().isdigit())
            fills = Counter(m.group() for m in
                            _re.finditer(r"然后|呃{1,}|嗯{2,}|哎|就是说", body))
            n_sent = len([b for b in txt.split("\n\n") if b.strip()])
            print(f"\n[{a.stem}] 成片 {n_sent} 条")
            print("  口癖残留:", (dict(fills) if fills else "无"))
            for m in _re.finditer(r".{8}(?:然后|呃|嗯{2,}).{8}", body):
                print(f"    …{m.group()}…")
            dup_lines = [l for l in out.splitlines() if "组（保最后" in l]
            print("  疑似重复组:", f"{len(dup_lines)} 组" if dup_lines else "无")
            for l in dup_lines:
                print("   ", l.strip())


def main():
    ap = argparse.ArgumentParser(description="cut 管线一键编排（机器段一条命令，AI 只管初选）")
    ap.add_argument("--init", nargs="+", dest="dirs", metavar="素材目录",
                    help="建工作区+单批转录+scan（多期可一起传，共享一次模型加载）")
    ap.add_argument("--finish", nargs="+", dest="workspaces", metavar="待粗剪",
                    help="决定就位后：合并决定→dry→apply→草稿→归位")
    ap.add_argument("--qa", nargs="+", dest="qa_ws", metavar="待粗剪",
                    help="成片复核：音频快剪→重转录→口癖/重复残留审计")
    ap.add_argument("--hotword", default="ESP32 ESP32-S3 ESP-IDF Claude Code VS Code "
                    "LCD 触摸屏 WS2812B Ctrl+Shift+P USB-JTAG COM口 GitHub IDF 乐鑫 "
                    "开发板 引脚 阿程 桌面代码搭子 清华源 串口烧录")
    ap.add_argument("--order", default=None, help="草稿拼轨顺序，逗号分段名（--finish 用）")
    ap.add_argument("--draft-name", default=None, help="草稿名（--finish 单工作区时可用）")
    args = ap.parse_args()
    if bool(args.dirs) == bool(args.workspaces) == bool(args.qa_ws):
        ap.error("--init / --finish / --qa 三选一")
    if args.dirs:
        cmd_init(args)
    elif args.qa_ws:
        args.workspaces = args.qa_ws
        cmd_qa(args)
    else:
        cmd_finish(args)


if __name__ == "__main__":
    main()
