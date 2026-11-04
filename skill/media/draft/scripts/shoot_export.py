#!/usr/bin/env python3
"""shoot_export.py — 拍摄计划清单导出（S2-B，纯标准库，可 import 可 CLI）

从定稿旁车 shoot.json 编译两份 md 产物，写到定稿 md 同目录：
  - <md去扩展名>_拍摄清单.md      人看：建议文件名 + 拍摄提示，手机可看可带走
  - <md去扩展名>_AI制作任务.md    agent 看：✨复制给任意 agent 逐条执行的任务清单

数据流（冻结 schema v1，字段语义见 shoot_io，本模块无权改动 schema）：
  读：annotations（kind=manual 人工拍摄 / kind=ai AI 制作）+ 定稿 md 块数组
      （按 block_hash 找「对应内容」：quote 圈句给「quote」，整块给块原文首
      40 字，块对不上回落给 quote/hint 本身）。
  写：plan.checklist_md / plan.ai_tasks_md —— 语义为「导出文件相对定稿 md
      所在目录的文件名」（本实现固定导出到同目录，故即纯文件名），
      走 shoot_io.save_shoot 落盘，source_sha256 指纹校验照走：md 被外部
      改动即拒收（ShootShaMismatch），此时两份清单一个字节都不落盘。

铁律：纯标准库；md 本体永远只读不写（导出只新增清单文件，绝不碰定稿本体）；
错误信息一律人类可读中文。
"""
import os
import sys
from pathlib import Path

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:  # 独立 CLI / 被任意目录 import 都能找到同目录兄弟模块
    sys.path.insert(0, _HERE)

from draft_blocks import parse_blocks  # noqa: E402
from shoot_io import load_shoot, save_shoot  # noqa: E402

# 导出文件名后缀（写到定稿 md 同目录：<md去扩展名>+后缀）
CHECKLIST_SUFFIX = "_拍摄清单.md"
AI_TASKS_SUFFIX = "_AI制作任务.md"

# 建议文件名非法字符：Windows 文件名禁忌 \/:*?"<>| + 换行/制表；另加反引号
# （清单表格里文件名用 code 包裹，反引号会破坏渲染）——中文/空格/「」一律保留
_ILLEGAL = set('\\/:*?"<>|') | set("\r\n\t`")

# AI 类型路由说明（给 agent 的话术；枚举本体 card/motion/aigen/other 不翻译）
AI_ROUTE_HINT = "card=字幕卡 / motion=动效 / aigen=AI 生成 / other=按指令自选"


# ---------------------------------------------------------------- 纯函数

def clean_slug(text):
    """去文件名非法字符与换行，保留中文；首尾空白一并去掉（中间空格保留）。"""
    return "".join(ch for ch in (text or "") if ch not in _ILLEGAL).strip()


def suggest_filename(ann):
    """人工拍摄建议文件名：{id}_{slug}.mp4。

    slug 取 shoot_hint 前 12 字（hint 为空回落 quote，再空用「镜头」兜底），
    先净化后截断（防非法字符恰好落在截断点）。id 前缀保证素材回收匹配器
    （文件名含批注 id 即命中）能直接对上号。
    """
    src = clean_slug(ann.get("shoot_hint", "")) or clean_slug(ann.get("quote", ""))
    slug = src[:12] or "镜头"
    return f"{ann.get('id') or 'R00'}_{slug}.mp4"


def suggest_ai_filename(ann):
    """AI 制作产物建议路径：{id}_{ai_type}.mp4（类型即路由，回收器同按 id 命中）。"""
    t = clean_slug(ann.get("ai_type", "")) or "other"
    return f"{ann.get('id') or 'R00'}_{t}.mp4"


def _block_by_hash(blocks, block_hash):
    """按锚点找块（blocks 是 draft_blocks.parse_blocks 的产物）；找不到给 None。"""
    for b in blocks or []:
        if isinstance(b, dict) and b.get("hash") == block_hash:
            return b
    return None


def ref_text(ann, blocks):
    """对应内容：quote 非空给「quote」；整块批注给块原文首 40 字（截断补省略号）；
    block_hash 对不上块时回落给 quote/hint 本身。换行折成空格（表格/引用行不破版）。"""
    quote = (ann.get("quote") or "").strip()
    if quote:
        return "「" + quote.replace("\r\n", " ").replace("\n", " ") + "」"
    b = _block_by_hash(blocks, ann.get("block_hash", ""))
    if b is not None:
        raw = (b.get("raw") or "").replace("\r\n", " ").replace("\n", " ").strip()
        if not raw:
            return "（空块）"
        return raw[:40] + ("…" if len(raw) > 40 else "")
    hint = (ann.get("shoot_hint") or "").replace("\r\n", " ").replace("\n", " ").strip()
    return hint or "（无对应内容）"


def _cell(text):
    """markdown 表格单元格净化：换行折空格、竖线转义（\\|），防破表。"""
    return (text or "").replace("\r\n", " ").replace("\n", " ").replace("|", "\\|")


def _ai_card(ann, blocks, level=3):
    """一条 AI 制作卡（清单与任务清单共用）：标题 / 引用 / 产物路径 / 指令全文。

    指令原文逐行放进 blockquote——多行指令保持行结构，也防止指令里出现
    「# 开头」之类的行被误认成新标题。
    """
    tag = "#" * level
    t = ann.get("ai_type") or "other"
    out = [f"{tag} {ann.get('id') or 'R00'} · {t}", ""]
    out.append(f"- 对应内容：{ref_text(ann, blocks)}")
    out.append(f"- 产物建议路径：`{suggest_ai_filename(ann)}`")
    out.append("")
    out.append("**制作指令**：")
    out.append("")
    brief = (ann.get("ai_brief") or "").strip()
    if brief:
        out.extend("> " + ln for ln in brief.splitlines())
    else:
        out.append("> （无指令）")
    out.append("")
    return out


def build_checklist(shoot, blocks, md_name=""):
    """拍摄计划清单 markdown：头部（标题+定稿来源+统计行）+ 人工拍摄表格 +
    AI 制作单列一节。纯函数——同输入恒同输出（重复导出幂等的前提）。"""
    anns = shoot.get("annotations", []) if isinstance(shoot, dict) else []
    manual = [a for a in anns if a.get("kind") == "manual"]
    ai = [a for a in anns if a.get("kind") == "ai"]
    L = ["# 📋 拍摄计划清单", ""]
    L.append(f"> 定稿来源：{md_name or '未知定稿'}")
    L.append(f"> 统计：实拍 {len(manual)} · AI制作 {len(ai)}")
    L.append("")
    L.append(f"## 🎬 人工拍摄（{len(manual)}）")
    L.append("")
    if manual:
        L.append("| 建议文件名 | 对应内容 | 拍摄提示 |")
        L.append("| --- | --- | --- |")
        for a in manual:
            hint = a.get("shoot_hint") or "（无提示）"
            L.append(f"| `{suggest_filename(a)}` | {_cell(ref_text(a, blocks))} "
                     f"| {_cell(hint)} |")
    else:
        L.append("（无人工拍摄项——在 draft 工作台用块工具条 🎬 打呈现批注）")
    L.append("")
    L.append(f"## 🤖 AI 制作（{len(ai)}）")
    L.append("")
    if ai:
        for a in ai:
            L.extend(_ai_card(a, blocks, level=3))
    else:
        L.append("（无 AI 制作项）")
    return "\n".join(L)


def build_ai_tasks_md(shoot, blocks, md_name=""):
    """✨AI 制作任务清单 markdown：开头给 agent 的执行说明 + 逐条任务卡
    （id/类型/指令/引用/产物路径）。只收 kind=ai 的批注——人工拍摄的归清单。"""
    anns = shoot.get("annotations", []) if isinstance(shoot, dict) else []
    ai = [a for a in anns if a.get("kind") == "ai"]
    L = ["# ✨ AI 制作任务清单", ""]
    L.append(f"> 定稿来源：{md_name or '未知定稿'}")
    L.append(f"> 任务数：{len(ai)}")
    L.append("")
    L.append("你是素材制作执行者。逐条完成以下 AI 制作任务：")
    L.append("")
    L.append(f"1. 按每条任务的「类型」路由到对应工具：{AI_ROUTE_HINT}；")
    L.append("2. 严格按「制作指令」原文制作素材，不要自行增删要求；")
    L.append("3. 产物保存到该条的「产物建议路径」（相对定稿 md 所在目录）；")
    L.append("4. 全部完成后逐条回报：任务 id、实际产物路径、完成状态。")
    L.append("")
    if ai:
        for a in ai:
            L.append(f"## {a.get('id') or 'R00'} · {a.get('ai_type') or 'other'}")
            L.append("")
            L.append(f"- 对应内容：{ref_text(a, blocks)}")
            L.append(f"- 产物建议路径：`{suggest_ai_filename(a)}`")
            L.append("")
            L.append("**制作指令**：")
            L.append("")
            brief = (a.get("ai_brief") or "").strip()
            if brief:
                L.extend("> " + ln for ln in brief.splitlines())
            else:
                L.append("> （无指令）")
            L.append("")
    else:
        L.append("（无 AI 制作任务）")
        L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------- 落盘

def _write_text(path, text):
    """原子写：tmp + os.replace，半份内容不落地（与 draft_server 同款）。"""
    tmp = str(path) + ".tmp"
    with open(tmp, "wb") as f:
        f.write(text.encode("utf-8"))
    os.replace(tmp, path)


def export_all(md_path):
    """导出全流程：读旁车 → 解析定稿块 → 编译两份 md → 回填旁车 → 落盘。

    顺序讲究：先 save_shoot（schema 校验 + sha 指纹拦截）再写清单文件——
    指纹不符 / 旁车非法时两份文件一个字节都不落，不产生半成品。
    返回 (拍摄清单路径, AI制作任务路径, 清单markdown, AI任务markdown)。
    """
    md_path = str(md_path)
    if not os.path.isfile(md_path):
        raise FileNotFoundError(f"定稿 md 不存在: {md_path}")
    shoot = load_shoot(md_path)
    with open(md_path, "rb") as f:
        text = f.read().decode("utf-8")
    blocks = parse_blocks(text)
    md_name = os.path.basename(md_path)
    stem = os.path.splitext(md_name)[0]
    cl_name = stem + CHECKLIST_SUFFIX
    ai_name = stem + AI_TASKS_SUFFIX
    cl_md = build_checklist(shoot, blocks, md_name=md_name)
    ai_md = build_ai_tasks_md(shoot, blocks, md_name=md_name)
    # 回填旁车 plan（语义：存导出文件相对定稿 md 所在目录的文件名）
    plan = shoot.get("plan")
    if not isinstance(plan, dict):
        plan = shoot["plan"] = {}
    plan["checklist_md"] = cl_name
    plan["ai_tasks_md"] = ai_name
    save_shoot(md_path, shoot)  # schema 校验 + md 指纹拦截都在这一步（照走）
    md_dir = os.path.dirname(os.path.abspath(md_path))
    cl_path = os.path.join(md_dir, cl_name)
    ai_path = os.path.join(md_dir, ai_name)
    _write_text(cl_path, cl_md)
    _write_text(ai_path, ai_md)
    return cl_path, ai_path, cl_md, ai_md


# ---------------------------------------------------------------- CLI

def main(argv=None):
    """用法: python shoot_export.py <定稿md路径> —— 导出两份清单并打印路径。"""
    if os.name == "nt":
        try:  # Windows 控制台中文不炸
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    if len(argv) != 1 or argv[0] in ("-h", "--help"):
        print("用法: python shoot_export.py <定稿md路径>")
        return 1
    p = argv[0].strip().strip('"')
    try:
        cl_path, ai_path, _, _ = export_all(p)
    except (OSError, ValueError) as e:  # 指纹不符/schema 不过/文件缺失 → 人话退出
        print(f"[shoot_export] 导出失败: {e}", file=sys.stderr)
        return 2
    print(f"[shoot_export] 拍摄清单:   {cl_path}")
    print(f"[shoot_export] AI制作任务: {ai_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
