"""draft_blocks 纯函数单测：round-trip 保真是硬约束（D2 md 纯净红线）。

审阅工作台把 AI 初稿 md 切块编辑后重组写回，任何字节漂移都会污染下游管线
（转录/初选/素材都吃这份 md）。用例覆盖：frontmatter、嵌套列表、围栏代码块
（内含空行/分隔线假信号）、表格、引用、CRLF、前后空行、重复块 hash 撞车锚定。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "skill" / "media" / "draft" / "scripts"))
from draft_blocks import (  # noqa: E402
    block_hash, match_comment_blocks, parse_blocks, render_blocks)


class TestRoundTrip(unittest.TestCase):
    """parse → render 必须逐字节还原"""

    def _rt(self, text):
        self.assertEqual(render_blocks(parse_blocks(text)), text)

    def test_kitchen_sink(self):
        text = (
            "---\ntitle: 第7期大纲\ntags: [视频]\n---\n"
            "\n"
            "# 开场钩子\n"
            "\n"
            "先抛问题再亮答案，前 5 秒必须留住人。\n"
            "这段是同一段落的软换行。\n"
            "\n"
            "## 要点\n"
            "\n"
            "- 第一条：喇叭麦克风驱动\n"
            "  - 嵌套子点\n"
            "- 第二条：AG 骨架\n"
            "1. 有序列表项\n"
            "2. 有序第二项\n"
            "\n"
            "> 引用：口癖根因是半角逗号分句\n"
            "> 引用第二行\n"
            "\n"
            "```python\n"
            "# 这行不是标题\n--- 这行不是分隔线\n\n\n空行也在围栏里\n"
            "```\n"
            "\n"
            "| 时间轴 | 口播 | 画面 |\n"
            "| --- | --- | --- |\n"
            "| 00:05 | 钩子 | 字幕卡 |\n"
            "\n"
            "---\n"
            "\n"
            "结尾段落。\n"
        )
        self._rt(text)

    def test_no_trailing_newline(self):
        self._rt("# 标题\n\n结尾无换行")

    def test_multiple_trailing_newlines(self):
        self._rt("段落一\n\n段落二\n\n\n\n")

    def test_leading_blank_lines(self):
        self._rt("\n\n\n开头前三个空行\n\n正文\n")

    def test_all_blank(self):
        self._rt("\n\n\n")

    def test_empty(self):
        self.assertEqual(parse_blocks(""), [])

    def test_crlf_preserved(self):
        text = "# 标题\r\n\r\n段落一\r\n段落二\r\n"
        self._rt(text)

    def test_unclosed_fence_eats_to_end(self):
        text = "```text\n永不闭合\n第二行"
        self._rt(text)

    def test_tight_vs_loose_list_gap(self):
        blocks = parse_blocks("- 甲\n- 乙\n\n- 丙\n")
        self.assertEqual(blocks[0]["gap"], 1)   # 紧列表：单换行
        self.assertEqual(blocks[1]["gap"], 2)   # 空行：松列表
        self.assertEqual(blocks[2]["gap"], 1)   # 文末换行


class TestBlockTyping(unittest.TestCase):
    def test_types_and_levels(self):
        blocks = parse_blocks(
            "---\nx: 1\n---\n# 一级\n## 二级\n- 项\n  - 子项\n段落\n")
        types = [b["type"] for b in blocks]
        self.assertEqual(types[0], "frontmatter")
        self.assertEqual([b["type"] for b in blocks[1:3]],
                         ["heading", "heading"])
        self.assertEqual(blocks[1]["level"], 1)
        self.assertEqual(blocks[2]["level"], 2)
        items = [b for b in blocks if b["type"] == "list_item"]
        self.assertEqual([b["level"] for b in items], [0, 1])

    def test_fence_not_parsed_inside(self):
        blocks = parse_blocks("```\n# 假标题\n- 假列表\n```\n")
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["type"], "code")

    def test_list_continuation_line_attaches(self):
        blocks = parse_blocks("- 项一\n  续行说明\n- 项二\n")
        self.assertEqual(len([b for b in blocks if b["type"] == "list_item"]), 2)
        self.assertIn("续行说明", blocks[0]["raw"])


class TestEditAndAnchor(unittest.TestCase):
    def test_edit_one_block_others_untouched(self):
        text = "# 标题\n\n- 甲\n- 乙\n\n尾段\n"
        blocks = parse_blocks(text)
        blocks[1]["raw"] = "- 甲（已改）"
        out = render_blocks(blocks)
        self.assertEqual(out, "# 标题\n\n- 甲（已改）\n- 乙\n\n尾段\n")

    def test_reorder_and_delete(self):
        from draft_blocks import delete_block, reorder_blocks
        blocks = parse_blocks("甲\n\n乙\n\n丙\n")
        out = reorder_blocks(blocks, [2, 0, 1])  # 丙甲乙，gap 留在位置上
        out = delete_block(out, 2)               # 删乙（末块，文末换行转移）
        self.assertEqual(render_blocks(out), "丙\n\n甲\n")

    def test_hash_stability(self):
        a = parse_blocks("- 相同项\n")[0]
        b = parse_blocks("- 相同项\n")[0]
        self.assertEqual(a["hash"], b["hash"])
        self.assertNotEqual(a["hash"], block_hash("list_item", "- 不同项\n"))

    def test_match_anchor_hash_quote_orphan(self):
        blocks = parse_blocks("# 标题\n\n第一段原文\n\n第二段\n")
        comments = [
            {"id": "c1", "block_hash": blocks[1]["hash"], "quote": "第一段"},
            {"id": "c2", "block_hash": "deadbeef0000", "quote": "第二段"},
            {"id": "c3", "block_hash": "deadbeef0000", "quote": "不存在"},
            {"id": "c4", "block_hash": "", "quote": ""},
        ]
        match_comment_blocks(blocks, comments)
        anchors = {c["id"]: (c["_anchor"], c["_block_index"]) for c in comments}
        self.assertEqual(anchors["c1"], ("hash", 1))
        self.assertEqual(anchors["c2"], ("quote", 2))
        self.assertEqual(anchors["c3"], ("orphan", None))
        self.assertEqual(anchors["c4"], ("orphan", None))

    def test_duplicate_blocks_anchor_first(self):
        blocks = parse_blocks("- 重复\n\n- 重复\n")
        comments = [{"id": "c1", "block_hash": blocks[0]["hash"],
                     "quote": "重复"}]
        match_comment_blocks(blocks, comments)
        self.assertEqual(comments[0]["_block_index"], 0)


if __name__ == "__main__":
    unittest.main()
