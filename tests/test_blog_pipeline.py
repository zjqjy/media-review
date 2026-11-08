"""S7 blog 子技能单测：blog_plan schema 校验 + frame_pick 预览/命名 + site_check 站点规矩
+ gzh_pack 打包（vendor html_converter 冒烟）。

覆盖点（对齐 S7-B/C 交付口径）：
  - blog_plan：slug/date/categories/frames/links/gzh 全维校验，错误定位到字段；
  - frame_pick：帧文件名 NN-name.jpg + 预览页自包含生成（抽帧本体归真一期 dry-run）；
  - site_check：文件名规矩/frontmatter 必填/links key 注册/图片存在/裸网盘链警告、
    yaml 缺失时极简解析兜底同结论；
  - gzh_pack：md 图片→占位符改写+images.json 清单+字数体检+vendor 转换器真跑一次；
  - vendor 冒烟：html_converter 15 主题可见、ai_score.py --help 依赖闭包可导入。
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "media" / "blog" / "scripts"))

import blog_plan  # noqa: E402
import frame_pick  # noqa: E402
import gzh_pack  # noqa: E402
import site_check  # noqa: E402

VENDOR_SCRIPTS = ROOT / "skill" / "media" / "blog" / "vendor" / "wechat-publisher" / "scripts"

GOOD_PLAN = {
    "slug": "esp32-lcd-screen",
    "episode": "第5期",
    "title": "AI 驱动 LCD 屏幕：三步走",
    "date": "2026-11-08",
    "categories": ["工程笔记"],
    "tags": ["ESP32", "AI"],
    "video": "video.mp4",
    "srt": "video.srt",
    "transcript": "transcript.md",
    "frames": [
        {"t": 63.5, "name": "install", "alt": "安装引导界面", "caption": "双击安装包",
         "section": "第一步"},
        {"t": 120, "name": "wiring", "alt": "接线图", "caption": "", "section": "第二步"},
    ],
    "links": [{"key": "ego_lite_download", "label": "ego lite 下载", "url": "https://x.y"}],
    "gzh": {"theme": "minimal-mono", "author": "阿程", "digest": "三步点亮屏幕"},
}


def write_tiny_jpg(p: Path) -> None:
    # 仅占位（site_check/gzh_pack 只查存在性）；真 JPEG 归 frame_pick ffmpeg 抽帧产生
    p.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 32)


class TestBlogPlan(unittest.TestCase):
    def test_good_plan_passes(self):
        self.assertEqual(blog_plan.validate_plan(GOOD_PLAN), [])

    def test_bad_slug(self):
        e = blog_plan.validate_plan({**GOOD_PLAN, "slug": "点亮屏幕"})
        self.assertTrue(any("slug" in x for x in e))

    def test_bad_date_and_categories(self):
        e = blog_plan.validate_plan({**GOOD_PLAN, "date": "2026/11/08",
                                     "categories": ["a", "b"]})
        self.assertTrue(any("date" in x for x in e))
        self.assertTrue(any("categories" in x for x in e))

    def test_frames_duplicate_name_and_missing_alt(self):
        plan = {**GOOD_PLAN, "frames": [
            {"t": 1, "name": "01-a", "alt": "x"},
            {"t": 2, "name": "01-a", "alt": ""},
        ]}
        e = blog_plan.validate_plan(plan)
        self.assertTrue(any("重复" in x for x in e))
        self.assertTrue(any("alt" in x for x in e))

    def test_negative_t(self):
        plan = {**GOOD_PLAN, "frames": [{"t": -1, "name": "01-a", "alt": "x"}]}
        self.assertTrue(any("为负" in x for x in blog_plan.validate_plan(plan)))

    def test_links_bad_key_and_digest_overflow(self):
        plan = {**GOOD_PLAN,
                "links": [{"key": "中文键", "label": "l", "url": "u"}],
                "gzh": {"theme": "minimal-mono", "digest": "x" * 121}}
        e = blog_plan.validate_plan(plan)
        self.assertTrue(any("key" in x for x in e))
        self.assertTrue(any("gzh.digest" in x for x in e))

    def test_frame_filename(self):
        self.assertEqual(blog_plan.frame_filename(3, "install"), "03-install.jpg")


class TestFramePickPreview(unittest.TestCase):
    def test_preview_page_built(self):
        with tempfile.TemporaryDirectory() as td:
            frames_dir = Path(td) / "images" / GOOD_PLAN["slug"]
            frames_dir.mkdir(parents=True)
            write_tiny_jpg(frames_dir / "01-install.jpg")
            write_tiny_jpg(frames_dir / "02-wiring.jpg")
            out = frame_pick.build_preview(GOOD_PLAN, frames_dir,
                                           Path(td) / "preview")
            text = out.read_text(encoding="utf-8")
            self.assertIn("选帧预览", text)
            self.assertIn("#1", text)
            self.assertIn("file:///", text)          # 帧图绝对 URI（预览页独立于站点树）
            self.assertIn("01-install.jpg", text)
            self.assertIn("01-install.jpg)", text)   # onerror 占位包含文件名


class TestSiteCheck(unittest.TestCase):
    def _make_site(self, root: Path, body_extra: str = "") -> Path:
        slug = "esp32-lcd-screen"
        posts = root / "source" / "_posts"
        imgs = root / "source" / "images" / slug
        data = root / "source" / "_data"
        for d in (posts, imgs, data):
            d.mkdir(parents=True, exist_ok=True)
        write_tiny_jpg(imgs / "01-install.jpg")
        (data / "links.yml").write_text(
            "esp32-lcd-screen:\n"
            "  - key: ego_lite_download\n    label: 下载\n"
            "    url: https://x.y\n    type: official\n    status: active\n",
            encoding="utf-8")
        md = (
            "---\ntitle: 三步点亮屏幕\ndate: 2026-11-08\n"
            "categories:\n  - 工程笔记\ntags:\n  - ESP32\n---\n\n"
            "结论先行：三步就能点亮。这里讲接线。\n\n"
            "![安装引导](/images/esp32-lcd-screen/01-install.jpg)\n\n"
            f'下载地址：{{% link "ego_lite_download" %}}\n\n{body_extra}'
            "后面再补一大段正文内容用于超过两百字符的最短长度门槛要求，"
            "嵌入式工程师的日常就是把点亮的灯再变成会响会听的机器，这一步靠 AI 提效不少，"
            "具体步骤正文里逐条展开，先学习再接线再实现，每一步都有图文对照，跟着做就行。"
            "最后补一句常见坑：PATH 只对新开进程生效，装完必须新开终端再验证，别在老窗口里反复试。\n"
        )
        p = posts / f"{slug}.md"
        p.write_text(md, encoding="utf-8")
        return p

    def test_good_post_passes(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._make_site(Path(td))
            self.assertEqual(site_check.check_post(p, Path(td)), 0)

    def test_missing_image_fails(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._make_site(Path(td))
            (Path(td) / "source/images/esp32-lcd-screen/01-install.jpg").unlink()
            self.assertEqual(site_check.check_post(p, Path(td)), 1)

    def test_unregistered_link_key_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = self._make_site(root)
            text = p.read_text(encoding="utf-8").replace("ego_lite_download", "no_such_key")
            p.write_text(text, encoding="utf-8")
            self.assertEqual(site_check.check_post(p, root), 1)

    def test_bare_pan_link_warns_and_strict_fails(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._make_site(Path(td), body_extra="网盘见 https://pan.baidu.com/s/abc\n\n")
            self.assertEqual(site_check.check_post(p, Path(td)), 0)  # 警告不挡
            self.assertEqual(site_check.check_post(p, Path(td), strict=True), 1)

    def test_chinese_filename_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = self._make_site(root)
            bad = p.with_name("点亮屏幕.md")
            bad.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
            self.assertEqual(site_check.check_post(bad, root), 1)

    def test_fallback_parser_same_verdict(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = self._make_site(root)
            orig = site_check._HAS_YAML
            try:
                site_check._HAS_YAML = False
                fm, body = site_check.split_frontmatter(p.read_text(encoding="utf-8"))
                self.assertEqual(fm["title"], "三步点亮屏幕")
                self.assertEqual(fm["categories"], ["工程笔记"])
                self.assertEqual(fm["tags"], ["ESP32"])
                self.assertEqual(site_check.check_post(p, root), 0)
            finally:
                site_check._HAS_YAML = orig


class TestGzhPack(unittest.TestCase):
    BODY = ("结论先行：三步点亮。\n\n"
            "![安装引导](/images/esp32-lcd-screen/01-install.jpg)\n\n"
            "接着讲接线。**接线图如下**。\n\n"
            "![接线](/images/esp32-lcd-screen/02-wiring.jpg)\n\n"
            "下载走 {% link \"ego_lite_download\" %}。收尾。")

    def test_rewrite_images(self):
        with tempfile.TemporaryDirectory() as td:
            imgs: list[dict] = []
            body = gzh_pack.rewrite_images(self.BODY, Path(td), imgs)
            self.assertEqual(len(imgs), 2)
            self.assertEqual(imgs[0]["name"], "01-install.jpg")
            self.assertEqual(imgs[1]["n"], 2)
            self.assertEqual(body.count("⟦图"), 2)
            self.assertNotIn("/images/", body)

    def test_pack_end_to_end_with_vendor_converter(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            imgs_dir = root / "source" / "images" / GOOD_PLAN["slug"]
            imgs_dir.mkdir(parents=True)
            write_tiny_jpg(imgs_dir / "01-install.jpg")
            write_tiny_jpg(imgs_dir / "02-wiring.jpg")
            post = root / "post.md"
            post.write_text("---\ntitle: t\n---\n\n" + self.BODY, encoding="utf-8")
            out = root / "pack"
            rc = gzh_pack.main(["--plan", str(_plan_file(root)), "--post", str(post),
                                "--site-root", str(root), "--out", str(out)])
            self.assertEqual(rc, 0)
            html = (out / "gzh.html").read_text(encoding="utf-8")
            manifest = json.loads((out / "images.json").read_text(encoding="utf-8"))
            self.assertIn("style=", html)          # 内联样式（公众号编辑器规矩）
            self.assertEqual(len(manifest), 2)
            report = (out / "report.txt").read_text(encoding="utf-8")
            self.assertNotIn("FAIL", report)

    def test_title_overflow_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            imgs_dir = root / "source" / "images" / GOOD_PLAN["slug"]
            imgs_dir.mkdir(parents=True)
            write_tiny_jpg(imgs_dir / "01-install.jpg")
            write_tiny_jpg(imgs_dir / "02-wiring.jpg")
            post = root / "post.md"
            post.write_text("---\ntitle: t\n---\n\n" + self.BODY, encoding="utf-8")
            plan = {**GOOD_PLAN, "gzh": {**GOOD_PLAN["gzh"], "title": "长" * 65}}
            pf = root / "plan.json"
            pf.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
            rc = gzh_pack.main(["--plan", str(pf), "--post", str(post),
                                "--site-root", str(root), "--out", str(root / "pack")])
            self.assertEqual(rc, 1)


def _plan_file(root: Path) -> Path:
    pf = root / "plan.json"
    pf.write_text(json.dumps(GOOD_PLAN, ensure_ascii=False), encoding="utf-8")
    return pf


class TestVendorSmoke(unittest.TestCase):
    def test_themes_visible_via_upstream_layout(self):
        sys.path.insert(0, str(VENDOR_SCRIPTS))
        try:
            import html_converter  # noqa: E402  上游相对 layout：scripts→parent.parent/assets
            themes = html_converter.list_themes()
            self.assertGreaterEqual(len(themes), 15)
            self.assertIn("minimal-mono", themes)
        finally:
            sys.path.remove(str(VENDOR_SCRIPTS))

    def test_ai_score_importable_and_cli_alive(self):
        r = subprocess.run([sys.executable, str(VENDOR_SCRIPTS / "ai_score.py"), "--help"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
