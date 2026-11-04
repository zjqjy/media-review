#!/usr/bin/env python3
"""emit_protocol.py — 把跨 agent 规程卡 AGENT_PROTOCOL.md + 回写校验器发进目标项目根（S2-E，纯标准库）

用法：
    python emit_protocol.py <项目根> [--force]

- 规程卡源文件与本脚本同技能目录（../AGENT_PROTOCOL.md）；
- 目标：<项目根>/AGENT_PROTOCOL.md（外部 agent 拿到项目目录即拿到卡）；
  校验器 <项目根>/shoot/scripts/shoot_validate.py 随卡一起发——卡里的自检命令
  `python shoot/scripts/shoot_validate.py <定稿md> --against <快照>` 在任何项目
  目录都能直接跑（校验器纯标准库单文件，无技能内依赖）；
- 卡目标已存在时不直接覆盖：打印差异摘要（两边行数、覆盖将新增/删除的行数）
  请求确认，加 --force 才真覆盖——规程卡是协作契约，静默改版容易让外部 agent
  拿着旧约干活。校验器按字节覆盖（保持与卡同版）。
退出码：0 = 已写入/已覆盖；1 = 参数错、源缺失、已存在未加 --force。
"""
import difflib
import os
import sys

CARD_NAME = "AGENT_PROTOCOL.md"
VAL_NAME = "shoot_validate.py"


def _card_source():
    """规程卡源路径：本脚本在 skill/media/shoot/scripts/ 下，卡在其上一级"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, CARD_NAME)


def _validator_source():
    """校验器源路径：与本脚本同目录"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), VAL_NAME)


def _read_lines(path):
    with open(path, "rb") as f:
        return f.read().decode("utf-8").splitlines()


def _read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def _write_bytes(path, payload):
    with open(path, "wb") as f:
        f.write(payload)


def main(argv):
    args = [a for a in argv if a != "--force"]
    force = "--force" in argv
    if len(args) != 1:
        print("用法: python emit_protocol.py <项目根> [--force]")
        return 1
    root = args[0]
    src = os.path.normpath(_card_source())
    if not os.path.isfile(src):
        print(f"错误: 找不到规程卡源文件: {src}（应与本脚本同技能目录）")
        return 1
    if not os.path.isdir(root):
        print(f"错误: 项目根不存在或不是目录: {root}")
        return 1
    dst = os.path.join(root, CARD_NAME)
    card_bytes = _read_bytes(src)
    card_lines = card_bytes.decode("utf-8").splitlines()

    if os.path.isfile(dst):
        cur_bytes = _read_bytes(dst)
        if cur_bytes == card_bytes:
            print(f"已是一致，无需写入: {dst}（{len(card_lines)} 行）")
            _emit_validator(root)
            return 0
        cur_lines = cur_bytes.decode("utf-8", errors="replace").splitlines()
        diff = list(difflib.unified_diff(cur_lines, card_lines,
                                         fromfile="现有", tofile="规程卡", lineterm=""))
        added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
        print(f"目标已存在: {dst}")
        print(f"差异摘要: 规程卡 {len(card_lines)} 行 / 现有 {len(cur_lines)} 行；"
              f"覆盖将 +{added} 行 / -{removed} 行")
        if not force:
            print("未覆盖（确认覆盖请加 --force）")
            return 1
        _write_bytes(dst, card_bytes)
        print(f"已覆盖: {dst}（{len(card_lines)} 行）")
        _emit_validator(root)
        return 0

    _write_bytes(dst, card_bytes)
    print(f"已写入: {dst}（{len(card_lines)} 行）——外部 agent 以此卡为协作入口")
    _emit_validator(root)
    return 0


def _emit_validator(root):
    """校验器随卡发（字节覆盖，保持与卡同版）：三种卡写入路径都走这里，
    卡的自检命令 `python shoot/scripts/shoot_validate.py …` 在项目目录内即可跑。"""
    val_src = _validator_source()
    if not os.path.isfile(val_src):
        print(f"警告: 找不到校验器源 {val_src}，卡的自检命令需外部技能路径兜底")
        return
    val_dst = os.path.join(root, "shoot", "scripts", VAL_NAME)
    os.makedirs(os.path.dirname(val_dst), exist_ok=True)
    _write_bytes(val_dst, _read_bytes(val_src))
    print(f"校验器已随卡发射: {val_dst}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
