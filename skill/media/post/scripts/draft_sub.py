#!/usr/bin/env python3
"""成片+字幕 → 剪映草稿——post 产物的草稿形态，想回剪映继续编辑就用这个。

  python draft_sub.py 成片_响度.mp4                  # 字幕自动找 <stem>_字幕.srt / <stem>.srt
  python draft_sub.py 成片_响度.mp4 成片字幕.srt --name 第N期_定稿

成片**整段**上主轨（不剪不挖洞——那是 cut 的活），字幕轨按 srt 建好，
样式与 cut 粗剪草稿一致（白字黑描边黑底板、末行锚底）。草稿防覆盖与
登记逻辑复用 jy_draft。
"""

import argparse
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
CUT_SCRIPTS = HERE.parent.parent / "cut" / "scripts"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(CUT_SCRIPTS))
from srt_cut import parse_srt, wrap_zh  # noqa: E402
from jy_draft import (SUB_BOTTOM_Y, SUB_LINE_UNIT, SUB_SIZE, SUB_WRAP,
                      draft_touched_by_user, register_in_root_meta,
                      resolve_draft_root, retire_draft)


def jianying_running():
    import subprocess
    tl = subprocess.run(["tasklist", "/FI", "IMAGENAME eq JianyingPro.exe"],
                        capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
    return "JianyingPro.exe" in (tl.stdout or "")


def main():
    ap = argparse.ArgumentParser(description="成片+字幕 → 剪映草稿（整段主轨+字幕轨）")
    ap.add_argument("video", help="定稿成片（一般用响度统一后的 *_响度.mp4）")
    ap.add_argument("srt", nargs="?", default=None,
                    help="字幕 srt（缺省找 <成片>_字幕.srt，再退 <成片>.srt）")
    ap.add_argument("--draft-folder", default=None, help="草稿根目录（缺省同 jy_draft）")
    ap.add_argument("--name", default=None, help="草稿名（缺省 <成片名>_成片）")
    ap.add_argument("--retire", default=None, metavar="粗剪草稿名",
                    help="生成定稿草稿后把粗剪草稿标记移除（进剪映回收站可恢复）"
                         "——草稿列表不堆积，一期一份活草稿")
    ap.add_argument("--fps", type=int, default=30)
    args = ap.parse_args()

    video = Path(args.video)
    if not video.exists():
        sys.exit(f"draft_sub: 成片不存在：{video}")
    srt = Path(args.srt) if args.srt else None
    if srt is None:
        for cand in (video.with_name(f"{video.stem}_字幕.srt"),
                     video.with_name(f"{video.stem}.srt")):
            if cand.exists():
                srt = cand
                break
        if srt is None:
            sys.exit(f"draft_sub: 找不到字幕 srt（试过 {video.stem}_字幕.srt / .srt），"
                     f"先跑 final_sub.py 或显式传入")
    if not srt.exists():
        sys.exit(f"draft_sub: 字幕不存在：{srt}")
    if jianying_running():
        sys.exit("检测到剪映正在运行——先关闭剪映再重跑（运行中的剪映退出时会把"
                 "外部新草稿扫进它的回收站，实测踩坑 2026-09-19）")

    try:
        from pyJianYingDraft import (ClipSettings, DraftFolder, TextBackground,
                                     TextBorder, TextSegment, TextStyle,
                                     Timerange, TrackSpec, TrackType,
                                     VideoMaterial, VideoSegment)
    except ImportError:
        sys.exit("缺依赖：pip install pyJianYingDraft")

    folder = resolve_draft_root(args.draft_folder)
    if not folder.exists():
        sys.exit(f"剪映草稿目录不存在：{folder}（用 --draft-folder 指定）")
    name = args.name or f"{video.stem}_成片"

    # 防覆盖：同 jy_draft——被剪映/人工改过的不覆盖，自动落 v2
    existing = folder / name / "draft_content.json"
    if existing.exists() and draft_touched_by_user(
            existing, folder / name / "_media_cut_stamp.json"):
        base = name
        for n in range(2, 100):
            if not (folder / f"{base}v{n}" / "draft_content.json").exists():
                name = f"{base}v{n}"
                break
        else:
            sys.exit(f"草稿版本名用尽：{base}v2..v99 都已存在")
        print(f"[draft_sub] {base} 已被改过——不覆盖，落到 {name}")

    material = VideoMaterial(str(video))
    script = DraftFolder(str(folder)).create_draft(
        name, material.width, material.height, fps=args.fps, allow_replace=True)
    script.append_track(TrackSpec(TrackType.video, name="主轨"))
    seg = VideoSegment(material, target_timerange=Timerange(0, material.duration))
    script.add_segment(seg, track="主轨")

    entries = parse_srt(str(srt))
    with tempfile.TemporaryDirectory() as td:
        def fmt(t):
            ms = int(round(t * 1000))
            h, rem = divmod(ms, 3600000)
            m, rem = divmod(rem, 60000)
            s, ms2 = divmod(rem, 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms2:03d}"
        wrapped = Path(td) / "sub.srt"
        lines = [f"{i}\n{fmt(a)} --> {fmt(b)}\n{wrap_zh(txt, SUB_WRAP)}\n"
                 for i, (a, b, txt) in enumerate(entries, 1)]
        wrapped.write_text("\n".join(lines), encoding="utf-8")
        sub_ref = TextSegment("样式参考", Timerange(0, 1),
                              style=TextStyle(size=SUB_SIZE, color=(1.0, 1.0, 1.0),
                                              align=1, bold=True),
                              border=TextBorder(color=(0.0, 0.0, 0.0), width=40),
                              background=TextBackground(color="#000000", alpha=0.6,
                                                        round_radius=0.1))
        script.import_srt(str(wrapped), "字幕",
                          style_reference=sub_ref,
                          clip_settings=ClipSettings(transform_y=-0.8))
        # 末行锚底（与 jy_draft 同款）：按每条实际行数微调文本框中心
        for tseg in script.tracks["字幕"].segments:
            n_lines = tseg.text.count("\n") + 1
            tseg.clip_settings.transform_y = (SUB_BOTTOM_Y
                                              + (n_lines - 1) * SUB_LINE_UNIT)
    script.save()

    import hashlib
    import json
    import time
    import uuid
    meta_path = folder / name / "draft_meta_info.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["draft_id"] = str(uuid.uuid4()).upper()
    meta["draft_name"] = name
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=4), encoding="utf-8")
    stamp_path = folder / name / "_media_cut_stamp.json"
    stamp_path.write_text(json.dumps({
        "sha256": hashlib.sha256((folder / name / "draft_content.json").read_bytes()).hexdigest(),
        "written_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }, ensure_ascii=False), encoding="utf-8")
    register_in_root_meta(folder, name)
    if args.retire:
        rough_content = folder / args.retire / "draft_content.json"
        rough_stamp = folder / args.retire / "_media_cut_stamp.json"
        if not rough_content.exists():
            print(f"[draft_sub] 粗剪草稿 {args.retire} 不存在，跳过 retire")
        elif draft_touched_by_user(rough_content, rough_stamp):
            # 保险丝：精剪的操作（加素材/调字幕/删段）都做在粗剪草稿里，且剪映
            # 一打开就加密、管线读不回——动过的粗剪草稿是精剪成果的唯一载体，
            # 绝不 retire。只有管线刚出、没人碰过的才退场（工作区可秒级重出）
            print(f"[draft_sub] 粗剪草稿 {args.retire} 被剪映/人工改过——里面可能有你的"
                  f"精剪操作，不 retire（确认没用了就在剪映里手动删）")
        else:
            retire_draft(folder, args.retire)

    dur = material.duration / 1e6
    print(f"[draft_sub] 草稿已生成：{folder / name}")
    print(f"  成片整段主轨 {int(dur // 60)}:{int(dur % 60):02d}；字幕轨 {len(entries)} 条")
    print("  打开剪映专业版，草稿列表里直接可见")


if __name__ == "__main__":
    main()
