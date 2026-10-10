"""silence_trim 纯函数单测：VAD 人声岛补集挖洞 + 区间合并。

不跑 ffmpeg/funasr（导入模块会做 ffmpeg 发现，本机走 imageio_ffmpeg 兜底）。
R02 回归用例的岛数据是 2026-10-10 对真实素材（R02_演示.mp4）实测的 FSMN-VAD 输出——
那次事故：ASR 把 05:59-13:33 的 7.5min 底噪并成一条、能量 -35dB 被瞬时毛刺打破，
成片残留 2min 噪声洞；VAD 岛补集必须把洞挖对。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "skill" / "media" / "cut" / "scripts"))
from silence_trim import holes_from_speech  # noqa: E402


class TestHolesFromSpeech(unittest.TestCase):
    def test_basic_complement_with_pad(self):
        holes = holes_from_speech([(10, 20)], 100)
        self.assertEqual(holes, [(0, 9.75), (20.25, 100)])

    def test_pad_clamps_to_bounds(self):
        self.assertEqual(holes_from_speech([(0, 10)], 20), [(10.25, 20)])
        self.assertEqual(holes_from_speech([(10, 20)], 20), [(0, 9.75)])

    def test_short_gap_not_dug(self):
        # 0.5s 停顿加 pad 后为负——自然停顿不挖
        holes = holes_from_speech([(5, 10), (10.5, 20)], 30)
        self.assertEqual(holes, [(0, 4.75), (20.25, 30)])

    def test_all_speech_no_holes(self):
        self.assertEqual(holes_from_speech([(0, 100)], 100), [])

    def test_no_speech_one_hole(self):
        self.assertEqual(holes_from_speech([], 50), [(0, 50)])

    def test_min_s_filters_tiny_holes(self):
        # 两侧人声挤紧时 0.5s 的洞不够 min_s，不挖；尾部 [20,30] 照常成洞
        holes = holes_from_speech([(0, 10), (10.5, 20)], 30, pad=0.0, min_s=0.8)
        self.assertEqual(holes, [(20, 30)])

    def test_r02_entry27_regression(self):
        """R02 实测：7.5min ASR 拉伸条目里的真实 VAD 岛——中间 ~4min 噪声必须成洞。"""
        speech = [(356.2, 360.0), (373.9, 374.4), (387.4, 389.3),
                  (625.9, 626.5), (798.6, 799.2), (812.0, 844.0)]
        holes = holes_from_speech(speech, 850)
        # 大噪声段整体落在某个洞里
        def covered(t):
            return any(s <= t <= e for s, e in holes)
        for t in (395, 450, 500, 620, 640, 700, 795):
            self.assertTrue(covered(t), f"源 {t}s 的噪声没被挖掉: {holes}")
        # 真人声岛不被任何洞触碰
        for s, e in speech:
            for hs, he in holes:
                self.assertFalse(hs < (s + e) / 2 < he,
                                 f"人声岛 [{s},{e}] 被洞 [{hs},{he}] 挖了")


if __name__ == "__main__":
    unittest.main()
