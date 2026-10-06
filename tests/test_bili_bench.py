# bili_bench.py 纯逻辑单元测试——fixtures 是手工构造的接口响应，不真连 B站
# 跑法：python -m unittest discover tests -v
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "skill" / "media" / "benchmark" / "scripts"))

import bili_bench as bb  # noqa: E402


def load_fixture(name):
    return json.loads((HERE / "fixtures" / name).read_text(encoding="utf-8"))


class TestCleanTitle(unittest.TestCase):
    def test_剥高亮标签(self):
        self.assertEqual(bb.clean_title('<em class="keyword">剪映</em>教程'), "剪映教程")

    def test_无标签原样(self):
        self.assertEqual(bb.clean_title("普通标题"), "普通标题")
        self.assertEqual(bb.clean_title(None), "")


class TestFmtSecs(unittest.TestCase):
    def test_分秒(self):
        self.assertEqual(bb.fmt_secs(754), "12:34")

    def test_时分秒(self):
        self.assertEqual(bb.fmt_secs(18952), "5:15:52")

    def test_空值(self):
        self.assertEqual(bb.fmt_secs(None), "00:00")


class TestExtractBvid(unittest.TestCase):
    def test_纯BV号(self):
        self.assertEqual(bb.extract_bvid("BV1hS4y1N7Gs"), "BV1hS4y1N7Gs")

    def test_完整链接(self):
        self.assertEqual(bb.extract_bvid("https://www.bilibili.com/video/BV1hS4y1N7Gs?p=1"),
                         "BV1hS4y1N7Gs")

    def test_认不出返回None(self):
        self.assertIsNone(bb.extract_bvid("随便一段话"))
        self.assertIsNone(bb.extract_bvid(""))


class TestSrtFromBody(unittest.TestCase):
    def test_转换与时间戳格式(self):
        body = load_fixture("bench_subtitle_body.json")
        srt = bb.srt_from_body(body)
        lines = srt.splitlines()
        self.assertEqual(lines[0], "1")
        self.assertEqual(lines[1], "00:00:00,480 --> 00:00:02,120")
        self.assertEqual(lines[2], "大家好")
        self.assertIn("2\n00:00:02,120 --> 00:00:04,000\n今天教大家", srt)

    def test_空body(self):
        self.assertEqual(bb.srt_from_body([]), "")

    def test_纯文本保留原文(self):
        body = load_fixture("bench_subtitle_body.json")
        text = bb.plain_from_body(body)
        self.assertEqual(text, "大家好\n今天教大家\n嗯，那个，剪辑")


class TestNetscapeLines(unittest.TestCase):
    def test_格式与跳过空值(self):
        text = bb.netscape_lines([("SESSDATA", "abc"), ("buvid3", "")])
        lines = text.splitlines()
        self.assertTrue(lines[0].startswith("# Netscape"))
        cookie = lines[2]
        self.assertEqual(cookie.split("\t")[5], "SESSDATA")
        self.assertEqual(cookie.split("\t")[6], "abc")
        self.assertEqual(len(lines), 3)  # 两行注释 + 一条 cookie（buvid3 空值跳过）


class TestParseSearchResult(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = bb.parse_search_result({"result": load_fixture("bench_search_result.json")})

    def test_只要视频条目(self):
        # fixture 混入一条 type=live 的直播卡，应被过滤
        self.assertEqual(len(self.rows), 2)
        self.assertTrue(all(r["bvid"] for r in self.rows))

    def test_标题剥标签(self):
        self.assertEqual(self.rows[0]["title"], "剪映教程 入门到精通")

    def test_字段提取(self):
        r = self.rows[0]
        self.assertEqual(r["author"], "测试UP主")
        self.assertEqual(r["play"], 5419312)
        self.assertEqual(r["duration"], "12:34")


class TestParseReplyMain(unittest.TestCase):
    def test_解析(self):
        rows = bb.parse_reply_main(load_fixture("bench_reply_main.json"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["like"], 502)
        self.assertEqual(rows[0]["uname"], "高赞用户")
        self.assertEqual(rows[0]["message"], "内容换行 应被替换")  # \n → 空格
        self.assertEqual(rows[1]["reply_ct"], 3)


class TestResolveMid(unittest.TestCase):
    def test_主页链接(self):
        self.assertEqual(bb.resolve_mid("https://space.bilibili.com/477756368"), "477756368")
        self.assertEqual(bb.resolve_mid("space.bilibili.com/477756368/video"), "477756368")

    def test_纯数字(self):
        self.assertEqual(bb.resolve_mid("477756368"), "477756368")

    def test_其他返回None(self):
        self.assertIsNone(bb.resolve_mid("BV1hS4y1N7Gs"))


if __name__ == "__main__":
    unittest.main()
