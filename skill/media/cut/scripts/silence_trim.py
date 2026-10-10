#!/usr/bin/env python3
"""静音废段自动压缩——口播素材的第一层粗剪（零依赖，仅需 ffmpeg）。

原理：检测无人声段，视频/音频同步剪掉（保留短停顿，只砍"长冷场"）。
输出压缩版视频 + 切割报告。

无人声判定分两档（detect_silences 的 db 参数）：
  db=None（缺省，智能模式）：FSMN-VAD 人声岛补集挖洞——神经 VAD 分"是不是人声"，
    底噪/键盘/系统音再响也不算人声（实测 R02：40min 底噪素材，ASR 把 7.5min 噪声
    并成一条、能量阈值 -35dB 又被瞬时毛刺打破，成片残留 2min 噪声洞；VAD 全兜住）。
  db 给定（如 -35）：纯能量模式，silencedetect 瞬时电平阈值（旧行为）。

用法：
  python silence_trim.py 素材.mp4                    # 输出 素材_trimmed.mp4
  python silence_trim.py 素材.mp4 -o out.mp4
  参数：
    --db -35        静音判定阈值 dB；缺省走智能模式（VAD），给定则纯能量
    --min 2.0       连续无人声超过 N 秒才剪（保留自然停顿，默认 2 秒）
    --pad 0.3       每段两头各保留 N 秒缓冲，避免切字
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


def find_ffmpeg():
    """PATH 优先，其次 imageio_ffmpeg 自带的二进制（剪辑机器常见）。"""
    p = shutil.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        sys.exit("找不到 ffmpeg：装一个（winget install ffmpeg）"
                 "或 pip install imageio-ffmpeg")


FFMPEG = find_ffmpeg()

# 智能模式不可用（无 funasr / VAD 失败）时的能量兜底阈值——比旧默认 -35 高一档，
# 底噪素材 -35 会被瞬时毛刺（峰值 -29dB 的鼠标/碰撞声）不断打断静音连续段
VAD_FALLBACK_DB = -30

_VAD_MODEL = None  # fsmn-vad 句柄，进程内复用（模型加载 10s 级）


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        print(p.stderr[-2000:], file=sys.stderr)
        sys.exit(f"命令失败：{' '.join(cmd[:4])}...")
    return p.stderr  # silencedetect 的输出在 stderr


def detect_speech(video, use_cache=True):
    """FSMN-VAD 人声岛 [(start, end)] 秒；funasr 不可用或 VAD 失败返回 None。

    结果按 文件+mtime 缓存到 <stem>.vad.json——jy_draft/srt_cut/qa_backfill 对同一
    素材反复检测（实测 40min 文件 抽 wav+VAD 约 1.5min），缓存后全场复用。
    人声岛是"是不是人声"的判定，底噪/键盘/系统音再响也不算——能量阈值分不开的
    噪声段（R02 实测 7.5min 噪声被 ASR 并成一条、-35dB 被瞬时毛刺打破）由它兜住。
    """
    video = Path(video)
    cache = video.with_name(f"{video.stem}.vad.json")
    if use_cache and cache.exists():
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if (data.get("mtime") == video.stat().st_mtime
                    and isinstance(data.get("speech"), list)):
                return [(s, e) for s, e in data["speech"]]
        except Exception:
            pass
    global _VAD_MODEL
    try:
        from funasr import AutoModel  # torch 级重依赖，缺了走能量兜底不炸
    except ImportError:
        return None
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / (video.stem + "_16k.wav")
        run([FFMPEG, "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
             str(wav)])
        try:
            if _VAD_MODEL is None:
                print("[silence_trim] FSMN-VAD 人声检测中（首跑加载模型）...")
                _VAD_MODEL = AutoModel(model="fsmn-vad", disable_update=True)
            res = _VAD_MODEL.generate(input=str(wav), batch_size_s=300)
        except Exception as e:
            print(f"[silence_trim] 警告：VAD 失败（{e}），回退能量阈值 "
                  f"{VAD_FALLBACK_DB}dB", file=sys.stderr)
            return None
    speech = [[round(a / 1000, 3), round(b / 1000, 3)]
              for a, b in (res[0].get("value") or [])]
    if use_cache:
        try:
            cache.write_text(json.dumps(
                {"mtime": video.stat().st_mtime, "speech": speech},
                ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
    return [(s, e) for s, e in speech]


def holes_from_speech(speech, dur, pad=0.25, min_s=0.8):
    """人声岛补集 → 可挖无人声洞 [(start, end)] 秒。

    岛两侧各留 pad 缓冲防切字；补集段不足 min_s 的不挖（保留自然停顿）。
    """
    holes = []
    cur = 0.0
    for s, e in speech:
        s2, e2 = max(0.0, s - pad), min(dur, e + pad)
        if s2 - cur >= min_s:
            holes.append((cur, s2))
        cur = max(cur, e2)
    if dur - cur >= min_s:
        holes.append((cur, dur))
    return holes


def detect_silences(video, db=None, min_s=2.0, use_cache=True):
    """返回 [(start, end)] 无人声段列表（秒）。

    db=None 智能模式：VAD 人声岛补集（min_s 同样生效），底噪/系统音不算人声。
    db 给定：纯能量模式（旧行为，silencedetect 瞬时电平阈值）；VAD 不可用
      （无 funasr / 检测失败）时智能模式也回退此路（阈值取 VAD_FALLBACK_DB）。

    结果按 文件+参数+视频mtime 缓存到 <stem>.silence.json——jy_draft/srt_cut/
    qa_backfill 对同一素材反复检测（实测 40min 文件 30-60s/次），缓存后全场复用。
    """
    video = Path(video)
    dur = duration_of(video)
    vad_holes = None
    if db is None:
        speech = detect_speech(video, use_cache)
        if speech is not None:
            vad_holes = holes_from_speech(speech, dur, pad=0.25, min_s=min_s)
            if not vad_holes:
                return [], dur  # 全程人声，无洞可挖
        else:
            db = VAD_FALLBACK_DB  # VAD 不可用，能量兜底
    cache = video.with_name(f"{video.stem}.silence.json")
    energy = None
    cache_hit = db is not None and use_cache and cache.exists()
    if cache_hit:
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if (data.get("db") == db and data.get("min") == min_s
                    and data.get("mtime") == video.stat().st_mtime
                    and isinstance(data.get("cut"), list)):
                energy = [(s, e) for s, e in data["cut"]]
        except Exception:
            pass
    if energy is None and db is not None:
        out = run([FFMPEG, "-i", str(video), "-af",
                   f"silencedetect=noise={db}dB:d={min_s}", "-f", "null", "-"])
        starts = [float(m) for m in re.findall(r"silence_start:\s*([\d.]+)", out)]
        ends = [float(m) for m in re.findall(r"silence_end:\s*([\d.]+)", out)]
        # silence_start/end 成对出现；末尾可能缺 end（素材以静音结束）→ 用时长补
        if len(ends) < len(starts):
            ends.append(dur)
        energy = list(zip(starts, ends))
        if use_cache:
            try:
                cache.write_text(json.dumps(
                    {"db": db, "min": min_s, "mtime": video.stat().st_mtime,
                     "dur": dur, "cut": [[s, e] for s, e in energy]},
                    ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
    if vad_holes is None:
        return energy, dur
    return vad_holes, dur  # 智能模式：VAD 命中即拍板，不再跑能量扫描


def duration_of(video):
    """不依赖 ffprobe：解析 ffmpeg -i 的 Duration 行。"""
    p = subprocess.run([FFMPEG, "-i", video], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", p.stderr)
    if not m:
        sys.exit("读不到视频时长——文件损坏或不是媒体文件")
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def fmt(t):
    m, s = divmod(int(t), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def build_filter(silences, dur, pad):
    """删除静音段：视频 select 与音频 aselect 用同一条件，保证音画同步。
    返回 (vf, af, 砍掉总秒数)。"""
    spans = []
    for s, e in silences:
        s, e = max(0, s + pad), min(dur, e - pad)
        if e - s <= 0.2:  # 加 pad 后没剩多少，不砍
            continue
        if spans and s <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], e))
        else:
            spans.append((s, e))
    if not spans:
        return None, None, 0.0

    removed = sum(e - s for s, e in spans)
    conds = "+".join(f"between(t,{s:.2f},{e:.2f})" for s, e in spans)
    vf = f"select='not({conds})',setpts=N/FRAME_RATE/TB"
    af = f"aselect='not({conds})',asetpts=N/SR/TB"
    return vf, af, removed


def main():
    ap = argparse.ArgumentParser(description="静音废段自动压缩")
    ap.add_argument("video")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--db", type=float, default=None,
                    help="静音判定阈值 dB；缺省智能模式（FSMN-VAD 人声检测），"
                         "给定则纯能量模式")
    ap.add_argument("--min", type=float, default=2.0, dest="min_s")
    ap.add_argument("--pad", type=float, default=0.3)
    args = ap.parse_args()

    video = Path(args.video)
    out = Path(args.out) if args.out else \
        video.with_name(f"{video.stem}_trimmed{video.suffix}")

    silences, dur = detect_silences(video, args.db, args.min_s)
    if not silences:
        print("没有检测到超过阈值的无人声段，无需压缩")
        return
    vf, af, removed = build_filter(silences, dur, args.pad)
    if not vf:
        print("静音段加缓冲后已无可砍内容")
        return

    cmd = [FFMPEG, "-y", "-i", str(video),
           "-vf", vf, "-af", af,
           "-c:v", "libx264", "-preset", "fast", "-crf", "20",
           "-c:a", "aac", "-b:a", "160k", str(out)]
    print(f"[silence_trim] {fmt(dur)} 的素材，检测到 {len(silences)} 段静音，"
          f"共 {fmt(removed)}——处理中（重编码，挂机等）...")
    run(cmd)

    kept = dur - removed
    print(f"[silence_trim] 完成 → {out}")
    print(f"  原始 {fmt(dur)} → 压缩后约 {fmt(kept)}（砍掉 {removed/dur:.0%}）")
    # 停顿落盘：被砍区间是"重录分隔符"，下游靠它配重录对（BUG_重录对误删）
    import json as _json
    spans_kept = []
    cur = 0.0
    for s, e in silences:
        if s > cur:
            spans_kept.append([round(cur, 3), round(s, 3)])
        cur = max(cur, e)
    if dur > cur:
        spans_kept.append([round(cur, 3), round(dur, 3)])
    sil = video.with_name(f"{video.stem}.silence.json")
    sil.write_text(_json.dumps(
        {"cut": [[round(s, 3), round(e, 3)] for s, e in silences],
         "kept": spans_kept}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  停顿记录 → {sil.name}（cut=被砍冷场 kept=保留段，供重录对配对）")
    print("  下一步：asr_funasr.py 转录 → AI 初选删行 → srt_cut.py 剪出粗片")


if __name__ == "__main__":
    main()
