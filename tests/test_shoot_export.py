"""shoot_export 单测：拍摄计划清单导出（S2-B）——清单编译/任务清单/落盘回填/幂等/拦截。

覆盖：建议文件名 slug 净化（非法字符/空 hint 回落/长文截断）、人工表格行数与
对应内容三级来源（quote/块原文首 40 字/hint 回落）、AI 任务节内容、export_all
落盘 + plan 字段回填、重复导出幂等、md 指纹不符拒写（一个字节都不落）、
locked 定稿锁下可导出（锁稿不锁清单）、CLI、HTTP /api/shoot_export 路由。

红线自查：导出绝不改 md 本体（字节级断言）；清单是独立新 md 文件，永不进定稿。
"""
import os
import sys

# ——先把标准库 select 钉进 sys.modules（必须在 import urllib / draft_server 之前）——
# 地雷：cut/scripts/select.py（素材初选 CLI）与标准库 select 同名。同进程里先跑的
# test_jy_draft / test_silence_trim 会把 cut/scripts 插到 sys.path 前列，本文件随后
# import urllib→socket→import select 时拿到的是那个假 select，导致 ThreadingHTTPServer
# 线程 AttributeError、HTTP 测试全超时。解法同 test_shoot_match：摘掉含 select.py 的
# 路径目录，import 真 select，再原样放回。
import pathlib  # noqa: E402

_shadow_dirs = [p for p in sys.path
                if p and os.path.isfile(os.path.join(p, "select.py"))]
if _shadow_dirs:
    sys.path[:] = [p for p in sys.path if p not in _shadow_dirs]
import select  # noqa: E402,F401 —— 真·标准库
assert hasattr(select, "select"), "标准库 select 被 cut/scripts/select.py 遮蔽"
sys.path.extend(_shadow_dirs)  # 原样放回，别影响其他测试的导入环境

import hashlib  # noqa: E402
import json  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import unittest  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "media" / "draft" / "scripts"))

from draft_blocks import parse_blocks  # noqa: E402
import shoot_export  # noqa: E402
import draft_server  # noqa: E402
from shoot_io import (  # noqa: E402
    ShootShaMismatch, load_shoot, save_shoot, shoot_path, validate_shoot)

SCRIPT = ROOT / "skill" / "media" / "draft" / "scripts" / "shoot_export.py"

# 定稿夹具：短段（整块引用不截断）+ 长段（>40 字，整块引用截断补省略号）
MD_TEXT = (
    "# 定稿大纲\n"
    "\n"
    "第一块口播，抛出问题再亮出答案，节奏要快。\n"
    "\n"
    "- 要点甲\n"
    "- 要点乙\n"
    "\n"
    "这是一段特别长的口播文本，专门用来验证整块批注的对应内容会在第四十个字处被截断并补上省略号。\n"
)


def _hash_of(fragment):
    """夹具里含 fragment 的块的真锚点（与前端 blockHash 算法同源，md5 前 10 位）"""
    for b in parse_blocks(MD_TEXT):
        if fragment in b["raw"]:
            return b["hash"]
    raise AssertionError(f"夹具里找不到含 {fragment!r} 的块")


def _ann(aid, kind="manual", hint="", quote="", bh="", ai_type="", ai_brief=""):
    """按冻结 schema v1 造一条呈现批注。"""
    return {"id": aid, "block_hash": bh, "quote": quote, "occurrence": 1,
            "kind": kind, "shoot_hint": hint, "ai_type": ai_type,
            "ai_brief": ai_brief, "status": "open",
            "created": "2026-11-05T10:00:00"}


def _make_shoot(sha):
    """一套覆盖各分支的合法旁车：4 人工（长 hint/非法字符/quote 圈句/多行 hint 失锚）
    + 2 AI 制作（card 单行指令 / motion 多行指令）。"""
    return {
        "version": 1, "source_sha256": sha, "locked": False,
        "annotations": [
            _ann("R01", hint="办公室开场实拍怼脸大特写镜头",       # 14 字 → 截 12
                 bh=_hash_of("特别长")),
            _ann("R02", hint='厨房/特写: A*B?"<x>|y',              # 非法字符净化
                 bh=_hash_of("第一块口播")),
            _ann("R03", hint="", quote="亮出答案",                  # 空 hint 回落 quote
                 bh=_hash_of("要点乙")),
            _ann("R04", hint="棚拍绿幕\n补拍第二行",                # 多行 hint + 失锚块
                 bh="deadbeef00"),
            _ann("R05", kind="ai", ai_type="card",
                 ai_brief="做一张「卖点」字幕卡，白底黑字。",
                 bh=_hash_of("第一块口播")),
            _ann("R06", kind="ai", ai_type="motion",
                 ai_brief="开场动效，标题从左滑入。\n配 whoosh 音效。",
                 bh=_hash_of("特别长")),
        ],
        "plan": {"checklist_md": "", "ai_tasks_md": ""},
        "footage": [], "editNotes": [], "tasks": [],
    }


def _blocks():
    return parse_blocks(MD_TEXT)


# ---------------------------------------------------------------- 纯函数

class TestSuggestFilename(unittest.TestCase):
    """建议文件名：{id}_{slug}.mp4 —— slug 净化/回落/截断的每条分支"""

    def test_非法字符与换行净化(self):
        a = _ann("R01", hint='a\\/b:c*d?e"f<g>h|i')
        self.assertEqual(shoot_export.suggest_filename(a), "R01_abcdefghi.mp4")
        a2 = _ann("R02", hint="开场\n镜头")
        self.assertEqual(shoot_export.suggest_filename(a2), "R02_开场镜头.mp4")

    def test_空hint回落quote(self):
        a = _ann("R03", hint="", quote="亮出答案")
        self.assertEqual(shoot_export.suggest_filename(a), "R03_亮出答案.mp4")

    def test_全空兜底镜头(self):
        self.assertEqual(shoot_export.suggest_filename(_ann("R99")),
                         "R99_镜头.mp4")

    def test_长文截断前12字(self):
        a = _ann("R01", hint="办公室开场实拍怼脸大特写镜头")  # 14 字
        self.assertEqual(shoot_export.suggest_filename(a),
                         "R01_办公室开场实拍怼脸大特写.mp4")

    def test_短hint不回落quote(self):
        # 「不足取 quote」的语义：hint 有内容（哪怕不足 12 字）就用 hint
        a = _ann("R02", hint="厨房", quote="亮出答案")
        self.assertEqual(shoot_export.suggest_filename(a), "R02_厨房.mp4")

    def test_净化先于截断(self):
        # 非法字符恰好在第 12 字附近：先净化再截断，截完仍干净
        a = _ann("R01", hint="aaaaaaaaaa/aaaa")   # 净化后 14 个 a
        self.assertEqual(shoot_export.suggest_filename(a),
                         "R01_" + "a" * 12 + ".mp4")


class TestRefText(unittest.TestCase):
    """对应内容三级来源：quote 圈句 → 块原文首 40 字 → 失锚回落 quote/hint"""

    def test_quote圈句(self):
        a = _ann("R03", quote="亮出答案")
        self.assertEqual(shoot_export.ref_text(a, _blocks()), "「亮出答案」")

    def test_整块引用短块全文(self):
        a = _ann("R02", bh=_hash_of("第一块口播"))
        self.assertEqual(shoot_export.ref_text(a, _blocks()),
                         "第一块口播，抛出问题再亮出答案，节奏要快。")

    def test_整块引用长块截断40字(self):
        long_raw = next(b["raw"] for b in _blocks() if "特别长" in b["raw"])
        self.assertGreater(len(long_raw), 40)
        a = _ann("R01", bh=_hash_of("特别长"))
        self.assertEqual(shoot_export.ref_text(a, _blocks()),
                         long_raw[:40] + "…")

    def test_失锚回落hint本身(self):
        a = _ann("R04", hint="棚拍绿幕\n补拍第二行", bh="deadbeef00")
        self.assertEqual(shoot_export.ref_text(a, _blocks()),
                         "棚拍绿幕 补拍第二行")   # 换行折空格

    def test_全空给占位(self):
        self.assertEqual(shoot_export.ref_text(_ann("R99"), _blocks()),
                         "（无对应内容）")


class TestBuildChecklist(unittest.TestCase):
    """拍摄计划清单编译：头部/表格/AI 节/空旁车"""

    def setUp(self):
        self.shoot = _make_shoot("0" * 64)
        self.md = shoot_export.build_checklist(self.shoot, _blocks(),
                                               md_name="大纲_v3.md")

    def test_头部三件套(self):
        self.assertIn("# 📋 拍摄计划清单", self.md)
        self.assertIn("> 定稿来源：大纲_v3.md", self.md)
        self.assertIn("> 统计：实拍 4 · AI制作 2", self.md)

    def test_人工表格行数与表头(self):
        self.assertIn("| 建议文件名 | 对应内容 | 拍摄提示 |", self.md)
        rows = [ln for ln in self.md.split("\n") if ln.startswith("| `R")]
        self.assertEqual(len(rows), 4)   # 4 条 manual → 4 行

    def test_建议文件名各分支落表(self):
        self.assertIn("`R01_办公室开场实拍怼脸大特写.mp4`", self.md)
        self.assertIn("`R02_厨房特写 ABxy.mp4`", self.md)
        self.assertIn("`R03_亮出答案.mp4`", self.md)
        self.assertIn("`R04_棚拍绿幕补拍第二行.mp4`", self.md)

    def test_对应内容三级来源落表(self):
        long_raw = next(b["raw"] for b in _blocks() if "特别长" in b["raw"])
        self.assertIn(long_raw[:40] + "…", self.md)          # 整块长文截断
        self.assertIn("「亮出答案」", self.md)                # 圈句
        self.assertIn("棚拍绿幕 补拍第二行", self.md)          # 失锚回落（换行折空格）

    def test_表格竖线转义不破表(self):
        # R02 原始 hint 含 |：原样进提示列但须转义，行仍是 3 列
        self.assertIn('厨房/特写: A*B?"<x>\\|y', self.md)

    def test_AI节内容(self):
        self.assertIn("### R05 · card", self.md)
        self.assertIn("### R06 · motion", self.md)
        self.assertIn("`R05_card.mp4`", self.md)
        self.assertIn("`R06_motion.mp4`", self.md)
        self.assertIn("做一张「卖点」字幕卡，白底黑字。", self.md)
        self.assertIn("> 配 whoosh 音效。", self.md)          # 多行指令逐行 blockquote

    def test_空旁车出占位不炸(self):
        md = shoot_export.build_checklist(
            {"annotations": []}, _blocks(), md_name="x.md")
        self.assertIn("> 统计：实拍 0 · AI制作 0", md)
        self.assertIn("（无人工拍摄项", md)
        self.assertIn("（无 AI 制作项）", md)


class TestBuildAiTasks(unittest.TestCase):
    """✨AI 制作任务清单编译：执行说明 + 逐条任务卡；人工拍摄绝不混入"""

    def setUp(self):
        self.shoot = _make_shoot("0" * 64)
        self.md = shoot_export.build_ai_tasks_md(self.shoot, _blocks(),
                                                 md_name="大纲_v3.md")

    def test_开头执行说明(self):
        self.assertIn("# ✨ AI 制作任务清单", self.md)
        self.assertIn("你是素材制作执行者", self.md)
        self.assertIn("产物建议路径", self.md)
        self.assertIn("回报", self.md)
        self.assertIn(shoot_export.AI_ROUTE_HINT, self.md)   # card/motion/aigen 路由

    def test_逐条任务卡(self):
        self.assertIn("## R05 · card", self.md)
        self.assertIn("## R06 · motion", self.md)
        self.assertIn("`R05_card.mp4`", self.md)
        self.assertIn("- 产物建议路径：`R06_motion.mp4`", self.md)

    def test_指令原文与引用(self):
        self.assertIn("> 开场动效，标题从左滑入。", self.md)
        self.assertIn("> 配 whoosh 音效。", self.md)
        self.assertIn("做一张「卖点」字幕卡，白底黑字。", self.md)
        # R05 锚在短段上 → 引用是块原文全文
        self.assertIn("第一块口播，抛出问题再亮出答案，节奏要快。", self.md)

    def test_人工拍摄不进任务清单(self):
        self.assertNotIn("R01", self.md)
        self.assertNotIn("R02", self.md)
        self.assertNotIn("拍摄提示", self.md)

    def test_空任务给占位(self):
        md = shoot_export.build_ai_tasks_md({"annotations": []}, _blocks())
        self.assertIn("> 任务数：0", md)
        self.assertIn("（无 AI 制作任务）", md)


# ---------------------------------------------------------------- export_all

class ExportTestBase(unittest.TestCase):
    """夹具：定稿 md + 指纹配套旁车（含 6 条批注），导出前先落旁车"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.md = os.path.join(self.tmp.name, "大纲_v3.md")
        with open(self.md, "wb") as f:  # 二进制写死，排除 Windows 换行翻译干扰
            f.write(MD_TEXT.encode("utf-8"))

    def md_sha(self):
        with open(self.md, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    def md_bytes(self):
        with open(self.md, "rb") as f:
            return f.read()

    def side(self):
        return shoot_path(self.md)

    def plant_sidecar(self, **over):
        data = _make_shoot(self.md_sha())
        data.update(over)
        save_shoot(self.md, data)
        return data

    def read_sidecar(self):
        return load_shoot(self.md)


class TestExportAll(ExportTestBase):
    """export_all：落盘路径/回填 plan/红线（md 不动）/幂等/指纹拦截/定稿锁"""

    def test_导出落盘与plan回填(self):
        self.plant_sidecar()
        cl_path, ai_path, cl_md, ai_md = shoot_export.export_all(self.md)
        self.assertEqual(os.path.basename(cl_path), "大纲_v3_拍摄清单.md")
        self.assertEqual(os.path.basename(ai_path), "大纲_v3_AI制作任务.md")
        self.assertEqual(os.path.dirname(os.path.abspath(cl_path)),
                         os.path.abspath(self.tmp.name))      # 定稿同目录
        self.assertTrue(os.path.isfile(cl_path))
        self.assertTrue(os.path.isfile(ai_path))
        with open(cl_path, "rb") as f:                        # 返回值 = 盘上内容
            self.assertEqual(f.read().decode("utf-8"), cl_md)
        with open(ai_path, "rb") as f:
            self.assertEqual(f.read().decode("utf-8"), ai_md)
        side = self.read_sidecar()
        # plan 语义：存导出文件相对定稿 md 所在目录的文件名（同目录=纯文件名）
        self.assertEqual(side["plan"]["checklist_md"], "大纲_v3_拍摄清单.md")
        self.assertEqual(side["plan"]["ai_tasks_md"], "大纲_v3_AI制作任务.md")
        self.assertEqual(validate_shoot(side), [])            # 回填后旁车仍合法

    def test_清单内容反映批注(self):
        self.plant_sidecar()
        _, _, cl_md, ai_md = shoot_export.export_all(self.md)
        self.assertIn("> 统计：实拍 4 · AI制作 2", cl_md)
        self.assertIn("## R06 · motion", ai_md)

    def test_md本体字节不变(self):
        self.plant_sidecar()
        before = self.md_bytes()
        shoot_export.export_all(self.md)
        self.assertEqual(self.md_bytes(), before)             # 红线：只增清单不动定稿

    def test_重复导出幂等(self):
        self.plant_sidecar()
        r1 = shoot_export.export_all(self.md)
        with open(r1[0], "rb") as f:
            cl1 = f.read()
        r2 = shoot_export.export_all(self.md)
        with open(r2[0], "rb") as f:
            cl2 = f.read()
        self.assertEqual(r1[2], r2[2])                        # 返回的 markdown 全等
        self.assertEqual(r1[3], r2[3])
        self.assertEqual(cl1, cl2)                            # 盘上文件字节全等
        side = self.read_sidecar()                            # 旁车仍能对上指纹
        self.assertEqual(side["source_sha256"], self.md_sha())
        self.assertEqual(validate_shoot(side), [])

    def test_sha不符拒写且不落文件(self):
        self.plant_sidecar()
        # md 被外部改动 → 旁车指纹过期
        with open(self.md, "wb") as f:
            f.write(MD_TEXT.replace("第一块", "第X块").encode("utf-8"))
        cl_path = os.path.join(self.tmp.name, "大纲_v3_拍摄清单.md")
        ai_path = os.path.join(self.tmp.name, "大纲_v3_AI制作任务.md")
        with self.assertRaises(ShootShaMismatch):
            shoot_export.export_all(self.md)
        self.assertFalse(os.path.exists(cl_path))             # 一个字节都不落
        self.assertFalse(os.path.exists(ai_path))
        side = self.read_sidecar()                            # plan 也没被污染
        self.assertEqual(side["plan"]["checklist_md"], "")
        self.assertEqual(side["plan"]["ai_tasks_md"], "")

    def test_locked下可导出(self):
        self.plant_sidecar(locked=True)                       # 锁稿不锁清单
        cl_path, ai_path, _, _ = shoot_export.export_all(self.md)
        self.assertTrue(os.path.isfile(cl_path))
        self.assertTrue(os.path.isfile(ai_path))
        self.assertEqual(self.read_sidecar()["plan"]["checklist_md"],
                         "大纲_v3_拍摄清单.md")

    def test_空旁车也可导出(self):
        # 定稿还没有任何呈现批注：出占位清单，plan 照常回填（幂等再导）
        cl_path, _, cl_md, _ = shoot_export.export_all(self.md)
        self.assertIn("（无人工拍摄项", cl_md)
        self.assertTrue(os.path.isfile(cl_path))
        self.assertEqual(self.read_sidecar()["plan"]["checklist_md"],
                         "大纲_v3_拍摄清单.md")

    def test_md不存在报人话(self):
        with self.assertRaises(FileNotFoundError):
            shoot_export.export_all(os.path.join(self.tmp.name, "没有.md"))


class TestCli(ExportTestBase):
    """CLI：python shoot_export.py <定稿md>"""

    def _run(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args],
                              capture_output=True)

    def test_cli导出成功(self):
        self.plant_sidecar()
        r = self._run(self.md)
        self.assertEqual(r.returncode, 0,
                         r.stderr.decode("utf-8", errors="replace"))
        out = r.stdout.decode("utf-8", errors="replace")
        self.assertIn("拍摄清单", out)
        self.assertIn("AI制作任务", out)
        self.assertTrue(os.path.isfile(
            os.path.join(self.tmp.name, "大纲_v3_拍摄清单.md")))
        self.assertTrue(os.path.isfile(
            os.path.join(self.tmp.name, "大纲_v3_AI制作任务.md")))

    def test_cli指纹不符退出码2(self):
        self.plant_sidecar()
        with open(self.md, "wb") as f:
            f.write(MD_TEXT.replace("要点甲", "要点改").encode("utf-8"))
        r = self._run(self.md)
        self.assertEqual(r.returncode, 2)
        self.assertIn("导出失败", r.stderr.decode("utf-8", errors="replace"))

    def test_cli无参给用法(self):
        r = self._run()
        self.assertEqual(r.returncode, 1)


# ---------------------------------------------------------------- HTTP 路由

class TestShootExportApi(ExportTestBase):
    """POST /api/shoot_export：起真服务（127.0.0.1 随机端口）走一遍"""

    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0),
                                      draft_server.DraftHandler)
        cls.port = cls.srv.server_address[1]
        cls.thread = threading.Thread(target=cls.srv.serve_forever,
                                      daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def _req(self, body):
        url = f"http://127.0.0.1:{self.port}/api/shoot_export"
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_导出200四件套(self):
        self.plant_sidecar()
        s, d = self._req({"path": self.md})
        self.assertEqual(s, 200)
        for k in ("checklist", "ai_tasks", "checklist_md_content",
                  "ai_tasks_md_content"):
            self.assertIn(k, d)
        self.assertTrue(os.path.isfile(d["checklist"]))
        self.assertTrue(os.path.isfile(d["ai_tasks"]))
        self.assertEqual(d["checklist_md_content"],
                         Path(d["checklist"]).read_text(encoding="utf-8"))
        self.assertEqual(self.read_sidecar()["plan"]["ai_tasks_md"],
                         "大纲_v3_AI制作任务.md")

    def test_文件不存在404(self):
        s, d = self._req({"path": os.path.join(self.tmp.name, "没有.md")})
        self.assertEqual(s, 404)
        self.assertIn("不存在", d["error"])

    def test_指纹不符409(self):
        self.plant_sidecar()
        with open(self.md, "wb") as f:  # md 被外部改动
            f.write(MD_TEXT.replace("要点乙", "要点换").encode("utf-8"))
        s, d = self._req({"path": self.md})
        self.assertEqual(s, 409)
        self.assertIn("外部修改", d["error"])

    def test_locked下200(self):
        self.plant_sidecar(locked=True)
        s, d = self._req({"path": self.md})
        self.assertEqual(s, 200)                              # 锁稿不锁清单
        self.assertTrue(os.path.isfile(d["checklist"]))


if __name__ == "__main__":
    unittest.main()
