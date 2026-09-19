#!/usr/bin/env python3
"""依赖环境核验 + 结果缓存——首跑全查写缓存，之后秒过（不重复验）。

痛点（2026-09-20 用户反馈）：每期剪辑前置"验依赖"要 ~6 分钟——大头是 torch 级包
（funasr/torch）import 慢 + 逐个试装。实际上依赖装好就是装好了，没必要每期重验。

两档路径：
  快路径：读本目录 _env_verified.json 缓存（<30 天且 ffmpeg 还在）→ 秒回，
          全程不 import 任何重库
  慢路径（首跑 / --force / 缓存过期 / ffmpeg 换位）：用 importlib.metadata 查版本
          （元数据表查询，**不触发 torch/funasr import**，全程几秒），
          ffmpeg 试跑 -version，模型缓存清点，剪映草稿根确认，写回缓存

用法：
  python env_check.py            # 有新鲜缓存秒过；没有/过期才全查
  python env_check.py --force    # 强制全查并刷新缓存（装了新包/换了环境后用）
  python env_check.py --check    # 只报告当前状态，不写缓存

缓存落在技能安装目录（_env_verified.json）——仓库里这份不进 git（机器状态）。
"""
import argparse
import json
import sys
import time
from importlib import metadata
from pathlib import Path

CACHE = Path(__file__).with_name("_env_verified.json")
TTL_DAYS = 30

# 必需 pip 包：名字=importlib.metadata 可查的发行名（import 名不同没关系，
# 元数据查询不触发 import，避开 torch 加载的分钟级开销）
REQUIRED_PKGS = {
    "funasr": "转录（第②层）",
    "torch": "funasr 底层",
    "pyJianYingDraft": "剪映草稿直出（第③层）",
}
OPTIONAL_PKGS = {
    "imageio-ffmpeg": "ffmpeg 兜底二进制（PATH 里已有 ffmpeg 则不需要）",
}


def full_check(write_cache: bool):
    """全量核验（秒级，无重 import）。返回 (ok, manifest)。"""
    problems = []
    manifest = {
        "verified_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "verified_ts": time.time(),
        "python": sys.version.split()[0],
        "packages": {},
        "optional": {},
        "models": [],
    }

    # pip 包版本：纯元数据查询
    for name, why in REQUIRED_PKGS.items():
        try:
            v = metadata.version(name)
            manifest["packages"][name] = v
            print(f"  [ok] {name} {v}（{why}）")
        except metadata.PackageNotFoundError:
            problems.append(f"{name}（{why}）→ pip install {name}")
            print(f"  [缺] {name}（{why}）")
    for name, why in OPTIONAL_PKGS.items():
        try:
            manifest["optional"][name] = metadata.version(name)
            print(f"  [ok] {name} {manifest['optional'][name]}（{why}，可选）")
        except metadata.PackageNotFoundError:
            print(f"  [--] {name} 未装（{why}）")

    # ffmpeg：能跑 -version 才算数（find_ffmpeg 覆盖 PATH + imageio 兜底）
    from silence_trim import FFMPEG
    import subprocess
    try:
        p = subprocess.run([FFMPEG, "-version"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=20)
        ok = p.returncode == 0
    except Exception:
        ok = False
    if ok:
        manifest["ffmpeg"] = str(FFMPEG)
        print(f"  [ok] ffmpeg → {FFMPEG}")
    else:
        problems.append("ffmpeg 跑不起来 → winget install ffmpeg 或 pip install imageio-ffmpeg")
        print("  [缺] ffmpeg 跑不起来")

    # FunASR 模型缓存清点（~1.2G，首跑转录时才下载；这里只记录有没有，缺了不报错）
    ms_cache = Path.home() / ".cache" / "modelscope" / "models"
    if ms_cache.exists():
        hits = sorted({d.name.split("--")[-1][:40] for d in ms_cache.iterdir()
                       if d.is_dir() and any(k in d.name.lower() for k in
                       ("paraformer", "fsmn", "punc", "vad"))})
        manifest["models"] = hits
        if hits:
            print(f"  [ok] 模型缓存 {len(hits)} 个（无需重下）")
        else:
            print("  [--] 模型缓存空——首次转录会下载 ~1.2G（ModelScope 国内 CDN，关 VPN）")
    else:
        print("  [--] 模型缓存空——首次转录会下载 ~1.2G（ModelScope 国内 CDN，关 VPN）")

    # 剪映草稿根：存在才记录（jy_draft 自己还会解析状态文件，这里只给个底）
    draft_root = Path.home() / "AppData/Local/JianyingPro/User Data/Projects/com.lveditor.draft"
    manifest["draft_root_default_exists"] = draft_root.exists()
    print(f"  [{'ok' if draft_root.exists() else '--'}] 剪映默认草稿根"
          f"{'存在' if draft_root.exists() else '不存在（用户改过位置属正常，jy_draft 会自己记）'}")

    if write_cache and not problems:
        CACHE.write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                         encoding="utf-8")
        print(f"[env_check] 核验通过，缓存已写 → {CACHE.name}"
              f"（{TTL_DAYS} 天内直接秒过）")
    elif write_cache:
        print("[env_check] 有缺失项，不写缓存；缺什么装什么后再跑")
    return (not problems), manifest


def fast_path():
    """缓存快路径。返回 True=缓存可用（已打印摘要）；False=需走全查。"""
    if not CACHE.exists():
        return False
    try:
        m = json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:
        return False
    age_days = (time.time() - m.get("verified_ts", 0)) / 86400
    if age_days > TTL_DAYS:
        print(f"[env_check] 缓存已 {age_days:.0f} 天（>{TTL_DAYS}），重新全查")
        return False
    ff = m.get("ffmpeg", "")
    if not ff or not Path(ff).exists():  # ffmpeg 被卸载/挪动是最常见的失效
        print("[env_check] 缓存里的 ffmpeg 已不在，重新全查")
        return False
    print(f"[env_check] 依赖已核验过（{m['verified_at']}，缓存 {age_days:.0f} 天前），跳过——"
          f"python {m['python']}、{len(m['packages'])} 个包、ffmpeg 就位、"
          f"模型缓存 {len(m.get('models', []))} 个")
    print(f"[env_check] 环境有变动时用 --force 刷新（本缓存：{CACHE}）")
    return True


def main():
    ap = argparse.ArgumentParser(description="依赖核验 + 缓存（首跑全查，之后秒过）")
    ap.add_argument("--force", action="store_true", help="忽略缓存强制全查并刷新")
    ap.add_argument("--check", action="store_true", help="只报告，不写缓存")
    args = ap.parse_args()

    if not args.force and not args.check and fast_path():
        return
    print(f"[env_check] 全查中（几秒，不 import 重库）...")
    ok, _ = full_check(write_cache=not args.check)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
