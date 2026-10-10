"""jy_draft 纯函数单测：normalize_fps 收敛剪映时间线帧率。

背景（2026-10-10 实测事故）：剪映时间线只认 30/60fps，pyJianYingDraft 不校验，
--fps 120 建出的草稿被剪映按 30fps 重解总帧数，时间线整条撑长 4 倍
（464s 成片显示 30:56），缩放等轨道交互全烂。高帧率素材按原速播放，
时间线一律 30/60，normalize_fps 负责兜底收敛。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "skill" / "media" / "cut" / "scripts"))
from jy_draft import normalize_fps  # noqa: E402


class TestNormalizeFps(unittest.TestCase):
    def test_supported_pass_through(self):
        self.assertEqual(normalize_fps(30), (30, False))
        self.assertEqual(normalize_fps(60), (60, False))

    def test_over_120_snaps_to_60(self):
        self.assertEqual(normalize_fps(120), (60, True))
        self.assertEqual(normalize_fps(90), (60, True))

    def test_under_snaps_to_30(self):
        for fps in (0, 24, 25, 29):
            self.assertEqual(normalize_fps(fps), (30, True), fps)

    def test_midway_tie_goes_to_30(self):
        self.assertEqual(normalize_fps(45), (30, True))

    def test_negative_also_snaps(self):
        self.assertEqual(normalize_fps(-5), (30, True))


if __name__ == "__main__":
    unittest.main()
