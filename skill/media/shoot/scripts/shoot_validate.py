#!/usr/bin/env python3
"""shoot_validate.py — shoot.json 全量校验 + agent 回写白名单 diff 校验器（S2-E，纯标准库）

给「只拿到项目目录」的外部 agent（claude code / codex / 任何 agent）当自检闸门：

    python shoot_validate.py <定稿md>                            # 全量 schema 校验 + md 指纹核对
    python shoot_validate.py <定稿md> --against <回写前快照.json>  # 再加 agent 回写白名单 diff

退出码：0 = 通过（[警告] 行不挡），1 = 拒收（按清单改到 0 才算完成）。

语义对齐声明：本模块独立实现，不 import 草稿侧代码，但校验语义与
skill/media/draft/scripts/shoot_io.py 的 validate_shoot / check_agent_writeback 对齐——
同一份合法回写两边都放行，同一份越权两边都拒收。差异只有两处（均为收紧，不放松）：
  1. tasks[].note 按 S2-D 备案扩展校验为可选字符串（draft 侧旧校验器不查类型）；
  2. done 任务的 output 指向不存在/空文件记为「[警告] 级」错误（不动退出码，draft 侧无此检查）。

冻结 schema v1（不得改动）：旁车 <定稿md同名>.shoot.json 与 md 同目录，五节
annotations / plan / footage / editNotes / tasks；agent 回写白名单（唯一可改）：
tasks[].state、tasks[].output、footage[].state、footage[].note。tasks[].note 是
生成器私有字段，不在白名单——diff 里出现它的变化 = 有人绕过协议，拒收。

铁律：纯标准库；错误信息一律人类可读中文；md 本体只读不写。
"""
import hashlib
import json
import os
import re
import sys

VERSION = 1

# 枚举（冻结 schema v1，与 shoot_io.py 一字不差）
KINDS = ("manual", "ai")
AI_TYPES = ("card", "motion", "aigen", "other")
FOOTAGE_STATES = ("candidate", "selected")
TASK_TYPES = ("reshoot", "card", "motion", "aigen")
TASK_STATES = ("open", "doing", "done")

# agent 回写白名单：节名 -> 允许改的字段（其余任何字段变化都算越权）
AGENT_WHITELIST = {"tasks": {"state", "output"}, "footage": {"state", "note"}}

# 顶层字段全集（未知顶层字段按拼写错误拒收；冻结 v1 就这 8 个）
_TOP_KEYS = {"version", "source_sha256", "locked",
             "annotations", "plan", "footage", "editNotes", "tasks"}

_ANN_ID_RE = re.compile(r"^R\d{2,}$")   # 呈现批注 id：R + 两位起数字
_WARN = "[警告] "                        # 警告级错误前缀（不挡退出码，硬错误无此前缀）


def shoot_path(md_path):
    """旁车路径：<原名>.shoot.json（与 md 同目录同名）"""
    return str(md_path) + ".shoot.json"


def _sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _is_int(x):
    """严格整数（bool 是 int 子类，必须排除）"""
    return isinstance(x, int) and not isinstance(x, bool)


def _is_str(x):
    return isinstance(x, str)


# ---------------------------------------------------------------- 全量校验


def validate(data, md_path=None, root=None):
    """schema v1 全量校验 → 中文错误清单（空列表 = 合法）。

    语义对齐 shoot_io.validate_shoot：version/source_sha256 必有；缺失的可选节按空
    处理（跨 agent 手写最小旁车也能过）；出现了的字段严格查类型/枚举/引用关系；
    未知顶层字段拒收。S2-D 备案扩展：tasks[].note 可选字符串。
    md_path 给了就加验两件事：
      - source_sha256 与 md 当前实际指纹一致（不符 = md 本体被外部改动，硬错误拒收）；
      - state=done 的任务 output 指向真实存在且非空的产物文件（警告级，[警告] 前缀），
        路径基准 = root（项目根=素材目录所在层）；缺省 md 所在目录（单目录项目重合）。
    """
    errs = []
    if not isinstance(data, dict):
        return ["根节点应是 JSON 对象"]

    if "version" not in data:
        errs.append("缺少 version")
    elif not _is_int(data["version"]) or data["version"] != VERSION:
        errs.append(f"version 必须是 {VERSION}（冻结 schema v1），得到 {data['version']!r}")

    if "source_sha256" not in data:
        errs.append("缺少 source_sha256")
    elif not _is_str(data["source_sha256"]) or \
            not re.fullmatch(r"[0-9a-f]{64}", data["source_sha256"]):
        errs.append("source_sha256 应是 64 位小写 hex（定稿 md 的 sha256），"
                    f"得到 {data['source_sha256']!r}")

    if "locked" in data and not isinstance(data["locked"], bool):
        errs.append(f"locked 应是布尔值，得到 {data['locked']!r}")

    unknown = set(data) - _TOP_KEYS
    if unknown:
        errs.append("未知顶层字段: " + "、".join(sorted(unknown)))

    # ---- annotations：呈现批注（id 从 R01 起顺序编号，定稿后永不变）----
    anns = data.get("annotations", [])
    if not isinstance(anns, list):
        errs.append("annotations 应是数组")
        anns = []
    ann_ids = set()
    for i, a in enumerate(anns):
        where = f"annotations[{i}]"
        if not isinstance(a, dict):
            errs.append(f"{where} 应是对象")
            continue
        aid = a.get("id")
        if not _is_str(aid) or not _ANN_ID_RE.match(aid):
            errs.append(f"{where}.id 应形如 R01（R+两位起数字），得到 {aid!r}")
        elif aid in ann_ids:
            errs.append(f"{where}.id 重复: {aid}")
        else:
            ann_ids.add(aid)
        if not _is_str(a.get("block_hash", "")):
            errs.append(f"{where}.block_hash 应是字符串（块锚点，空串走 quote 回落）")
        if not _is_str(a.get("quote", "")):
            errs.append(f"{where}.quote 应是字符串（空串=整块批注）")
        occ = a.get("occurrence", 1)
        if not _is_int(occ) or occ < 1:
            errs.append(f"{where}.occurrence 应是 ≥1 的整数（quote 在块内第几次出现），"
                        f"得到 {occ!r}")
        kind = a.get("kind")
        if kind not in KINDS:
            errs.append(f"{where}.kind 应是 {'/'.join(KINDS)}，得到 {kind!r}")
        ai_type = a.get("ai_type", "")
        if ai_type and ai_type not in AI_TYPES:
            errs.append(f"{where}.ai_type 应是 {'/'.join(AI_TYPES)}，得到 {ai_type!r}")
        if kind == "ai" and not ai_type:
            errs.append(f"{where}.ai_type 缺失（kind=ai 必须给路由类型）")
        if not _is_str(a.get("shoot_hint", "")):
            errs.append(f"{where}.shoot_hint 应是字符串（kind=manual 拍什么提示）")
        if not _is_str(a.get("ai_brief", "")):
            errs.append(f"{where}.ai_brief 应是字符串（kind=ai 给 AI 的指令）")
        if not _is_str(a.get("status", "open")) or not a.get("status", "open"):
            errs.append(f"{where}.status 应是非空字符串（如 open）")
        if not _is_str(a.get("created", "")):
            errs.append(f"{where}.created 应是 ISO 时间字符串")

    # ---- footage：素材表（ann_ids 必须指向真实存在的呈现批注）----
    footage = data.get("footage", [])
    if not isinstance(footage, list):
        errs.append("footage 应是数组")
        footage = []
    fids = set()
    for i, ft in enumerate(footage):
        where = f"footage[{i}]"
        if not isinstance(ft, dict):
            errs.append(f"{where} 应是对象")
            continue
        fid = ft.get("id")
        if not _is_str(fid) or not fid:
            errs.append(f"{where}.id 缺失或非字符串")
        elif fid in fids:
            errs.append(f"{where}.id 重复: {fid}")
        else:
            fids.add(fid)
        if not _is_str(ft.get("file", "")) or not ft.get("file"):
            errs.append(f"{where}.file 缺失（相对项目根的素材路径）")
        st = ft.get("state", "candidate")
        if st not in FOOTAGE_STATES:
            errs.append(f"{where}.state 应是 {'/'.join(FOOTAGE_STATES)}，得到 {st!r}")
        if "match" in ft and not _is_str(ft["match"]):
            errs.append(f"{where}.match 应是字符串（如 filename / ai:0.87 / manual）")
        if "note" in ft and not _is_str(ft["note"]):
            errs.append(f"{where}.note 应是字符串")
        ids = ft.get("ann_ids", [])
        if not isinstance(ids, list) or any(not _is_str(x) for x in ids):
            errs.append(f"{where}.ann_ids 应是字符串数组")
        else:
            for x in ids:
                if x not in ann_ids:
                    errs.append(f"{where}.ann_ids 引用不存在的批注: {x}")

    # ---- editNotes：剪辑批注（挂在素材条目上）----
    notes = data.get("editNotes", [])
    if not isinstance(notes, list):
        errs.append("editNotes 应是数组")
        notes = []
    eids = set()
    for i, en in enumerate(notes):
        where = f"editNotes[{i}]"
        if not isinstance(en, dict):
            errs.append(f"{where} 应是对象")
            continue
        eid = en.get("id")
        if not _is_str(eid) or not eid:
            errs.append(f"{where}.id 缺失或非字符串")
        elif eid in eids:
            errs.append(f"{where}.id 重复: {eid}")
        else:
            eids.add(eid)
        fid_ref = en.get("footage_id")
        if not _is_str(fid_ref) or fid_ref not in fids:
            errs.append(f"{where}.footage_id 引用不存在的素材: {fid_ref!r}")
        if not _is_str(en.get("note", "")):
            errs.append(f"{where}.note 应是字符串（截哪段/效果/接哪）")

    # ---- tasks：补制任务（ref 必须指向真实存在的呈现批注）----
    tasks = data.get("tasks", [])
    if not isinstance(tasks, list):
        errs.append("tasks 应是数组")
        tasks = []
    tids = set()
    for i, t in enumerate(tasks):
        where = f"tasks[{i}]"
        if not isinstance(t, dict):
            errs.append(f"{where} 应是对象")
            continue
        tid = t.get("id")
        if not _is_str(tid) or not tid:
            errs.append(f"{where}.id 缺失或非字符串")
        elif tid in tids:
            errs.append(f"{where}.id 重复: {tid}")
        else:
            tids.add(tid)
        if t.get("type") not in TASK_TYPES:
            errs.append(f"{where}.type 应是 {'/'.join(TASK_TYPES)}，得到 {t.get('type')!r}")
        st = t.get("state", "open")
        if st not in TASK_STATES:
            errs.append(f"{where}.state 应是 {'/'.join(TASK_STATES)}，得到 {st!r}")
        ref = t.get("ref")
        if not _is_str(ref) or not ref:
            errs.append(f"{where}.ref 缺失（应指向呈现批注 id）")
        elif ref not in ann_ids:
            errs.append(f"{where}.ref 引用不存在的批注: {ref}")
        if not _is_str(t.get("output", "")):
            errs.append(f"{where}.output 应是字符串（产物相对路径）")
        # S2-D 备案扩展：tasks[].note 生成器私有，可选字符串（不在 agent 白名单）
        if "note" in t and not _is_str(t["note"]):
            errs.append(f"{where}.note 应是字符串（S2-D 生成器私有备案字段）")

    # ---- plan：清单宿主 ----
    plan = data.get("plan", {})
    if not isinstance(plan, dict):
        errs.append("plan 应是对象")
    else:
        for k in ("checklist_md", "ai_tasks_md"):
            if k in plan and not _is_str(plan[k]):
                errs.append(f"plan.{k} 应是字符串")

    # ---- md_path 加验：md 指纹 + done 任务产物实况 ----
    if md_path is not None:
        if not os.path.isfile(md_path):
            errs.append(f"md 文件不存在: {md_path}")
        else:
            actual = _sha256_file(md_path)
            claimed = str(data.get("source_sha256") or "")
            if claimed != actual:
                errs.append(
                    f"md 指纹不符（旁车 source_sha256 {claimed[:12]}… ≠ 当前 md "
                    f"{actual[:12]}…）——定稿 md 本体已被外部改动，拒收")
        errs.extend(_check_done_outputs(tasks, md_path, root=root))
    return errs


def _check_done_outputs(tasks, md_path, root=None):
    """done 任务的 output 实况核对 → [警告] 级清单（不挡退出码）。

    完成定义：task.state=done 且 output 指向真实存在且非空的产物文件（相对项目根，
    posix 风格）。项目根由 root 参数显式给（=素材目录所在层，与 footage.file 同基准）；
    缺省取 md 所在目录（单目录项目两者天然重合）。
    """
    warns = []
    root = os.path.abspath(str(root)) if root else os.path.dirname(os.path.abspath(str(md_path)))
    for i, t in enumerate(tasks):
        if not isinstance(t, dict) or t.get("state") != "done":
            continue
        out = t.get("output", "")
        tid = t.get("id") or f"#{i}"
        if not _is_str(out):  # 非字符串 output 已由 schema 报硬错误，这里不重复也不崩
            continue
        if not out:
            warns.append(f"{_WARN}tasks[{i}]（{tid}）state=done 但 output 为空"
                         f"——完成定义要求产物文件")
            continue
        if os.path.isabs(out) or ".." in out.split("/"):
            warns.append(f"{_WARN}tasks[{i}]（{tid}）output 应是相对项目根的 posix 路径，"
                         f"得到 {out!r}")
            continue
        p = os.path.join(root, *out.split("/"))
        if not os.path.isfile(p):
            warns.append(f"{_WARN}tasks[{i}]（{tid}）state=done 但 output 指向的产物"
                         f"不存在: {out}")
        elif os.path.getsize(p) == 0:
            warns.append(f"{_WARN}tasks[{i}]（{tid}）output 指向的产物是空文件: {out}")
    return warns


# ---------------------------------------------------------------- 回写白名单 diff


def _strip_private(data):
    """剥掉下划线开头的私有缓存字段（前端 _anchor 等）——不参与 diff 比对"""
    if isinstance(data, dict):
        return {k: _strip_private(v) for k, v in data.items() if not k.startswith("_")}
    if isinstance(data, list):
        return [_strip_private(x) for x in data]
    return data


def _index_entries(items):
    """条目按 id 建索引：id -> (首次出现下标, 条目)。id 缺失/非字符串/重复 → None（拒收）。

    id 必须是非空字符串（可哈希）——列表等不可哈希的 id 无法当 diff 键，按缺 id 拒收，
    不让校验器自己崩掉（语义对齐 draft 侧的「缺 id 或重复 id 拒收」）。
    """
    idx, seen = {}, set()
    for i, x in enumerate(items):
        if not isinstance(x, dict) or not _is_str(x.get("id")) or not x.get("id"):
            return None
        if x["id"] in seen:
            return None
        idx[x["id"]] = (i, x)
        seen.add(x["id"])
    return idx


def check_writeback(old, new):
    """agent 回写白名单 diff → 中文错误清单（空列表 = 放行）。

    白名单（唯一可改）：tasks[].state、tasks[].output、footage[].state、footage[].note
    ——只许改「既有条目」的白名单字段，条目不可增删；tasks[].note 是生成器私有字段，
    它的变化 = 绕过协议，拒收；其余任何节（annotations/version/source_sha256/locked/
    plan/editNotes）整体变化都算越权。new 整体还须过全量 schema 校验（把白名单字段
    写成非法枚举同样拒收）。
    """
    errors = []
    if not isinstance(old, dict) or not isinstance(new, dict):
        return ["old/new 应是 shoot.json 的 dict"]
    old, new = _strip_private(old), _strip_private(new)

    # 整节只读区：任何差异都拒（annotations/editNotes/plan 连字段级机会都没有）
    for k in ("version", "source_sha256", "locked", "annotations", "plan", "editNotes"):
        if old.get(k) != new.get(k):
            errors.append(f"「{k}」被改动——agent 只许改 tasks[].state/output、"
                          f"footage[].state/note")

    # 白名单区：逐条目逐字段
    for sec, wl in AGENT_WHITELIST.items():
        o = old.get(sec) if isinstance(old.get(sec), list) else []
        n = new.get(sec) if isinstance(new.get(sec), list) else []
        om = _index_entries(o)
        nm = _index_entries(n)
        if om is None or nm is None:
            errors.append(f"{sec} 存在缺 id 或重复 id 的条目，拒收")
            continue
        for k in sorted(nm.keys() - om.keys()):
            errors.append(f"新增了 {sec} 条目 {k}——agent 不许增删条目"
                          f"（新增由主控编排器负责）")
        for k in sorted(om.keys() - nm.keys()):
            errors.append(f"删除了 {sec} 条目 {k}——agent 不许增删条目")
        for k in sorted(om.keys() & nm.keys()):
            oi, ov = om[k]
            _, nv = nm[k]
            for f in sorted(set(ov) | set(nv)):
                if ov.get(f) == nv.get(f):
                    continue
                if sec == "tasks" and f == "note":
                    errors.append(f"tasks[{oi}]（{k}）.note 被改动——tasks[].note 是"
                                  f"生成器私有字段，不在 agent 白名单（疑似绕过协议），拒收")
                elif f not in wl:
                    errors.append(f"{sec}[{oi}]（{k}）.{f} 被越权改动（白名单外字段）")

    # 回写结果整体必须仍是合法 shoot.json（白名单字段写成非法枚举同样拒收）
    verrs = [e for e in validate(new) if not e.startswith(_WARN)]
    if verrs:
        errors.extend("回写结果 schema 不过: " + e for e in verrs)
    return errors


def summarize_changes(old, new):
    """白名单内实际改动的摘要行（信息性，供 CLI 打印；不含越权项——越权归错误清单）"""
    lines = []
    if not isinstance(old, dict) or not isinstance(new, dict):
        return lines
    old, new = _strip_private(old), _strip_private(new)
    for sec, wl in AGENT_WHITELIST.items():
        o = old.get(sec) if isinstance(old.get(sec), list) else []
        n = new.get(sec) if isinstance(new.get(sec), list) else []
        om, nm = _index_entries(o), _index_entries(n)
        if om is None or nm is None:
            continue
        for k in sorted(om.keys() & nm.keys()):
            for f in sorted(wl):
                a, b = om[k][1].get(f, ""), nm[k][1].get(f, "")
                if a != b:
                    lines.append(f"{sec}[{k}].{f}: {a!r} → {b!r}")
    return lines


# ---------------------------------------------------------------- CLI


def _load_json_file(path):
    """读 JSON 文件 → (data, 错误消息)。损坏/根不是对象都算错误。"""
    try:
        with open(path, "rb") as f:
            raw = f.read().decode("utf-8")
    except OSError as e:
        return None, f"读不了文件 {path}：{e}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, f"JSON 解析失败（{os.path.basename(path)}）：{e}"
    if not isinstance(data, dict):
        return None, f"文件内容应是 JSON 对象（{os.path.basename(path)}）"
    return data, ""


def main(argv):
    """CLI 入口 → 退出码 0/1"""
    md, against, root = None, None, None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--against":
            if i + 1 >= len(argv):
                print("错误: --against 需要一个参数（回写前快照 json 路径）")
                return 1
            against = argv[i + 1]
            i += 2
            continue
        if a == "--root":
            if i + 1 >= len(argv):
                print("错误: --root 需要一个参数（项目根=素材目录所在层）")
                return 1
            root = argv[i + 1]
            i += 2
            continue
        if a in ("-h", "--help"):
            print(__doc__.strip())
            return 0
        if md is None:
            md = a
        else:
            print(f"错误: 多余的参数 {a!r}")
            return 1
        i += 1
    if md is None:
        print("用法: python shoot_validate.py <定稿md> [--against <回写前快照.json>] "
              "[--root <项目根>]")
        return 1

    print("== shoot.json 校验（S2-E agent 回写自检）==")
    if not os.path.isfile(md):
        print(f"[拒收] md 文件不存在: {md}")
        return 1
    side = shoot_path(md)
    if not os.path.isfile(side):
        print(f"[拒收] 旁车不存在: {side}（应与定稿 md 同目录同名）")
        return 1
    new, err = _load_json_file(side)
    if err:
        print(f"[拒收] {err}")
        return 1

    all_errs = validate(new, md_path=md, root=root)
    hard = [e for e in all_errs if not e.startswith(_WARN)]
    warns = [e for e in all_errs if e.startswith(_WARN)]
    if against:
        old, err = _load_json_file(against)
        if err:
            print(f"[拒收] {err}")
            return 1
        for line in summarize_changes(old, new):
            print(f"[改动] {line}")
        hard.extend(check_writeback(old, new))

    for w in warns:
        print(w)
    if hard:
        print(f"结果: 拒收（{len(hard)} 个硬错误）——按下面清单改到 0 才算完成：")
        for e in hard:
            print(f"[拒收] {e}")
        return 1
    if warns:
        print(f"结果: 通过（{len(warns)} 条警告，请自查完成定义）")
    else:
        print("结果: 通过")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
