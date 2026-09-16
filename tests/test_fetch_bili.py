# fetch_bili.py 纯逻辑单元测试——fixtures 是手工构造的接口响应，不真连 B站
# 跑法：python -m unittest discover tests -v
import json
import sys
import unittest
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "skill" / "media-review" / "scripts"))

import fetch_bili as fb  # noqa: E402


def load_fixture(name):
    return json.loads((HERE / "fixtures" / name).read_text(encoding="utf-8"))


def ts(y, m, d):
    """本地时区下的当日零点时间戳（与 compute_watchpoints 的 fromtimestamp 对称）。"""
    return int(datetime(y, m, d).timestamp())


class TestParseArchives(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = load_fixture("list_response.json")
        cls.archives = fb.parse_archives(cls.payload["data"])

    def test条数(self):
        self.assertEqual(len(self.archives), 3)

    def test字段提取(self):
        first = self.archives[0]
        self.assertEqual(first["bvid"], "BV1example01")
        self.assertEqual(first["title"], "ESP32 桌面小机器人：从零到会眨眼")
        self.assertEqual(first["pubtime"], 1789170000)
        self.assertEqual(first["stat"]["view"], 12450)

    def test_stat只留关注的键(self):
        self.assertEqual(set(self.archives[0]["stat"]),
                         {"view", "like", "coin", "favorite", "share", "reply", "danmaku"})

    def test_ptime为0回退ctime(self):
        self.assertEqual(self.archives[2]["pubtime"], 1790000000)


class TestComputeWatchpoints(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 9, 16)

    def make(self, *dates):
        return [{"bvid": f"BV{i}", "title": str(d), "pubtime": ts(*d), "stat": {}}
                for i, d in enumerate(dates)]

    def test_恰好D3算到期(self):
        due = fb.compute_watchpoints(self.make((2026, 9, 13)), self.today)
        self.assertEqual(due[0]["due_points"], [3])

    def test_D5只有D3到期(self):
        due = fb.compute_watchpoints(self.make((2026, 9, 11)), self.today)
        self.assertEqual(due[0]["due_points"], [3])

    def test_D7两个观察点(self):
        due = fb.compute_watchpoints(self.make((2026, 9, 9)), self.today)
        self.assertEqual(due[0]["due_points"], [3, 7])

    def test_D30全到期(self):
        due = fb.compute_watchpoints(self.make((2026, 8, 17)), self.today)
        self.assertEqual(due[0]["due_points"], [3, 7, 30])

    def test_未到期不出现(self):
        self.assertEqual(fb.compute_watchpoints(self.make((2026, 9, 14)), self.today), [])

    def test_pubtime缺失跳过(self):
        archives = [{"bvid": "BVx", "title": "t", "pubtime": None, "stat": {}}]
        self.assertEqual(fb.compute_watchpoints(archives, self.today), [])

    def test_按发布时间升序(self):
        due = fb.compute_watchpoints(
            self.make((2026, 9, 9), (2026, 8, 17)), self.today)
        self.assertEqual([d["age_days"] for d in due], [30, 7])


class TestConvertRates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = load_fixture("diagnose_response.json")
        cls.items = fb.convert_rates(payload["data"]["list"])

    def test_比率换算10000分母(self):
        self.assertAlmostEqual(self.items[0]["full_play_ratio"], 0.2816)
        self.assertAlmostEqual(self.items[0]["tm_rate"], 0.0823)
        self.assertAlmostEqual(self.items[1]["full_play_ratio"], 0.41)

    def test_非比率字段不动(self):
        self.assertEqual(self.items[0]["play"], 12450)
        self.assertEqual(self.items[0]["avg_play_time"], 0)

    def test_空列表(self):
        self.assertEqual(fb.convert_rates([]), [])


if __name__ == "__main__":
    unittest.main()
