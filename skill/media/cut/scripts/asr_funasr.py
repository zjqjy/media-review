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
import json
import re
import tempfile
from difflib import SequenceMatcher
from pathlib import Path

from silence_trim import FFMPEG, run  # 同目录，复用 ffmpeg 通道

TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
CJK_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
PUNCT_SKIP = "，。？！；：、,"


def _token_spans(text):
    """占时间戳的字符区段：汉字一字一段；连续英数串一段；其余（标点/符号/空白）不占。"""
    spans = []
    i = 0
    while i < len(text):
        m = TOKEN_RE.match(text, i)
        if m:
            spans.append((m.start(), m.end()))
            i = m.end()
            continue
        if CJK_RE.match(text, i):
            spans.append((i, i + 1))
        i += 1
    return spans


def build_entries(text, ts, fillers=()):
    """字级时间戳 → 标点分句条目 [(start_ms, end_ms, 句子)] + 口头禅洞 cuts。

    fillers 里的句首口头禅（如"然后"）不进句子，而是记成洞
    [{"start":ms,"end":ms,"word":词}]，剪切时从音频里精确抠掉（词级跳剪）。
    数目对不上 → 按比例兜底（此时出不了洞，口头禅留在句子里）。
    """
    cuts = []
    spans = _token_spans(text)
    if len(spans) != len(ts):
        odd = sorted({c for c in text
                      if not (CJK_RE.match(c) or TOKEN_RE.fullmatch(c)
                              or c.isspace() or c in PUNCT_SKIP)})
        print(f"[asr_funasr] 警告：token {len(spans)} ≠ 时间戳 {len(ts)}，"
              f"按比例兜底；可疑字符：{''.join(odd)[:50]}")
        sents = []
        buf = ""
        for seg in re.split(r"([。？！；，])", text):
            buf += seg
            if seg in "。？！；，" or seg == "":
                if buf.strip():
                    sents.append(buf.strip())
                buf = ""
        total_a, total_b = ts[0][0], ts[-1][1]
        n_chars = sum(len(s) for s in sents) or 1
        out, acc = [], 0
        for s in sents:
            a = total_a + (total_b - total_a) * acc / n_chars
            acc += len(s)
            b = total_a + (total_b - total_a) * acc / n_chars
            out.append((a, b, s))
        return out, cuts

    toks = [(a, b, ts[k]) for k, (a, b) in enumerate(spans)]
    entries = []
    cur = []  # 当前句的 token 列表 [(ci, cj, [t_start, t_end])]
    for idx, (ci, cj, t) in enumerate(toks):
        cur.append((ci, cj, t))
        nxt = toks[idx + 1] if idx + 1 < len(toks) else None
        if nxt is not None and not any(p in "。？！；，" for p in text[cj:nxt[0]]):
            continue
        # 句子闭合：句首口头禅剥成洞（词级跳剪用），正文作为条目
        for f in fillers:
            n_tok = len(f)  # filler 全汉字，一字一 token
            if len(cur) > n_tok and \
                    "".join(text[a:b] for a, b, _ in cur[:n_tok]) == f:
                cuts.append({"start": cur[0][2][0], "end": cur[n_tok - 1][2][1],
                             "word": f})
                cur = cur[n_tok:]
                break
        word = text[cur[0][0]:cur[-1][1]]
        word = re.sub(r"^[，,]", "", word).strip()
        entries.append((cur[0][2][0], cur[-1][2][1], word))
        cur = []
    return entries, cuts


def _norm(text):
    """归一化文本：去标点/空白，叠词折叠（在使用在使用→在使用），供重录对比对。"""
    t = re.sub(r"[^\w\u3400-\u9fff]", "", text)
    t = re.sub(r"([\u3400-\u9fff]{1,4})\1+", r"\1", t)
    return t


def detect_retake_pairs(sents, min_sim=0.55, min_ratio=0.35, max_gap_s=6.0, window=3):
    """重录对检测（窗口内链式）：口误→[停顿]→重说，重说可连续多遍（6→7→8 链）。

    对每条 b，在前 window 条里找被 b 覆盖的 a。判定（全部满足）：
    - 覆盖率 cov（a 归一化后被 b 最长匹配覆盖）≥min_sim，且 ratio ≥min_ratio
      ——实测校准：真重录 #4→#5 cov=0.57/#6→#8 cov=0.58/#7→#8 cov=0.67，
      而"在这过程中"类口播高频短句对 #9→#11/#12 cov 也 0.60，纯文本分不开，
      所以叠加：a 归一化长度 ≥6 字（超短短语必须 cov≥0.9 才算），且
    - gap ≤max_gap_s（口误后立即重说；#9→#12 gap=9.8s 的真重复靠初选人工兜底）
    返回 [{a,b,sim,gap_ms,text_a,text_b}]。用户规则：**保最后一个**，a 进 cuts。
    """
    pairs = []
    for j, b in enumerate(sents):
        nb = _norm(b[2])
        if not nb or len(nb) < 8:
            continue
        for i in range(max(0, j - window), j):
            a = sents[i]
            na = _norm(a[2])
            if not na or len(na) > len(nb):
                continue
            sm = SequenceMatcher(None, na, nb)
            m = sm.find_longest_match(0, len(na), 0, len(nb))
            cov = m.size / len(na) if len(na) else 0.0
            ratio = sm.ratio()
            short = len(na) < 6
            if cov >= (0.9 if short else min_sim) and ratio >= (0.7 if short else min_ratio):
                gap_s = (b[0] - a[1]) / 1000
                if gap_s <= max_gap_s:
                    pairs.append({"a": i + 1, "b": j + 1, "sim": round(max(cov, ratio), 2),
                                  "gap_ms": int(b[0] - a[1]),
                                  "text_a": a[2], "text_b": b[2]})
    return pairs


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
    ap.add_argument("--strip-filler", default="然后",
                    help="句首口头禅词级剥离（逗号分隔多个），记入 .cuts.json 供剪切时抠掉；空串=关闭")
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
    fillers = tuple(f for f in args.strip_filler.split(",") if f)
    # funasr 1.4.x 无 sentence_info：用字级 timestamp 自行分句对齐
    if r.get("sentence_info"):
        sents = [(s["start"], s["end"], s["text"].strip())
                 for s in r["sentence_info"]]
        cuts = []
    elif r.get("timestamp"):
        sents, cuts = build_entries(r["text"], r["timestamp"], fillers)
    else:
        sents, cuts = [(0, 0, r.get("text", ""))], []

    # 重录对：口误→停顿→重说。保删规则（用户拍板）：保最后一个，前遍进 cuts 挖掉
    retakes = detect_retake_pairs(sents)
    for p in retakes:
        a = sents[p["a"] - 1]
        cuts.append({"start": a[0], "end": a[1], "word": "🔁重录",
                     "retake_of": sents[p["b"] - 1][2]})
    with open(out, "w", encoding="utf-8") as f:
        for i, (a, b, txt) in enumerate(sents, 1):
            f.write(f"{i}\n{fmt_ts(a)} --> {fmt_ts(b)}\n{txt}\n\n")
    payload = {}
    if cuts:
        payload["fillers"] = cuts
    if retakes:
        payload["retake_pairs"] = retakes
    if payload:
        cuts_path = out.with_suffix(".cuts.json")
        cuts_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                             encoding="utf-8")
        if cuts:
            words = sorted({c["word"] for c in cuts})
            print(f"[asr_funasr] 词级洞 {len(cuts)} 个（{'、'.join(words)}）")
        if retakes:
            print(f"[asr_funasr] 重录对 {len(retakes)} 组（默认保最后一个，前遍已挖）:")
            for p in retakes:
                print(f"  #{p['a']}/{p['b']} sim={p['sim']} → 保: [{fmt_ts(sents[p['b']-1][0])[3:8]}] {p['text_b']}")
        print(f"[asr_funasr] → {out.with_suffix('.cuts.json')}")
    print(f"[asr_funasr] {len(sents)} 句 → {out}")
    for a, b, txt in sents:
        print(f"[{fmt_ts(a)[3:8]}] {txt}")


if __name__ == "__main__":
    main()
