"""media/cover 封面子技能（S3，oil-cover 移植+火山 Ark 化）单测。

覆盖：resolve_ark_key 三级来源与缺 key 人话、ark_error_hint 错码翻译、
ark_post_with_fallback 候选链降级（404 换下一个/401 人话退出）、
analysis_from_agent_prompt（纯文本 master / JSON 透传 / --frame 解析）、
lock_known_title 标题逐字锁定、apply_script_guards 硬规则回填与去副标题、
generate_images 假 Ark 全链路（参考帧上传开关/产物/sidecar/模型记录）、
--prescan 真链路（真 mp4→候选帧→零 API）、agent 模式无 prompt-file 人话守门。

真链路造视频用 imageio_ffmpeg 自带 ffmpeg（install.ps1 固定依赖），不碰用户素材。
"""
import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

# ——先钉真·标准库 select（必须在任何 import 之前，地雷见 problem-log P6）——
_shadow_dirs = [p for p in sys.path
                if p and os.path.isfile(os.path.join(p, "select.py"))]
if _shadow_dirs:
    sys.path[:] = [p for p in sys.path if p not in _shadow_dirs]
import select  # noqa: E402,F401 —— 真·标准库
assert hasattr(select, "select"), "标准库 select 被 cut/scripts/select.py 遮蔽"
sys.path.extend(_shadow_dirs)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skill" / "media" / "cover" / "scripts" / "generate_cover.py"

# ——隔离用户配置/key（必须在 import 模块之前）——
_TMP = Path(tempfile.mkdtemp(prefix="cover_test_"))
os.environ["COVER_CONFIG"] = str(_TMP / "nonexistent-config.json")
os.environ.pop("ARK_API_KEY", None)

sys.path.insert(0, str(SCRIPT.parent))
import generate_cover as gc  # noqa: E402

try:
    import imageio_ffmpeg  # noqa: E402
    _FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:  # noqa: BLE001
    _FFMPEG = None

# 1x1 透明 png
_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _args(**over):
    base = dict(
        video=None, image=None, composite_base=None, composite_output=None,
        composite_aspect=None, title="后台设计 更有质感", topic="", subtitle=None,
        logo=None, rules_file=gc.DEFAULT_RULES_FILE, output_root=None, mode=None,
        prompt_file=None, frame="", prescan=False, api_base="https://ark.test/api/v3",
        analysis_model=None, image_model=None, api_key_file=None, frame_count=8,
        candidate_seconds="", scan_fps=0.0, max_frame_width=320,
        portrait_size="1536x2048", landscape_size="2048x1536", bilibili_size="2048x1152",
        no_reference=False, default_creator_portrait=False, aspect="all",
        allow_subtitle=True, skip_generate=False, dry_run=False, timeout=1,
    )
    base.update(over)
    return argparse.Namespace(**base)


def _frames(tmp):
    files = []
    for idx in range(3):
        p = tmp / f"candidate_{idx + 1:02d}.jpg"
        p.write_bytes(_TINY_PNG)
        files.append({"label": f"candidate_{idx + 1:02d}", "path": str(p), "timestamp": f"{idx + 0.5:.2f}"})
    return files


def _subprocess_env():
    env = {**os.environ, "COVER_CONFIG": str(_TMP / "nonexistent-config.json")}
    env.pop("ARK_API_KEY", None)
    if _FFMPEG:
        # imageio_ffmpeg 只带 ffmpeg 不进 PATH——喂给子进程让 shutil.which 找得到
        env["PATH"] = f"{Path(_FFMPEG).parent}{os.pathsep}{env.get('PATH', '')}"
    return env


# ---------------------------------------------------------------- key

class TestArkKey(unittest.TestCase):
    def test_env_priority(self):
        with mock.patch.dict(os.environ, {"ARK_API_KEY": "env-key"}):
            self.assertEqual(gc.resolve_ark_key(_args()), "env-key")

    def test_api_key_file(self):
        key_file = _TMP / "k.txt"
        key_file.write_text(" file-key\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"ARK_API_KEY": ""}):
            self.assertEqual(gc.resolve_ark_key(_args(api_key_file=key_file)), "file-key")

    def test_missing_fails_human(self):
        with mock.patch.dict(os.environ, {"ARK_API_KEY": ""}), \
                mock.patch.object(gc, "_ark_key_candidates", return_value=[]):
            err = StringIO()
            with mock.patch("sys.stderr", err):
                with self.assertRaises(SystemExit):
                    gc.resolve_ark_key(_args())
        self.assertIn("ARK_API_KEY", err.getvalue())
        self.assertIn(".ark_key", err.getvalue())


# ---------------------------------------------------------------- ark errors

class TestArkErrors(unittest.TestCase):
    def test_hint_mapping(self):
        self.assertIn("脱敏", gc.ark_error_hint(401, "HTTP 401: bad key"))
        self.assertIn("开通", gc.ark_error_hint(404, "ModelNotOpen"))
        self.assertIn("安全体验模式", gc.ark_error_hint(429, "SetLimitExceeded"))
        self.assertEqual(gc.ark_error_hint(404, "no such path"), "")

    def test_fallback_chain_404_then_success(self):
        tried = []
        responses = [RuntimeError("HTTP 404 from url: ModelNotOpen"), {"ok": 1}]

        def fake_post(url, payload, key, timeout):
            tried.append(payload["model"])
            r = responses[len(tried) - 1]
            if isinstance(r, Exception):
                raise r
            return r

        with mock.patch.object(gc, "post_json", side_effect=fake_post):
            model, resp = gc.ark_post_with_fallback(
                "https://ark.test/api/v3/images/generations",
                lambda m: {"model": m}, gc.IMAGE_MODEL_FALLBACKS, "k", 1, "生图",
            )
        self.assertEqual(model, gc.IMAGE_MODEL_FALLBACKS[1])
        self.assertEqual(resp, {"ok": 1})
        self.assertEqual(tried[0], gc.IMAGE_MODEL_FALLBACKS[0])

    def test_401_fails_fast_human(self):
        err = StringIO()
        with mock.patch.object(gc, "post_json",
                               side_effect=RuntimeError("HTTP 401 from url: invalid")), \
                mock.patch("sys.stderr", err):
            with self.assertRaises(SystemExit):
                gc.ark_post_with_fallback(
                    "u", lambda m: {"model": m}, ["a", "b"], "k", 1, "生图",
                )
        self.assertIn("脱敏", err.getvalue())

    def test_all_models_fail_human(self):
        with mock.patch.object(gc, "post_json",
                               side_effect=RuntimeError("HTTP 404 from url: ModelNotOpen")):
            with self.assertRaises(RuntimeError) as ctx:
                gc.ark_post_with_fallback(
                    "u", lambda m: {"model": m}, ["a"], "k", 1, "视觉分析",
                )
        self.assertIn("没开通", str(ctx.exception))


# ---------------------------------------------------------------- agent prompt

class TestAgentPrompt(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cover_ap_"))
        self.frames = _frames(self.tmp)

    def test_plain_text_master(self):
        pf = self.tmp / "prompt.txt"
        pf.write_text("一张精致封面……", encoding="utf-8")
        analysis = gc.analysis_from_agent_prompt(_args(prompt_file=pf), self.frames)
        self.assertEqual(analysis["task_type"], "agent_prompt")
        self.assertEqual(set(analysis["prompts"]), {"3x4", "4x3", "16x9"})
        for key, item in analysis["prompts"].items():
            self.assertEqual(item["prompt"], "一张精致封面……")
            self.assertEqual(item["size"], gc.aspect_size(_args(), key))
        self.assertEqual(analysis["selected_frame"]["label"], "candidate_01")

    def test_frame_by_number_and_label(self):
        pf = self.tmp / "prompt.txt"
        pf.write_text("P", encoding="utf-8")
        a = gc.analysis_from_agent_prompt(_args(prompt_file=pf, frame="2"), self.frames)
        self.assertEqual(a["selected_frame"]["label"], "candidate_02")
        a = gc.analysis_from_agent_prompt(_args(prompt_file=pf, frame="candidate_03"), self.frames)
        self.assertEqual(a["selected_frame"]["label"], "candidate_03")

    def test_frame_by_path_and_invalid(self):
        pf = self.tmp / "prompt.txt"
        pf.write_text("P", encoding="utf-8")
        outside = self.tmp / "my.png"
        outside.write_bytes(_TINY_PNG)
        a = gc.analysis_from_agent_prompt(_args(prompt_file=pf, frame=str(outside)), self.frames)
        self.assertEqual(a["selected_frame"]["path"], str(outside))
        err = StringIO()
        with mock.patch("sys.stderr", err):
            with self.assertRaises(SystemExit):
                gc.analysis_from_agent_prompt(_args(prompt_file=pf, frame="candidate_99"), self.frames)
        self.assertIn("candidate_99", err.getvalue())

    def test_json_passthrough(self):
        pf = self.tmp / "analysis.json"
        data = {"prompts": {"3x4": {"size": "1536x2048", "prompt": "逐画幅"}},
                "selected_frame": {"label": "candidate_02"}}
        pf.write_text(json.dumps(data), encoding="utf-8")
        a = gc.analysis_from_agent_prompt(_args(prompt_file=pf), self.frames)
        self.assertEqual(a["task_type"], "agent_prompt_json")
        self.assertEqual(a["prompts"]["3x4"]["prompt"], "逐画幅")
        # 已带 selected_frame 时不覆盖
        self.assertEqual(a["selected_frame"]["label"], "candidate_02")


# ---------------------------------------------------------------- title lock & guards

class TestTitleLockAndGuards(unittest.TestCase):
    def test_exact_title_lines_chinese(self):
        self.assertEqual(gc.exact_title_lines("后台设计 更有质感"), ["后台设计", "更有质感"])

    def test_exact_title_lines_latin_single(self):
        self.assertEqual(gc.exact_title_lines("ClipSy"), ["ClipSy"])

    def test_lock_known_title_prepends(self):
        analysis = {"prompts": {"3x4": {"size": "s", "prompt": "A clean light base cover."}}}
        notes = gc.lock_known_title(_args(title="后台设计 更有质感"), analysis)
        prompt = analysis["prompts"]["3x4"]["prompt"]
        self.assertTrue(notes)
        self.assertIn('Title text: "后台设计 更有质感"', prompt)
        self.assertIn("Title rendering guard:", prompt)

    def test_guards_backfill_aspect_and_strip_subtitle(self):
        tmp = Path(tempfile.mkdtemp(prefix="cover_g_"))
        analysis = {
            "title": {"main": "后台设计 更有质感", "line_breaks": ["后台设计", "更有质感"], "subtitle": "副标题x"},
            "prompts": {
                "3x4": {"size": "s", "prompt": 'Big title. optional subtitle "限时干货". Clean pastel grid background with overflow, shadow, perspective tilt, colour sampling. Output exactly one complete 3:4 cover.'},
            },
        }
        out = gc.apply_script_guards(_args(title="后台设计 更有质感", allow_subtitle=False,
                                           default_creator_portrait=False), analysis, tmp, [])
        prompt = out["prompts"]["3x4"]["prompt"]
        self.assertNotIn("限时干货", prompt)
        self.assertIn("No external subtitle", prompt)
        self.assertIn("Output exactly one complete 3:4 cover", prompt)
        self.assertTrue((tmp / "analysis.json").exists())


# ---------------------------------------------------------------- fake generation

class TestGenerateFake(unittest.TestCase):
    def test_full_flow_with_reference(self):
        tmp = Path(tempfile.mkdtemp(prefix="cover_gen_"))
        ref = tmp / "ref.jpg"
        ref.write_bytes(_TINY_PNG)
        analysis = {"prompts": {"3x4": {"size": "1536x2048", "prompt": "P"}}}
        sidecars = {"3x4": tmp / "3x4.prompt.md"}
        sidecars["3x4"].write_text("PENDING", encoding="utf-8")
        captured = {}

        def fake_ark(url, build_payload, candidates, key, timeout, what):
            captured["payload"] = build_payload(candidates[0])
            captured["candidates"] = candidates
            return "m-flash", {"data": [{"b64_json": base64.b64encode(_TINY_PNG).decode()}]}

        with mock.patch.object(gc, "ark_post_with_fallback", side_effect=fake_ark):
            results, models_used = gc.generate_images(
                _args(aspect="3x4"), "k", tmp, tmp, "vid", analysis, [ref], sidecars, ["m-flash", "m-pro"],
            )
        self.assertEqual(results, {"3x4": str(tmp / "vid_3x4.png")})
        self.assertEqual(models_used, {"3x4": "m-flash"})
        self.assertTrue((tmp / "vid_3x4.png").exists())
        self.assertGreater((tmp / "vid_3x4.png").stat().st_size, 0)
        self.assertIn("GENERATED", sidecars["3x4"].read_text(encoding="utf-8"))
        raw = json.loads((tmp / "3x4.response.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["model"], "m-flash")
        self.assertEqual(captured["candidates"], ["m-flash", "m-pro"])
        self.assertIn("image", captured["payload"])  # 参考帧已上传（data URI）

    def test_no_reference_omits_image(self):
        tmp = Path(tempfile.mkdtemp(prefix="cover_gen2_"))
        analysis = {"prompts": {"3x4": {"size": "s", "prompt": "P"}}}
        sidecars = {"3x4": tmp / "s.md"}
        sidecars["3x4"].write_text("", encoding="utf-8")
        captured = {}

        def fake_ark(url, build_payload, candidates, key, timeout, what):
            captured["payload"] = build_payload(candidates[0])
            return "m", {"data": [{"b64_json": base64.b64encode(_TINY_PNG).decode()}]}

        with mock.patch.object(gc, "ark_post_with_fallback", side_effect=fake_ark):
            gc.generate_images(
                _args(aspect="3x4", no_reference=True), "k", tmp, tmp, "v", analysis, [], sidecars, ["m"],
            )
        self.assertNotIn("image", captured["payload"])


# ---------------------------------------------------------------- real CLI links

def _make_mp4(workdir):
    mp4 = workdir / "testsrc.mp4"
    subprocess.run(
        [_FFMPEG, "-y", "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=10",
         "-pix_fmt", "yuv420p", str(mp4)],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return mp4


@unittest.skipUnless(_FFMPEG, "需要 ffmpeg（imageio_ffmpeg 自带即可；时长读取有 ffprobe 兜底）")
class TestRealLinks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = Path(tempfile.mkdtemp(prefix="cover_e2e_"))
        cls.mp4 = _make_mp4(cls.work)

    def test_prescan_zero_api(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--video", str(self.mp4), "--prescan",
             "--candidate-seconds", "0.5,1.5,2.5", "--max-frame-width", "320"],
            capture_output=True, text=True, env=_subprocess_env(), cwd=str(self.work), timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        manifest = json.loads(proc.stdout)
        self.assertTrue(manifest["prescan"])
        self.assertEqual(manifest["mode"], "agent")
        self.assertEqual(len(manifest["frames"]), 3)
        for item in manifest["frames"]:
            self.assertTrue(Path(item["path"]).exists())
        self.assertIn("--prompt-file", manifest["next_step"])

    def test_agent_mode_guard_human(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--video", str(self.mp4),
             "--candidate-seconds", "0.5,1.5,2.5", "--max-frame-width", "320"],
            capture_output=True, text=True, env=_subprocess_env(), cwd=str(self.work), timeout=120,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--mode api", proc.stderr)
        self.assertIn("--prompt-file", proc.stderr)

    def test_help_smoke(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True, text=True, env=_subprocess_env(), timeout=60,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--prompt-file", proc.stdout)


if __name__ == "__main__":
    unittest.main()
