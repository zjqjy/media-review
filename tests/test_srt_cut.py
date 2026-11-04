"""srt_cut 单测：VAD 边界焊回（P1a 条目边界切字修复）+ build_spans 旧语义回归。

P1a 案卷（.em/problem-log.md）：ASR 把连续语音拆条时边界时间戳撒谎，真词落在
相邻条目的间隙里被整段切掉——R02 #71→#72 间隙 1.34s 落着真词「个」
1711.53-1711.77，新旧管线同切。修法：间隙 < weld_gap 且 VAD 语音岛横跨间隙
两端（间隙内连续人声 → 不是真静音）→ 两段 span 连间隙焊回。

不跑 ffmpeg/funasr：纯函数直测 + process_one 接线用 mock（依赖全替身）。
"""
import argparse
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

# ——先把标准库 select 钉进 sys.modules（必须在 import srt_cut 之前）——
# 地雷：cut/scripts/select.py（素材初选 CLI）与标准库 select 同名。同进程里先跑的
# test_jy_draft / test_silence_trim 会把 cut/scripts 插到 sys.path 前列，本文件随后
# import 链上若有谁再拉起 socket/urllib→select，拿到的是那个假 select。
# 解法：临时摘掉所有含 select.py 的路径目录，import 真 select，再原样放回。
import pathlib  # noqa: E402

_shadow_dirs = [p for p in sys.path
                if p and os.path.isfile(os.path.join(p, "select.py"))]
if _shadow_dirs:
    sys.path[:] = [p for p in sys.path if p not in _shadow_dirs]
import select  # noqa: E402,F401 —— 真·标准库
assert hasattr(select, "select"), "标准库 select 被 cut/scripts/select.py 遮蔽"
sys.path.extend(_shadow_dirs)  # 原样放回，别影响其他测试的导入环境

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "skill" / "media" / "cut" / "scripts"))
import srt_cut  # noqa: E402


def _rnd(spans):
    """浮点收敛到 1e-6 再比较（0.2 这类数在二进制里不精确，断言语义别断在表示上）。"""
    return [(round(s, 6), round(e, 6)) for s, e in spans]


# —— P1a 案卷 R02 场景的合成复刻 ——
# #71 →(1710.60,1711.13)  #72 →(1712.47,1713.10)，间隙恰 1.34s；
# 真词「个」1711.53-1711.77 落在间隙正中——±pad(0.2) 后两段 span 为
# (1710.40,1711.33)/(1712.27,1713.30)，词整段落在 spans 之外（旧版必切）。
E71 = (1710.60, 1711.13, "第七十一句")
E72 = (1712.47, 1713.10, "第七十二句")
WORD = (1711.53, 1711.77)      # 真词「个」
ISLAND = [(1710.80, 1713.00)]  # 横跨间隙两端的连续语音岛（VAD 判不是真静音）
DUR = 1800.0


def _covers(spans, interval):
    """某个 span 是否完整盖住闭区间。"""
    s0, e0 = interval
    return any(s <= s0 and e0 <= e for s, e in spans)


class TestGapIsVoiced(unittest.TestCase):
    """_gap_is_voiced：岛链横跨间隙两端才判连续人声。"""

    def test_straddling_island_with_margins(self):
        self.assertTrue(srt_cut._gap_is_voiced([(10.0, 20.0)], 12.0, 15.0))

    def test_island_touching_ends_exactly(self):
        self.assertTrue(srt_cut._gap_is_voiced([(12.0, 15.0)], 12.0, 15.0))

    def test_island_strictly_inside_not_enough(self):
        # 岛悬在间隙中间、两端都没贴住 → 可能是删行后的残留人声，不焊
        self.assertFalse(srt_cut._gap_is_voiced([(12.5, 14.5)], 12.0, 15.0))

    def test_left_edge_within_tolerance_welds(self):
        # VAD 起点比间隙左端晚 0.15s（≤容差 0.2 的两端微裁）→ 算贴住
        self.assertTrue(srt_cut._gap_is_voiced([(12.15, 16.0)], 12.0, 15.0))

    def test_chain_with_small_break_is_continuous(self):
        # 岛间 0.15s 微缝（≤容差）：FSMN-VAD 对词间短停顿常切岛，算连续
        speech = [(11.0, 12.1), (12.25, 16.0)]
        self.assertTrue(srt_cut._gap_is_voiced(speech, 12.0, 15.0))

    def test_chain_with_real_break_is_silence(self):
        # 岛间 0.35s 无人声断档（>容差）：真停顿/删行留洞，不焊
        speech = [(11.0, 12.1), (12.45, 16.0)]
        self.assertFalse(srt_cut._gap_is_voiced(speech, 12.0, 15.0))

    def test_speech_only_before_gap(self):
        self.assertFalse(srt_cut._gap_is_voiced([(10.0, 12.05)], 12.0, 15.0))

    def test_speech_only_after_gap(self):
        self.assertFalse(srt_cut._gap_is_voiced([(14.95, 16.0)], 12.0, 15.0))

    def test_no_speech_at_all(self):
        self.assertFalse(srt_cut._gap_is_voiced([], 12.0, 15.0))

    def test_speech_far_away(self):
        self.assertFalse(srt_cut._gap_is_voiced([(0.0, 5.0)], 12.0, 15.0))


class TestBuildSpansVadWeld(unittest.TestCase):
    """build_spans 的 VAD 焊回：假间隙焊回、真静音/删行大间隙不焊、降级同旧版。"""

    def test_p1a_r02_gap_welded_word_survives(self):
        """案卷场景：1.34s 假间隙 + 岛横跨 → 焊成一段，真词「个」不再被切。"""
        spans = srt_cut.build_spans([E71, E72], DUR, 0.2, 0.4, vad_speech=ISLAND)
        self.assertEqual(_rnd(spans), [(1710.40, 1713.30)])
        self.assertTrue(_covers(spans, WORD),
                        f"真词 {WORD} 仍落在 spans 之外: {spans}")

    def test_p1a_word_was_cut_before_fix(self):
        """降级对照（钉死案卷真实性）：无 VAD 时词确实在 spans 之外——旧版必切。"""
        spans = srt_cut.build_spans([E71, E72], DUR, 0.2, 0.4)
        self.assertEqual(_rnd(spans), [(1710.40, 1711.33), (1712.27, 1713.30)])
        self.assertFalse(_covers(spans, WORD))

    def test_gap_09s_beyond_gap_merge_welds(self):
        # 0.9s 间隙：--gap(0.4)+双pad(0.4) 并不动它（0.9>0.8），VAD 岛横跨 → 焊回
        a, b = (100.0, 101.0, "甲"), (101.9, 103.0, "乙")
        spans = srt_cut.build_spans([a, b], 200.0, 0.2, 0.4,
                                    vad_speech=[(100.5, 102.5)])
        self.assertEqual(_rnd(spans), [(99.8, 103.2)])

    def test_three_entries_chain_weld(self):
        # 连续三句两两间隙都满足 → 链式焊成一段
        ents = [(100.0, 101.0, "甲"), (101.9, 102.5, "乙"), (103.4, 104.5, "丙")]
        spans = srt_cut.build_spans(ents, 200.0, 0.2, 0.4,
                                    vad_speech=[(100.3, 104.8)])
        self.assertEqual(_rnd(spans), [(99.8, 104.7)])

    def test_gap_3s_not_welded_even_with_island(self):
        # 3s 间隙 ≥ WELD_GAP：即使 VAD 岛横跨也不焊——删行留下的大间隙
        # （被删行不在输入 srt 里）不能焊活被删音频
        a, b = (100.0, 101.0, "甲"), (104.0, 105.0, "乙")
        spans = srt_cut.build_spans([a, b], 200.0, 0.2, 0.4,
                                    vad_speech=[(100.5, 104.5)])
        self.assertEqual(_rnd(spans), [(99.8, 101.2), (103.8, 105.2)])

    def test_real_silence_in_gap_not_welded(self):
        # 间隙 0.9s 但中间有 0.4s 无人声断档（>岛链容差 0.2）→ 真停顿不焊，同现状
        a, b = (100.0, 101.0, "甲"), (101.9, 103.0, "乙")
        spans = srt_cut.build_spans([a, b], 200.0, 0.2, 0.4,
                                    vad_speech=[(100.5, 101.35), (101.75, 102.5)])
        self.assertEqual(_rnd(spans), [(99.8, 101.2), (101.7, 103.2)])

    def test_vad_missing_degrades_exactly_to_legacy(self):
        # VAD 依赖缺失（detect_speech 返回 None）→ 与旧版逐点一致；weld_gap=0 同
        entries = [E71, E72]
        legacy = srt_cut.build_spans(entries, DUR, 0.2, 0.4)
        self.assertEqual(
            srt_cut.build_spans(entries, DUR, 0.2, 0.4, vad_speech=None), legacy)
        self.assertEqual(
            srt_cut.build_spans(entries, DUR, 0.2, 0.4,
                                vad_speech=ISLAND, weld_gap=0), legacy)

    def test_empty_speech_degrades(self):
        # VAD 跑了但全程无人声（空岛表）→ 无从判定连续，不焊
        spans = srt_cut.build_spans([E71, E72], DUR, 0.2, 0.4, vad_speech=[])
        self.assertEqual(len(spans), 2)

    def test_weld_gap_param_respected(self):
        # 阈值参数生效：weld_gap 放宽到 3.5 → 3s 间隙+岛横跨也会焊（标定旋钮）
        a, b = (100.0, 101.0, "甲"), (104.0, 105.0, "乙")
        spans = srt_cut.build_spans([a, b], 200.0, 0.2, 0.4,
                                    vad_speech=[(100.5, 104.5)], weld_gap=3.5)
        self.assertEqual(_rnd(spans), [(99.8, 105.2)])

    def test_unsorted_speech_still_welds(self):
        # 防御：调用方给的岛表乱序也能焊（build_spans 内部先 sorted）
        spans = srt_cut.build_spans([E71, E72], DUR, 0.2, 0.4,
                                    vad_speech=list(reversed(ISLAND)))
        self.assertEqual(len(spans), 1)

    def test_weld_prints_diagnosis_line(self):
        # 焊回发生时打一行诊断（真实素材标定时看它核对焊了几处）
        buf = io.StringIO()
        with redirect_stdout(buf):
            srt_cut.build_spans([E71, E72], DUR, 0.2, 0.4, vad_speech=ISLAND)
        self.assertIn("VAD 焊回", buf.getvalue())
        self.assertIn("1 处", buf.getvalue())


class TestBuildSpansLegacySemantics(unittest.TestCase):
    """--gap/--pad 既有语义不回归（不传 vad_speech 即旧代码路径）。"""

    def test_pad_expansion(self):
        self.assertEqual(_rnd(srt_cut.build_spans([(10, 12, "x")], 100, 0.2, 0.4)),
                         [(9.8, 12.2)])

    def test_pad_clamps_to_zero_and_dur(self):
        self.assertEqual(_rnd(srt_cut.build_spans([(0.1, 99.95, "x")], 100, 0.2, 0.4)),
                         [(0.0, 100.0)])

    def test_gap_merges_close_entries(self):
        # 原始间隙 0.5 ≤ gap+2pad(0.8) → 并一段
        ents = [(10, 11, "a"), (11.5, 12, "b")]
        self.assertEqual(_rnd(srt_cut.build_spans(ents, 100, 0.2, 0.4)),
                         [(9.8, 12.2)])

    def test_gap_keeps_far_entries(self):
        # 原始间隙 1.0 > 0.8 → 两段（无 VAD 时的现状；给了岛才会焊回）
        ents = [(10, 11, "a"), (12.0, 13, "b")]
        self.assertEqual(_rnd(srt_cut.build_spans(ents, 100, 0.2, 0.4)),
                         [(9.8, 11.2), (11.8, 13.2)])

    def test_unsorted_input_sorted(self):
        ents = [(12, 13, "b"), (10, 11, "a")]
        self.assertEqual(_rnd(srt_cut.build_spans(ents, 100, 0.2, 0.4)),
                         [(9.8, 11.2), (11.8, 13.2)])


class TestProcessOneWiring(unittest.TestCase):
    """接线：--weld-gap 把 detect_speech 的人声岛喂进 build_spans，落到 ffmpeg 条件里。

    process_one 的外设（时长探测/cuts 查找/VAD/ffmpeg）全 mock，只验数据流；
    成片 select 条件里间隙区间的存亡就是最终裁决。
    """

    SRT = ("71\n00:28:30,600 --> 00:28:31,130\n第七十一句\n\n"
           "72\n00:28:32,470 --> 00:28:33,100\n第七十二句\n")

    def _args(self, weld_gap):
        return argparse.Namespace(pad=0.2, gap=0.4, min_inner=0.0, db=None,
                                  audio_only=True, out_dir=None, weld_gap=weld_gap)

    def _run_process(self, weld_gap, speech):
        """跑 process_one（mock 外设），返回 (ffmpeg 命令, stdout)。"""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            video = Path(td) / "R02_演示.mp4"
            video.touch()
            srt = Path(td) / "剪切稿.srt"
            srt.write_text(self.SRT, encoding="utf-8")
            cmds = []
            buf = io.StringIO()
            with redirect_stdout(buf), \
                 mock.patch.object(srt_cut, "duration_of", return_value=DUR), \
                 mock.patch.object(srt_cut, "find_cuts_json", return_value=None), \
                 mock.patch.object(srt_cut, "detect_speech", return_value=speech) as ds, \
                 mock.patch.object(srt_cut, "run", side_effect=lambda c: cmds.append(c)):
                srt_cut.process_one(video, srt, self._args(weld_gap))
            return cmds, ds, buf.getvalue()

    @staticmethod
    def _af(cmds):
        return cmds[0][cmds[0].index("-af") + 1]

    def test_weld_reaches_ffmpeg_select(self):
        # 案卷场景全链路：VAD 岛 → 焊回 → select 条件里间隙（含真词区间）整段保留
        cmds, ds, out = self._run_process(2.0, ISLAND)
        ds.assert_called_once()
        self.assertIn("between(t,1710.40,1713.30)", self._af(cmds))
        self.assertIn("VAD 焊回", out)

    def test_weld_gap_zero_skips_vad(self):
        # --weld-gap 0：不碰 VAD（零开销），select 条件与旧版一致的两段
        cmds, ds, _ = self._run_process(0, ISLAND)
        ds.assert_not_called()
        af = self._af(cmds)
        self.assertIn("between(t,1710.40,1711.33)", af)
        self.assertIn("between(t,1712.27,1713.30)", af)

    def test_vad_missing_degrades_with_notice(self):
        # funasr 缺失（detect_speech→None）：显式提示 + 行为同旧版
        cmds, ds, out = self._run_process(2.0, None)
        ds.assert_called_once()
        af = self._af(cmds)
        self.assertIn("between(t,1710.40,1711.33)", af)
        self.assertIn("between(t,1712.27,1713.30)", af)
        self.assertIn("边界焊回跳过", out)


if __name__ == "__main__":
    unittest.main()
