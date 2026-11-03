#!/usr/bin/env python3
"""draft_server.py — draft 审阅工作台本地服务（纯标准库，零依赖）

职责：静态托管 web/ 前端 + 四个 JSON API。文件即数据库：
  - md 本体：<path>（客户端整档块数组写回，round-trip 保真见 draft_blocks）
  - 批注旁车：<path>.review.json（原子写：tmp + os.replace）

安全边界：只绑 127.0.0.1，无鉴权（本机个人工具，与 fetch_bili 同红线——
不对外暴露）。路径由用户在页面里给，服务端不做目录白名单（vault 在仓外）。

用法:
    python draft_server.py [端口] [--dir 默认浏览目录]
端口被占自动 +1 重试（最多 10 次）。默认端口 8765。
"""
import argparse
import hashlib
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from draft_blocks import parse_blocks, render_blocks, match_comment_blocks  # noqa: E402

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# ---------------------------------------------------------------- 工具


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _sidecar_path(md_path):
    """批注旁车：<原名>.review.json（outline.md → outline.md.review.json）"""
    return str(md_path) + ".review.json"


def _read_text(md_path):
    """读 md（utf-8）。容错换行：不转 \n，保字节原样交给解析器。"""
    with open(md_path, "rb") as f:
        return f.read().decode("utf-8")


def _write_text_atomic(path, text):
    """原子写：tmp + os.replace，避免写一半崩掉毁原文"""
    tmp = str(path) + ".tmp"
    with open(tmp, "wb") as f:
        f.write(text.encode("utf-8"))
    os.replace(tmp, path)


def _load_review(md_path):
    side = _sidecar_path(md_path)
    if os.path.exists(side):
        with open(side, "rb") as f:
            return json.loads(f.read().decode("utf-8"))
    return {"version": 1, "comments": []}


def _write_review(md_path, review):
    _write_text_atomic(_sidecar_path(md_path),
                       json.dumps(review, ensure_ascii=False, indent=2))


def _empty_review():
    return {"version": 1, "comments": []}


def _open_doc(md_path):
    """读 md + 旁车 → 客户端一屏所需全部数据"""
    text = _read_text(md_path)
    blocks = parse_blocks(text)
    review = _load_review(md_path)
    match_comment_blocks(blocks, review.get("comments", []))
    return {
        "path": str(md_path),
        "sha256": _sha256_bytes(text.encode("utf-8")),
        "blocks": blocks,
        "review": review,
    }


def _list_md(root, limit=200):
    """递归列目录下 md（跳隐藏目录/node_modules/__pycache__），按 mtime 新→旧"""
    root = os.path.abspath(root)
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and d not in
                       ("node_modules", "__pycache__")]
        for name in filenames:
            if name.lower().endswith(".md"):
                p = os.path.join(dirpath, name)
                try:
                    st = os.stat(p)
                    found.append({"path": p, "name": name,
                                  "mtime": int(st.st_mtime),
                                  "size": st.st_size})
                except OSError:
                    continue
                if len(found) >= limit * 3:  # 粗剪枝，排序后再截
                    break
        if len(found) >= limit * 3:
            break
    found.sort(key=lambda x: -x["mtime"])
    return found[:limit]


# ---------------------------------------------------------------- HTTP


class DraftHandler(BaseHTTPRequestHandler):
    server_version = "DraftServer/1.0"

    # —— 基础设施 ——
    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def log_message(self, fmt, *args):  # 静音逐请求日志，出错时 _json 兜底
        pass

    # —— 静态文件 ——
    _STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
               "/index.html": ("index.html", "text/html; charset=utf-8"),
               "/app.js": ("app.js", "application/javascript; charset=utf-8"),
               "/style.css": ("style.css", "text/css; charset=utf-8")}

    def _serve_static(self, urlpath):
        item = self._STATIC.get(urlpath)
        if item is None:
            self._json({"error": "not found"}, 404)
            return
        fname, ctype = item
        fpath = WEB_DIR / fname
        if not fpath.exists():
            self._json({"error": f"web/{fname} 缺失"}, 500)
            return
        body = fpath.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # —— 路由 ——
    def do_GET(self):
        try:
            u = urlparse(self.path)
            if u.path in self._STATIC:
                return self._serve_static(u.path)
            if u.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            if u.path == "/api/config":
                return self._json({"default_dir": getattr(
                    self, "default_dir", "") or os.getcwd()})
            if u.path == "/api/list":
                qs = parse_qs(u.query)
                d = unquote(qs.get("dir", [""])[0]) or os.getcwd()
                return self._json({"dir": d, "files": _list_md(d)})
            if u.path == "/api/review":
                qs = parse_qs(u.query)
                p = unquote(qs.get("path", [""])[0])
                if not p or not os.path.isfile(p):
                    return self._json({"error": "文件不存在"}, 404)
                return self._json({"path": p, "review": _load_review(p)})
            return self._json({"error": "unknown endpoint"}, 404)
        except Exception as e:  # noqa: BLE001 —— 兜底别让线程静默死
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def do_POST(self):
        try:
            u = urlparse(self.path)
            data = self._body()
            if u.path == "/api/open":
                return self._api_open(data)
            if u.path == "/api/save":
                return self._api_save(data)
            if u.path == "/api/review":
                return self._api_review(data)
            return self._json({"error": "unknown endpoint"}, 404)
        except Exception as e:  # noqa: BLE001
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    # —— API 实现 ——
    def _api_open(self, data):
        p = data.get("path", "")
        if not p or not os.path.isfile(p):
            return self._json({"error": "文件不存在: " + p}, 404)
        return self._json(_open_doc(os.path.abspath(p)))

    def _api_save(self, data):
        p = data.get("path", "")
        if not p or not os.path.isfile(p):
            return self._json({"error": "文件不存在: " + p}, 404)
        blocks = data.get("blocks")
        if not isinstance(blocks, list) or not blocks:
            return self._json({"error": "blocks 为空，拒绝写回"}, 400)
        current = _read_text(p)
        cur_sha = _sha256_bytes(current.encode("utf-8"))
        base = data.get("base_sha256", "")
        force = bool(data.get("force"))
        if cur_sha != base and not force:
            print(f"[draft][409] base={base[:12]} cur={cur_sha[:12]} path={p}",
                  flush=True)  # 观测：谁在 open/save 之间动了文件
            return self._json({"error": "文件已被外部修改，保存被拒"
                                       "（可强制覆盖）", "sha256": cur_sha}, 409)
        text = render_blocks(blocks)
        _write_text_atomic(p, text)
        review = data.get("review")
        if isinstance(review, dict):
            _write_review(p, review)
        new_sha = _sha256_bytes(text.encode("utf-8"))
        return self._json({"path": p, "sha256": new_sha,
                           "bytes": len(text.encode("utf-8"))})

    def _api_review(self, data):
        p = data.get("path", "")
        if not p or not os.path.isfile(p):
            return self._json({"error": "文件不存在: " + p}, 404)
        review = data.get("review")
        if not isinstance(review, dict):
            return self._json({"error": "review 缺失"}, 400)
        _write_review(p, review)
        return self._json({"path": p, "saved": True})


# ---------------------------------------------------------------- 入口


def main():
    if os.name == "nt":
        try:  # Windows 控制台中文不炸
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description="draft 审阅工作台本地服务")
    ap.add_argument("port", nargs="?", type=int, default=8765)
    ap.add_argument("--dir", default="", help="页面文件浏览器的默认目录")
    args = ap.parse_args()

    default_dir = args.dir

    port, server = args.port, None
    for attempt in range(10):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), DraftHandler)
            break
        except OSError:
            print(f"[draft] 端口 {port} 被占，试 {port + 1}")
            port += 1
    if server is None:
        print("[draft] 连续 10 个端口都被占，退出")
        sys.exit(1)

    default_dir = default_dir or os.getcwd()
    # 把默认目录传给前端：实例属性 + /api/config 拉取
    DraftHandler.default_dir = default_dir
    print(f"[draft] 审阅工作台: http://127.0.0.1:{port}/")
    print(f"[draft] 默认浏览目录: {default_dir}")
    print("[draft] Ctrl+C 退出；md 写回保真由 draft_blocks 单测保证")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[draft] bye")


if __name__ == "__main__":
    main()
