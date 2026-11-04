"""S2-D 单测：剪辑批注 upsert、补制任务生成（幂等）、cut 输入编译（05_剪辑交接）。

覆盖：generate_tasks 幂等（重跑零新增）/ ai_type=other→reshoot+note 映射 /
缺拍 manual→reshoot / editnote upsert 覆盖语义（同 footage_id 收敛一条）/
compile 产物目录结构 + 文件命名 {ann_id}_{footage_id}_{原名} + 剪辑说明.md
内容断言（逐段/缺口段/任务引用/给 cut 的输入说明）/ 同 ann 多段全放 /
多批注共用素材只复制一份 / 无 selected 全走缺口 / dry-run 零写盘 /
定稿 sha 拦截 / CLI 自动定位定稿 / HTTP API（editnote/tasks/handoff）。

不测真实视频（夹具是小字节文件，复制语义与字节数无关）。
"""
import hashlib
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

# ——先把标准库 select 钉进 sys.modules（必须在 import shoot_server 之前）——
# 地雷说明同 test_shoot_match.py：cut/scripts/select.py 与标准库 select 同名，
# 同进程先跑的 test_jy_draft 会把 cut/scripts 插进 sys.path，随后 import
# http.server→socket→selectors→select 拿到假 select，HTTP 测试全体超时。
import pathlib  # noqa: E402

_shadow_dirs = [p for p in sys.path
                if p and os.path.isfile(os.path.join(p, "select.py"))]
if _shadow_dirs:
    sys.path[:] = [p for p in sys.path if p not in _shadow_dirs]
import select  # noqa: E402 —— 真·标准库
assert hasattr(select, "select"), "标准库 select 被 cut/scripts/select.py 遮蔽"
sys.path.extend(_shadow_dirs)  # 原样放回，别影响其他测试的导入环境

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "media" / "shoot" / "scripts"))

import 剪辑交接 as handoff  # noqa: E402
import shoot_server  # noqa: E402

MD_TEXT = "# 定稿口播\n\n第一段口播。\n\n第二段口播。\n"


def _mk_ann(aid, kind="manual", quote="", hint="", ai_type="", ai_brief=""):
    """按冻结 schema v1 造一条呈现批注。"""
    return {"id": aid, "block_hash": "ab12cd34ef"[:10], "quote": quote,
            "occurrence": 1, "kind": kind, "shoot_hint": hint,
            "ai_type": ai_type, "ai_brief": ai_brief, "status": "open",
            "created": "2026-11-05T10:00:00"}


def _mk_footage(fid, file, ann_ids, state="candidate"):
    return {"id": fid, "file": file, "ann_ids": ann_ids, "state": state,
            "match": "filename", "note": ""}


def make_project(tmp, anns=None, footage=None, edit_notes=None, tasks=None,
                 files=()):
    """造假项目：定稿 md（字节写防换行翻译动指纹）+ 指纹配套旁车 + 素材文件。
    返回项目根 Path。"""
    root = Path(tmp)
    (root / "定稿.md").write_bytes(MD_TEXT.encode("utf-8"))
    sha = hashlib.sha256(MD_TEXT.encode("utf-8")).hexdigest()
    state = {
        "version": 1, "source_sha256": sha, "locked": True,
        "annotations": anns if anns is not None else [],
        "plan": {"checklist_md": "", "ai_tasks_md": ""},
        "footage": footage if footage is not None else [],
        "editNotes": edit_notes if edit_notes is not None else [],
        "tasks": tasks if tasks is not None else [],
    }
    (root / "定稿.md.shoot.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    for rel in files:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"fake-bytes:" + rel.encode("utf-8"))
    return root


def read_state(root):
    return json.loads((root / "定稿.md.shoot.json").read_text(encoding="utf-8"))


def write_state(root, state):
    (root / "定稿.md.shoot.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


class TestGenerateTasks(unittest.TestCase):
    """补制任务生成：显式、幂等、类型路由。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def test_ai批注按ai_type开任务(self):
        root = make_project(self._tmp.name, anns=[
            _mk_ann("R01", "ai", ai_type="card", ai_brief="数据卡"),
            _mk_ann("R02", "ai", ai_type="motion", ai_brief="转场"),
            _mk_ann("R03", "ai", ai_type="aigen", ai_brief="生图"),
        ])
        added, tasks = handoff.generate_tasks(read_state(root))
        self.assertEqual([(t["id"], t["type"], t["ref"]) for t in added],
                         [("t01", "card", "R01"), ("t02", "motion", "R02"),
                          ("t03", "aigen", "R03")])
        self.assertTrue(all(t["state"] == "open" and t["output"] == ""
                            for t in added))
        self.assertEqual(added, tasks)  # 全是新增

    def test_other映射为reshoot并说明需人工定工具(self):
        root = make_project(self._tmp.name, anns=[
            _mk_ann("R01", "ai", ai_type="other", ai_brief="特殊效果")])
        added, _ = handoff.generate_tasks(read_state(root))
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]["type"], "reshoot")
        self.assertEqual(added[0]["note"], "other 需人工定工具")

    def test_缺拍manual开补拍任务_有关联素材不开(self):
        root = make_project(
            self._tmp.name,
            anns=[_mk_ann("R01", quote="有素材"), _mk_ann("R02", quote="缺拍")],
            footage=[_mk_footage("f01", "a/R01_x.mp4", ["R01"])])
        added, _ = handoff.generate_tasks(read_state(root))
        # R01 有素材关联（哪怕还是候选）→ 不开任务；R02 零关联 → 补拍
        self.assertEqual([(t["type"], t["ref"]) for t in added],
                         [("reshoot", "R02")])
        self.assertNotIn("note", added[0])

    def test_幂等_跑两遍同样结果(self):
        root = make_project(self._tmp.name, anns=[
            _mk_ann("R01", "ai", ai_type="card"),
            _mk_ann("R02", quote="缺拍"),
            _mk_ann("R03", "ai", ai_type="other")])
        state = read_state(root)
        added1, tasks1 = handoff.generate_tasks(state)
        snapshot = json.loads(json.dumps(tasks1))  # 深拷贝对照
        added2, tasks2 = handoff.generate_tasks(state)
        self.assertEqual(len(added1), 3)
        self.assertEqual(added2, [])          # 第二遍零新增
        self.assertEqual(tasks2, snapshot)    # 任务清单原样（含 note 字段）

    def test_已有ref不重复生成且不动已有任务(self):
        tasks = [{"id": "t01", "type": "card", "ref": "R01",
                  "state": "doing", "output": "05_AI产出/r01.png"}]
        root = make_project(self._tmp.name,
                            anns=[_mk_ann("R01", "ai", ai_type="card")],
                            tasks=tasks)
        added, all_tasks = handoff.generate_tasks(read_state(root))
        self.assertEqual(added, [])
        self.assertEqual(all_tasks, tasks)    # 状态/产物一个字不动

    def test_手动批注已有素材但未选用不开任务(self):
        """「无任何 footage 关联」才开补拍——有候选素材挂着不算缺拍。"""
        root = make_project(
            self._tmp.name, anns=[_mk_ann("R01", quote="有候选")],
            footage=[_mk_footage("f01", "a/R01_x.mp4", ["R01"])])
        added, _ = handoff.generate_tasks(read_state(root))
        self.assertEqual(added, [])


class TestUpsertEditnote(unittest.TestCase):
    """剪辑批注 upsert（纯函数）：同 footage_id 覆盖、收敛、校验。"""

    def setUp(self):
        self.state = {"version": 1, "source_sha256": "x" * 64,
                      "annotations": [],
                      "footage": [_mk_footage("f01", "a.mp4", ["R01"]),
                                  _mk_footage("f02", "b.mp4", ["R02"])],
                      "editNotes": [], "tasks": []}

    def test_新增再覆盖_不涨条目(self):
        e1 = shoot_server.upsert_editnote(self.state, "f01", "截 0:03-0:07")
        self.assertEqual(self.state["editNotes"],
                         [{"id": "e01", "footage_id": "f01",
                           "note": "截 0:03-0:07"}])
        e2 = shoot_server.upsert_editnote(self.state, "f01", "改成 0:05-0:09")
        self.assertIs(e2, e1)                     # 同条目就地覆盖
        self.assertEqual(len(self.state["editNotes"]), 1)
        self.assertEqual(self.state["editNotes"][0]["note"], "改成 0:05-0:09")

    def test_多素材各一条_id顺延不缩号(self):
        shoot_server.upsert_editnote(self.state, "f02", "乙")
        shoot_server.upsert_editnote(self.state, "f01", "甲")
        self.assertEqual([n["id"] for n in self.state["editNotes"]],
                         ["e01", "e02"])          # 先到先编号

    def test_历史重复条目收敛为一条(self):
        self.state["editNotes"] = [
            {"id": "e01", "footage_id": "f01", "note": "旧一"},
            {"id": "e02", "footage_id": "f01", "note": "旧二"}]
        shoot_server.upsert_editnote(self.state, "f01", "新批注")
        self.assertEqual(self.state["editNotes"],
                         [{"id": "e01", "footage_id": "f01",
                           "note": "新批注"}])

    def test_非法输入一律拒(self):
        for fid, note in [("f99", "x"), ("", "x"), (None, "x"),
                          ("f01", 123), ("f01", None)]:
            with self.assertRaises(ValueError, msg=(fid, note)):
                shoot_server.upsert_editnote(self.state, fid, note)


class TestCompileHandoff(unittest.TestCase):
    """cut 输入编译：目录结构、命名、剪辑说明.md 内容、幂等副作用为零。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    @staticmethod
    def _full_project(tmp):
        """标准夹具：R01 两段选用（其一有剪辑批注）；R02 选用无批注；
        R03 只有候选；R04（AI motion）零素材。任务先 generate 进旁车。"""
        anns = [
            _mk_ann("R01", quote="开机仰角", hint="三脚架仰拍"),
            _mk_ann("R02", "ai", ai_type="card", ai_brief="数据卡"),
            _mk_ann("R03", quote="候选不算选用"),
            _mk_ann("R04", "ai", ai_type="motion", ai_brief="转场动效"),
        ]
        footage = [
            _mk_footage("f01", "03_实拍/R01_a.mp4", ["R01"], state="selected"),
            _mk_footage("f02", "03_实拍/R01_b.mp4", ["R01"], state="selected"),
            _mk_footage("f03", "03_实拍/R02_c.mp4", ["R02"], state="selected"),
            _mk_footage("f04", "03_实拍/R03_d.mp4", ["R03"]),
        ]
        edit_notes = [{"id": "e01", "footage_id": "f01",
                       "note": "截 0:03-0:07，接 R02 卡片后"}]
        root = make_project(tmp, anns=anns, footage=footage,
                            edit_notes=edit_notes,
                            files=["03_实拍/R01_a.mp4", "03_实拍/R01_b.mp4",
                                   "03_实拍/R02_c.mp4", "03_实拍/R03_d.mp4"])
        state = read_state(root)
        handoff.generate_tasks(state)
        write_state(root, state)
        return root

    def test_目录结构与文件命名_复制非硬链接(self):
        root = self._full_project(self._tmp.name)
        r = handoff.compile_handoff(root, root / "定稿.md")
        base = root / "05_剪辑交接"
        self.assertTrue((base / "素材").is_dir())
        self.assertTrue((base / "剪辑说明.md").is_file())
        self.assertEqual(sorted(os.listdir(base / "素材")),
                         ["R01_f01_R01_a.mp4", "R01_f02_R01_b.mp4",
                          "R02_f03_R02_c.mp4"])
        # 复制不是硬链接：内容相等、不同 inode、素材本体原位未动
        src = root / "03_实拍" / "R01_a.mp4"
        dst = base / "素材" / "R01_f01_R01_a.mp4"
        self.assertEqual(src.read_bytes(), dst.read_bytes())
        self.assertFalse(os.path.samefile(src, dst))
        self.assertTrue(src.is_file())
        self.assertEqual(r["dir"], str(base))

    def test_说明md_头部与逐段清单(self):
        root = self._full_project(self._tmp.name)
        md = handoff.compile_handoff(root, root / "定稿.md")["md"]
        self.assertTrue(md.startswith("# 剪辑说明"))
        self.assertIn("定稿：定稿.md", md)
        self.assertIn("生成时间：", md)
        self.assertIn("## 逐段清单", md)
        self.assertIn("### R01 🎬 「开机仰角」", md)     # quote 优先
        self.assertIn("### R02 🤖 AI·card：数据卡", md)  # 无 quote 退整块提示
        self.assertIn("- 素材 `R01_f01_R01_a.mp4`（源：03_实拍/R01_a.mp4）", md)
        self.assertIn("剪辑批注：截 0:03-0:07，接 R02 卡片后", md)  # note 原文
        self.assertIn("剪辑批注：（未写", md)            # f02/f03 没写批注
        # 同 ann 多段全放，且按 footage 顺序
        self.assertLess(md.index("R01_f01_R01_a.mp4"),
                        md.index("R01_f02_R01_b.mp4"))
        # 批注顺序：R01 段在 R02 段前
        self.assertLess(md.index("### R01"), md.index("### R02"))
        # 逐段清单不收缺口批注（R03 有候选但没选用；R04 零素材）
        self.assertNotIn("### R03", md)
        self.assertNotIn("### R04", md)

    def test_说明md_任务引用type_state_output(self):
        root = self._full_project(self._tmp.name)
        # 给 R02 的任务回填产物 + 置 done，验证 md 引用跟着走
        state = read_state(root)
        state["tasks"][0]["state"] = "done"
        state["tasks"][0]["output"] = "05_AI产出/r02_card.png"
        write_state(root, state)
        md = handoff.compile_handoff(root, root / "定稿.md")["md"]
        self.assertIn("补制任务 t01 · card · done · 产物：05_AI产出/r02_card.png",
                      md)
        self.assertIn("补制任务 t02 · motion · open · 产物：（产物未回填）", md)

    def test_说明md_缺口段(self):
        root = self._full_project(self._tmp.name)
        r = handoff.compile_handoff(root, root / "定稿.md")
        md = r["md"]
        self.assertEqual(r["missing"], ["R03", "R04"])  # 按批注顺序
        self.assertEqual(r["missing_count"], 2)
        gap = md.split("## 缺口", 1)[1].split("## 给 cut 的输入说明", 1)[0]
        self.assertIn("R03 🎬 「候选不算选用」", gap)
        self.assertIn("R04 🤖 AI·motion：转场动效", gap)
        self.assertIn("补制任务 t02 · motion · open", gap)  # 缺口也带任务引用

    def test_说明md_给cut的输入说明(self):
        root = self._full_project(self._tmp.name)
        md = handoff.compile_handoff(root, root / "定稿.md")["md"]
        tail = md.split("## 给 cut 的输入说明", 1)[1]
        self.assertIn(str((root / "05_剪辑交接" / "素材").resolve()), tail)
        self.assertIn("本清单用法", tail)
        self.assertIn("不回读定稿 md 与旁车", tail)

    def test_多批注共用素材只复制一份_两段都列(self):
        anns = [_mk_ann("R01", quote="甲"), _mk_ann("R03", quote="乙")]
        footage = [_mk_footage("f01", "a/R01R03双命中.mp4", ["R01", "R03"],
                               state="selected")]
        root = make_project(self._tmp.name, anns=anns, footage=footage,
                            files=["a/R01R03双命中.mp4"])
        r = handoff.compile_handoff(root, root / "定稿.md")
        # owner = 批注顺序最前者 → 命名用 R01；只复制一份
        self.assertEqual([c["copy_name"] for c in r["copied"]],
                         ["R01_f01_R01R03双命中.mp4"])
        md = r["md"]
        r01 = md.split("### R01", 1)[1].split("### R03", 1)[0]
        r03 = md.split("### R03", 1)[1].split("## 缺口", 1)[0]
        self.assertIn("R01_f01_R01R03双命中.mp4", r01)
        self.assertIn("R01_f01_R01R03双命中.mp4", r03)   # 两段清单都引用

    def test_无selected全走缺口_素材目录空(self):
        root = make_project(
            self._tmp.name, anns=[_mk_ann("R01", quote="只有候选")],
            footage=[_mk_footage("f01", "a/R01_x.mp4", ["R01"])],
            files=["a/R01_x.mp4"])
        r = handoff.compile_handoff(root, root / "定稿.md")
        self.assertEqual(r["missing"], ["R01"])
        self.assertEqual(r["copied"], [])
        self.assertEqual(os.listdir(root / "05_剪辑交接" / "素材"), [])
        md = r["md"]
        self.assertIn("缺口 1", md)
        self.assertIn("R01 🎬 「只有候选」", md.split("## 缺口", 1)[1])
        self.assertNotIn("- 素材 `", md)               # 一段素材都没进逐段

    def test_选用但未挂批注的素材_不复制_尾部提醒(self):
        root = make_project(
            self._tmp.name, anns=[_mk_ann("R01", quote="正常")],
            footage=[_mk_footage("f01", "a/R01_x.mp4", ["R01"],
                                 state="selected"),
                     _mk_footage("f02", "a/未挂.mp4", [], state="selected")],
            files=["a/R01_x.mp4", "a/未挂.mp4"])
        r = handoff.compile_handoff(root, root / "定稿.md")
        self.assertEqual(r["loose"], ["f02"])
        self.assertEqual([c["copy_name"] for c in r["copied"]],
                         ["R01_f01_R01_x.mp4"])          # 未挂批注的不复制
        self.assertIn("1 段选用素材未挂任何呈现批注", r["md"])

    def test_源文件缺失_标记不复制_其余照常(self):
        root = self._full_project(self._tmp.name)
        (root / "03_实拍" / "R01_a.mp4").unlink()  # 拍完又清理掉了一段
        r = handoff.compile_handoff(root, root / "定稿.md")
        by_name = {c["copy_name"]: c for c in r["copied"]}
        self.assertFalse(by_name["R01_f01_R01_a.mp4"]["exists"])
        self.assertTrue(by_name["R01_f02_R01_b.mp4"]["exists"])
        self.assertIn("源文件缺失，未复制", r["md"])

    def test_dry_run零写盘(self):
        root = self._full_project(self._tmp.name)
        side_before = (root / "定稿.md.shoot.json").read_bytes()
        md_before = (root / "定稿.md").read_bytes()
        r = handoff.compile_handoff(root, root / "定稿.md", dry_run=True)
        self.assertTrue(r["dry_run"])
        self.assertFalse((root / "05_剪辑交接").exists())   # 目录都没建
        self.assertEqual((root / "定稿.md.shoot.json").read_bytes(),
                         side_before)
        self.assertEqual((root / "定稿.md").read_bytes(), md_before)
        self.assertEqual(len(r["copied"]), 3)               # 内容照常返回
        self.assertIn("## 逐段清单", r["md"])

    def test_指纹不符拒编译(self):
        root = self._full_project(self._tmp.name)
        (root / "定稿.md").write_bytes((MD_TEXT + "外部改动\n").encode("utf-8"))
        with self.assertRaises(ValueError):
            handoff.compile_handoff(root, root / "定稿.md")
        self.assertFalse((root / "05_剪辑交接").exists())   # 一个字没写

    def test_旁车version错拒编译(self):
        root = make_project(self._tmp.name)
        state = read_state(root)
        state["version"] = 2
        write_state(root, state)
        with self.assertRaises(ValueError):
            handoff.compile_handoff(root, root / "定稿.md")


class TestCli(unittest.TestCase):
    """CLI 入口：自动定位定稿、退出码。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def test_run_自动定位定稿并产出(self):
        root = TestCompileHandoff._full_project(self._tmp.name)
        self.assertEqual(handoff.run(str(root)), 0)
        self.assertTrue((root / "05_剪辑交接" / "剪辑说明.md").is_file())

    def test_run_缺旁车退1(self):
        root = Path(self._tmp.name)
        root.mkdir(exist_ok=True)
        self.assertEqual(handoff.run(str(root)), 1)

    def test_run_指纹不符退1且不落盘(self):
        root = TestCompileHandoff._full_project(self._tmp.name)
        (root / "定稿.md").write_bytes((MD_TEXT + "改动\n").encode("utf-8"))
        self.assertEqual(handoff.run(str(root)), 1)
        self.assertFalse((root / "05_剪辑交接").exists())


class TestServerCutApi(unittest.TestCase):
    """HTTP API（真服务随机端口）：剪辑批注 / 任务 / 编译三组新路由。"""

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

    def _open(self, root):
        s, d = self._req("POST", "/api/project", {"project": str(root)})
        self.assertEqual(s, 200)
        return d

    def _basic_project(self):
        return make_project(
            self._tmp.name,
            anns=[_mk_ann("R01", quote="开机仰角"),
                  _mk_ann("R02", "ai", ai_type="card", ai_brief="数据卡")],
            footage=[_mk_footage("f01", "a/R01_x.mp4", ["R01"],
                                 state="selected")],
            files=["a/R01_x.mp4"])

    def test_editnote_upsert与落盘(self):
        root = self._basic_project()
        self._open(root)
        s, d = self._req("POST", "/api/editnote",
                         {"footage_id": "f01", "note": "截 0:03-0:07"})
        self.assertEqual(s, 200)
        self.assertEqual(d["editnote"]["id"], "e01")
        s, d = self._req("POST", "/api/editnote",
                         {"footage_id": "f01", "note": "改成 0:05-0:09"})
        self.assertEqual(s, 200)
        notes = read_state(root)["editNotes"]
        self.assertEqual(len(notes), 1)               # upsert：同素材覆盖
        self.assertEqual(notes[0]["note"], "改成 0:05-0:09")
        # 未知素材 → 400；note 非字符串 → 400
        s, d = self._req("POST", "/api/editnote",
                         {"footage_id": "f99", "note": "x"})
        self.assertEqual(s, 400)
        s, d = self._req("POST", "/api/editnote", {"footage_id": "f01"})
        self.assertEqual(s, 400)

    def test_editnote_sha拦截(self):
        root = self._basic_project()
        self._open(root)
        (root / "定稿.md").write_bytes((MD_TEXT + "外部改动\n").encode("utf-8"))
        s, d = self._req("POST", "/api/editnote",
                         {"footage_id": "f01", "note": "x"})
        self.assertEqual(s, 409)
        self.assertEqual(read_state(root)["editNotes"], [])  # 一个字没写

    def test_任务生成幂等与查询(self):
        root = self._basic_project()
        self._open(root)
        s, d = self._req("POST", "/api/tasks/generate", {})
        self.assertEqual(s, 200)
        self.assertEqual(d["added_count"], 1)   # R01 有关联不开；R02 AI→card
        self.assertEqual([t["type"] for t in d["added"]], ["card"])
        self.assertEqual(d["added"][0]["ref"], "R02")
        self.assertEqual(read_state(root)["tasks"], d["tasks"])
        s, d = self._req("GET", "/api/tasks")
        self.assertEqual(s, 200)
        self.assertEqual(d["task_count"], 1)
        self.assertEqual(d["tasks"][0]["type"], "card")
        s, d = self._req("POST", "/api/tasks/generate", {})  # 重跑幂等
        self.assertEqual(s, 200)
        self.assertEqual(d["added_count"], 0)
        self.assertEqual(len(d["tasks"]), 1)

    def test_handoff_compile(self):
        root = self._basic_project()
        self._open(root)
        self._req("POST", "/api/editnote",
                  {"footage_id": "f01", "note": "截 0:03-0:07"})
        s, d = self._req("POST", "/api/handoff/compile", {})
        self.assertEqual(s, 200)
        self.assertTrue(d["ok"])
        self.assertTrue((root / "05_剪辑交接" / "剪辑说明.md").is_file())
        self.assertEqual(os.listdir(root / "05_剪辑交接" / "素材"),
                         ["R01_f01_R01_x.mp4"])
        self.assertEqual(d["copied"], ["R01_f01_R01_x.mp4"])
        self.assertEqual(d["missing"], ["R02"])   # R01 有选用素材；R02 零素材
        self.assertEqual(d["missing_count"], 1)
        self.assertIn("## 逐段清单", d["md"])
        self.assertIn("截 0:03-0:07", d["md"])
        # sha 拦截：md 被外部改动后编译同样被拒
        (root / "定稿.md").write_bytes((MD_TEXT + "外部改动\n").encode("utf-8"))
        s, d = self._req("POST", "/api/handoff/compile", {})
        self.assertEqual(s, 409)

    def test_未设项目新路由全400(self):
        for method, path, body in [
                ("POST", "/api/editnote", {"footage_id": "f01", "note": "x"}),
                ("POST", "/api/tasks/generate", {}),
                ("POST", "/api/handoff/compile", {}),
                ("GET", "/api/tasks", None)]:
            s, d = self._req(method, path, body)
            self.assertEqual(s, 400, path)
            self.assertIn("未设置项目", d["error"])


if __name__ == "__main__":
    unittest.main()
