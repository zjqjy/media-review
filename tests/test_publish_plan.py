"""publish_plan 单测（S6-B）：字数校验 / 确认单渲染 / 发布记录。

口径锚点：platforms.json 是常量源，verified=false 的上限也参与校验（保守收紧）；
发布记录与成片同目录同名（<成片>.publish.json），同平台多次发布=多条含时间戳。
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "skill" / "media" / "publish" / "scripts"))
import publish_plan as pp  # noqa: E402

SCRIPT = (Path(__file__).resolve().parents[1]
          / "skill" / "media" / "publish" / "scripts" / "publish_plan.py")


class TestPlatformsTable(unittest.TestCase):
    def test_three_platforms_with_limits(self):
        plats = pp.load_platforms()
        self.assertEqual(set(plats), {"douyin", "bilibili", "xhs"})
        self.assertEqual(plats["douyin"]["title"]["max_chars"], 30)
        self.assertTrue(plats["douyin"]["title"]["verified"])  # 源码实锤的才 true
        for pid, p in plats.items():
            self.assertTrue(p.get("creator_entry"), f"{pid} 缺入口 URL")

    def test_missing_table_raises(self):
        with self.assertRaises(FileNotFoundError):
            pp.load_platforms(Path("Z:/不存在/platforms.json"))


class TestValidateDraft(unittest.TestCase):
    def setUp(self):
        self.plats = pp.load_platforms()

    def test_ok_draft_passes(self):
        self.assertEqual(pp.validate_draft(
            "douyin", {"title": "算" * 30, "desc": "简介", "tags": ["a"]}, self.plats), [])

    def test_title_over_limit_tells_how_many(self):
        errs = pp.validate_draft("douyin", {"title": "字" * 31}, self.plats)
        self.assertTrue(any("30" in e and "超" in e for e in errs), errs)

    def test_title_exact_limit_passes(self):
        self.assertEqual(pp.validate_draft(
            "bilibili", {"title": "题" * 80}, self.plats), [])

    def test_empty_title_rejected(self):
        errs = pp.validate_draft("xhs", {"title": "  "}, self.plats)
        self.assertTrue(any("标题不能为空" in e for e in errs))

    def test_desc_over_limit(self):
        errs = pp.validate_draft("bilibili", {"title": "t", "desc": "介" * 2001}, self.plats)
        self.assertTrue(any("简介" in e and "2000" in e for e in errs), errs)

    def test_too_many_tags(self):
        errs = pp.validate_draft("douyin", {"title": "t", "tags": [f"t{i}" for i in range(11)]},
                                 self.plats)
        self.assertTrue(any("标签" in e for e in errs))

    def test_unknown_platform(self):
        errs = pp.validate_draft("kuaishou", {"title": "t"}, self.plats)
        self.assertTrue(any("未知平台" in e for e in errs))


class TestValidatePlan(unittest.TestCase):
    def setUp(self):
        self.plats = pp.load_platforms()
        self.tmp = tempfile.TemporaryDirectory()
        self.png = Path(self.tmp.name) / "cover_16x9.png"
        self.png.write_bytes(b"\x89PNG fake")

    def tearDown(self):
        self.tmp.cleanup()

    def _plan(self, **kw):
        draft = {"title": "标题", "desc": "", "tags": []}
        plan = {
            "video": "x.mp4",
            "covers": {"douyin": str(self.png), "xhs": str(self.png)},
            "drafts": {"douyin": draft, "bilibili": draft, "xhs": draft},
        }
        plan.update(kw)
        return plan

    def test_missing_cover_for_required_platform(self):
        # xhs 校准后非必设（默认首帧兜底）；douyin 仍必设
        errs = pp.validate_plan(self._plan(covers={"xhs": str(self.png)}), self.plats)
        self.assertIn("douyin", errs)
        self.assertTrue(any("封面必设" in e for e in errs["douyin"]))
        self.assertNotIn("bilibili", errs)  # B站封面可缺
        self.assertNotIn("xhs", errs)

    def test_cover_file_must_exist(self):
        errs = pp.validate_plan(self._plan(covers={
            "douyin": str(self.png), "xhs": "Z:/不存在的图.png"}), self.plats)
        self.assertTrue(any("封面文件不存在" in e for e in errs["xhs"]))

    def test_fully_valid_plan_has_no_errors(self):
        self.assertEqual(pp.validate_plan(self._plan(), self.plats), {})

    def test_missing_draft_counts_as_empty(self):
        errs = pp.validate_plan(
            self._plan(drafts={"douyin": {"title": "t"}}), self.plats)
        self.assertIn("bilibili", errs)  # 缺草稿=空草稿=标题为空


class TestConfirmation(unittest.TestCase):
    def setUp(self):
        self.plats = pp.load_platforms()
        self.tmp = tempfile.TemporaryDirectory()
        self.png = Path(self.tmp.name) / "c.png"
        self.png.write_bytes(b"png")

    def tearDown(self):
        self.tmp.cleanup()

    def test_markdown_contains_counts_and_marks(self):
        plan = {
            "video": "成片.mp4",
            "covers": {"douyin": str(self.png), "xhs": str(self.png)},
            "drafts": {
                "douyin": {"title": "算" * 30, "desc": "", "tags": ["干货"]},
                "bilibili": {"title": "题" * 81, "desc": "", "tags": []},  # 超 1 字
                "xhs": {"title": "种" * 20, "desc": "好物", "tags": []},
            },
        }
        md = pp.build_confirmation(plan, self.plats)
        self.assertIn("发布确认单", md)
        self.assertIn("30/30", md)
        self.assertIn("81/80", md)
        self.assertIn("❌ B站", md)
        self.assertIn("✅ 抖音", md)
        self.assertIn("✅ 小红书", md)
        self.assertIn("待修", md)

    def test_optional_fields_rendered(self):
        # 用户反馈三件套：话题芯片/原创声明/内容类型声明/合集 都要进确认单
        plan = {
            "video": "成片.mp4",
            "covers": {"douyin": "x.png", "xhs": "x.png"},
            "drafts": {
                "douyin": {"title": "标", "desc": "", "tags": [], "topics": ["测试"],
                           "original": True, "declare": "自制", "collection": "硬件测评"},
                "bilibili": {"title": "标", "desc": "", "tags": []},
                "xhs": {"title": "标", "desc": "", "tags": []},
            },
        }
        md = pp.build_confirmation(plan, self.plats)
        self.assertIn("话题（挂芯片）：测试", md)
        self.assertIn("原创声明：✅ 开", md)
        self.assertIn("内容类型声明：自制", md)
        self.assertIn("合集：硬件测评", md)

    def test_all_green_has_no_pending_fix(self):
        plan = {
            "video": "成片.mp4",
            "covers": {"douyin": str(self.png), "xhs": str(self.png)},
            "drafts": {pid: {"title": "标", "desc": "", "tags": []}
                       for pid in ("douyin", "bilibili", "xhs")},
        }
        md = pp.build_confirmation(plan, self.plats)
        self.assertNotIn("❌", md)
        self.assertIn("回复「发」", md)


class TestRecords(unittest.TestCase):
    def test_record_roundtrip_beside_video(self):
        with tempfile.TemporaryDirectory() as d:
            video = Path(d) / "第7期_成片.mp4"
            video.write_bytes(b"")
            rp = pp.record_publish(video, "douyin", "标题A", url=None, now="2026-11-07 10:00:00")
            self.assertEqual(rp, Path(d) / "第7期_成片.publish.json")
            pp.record_publish(video, "douyin", "标题B", url="https://v.douyin.com/x",
                              now="2026-11-07 11:00:00")
            recs = pp.load_records(video)
            self.assertEqual(len(recs), 2)
            self.assertEqual(recs[0]["platform"], "douyin")
            self.assertEqual(recs[1]["url"], "https://v.douyin.com/x")
            self.assertEqual(recs[1]["time"], "2026-11-07 11:00:00")
            self.assertEqual(pp.load_records(Path(d) / "别的视频.mp4"), [])  # 无记录=空表


class TestCli(unittest.TestCase):
    def _run(self, *args):
        return subprocess.run(
            [sys.executable, "-I", str(SCRIPT), *args],
            capture_output=True, text=True, encoding="utf-8", timeout=60)

    def test_check_green_and_red(self):
        with tempfile.TemporaryDirectory() as d:
            png = Path(d) / "c.png"
            png.write_bytes(b"png")
            draft = {"title": "标", "desc": "", "tags": []}
            good = {"video": "v.mp4",
                    "covers": {"douyin": str(png), "xhs": str(png)},
                    "drafts": {pid: draft for pid in ("douyin", "bilibili", "xhs")}}
            plan_file = Path(d) / "plan.json"
            plan_file.write_text(json.dumps(good, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(self._run("check", "--plan", str(plan_file)).returncode, 0)
            bad = dict(good)
            bad["drafts"] = {pid: {"title": "字" * 31, "desc": "", "tags": []}
                             for pid in ("douyin", "bilibili", "xhs")}
            plan_file.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(self._run("check", "--plan", str(plan_file)).returncode, 1)

    def test_confirm_and_record(self):
        with tempfile.TemporaryDirectory() as d:
            png = Path(d) / "c.png"
            png.write_bytes(b"png")
            draft = {"title": "标", "desc": "", "tags": []}
            plan = {"video": str(Path(d) / "v.mp4"),
                    "covers": {"douyin": str(png), "xhs": str(png)},
                    "drafts": {pid: draft for pid in ("douyin", "bilibili", "xhs")}}
            plan_file = Path(d) / "plan.json"
            plan_file.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
            out = self._run("confirm", "--plan", str(plan_file))
            self.assertEqual(out.returncode, 0)
            self.assertIn("发布确认单", out.stdout)
            rec = self._run("record", "--video", str(Path(d) / "v.mp4"),
                            "--platform", "xhs", "--title", "首发", "--url", "https://x.co/1")
            self.assertEqual(rec.returncode, 0)
            self.assertEqual(len(pp.load_records(Path(d) / "v.mp4")), 1)


if __name__ == "__main__":
    unittest.main()
