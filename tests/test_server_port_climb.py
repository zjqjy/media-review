"""端口占用检测回归：Windows 的 SO_REUSEADDR 曾允许第二个服务进程绑定同一监听
端口——「被占爬位 +1」永不触发，新旧服务挤同端口流量随机分，僵尸旧服务吞掉
保存的版本快照（problem-log P7）。占用检测必须真失败，爬位逻辑才工作。"""
import os
import sys

# ——先钉真·标准库 select（必须在 import draft_server/http.server 之前）——
# 地雷：cut/scripts/select.py 与标准库同名，同进程先跑的 test_jy_draft /
# test_silence_trim 会把 cut/scripts 插进 sys.path，本文件随后 import
# http.server→socketserver→import select 拿到假模块。解法同 test_shoot_match。
import pathlib  # noqa: E402

_shadow_dirs = [p for p in sys.path
                if p and os.path.isfile(os.path.join(p, "select.py"))]
if _shadow_dirs:
    sys.path[:] = [p for p in sys.path if p not in _shadow_dirs]
import select  # noqa: E402 —— 真·标准库
assert hasattr(select, "select"), "标准库 select 被 cut/scripts/select.py 遮蔽"
sys.path.extend(_shadow_dirs)
import socket  # noqa: E402 —— 钉完再导（socket 间接 import select）

import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "media" / "draft" / "scripts"))
sys.path.insert(1, str(ROOT / "skill" / "media" / "shoot" / "scripts"))

import draft_server as ds  # noqa: E402
import shoot_server as ss  # noqa: E402


class TestPortClimb(unittest.TestCase):
    """服务类对已占端口必须抛 OSError（爬位循环依赖这个失败）。"""

    @staticmethod
    def _occupy():
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        return s, s.getsockname()[1]

    def test_draft_拒绝绑定已占端口(self):
        s, port = self._occupy()
        try:
            with self.assertRaises(OSError):
                ds.DraftServer(("127.0.0.1", port), ds.DraftHandler)
        finally:
            s.close()

    def test_shoot_拒绝绑定已占端口(self):
        s, port = self._occupy()
        try:
            with self.assertRaises(OSError):
                ss.ShootServer(("127.0.0.1", port), ss.ShootHandler)
        finally:
            s.close()

    def test_free_port_可正常起服(self):
        # 对照组：没被占的端口构造成功（证明拒占不是构造器本身坏了）
        s1 = ds.DraftServer(("127.0.0.1", 0), ds.DraftHandler)
        port = s1.server_address[1]
        s2 = ss.ShootServer(("127.0.0.1", 0), ss.ShootHandler)
        try:
            self.assertNotEqual(port, 0)
        finally:
            s1.server_close()
            s2.server_close()


if __name__ == "__main__":
    unittest.main()
