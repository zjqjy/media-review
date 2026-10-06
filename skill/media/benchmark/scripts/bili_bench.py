#!/usr/bin/env python3
"""B站对标研究工具——找对标、拉对标视频和逐字稿，供拆解模仿用。

与 review/fetch_bili.py（创作中心、只取自己账号数据）不同，本脚本走**公开接口**
（搜索/稿件详情/评论区任何人网页上都能看），登录态用**小号**（bench_sessdata，
与大号 sessdata 物理隔离——下载他人视频比看自己后台风险略高，风控只伤小号）。
个人学习拆解用，限速单线程，禁止批量爬取。

用法：
  python bili_bench.py login --config PATH          # 二维码登录小号，写 bench_sessdata（需 qrcode 库）
  python bili_bench.py search "剪映教程" [--pages 2] [--order click]   # 关键词搜索（公开）
  python bili_bench.py space <mid|主页URL> [--order click] [--pages 2] # UP热门稿（接口被风控自动降级搜索召回）
  python bili_bench.py view BVxx|URL                # 单视频详情（公开）
  python bili_bench.py comments BVxx [--n 30]       # 高赞评论（公开）
  python bili_bench.py subs BVxx [--dir DIR]        # 只拉 AI 字幕 → srt+md（需小号登录）
  python bili_bench.py fetch BVxx|URL [--dir DIR] [--no-video]
                                                    # 一条龙：详情+封面+视频(yt-dlp)+AI字幕逐字稿
  通用参数：--config PATH（默认自动向上找 _config_local.json）
           --json（表格输出改 JSON，机器可读）

搜索/详情/评论区匿名可用（主站预热+buvid+wbi 签名）；AI 字幕要小号登录。
space 投稿接口 2026-10 实测被服务端风控挡死（连 yt-dlp 都 412），命令会自动降级：
card 换 UP 名 → 搜索召回该 UP 热门稿（近似列表，不全）。无 AI 字幕的稿子逐字稿
走 cut 子技能的 FunASR 转录（见 benchmark/SKILL.md）。
"""

import argparse
import hashlib
import http.cookiejar
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# 同调用之间限速（秒）——风控第一道闸，别调小
RATE = 1.2

# wbi 参数签名混淆表。文档：bilibili-API-collect docs/misc/sign/wbi.md
WBI_MIXIN = [46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27,
             43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48,
             7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54,
             21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52]

# 二维码登录（passport，免 Cookie）。文档：bilibili-API-collect docs/login/login_action/QR.md
QR_API = {
    "generate": "https://passport.bilibili.com/x/passport-login/web/qrcode/generate",
    "poll": "https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
}
QR_CODE_MSG = {86101: "等待扫码", 86090: "已扫码，请在手机上确认", 86038: "二维码已过期"}


def die(msg, code=1):
    print(f"[bili_bench] 错误：{msg}", file=sys.stderr)
    sys.exit(code)


def clean_title(raw):
    """搜索结果的标题带 <em class="keyword"> 高亮标签，剥掉。"""
    return (raw or "").replace('<em class="keyword">', "").replace("</em>", "")


def fmt_secs(secs):
    """秒 → mm:ss（超过 1h 进 h:mm:ss）。"""
    secs = int(secs or 0)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def extract_bvid(text):
    """从 BV 号 / 完整链接 / b23.tv 短链里抠 BV 号（短链由调用方先解析）。"""
    m = re.search(r"(BV[0-9A-Za-z]{10})", text or "")
    return m.group(1) if m else None


def srt_ts(secs):
    """秒 → SRT 时间戳 00:00:00,000。"""
    ms = int(round((secs or 0) * 1000))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def srt_from_body(body):
    """AI 字幕 JSON 的 body[{from,to,content}] → SRT 全文（纯函数，可测）。"""
    lines = []
    for i, seg in enumerate(body or [], 1):
        lines.append(str(i))
        lines.append(f"{srt_ts(seg.get('from'))} --> {srt_ts(seg.get('to'))}")
        lines.append((seg.get("content") or "").strip())
        lines.append("")
    return "\n".join(lines)


def plain_from_body(body):
    """body[{content}] → 纯文本逐字稿（保留原文含口误，不合并行）。"""
    return "\n".join((seg.get("content") or "").strip()
                     for seg in (body or []) if (seg.get("content") or "").strip())


def netscape_lines(pairs):
    """cookie 名值对 → Netscape cookie 文件行（yt-dlp --cookies 用）。纯函数，可测。"""
    out = ["# Netscape HTTP Cookie File", "# 由 bili_bench.py 生成——含登录凭据，勿提交 git"]
    for name, value in pairs:
        if value:
            out.append(f".bilibili.com\tTRUE\t/\tTRUE\t0\t{name}\t{value}")
    return "\n".join(out) + "\n"


def parse_search_result(data):
    """搜索接口 data.result → 紧凑列表（纯函数，可测）。"""
    out = []
    for it in (data or {}).get("result") or []:
        if it.get("type") not in (None, "video"):  # 搜出直播/课程等混入，只要视频
            continue
        out.append({
            "bvid": it.get("bvid"),
            "title": clean_title(it.get("title")),
            "author": it.get("author"),
            "mid": it.get("mid"),
            "play": it.get("play"),
            "favorite": it.get("favorites"),
            "review": it.get("review"),  # 评论数
            "duration": it.get("duration"),  # 字符串 mm:ss
            "pubdate": it.get("pubdate"),
            "desc": (it.get("description") or "")[:80],
        })
    return out


def parse_reply_main(data):
    """评论接口 data.replies → 紧凑列表（纯函数，可测）。"""
    out = []
    for r in (data or {}).get("replies") or []:
        out.append({
            "like": r.get("like"),
            "uname": (r.get("member") or {}).get("uname"),
            "reply_ct": r.get("rcount"),
            "message": ((r.get("content") or {}).get("message") or "").replace("\n", " ")[:120],
        })
    return out


# ---------------------------------------------------------------- 客户端

class Bili:
    """带预热/buvid/wbi 的最小 B站客户端（ urllib + cookiejar，零依赖）。

    预热 = 先 GET 一次主站拿 b_nut/buvid3，再 finger/spi 补 buvid3/4——
    没这步搜索和详情接口一律 412（2026-10 实测）。
    """

    def __init__(self, sessdata=""):
        self.sessdata = sessdata or ""
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar))
        self.opener.addheaders = [("User-Agent", UA),
                                  ("Referer", "https://www.bilibili.com/")]
        self.jar = jar
        self._wbi_keys = None
        self._warmed = False

    def _set_cookie(self, name, value, domain=".bilibili.com"):
        c = http.cookiejar.Cookie(
            0, name, value, None, False, domain, True, domain.startswith("."),
            "/", True, False, None, False, None, None, {})
        self.jar.set_cookie(c)

    def warm(self):
        """主站预热 + buvid + 登录态（幂等，首个 API 调用前执行一次）。"""
        if self._warmed:
            return
        try:
            self.opener.open("https://www.bilibili.com/", timeout=15).read()
        except Exception as exc:  # noqa: BLE001——主站预热失败不拦路，接口层再报
            print(f"[bili_bench] 警告：主站预热失败（{exc}），接口可能 412", file=sys.stderr)
        try:
            payload = self._raw_json("https://api.bilibili.com/x/frontend/finger/spi")
            spi = payload.get("data") or {}
            if spi.get("b_3"):
                self._set_cookie("buvid3", spi["b_3"])
                self._set_cookie("buvid4", spi["b_4"])
        except Exception as exc:  # noqa: BLE001
            print(f"[bili_bench] 警告：buvid 获取失败（{exc}）", file=sys.stderr)
        if self.sessdata:
            self._set_cookie("SESSDATA", self.sessdata)
        self._warmed = True

    def _raw_json(self, url, params=None, timeout=15):
        qs = urllib.parse.urlencode(params) if params else ""
        full = f"{url}?{qs}" if qs else url
        with self.opener.open(full, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _wbi_sign(self, params):
        """wbi 参数签名：wts 混入排序后 md5。文档见 WBI_MIXIN 注释。"""
        if self._wbi_keys is None:
            # 未登录 nav 返回 code -101 但 wbi_img 照常在 data 里
            nav = self._raw_json("https://api.bilibili.com/x/web-interface/nav")
            wbi = (nav.get("data") or {}).get("wbi_img") or {}
            img = (wbi.get("img_url") or "").rsplit("/", 1)[-1].split(".")[0]
            sub = (wbi.get("sub_url") or "").rsplit("/", 1)[-1].split(".")[0]
            if not (img and sub):
                die("拿不到 wbi 签名密钥（nav 接口异常）")
            self._wbi_keys = (img, sub)
        img, sub = self._wbi_keys
        params = dict(params)
        params["wts"] = int(time.time())
        params = dict(sorted(params.items()))
        q = urllib.parse.urlencode(params)
        params["w_rid"] = hashlib.md5((q + img + sub).encode()).hexdigest()
        return params

    def api(self, url, params=None, wbi=False):
        """GET 业务接口：预热→签名→校验 code→限速。code -352/-412 给登录提示。"""
        self.warm()
        if wbi:
            params = self._wbi_sign(params or {})
        try:
            payload = self._raw_json(url, params)
        except urllib.error.HTTPError as exc:
            if exc.code in (412,):
                die(f"HTTP 412 风控（{url.rsplit('/', 1)[-1]}）——稍后再试；"
                    "反复 412 就登录小号（跑 login）或换网络")
            raise
        code = payload.get("code")
        if code == 0:
            time.sleep(RATE)
            return payload.get("data")
        if code in (-101, -352):
            die(f"接口要求登录或风控拦截（code {code}）——本接口需小号登录："
                "跑 python bili_bench.py login 扫码写入 bench_sessdata")
        die(f"接口返回异常 code={code} message={payload.get('message')}（{url}）")


# ---------------------------------------------------------------- 配置（与 review 同一套约定）

def find_config(explicit=None, required=True):
    """定位 _config_local.json：显式路径 > 脚本各级上级目录。
    公开命令（search/view/comments）不依赖配置，required=False 时找不到返回 None。"""
    if explicit:
        p = Path(explicit)
        if not p.is_file():
            die(f"指定的配置不存在：{p}")
        return p
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "_config_local.json"
        if candidate.is_file():
            return candidate
    if not required:
        return None
    die("找不到 _config_local.json。把仓根 config.example.json 复制为 "
        "_config_local.json，或用 --config 显式指定路径")


def load_config(path, need_session=False):
    cfg = json.loads(path.read_text(encoding="utf-8-sig"))
    if need_session and not cfg.get("bench_sessdata"):
        die("配置里没有 bench_sessdata（对标用小号 Cookie）——"
            "跑 python bili_bench.py login --config <配置路径> 扫码写入")
    return cfg


def vault_root(cfg, config_path):
    vp = cfg.get("vault_path")
    if vp:
        return Path(vp)
    return config_path.parents[2]


def bench_dir(cfg, config_path):
    """对标笔记目录（vault 内，随 git 提交）。"""
    key = (cfg.get("paths") or {}).get("benchmarks", "20_自媒体/对标")
    return vault_root(cfg, config_path) / key


def default_media_dir(cfg, config_path):
    """下载素材默认目录：vault 对标目录下的 _下载（会自动写 .gitignore 防止视频进 git）。
    vault 根在磁盘上不存在（vault_path 还是占位符/没配置）时回落当前目录，
    防止把下载目录建到假路径下面。"""
    try:
        root = vault_root(cfg, config_path)
        if root.is_dir():
            key = (cfg.get("paths") or {}).get("benchmarks", "20_自媒体/对标")
            return root / key / "_下载"
    except Exception:  # noqa: BLE001
        pass
    return Path.cwd() / "对标下载"


# ---------------------------------------------------------------- login（扫码，写 bench_sessdata）

def _show_qr(url, cfg_path):
    """二维码展示：tkinter 弹窗 → PNG 系统查看器 → 终端 ASCII，逐级回退。
    返回 (root或None, status_var或None, png_path或None)。"""
    import tkinter as tk
    import qrcode
    qr = qrcode.QRCode(border=2, box_size=8)
    qr.add_data(url)
    qr.make(fit=True)
    try:
        from PIL import ImageTk
        img = qr.make_image()
        pil_img = img.get_image() if hasattr(img, "get_image") else img
        root = tk.Tk()
        root.title("B站扫码登录（对标小号）")
        root.attributes("-topmost", True)
        tk_img = ImageTk.PhotoImage(pil_img)
        tk.Label(root, image=tk_img).pack(padx=24, pady=(24, 8))
        status = tk.StringVar(value="用小号 B站 App 扫一扫（180 秒内有效），确认后本窗口自动关闭")
        tk.Label(root, textvariable=status, fg="#555").pack(pady=(0, 20))
        root._qr_img_ref = tk_img  # 防 PhotoImage 被垃圾回收
        print("[login] 二维码窗口已弹出", file=sys.stderr)
        return root, status, None
    except Exception as exc:  # noqa: BLE001
        print(f"[login] 弹窗失败（{exc}），改存 PNG 由系统查看器打开", file=sys.stderr)
        try:
            path = cfg_path.parent / "_login_qr.png"
            qr.make_image().save(path)
            os.startfile(path)
            return None, None, path
        except Exception as exc2:  # noqa: BLE001
            print(f"[login] PNG 也失败（{exc2}），回退终端二维码", file=sys.stderr)
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            qr.print_ascii(invert=True)
            return None, None, None


def cmd_login(cfg_path, cfg):
    """小号二维码登录：SESSDATA 写入 bench_sessdata 字段（与大号 sessdata 隔离）。"""
    try:
        import qrcode  # noqa: F401
    except ImportError:
        die("login 需要 qrcode 库（仅此命令用）：python -m pip install qrcode")

    http2 = urllib.request
    def _get(url, params=None):
        qs = urllib.parse.urlencode(params) if params else ""
        req = http2.Request(f"{url}?{qs}" if qs else url,
                            headers={"User-Agent": UA, "Referer": "https://passport.bilibili.com/"})
        return json.loads(http2.urlopen(req, timeout=15).read())

    gen = _get(QR_API["generate"])
    if gen.get("code") != 0:
        die(f"二维码生成失败 code={gen.get('code')}")
    qrcode_key = gen["data"]["qrcode_key"]
    root, status, png_path = _show_qr(gen["data"]["url"], cfg_path)

    deadline = time.time() + 180
    sessdata = None
    resp_headers = None
    last_code = None
    last_poll = 0.0
    while time.time() < deadline:
        if root:
            root.update()
        if time.time() - last_poll < 2:
            time.sleep(0.1)
            continue
        last_poll = time.time()
        req = http2.Request(f"{QR_API['poll']}?qrcode_key={qrcode_key}",
                            headers={"User-Agent": UA})
        with http2.urlopen(req, timeout=15) as resp:
            resp_headers = resp.headers
            payload = json.loads(resp.read().decode("utf-8"))
        code = (payload.get("data") or {}).get("code")
        if code != last_code:
            msg = QR_CODE_MSG.get(code, "确认中…")
            print(f"[login] {msg}", file=sys.stderr)
            if status:
                status.set(msg)
            last_code = code
        if code == 86038:
            if root:
                root.destroy()
            die("二维码过期——重跑 login")
        if code == 0:
            for header in resp_headers.get_all("Set-Cookie") or []:
                for part in header.split(";"):
                    if part.strip().startswith("SESSDATA="):
                        sessdata = part.strip().split("=", 1)[1]
                        break
                if sessdata:
                    break
            break

    if root:
        root.destroy()
    if png_path and png_path.is_file():
        png_path.unlink()  # 用完即删，不留登录凭据图
    if not sessdata:
        die("超时未确认或没拿到 SESSDATA——重跑 login")
    cfg["bench_sessdata"] = sessdata
    cfg_path.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[login] OK——小号 SESSDATA 已写入 {cfg_path} 的 bench_sessdata", file=sys.stderr)


# ---------------------------------------------------------------- 输出

def print_rows(rows, columns, json_mode=False, json_key="rows"):
    """列输出：默认 markdown 表（人看），--json 转 JSON（AI 用）。"""
    if json_mode:
        print(json.dumps({json_key: rows}, ensure_ascii=False, indent=2))
        return
    if not rows:
        print("（空）")
        return
    print("| " + " | ".join(name for name, _ in columns) + " |")
    print("|" + "---|" * len(columns))
    for row in rows:
        cells = []
        for _, key in columns:
            v = row.get(key)
            if key == "duration" and isinstance(v, (int, float)):
                v = fmt_secs(v)
            cells.append("" if v is None else str(v))
        print("| " + " | ".join(cells) + " |")


# ---------------------------------------------------------------- 子命令实现

def cmd_search(client, args):
    """关键词搜索（公开）。order: 综合排序(默认)/click 播放多/pubdate 最新。"""
    rows = []
    for page in range(1, max(1, args.pages) + 1):
        data = client.api(
            "https://api.bilibili.com/x/web-interface/wbi/search/type",
            {"search_type": "video", "keyword": args.keyword, "page": page,
             "order": {"relevance": "", "click": "click", "pubdate": "pubdate"}.get(args.order, "")},
            wbi=True)
        page_rows = parse_search_result(data)
        rows += page_rows
        if not page_rows:
            break
    rows = fmt_search_rows(rows[:args.limit] if args.limit else rows)
    if not rows:
        print(f"没搜到「{args.keyword}」的结果——换个关键词试试")
        return
    print(f"## 搜索「{args.keyword}」共 {len(rows)} 条\n")
    print_rows(rows, [("BV", "bvid"), ("标题", "title"), ("UP", "author"),
                      ("播放", "play"), ("藏", "favorite"), ("评", "review"),
                      ("时长", "duration"), ("发布", "pubdate")],
               args.json)


def resolve_mid(text):
    """space 参数 → mid：纯数字 / space.bilibili.com/<mid> 链接。"""
    m = re.search(r"space\.bilibili\.com/(\d+)", text or "")
    if m:
        return m.group(1)
    if (text or "").isdigit():
        return text
    return None


def fmt_search_rows(rows):
    """pubdate 时间戳 → 日期字符串（就地转换）。"""
    for r in rows:
        if r.get("pubdate") and isinstance(r["pubdate"], int):
            r["pubdate"] = datetime.fromtimestamp(r["pubdate"]).strftime("%Y-%m-%d")
    return rows


def space_via_api(client, mid, order, pages):
    """space 投稿接口。2026-10 实测大概率 -403 风控（服务端要页面 JS 下发的
    风控令牌，连 yt-dlp 都 412）——失败抛 SystemExit，调用方降级。"""
    rows = []
    for page in range(1, max(1, pages) + 1):
        data = client.api(
            "https://api.bilibili.com/x/space/wbi/arc/search",
            {"mid": mid, "pn": page, "ps": 30, "order": order}, wbi=True) or {}
        vlist = ((data.get("list") or {}).get("vlist")) or []
        for v in vlist:
            rows.append({
                "bvid": v.get("bvid"),
                "title": v.get("title"),
                "play": v.get("play"),
                "favorite": v.get("favorites"),
                "review": v.get("comment"),
                "duration": v.get("length"),  # 字符串 mm:ss
                "pubdate": datetime.fromtimestamp(v.get("created") or 0).strftime("%Y-%m-%d")
                           if v.get("created") else "",
            })
        total = (data.get("page") or {}).get("count", 0)
        if page * 30 >= total or not vlist:
            break
    return rows


def space_via_search(client, mid, pages):
    """space 接口被风控时的降级：card 换 UP 名 → 搜索召回该 UP 稿件按播放排。
    召回不全（搜索只收热门/相关度高的），够"挑对标爆款"用，不够当全量列表。"""
    card = client._raw_json("https://api.bilibili.com/x/web-interface/card", {"mid": mid})
    if card.get("code") != 0:
        die(f"card 接口失败 code={card.get('code')}（mid={mid}）")
    data = card.get("data") or {}
    name = (data.get("card") or {}).get("name")
    fans = data.get("follower")
    if not name:
        die(f"mid={mid} 查不到 UP 名")
    rows = []
    for page in range(1, max(2, pages) + 1):  # 搜索召回默认翻 2 页补召回
        d = client.api("https://api.bilibili.com/x/web-interface/wbi/search/type",
                       {"search_type": "video", "keyword": name, "page": page}, wbi=True)
        rows += [r for r in parse_search_result(d) if str(r.get("mid")) == str(mid)]
        if not rows:
            break
    rows.sort(key=lambda r: -(r.get("play") or 0))
    return name, fans, fmt_search_rows(rows)


def cmd_space(client, args):
    """UP 投稿列表：space 接口优先（需小号），被风控自动降级搜索召回。"""
    mid = resolve_mid(args.target)
    if not mid:
        die("space 参数要 mid（纯数字）或 space.bilibili.com 链接")
    order = {"pubdate": "pubdate", "click": "click", "stow": "stow"}.get(args.order, "pubdate")
    try:
        rows = space_via_api(client, mid, order, args.pages)
    except SystemExit:
        rows = None
    if rows is not None:
        if not rows:
            print("该 UP 没拉到投稿（接口要求小号登录，跑 login 后重试）")
            return
        print(f"## UP（mid={mid}）投稿 {len(rows)} 条（按 {order} 排）\n")
    else:
        name, fans, rows = space_via_search(client, mid, args.pages)
        if not rows:
            print(f"UP「{name}」（粉丝 {fans}）：space 投稿接口被 B站风控拦截"
                  "（2026-10 实测连 yt-dlp 都过不去），搜索也召回不到其稿件——"
                  "用浏览器打开 space.bilibili.com/<mid>/video 读全量列表"
                  "（见 benchmark/SKILL.md 浏览器路线），或让用户直接贴视频链接")
            return
        print(f"## UP「{name}」（粉丝 {fans}）热门稿 {len(rows)} 条"
              "（space 接口被风控，此为搜索召回的近似列表，不全——"
              "全量列表用浏览器开 space.bilibili.com/<mid>/video 读，见 benchmark/SKILL.md）\n")
    print_rows(rows, [("BV", "bvid"), ("标题", "title"), ("播放", "play"),
                      ("藏", "favorite"), ("评", "review"), ("时长", "duration"),
                      ("发布", "pubdate")], args.json)


def fetch_view(client, target):
    """目标（BV/链接）→ 稿件详情。短链 b23.tv 先跟随跳转。"""
    bvid = extract_bvid(target)
    if not bvid and "b23.tv" in (target or ""):
        # 短链：跟随跳转拿最终地址
        req = urllib.request.Request(target if target.startswith("http") else f"https://{target}",
                                     headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as resp:
            bvid = extract_bvid(resp.geturl())
    if not bvid:
        die(f"认不出 BV 号：{target}（支持 BV 号 / 视频链接 / b23.tv 短链）")
    data = client.api("https://api.bilibili.com/x/web-interface/wbi/view",
                      {"bvid": bvid}, wbi=True)
    if not data:
        die(f"稿件不存在或已删除：{bvid}")
    return data


def cmd_view(client, args):
    data = fetch_view(client, args.target)
    stat = data.get("stat") or {}
    owner = data.get("owner") or {}
    rows = [{
        "bvid": data.get("bvid"), "aid": data.get("aid"), "cid": data.get("cid"),
        "title": data.get("title"), "UP": owner.get("name"), "mid": owner.get("mid"),
        "play": stat.get("view"), "like": stat.get("like"),
        "coin": stat.get("coin"), "favorite": stat.get("favorite"),
        "share": stat.get("share"), "reply": stat.get("reply"),
        "danmaku": stat.get("danmaku"),
        "duration": data.get("duration"),
        "pubdate": datetime.fromtimestamp(data.get("pubdate") or 0).strftime("%Y-%m-%d"),
        "分P数": data.get("videos"),
        "desc": (data.get("desc") or "")[:200],
    }]
    print_rows(rows, [("BV", "bvid"), ("标题", "title"), ("UP", "UP"),
                      ("播放", "play"), ("赞", "like"), ("投", "coin"),
                      ("藏", "favorite"), ("评", "reply"), ("时长", "duration"),
                      ("发布", "pubdate")], args.json)
    if args.json:
        return
    print(f"\n描述：{rows[0]['desc']}")
    print(f"分P：{rows[0]['分P数']}（cid={rows[0]['cid']}）")


def cmd_comments(client, args):
    """高赞评论（公开）：wbi/main 优先，失败退老接口 x/v2/reply。"""
    view = fetch_view(client, args.target)
    oid = view.get("aid")
    params = {"type": 1, "oid": oid, "mode": 3, "ps": min(args.n, 49), "next": 0}
    try:
        data = client.api("https://api.bilibili.com/x/v2/reply/wbi/main", params, wbi=True) or {}
    except SystemExit:
        data = client.api("https://api.bilibili.com/x/v2/reply",
                          {"type": 1, "oid": oid, "sort": 1, "ps": min(args.n, 49)}) or {}
    rows = parse_reply_main(data)[:args.n]
    print(f"## 《{view.get('title')}》高赞评论 {len(rows)} 条\n")
    print_rows(rows, [("赞", "like"), ("用户", "uname"), ("回复数", "reply_ct"),
                      ("内容", "message")], args.json)


def find_ytdlp():
    """yt-dlp 定位：环境变量 YT_DLP > PATH（bilibiliget 目录就在 PATH）> pip 模块。"""
    env = os.environ.get("YT_DLP")
    if env and Path(env).is_file():
        return [env]
    which = shutil.which("yt-dlp")
    if which:
        return [which]
    try:
        import importlib.util
        if importlib.util.find_spec("yt_dlp"):
            return [sys.executable, "-m", "yt_dlp"]
    except Exception:  # noqa: BLE001
        pass
    return None


def resolve_cookiefile(cfg, out_dir):
    """登录态 → Netscape cookie 文件（写进下载目录，随 .gitignore 挡出 git）。"""
    if not cfg.get("bench_sessdata"):
        return None
    client = Bili()  # 只为拿 buvid，和 yt-dlp 请求对齐，降低风控概率
    client.warm()
    pairs = [("SESSDATA", cfg["bench_sessdata"])]
    for c in client.jar:
        if c.name in ("buvid3", "buvid4", "b_nut"):
            pairs.append((c.name, c.value))
    path = out_dir / "_cookie.txt"
    path.write_text(netscape_lines(pairs), encoding="utf-8")
    return path


def pull_subs(client, view, out_dir):
    """AI 字幕 → (srt_path, md_path) 或 (None, 原因)。需小号登录。"""
    aid, cid, bvid = view.get("aid"), view.get("cid"), view.get("bvid")
    if not (aid and cid):
        return None, "详情缺 aid/cid"
    data = client.api("https://api.bilibili.com/x/player/wbi/v2",
                      {"aid": aid, "cid": cid, "bvid": bvid}, wbi=True) or {}
    subs = ((data.get("subtitle") or {}).get("subtitles")) or []
    if not subs:
        return None, "该视频没有 AI 字幕（UP 也没传 CC）——逐字稿走 cut 转录（asr_funasr.py）"
    pick = next((s for s in subs if str(s.get("lan", "")).startswith("ai-")), subs[0])
    url = pick.get("subtitle_url") or ""
    if url.startswith("//"):
        url = "https:" + url
    # 字幕 JSON 在 aisubtitle.hdslb.com，同样要登录态
    client.warm()
    body_payload = client._raw_json(url)
    body = body_payload.get("body") or []
    if not body:
        return None, "字幕 JSON 为空"
    out_dir.mkdir(parents=True, exist_ok=True)
    srt = out_dir / "逐字稿.srt"
    md = out_dir / "逐字稿.md"
    srt.write_text(srt_from_body(body), encoding="utf-8")
    md.write_text(
        f"# 逐字稿：《{view.get('title')}》\n\n"
        f"- 链接：https://www.bilibili.com/video/{bvid}\n"
        f"- 来源：B站 AI 字幕（{pick.get('lan_doc') or pick.get('lan')}），含识别误差，拆解时对照视频\n\n"
        + plain_from_body(body) + "\n", encoding="utf-8")
    return srt, md


def cmd_fetch(client, cfg, cfg_path, args):
    """一条龙：详情 → 信息.json → 视频+封面(yt-dlp) → AI 字幕逐字稿。"""
    view = fetch_view(client, args.target)
    bvid = view["bvid"]
    base = Path(args.dir) if args.dir else default_media_dir(cfg, cfg_path)
    out_dir = base / bvid
    out_dir.mkdir(parents=True, exist_ok=True)
    # 下载素材不进 git：视频几十上百 MB，vault 是 git 仓库时会炸
    gitignore = out_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n!.gitignore\n", encoding="utf-8")

    # 1. 元数据（拆解的事实底座）
    stat = view.get("stat") or {}
    info = {
        "bvid": bvid, "aid": view.get("aid"), "cid": view.get("cid"),
        "title": view.get("title"), "desc": view.get("desc"),
        "owner": view.get("owner"), "duration": view.get("duration"),
        "pubdate": view.get("pubdate"), "stat": {k: stat.get(k) for k in
                                                 ("view", "like", "coin", "favorite",
                                                  "share", "reply", "danmaku")},
        "pages": [{"cid": p.get("cid"), "part": p.get("part")}
                  for p in view.get("pages") or []],
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }
    info_path = out_dir / "信息.json"
    info_path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[fetch] 信息.json → {info_path}")

    # 2. 视频 + 封面（yt-dlp；登录 1080p，匿名 480p）
    got_video = None
    if not args.no_video:
        ytdlp = find_ytdlp()
        if not ytdlp:
            print("[fetch] 没找到 yt-dlp——跳过视频下载。装法：winget install yt-dlp"
                  " 或 python -m pip install yt-dlp，或把 yt-dlp.exe 放进 PATH", file=sys.stderr)
        else:
            cookie_file = resolve_cookiefile(cfg, out_dir)
            # 拆解看手法 720p 够用（花字/字幕/素材比例都看得清），1080p 体积大一个
            # 量级且实测易断流；匿名只能 480p
            height = 720 if cookie_file else 480
            cmd = ytdlp + [
                "-f", f"bv*[height<={height}][ext=mp4]+ba[ext=m4a]/b[height<={height}][ext=mp4]/bv*+ba/b",
                "--merge-output-format", "mp4",
                "-o", str(out_dir / "视频.%(ext)s"),
                "--write-thumbnail", "--no-playlist",
                "--socket-timeout", "60", "--retries", "10",
                "--fragment-retries", "10", "-N", "3",
                "--newline", "--no-warnings",
                f"https://www.bilibili.com/video/{bvid}",
            ]
            if cookie_file:
                cmd += ["--cookies", str(cookie_file)]
            else:
                cmd += ["--add-headers", "Referer: https://www.bilibili.com/"]
            print(f"[fetch] yt-dlp 下载中（≤{height}p，"
                  f"{'小号登录' if cookie_file else '匿名'}）…", file=sys.stderr)
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace")
            if proc.returncode == 0:
                # 合并产物可能是 视频.mp4（常见）或 视频.<格式id>.mp4（单流直下），优先前者
                hits = sorted(out_dir.glob("视频.mp4")) or \
                    [h for h in sorted(out_dir.glob("视频.*")) if h.suffix != ".part"]
                got_video = hits[0] if hits else None
                print(f"[fetch] 视频 → {got_video}" if got_video
                      else "[fetch] yt-dlp 返回 0 但没找到视频文件，检查下载目录", file=sys.stderr)
            else:
                print(f"[fetch] yt-dlp 失败（exit {proc.returncode}）：\n"
                      f"{(proc.stderr or '')[-800:]}", file=sys.stderr)

    # 3. AI 字幕逐字稿（失败不拦路，SKILL.md 有兜底路径）
    srt = md = None
    if client.sessdata:
        try:
            srt, md = pull_subs(client, view, out_dir)
        except SystemExit as exc:  # api() 的 die 会走这里，转普通提示
            print(f"[fetch] 字幕拉取失败：{exc}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            print(f"[fetch] 字幕拉取异常：{exc}", file=sys.stderr)
        if md:
            print(f"[fetch] 逐字稿 → {md}")
        elif srt is None and not args.json:
            print("[fetch] 无 AI 字幕——逐字稿用 cut 的转录："
                  "python skill/media/cut/scripts/asr_funasr.py <视频> （见 benchmark/SKILL.md）",
                  file=sys.stderr)

    print_rows([{
        "bvid": bvid, "标题": info["title"], "目录": str(out_dir),
        "视频": str(got_video) if got_video else ("--no-video" if args.no_video else "未下载"),
        "逐字稿": str(md) if md else "无（走 cut 转录）",
        "信息": str(info_path),
    }], [("BV", "bvid"), ("标题", "标题"), ("目录", "目录"), ("视频", "视频"),
         ("逐字稿", "逐字稿"), ("信息", "信息")], args.json, json_key="fetched")


def cmd_subs(client, cfg, cfg_path, args):
    view = fetch_view(client, args.target)
    base = Path(args.dir) if args.dir else default_media_dir(cfg, cfg_path)
    result = pull_subs(client, view, base / view["bvid"])
    if result[0] is None:
        die(result[1], code=3)
    print_rows([{"srt": str(result[0]), "md": str(result[1])}],
               [("srt", "srt"), ("md", "md")], args.json)


# ---------------------------------------------------------------- main

def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    ap = argparse.ArgumentParser(description="B站对标研究（公开接口+小号登录，个人学习用）")
    ap.add_argument("command", choices=["login", "search", "space", "view",
                                        "comments", "subs", "fetch"])
    ap.add_argument("target", nargs="?", help="BV号/链接（space 子命令为 mid/主页链接；search 为关键词）")
    ap.add_argument("--keyword", help="search：关键词（也可直接放在 target 位）")
    ap.add_argument("--config", help="_config_local.json 路径")
    ap.add_argument("--dir", help="subs/fetch：输出目录（默认 <对标>/_下载/<BV号>）")
    ap.add_argument("--pages", type=int, default=1, help="search/space：翻页数（默认 1）")
    ap.add_argument("--limit", type=int, default=0, help="search：最多返回条数（默认不限）")
    ap.add_argument("--n", type=int, default=30, help="comments：取前 N 条（默认 30）")
    ap.add_argument("--order", default="relevance",
                    help="search: relevance(默认)/click/pubdate；space: pubdate(默认)/click/stow")
    ap.add_argument("--no-video", action="store_true", help="fetch：不下视频，只要信息+逐字稿")
    ap.add_argument("--json", action="store_true", help="输出 JSON 而非 markdown 表")
    args = ap.parse_args()

    if args.command == "login":
        if not args.config:
            die("login 需要指定配置路径：--config 你的_config_local.json"
                "（文件不存在会自动创建，schema 见仓根 config.example.json）")
        path = Path(args.config)
        if path.is_file():
            cfg = json.loads(path.read_text(encoding="utf-8-sig"))
        else:
            # 自动建配置：从就近的 config.example.json 继承 schema（同 fetch_bili login）
            cfg = None
            for anc in [path.parent, *path.parents]:
                ex = anc / "config.example.json"
                if ex.is_file():
                    cfg = json.loads(ex.read_text(encoding="utf-8-sig"))
                    cfg["sessdata"] = ""
                    cfg["bench_sessdata"] = ""
                    break
            if cfg is None:
                cfg = {"sessdata": "", "bench_sessdata": ""}
            cfg.setdefault("vault_path", str(path.parents[2]) if len(path.parents) >= 3
                           else str(path.parent))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[login] 已生成配置骨架 → {path}")
        cmd_login(path, cfg)
        return

    if args.command == "search" and args.target and not args.keyword:
        args.keyword = args.target
    if args.command == "search" and not args.keyword:
        die('search 需要关键词：python bili_bench.py search "剪映教程"')
    if args.command != "search" and not args.target:
        die(f"{args.command} 需要 target（BV号/链接）")

    # search/view/comments/fetch 不强制配置（fetch 没配置就落 ./对标下载/）；
    # space/subs 必须有配置（要小号 bench_sessdata）
    config_optional = args.command in ("search", "view", "comments", "fetch")
    cfg_path = find_config(args.config, required=not config_optional)
    if cfg_path:
        cfg = load_config(cfg_path, need_session=args.command in ("space", "subs"))
    else:
        cfg = {}
    client = Bili(sessdata=cfg.get("bench_sessdata") or "")

    if args.command == "search":
        cmd_search(client, args)
    elif args.command == "space":
        cmd_space(client, args)
    elif args.command == "view":
        cmd_view(client, args)
    elif args.command == "comments":
        cmd_comments(client, args)
    elif args.command == "subs":
        cmd_subs(client, cfg, cfg_path, args)
    elif args.command == "fetch":
        cmd_fetch(client, cfg, cfg_path, args)


if __name__ == "__main__":
    main()
