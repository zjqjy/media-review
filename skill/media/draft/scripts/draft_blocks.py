#!/usr/bin/env python3
"""draft_blocks.py — md ⇄ 块数组 双向解析（draft 审阅工作台核心）

块模型：把 AI 初稿 md 切成可独立编辑/批注的块（frontmatter/标题/段落/列表项/
引用/代码块/表格/分隔线），每块带内容 hash 作批注锚点。

硬约束（D2）：round-trip 保真——parse_blocks(text) → render_blocks(...) 必须
逐字节还原原文（md 本体纯净红线，下游管线照吃）。所有块只存原文行与块间
换行数（gap），绝不改写任何字符；语义识别错了顶多影响 UI 图标，不影响还原。

gap 语义：块 raw 之后的换行数。块间 = 空行数+1；文末 = 尾部换行数（可为 0）。
文件开头的空行收成一个 raw 为空的 blank 块，靠 gap 还原。
重排语义：分隔符属于「位置」不属于「块」——reorder_blocks 内容动、gap 不动。

空行判定：严格 == ""（strip 会把纯空格行当空行吃掉，字节数对不上）。
CRLF 文件整档识别后剥 \r 解析，渲染时统一补回，避免 \r 掉进 gap 丢字节。
"""
import hashlib
import re

# 结构起始行识别（段落在此停下、列表续行不得撞上）
HEADING_RE = re.compile(r"^#{1,6}\s+")
QUOTE_RE = re.compile(r"^\s*>")
FENCE_RE = re.compile(r"^(\s*)(```+|~~~+)")
TABLE_ROW_RE = re.compile(r"^\s*\|")
HR_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])(\s+)")


def _structural(line):
    """该行是否开启一个结构块（段落/列表续行遇到它必须让位）"""
    return bool(HEADING_RE.match(line) or QUOTE_RE.match(line)
                or FENCE_RE.match(line) or TABLE_ROW_RE.match(line)
                or HR_RE.match(line) or LIST_RE.match(line))


def block_hash(btype, raw):
    """块锚点：类型+原文 md5 前 10 位（同内容同 hash，改一字即换锚）"""
    return hashlib.md5((btype + "\x00" + raw).encode("utf-8")).hexdigest()[:10]


def _blank_block(gap, line_no):
    return {"hash": block_hash("blank", ""), "type": "blank", "raw": "",
            "gap": gap, "level": 0, "line": line_no}


def _make(btype, lines_slice, line_no, gap, level=0):
    raw = "\n".join(lines_slice)
    return {"hash": block_hash(btype, raw), "type": btype, "raw": raw,
            "gap": gap, "level": level, "line": line_no}


def _is_crlf(text):
    """整档 CRLF 判定：含 \r\n 且除末行（可能无结尾换行）外每行以 \r 收尾"""
    if "\r\n" not in text:
        return False
    lines = text.split("\n")
    body = lines[:-1] if text.endswith("\n") else lines
    return all(l.endswith("\r") for l in body)


def parse_blocks(text):
    """md 文本 → 块数组。空文件返回 []。CRLF 文件剥 \r 解析（渲染时补回）。"""
    if not text:
        return []
    crlf = _is_crlf(text)
    lines = [l[:-1] if l.endswith("\r") else l
             for l in text.split("\n")] if crlf else text.split("\n")
    n = len(lines)
    blocks = []
    i = 0

    # 文件开头空行 → blank 块（raw 空，gap=空行数，渲染时靠 "\n"*gap 还原）
    if lines[0] == "":
        j = 0
        while j < n and lines[j] == "":
            j += 1
        if j == n:  # 全文皆空行
            return [_blank_block(n - 1, 1)]
        blocks.append(_blank_block(j, 1))
        blocks[0]["eol"] = "crlf" if crlf else "lf"
        i = j

    while i < n:
        line = lines[i]
        if line == "":  # 防御：内部空行已被上一块 gap 吸收
            i += 1
            continue
        level = 0

        # —— 按 Block 语法分派，每个分支返回块结束行（不含）——
        if i == 0 and line.strip() == "---":
            close = None
            for k in range(1, n):
                if lines[k].strip() == "---":
                    close = k + 1
                    break
            end = close if close is not None else 1  # 没闭合按 hr 单行处理
            btype = "frontmatter" if close is not None else "hr"
        elif FENCE_RE.match(line):
            m = FENCE_RE.match(line)
            fchar, flen = m.group(2)[0], len(m.group(2))
            end = n  # 未闭合的围栏吃到底
            for k in range(i + 1, n):
                s = lines[k].strip()
                if s and set(s) == {fchar} and len(s) >= flen:
                    end = k + 1
                    break
            btype = "code"
        elif TABLE_ROW_RE.match(line):
            end = i + 1
            while end < n and TABLE_ROW_RE.match(lines[end]):
                end += 1
            btype = "table"
        elif QUOTE_RE.match(line):
            end = i + 1
            while end < n and QUOTE_RE.match(lines[end]):
                end += 1
            btype = "quote"
        elif HR_RE.match(line):
            end, btype = i + 1, "hr"
        elif HEADING_RE.match(line):
            end, btype = i + 1, "heading"
            level = len(line) - len(line.lstrip("#"))
        elif LIST_RE.match(line):
            indent = len(LIST_RE.match(line).group(1))
            end = i + 1
            # 列表项续行：非空、有缩进、且不是新结构块（嵌套列表行自成一块）
            while (end < n and lines[end] != ""
                   and lines[end][:1] in (" ", "\t")
                   and not _structural(lines[end])):
                end += 1
            btype, level = "list_item", indent // 2
        else:
            end = i + 1
            while end < n and lines[end] != "" and not _structural(lines[end]):
                end += 1
            btype = "paragraph"

        # 块后空行 → gap（空行数+1）；到文件尾则 gap=尾部换行数（可为 0）
        g = end
        while g < n and lines[g] == "":
            g += 1
        gap = (g - end + 1) if g < n else (n - end)

        blocks.append(_make(btype, lines[i:end], i + 1, gap, level))
        blocks[-1]["eol"] = "crlf" if crlf else "lf"
        i = end
    return blocks


def render_blocks(blocks):
    """块数组 → md 文本（parse 的逆运算，逐字节还原）。"""
    text = "".join((b.get("raw") or "") + "\n" * int(b.get("gap", 1))
                   for b in blocks)
    if blocks and all(b.get("eol") == "crlf" for b in blocks):
        text = text.replace("\n", "\r\n")
    return text


def reorder_blocks(blocks, order):
    """按 order 重排块：内容动、gap 不动（分隔符属于位置不属于块）。

    [甲,乙,丙] gaps [2,2,1] 重排成 [丙,甲,乙] 后仍是 gaps [2,2,1]，
    即「丙\\n\\n甲\\n\\n乙」——文末换行数始终由最后位置继承。
    """
    gaps = [b["gap"] for b in blocks]
    out = [dict(blocks[i]) for i in order]
    for b, g in zip(out, gaps):
        b["gap"] = g
    return out


def delete_block(blocks, idx):
    """删除块：删末块时把文末换行数转移给新末块（内部 gap 不残留成双尾换行）。"""
    out = list(blocks)
    removed = out.pop(idx)
    if idx == len(out) and out:  # 删的是末块：文末换行随位置转移
        out[-1]["gap"] = removed["gap"]
    return out


def match_comment_blocks(blocks, comments):
    """批注锚定三级回落：block_hash 精确 → quote 全文包含 → orphan。

    就地写回 c["_block_index"]（无锚为 None）与 c["_anchor"]。
    同文重复块（相同列表项）hash 撞车时锚到首个，v1 接受。
    """
    by_hash = {}
    for idx, b in enumerate(blocks):  # setdefault：重复 hash 锚首个
        by_hash.setdefault(b["hash"], idx)
    for c in comments:
        idx = by_hash.get(c.get("block_hash"))
        if idx is not None:
            c["_anchor"] = "hash"
        elif c.get("quote"):
            idx = next((k for k, b in enumerate(blocks)
                        if c["quote"] in (b["raw"] or "")), None)
            c["_anchor"] = "quote" if idx is not None else "orphan"
        else:
            idx = None
            c["_anchor"] = "orphan"
        c["_block_index"] = idx
    return comments


if __name__ == "__main__":
    # 冒烟：stdin → 块列表摘要 → 渲染还原校验
    import sys
    src = sys.stdin.read()
    bs = parse_blocks(src)
    for b in bs:
        print(f"L{b['line']:>4} {b['type']:<12} lv{b['level']} gap{b['gap']:<3} {b['raw'][:48]!r}")
    assert render_blocks(bs) == src, "round-trip 失败"
    print(f"[OK] {len(bs)} 块 round-trip 保真")
