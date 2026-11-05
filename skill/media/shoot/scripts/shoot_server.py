#!/usr/bin/env python3
"""shoot_server.py — 素材关联面板本地服务（纯标准库，零依赖）

仿 draft_server.py 结构：静态托管 web/ 前端 + 少量 JSON API。文件即数据库：
  - 状态全在旁车 shoot.json（<定稿md>.shoot.json），服务端本身不存任何业务状态，
    唯一内存态是「当前打开的项目」（重启即失，可用 --project 启动时带回来）
  - md 本体永远只读（定稿锁定），本服务绝不写 md

写回纪律：POST /api/footage 只接受白名单字段（footage 的 state/note/ann_ids），
先做 schema 校验 + 定稿 sha 拦截（md 被外部改动 → 409 拒写），再 tmp+os.replace 原子写。

安全边界：只绑 127.0.0.1，无鉴权（本机个人工具，与 draft_server 同红线）。

用法:
    python shoot_server.py [端口] [--project 项目根]
端口默认 8790，被占自动 +1 重试（最多 10 次）。
"""

import argparse
import hashlib
import json
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class ShootServer(ThreadingHTTPServer):
    # 同 draft_server：Windows 的 SO_REUSEADDR 允许双绑定同端口，占用检测失效、
    # 流量随机分（僵尸服务吞写事故的根因）。关掉 reuse，爬位 +1 才能触发。
    allow_reuse_address = False
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from 素材回收 import (  # noqa: E402 —— 复用同目录的旁车定位/匹配内核/时长探测
    find_sidecar, probe_duration, FOOTAGE_EXTS, VIDEO_EXTS)
import 剪辑交接  # noqa: E402 —— S2-D：补制任务生成 + cut 输入编译（05_剪辑交接）

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

VALID_FOOTAGE_STATE = ("candidate", "selected")

# 服务端唯一内存态：当前项目（LOCK 保护所有旁车读改写）
CTX = {"project_root": None, "md_path": None, "sidecar_path": None}
LOCK = threading.Lock()
_DUR_CACHE = {}  # (abs_path, mtime_ns, size) -> 秒 | None，进程内复用


def reset_ctx():
    """测试用：清空内存项目态。"""
    CTX["project_root"] = None
    CTX["md_path"] = None
    CTX["sidecar_path"] = None


# ---------------------------------------------------------------- 工具


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def _write_text_atomic(path, text):
    """原子写：tmp + os.replace，避免写一半崩掉毁旁车。"""
    tmp = str(path) + ".tmp"
    with open(tmp, "wb") as f:
        f.write(text.encode("utf-8"))
    os.replace(tmp, str(path))


def load_state():
    """读当前旁车 shoot.json 全量（调用方持有 LOCK 或自担竞态）。"""
    return json.loads(_read_bytes(CTX["sidecar_path"]).decode("utf-8"))


def current_md_sha256():
    """当前定稿 md 的字节 sha256（每次现算，不缓存——拦截要抓的就是外部改动）。"""
    return _sha256_bytes(_read_bytes(CTX["md_path"]))


def sha_ok():
    """定稿 md 是否仍与旁车指纹一致（旁车缺指纹时按 True 处理，只降级不拦死）。"""
    try:
        state = load_state()
    except Exception:  # noqa: BLE001
        return False
    src = str(state.get("source_sha256", ""))
    return bool(src) and current_md_sha256() == src


def project_info():
    """GET /api/project 的响应体。"""
    if not CTX["project_root"]:
        return {"project_root": None}
    return {
        "project_root": CTX["project_root"],
        "md_path": CTX["md_path"],
        "source_sha256": _sidecar_sha(),
        "md_sha256": current_md_sha256(),
        "sha_ok": sha_ok(),
    }


def _sidecar_sha():
    try:
        return str(load_state().get("source_sha256", ""))
    except Exception:  # noqa: BLE001
        return ""


def set_project(root=None, md=None):
    """设置当前项目（校验定稿 md + 旁车存在 + schema 版本）。失败抛 ValueError。"""
    if md:
        root = Path(md).parent
    elif root:
        root = Path(root)
    else:
        raise ValueError("缺少 project（项目根）或 md（定稿路径）")
    if not root.is_dir():
        raise ValueError(f"项目根不存在: {root}")
    md_path, sidecar_path = find_sidecar(root, md or "")
    state = json.loads(_read_bytes(sidecar_path).decode("utf-8"))
    if not isinstance(state, dict) or state.get("version") != 1:
        raise ValueError(f"旁车不是 version 1 schema: {sidecar_path}")
    if not isinstance(state.get("annotations"), list):
        raise ValueError(f"旁车缺 annotations 数组: {sidecar_path}")
    CTX["project_root"] = str(root.resolve())
    CTX["md_path"] = str(md_path.resolve())
    CTX["sidecar_path"] = str(sidecar_path.resolve())
    return project_info()


def apply_updates(state, updates):
    """把批量更新应用到 state（就地修改）——纯函数，测试直接调。
    白名单：footage[].state / footage[].note / footage[].ann_ids / footage[].match（限 manual）。
    其余一律拒。校验失败抛 ValueError（消息可直接给前端）。
    """
    if not isinstance(updates, list) or not updates:
        raise ValueError("updates 必须是非空数组")
    ann_ids = [str(a.get("id", "")) for a in state.get("annotations", [])
               if a.get("id")]
    by_id = {str(f.get("id")): f for f in state.get("footage", [])}
    n = 0
    for u in updates:
        if not isinstance(u, dict):
            raise ValueError("updates 每项必须是对象")
        fid = str(u.get("footage_id", ""))
        f = by_id.get(fid)
        if f is None:
            raise ValueError(f"footage 条目不存在: {fid}")
        touched = False
        if "state" in u:
            if u["state"] not in VALID_FOOTAGE_STATE:
                raise ValueError(f"非法 state: {u['state']!r}"
                                 f"（只允许 {'/'.join(VALID_FOOTAGE_STATE)}）")
            f["state"] = u["state"]
            touched = True
        if "note" in u:
            if not isinstance(u["note"], str):
                raise ValueError("note 必须是字符串")
            f["note"] = u["note"]
            touched = True
        if "ann_ids" in u:
            v = u["ann_ids"]
            if not isinstance(v, list) or any(not isinstance(x, str) for x in v):
                raise ValueError("ann_ids 必须是批注 id 字符串数组")
            unknown = [x for x in v if x not in ann_ids]
            if unknown:
                raise ValueError(f"未知批注 id: {unknown}（annotation id 定稿后"
                                 f"永不变，不许发明新 id）")
            f["ann_ids"] = list(dict.fromkeys(v))  # 去重保序
            touched = True
        if "match" in u:
            # 面板挂接/确认 = 人拍板，match 记 manual（b-manual 徽标由此点亮）；
            # filename/ai:* 由匹配器与 AI 建议直接写旁车，不走本端点（防伪造机器来源）
            if u["match"] != "manual":
                raise ValueError("match 只允许设 manual（filename/ai:* 由匹配器写入）")
            f["match"] = u["match"]
            touched = True
        if not touched:
            raise ValueError(f"update 缺少可写字段（state/note/ann_ids/match）: {fid}")
        n += 1
    return n


def upsert_editnote(state, footage_id, note):
    """剪辑批注 upsert（纯函数，就地改 state["editNotes"]，测试直接调）。

    语义：同 footage_id 覆盖（一条素材一条剪辑批注——截哪段/效果/接哪）；
    不存在则追加新条目（e 编号顺延）；历史上同 footage_id 的重复条目收敛为一条。
    校验失败抛 ValueError（消息可直接给前端）。
    """
    if not isinstance(footage_id, str) or not footage_id:
        raise ValueError("缺少 footage_id")
    if not isinstance(note, str):
        raise ValueError("note 必须是字符串")
    if not any(str(f.get("id")) == footage_id
               for f in state.get("footage", [])):
        raise ValueError(f"footage 条目不存在: {footage_id}")
    notes = state.setdefault("editNotes", [])
    kept, entry = [], None
    for en in notes:
        if str(en.get("footage_id", "")) == footage_id:
            if entry is None:
                entry = en          # 首条占原位，就地覆盖
                kept.append(en)
            continue                # 其余重复条目丢弃（upsert 收敛成一条）
        kept.append(en)
    if entry is None:
        entry = {"id": 剪辑交接.next_id(notes, "e"),
                 "footage_id": footage_id, "note": ""}
        kept.append(entry)
    entry["note"] = note
    state["editNotes"] = kept
    return entry


def _clean_path_arg(raw):
    """防御性清路径：首尾空白 + Windows「复制文件地址」的引号（前端也清，双保险）。"""
    s = str(raw or "").strip()
    return s.strip("\"'\u201c\u201d\u2018\u2019\u300c\u300d").strip()


def add_footage(state, files, ann_ids):
    """手动添加素材（P8：不跑素材回收.py 也能在面板直接登记）。

    files: 路径字符串数组，必须真实存在于盘上；旁车 file 字段一律存**相对项目根**
    的 posix 风格（与素材回收/剪辑交接/校验器同基准）；项目根外的文件拒收——
    05_剪辑交接按项目根复制素材，根外的素材交接会找不到。
    ann_ids: 可选，登记时立即挂接的批注 id（必须是旁车已有 id，不发明新 id）。
    同一文件（按解析后的绝对路径判重）重复添加 → 跳过并给原因；素材 id 从现有
    footage 最大号顺延（f01 起，不复用）。
    返回 (added, skipped)：added 为新条目清单（match=manual, state=candidate），
    skipped 为 [{file, reason}]。结构性参数错抛 ValueError 给前端 400。
    """
    if not isinstance(files, list) or not files:
        raise ValueError("files 必须是非空路径数组")
    if ann_ids is None:
        ann_ids = []
    if not isinstance(ann_ids, list) or any(not isinstance(x, str) for x in ann_ids):
        raise ValueError("ann_ids 必须是批注 id 字符串数组")
    known = {str(a.get("id")) for a in state.get("annotations", []) if a.get("id")}
    unknown = sorted({x for x in ann_ids if x not in known})
    if unknown:
        raise ValueError(f"未知批注 id: {unknown}（annotation id 定稿后永不变，"
                         f"不许发明新 id）")
    root = Path(CTX["project_root"]).resolve()
    by_abs = {}
    for f in state.get("footage", []):
        rel = str(f.get("file", ""))
        if not rel:
            continue
        try:
            by_abs[str(Path(root, *rel.split("/")).resolve())] = str(f.get("id"))
        except OSError:
            continue
    mx = 0
    for f in state.get("footage", []):
        m = re.match(r"^f(\d+)$", str(f.get("id") or ""))
        if m:
            mx = max(mx, int(m.group(1)))
    added, skipped = [], []
    for raw in files:
        p = Path(_clean_path_arg(raw))
        if not p.is_absolute():  # 相对路径按项目根解析（与旁车 file 字段同基准）
            p = root / p
        abs_p = p.expanduser().resolve()
        if not abs_p.is_file():
            skipped.append({"file": str(raw), "reason": "文件不存在"})
            continue
        try:
            rel = abs_p.relative_to(root)
        except ValueError:
            raise ValueError(f"素材必须在项目根内（剪辑交接按项目根复制素材）: "
                             f"{raw}")
        if str(abs_p) in by_abs:
            skipped.append({"file": abs_p.name,
                            "reason": f"已在素材表（{by_abs[str(abs_p)]}）"})
            continue
        mx += 1
        entry = {"id": f"f{mx:02d}", "file": rel.as_posix(),
                 "ann_ids": list(dict.fromkeys(ann_ids)),
                 "state": "candidate", "match": "manual", "note": ""}
        state.setdefault("footage", []).append(entry)
        by_abs[str(abs_p)] = entry["id"]
        added.append(entry)
    return added, skipped


def browse_dir(d=None):
    """GET /api/browse 的内核：列目录下的子目录与素材文件（不递归）。
    dir 缺省用当前项目根。返回 {cur, parent, dirs, files}，文件带 size/mtime。"""
    base = Path(_clean_path_arg(d) or CTX["project_root"] or "")
    if not str(base):
        raise ValueError("未打开项目：请先在页面打开项目，或显式给 dir")
    if not base.is_dir():
        raise ValueError(f"目录不存在: {base}")
    base = base.resolve()
    dirs, files = [], []
    for e in sorted(base.iterdir(), key=lambda x: x.name.lower()):
        try:
            if e.is_dir():
                if not e.name.startswith("."):
                    dirs.append(e.name)
            elif e.suffix.lower() in FOOTAGE_EXTS:
                st = e.stat()
                files.append({"name": e.name, "size": st.st_size,
                              "mtime": int(st.st_mtime)})
        except OSError:  # 个别项探不到（权限/占用）跳过，别让整个列表挂掉
            continue
    parent = base.parent
    return {"cur": str(base),
            "parent": str(parent) if parent != base else None,
            "dirs": dirs, "files": files}


def missing_anns(state):
    """缺拍清单：没有任何 footage 关联的**人工拍摄**批注（拍摄口径）。

    AI 制作批注的缺口不在「缺拍」里表达——它等的是 AI 产物（补制任务），
    任务区与剪辑说明.md 的「缺口」段已覆盖，混进来会让补拍清单永远非空。
    """
    linked = set()
    for f in state.get("footage", []):
        linked.update(f.get("ann_ids", []))
    out = []
    for a in state.get("annotations", []):
        if str(a.get("kind", "manual")) != "manual":
            continue
        if str(a.get("id", "")) not in linked:
            out.append({
                "id": a.get("id", ""), "kind": a.get("kind", "manual"),
                "quote": a.get("quote", ""),
                "shoot_hint": a.get("shoot_hint", ""),
                "ai_type": a.get("ai_type", ""),
                "ai_brief": a.get("ai_brief", ""),
                "status": a.get("status", "open"),
            })
    return out


def probe_items():
    """素材文件在盘状态 + 视频时长（内存缓存，键 = 路径+mtime+大小）。"""
    root = CTX["project_root"]
    state = load_state()
    items = []
    for f in state.get("footage", []):
        rel = str(f.get("file", ""))
        abs_p = os.path.join(root, rel.replace("/", os.sep))
        exists = os.path.isfile(abs_p)
        dur = None
        if exists and Path(abs_p).suffix.lower() in VIDEO_EXTS:
            try:
                st = os.stat(abs_p)
                key = (abs_p, st.st_mtime_ns, st.st_size)
            except OSError:
                key = (abs_p, 0, 0)
            if key in _DUR_CACHE:
                dur = _DUR_CACHE[key]
            else:
                dur = probe_duration(abs_p)  # 外部二进制只经 subprocess
                _DUR_CACHE[key] = dur
        items.append({"file": rel, "exists": exists, "duration": dur})
    return items


# ---------------------------------------------------------------- HTTP


class ShootHandler(BaseHTTPRequestHandler):
    server_version = "ShootServer/1.0"

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
    _STATIC = {"/": ("shoot.html", "text/html; charset=utf-8"),
               "/index.html": ("shoot.html", "text/html; charset=utf-8"),
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
            if u.path == "/api/project":
                with LOCK:
                    if not CTX["project_root"]:
                        return self._json({"project_root": None})
                    return self._json(project_info())
            if u.path == "/api/state":
                with LOCK:
                    if not CTX["project_root"]:
                        return self._json({"project_root": None})
                    return self._json({**project_info(), "state": load_state()})
            if u.path == "/api/missing":
                with LOCK:
                    if not CTX["project_root"]:
                        return self._json({"error": "未设置项目"}, 400)
                    state = load_state()
                    miss = missing_anns(state)
                    return self._json({
                        "missing": miss, "missing_count": len(miss),
                        "total_annotations": len(state.get("annotations", []))})
            if u.path == "/api/probe":
                with LOCK:
                    if not CTX["project_root"]:
                        return self._json({"error": "未设置项目"}, 400)
                    return self._json({"items": probe_items()})
            if u.path == "/api/tasks":
                with LOCK:
                    if not CTX["project_root"]:
                        return self._json({"error": "未设置项目"}, 400)
                    tasks = load_state().get("tasks", [])
                    return self._json({"tasks": tasks,
                                       "task_count": len(tasks)})
            if u.path == "/api/browse":
                q = parse_qs(u.query)
                return self._json(browse_dir((q.get("dir") or [""])[0]))
            return self._json({"error": "unknown endpoint"}, 404)
        except Exception as e:  # noqa: BLE001 —— 兜底别让线程静默死
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def do_POST(self):
        try:
            u = urlparse(self.path)
            data = self._body()
            if u.path == "/api/project":
                with LOCK:
                    info = set_project(data.get("project"),
                                       data.get("md"))
                    return self._json({**info,
                                       "state": load_state()})
            if u.path == "/api/footage":
                return self._api_footage(data)
            if u.path == "/api/footage/add":
                return self._api_footage_add(data)
            if u.path == "/api/editnote":
                return self._api_editnote(data)
            if u.path == "/api/tasks/generate":
                return self._api_tasks_generate(data)
            if u.path == "/api/handoff/compile":
                return self._api_handoff_compile()
            return self._json({"error": "unknown endpoint"}, 404)
        except ValueError as e:  # 项目/参数校验失败
            return self._json({"error": str(e)}, 400)
        except Exception as e:  # noqa: BLE001
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def _api_footage(self, data):
        """批量确认/改状态/挂接。body: {updates:[{footage_id, state?, note?, ann_ids?}]}"""
        updates = data.get("updates")
        with LOCK:
            if not CTX["project_root"]:
                return self._json({"error": "未设置项目"}, 400)
            state = load_state()
            # sha 拦截：定稿 md 被外部改动 → 拒写（409，同 draft_server 语义）
            src = str(state.get("source_sha256", ""))
            cur = current_md_sha256()
            if src and cur != src:
                print(f"[shoot][409] 旁车 source={src[:12]} 当前md={cur[:12]}",
                      flush=True)  # 观测：谁在面板开着时动了定稿
                return self._json({
                    "error": "定稿 md 已被外部修改，写回被拒"
                             "（先核对旁车 source_sha256 与定稿是否还配套）",
                    "md_sha256": cur}, 409)
            try:
                n = apply_updates(state, updates)
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
            _write_text_atomic(CTX["sidecar_path"],
                               json.dumps(state, ensure_ascii=False, indent=2))
            return self._json({"updated": n, "state": state,
                               "md_sha256": cur})

    # —— 以下 S2-D 新增路由（剪辑批注 / 补制任务 / cut 输入编译）——

    def _api_footage_add(self, data):
        """手动添加素材（P8）。body: {files:[绝对/相对路径], ann_ids?:[批注id]}
        ——浏览弹层勾文件登记进素材表并顺手挂接，不依赖素材回收.py。
        sha 拦截照走；同文件重复添加跳过并给原因（幂等）。"""
        with LOCK:
            if not CTX["project_root"]:
                return self._json({"error": "未设置项目"}, 400)
            state = load_state()
            blocked = self._sha_guard(state)
            if blocked:
                return blocked
            try:
                added, skipped = add_footage(state, data.get("files"),
                                             data.get("ann_ids"))
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
            if added:
                _write_text_atomic(CTX["sidecar_path"],
                                   json.dumps(state, ensure_ascii=False, indent=2))
            return self._json({"added": added, "skipped": skipped,
                               "state": state})

    def _sha_guard(self, state):
        """新路由共用的定稿指纹拦截：md 被外部改动 → 409 拒写（语义同
        _api_footage）。返回 None = 放行；否则已发出 409 响应。"""
        src = str(state.get("source_sha256", ""))
        cur = current_md_sha256()
        if src and cur != src:
            print(f"[shoot][409] 旁车 source={src[:12]} 当前md={cur[:12]}",
                  flush=True)
            return self._json({
                "error": "定稿 md 已被外部修改，写回被拒"
                         "（先核对旁车 source_sha256 与定稿是否还配套）",
                "md_sha256": cur}, 409)
        return None

    def _api_editnote(self, data):
        """剪辑批注 upsert。body: {footage_id, note}——同 footage_id 覆盖，
        截哪段/什么效果/接在哪。sha 拦截照走，原子写旁车。"""
        with LOCK:
            if not CTX["project_root"]:
                return self._json({"error": "未设置项目"}, 400)
            state = load_state()
            blocked = self._sha_guard(state)
            if blocked:
                return blocked
            try:
                entry = upsert_editnote(state, data.get("footage_id"),
                                        data.get("note"))
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
            _write_text_atomic(CTX["sidecar_path"],
                               json.dumps(state, ensure_ascii=False, indent=2))
            return self._json({"editnote": entry, "state": state})

    def _api_tasks_generate(self, data):
        """按呈现批注幂等生成补制任务并落盘（AI 批注→对应工具任务；
        缺素材的人工批注→补拍任务）。body 可为空对象。返回新增清单。"""
        with LOCK:
            if not CTX["project_root"]:
                return self._json({"error": "未设置项目"}, 400)
            state = load_state()
            blocked = self._sha_guard(state)
            if blocked:
                return blocked
            added, tasks = 剪辑交接.generate_tasks(state)
            if added:
                _write_text_atomic(
                    CTX["sidecar_path"],
                    json.dumps(state, ensure_ascii=False, indent=2))
            return self._json({"added": added, "added_count": len(added),
                               "tasks": tasks, "state": state})

    def _api_handoff_compile(self):
        """cut 输入编译（实跑）：写 <项目根>/05_剪辑交接/（素材复制副本 +
        剪辑说明.md），返回说明 md 内容 + 素材清单 + 缺口数。
        编译产物全部来自批注/素材状态，指纹不对不编译（同样 409 拦下）。
        持 LOCK 跑完——大文件复制期间挡住其他写请求，换状态一致。"""
        with LOCK:
            if not CTX["project_root"]:
                return self._json({"error": "未设置项目"}, 400)
            state = load_state()
            blocked = self._sha_guard(state)
            if blocked:
                return blocked
            try:
                r = 剪辑交接.compile_handoff(CTX["project_root"],
                                             CTX["md_path"])
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
            return self._json({"ok": True, "dir": r["dir"],
                               "copied": [c["copy_name"] for c in r["copied"]],
                               "missing": r["missing"],
                               "missing_count": r["missing_count"],
                               "md": r["md"]})


# ---------------------------------------------------------------- 入口


def make_server(host, port):
    """起一个 ThreadingHTTPServer（测试用它拿 0 号端口）。"""
    return ShootServer((host, port), ShootHandler)


def main():
    if os.name == "nt":
        try:  # Windows 控制台中文不炸
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description="shoot 素材关联面板本地服务")
    ap.add_argument("port", nargs="?", type=int, default=8790)
    ap.add_argument("--project", default="",
                    help="启动即设置项目根（等价页面里输入路径打开）")
    args = ap.parse_args()

    port, server = args.port, None
    for attempt in range(10):
        try:
            server = ShootServer(("127.0.0.1", port), ShootHandler)
            break
        except OSError:
            print(f"[shoot] 端口 {port} 被占，试 {port + 1}", flush=True)
            port += 1
    if server is None:
        print("[shoot] 连续 10 个端口都被占，退出")
        sys.exit(1)

    if args.project:
        try:
            info = set_project(root=args.project)
            print(f"[shoot] 项目: {info['project_root']}", flush=True)
            print(f"[shoot] 定稿: {info['md_path']}", flush=True)
        except ValueError as e:
            print(f"[shoot] --project 无效: {e}", flush=True)
    else:
        print("[shoot] 未设项目——在页面顶部输入项目根（或定稿 md 路径）打开",
              flush=True)
    port = server.server_address[1]  # 实际绑定端口（爬升后与入参可能不同）
    print(f"[shoot] 素材关联面板: http://127.0.0.1:{port}/", flush=True)
    print("[shoot] Ctrl+C 退出；状态全在旁车 shoot.json，服务重启不丢数据",
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[shoot] bye")


if __name__ == "__main__":
    main()
