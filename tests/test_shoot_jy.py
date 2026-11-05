"""剪映草稿（shoot 粗拼直出）单测。

覆盖：build_plan 编排纯函数（批注数值排序/选用过滤/跨批注共用只落首条/
orphans 追加尾部/缺盘文件跳过告警）、dry-run 零写盘、错误路径（无选用素材/
草稿根不存在）、真 mp4 全链路（imageio_ffmpeg 造 1s 彩条 → 生成到临时草稿根 →
draft_content/盖戳/root_meta 登记断言；依赖缺失时 skip）。

真链路造素材用 imageio_ffmpeg 自带二进制（install.ps1 固定依赖），不碰用户素材。
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# ——先钉真·标准库 select（必须在任何 import 之前，地雷见 problem-log P6）——
import pathlib  # noqa: E402

_shadow_dirs = [p for p in sys.path
                if p and os.path.isfile(os.path.join(p, "select.py"))]
if _shadow_dirs:
    sys.path[:] = [p for p in sys.path if p not in _shadow_dirs]
import select  # noqa: E402 —— 真·标准库
assert hasattr(select, "select"), "标准库 select 被 cut/scripts/select.py 遮蔽"
sys.path.extend(_shadow_dirs)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "media" / "shoot" / "scripts"))

import 剪映草稿 as jys  # noqa: E402

try:
    import imageio_ffmpeg  # noqa: E402
    _FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:  # noqa: BLE001
    _FFMPEG = None

try:
    import pyJianYingDraft  # noqa: F401,E402
    _HAS_JY = True
except Exception:  # noqa: BLE001
    _HAS_JY = False


def _mk_ann(aid):
    return {"id": aid, "block_hash": "ab12cd34ef", "quote": "", "occurrence": 1,
            "kind": "manual", "shoot_hint": "", "ai_type": "", "ai_brief": "",
            "status": "open", "created": "2026-11-06T00:00:00"}


def _mk_foot(fid, rel, state="selected", ann_ids=None):
    return {"id": fid, "file": rel, "ann_ids": ann_ids or [], "state": state,
            "match": "manual", "note": ""}


def _make_state(anns, footage):
    return {"version": 1, "source_sha256": "x" * 64, "locked": True,
            "annotations": anns, "plan": {}, "footage": footage,
            "editNotes": [], "tasks": []}


class TestBuildPlan(unittest.TestCase):
    """编排纯函数：顺序/过滤/去重/孤儿/缺盘。build_plan 查文件在盘，夹具落空文件。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        for name in ("a.mp4", "b.mp4", "shared.mp4", "loose.mp4"):
            (self.root / name).write_bytes(b"")
        self.state_files = {"a": self.root / "a.mp4",
                            "b": self.root / "b.mp4",
                            "shared": self.root / "shared.mp4",
                            "loose": self.root / "loose.mp4"}

    def _rel(self, key):
        return self.state_files[key].name

    def test_批注数值排序与选用过滤(self):
        state = _make_state(
            [_mk_ann("R10"), _mk_ann("R02")],
            [_mk_foot("f01", self._rel("a"), ann_ids=["R02"]),
             _mk_foot("f02", self._rel("b"), state="candidate", ann_ids=["R02"])])
        clips, orphans, warnings = jys.build_plan(state, self.root)
        # R10 没挂素材所以不出 clip；候选不进时间轴
        self.assertEqual([c["ann_id"] for c in clips], ["R02"])
        self.assertEqual([c["footage_id"] for c in clips], ["f01"])
        self.assertEqual(orphans, [])
        self.assertEqual(warnings, [])

    def test_跨批注共用只落首条(self):
        state = _make_state(
            [_mk_ann("R01"), _mk_ann("R08")],
            [_mk_foot("f08", self._rel("shared"), ann_ids=["R01", "R08"])])
        clips, _, _ = jys.build_plan(state, self.root)
        self.assertEqual(len(clips), 1)
        self.assertEqual(clips[0]["ann_id"], "R01")   # 首条批注处落一次

    def test_孤儿追加尾部(self):
        state = _make_state(
            [_mk_ann("R01")],
            [_mk_foot("f01", self._rel("a"), ann_ids=["R01"]),
             _mk_foot("f09", self._rel("loose"), ann_ids=[])])
        clips, orphans, _ = jys.build_plan(state, self.root)
        self.assertEqual([c["ann_id"] for c in clips], ["R01"])
        self.assertEqual([o["footage_id"] for o in orphans], ["f09"])

    def test_缺盘文件跳过并告警(self):
        state = _make_state(
            [_mk_ann("R01")],
            [_mk_foot("f01", "没有这文件.mp4", ann_ids=["R01"])])
        clips, orphans, warnings = jys.build_plan(state, self.root)
        self.assertEqual(clips, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("缺失", warnings[0])

    def test_非标准id排尾部(self):
        state = _make_state(
            [_mk_ann("RZZ"), _mk_ann("R01")],
            [_mk_foot("f01", self._rel("a"), ann_ids=["R01"]),
             _mk_foot("f02", self._rel("b"), ann_ids=["RZZ"])])
        clips, _, _ = jys.build_plan(state, self.root)
        self.assertEqual([c["ann_id"] for c in clips], ["R01", "RZZ"])


class TestGenerate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "proj"
        self.root.mkdir(parents=True)
        self.draft_root = Path(self._tmp.name) / "drafts"

    def test_无选用素材_友好报错(self):
        (self.root / "定稿.md").write_bytes(b"x")
        state = _make_state([_mk_ann("R01")], [])
        with self.assertRaises(RuntimeError) as cm:
            jys.generate(self.root, state=state, draft_folder=self.draft_root)
        self.assertIn("选用素材", str(cm.exception))

    def test_草稿根不存在_友好报错(self):
        (self.root / "定稿.md").write_bytes(b"x")
        state = _make_state([_mk_ann("R01")],
                            [_mk_foot("f01", "a.mp4", ann_ids=["R01"])])
        (self.root / "a.mp4").write_bytes(b"x")
        with self.assertRaises(RuntimeError) as cm:
            jys.generate(self.root, state=state, draft_folder=self.draft_root)
        self.assertIn("草稿目录不存在", str(cm.exception))

    def test_dry_run_零写盘(self):
        (self.root / "定稿.md").write_bytes(b"x")
        (self.root / "a.mp4").write_bytes(b"x")
        state = _make_state([_mk_ann("R01")],
                            [_mk_foot("f01", "a.mp4", ann_ids=["R01"])])
        self.draft_root.mkdir(parents=True)
        r = jys.generate(self.root, state=state, draft_folder=self.draft_root,
                         dry_run=True)
        self.assertTrue(r["dry_run"])
        self.assertEqual(r["clips_count"], 1)
        self.assertEqual(list(self.draft_root.iterdir()), [])  # 一个字节都没写


@unittest.skipUnless(_FFMPEG and _HAS_JY, "需要 imageio_ffmpeg + pyJianYingDraft")
class TestGenerateReal(unittest.TestCase):
    """真 mp4 全链路：造 1s 彩条素材 → 生成到临时草稿根 → 断言草稿/戳/登记。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "proj"
        self.draft_root = Path(self._tmp.name) / "drafts"
        self.draft_root.mkdir(parents=True)
        self.root.mkdir(parents=True)
        (self.root / "定稿.md").write_bytes("# 定稿\n".encode("utf-8"))
        for name in ("a.mp4", "b.mp4"):
            subprocess.run(
                [os.fspath(_FFMPEG), "-y", "-loglevel", "error",
                 "-f", "lavfi", "-i", f"testsrc=duration=1:size=256x256:rate=30",
                 "-pix_fmt", "yuv420p", str(self.root / name)],
                check=True, capture_output=True)

    def test_真链路_草稿与登记落盘(self):
        state = _make_state(
            [_mk_ann("R02"), _mk_ann("R01")],
            [_mk_foot("f01", "a.mp4", ann_ids=["R01"]),
             _mk_foot("f02", "b.mp4", ann_ids=["R02"]),
             _mk_foot("f09", "a.mp4", ann_ids=[])])  # 孤儿（复用 a.mp4 字节）
        r = jys.generate(self.root, state=state, name="测试粗拼",
                         draft_folder=self.draft_root)
        self.assertTrue(r["ok"])
        # 编排：数值序 R01→R02，孤儿 f09 追加尾部
        self.assertEqual([c["ann_id"] for c in r["clips"]], ["R01", "R02"])
        self.assertEqual(r["orphans_count"], 1)
        self.assertGreater(r["duration_s"], 0)
        ddir = self.draft_root / "测试粗拼"
        self.assertTrue((ddir / "draft_content.json").is_file())
        # 盖戳 + draft_id 随机化
        stamp = json.loads((ddir / jys.STAMP_NAME).read_text(encoding="utf-8"))
        self.assertEqual(stamp.get("by"), "shoot/剪映草稿")
        meta = json.loads((ddir / "draft_meta_info.json").read_text(encoding="utf-8"))
        self.assertTrue(len(meta["draft_id"]) >= 32)   # uuid 随机化，非模板固定值
        # root_meta_info.json 登记了同名条目（不登记 = 剪映列表隐形）
        reg = json.loads(
            (self.draft_root / "root_meta_info.json").read_text(encoding="utf-8-sig"))
        names = [e.get("draft_name") for e in reg.get("all_draft_store", [])]
        self.assertIn("测试粗拼", names)
        # 防覆盖：没动过的管线产物原地刷新（同名不涨版本）
        r2 = jys.generate(self.root, state=state, name="测试粗拼",
                          draft_folder=self.draft_root)
        self.assertEqual(r2["name"], "测试粗拼")
        self.assertFalse(any(w.startswith("同名草稿被") for w in r2["warnings"]))

    def test_防覆盖_被改过的同名稿落v2(self):
        state = _make_state([_mk_ann("R01")],
                            [_mk_foot("f01", "a.mp4", ann_ids=["R01"])])
        jys.generate(self.root, state=state, name="粗拼X",
                     draft_folder=self.draft_root)
        # 模拟剪映/人工改动：draft_content 被覆写（戳哈希不符）
        ddir = self.draft_root / "粗拼X"
        content = json.loads((ddir / "draft_content.json").read_text(encoding="utf-8"))
        content["touched"] = True
        (ddir / "draft_content.json").write_text(
            json.dumps(content, ensure_ascii=False), encoding="utf-8")
        r = jys.generate(self.root, state=state, name="粗拼X",
                         draft_folder=self.draft_root)
        self.assertEqual(r["name"], "粗拼Xv2")
        self.assertTrue(any("自动落" in w for w in r["warnings"]))


if __name__ == "__main__":
    unittest.main()
