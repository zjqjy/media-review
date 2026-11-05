#!/usr/bin/env python3
"""剪映草稿.py — 选用素材粗拼直出剪映草稿（shoot 链路终点，S2-D 延伸）

与 cut 的 jy_draft.py 分工（两条管线，别混）：
  - cut/jy_draft：吃**转录剪切稿**——词级挖洞 + 静音细剪 + 字幕轨（AI 粗剪）
  - shoot/本模块：吃 **shoot.json 的选用素材表**——按呈现批注顺序全段硬拼 + Rxx 标签
    （人挑完料的粗拼；精细剪辑在剪映里做。剪辑批注 editNotes 是给人看的参考，
    不自动截段——自由文本里的时间范围解析不可靠，宁整段勿错切）

时间轴规则：
  - 批注按 R01..R09 数值顺序；同批注多段选用素材按 footage 顺序接排（硬切）
  - 一段素材挂多条批注 → 只在**第一条**引用它的批注处落一次（与剪辑交接 compile 同语义）
  - 选用但没挂任何批注的素材（orphans）追加到时间轴末尾，报告里提醒回面板挂接
  - 文件在盘缺失 → 跳过 + 警告（不炸整条时间轴）
  - 每段开头打 2 秒 Rxx 小字标签（导航用，精剪时随手删）

复用 cut 家底（懒加载 + select 地雷防护，见 _import_jy_helpers）：
resolve_draft_root / draft_touched_by_user / register_in_root_meta / normalize_fps。
防覆盖政策同 jy_draft：同名草稿被剪映/人工改过 → 自动落 v2/v3，绝不覆盖用户成果；
没动过的管线产物可原地刷新。依赖：pip install pyJianYingDraft（懒加载，缺了给人话）。

用法：
    python 剪映草稿.py <项目根> [--md 定稿md] [--name 草稿名]
                       [--draft-folder 剪映草稿目录] [--dry-run]
"""
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from 素材回收 import find_sidecar  # noqa: E402 —— 旁车定位复用

STAMP_NAME = "_media_cut_stamp.json"  # 与 jy_draft 同名戳：两管线互相认账


# ---------------------------------------------------------------- 编排（纯函数）

def _ann_sort_key(a):
    """批注排序键：R01..R09 按数值；非标准 id 排尾部按字典序。"""
    m = re.match(r"^R(\d+)", str(a.get("id", "")))
    return (int(m.group(1)) if m else 10 ** 9, str(a.get("id", "")))


def build_plan(state, project_root):
    """选用素材 → 时间轴编排（纯函数，测试直接调）。

    返回 (clips, orphans, warnings)：
      clips   = [{ann_id, footage_id, rel, abs}]——已按批注顺序+footage 顺序排好，
                跨批注重复引用的素材只在首条批注处落一次
      orphans = [{footage_id, rel, abs}]——选用但没挂批注的（追加时间轴尾部用）
      warnings= [人话]——文件缺失等（缺失素材跳过不出 clip）
    """
    root = Path(project_root)
    footage = [f for f in state.get("footage", []) if isinstance(f, dict)]
    warnings = []
    anns = sorted((a for a in state.get("annotations", [])
                   if isinstance(a, dict) and a.get("id")), key=_ann_sort_key)
    by_ann = {}  # ann_id -> [footage 按数组顺序]
    for f in footage:
        if f.get("state") != "selected":
            continue
        abs_p = root / str(f.get("file", ""))
        if not abs_p.is_file():
            warnings.append(f"素材在盘缺失，跳过：{f.get('file')}"
                            f"（{f.get('id')}）——回面板核对或重挂")
            continue
        for aid in f.get("ann_ids") or []:
            by_ann.setdefault(str(aid), []).append(f)
    clips, used = [], set()
    for a in anns:
        aid = str(a["id"])
        for f in by_ann.get(aid, []):
            if f["id"] in used:      # 跨批注共用：只在首条批注处落一次
                continue
            used.add(f["id"])
            clips.append({"ann_id": aid, "footage_id": str(f["id"]),
                          "rel": str(f.get("file", "")),
                          "abs": str(root / str(f.get("file", "")))})
    orphans = []
    for f in footage:
        if f.get("state") != "selected" or (f.get("ann_ids") or []):
            continue
        abs_p = root / str(f.get("file", ""))
        if not abs_p.is_file():
            warnings.append(f"未挂素材在盘缺失，跳过：{f.get('file')}"
                            f"（{f.get('id')}）")
            continue
        orphans.append({"footage_id": str(f["id"]),
                        "rel": str(f.get("file", "")),
                        "abs": str(abs_p)})
    return clips, orphans, warnings


# ---------------------------------------------------------------- 生成

def _import_jy_helpers():
    """从 cut/scripts 借 jy_draft 的家底（草稿根/防覆盖/登记/fps 收敛）。

    地雷防护（problem-log P6）：cut/scripts 里的 select.py 会遮蔽标准库——
    import 期间临时摘掉所有含 select.py 的路径目录，拿到模块后原样放回
    （jy_draft 及其依赖此时已进 sys.modules 缓存，函数运行期不再吃 path）。
    """
    cut_dir = Path(__file__).resolve().parents[2] / "cut" / "scripts"
    shadow = [p for p in sys.path
              if p and os.path.isfile(os.path.join(p, "select.py"))]
    saved = sys.path[:]
    if shadow:
        sys.path[:] = [p for p in sys.path if p not in shadow]
    if str(cut_dir) not in sys.path:
        sys.path.insert(0, str(cut_dir))
    try:
        import jy_draft
        return jy_draft
    finally:
        sys.path[:] = saved


def generate(project_root, state=None, md_path=None, name=None,
             draft_folder=None, dry_run=False):
    """选用素材 → 剪映草稿。返回结果 dict（dry_run 只返回编排不写盘）。

    友好失败抛 RuntimeError（缺依赖/草稿根不存在/没有选用素材），消息直接给前端。
    """
    root = Path(project_root).resolve()
    if state is None:
        side = find_sidecar(str(root), md_path or "")
        state = json.loads(Path(side).read_text(encoding="utf-8"))
    clips, orphans, warnings = build_plan(state, root)
    if not clips and not orphans:
        raise RuntimeError("没有选用素材——先在面板勾选确认（候选 → 选用）再生成")

    if dry_run:
        return {"ok": True, "dry_run": True, "clips": clips,
                "orphans": orphans, "warnings": warnings,
                "clips_count": len(clips), "orphans_count": len(orphans)}

    # —— 依赖与家底（都在确定要真写盘之后才 import）——
    try:
        from pyJianYingDraft import (ClipSettings, DraftFolder, TextSegment,
                                     Timerange, TrackSpec, TrackType,
                                     TextStyle, VideoMaterial, VideoSegment)
    except ImportError:
        raise RuntimeError("缺依赖：pip install pyJianYingDraft")
    jy = _import_jy_helpers()

    folder = Path(jy.resolve_draft_root(draft_folder))
    if not folder.exists():
        raise RuntimeError(f"剪映草稿目录不存在：{folder}"
                           f"（剪映全局设置→草稿位置；用 --draft-folder 指定）")
    name = name or f"{root.name}_粗拼"
    # 防覆盖（政策同 jy_draft）：被剪映/人工改过的同名稿自动落 v2，绝不覆盖
    existing = folder / name / "draft_content.json"
    if existing.exists():
        stamp = folder / name / STAMP_NAME
        if jy.draft_touched_by_user(existing, stamp):
            base = name
            for n in range(2, 100):
                if not (folder / f"{base}v{n}" / "draft_content.json").exists():
                    name = f"{base}v{n}"
                    break
            else:
                raise RuntimeError(f"草稿版本名用尽：{base}v2..v99 都已存在")
            warnings.append(f"同名草稿被剪映/人工改过——自动落 v2：本次写到 "
                            f"{name}，未覆盖旧稿")

    # —— 时间线 fps 只认 30/60（jy_draft 教训：越界值剪映整条撑长）——
    first_probe = next((c for c in clips if Path(c["abs"]).is_file()), None)
    if first_probe is None:
        raise RuntimeError("选用素材没有一个真实在盘——无法建草稿")
    probe = VideoMaterial(first_probe["abs"])
    fps, coerced = jy.normalize_fps(30)
    if coerced:
        warnings.append("时间线 fps 收敛到 30（剪映只认 30/60）；高帧率素材按原速播放")

    script = DraftFolder(str(folder)).create_draft(
        name, probe.width, probe.height, fps=fps, allow_replace=True)
    script.append_track(TrackSpec(TrackType.video, name="主轨"))
    script.append_track(TrackSpec(TrackType.text, name="标注"))

    t_us = 0
    items = [{"ann_id": c["ann_id"], **c} for c in clips]
    items += [{"ann_id": "", "footage_id": o["footage_id"],
               "rel": o["rel"], "abs": o["abs"]} for o in orphans]
    for it in items:
        material = VideoMaterial(it["abs"])
        dur = int(material.duration)  # μs
        seg = VideoSegment(material,
                           target_timerange=Timerange(t_us, dur),
                           source_timerange=Timerange(0, dur))
        script.add_segment(seg, track="主轨")
        # Rxx 导航标签：2 秒小字挂在段首（左上角，精剪时随手删）
        label = it["ann_id"] or f"尾·未挂（{it['footage_id']}）"
        script.add_segment(
            TextSegment(label, Timerange(t_us, min(2_000_000, dur)),
                        style=TextStyle(size=5, color=(1.0, 1.0, 1.0),
                                        align=1, bold=True),
                        clip_settings=ClipSettings(transform_x=-0.78,
                                                   transform_y=0.82)),
            track="标注")
        t_us += dur

    script.save()
    # —— 收尾三件套（照抄 jy_draft 规矩）：draft_id 随机化 / 盖戳 / 登记索引 ——
    meta_path = folder / name / "draft_meta_info.json"
    import uuid
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["draft_id"] = str(uuid.uuid4()).upper()
    meta["draft_name"] = name
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=4),
                         encoding="utf-8")
    import hashlib
    (folder / name / STAMP_NAME).write_text(json.dumps({
        "sha256": hashlib.sha256(
            (folder / name / "draft_content.json").read_bytes()).hexdigest(),
        "written_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "by": "shoot/剪映草稿",
    }, ensure_ascii=False), encoding="utf-8")
    jy.register_in_root_meta(folder, name)

    return {"ok": True, "name": name, "draft_path": str(folder / name),
            "clips": clips, "clips_count": len(clips),
            "orphans_count": len(orphans), "duration_s": round(t_us / 1e6, 1),
            "warnings": warnings}


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="选用素材粗拼直出剪映草稿（shoot）")
    ap.add_argument("project_root", help="项目根（含定稿 md + shoot.json）")
    ap.add_argument("--md", default="", help="定稿 md（缺省自动找唯一旁车）")
    ap.add_argument("--name", default="", help="草稿名（缺省 <项目根名>_粗拼）")
    ap.add_argument("--draft-folder", default=None,
                    help="剪映草稿目录（缺省：上次位置或剪映默认）")
    ap.add_argument("--dry-run", action="store_true", help="只打印编排不写盘")
    args = ap.parse_args(argv)
    r = generate(args.project_root, md_path=args.md, name=args.name or None,
                 draft_folder=args.draft_folder, dry_run=args.dry_run)
    if r.get("dry_run"):
        print(f"[剪映草稿] 编排预览：{r['clips_count']} 段选用 + "
              f"{r['orphans_count']} 段未挂（将追加尾部）")
        for c in r["clips"]:
            print(f"  {c['ann_id']:>4}  {c['footage_id']}  {c['rel']}")
        for o in r["orphans"]:
            print(f"  尾部  {o['footage_id']}  {o['rel']}（未挂批注）")
    else:
        print(f"[剪映草稿] 已生成「{r['name']}」：{r['clips_count']} 段，"
              f"约 {r['duration_s']}s → {r['draft_path']}")
        print("[剪映草稿] 打开剪映即可精剪；若剪映已开着，重启/刷新草稿列表可见")
    for w in r["warnings"]:
        print(f"[剪映草稿] ⚠ {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
