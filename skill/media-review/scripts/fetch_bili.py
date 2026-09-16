#!/usr/bin/env python3
"""B站创作中心数据拉取——只取自己账号的数据。

接口文档：bilibili-API-collect docs/creativecenter/
鉴权：仅 Cookie（SESSDATA），全部 GET，无 wbi 签名。
注意：创作中心数据次日中午 12 点刷新，D+1 内的数据可能不全。

用法：
  python fetch_bili.py login --config PATH        # 扫码登录，SESSDATA 自动写配置（需 qrcode 库）
  python fetch_bili.py list                      # 投稿列表 + 观察点清算
  python fetch_bili.py diagnose [--size 50]      # 近 N 条视频诊断（完播/CTR/涨粉）
  python fetch_bili.py overview                  # 账号基线（粉丝数等）
  python fetch_bili.py playsource                # 播放来源占比（账号级）
  通用参数：--config PATH（默认自动找 vault 侧 _config_local.json）
           --out FILE（默认写 vault/20_自媒体/复盘/_data/，- 表示 stdout）
           --dry-run（只打印不写盘）
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path

# 发布后观察点（天）
OBSERVATION_DAYS = (3, 7, 30)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

API = {
    # 稿件列表（自己的投稿）：Archive{aid,bvid,title,ptime,ctime} + stat{view,like,...}
    "list": "https://member.bilibili.com/x2/creative/web/archives/sp",
    # 近 N 条视频诊断：full_play_ratio 完播比 / crash_rate 3秒退出率 /
    # tm_rate 封标点击率 / total_new_attention_cnt 涨粉（百分比字段 10000=100%）
    "diagnose": "https://member.bilibili.com/x/web/data/archive_diagnose/compare",
    # 账号总览：total_fans 粉丝基线 + 各类增量
    "overview": "https://member.bilibili.com/x/web/index/stat",
    # 播放来源占比（账号级）：page_source{推荐/搜索/动态/空间…} + play_proportion{平台}
    "playsource": "https://member.bilibili.com/x/web/data/playsource",
}

# 二维码登录（passport，免 Cookie）。文档：bilibili-API-collect docs/login/login_action/QR.md
QR_API = {
    "generate": "https://passport.bilibili.com/x/passport-login/web/qrcode/generate",
    "poll": "https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
}
QR_CODE_MSG = {86101: "等待扫码", 86090: "已扫码，请在手机上确认", 86038: "二维码已过期"}


def find_config(explicit=None):
    """定位 _config_local.json：显式路径 > 脚本各级上级目录（开发便利）。"""
    if explicit:
        p = Path(explicit)
        if not p.is_file():
            die(f"指定的配置不存在：{p}")
        return p
    here = Path(__file__).resolve()
    for parent in here.parents:  # skill/scripts/ -> skill/ -> 仓根 -> ...
        candidate = parent / "_config_local.json"
        if candidate.is_file():
            return candidate
    die("找不到 _config_local.json（含 sessdata）。"
        "把 vault 侧 20_自媒体/复盘/_config_local.example.json 复制为 _config_local.json 并填 Cookie，"
        "或用 --config 显式指定路径")


def load_config(path):
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if not cfg.get("sessdata"):
        die(f"{path} 里 sessdata 为空")
    return cfg


def vault_root(cfg, config_path):
    """vault 根目录：显式配置优先，否则从配置文件位置推断
    （配置位于 <vault>/20_自媒体/复盘/_config_local.json → parents[2] 即 vault 根）。"""
    vp = cfg.get("vault_path")
    if vp:
        return Path(vp)
    return config_path.parents[2]


def die(msg, code=1):
    print(f"[fetch_bili] 错误：{msg}", file=sys.stderr)
    sys.exit(code)


def http_get(url, params=None, sessdata=None, timeout=15):
    """底层 GET。返回 (json负载, 响应头)。Referer 必须带，否则部分接口拒绝。"""
    qs = urllib.parse.urlencode(params) if params else ""
    full = f"{url}?{qs}" if qs else url
    headers = {"User-Agent": UA, "Referer": "https://member.bilibili.com/"}
    if sessdata:
        headers["Cookie"] = f"SESSDATA={sessdata}"
    req = urllib.request.Request(full, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
        return payload, resp.headers


def api_get(url, params, sessdata, timeout=15):
    """创作中心 GET，校验业务 code。"""
    payload, _ = http_get(url, params, sessdata, timeout)
    # 通用返回结构：code 0 成功 / -101 未登录（Cookie 失效）
    if payload.get("code") == -101:
        die("Cookie 失效（code -101）——重跑 login 子命令扫码刷新，"
            "或去 B站网页 F12 手动复制 SESSDATA 更新 _config_local.json")
    if payload.get("code") != 0:
        die(f"接口返回异常 code={payload.get('code')} message={payload.get('message')}")
    return payload.get("data")


# ---------------------------------------------------------------- list

def parse_archives(data):
    """从 archives/sp 接口响应提取投稿摘要（纯函数，可测）。"""
    out = []
    for a in data.get("arc_audits") or []:
        arc = a.get("Archive") or {}
        stat = a.get("stat") or {}
        out.append({
            "aid": arc.get("aid"),
            "bvid": arc.get("bvid"),
            "title": arc.get("title"),
            # ptime 实际发布时间（定时发布场景），空则回退 ctime
            "pubtime": arc.get("ptime") or arc.get("ctime"),
            "stat": {k: stat.get(k) for k in
                     ("view", "like", "coin", "favorite", "share", "reply", "danmaku")},
        })
    return out


def fetch_all_archives(sessdata, page_size=100, max_pages=20):
    """分页拉全部投稿。"""
    out, pn = [], 1
    while pn <= max_pages:
        data = api_get(API["list"], {"pn": pn, "ps": page_size}, sessdata)
        page_items = parse_archives(data)
        out += page_items
        total = (data.get("page") or {}).get("count", 0)
        if pn * page_size >= total or not page_items:
            break
        pn += 1
    return out


def compute_watchpoints(archives, today=None):
    """每个视频今天已到期的观察点列表。到期判定：age >= D。"""
    today = today or date.today()
    result = []
    for arc in archives:
        pub = arc.get("pubtime")
        if not pub:
            continue
        pubdate = date.fromtimestamp(pub)
        age = (today - pubdate).days
        due = [d for d in OBSERVATION_DAYS if age >= d]
        if due:
            result.append({**arc, "age_days": age, "due_points": due})
    result.sort(key=lambda x: x["pubtime"])
    return result


# ---------------------------------------------------------------- diagnose / overview

def convert_rates(items):
    """诊断接口的比率字段原始值 10000=100%，统一换算为小数（纯函数，可测）。
    比率字段后缀 _rate（tm_rate/crash_rate…）或 _ratio（full_play_ratio），
    逐项判断——不同视频返回的字段不齐。"""
    for item in items or []:
        for k, v in item.items():
            if k.endswith(("_rate", "_ratio")) and isinstance(v, (int, float)):
                item[k] = round(v / 10000, 4)
    return items or []


def fetch_diagnose(sessdata, size=50):
    """近 size 条视频的诊断数据（完播/退出率/CTR/涨粉）。"""
    data = api_get(API["diagnose"], {"size": size}, sessdata)
    return convert_rates(data.get("list") or [])


def fetch_overview(sessdata):
    """账号基线：total_fans 粉丝、total_click 总播放等。"""
    return api_get(API["overview"], None, sessdata) or {}


def fetch_playsource(sessdata):
    """播放来源占比（账号级，单视频无此粒度，复盘时作参考）。"""
    return api_get(API["playsource"], None, sessdata) or {}


# ---------------------------------------------------------------- login（扫码）

def _show_qr(url, cfg_path):
    """展示登录二维码：优先存 PNG 并自动打开（GBK 终端渲染块字符会花，
    图片查看器万无一失）；Pillow 不可用时回退终端 ASCII（UTF-8 终端才行）。"""
    import qrcode
    qr = qrcode.QRCode(border=2)
    qr.add_data(url)
    qr.make(fit=True)
    try:
        img = qr.make_image()
        path = cfg_path.parent / "_login_qr.png"
        img.save(path)
        os.startfile(path)  # Windows 默认图片查看器
        print(f"[login] 二维码已弹出（{path}），登录成功后此图自动删除", file=sys.stderr)
        return path
    except Exception as exc:  # noqa: BLE001——任何渲染失败都走 ASCII 回退
        print(f"[login] 图片渲染失败（{exc}），回退终端二维码（需 UTF-8 终端）", file=sys.stderr)
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        qr.print_ascii(invert=True)
        return None


def cmd_login(cfg_path, cfg):
    """B站二维码登录：弹码 → 手机 App 扫码确认 → SESSDATA 自动写回配置。"""
    try:
        import qrcode  # noqa: F401——提前 fail-fast 提示装依赖
    except ImportError:
        die("login 需要 qrcode 库（仅此命令用）：python -m pip install qrcode")

    gen, _ = http_get(QR_API["generate"])
    if gen.get("code") != 0:
        die(f"二维码生成失败 code={gen.get('code')}")
    qrcode_key = gen["data"]["qrcode_key"]
    qr_image = _show_qr(gen["data"]["url"], cfg_path)
    print("↑ 用 B站 App（扫一扫）扫码登录，180 秒内有效...", file=sys.stderr)

    deadline = time.time() + 180
    last_code = None
    while time.time() < deadline:
        time.sleep(2)
        payload, headers = http_get(QR_API["poll"], {"qrcode_key": qrcode_key})
        code = (payload.get("data") or {}).get("code")
        if code != last_code and code in QR_CODE_MSG:
            print(f"[login] {QR_CODE_MSG[code]}", file=sys.stderr)
            last_code = code
        if code == 86038:
            die("二维码过期——重跑 login")
        if code == 0:
            # 登录成功，cookie 在 Set-Cookie 响应头里
            sessdata = None
            for header in headers.get_all("Set-Cookie") or []:
                for part in header.split(";"):
                    if part.strip().startswith("SESSDATA="):
                        sessdata = part.strip().split("=", 1)[1]
                        break
                if sessdata:
                    break
            if qr_image and qr_image.is_file():
                qr_image.unlink()  # 用完即删，不留登录凭据图
            if not sessdata:
                die("登录成功但响应里没拿到 SESSDATA——请改用手动 F12 复制")
            cfg["sessdata"] = sessdata
            cfg_path.write_text(
                json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"[login] OK——SESSDATA 已写入 {cfg_path}", file=sys.stderr)
            return
    if qr_image and qr_image.is_file():
        qr_image.unlink()
    die("超时未确认——重跑 login")


# ---------------------------------------------------------------- 输出

def emit(payload, out, data_dir, dry=False):
    """写 JSON：--out - 打 stdout，否则写 data_dir/<out>.json。"""
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if out == "-":
        print(text)
        return
    target = data_dir / out
    if dry:
        print(f"[dry-run] 本应写入 {target}：\n{text[:800]}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    print(f"[fetch_bili] 已写入 {target}")


def main():
    ap = argparse.ArgumentParser(description="B站创作中心数据拉取（仅自己账号）")
    ap.add_argument("command", choices=["list", "diagnose", "overview", "playsource", "login"])
    ap.add_argument("--config", help="_config_local.json 路径")
    ap.add_argument("--out", default=None, help="输出文件名（默认 <命令>_YYYYMMDD.json，- 为 stdout）")
    ap.add_argument("--size", type=int, default=50, help="diagnose 拉最近 N 条（默认 50）")
    ap.add_argument("--dry-run", action="store_true", help="不写盘")
    args = ap.parse_args()

    if args.command == "login":
        # login 不要求配置已存在：新建或更新 sessdata 字段
        if not args.config:
            die("login 需要指定配置路径：--config <vault>/20_自媒体/复盘/_config_local.json"
                "（文件不存在会自动创建）")
        path = Path(args.config)
        cfg = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"vault_path": str(path.parents[2])}
        cmd_login(path, cfg)
        return

    cfg_path = find_config(args.config)
    cfg = load_config(cfg_path)
    data_dir = vault_root(cfg, cfg_path) / "20_自媒体" / "复盘" / "_data"
    out = args.out or f"{args.command}_{date.today():%Y%m%d}.json"

    if args.command == "list":
        archives = fetch_all_archives(cfg["sessdata"])
        payload = {
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
            "total": len(archives),
            "archives": archives,
            "due_watchpoints": compute_watchpoints(archives),
        }
        print(f"[fetch_bili] 共 {len(archives)} 条投稿，"
              f"今日到期观察点 {len(payload['due_watchpoints'])} 条", file=sys.stderr)
    elif args.command == "diagnose":
        payload = {"fetched_at": datetime.now().isoformat(timespec="seconds"),
                   "list": fetch_diagnose(cfg["sessdata"], args.size)}
        print(f"[fetch_bili] 诊断数据 {len(payload['list'])} 条", file=sys.stderr)
    elif args.command == "playsource":
        payload = {"fetched_at": datetime.now().isoformat(timespec="seconds"),
                   "playsource": fetch_playsource(cfg["sessdata"])}
    else:
        payload = {"fetched_at": datetime.now().isoformat(timespec="seconds"),
                   "overview": fetch_overview(cfg["sessdata"])}

    emit(payload, out, data_dir, args.dry_run)


if __name__ == "__main__":
    main()
