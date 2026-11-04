#!/usr/bin/env python3
"""shoot_io.py — 定稿拍摄计划旁车（<md>.shoot.json）读写与校验（S2-A 地基，纯标准库）

职责：呈现批注/拍摄计划/素材表/剪辑批注/补制任务 五节数据的加载、schema 校验、
原子落盘，以及跨 agent 回写白名单检查（S2-E 跨 agent 协议的校验地基在这里做对）。

数据契约（冻结 schema v1，三路并行开发的共同约定，本模块无权改动）：
  - 旁车文件：<定稿md同名>.shoot.json，与 md 同目录（大纲_v3.md → 大纲_v3.md.shoot.json）
  - source_sha256 = 定稿 md 的 sha256——与当前 md 实际指纹不符即拒收
    （外部改动拦截，语义同 draft_server /api/save 的 409）
  - locked = 定稿锁：true 时 md 本体只读（draft_server /api/save 403），
    呈现批注（本旁车）仍可增删改——锁的是稿子，不是拍摄计划
  - annotations[].id 从 R01 起两位顺序编号，定稿后永不变（也是建议文件名主干）
  - agent 回写白名单（唯一可改字段）：tasks[].state、tasks[].output、
    footage[].state、footage[].note——其余任何增删改都非法（check_agent_writeback 拒收）

铁律：纯标准库；md 本体永远只读不写（只碰旁车）；错误信息一律人类可读中文。
"""
import hashlib
import json
import os
import re

VERSION = 1

# 枚举（冻结 schema v1）
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

_ANN_ID_RE = re.compile(r"^R\d{2,}$")   # 呈现批注 id：R + 两位起数字（R01、R99、R100…）


class ShootValidationError(ValueError):
    """schema 校验失败 / 外部改动拦截（消息为换行分隔的中文错误清单）"""


class ShootShaMismatch(ShootValidationError):
    """source_sha256 与 md 当前实际指纹不符——md 已被外部改动，落盘被拒"""


# ---------------------------------------------------------------- 路径与骨架


def shoot_path(md_path):
    """旁车路径：<原名>.shoot.json（与 .review.json 同模式、互不干扰）"""
    return str(md_path) + ".shoot.json"


def _sha256_file(md_path):
    with open(md_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def default_shoot(md_path):
    """默认骨架：source_sha256 取当前 md 实际指纹（旁车不存在时 load 的落点）"""
    return {
        "version": VERSION,
        "source_sha256": _sha256_file(md_path),
        "locked": False,
        "annotations": [],
        "plan": {"checklist_md": "", "ai_tasks_md": ""},
        "footage": [],
        "editNotes": [],
        "tasks": [],
    }


def _fill_defaults(data):
    """补齐缺失节（手写旁车/少节不炸）：只补缺失不纠错——纠错归 validate_shoot"""
    data.setdefault("version", VERSION)
    data.setdefault("source_sha256", "")
    data.setdefault("locked", False)
    data.setdefault("annotations", [])
    data.setdefault("plan", {"checklist_md": "", "ai_tasks_md": ""})
    data.setdefault("footage", [])
    data.setdefault("editNotes", [])
    data.setdefault("tasks", [])
    return data


def load_shoot(md_path):
    """读旁车 → 完整 dict。

    旁车不存在 → 默认骨架（source_sha256=当前 md 指纹，首次保存即可对上）；
    存在 → 解析 + 补齐缺失节。JSON 损坏/根不是对象 → ValueError（中文原因）；
    md 不存在 → FileNotFoundError 冒泡（调用方应先验 isfile，同 draft_server）。
    """
    side = shoot_path(md_path)
    if not os.path.exists(side):
        return default_shoot(md_path)
    with open(side, "rb") as f:
        raw = f.read().decode("utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"旁车 JSON 解析失败（{os.path.basename(side)}）：{e}") from e
    if not isinstance(data, dict):
        raise ValueError(f"旁车内容应是 JSON 对象（{os.path.basename(side)}）")
    return _fill_defaults(data)


def is_locked(md_path):
    """定稿锁状态。旁车不存在/读不出 → False——旁车损坏不该把 md 编辑一起锁死。"""
    try:
        return bool(load_shoot(md_path).get("locked"))
    except (OSError, ValueError):
        return False


# ---------------------------------------------------------------- 校验


def _is_int(x):
    """严格整数（bool 是 int 子类，True 会被当 1——必须排除）"""
    return isinstance(x, int) and not isinstance(x, bool)


def _is_str(x):
    return isinstance(x, str)


def validate_shoot(data):
    """schema 校验 → 中文错误清单（空列表 = 合法）。

    宽进严出：version/source_sha256 必有；缺失的可选节按空处理（跨 agent 手写
    最小旁车也能过）；出现了的字段严格查类型/枚举/引用关系。
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
        quote = a.get("quote", "")
        if not _is_str(quote):
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
        fid = en.get("footage_id")
        if not _is_str(fid):
            # 类型守卫：非字符串（如 list/dict）不可哈希，直接进集合判定会 TypeError 崩溃而非拒收
            errs.append(f"{where}.footage_id 应是字符串: {fid!r}")
        elif fid not in fids:
            errs.append(f"{where}.footage_id 引用不存在的素材: {fid!r}")
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

    # ---- plan：清单宿主 ----
    plan = data.get("plan", {})
    if not isinstance(plan, dict):
        errs.append("plan 应是对象")
    else:
        for k in ("checklist_md", "ai_tasks_md"):
            if k in plan and not _is_str(plan[k]):
                errs.append(f"plan.{k} 应是字符串")
    return errs


def next_ann_id(data):
    """下一个呈现批注 id：已有最大 R 编号 +1，两位起（R01…R09→R10…R99→R100）。

    编号只进不退、不复用——删除 R02 后新建仍是现有最大+1，id 定稿后永不变。
    """
    mx = 0
    anns = data.get("annotations", []) if isinstance(data, dict) else []
    for a in anns:
        m = re.match(r"^R(\d+)$", str(a.get("id", ""))) if isinstance(a, dict) else None
        if m:
            mx = max(mx, int(m.group(1)))
    return f"R{mx + 1:02d}"


# ---------------------------------------------------------------- 落盘


def _strip_private(data):
    """剥掉下划线开头的私有字段（前端匹配缓存 _anchor 等）——旁车只存契约字段"""
    if isinstance(data, dict):
        return {k: _strip_private(v) for k, v in data.items() if not k.startswith("_")}
    if isinstance(data, list):
        return [_strip_private(x) for x in data]
    return data


def save_shoot(md_path, data):
    """全量校验 + md 指纹核对 + 原子写（tmp + os.replace）。

    校验失败 → ShootValidationError；md 指纹与 source_sha256 不符 →
    ShootShaMismatch（外部改动拦截，语义同 draft_server 的 409）。
    两者均为 ValueError 子类，消息即人类可读中文清单。
    """
    errs = validate_shoot(data)
    if errs:
        raise ShootValidationError("shoot.json 校验失败：\n" + "\n".join(errs))
    actual = _sha256_file(md_path)
    if data.get("source_sha256") != actual:
        raise ShootShaMismatch(
            f"md 已被外部修改，保存被拒（旁车指纹 "
            f"{str(data.get('source_sha256'))[:12]}… ≠ 当前 {actual[:12]}…）"
            f"——重新打开核对后再存")
    payload = json.dumps(_strip_private(data), ensure_ascii=False, indent=2)
    tmp = shoot_path(md_path) + ".tmp"
    with open(tmp, "wb") as f:
        f.write(payload.encode("utf-8"))
    os.replace(tmp, shoot_path(md_path))
    return True


# ---------------------------------------------------------------- agent 回写


def check_agent_writeback(old, new):
    """跨 agent 回写检查 → (ok, 中文错误清单)。

    白名单（唯一可改）：tasks[].state、tasks[].output、footage[].state、
    footage[].note——只许改「既有条目」的白名单字段，条目不可增删；
    其余任何字段（annotations/version/source_sha256/locked/plan/editNotes…）
    变化都算越权。new 整体还须过 schema 校验（把白名单字段写成非法枚举同样拒收）。
    """
    errors = []
    if not isinstance(old, dict) or not isinstance(new, dict):
        return False, ["old/new 应是 shoot.json 的 dict"]
    old, new = _strip_private(old), _strip_private(new)  # 私有缓存字段不参与比对

    for k in ("version", "source_sha256", "locked", "annotations", "plan", "editNotes"):
        if old.get(k) != new.get(k):
            errors.append(f"「{k}」被改动——agent 只许改 tasks[].state/output、"
                          f"footage[].state/note")

    for sec, wl in AGENT_WHITELIST.items():
        o = old.get(sec) if isinstance(old.get(sec), list) else []
        n = new.get(sec) if isinstance(new.get(sec), list) else []
        om, nm = {}, {}
        for x in o:
            if isinstance(x, dict) and x.get("id") is not None:
                om[x["id"]] = x
        for x in n:
            if isinstance(x, dict) and x.get("id") is not None:
                nm[x["id"]] = x
        if len(om) != len(o) or len(nm) != len(n):
            errors.append(f"{sec} 存在缺 id 或重复 id 的条目，拒收")
            continue
        for k in sorted(nm.keys() - om.keys()):
            errors.append(f"{sec} 新增条目 {k}——agent 不许增删条目")
        for k in sorted(om.keys() - nm.keys()):
            errors.append(f"{sec} 删除条目 {k}——agent 不许增删条目")
        for k in sorted(om.keys() & nm.keys()):
            for f in sorted(set(om[k]) | set(nm[k])):
                if om[k].get(f) != nm[k].get(f) and f not in wl:
                    errors.append(f"{sec}[{k}].{f} 被越权改动（白名单外字段）")

    verrs = validate_shoot(new)
    if verrs:
        errors.extend("回写结果 schema 不过: " + e for e in verrs)
    return (not errors), errors


if __name__ == "__main__":
    # 冒烟：对命令行给的 md 打印默认骨架与校验结果
    import sys
    if len(sys.argv) < 2:
        print("用法: python shoot_io.py <md路径>")
        sys.exit(1)
    d = load_shoot(sys.argv[1])
    print(json.dumps(d, ensure_ascii=False, indent=2)[:600])
    print("校验:", validate_shoot(d) or "通过")
