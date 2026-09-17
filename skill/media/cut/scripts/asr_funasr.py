#!/usr/bin/env python3
"""FunASR 转录——第②层"文本粗剪"的转录端（Paraformer 中文，热词可加，产出 SRT）。

模型从 ModelScope（国内 CDN）拉取。网络要点：**下载模型关 VPN 直连**（快 10 倍+），
`pip install funasr` 时才需要开 VPN。首跑共下载 ~1.2G（ASR 主模型 990M + VAD + 标点），
之后走本地缓存。CPU 几分钟出稿（Paraformer 非自回归架构，CPU 亲和，无需 GPU）。

用法：
  python asr_funasr.py 素材.mp4                    # 输出 素材.srt（视频自动抽 16k 音轨）
  python asr_funasr.py 音频.wav -o out.srt
  python asr_funasr.py 素材.mp4 --hotword "ESP32 乐鑫 IDF CubeMX"
"""

import argparse
import re
import tempfile
from pathlib import Path

from silence_trim import FFMPEG, run  # 同目录，复用 ffmpeg 通道

TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
PUNCT_SKIP = "，。？！；：、,"


def build_entries(text, ts):
    """字级时间戳 → 标点分句条目 [(start_ms, end_ms, 句子)]。

    对齐规则（实测 funasr 1.4.x）：标点/空白不占时间戳；连续英数串
    （Hello/ESP32/LED 是一个 token）只占 1 个时间戳，汉字一字一个。
    分句在 。？！；， 处断开——条目粒度到从句，"删句子=剪视频"更好使。
    对不上（别的版本行为变了）→ 按字符比例兜底，并打警告。
    """
    toks = []  # (char_i, char_j, [s,e])
    i = k = 0
    while i < len(text):
        if text[i] in PUNCT_SKIP or text[i].isspace():
            i += 1
            continue
        m = TOKEN_RE.match(text, i)
        if m:
            toks.append((m.start(), m.end(), ts[k]))
            i = m.end()
        else:
            toks.append((i, i + 1, ts[k]))
            i += 1
        k += 1

    if k != len(ts):
        print(f"[asr_funasr] 警告：字符/时间戳对不上（{k} vs {len(ts)}），按比例兜底")
        spans = re.split(r"([。？！；，])", text)
        sents, buf = [], ""
        for seg in spans:
            buf += seg
            if seg in "。？！；，" or seg == "":
                s = buf.strip()
                if s:
                    sents.append(s)
                buf = ""
        total_a, total_b = ts[0][0], ts[-1][1]
        n_chars = sum(len(s) for s in sents) or 1
        out, acc = [], 0
        for s in sents:
            a = total_a + (total_b - total_a) * acc / n_chars
            acc += len(s)
            b = total_a + (total_b - total_a) * acc / n_chars
            out.append((a, b, s))
        return out

    entries = []
    cur = []  # 当前句的 token 列表
    for idx, (ci, cj, t) in enumerate(toks):
        cur.append((ci, cj, t))
        nxt = toks[idx + 1] if idx + 1 < len(toks) else None
        if nxt is None:
            end_text = cj
        else:
            end_text = nxt[0]  # 句子连着后面的标点一起收，字幕更像话
            if any(p in "。？！；，" for p in text[cj:nxt[0]]):
                entries.append((cur[0][2][0], cur[-1][2][1],
                                text[cur[0][0]:end_text].strip()))
                cur = []
                continue
        if nxt is None and cur:
            entries.append((cur[0][2][0], cur[-1][2][1],
                            text[cur[0][0]:end_text].strip()))
    return entries


def extract_wav(media: Path, tmpdir: str) -> Path:
    """视频抽 16k 单声道 wav（Paraformer 的输入格式）；已是 wav 则直通。"""
    if media.suffix.lower() == ".wav":
        return media
    wav = Path(tmpdir) / (media.stem + "_16k.wav")
    run([FFMPEG, "-y", "-i", str(media), "-vn", "-ac", "1", "-ar", "16000", str(wav)])
    return wav


def fmt_ts(ms) -> str:
    h, rem = divmod(int(ms), 3600000)
    m, rem = divmod(rem, 60000)
    s, ms2 = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms2:03d}"


def main():
    ap = argparse.ArgumentParser(description="FunASR 转录出 SRT（Paraformer + VAD + 标点）")
    ap.add_argument("media")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--hotword", default="", help="热词，空格分隔（技术词塞这里准确率立涨）")
    args = ap.parse_args()

    media = Path(args.media)
    out = Path(args.out) if args.out else media.with_name(f"{media.stem}.srt")

    from funasr import AutoModel  # torch 级重依赖，参数解析后再 import
    model = AutoModel(model="paraformer-zh", vad_model="fsmn-vad",
                      punc_model="ct-punc-c", disable_update=True)

    with tempfile.TemporaryDirectory() as td:
        wav = extract_wav(media, td)
        kw = {"input": str(wav), "batch_size_s": 300}
        if args.hotword:
            kw["hotword"] = args.hotword
        res = model.generate(**kw)

    r = res[0]
    # funasr 1.4.x 无 sentence_info：用字级 timestamp 自行分句对齐
    if r.get("sentence_info"):
        sents = [(s["start"], s["end"], s["text"].strip())
                 for s in r["sentence_info"]]
    elif r.get("timestamp"):
        sents = build_entries(r["text"], r["timestamp"])
    else:
        sents = [(0, 0, r.get("text", ""))]
    with open(out, "w", encoding="utf-8") as f:
        for i, (a, b, txt) in enumerate(sents, 1):
            f.write(f"{i}\n{fmt_ts(a)} --> {fmt_ts(b)}\n{txt}\n\n")
    print(f"[asr_funasr] {len(sents)} 句 → {out}")
    for a, b, txt in sents:
        print(f"[{fmt_ts(a)[3:8]}] {txt}")


if __name__ == "__main__":
    main()
