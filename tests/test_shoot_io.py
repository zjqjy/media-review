"""shoot_io 单测：shoot.json 旁车（S2-A 地基）——骨架/校验/原子写/agent 回写白名单。

呈现批注 id 从 R01 起顺序编号且定稿后永不变；source_sha256 对不上 = md 被外部
动过，拒收（语义同 draft_server 409）；agent 回写只许碰 tasks[].state/output、
footage[].state/note——越权一律拒（S2-E 跨 agent 协议的校验地基）。
"""
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "skill" / "media" / "draft" / "scripts"))
from shoot_io import (  # noqa: E402
    ShootShaMismatch, ShootValidationError, check_agent_writeback, default_shoot,
    is_locked, load_shoot, next_ann_id, save_shoot, shoot_path, validate_shoot)

MD_TEXT = "# 定稿大纲\n\n先抛问题再亮答案。\n\n- 要点甲\n- 要点乙\n"


def _fake_hash(seed):
    """像块锚点的 10 位 hex（校验只看非空字符串，值本身不参与锚定）"""
    return hashlib.md5(seed.encode("utf-8")).hexdigest()[:10]


def _ann(aid="R01", kind="manual", quote="", **kw):
    a = {"id": aid, "block_hash": _fake_hash(aid + kind), "quote": quote,
         "occurrence": 1, "kind": kind,
         "shoot_hint": "办公室实测镜头" if kind == "manual" else "",
         "ai_type": "card" if kind == "ai" else "",
         "ai_brief": "做一张卖点字幕卡" if kind == "ai" else "",
         "status": "open", "created": "2026-11-05T10:00:00"}
    a.update(kw)
    return a


def _full_shoot(sha):
    """一套交叉引用齐全的合法数据：2 批注 + 1 素材 + 1 剪辑批注 + 1 任务"""
    return {
        "version": 1, "source_sha256": sha, "locked": False,
        "annotations": [_ann("R01"), _ann("R02", kind="ai", quote="先抛问题",
                                          occurrence=1)],
        "plan": {"checklist_md": "", "ai_tasks_md": ""},
        "footage": [{"id": "f01", "file": "03_实拍/办公室.mp4",
                     "ann_ids": ["R01"], "state": "candidate",
                     "match": "filename", "note": ""}],
        "editNotes": [{"id": "e01", "footage_id": "f01",
                       "note": "截 0:03-0:07，接 R02 卡片后"}],
        "tasks": [{"id": "t01", "type": "card", "ref": "R02",
                   "state": "open", "output": ""}],
    }


class ShootTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.md = os.path.join(self.tmp.name, "大纲_v3.md")
        with open(self.md, "wb") as f:  # 二进制写死字节，排除换行翻译干扰
            f.write(MD_TEXT.encode("utf-8"))

    def tearDown(self):
        self.tmp.cleanup()

    def side(self):
        return shoot_path(self.md)

    def read_side(self):
        with open(self.side(), "rb") as f:
            return json.loads(f.read().decode("utf-8"))

    def md_sha(self):
        with open(self.md, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()


class TestDefaultSkeleton(ShootTestBase):
    """默认骨架：旁车不存在 → 带当前 md 指纹的完整骨架"""

    def test_skeleton_fields(self):
        d = load_shoot(self.md)
        self.assertEqual(d["version"], 1)
        self.assertFalse(d["locked"])
        self.assertEqual(d["annotations"], [])
        self.assertEqual(d["plan"], {"checklist_md": "", "ai_tasks_md": ""})
        self.assertEqual(d["footage"], [])
        self.assertEqual(d["editNotes"], [])
        self.assertEqual(d["tasks"], [])
        self.assertEqual(validate_shoot(d), [])

    def test_skeleton_sha_is_current_md(self):
        d = load_shoot(self.md)
        self.assertEqual(d["source_sha256"], self.md_sha())
        self.assertEqual(default_shoot(self.md)["source_sha256"], self.md_sha())

    def test_sidecar_path_naming(self):
        self.assertTrue(self.side().endswith("大纲_v3.md.shoot.json"))

    def test_load_existing_roundtrip(self):
        data = _full_shoot(self.md_sha())
        save_shoot(self.md, data)
        back = load_shoot(self.md)
        self.assertEqual(back, data)

    def test_load_corrupt_json_raises(self):
        with open(self.side(), "wb") as f:
            f.write("{不是json".encode("utf-8"))
        with self.assertRaises(ValueError):
            load_shoot(self.md)

    def test_load_sparse_sidecar_fills_defaults(self):
        """手写最小旁车（跨 agent 场景）少节不炸，缺的节按空补齐"""
        with open(self.side(), "wb") as f:
            f.write(json.dumps({"version": 1, "source_sha256": self.md_sha()},
                               ensure_ascii=False).encode("utf-8"))
        d = load_shoot(self.md)
        self.assertEqual(d["annotations"], [])
        self.assertFalse(d["locked"])
        self.assertEqual(validate_shoot(d), [])


class TestValidate(ShootTestBase):
    """schema 合法/非法两路"""

    def test_ok_skeleton(self):
        self.assertEqual(validate_shoot(default_shoot(self.md)), [])

    def test_ok_manual_annotation(self):
        d = default_shoot(self.md)
        d["annotations"] = [_ann()]
        self.assertEqual(validate_shoot(d), [])

    def test_ok_full_graph(self):
        self.assertEqual(validate_shoot(_full_shoot(self.md_sha())), [])

    def test_ok_sparse_top_only(self):
        self.assertEqual(validate_shoot({"version": 1,
                                         "source_sha256": self.md_sha()}), [])

    # ---- 非法 ----

    def test_bad_missing_version(self):
        d = _full_shoot(self.md_sha())
        del d["version"]
        self.assertTrue(any("version" in e for e in validate_shoot(d)))

    def test_bad_version_value(self):
        d = _full_shoot(self.md_sha())
        d["version"] = 2
        self.assertTrue(any("version" in e for e in validate_shoot(d)))

    def test_bad_sha_format(self):
        for bad in ("", "abc", "A" * 64, "z" * 64):
            d = _full_shoot(bad)
            self.assertTrue(any("source_sha256" in e for e in validate_shoot(d)))

    def test_bad_ann_id_format(self):
        for bad in ("R1", "r01", "X01", "R", "Ann1"):
            d = default_shoot(self.md)
            d["annotations"] = [_ann(aid=bad)]
            self.assertTrue(any(".id" in e for e in validate_shoot(d)), bad)

    def test_bad_ann_id_duplicate(self):
        d = default_shoot(self.md)
        d["annotations"] = [_ann("R01"), _ann("R01")]
        errs = validate_shoot(d)
        self.assertTrue(any("重复" in e for e in errs))

    def test_bad_kind(self):
        d = default_shoot(self.md)
        d["annotations"] = [_ann(kind="shoot")]
        self.assertTrue(any(".kind" in e for e in validate_shoot(d)))

    def test_bad_ai_type(self):
        d = default_shoot(self.md)
        d["annotations"] = [_ann("R01", kind="ai", ai_type="video")]
        self.assertTrue(any(".ai_type" in e for e in validate_shoot(d)))

    def test_bad_ai_missing_type(self):
        d = default_shoot(self.md)
        d["annotations"] = [_ann("R01", kind="ai", ai_type="")]
        self.assertTrue(any(".ai_type" in e for e in validate_shoot(d)))

    def test_bad_footage_state(self):
        d = _full_shoot(self.md_sha())
        d["footage"][0]["state"] = "picked"
        self.assertTrue(any(".state" in e for e in validate_shoot(d)))

    def test_bad_task_type_and_state(self):
        d = _full_shoot(self.md_sha())
        d["tasks"][0]["type"] = "subclip"
        d["tasks"][0]["state"] = "finished"
        errs = validate_shoot(d)
        self.assertTrue(any(".type" in e for e in errs))
        self.assertTrue(any(".state" in e for e in errs))

    def test_bad_dangling_refs(self):
        d = _full_shoot(self.md_sha())
        d["footage"][0]["ann_ids"] = ["R09"]     # 批注只有 R01/R02
        d["editNotes"][0]["footage_id"] = "f99"  # 素材只有 f01
        d["tasks"][0]["ref"] = "R09"
        errs = validate_shoot(d)
        self.assertTrue(any("ann_ids" in e for e in errs))
        self.assertTrue(any("footage_id" in e for e in errs))
        self.assertTrue(any(".ref" in e for e in errs))

    def test_bad_occurrence(self):
        for bad in (0, -1, "1", True, 1.5, None):
            d = default_shoot(self.md)
            d["annotations"] = [_ann(quote="先抛问题", occurrence=bad)]
            self.assertTrue(any(".occurrence" in e for e in validate_shoot(d)), bad)

    def test_bad_quote_type(self):
        d = default_shoot(self.md)
        d["annotations"] = [_ann(quote=123)]
        self.assertTrue(any(".quote" in e for e in validate_shoot(d)))

    def test_bad_unknown_top_key(self):
        d = _full_shoot(self.md_sha())
        d["annnotations"] = []  # 拼写错误
        self.assertTrue(any("未知顶层字段" in e for e in validate_shoot(d)))


class TestNextAnnId(ShootTestBase):
    """R01 起顺序编号，只进不退不复用"""

    def test_first_is_r01(self):
        self.assertEqual(next_ann_id(default_shoot(self.md)), "R01")

    def test_increments(self):
        d = default_shoot(self.md)
        d["annotations"] = [_ann("R01")]
        self.assertEqual(next_ann_id(d), "R02")
        d["annotations"] = [_ann("R01"), _ann("R02", kind="ai")]
        self.assertEqual(next_ann_id(d), "R03")

    def test_gap_not_reused(self):
        d = default_shoot(self.md)
        d["annotations"] = [_ann("R01"), _ann("R05", kind="ai")]
        self.assertEqual(next_ann_id(d), "R06")

    def test_carry_and_beyond_two_digits(self):
        d = default_shoot(self.md)
        d["annotations"] = [_ann("R09")]
        self.assertEqual(next_ann_id(d), "R10")
        d["annotations"] = [_ann("R99")]
        self.assertEqual(next_ann_id(d), "R100")

    def test_ignores_foreign_ids(self):
        d = default_shoot(self.md)
        d["annotations"] = [{"id": "X1"}, {"id": "c123"}, {}]
        self.assertEqual(next_ann_id(d), "R01")


class TestSaveSha(ShootTestBase):
    """save_shoot：校验 + 指纹拦截 + 原子写"""

    def test_save_ok_creates_sidecar(self):
        d = default_shoot(self.md)
        d["annotations"] = [_ann()]
        self.assertTrue(save_shoot(self.md, d))
        self.assertEqual(self.read_side()["annotations"][0]["id"], "R01")

    def test_save_rejects_stale_sha(self):
        """旁车存的是旧指纹、md 已被外部改动 → 拒收且不留半成品"""
        d = default_shoot(self.md)
        d["annotations"] = [_ann()]
        with open(self.md, "ab") as f:  # 外部追加改动 → 指纹变了
            f.write("外部改动\n".encode("utf-8"))
        with self.assertRaises(ShootShaMismatch):
            save_shoot(self.md, d)
        self.assertFalse(os.path.exists(self.side()))  # 拒收时不落盘

    def test_save_rejects_invalid_schema(self):
        d = default_shoot(self.md)
        del d["version"]
        with self.assertRaises(ShootValidationError):
            save_shoot(self.md, d)
        self.assertFalse(os.path.exists(self.side()))

    def test_save_atomic_replaces_whole_file(self):
        """二次保存整体替换（不是追加/残留），且无 .tmp 剩余、原 md 字节不动"""
        d1 = default_shoot(self.md)
        d1["annotations"] = [_ann("R01")]
        save_shoot(self.md, d1)
        md_bytes_before = open(self.md, "rb").read()
        d2 = load_shoot(self.md)
        d2["annotations"].append(_ann("R02", kind="ai"))
        save_shoot(self.md, d2)
        self.assertEqual(self.read_side(), d2)
        self.assertFalse(os.path.exists(self.side() + ".tmp"))
        self.assertEqual(open(self.md, "rb").read(), md_bytes_before)  # md 本体未动

    def test_save_strips_private_fields(self):
        """前端匹配缓存（_anchor 等）不落盘——旁车只存契约字段"""
        d = default_shoot(self.md)
        a = _ann()
        a["_anchor"] = "hash"
        a["_block_index"] = 1
        d["annotations"] = [a]
        save_shoot(self.md, d)
        self.assertNotIn("_anchor", self.read_side()["annotations"][0])

    def test_is_locked(self):
        self.assertFalse(is_locked(self.md))
        d = default_shoot(self.md)
        d["locked"] = True
        save_shoot(self.md, d)
        self.assertTrue(is_locked(self.md))
        with open(self.side(), "wb") as f:  # 旁车损坏不该把编辑一起锁死
            f.write(b"{{{")
        self.assertFalse(is_locked(self.md))


class TestAgentWriteback(ShootTestBase):
    """agent 回写白名单：只许改 tasks[].state/output、footage[].state/note"""

    def setUp(self):
        super().setUp()
        self.old = _full_shoot(self.md_sha())

    def _check(self, new):
        return check_agent_writeback(self.old, new)

    def _mutate(self, fn):
        import copy
        new = copy.deepcopy(self.old)
        fn(new)
        return new

    # ---- 放行（白名单内） ----

    def test_allow_task_state(self):
        ok, errs = self._check(self._mutate(
            lambda d: d["tasks"][0].update(state="doing")))
        self.assertTrue(ok, errs)

    def test_allow_task_output(self):
        ok, errs = self._check(self._mutate(
            lambda d: d["tasks"][0].update(output="cards/r02.json")))
        self.assertTrue(ok, errs)

    def test_allow_task_done_and_footage_selected_together(self):
        def mut(d):
            d["tasks"][0]["state"] = "done"
            d["footage"][0]["state"] = "selected"
            d["footage"][0]["note"] = "已确认采用"
        ok, errs = self._check(self._mutate(mut))
        self.assertTrue(ok, errs)

    def test_allow_noop(self):
        import copy
        ok, errs = self._check(copy.deepcopy(self.old))
        self.assertTrue(ok, errs)

    # ---- 拒收（白名单外） ----

    def test_reject_annotation_change(self):
        ok, errs = self._check(self._mutate(
            lambda d: d["annotations"][0].update(shoot_hint="改了提示")))
        self.assertFalse(ok)
        self.assertTrue(any("annotations" in e for e in errs))

    def test_reject_annotation_add_and_remove(self):
        ok, errs = self._check(self._mutate(
            lambda d: d["annotations"].append(_ann("R03"))))
        self.assertFalse(ok)
        ok, errs = self._check(self._mutate(lambda d: d["annotations"].pop()))
        self.assertFalse(ok)

    def test_reject_footage_add_remove(self):
        def add(d):
            d["footage"].append({"id": "f02", "file": "x.mp4", "ann_ids": [],
                                 "state": "candidate", "match": "manual",
                                 "note": ""})
        self.assertFalse(self._check(self._mutate(add))[0])
        self.assertFalse(self._check(self._mutate(
            lambda d: d["footage"].pop()))[0])

    def test_reject_footage_field_overreach(self):
        for mut in (lambda d: d["footage"][0].update(file="别处.mp4"),
                    lambda d: d["footage"][0].update(ann_ids=["R02"]),
                    lambda d: d["footage"][0].update(match="ai:0.99")):
            ok, errs = self._check(self._mutate(mut))
            self.assertFalse(ok, mut)
            self.assertTrue(any("越权" in e for e in errs))

    def test_reject_footage_id_change(self):
        """改 id 等于删一条加一条——按增删条目拒收"""
        ok, errs = self._check(self._mutate(
            lambda d: d["footage"][0].update(id="f09")))
        self.assertFalse(ok)
        self.assertTrue(any("不许增删条目" in e for e in errs))

    def test_reject_task_add_remove_and_ref(self):
        def add(d):
            d["tasks"].append({"id": "t02", "type": "motion", "ref": "R01",
                               "state": "open", "output": ""})
        self.assertFalse(self._check(self._mutate(add))[0])
        self.assertFalse(self._check(self._mutate(
            lambda d: d["tasks"].pop()))[0])
        ok, errs = self._check(self._mutate(
            lambda d: d["tasks"][0].update(ref="R01", type="aigen")))
        self.assertFalse(ok)  # type/ref 都不在白名单

    def test_reject_locked_and_sha_and_version(self):
        for mut in (lambda d: d.update(locked=True),
                    lambda d: d.update(source_sha256="0" * 64),
                    lambda d: d.update(version=2)):
            ok, errs = self._check(self._mutate(mut))
            self.assertFalse(ok, mut)

    def test_reject_plan_and_editnotes_change(self):
        ok, _ = self._check(self._mutate(
            lambda d: d["plan"].update(checklist_md="清单.md")))
        self.assertFalse(ok)
        ok, _ = self._check(self._mutate(
            lambda d: d["editNotes"][0].update(note="偷改剪辑批注")))
        self.assertFalse(ok)

    def test_reject_illegal_enum_in_whitelist_field(self):
        """白名单字段也不是随便写——写成非法枚举照样被 schema 拦下"""
        ok, errs = self._check(self._mutate(
            lambda d: d["tasks"][0].update(state="finished")))
        self.assertFalse(ok)
        self.assertTrue(any("schema" in e for e in errs))

    def test_reject_private_and_unknown_fields(self):
        ok, errs = self._check(self._mutate(
            lambda d: d["tasks"][0].update(hack="埋字段")))
        self.assertFalse(ok)
        ok, errs = self._check(self._mutate(
            lambda d: d["footage"][0].update(_anchor="x")))
        self.assertTrue(ok, errs)  # 下划线私有字段剥掉后视为没改


if __name__ == "__main__":
    unittest.main()
