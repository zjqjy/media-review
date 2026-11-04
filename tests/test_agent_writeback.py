"""agent 回写单测：跨 agent 协作协议卡 + 回写校验器（S2-E）。

覆盖 shoot_validate 的两条命脉：
  - validate：全量 schema v1 校验（语义对齐 draft/shoot_io.validate_shoot，另加
    S2-D 的 tasks[].note 可选字符串、md 指纹加验、done 任务产物实况警告）；
  - check_writeback：白名单 diff——只许改 tasks[].state/output、footage[].state/note，
    tasks[].note 是生成器私有字段（动了 = 绕过协议，拒收），条目不许增删；
并做与 draft/shoot_io.check_agent_writeback 的对拍（同输入同结论），以及
shoot_validate / emit_protocol 两个 CLI 的退出码断言。
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# 注意：绝不把 cut/scripts 插进 sys.path（其中的 select.py 会遮蔽标准库）
sys.path.insert(0, str(ROOT / "skill" / "media" / "draft" / "scripts"))
sys.path.insert(0, str(ROOT / "skill" / "media" / "shoot" / "scripts"))

import shoot_validate  # noqa: E402
from shoot_io import check_agent_writeback as draft_check  # noqa: E402  对拍基准（S2-A）

VALIDATE_SCRIPT = ROOT / "skill" / "media" / "shoot" / "scripts" / "shoot_validate.py"
EMIT_SCRIPT = ROOT / "skill" / "media" / "shoot" / "scripts" / "emit_protocol.py"
CARD = ROOT / "skill" / "media" / "shoot" / "AGENT_PROTOCOL.md"

MD_TEXT = "# 定稿大纲\n\n先抛问题再亮答案。\n\n- 要点甲\n- 要点乙\n"


def _fake_hash(seed):
    """像块锚点的 10 位 hex（校验只看非空字符串）"""
    return hashlib.md5(seed.encode("utf-8")).hexdigest()[:10]


def _ann(aid="R01", kind="manual", quote="", **kw):
    """按冻结 schema v1 造一条呈现批注"""
    a = {"id": aid, "block_hash": _fake_hash(aid + kind), "quote": quote,
         "occurrence": 1, "kind": kind,
         "shoot_hint": "办公室实测镜头" if kind == "manual" else "",
         "ai_type": "card" if kind == "ai" else "",
         "ai_brief": "做一张卖点字幕卡" if kind == "ai" else "",
         "status": "open", "created": "2026-11-05T10:00:00"}
    a.update(kw)
    return a


def _shoot(sha):
    """一套交叉引用齐全的合法数据：2 批注 + 1 素材 + 1 剪辑批注 + 2 任务（t02 带 S2-D note）"""
    return {
        "version": 1, "source_sha256": sha, "locked": False,
        "annotations": [_ann("R01"), _ann("R02", kind="ai", quote="先抛问题")],
        "plan": {"checklist_md": "", "ai_tasks_md": ""},
        "footage": [{"id": "f01", "file": "03_实拍/办公室.mp4",
                     "ann_ids": ["R01"], "state": "candidate",
                     "match": "filename", "note": ""}],
        "editNotes": [{"id": "e01", "footage_id": "f01",
                       "note": "截 0:03-0:07，接 R02 卡片后"}],
        "tasks": [
            {"id": "t01", "type": "card", "ref": "R02", "state": "open", "output": ""},
            {"id": "t02", "type": "aigen", "ref": "R01", "state": "open",
             "output": "", "note": "other 需人工定工具"},
        ],
    }


def _mutate(data, fn):
    """深拷贝后套用变更函数（回写模拟的最小脚手架）"""
    new = json.loads(json.dumps(data, ensure_ascii=False))
    fn(new)
    return new


class AgentTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.md = os.path.join(self.tmp.name, "大纲_v3.md")
        with open(self.md, "wb") as f:  # 二进制写死字节，排除换行翻译干扰
            f.write(MD_TEXT.encode("utf-8"))
        with open(self.md, "rb") as f:
            self.sha = hashlib.sha256(f.read()).hexdigest()
        self.data = _shoot(self.sha)
        self.side = shoot_validate.shoot_path(self.md)

    def tearDown(self):
        self.tmp.cleanup()

    def plant_sidecar(self, data=None):
        """把数据落成真实旁车文件"""
        with open(self.side, "wb") as f:
            f.write(json.dumps(data if data is not None else self.data,
                               ensure_ascii=False, indent=2).encode("utf-8"))

    def plant_output(self, rel, text="占位产物内容"):
        """在项目根造一个真实产物文件（posix 相对路径）"""
        p = os.path.join(self.tmp.name, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(text.encode("utf-8"))
        return p

    def run_cli(self, script, *args):
        return subprocess.run([sys.executable, str(script), *args],
                              capture_output=True)


class TestValidateSchema(AgentTestBase):
    """validate 全量 schema v1 校验（语义对齐 draft/shoot_io.validate_shoot）"""

    def test_合法数据零错误_含S2D备案note(self):
        self.assertEqual(shoot_validate.validate(self.data), [])

    def test_version必填且恒为1(self):
        for bad in ({**self.data, "version": 2}, {**self.data, "version": True}):
            with self.subTest(bad=bad.get("version")):
                errs = shoot_validate.validate({**bad, "version": bad["version"]})
                self.assertTrue(any("version" in e for e in errs))
        d = _mutate(self.data, lambda x: x.pop("version"))
        self.assertTrue(any("缺少 version" in e for e in shoot_validate.validate(d)))

    def test_source_sha256格式(self):
        d = _mutate(self.data, lambda x: x.update(source_sha256="ABC"))
        self.assertTrue(any("source_sha256" in e for e in shoot_validate.validate(d)))
        d = _mutate(self.data, lambda x: x.pop("source_sha256"))
        self.assertTrue(any("缺少 source_sha256" in e for e in shoot_validate.validate(d)))

    def test未知顶层字段拒收(self):
        d = _mutate(self.data, lambda x: x.update(agent_progress="50%"))
        errs = shoot_validate.validate(d)
        self.assertTrue(any("未知顶层字段" in e and "agent_progress" in e for e in errs))

    def test_S2D备案note必须是可选字符串(self):
        d = _mutate(self.data, lambda x: x["tasks"][1].update(note=123))
        self.assertTrue(any("tasks[1].note" in e for e in shoot_validate.validate(d)))
        d = _mutate(self.data, lambda x: x["tasks"][1].pop("note"))
        self.assertEqual(shoot_validate.validate(d), [])  # 缺省也合法

    def test任务枚举与引用(self):
        d = _mutate(self.data, lambda x: x["tasks"][0].update(state="finished"))
        self.assertTrue(any("tasks[0].state" in e for e in shoot_validate.validate(d)))
        d = _mutate(self.data, lambda x: x["tasks"][0].update(type="3d_print"))
        self.assertTrue(any("tasks[0].type" in e for e in shoot_validate.validate(d)))
        d = _mutate(self.data, lambda x: x["tasks"][0].update(ref="R99"))
        self.assertTrue(any("tasks[0].ref 引用不存在" in e for e in shoot_validate.validate(d)))

    def test_id重复拒收(self):
        d = _mutate(self.data, lambda x: x["tasks"][1].update(id="t01"))
        self.assertTrue(any("tasks[1].id 重复" in e for e in shoot_validate.validate(d)))

    def test_footage_ann_ids引用存在(self):
        d = _mutate(self.data, lambda x: x["footage"][0].update(ann_ids=["R77"]))
        self.assertTrue(any("引用不存在的批注: R77" in e for e in shoot_validate.validate(d)))

    def test_locked非布尔拒收(self):
        d = _mutate(self.data, lambda x: x.update(locked="yes"))
        self.assertTrue(any("locked" in e for e in shoot_validate.validate(d)))

    def test根不是对象(self):
        self.assertEqual(shoot_validate.validate([1, 2]), ["根节点应是 JSON 对象"])


class TestValidateMdSha(AgentTestBase):
    """md_path 加验：source_sha256 与 md 实况一致（md 本体被改 = 硬错误拒收）"""

    def test指纹一致零错误(self):
        self.assertEqual(shoot_validate.validate(self.data, md_path=self.md), [])

    def test_md被外部改动拒收(self):
        with open(self.md, "wb") as f:  # 模拟有人动了定稿本体
            f.write(MD_TEXT.replace("要点甲", "要点被改").encode("utf-8"))
        errs = shoot_validate.validate(self.data, md_path=self.md)
        self.assertTrue(any("指纹不符" in e for e in errs))
        # 硬错误：不带 [警告] 前缀
        self.assertTrue(all(not e.startswith("[警告]") for e in errs if "指纹不符" in e))

    def test_md不存在报错(self):
        errs = shoot_validate.validate(self.data, md_path=os.path.join(self.tmp.name, "无.md"))
        self.assertTrue(any("md 文件不存在" in e for e in errs))


class TestValidateDoneOutputWarning(AgentTestBase):
    """done 任务的 output 实况：警告级（[警告] 前缀），单独断言等级"""

    def test_done且产物不存在_警告级(self):
        d = _mutate(self.data, lambda x: x["tasks"][0].update(state="done",
                                                              output="04_卡片/没有.html"))
        errs = shoot_validate.validate(d, md_path=self.md)
        w = [e for e in errs if "不存在" in e and "tasks[0]" in e]
        self.assertEqual(len(w), 1)
        self.assertTrue(w[0].startswith("[警告]"))  # 等级：警告，不挡退出码

    def test_done且output为空_警告级(self):
        d = _mutate(self.data, lambda x: x["tasks"][0].update(state="done"))
        errs = shoot_validate.validate(d, md_path=self.md)
        w = [e for e in errs if "output 为空" in e]
        self.assertEqual(len(w), 1)
        self.assertTrue(w[0].startswith("[警告]"))

    def test_done且产物是空文件_警告级(self):
        self.plant_output("04_卡片/R02.html", text="")
        d = _mutate(self.data, lambda x: x["tasks"][0].update(state="done",
                                                              output="04_卡片/R02.html"))
        errs = shoot_validate.validate(d, md_path=self.md)
        w = [e for e in errs if "空文件" in e]
        self.assertEqual(len(w), 1)
        self.assertTrue(w[0].startswith("[警告]"))

    def test_done且产物真实非空_无警告(self):
        self.plant_output("04_卡片/R02.html")
        d = _mutate(self.data, lambda x: x["tasks"][0].update(state="done",
                                                              output="04_卡片/R02.html"))
        self.assertEqual(shoot_validate.validate(d, md_path=self.md), [])

    def test未完成任务不查产物(self):
        d = _mutate(self.data, lambda x: x["tasks"][0].update(state="doing"))
        self.assertEqual(shoot_validate.validate(d, md_path=self.md), [])


class TestCheckWriteback(AgentTestBase):
    """check_writeback 白名单 diff：合法放行、越权逐项拒收"""

    def test_合法回写_只改tasks_state_output(self):
        new = _mutate(self.data, lambda x: x["tasks"][0].update(
            state="done", output="04_卡片/R02_卖点卡.html"))
        self.assertEqual(shoot_validate.check_writeback(self.data, new), [])

    def test_合法回写_只改footage_state_note(self):
        new = _mutate(self.data, lambda x: x["footage"][0].update(
            state="selected", note="已人工确认选用"))
        self.assertEqual(shoot_validate.check_writeback(self.data, new), [])

    def test_认领doing放行(self):
        new = _mutate(self.data, lambda x: x["tasks"][0].update(state="doing"))
        self.assertEqual(shoot_validate.check_writeback(self.data, new), [])

    def test_S2D私有note原样保留放行(self):
        # note 新旧一致（agent 路径上带着它走）不算变化
        new = _mutate(self.data, lambda x: x["tasks"][1].update(state="doing"))
        self.assertEqual(shoot_validate.check_writeback(self.data, new), [])

    def test_新旧相同零错误(self):
        self.assertEqual(shoot_validate.check_writeback(self.data, self.data), [])

    # ---- 以下越权各例，必须拒收且错误信息具体 ----

    def test_改annotations字段拒收(self):
        new = _mutate(self.data, lambda x: x["annotations"][0].update(status="closed"))
        errs = shoot_validate.check_writeback(self.data, new)
        self.assertTrue(any("annotations" in e and "被改动" in e for e in errs))

    def test_改source_sha256拒收(self):
        new = _mutate(self.data, lambda x: x.update(source_sha256="0" * 64))
        errs = shoot_validate.check_writeback(self.data, new)
        self.assertTrue(any("source_sha256" in e for e in errs))

    def test_改plan拒收(self):
        new = _mutate(self.data, lambda x: x["plan"].update(checklist_md="乱指"))
        errs = shoot_validate.check_writeback(self.data, new)
        self.assertTrue(any("plan" in e for e in errs))

    def test_改locked拒收(self):
        new = _mutate(self.data, lambda x: x.update(locked=True))
        self.assertTrue(shoot_validate.check_writeback(self.data, new))

    def test_改editNotes拒收(self):
        new = _mutate(self.data, lambda x: x["editNotes"][0].update(note="改剪法"))
        errs = shoot_validate.check_writeback(self.data, new)
        self.assertTrue(any("editNotes" in e for e in errs))

    def test_新增footage条目拒收(self):
        new = _mutate(self.data, lambda x: x["footage"].append(
            {"id": "f02", "file": "03_实拍/新.mp4", "ann_ids": ["R01"],
             "state": "candidate"}))
        errs = shoot_validate.check_writeback(self.data, new)
        self.assertTrue(any("新增了 footage 条目 f02" in e for e in errs))

    def test_删除tasks条目拒收(self):
        new = _mutate(self.data, lambda x: x["tasks"].pop(1))
        errs = shoot_validate.check_writeback(self.data, new)
        self.assertTrue(any("删除了 tasks 条目 t02" in e for e in errs))

    def test_改tasks私有note拒收_绕过协议(self):
        new = _mutate(self.data, lambda x: x["tasks"][1].update(note="agent 自己加的"))
        errs = shoot_validate.check_writeback(self.data, new)
        self.assertTrue(any("tasks[1]" in e and ".note 被改动" in e and "绕过协议" in e
                            for e in errs))

    def test_白名单字段写非法枚举拒收(self):
        new = _mutate(self.data, lambda x: x["tasks"][0].update(state="finished"))
        errs = shoot_validate.check_writeback(self.data, new)
        self.assertTrue(any("回写结果 schema 不过" in e and "state" in e for e in errs))

    def test_白名单字段写错类型拒收(self):
        new = _mutate(self.data, lambda x: x["tasks"][0].update(output=123))
        errs = shoot_validate.check_writeback(self.data, new)
        self.assertTrue(any("回写结果 schema 不过" in e for e in errs))

    def test_footage条目改白名单外字段拒收(self):
        new = _mutate(self.data, lambda x: x["footage"][0].update(file="偷换素材.mp4"))
        errs = shoot_validate.check_writeback(self.data, new)
        self.assertTrue(any("footage[0]（f01）.file 被越权改动" in e for e in errs))

    def test_缺id条目拒收(self):
        new = _mutate(self.data, lambda x: x["tasks"][0].pop("id"))
        errs = shoot_validate.check_writeback(self.data, new)
        self.assertTrue(any("缺 id 或重复 id" in e for e in errs))


class TestCrossCheckWithDraft(AgentTestBase):
    """对拍：同一份输入，shoot_validate.check_writeback 与 draft/shoot_io.
    check_agent_writeback 必须同结论（合法两边都放行，越权两边都拒收）"""

    def _scenarios(self):
        return [
            ("合法: tasks state/output", _mutate(self.data, lambda x: x["tasks"][0].update(
                state="done", output="04_卡片/R02.html"))),
            ("合法: footage state/note", _mutate(self.data, lambda x: x["footage"][0].update(
                state="selected", note="确认选用"))),
            ("合法: 认领doing", _mutate(self.data, lambda x: x["tasks"][0].update(state="doing"))),
            ("越权: 改 tasks 私有 note", _mutate(self.data, lambda x: x["tasks"][1].update(
                note="被人动了"))),
            ("越权: 新增 footage 条目", _mutate(self.data, lambda x: x["footage"].append(
                {"id": "f02", "file": "x.mp4", "ann_ids": ["R01"], "state": "candidate"}))),
            ("越权: 删除 tasks 条目", _mutate(self.data, lambda x: x["tasks"].pop())),
            ("越权: 改 annotations", _mutate(self.data, lambda x: x["annotations"][0].update(
                quote="偷改引文"))),
            ("越权: 改 source_sha256", _mutate(self.data, lambda x: x.update(
                source_sha256="a" * 64))),
            ("越权: 改 plan", _mutate(self.data, lambda x: x["plan"].update(
                ai_tasks_md="x.md"))),
            ("越权: 白名单字段非法枚举", _mutate(self.data, lambda x: x["tasks"][0].update(
                state="halfway"))),
        ]

    def test_同输入同结论(self):
        for name, new in self._scenarios():
            with self.subTest(场景=name):
                mine_pass = not shoot_validate.check_writeback(self.data, new)
                draft_pass, _ = draft_check(self.data, new)
                self.assertEqual(mine_pass, draft_pass,
                                 f"对拍不一致: mine_pass={mine_pass} draft_pass={draft_pass}")


class TestValidateCli(AgentTestBase):
    """CLI 退出码 0/1：python shoot_validate.py <定稿md> [--against <快照>]"""

    def _snapshot(self, data=None):
        p = os.path.join(self.tmp.name, "快照.json")
        with open(p, "wb") as f:
            f.write(json.dumps(data if data is not None else self.data,
                               ensure_ascii=False, indent=2).encode("utf-8"))
        return p

    def test_全量校验合法退出0(self):
        self.plant_sidecar()
        r = self.run_cli(VALIDATE_SCRIPT, self.md)
        self.assertEqual(r.returncode, 0, r.stdout.decode("utf-8", errors="replace"))
        self.assertIn("结果: 通过", r.stdout.decode("utf-8", errors="replace"))

    def test_md被改退出1(self):
        self.plant_sidecar()
        with open(self.md, "wb") as f:
            f.write(MD_TEXT.replace("要点乙", "要点丙").encode("utf-8"))
        r = self.run_cli(VALIDATE_SCRIPT, self.md)
        self.assertEqual(r.returncode, 1)
        out = r.stdout.decode("utf-8", errors="replace")
        self.assertIn("指纹不符", out)

    def test_against合法回写退出0(self):
        self.plant_sidecar(_mutate(self.data, lambda x: x["tasks"][0].update(
            state="doing")))
        r = self.run_cli(VALIDATE_SCRIPT, self.md, "--against", self._snapshot())
        self.assertEqual(r.returncode, 0, r.stdout.decode("utf-8", errors="replace"))
        out = r.stdout.decode("utf-8", errors="replace")
        self.assertIn("[改动] tasks[t01].state", out)

    def test_against越权回写退出1(self):
        bad = _mutate(self.data, lambda x: x["footage"].append(
            {"id": "f02", "file": "x.mp4", "ann_ids": ["R01"], "state": "candidate"}))
        self.plant_sidecar(bad)
        r = self.run_cli(VALIDATE_SCRIPT, self.md, "--against", self._snapshot())
        self.assertEqual(r.returncode, 1)
        out = r.stdout.decode("utf-8", errors="replace")
        self.assertIn("新增了 footage 条目 f02", out)

    def test_against改私有note退出1(self):
        self.plant_sidecar(_mutate(self.data, lambda x: x["tasks"][1].update(
            note="agent 改的")))
        r = self.run_cli(VALIDATE_SCRIPT, self.md, "--against", self._snapshot())
        self.assertEqual(r.returncode, 1)
        self.assertIn("绕过协议", r.stdout.decode("utf-8", errors="replace"))

    def test_against警告级不挡退出码(self):
        # done 任务 output 指向不存在文件 → [警告] 打印但退出码 0（单独断言等级）
        self.plant_sidecar(_mutate(self.data, lambda x: x["tasks"][0].update(
            state="done", output="04_卡片/没有.html")))
        r = self.run_cli(VALIDATE_SCRIPT, self.md, "--against", self._snapshot())
        self.assertEqual(r.returncode, 0, r.stdout.decode("utf-8", errors="replace"))
        out = r.stdout.decode("utf-8", errors="replace")
        self.assertIn("[警告]", out)
        self.assertIn("不存在", out)

    def test_旁车缺失退出1(self):
        r = self.run_cli(VALIDATE_SCRIPT, self.md)
        self.assertEqual(r.returncode, 1)
        self.assertIn("旁车不存在", r.stdout.decode("utf-8", errors="replace"))

    def test_旁车JSON损坏退出1(self):
        with open(self.side, "wb") as f:
            f.write("{oops".encode("utf-8"))
        r = self.run_cli(VALIDATE_SCRIPT, self.md)
        self.assertEqual(r.returncode, 1)
        self.assertIn("JSON 解析失败", r.stdout.decode("utf-8", errors="replace"))

    def test_快照缺失退出1(self):
        self.plant_sidecar()
        r = self.run_cli(VALIDATE_SCRIPT, self.md, "--against",
                         os.path.join(self.tmp.name, "没有的快照.json"))
        self.assertEqual(r.returncode, 1)

    def test_无参数打印用法退出1(self):
        r = self.run_cli(VALIDATE_SCRIPT)
        self.assertEqual(r.returncode, 1)
        self.assertIn("用法", r.stdout.decode("utf-8", errors="replace"))

    def test_md不存在退出1(self):
        r = self.run_cli(VALIDATE_SCRIPT, os.path.join(self.tmp.name, "没有.md"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("md 文件不存在", r.stdout.decode("utf-8", errors="replace"))


class TestEmitProtocolCli(unittest.TestCase):
    """emit_protocol CLI：复制规程卡进项目根，已存在时打印差异摘要并等 --force"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "生产项目")
        os.makedirs(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def _dst(self):
        return os.path.join(self.root, "AGENT_PROTOCOL.md")

    def test_首次写入内容一致(self):
        r = subprocess.run([sys.executable, str(EMIT_SCRIPT), self.root],
                           capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", errors="replace"))
        with open(CARD, "rb") as f:
            self.assertEqual(open(self._dst(), "rb").read(), f.read())  # 字节级一致
        self.assertIn("已写入", r.stdout.decode("utf-8", errors="replace"))

    def test_重复写入已一致退出0(self):
        subprocess.run([sys.executable, str(EMIT_SCRIPT), self.root], capture_output=True)
        r = subprocess.run([sys.executable, str(EMIT_SCRIPT), self.root],
                           capture_output=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("已是一致", r.stdout.decode("utf-8", errors="replace"))

    def test_已存在且不同_未force退出1并打印差异摘要(self):
        with open(self._dst(), "wb") as f:
            f.write("# 旧版规程卡\n只有一行\n".encode("utf-8"))
        r = subprocess.run([sys.executable, str(EMIT_SCRIPT), self.root],
                           capture_output=True)
        self.assertEqual(r.returncode, 1)
        out = r.stdout.decode("utf-8", errors="replace")
        self.assertIn("差异摘要", out)
        self.assertIn("未覆盖", out)
        with open(self._dst(), "rb") as f:  # 未 force 不许动原文件
            self.assertIn("旧版规程卡".encode("utf-8"), f.read())

    def test_force覆盖(self):
        with open(self._dst(), "wb") as f:
            f.write("# 旧版规程卡\n".encode("utf-8"))
        r = subprocess.run([sys.executable, str(EMIT_SCRIPT), self.root, "--force"],
                           capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", errors="replace"))
        with open(CARD, "rb") as f:
            self.assertEqual(open(self._dst(), "rb").read(), f.read())

    def test_无参数与坏根退出1(self):
        for args in ([], [os.path.join(self.tmp.name, "不存在的根")]):
            with self.subTest(args=args):
                r = subprocess.run([sys.executable, str(EMIT_SCRIPT), *args],
                                   capture_output=True)
                self.assertEqual(r.returncode, 1)


if __name__ == "__main__":
    unittest.main()
