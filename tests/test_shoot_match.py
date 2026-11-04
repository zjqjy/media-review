"""素材回收匹配 + shoot 面板服务端单测。

覆盖：文件名精确匹配（大小写/全半角宽容、后随数字防误吃）、双 id 挂接、
unmatched 报告、幂等重跑、--dry-run、定稿 sha 拦截、footage 批量更新白名单校验、
HTTP API（/api/project、/api/state、/api/footage、/api/missing）。

不测真实视频时长（夹具是空文件，ffmpeg 探不到），只测 Duration 解析纯函数。
"""
import os
import sys

# ——先把标准库 select 钉进 sys.modules（必须在 import urllib / shoot_server 之前）——
# 地雷：cut/scripts/select.py（素材初选 CLI）与标准库 select 同名。同进程里先跑的
# test_jy_draft / test_silence_trim 会把 cut/scripts 插到 sys.path 前列，本文件随后
# import urllib→socket→selectors→import select 时拿到的是那个假 select，导致
# ThreadingHTTPServer 的 serve_forever 线程 AttributeError，全部 HTTP 测试超时。
# 解法：临时摘掉所有含 select.py 的路径目录，import 真 select，再原样放回。
import pathlib  # noqa: E402

_shadow_dirs = [p for p in sys.path
                if p and os.path.isfile(os.path.join(p, "select.py"))]
if _shadow_dirs:
    sys.path[:] = [p for p in sys.path if p not in _shadow_dirs]
import select  # noqa: E402 —— 真·标准库
assert hasattr(select, "select"), "标准库 select 被 cut/scripts/select.py 遮蔽"
sys.path.extend(_shadow_dirs)  # 原样放回，别影响其他测试的导入环境

import hashlib
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "media" / "shoot" / "scripts"))

import 素材回收 as recycle  # noqa: E402
import shoot_server  # noqa: E402

MD_TEXT = "# 定稿口播\n\n第一段口播。\n\n第二段口播。\n"


def _mk_ann(aid, kind="manual", quote="", hint="", ai_type="", ai_brief=""):
    """按冻结 schema v1 造一条呈现批注。"""
    return {"id": aid, "block_hash": "ab12cd34ef"[:10], "quote": quote,
            "occurrence": 1, "kind": kind, "shoot_hint": hint,
            "ai_type": ai_type, "ai_brief": ai_brief, "status": "open",
            "created": "2026-11-05T10:00:00"}


def make_project(tmp, files=(), footage=None, anns=None):
    """造假项目：定稿 md + 旁车 shoot.json（指纹配套）+ 素材空文件。
    返回项目根 Path。"""
    root = Path(tmp)
    # md 用字节写：write_text 在 Windows 会把 \n 翻译成 \r\n，指纹就对不上了
    (root / "定稿.md").write_bytes(MD_TEXT.encode("utf-8"))
    sha = hashlib.sha256(MD_TEXT.encode("utf-8")).hexdigest()
    state = {
        "version": 1, "source_sha256": sha, "locked": True,
        "annotations": anns if anns is not None else [
            _mk_ann("R01", "manual", quote="开机仰角拍产品", hint="三脚架仰拍"),
            _mk_ann("R02", "ai", quote="数据卡片", ai_type="card",
                    ai_brief="做一张留存数据卡"),
            _mk_ann("R03", "manual", quote="关机特写", hint="手拧开关特写"),
            _mk_ann("R04", "manual", quote="桌面全景", hint="俯拍桌面"),
            _mk_ann("R05", "ai", quote="转场动效", ai_type="motion",
                    ai_brief="logo 转场"),
        ],
        "plan": {"checklist_md": "", "ai_tasks_md": ""},
        "footage": footage if footage is not None else [],
        "editNotes": [], "tasks": [],
    }
    (root / "定稿.md.shoot.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    for rel in files:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"")  # 空文件足够——匹配只看文件名
    return root


def read_state(root):
    return json.loads((root / "定稿.md.shoot.json").read_text(encoding="utf-8"))


class TestIdInName(unittest.TestCase):
    """匹配内核：宽容度与防误吃。"""

    def test_大小写与全半角宽容(self):
        self.assertTrue(recycle.id_in_name("R03", "R03_开机仰角.mp4"))
        self.assertTrue(recycle.id_in_name("R03", "r03_开机仰角.MP4"))
        self.assertTrue(recycle.id_in_name("R05", "Ｒ０５_全角.mp4"))
        self.assertTrue(recycle.id_in_name("R04", "r04_小写.JPG"))

    def test_后随数字不命中(self):
        # R01 不能吃进 R010；R1 不能吃进 R12
        self.assertFalse(recycle.id_in_name("R01", "R010_混淆.mp4"))
        self.assertFalse(recycle.id_in_name("R1", "R12_混淆.mp4"))

    def test_前随字符不设限_双命中文件两头命中(self):
        self.assertTrue(recycle.id_in_name("R01", "R01R03双命中.mp4"))
        self.assertTrue(recycle.id_in_name("R03", "R01R03双命中.mp4"))

    def test_多命中按批注顺序(self):
        hits = recycle.match_file_to_anns(
            "R01R03双命中.mp4", ["R01", "R02", "R03"])
        self.assertEqual(hits, ["R01", "R03"])


class TestMatchCli(unittest.TestCase):
    """CLI 全链路：匹配 → 挂接 → 报告 → 幂等。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def test_精确匹配挂候选(self):
        root = make_project(self._tmp.name, files=[
            "拍摄素材/R01_a.mp4", "拍摄素材/R02_b.mp4"])
        self.assertEqual(recycle.run(str(root)), 0)
        st = read_state(root)
        self.assertEqual(len(st["footage"]), 2)
        f1 = next(f for f in st["footage"] if f["file"].endswith("R01_a.mp4"))
        self.assertEqual(f1["ann_ids"], ["R01"])
        self.assertEqual(f1["state"], "candidate")
        self.assertEqual(f1["match"], "filename")
        self.assertEqual(f1["id"], "f01")
        # 相对路径用 posix 分隔，且相对项目根
        self.assertEqual(f1["file"], "拍摄素材/R01_a.mp4")

    def test_双命中与一条id多文件(self):
        root = make_project(self._tmp.name, files=[
            "拍摄素材/R01_a.mp4", "拍摄素材/R01R03双命中.mp4"])
        self.assertEqual(recycle.run(str(root)), 0)
        st = read_state(root)
        dbl = next(f for f in st["footage"] if "双命中" in f["file"])
        self.assertEqual(dbl["ann_ids"], ["R01", "R03"])
        # R01 命中两个文件 → 全部挂候选
        r01 = [f for f in st["footage"] if "R01" in f["ann_ids"]]
        self.assertEqual(len(r01), 2)
        self.assertTrue(all(f["state"] == "candidate" for f in r01))

    def test_大小写全角命中_后随数字不命中(self):
        root = make_project(self._tmp.name, files=[
            "拍摄素材/r04_小写.JPG", "拍摄素材/Ｒ０５_全角.mp4",
            "拍摄素材/R010_混淆.mp4"])
        self.assertEqual(recycle.run(str(root)), 0)
        st = read_state(root)
        by_ann = {}
        for f in st["footage"]:
            for aid in f["ann_ids"]:
                by_ann.setdefault(aid, []).append(f["file"])
        self.assertEqual(by_ann.get("R04"), ["拍摄素材/r04_小写.JPG"])
        self.assertEqual(by_ann.get("R05"), ["拍摄素材/Ｒ０５_全角.mp4"])
        # R010_混淆.mp4 不该挂到 R01 → 不进 footage，只进报告
        self.assertNotIn("R01", by_ann)
        report = (root / "素材回收报告.md").read_text(encoding="utf-8")
        self.assertIn("R010_混淆.mp4", report)

    def test_未匹配进报告_建议列留空(self):
        root = make_project(self._tmp.name, files=[
            "拍摄素材/random1.mp4", "拍摄素材/random2.png"])
        self.assertEqual(recycle.run(str(root)), 0)
        st = read_state(root)
        self.assertEqual(st["footage"], [])   # 没命中就不挂接
        report = (root / "素材回收报告.md").read_text(encoding="utf-8")
        self.assertIn("random1.mp4", report)
        self.assertIn("random2.png", report)
        self.assertIn("建议", report)          # 建议列表头在，列内容留给 AI 填
        self.assertIn("未匹配 2", report)

    def test_幂等重跑不重复挂接(self):
        root = make_project(self._tmp.name, files=[
            "拍摄素材/R01_a.mp4", "拍摄素材/random1.mp4"])
        self.assertEqual(recycle.run(str(root)), 0)
        first = read_state(root)
        self.assertEqual(len(first["footage"]), 1)
        self.assertEqual(recycle.run(str(root)), 0)  # 第二遍
        second = read_state(root)
        self.assertEqual(second["footage"], first["footage"])  # 原样，无重复
        # 已选用状态不被重跑冲掉
        second["footage"][0]["state"] = "selected"
        (root / "定稿.md.shoot.json").write_text(
            json.dumps(second, ensure_ascii=False, indent=2), encoding="utf-8")
        self.assertEqual(recycle.run(str(root)), 0)
        self.assertEqual(read_state(root)["footage"][0]["state"], "selected")

    def test_dry_run不写盘(self):
        root = make_project(self._tmp.name, files=["拍摄素材/R01_a.mp4"])
        self.assertEqual(recycle.run(str(root), dry_run=True), 0)
        self.assertEqual(read_state(root)["footage"], [])      # 旁车没动
        self.assertFalse((root / "素材回收报告.md").exists())  # 报告没落

    def test_定稿被外部改动拒写(self):
        root = make_project(self._tmp.name, files=["拍摄素材/R01_a.mp4"])
        (root / "定稿.md").write_bytes((MD_TEXT + "外部改动\n").encode("utf-8"))
        self.assertEqual(recycle.run(str(root)), 1)
        self.assertEqual(read_state(root)["footage"], [])      # 一个字没写

    def test_缺旁车报错(self):
        root = Path(self._tmp.name)
        root.mkdir(exist_ok=True)
        self.assertEqual(recycle.run(str(root)), 1)

    def test_footage_dir限定扫描范围(self):
        root = make_project(self._tmp.name, files=[
            "拍摄素材/R01_a.mp4", "不要扫/R02_b.mp4"])
        self.assertEqual(recycle.run(str(root), footage_dir="拍摄素材"), 0)
        st = read_state(root)
        self.assertEqual([f["file"] for f in st["footage"]],
                         ["拍摄素材/R01_a.mp4"])

    def test_footage_dir逃出项目根被拒(self):
        root = make_project(self._tmp.name, files=["拍摄素材/R01_a.mp4"])
        self.assertEqual(recycle.run(str(root), footage_dir="../外面"), 1)
        self.assertEqual(read_state(root)["footage"], [])


class TestReportAndSidecar(unittest.TestCase):
    """报告辅助与旁车定位。"""

    def test_解析ffmpeg时长(self):
        self.assertEqual(
            recycle.parse_ffmpeg_duration("Duration: 00:01:02.34, start: 0"),
            62.34)
        self.assertEqual(recycle.parse_ffmpeg_duration("没有 Duration"),
                         None)

    def test_旁车定位_唯一顶层(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp)
            md, side = recycle.find_sidecar(root)
            self.assertEqual(side.name, "定稿.md.shoot.json")
            self.assertEqual(md.name, "定稿.md")

    def test_旁车定位_多份要消歧(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(tmp)
            (root / "定稿2.md").write_text(MD_TEXT, encoding="utf-8")
            (root / "定稿2.md.shoot.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                recycle.find_sidecar(root)
            md, side = recycle.find_sidecar(root, "定稿2.md")  # --md 消歧
            self.assertEqual(side.name, "定稿2.md.shoot.json")

    def test_旁车定位_递归兜底(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sub = root / "项目A"
            sub.mkdir()
            (sub / "定稿.md").write_text(MD_TEXT, encoding="utf-8")
            (sub / "定稿.md.shoot.json").write_text("{}", encoding="utf-8")
            md, side = recycle.find_sidecar(root)
            self.assertEqual(side.parent, sub)


def _fixture_state():
    return {
        "version": 1, "source_sha256": "x" * 64, "locked": True,
        "annotations": [_mk_ann("R01"), _mk_ann("R02"), _mk_ann("R03")],
        "plan": {"checklist_md": "", "ai_tasks_md": ""},
        "footage": [
            {"id": "f01", "file": "a/R01_a.mp4", "ann_ids": ["R01"],
             "state": "candidate", "match": "filename", "note": ""},
        ],
        "editNotes": [], "tasks": [],
    }


class TestApplyUpdates(unittest.TestCase):
    """批量更新白名单校验（纯函数）。"""

    def test_合法状态与备注(self):
        st = _fixture_state()
        n = shoot_server.apply_updates(st, [
            {"footage_id": "f01", "state": "selected"},
            {"footage_id": "f01", "note": "截 0:03-0:07"},
        ])
        self.assertEqual(n, 2)
        self.assertEqual(st["footage"][0]["state"], "selected")
        self.assertEqual(st["footage"][0]["note"], "截 0:03-0:07")

    def test_挂接去重保序(self):
        st = _fixture_state()
        shoot_server.apply_updates(
            st, [{"footage_id": "f01",
                  "ann_ids": ["R03", "R01", "R03"]}])
        self.assertEqual(st["footage"][0]["ann_ids"], ["R03", "R01"])

    def test_非法写一律拒(self):
        st = _fixture_state()
        for bad in [
            {"footage_id": "f99", "state": "selected"},        # 条目不存在
            {"footage_id": "f01", "state": "selected2"},       # 非法枚举
            {"footage_id": "f01", "note": 123},                # note 非字符串
            {"footage_id": "f01", "ann_ids": ["R09"]},         # 未知批注 id
            {"footage_id": "f01", "ann_ids": "R01"},           # ann_ids 非数组
            {"footage_id": "f01", "match": "ai:0.9"},          # match 限 manual（机器来源不许伪造）
            {"footage_id": "f01"},                             # 啥都没改
        ]:
            with self.assertRaises(ValueError, msg=bad):
                shoot_server.apply_updates(st, [bad])
        with self.assertRaises(ValueError):                    # 空 updates
            shoot_server.apply_updates(st, [])


class TestServerApi(unittest.TestCase):
    """HTTP API：起真服务（127.0.0.1 随机端口）走一遍。"""

    @classmethod
    def setUpClass(cls):
        cls.srv = shoot_server.make_server("127.0.0.1", 0)
        cls.port = cls.srv.server_address[1]
        cls.thread = threading.Thread(target=cls.srv.serve_forever,
                                      daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        shoot_server.reset_ctx()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _req(self, method, path, body=None):
        url = f"http://127.0.0.1:{self.port}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            url, data=data, method=method,
            headers={"Content-Type": "application/json"} if data else {})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_项目校验与state与批量写回(self):
        root = make_project(self._tmp.name, files=["拍摄素材/R01_a.mp4"])
        self.assertEqual(recycle.run(str(root)), 0)   # 先跑匹配器，footage 才有条目
        # 未设项目时读 state → 拒
        s, d = self._req("GET", "/api/state")
        self.assertEqual(s, 200)
        self.assertIsNone(d["project_root"])
        # 打开项目（校验定稿 + 旁车）
        s, d = self._req("POST", "/api/project", {"project": str(root)})
        self.assertEqual(s, 200)
        self.assertEqual(d["project_root"], str(Path(root).resolve()))
        self.assertTrue(d["sha_ok"])
        self.assertIn("annotations", d["state"])
        # GET /api/state 全量
        s, d = self._req("GET", "/api/state")
        self.assertEqual(s, 200)
        self.assertEqual(len(d["state"]["annotations"]), 5)
        # 批量写回：候选 → 选用
        fid = d["state"]["footage"][0]["id"]
        s, d = self._req("POST", "/api/footage",
                         {"updates": [{"footage_id": fid, "state": "selected"}]})
        self.assertEqual(s, 200)
        self.assertEqual(d["updated"], 1)
        self.assertEqual(read_state(root)["footage"][0]["state"], "selected")
        # 非法更新 → 400
        s, d = self._req("POST", "/api/footage",
                         {"updates": [{"footage_id": fid, "state": "done"}]})
        self.assertEqual(s, 400)
        self.assertIn("state", d["error"])

    def test_缺拍清单(self):
        root = make_project(self._tmp.name, files=["拍摄素材/R01_a.mp4"])
        self.assertEqual(recycle.run(str(root)), 0)   # 只有 R01 有素材
        s, d = self._req("POST", "/api/project", {"project": str(root)})
        self.assertEqual(s, 200)
        s, d = self._req("GET", "/api/missing")
        self.assertEqual(s, 200)
        # 拍摄口径：只算人工拍摄批注——AI 批注（R02/R05）的缺口在补制任务里表达，
        # 混进来会让补拍清单永远非空
        self.assertEqual(d["missing_count"], 2)
        self.assertEqual([m["id"] for m in d["missing"]], ["R03", "R04"])
        r03 = d["missing"][0]
        self.assertEqual(r03["kind"], "manual")
        self.assertEqual(r03["shoot_hint"], "手拧开关特写")

    def test_match_manual白名单(self):
        """面板挂接=人拍板 → match 记 manual；机器来源（filename/ai:*）不许走 API 伪造。"""
        root = make_project(self._tmp.name, files=["拍摄素材/R01_a.mp4"])
        self.assertEqual(recycle.run(str(root)), 0)
        s, d = self._req("POST", "/api/project", {"project": str(root)})
        self.assertEqual(s, 200)
        fid = d["state"]["footage"][0]["id"]
        s, d = self._req("POST", "/api/footage",
                         {"updates": [{"footage_id": fid, "match": "manual"}]})
        self.assertEqual(s, 200)
        self.assertEqual(read_state(root)["footage"][0]["match"], "manual")
        s, d = self._req("POST", "/api/footage",
                         {"updates": [{"footage_id": fid, "match": "ai:0.9"}]})
        self.assertEqual(s, 400)
        self.assertIn("manual", d["error"])

    def test_sha拦截_定稿被外部改动(self):
        root = make_project(self._tmp.name, files=["拍摄素材/R01_a.mp4"])
        self.assertEqual(recycle.run(str(root)), 0)
        s, d = self._req("POST", "/api/project", {"project": str(root)})
        self.assertEqual(s, 200)
        fid = d["state"]["footage"][0]["id"]
        (root / "定稿.md").write_bytes((MD_TEXT + "外部改动\n").encode("utf-8"))
        s, d = self._req("POST", "/api/footage",
                         {"updates": [{"footage_id": fid, "state": "selected"}]})
        self.assertEqual(s, 409)                       # 拦截
        self.assertEqual(read_state(root)["footage"][0]["state"],
                         "candidate")                  # 一个字没写
        # 修好指纹（旁车重算）后放行——模拟「定稿重锁」流程
        st = read_state(root)
        st["source_sha256"] = hashlib.sha256(
            (MD_TEXT + "外部改动\n").encode("utf-8")).hexdigest()
        (root / "定稿.md.shoot.json").write_text(
            json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
        s, d = self._req("POST", "/api/footage",
                         {"updates": [{"footage_id": fid, "state": "selected"}]})
        self.assertEqual(s, 200)

    def test_项目不存在_400(self):
        s, d = self._req("POST", "/api/project",
                         {"project": os.path.join(self._tmp.name, "没有")})
        self.assertEqual(s, 400)


if __name__ == "__main__":
    unittest.main()
