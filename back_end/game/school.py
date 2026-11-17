"""
上课系统 v1（world-v1.4.0；方案 docs/class-system-sandbox.md，主播 11-16 拍板，总控 / A / C 对齐）。

- 课表 game/school.json：周一至五 09:00 / 10:45，周二四 14:00 写作选修；每节 90 分钟、9 段、每 10 分钟一段。
- 课案 run/data/<town>/school/<YYYY-MM-DD>.json（A 写，沙盒只读；缺了照常开课、讲授用占位并记 lesson_missing）。
- 课时段内学生坐在课桌上 = 上课中（tag in_class）；每段推 pendingMessage「【课名】原文」；鲸仔每段 5% 打瞌睡（hash 种子可复现，只吞讲授不吞问题）。
- 课中 1 问 / 课末 1–2 问：动作 answer（坐着也能答），当场公布标准答案，落 school/answers.jsonl。
- 考勤：开课 late_after_minutes 内入座 present，之后 late，下课没坐过 absent；离座没回来记 left_early_at；school/attendance.jsonl。
- 下课：在座学生离座（class_over）；出勤 / 迟到者发「课堂笔记」class_notes（meta 逐段原文与 heard / slept / absent）。
- 作业提交箱 homework_box：收 pending / delivered / final 的 compose CD（redo 拒），CD 不没收；同 request_id 同周再交 = 更新 audio；跨周拒；school/submissions.jsonl + 回执 homework_receipt。
- 评分回写 POST /school/grade（A）：推本人 pendingMessage、写 school/grades.jsonl、作业成绩按配置影响心情。
调用方（ticker / 路由）持 STATE_LOCK。
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
from datetime import datetime, timedelta
from pathlib import Path

_CFG_PATH = Path(__file__).parent / "school.json"
_CFG: dict = {}
_LOCK = threading.Lock()                 # 只管 jsonl 写入
_lesson_cache: dict[str, tuple[float, dict | None]] = {}   # date -> (mtime, doc)

_active: dict[str, dict] = {}            # lesson_id -> 进行中（含刚结束待收尾）的课
_done: dict[str, dict] = {}              # lesson_id -> 已结束的课（今天的，给 today / 课末题窗口；跨日清）
_answers: dict[str, dict] = {}           # "<lesson_id>|<qid>|<agent>" -> 作答行
_subs: dict[str, dict] = {}              # request_id -> 提交记录（首次）{week, receipt_id, agent_id, late, audio, first_ts, title}
_WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DOZE_PREFIX = "（刚才走神睡着了）"


# ── 配置 / 路径 ────────────────────────────────────────────────────────────────
def cfg() -> dict:
    """school.json；env SANDBOX_SCHOOL_TERM_START=YYYY-MM-DD 覆盖开学日（bench 在开学前跑课用）。"""
    global _CFG
    if not _CFG:
        _CFG = json.loads(_CFG_PATH.read_text(encoding="utf-8"))
        ts = os.environ.get("SANDBOX_SCHOOL_TERM_START")
        if ts:
            _CFG["term_start"] = ts
        seed = os.environ.get("SANDBOX_SCHOOL_DOZE_SEED")         # v1.4.2：bench 固定瞌睡种子（保证至少掷中一次）
        if seed:
            _CFG.setdefault("doze", {})["seed"] = seed
    return _CFG


def reload_cfg() -> dict:
    global _CFG
    _CFG = {}
    return cfg()


def school_dir() -> Path:
    ov = os.environ.get("SANDBOX_SCHOOL_DIR")
    if ov:
        p = Path(ov)
    else:
        from game.paths import data_dir
        from game.interventions import town
        base = data_dir().resolve()
        root = next((a for a in [base, *base.parents] if a.name == "data"), None)
        p = (root / town() / cfg().get("lesson_dir", "school")) if root is not None else (base / "school")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _append(name: str, row: dict) -> None:
    try:
        with _LOCK:
            with open(school_dir() / name, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _now_ts() -> float:
    from game.time_state import game_now_ts
    return game_now_ts()


def _dt(ts: float) -> datetime:
    from game.time_state import GAME_TZ
    return datetime.fromtimestamp(ts, GAME_TZ)


def _iso(ts: float) -> str:
    return _dt(ts).isoformat(timespec="seconds")


def _wall_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _town() -> str:
    from game.interventions import town
    return town()


def _push(ev: dict) -> None:
    try:
        from routers.ws import hub
        hub.push_event({"type": "lesson", **ev})
    except Exception:
        pass


def _say(pid: str, text: str) -> None:
    """pendingMessage：已有未读的就接在后面（一个 tick 里可能连推讲授 + 提问）。"""
    from game import world_state as ws
    cur = ws._pending_messages.get(pid)
    ws._pending_messages[pid] = f"{cur}\n{text}" if cur else text


# ── 课表 ──────────────────────────────────────────────────────────────────────
def week_of(date: str) -> int | None:
    d0 = datetime.fromisoformat(cfg()["term_start"]).date()
    d = datetime.fromisoformat(date).date()
    if d < d0:
        return None
    return (d - d0).days // 7 + 1


def week_genre(week: int | None) -> str | None:
    ws_ = cfg().get("weeks") or []
    return ws_[week - 1] if week and 1 <= week <= len(ws_) else None


def course_name(course: str) -> str:
    return ((cfg().get("courses") or {}).get(course) or {}).get("name", course)


def students_for(course: str) -> list[str]:
    el = (cfg().get("elective_students") or {}).get(course)
    if el is not None:
        return list(el)
    return list(cfg().get("students") or [])


def day_index(date: str) -> int | None:
    """v1.4.2：按**开学日起算**的星期序号（开学日 = 周一 = 0）。正式开学日 2026-11-23 本就是周一，与日历一致；
    bench 把 SANDBOX_SCHOOL_TERM_START 设成任意一天时，那天就按「第 1 周周一」排课（与 A 的课案生成器 --term-start 同口径）。"""
    d0 = datetime.fromisoformat(cfg()["term_start"]).date()
    d = datetime.fromisoformat(date).date()
    return None if d < d0 else (d - d0).days % 7


def lessons_for_date(date: str) -> list[dict]:
    """当天课表（开学前 / 周末为空）：[{lesson_id, date, start, end, start_ts, end_ts, course, course_name, students}]。"""
    from game.time_state import GAME_TZ
    if week_of(date) is None:
        return []
    d = datetime.fromisoformat(date).date()
    wd = _WEEKDAYS[day_index(date)]
    out = []
    mins = int(cfg().get("lesson_minutes", 90))
    for start, course in (cfg().get("timetable") or {}).get(wd, []):
        h, m = (int(x) for x in start.split(":"))
        st = datetime(d.year, d.month, d.day, h, m, tzinfo=GAME_TZ)
        en = st + timedelta(minutes=mins)
        out.append({"lesson_id": f"{date}-{start.replace(':', '')}-{course}", "date": date, "start": start, "end": en.strftime("%H:%M"),
                    "start_ts": st.timestamp(), "end_ts": en.timestamp(), "course": course, "course_name": course_name(course),
                    "students": students_for(course)})
    return out


def due_ts_for_week(date: str) -> float | None:
    """本周作业截止（配置 'fri 10:45'）。"""
    from game.time_state import GAME_TZ
    spec = (cfg().get("homework") or {}).get("due", "fri 10:45")
    wd, hm = spec.split()
    d = datetime.fromisoformat(date).date()
    di = day_index(date)
    if di is None:
        return None
    target = d + timedelta(days=(_WEEKDAYS.index(wd) - di))            # v1.4.2：按开学日起算的周（同 lessons_for_date）
    h, m = (int(x) for x in hm.split(":"))
    return datetime(target.year, target.month, target.day, h, m, tzinfo=GAME_TZ).timestamp()


def due_label() -> str:
    spec = (cfg().get("homework") or {}).get("due", "fri 10:45")
    wd, hm = spec.split()
    return {"mon": "周一", "tue": "周二", "wed": "周三", "thu": "周四", "fri": "周五", "sat": "周六", "sun": "周日"}.get(wd, wd) + " " + hm


# ── 课案 ──────────────────────────────────────────────────────────────────────
def load_lesson_doc(date: str) -> dict | None:
    f = school_dir() / f"{date}.json"
    try:
        mt = f.stat().st_mtime
    except OSError:
        return None
    c = _lesson_cache.get(date)
    if c and c[0] == mt:
        return c[1]
    try:
        doc = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        doc = None
    _lesson_cache[date] = (mt, doc)
    return doc


def _lesson_mtime(date: str) -> float | None:
    try:
        return (school_dir() / f"{date}.json").stat().st_mtime
    except OSError:
        return None


def _lesson_plan(meta: dict, quiet: bool = False) -> dict:
    """课案里这节的 {title, segments[9 × text], questions[], homework_note, missing}；缺 / 坏 → 占位。quiet：重载时不重复记 lesson_missing。"""
    from game import external_log
    n = int(cfg().get("segments_per_lesson", 9))
    doc = load_lesson_doc(meta["date"]) or {}
    plan = next((l for l in (doc.get("lessons") or []) if l.get("lesson_id") == meta["lesson_id"]), None)
    if plan is None:
        plan = next((l for l in (doc.get("lessons") or []) if l.get("start") == meta["start"] and l.get("course") == meta["course"]), None)
    missing = plan is None
    if missing and not quiet:
        external_log.log("school", None, action="lesson_missing", lesson_id=meta["lesson_id"])
        plan = {}
    segs = [str((s or {}).get("text") or "") for s in sorted(plan.get("segments") or [], key=lambda s: int((s or {}).get("i") or 0))]
    if len(segs) != n and not missing and not quiet:
        external_log.log("school", None, action="segments_count", lesson_id=meta["lesson_id"], got=len(segs), want=n)
    segs = (segs + ["老师今天讲得比较散，没记住要点。"] * n)[:n]
    segs = [s if s.strip() else "老师今天讲得比较散，没记住要点。" for s in segs]
    qs = []
    for q in plan.get("questions") or []:
        if not q.get("qid") or not q.get("text"):
            continue
        phase = q.get("phase") if q.get("phase") in ("mid", "end") else "end"
        after = int(q.get("after_segment") or (5 if phase == "mid" else n))
        qs.append({"qid": str(q["qid"]), "phase": phase, "after_segment": max(1, min(n, after)), "text": str(q["text"]),
                   "answer": q.get("answer"), "explanation": q.get("explanation")})
    return {"title": plan.get("title") or meta["course_name"], "segments": segs, "questions": qs,
            "homework_note": plan.get("homework_note"), "missing": missing}


# ── 教室规则（v1.4.3，主播 11-17）────────────────────────────────────────────
ROOM_MSG = "正在上课，不能打扰学生们上课"
CLEAR_MSG = "马上要上课啦，先出去吧，不能打扰学生们上课。"
_term_override: str | None = None        # POST /admin/school/term_start 热改的开学日（进检查点，优先于 env / 文件）


def set_term_start(date: str) -> dict:
    """不重启改开学日（主镇 11-18 试跑、周五改回 11-23）。立即生效：之后的课表 / 周次 / 截止都按新开学日算。"""
    global _term_override
    datetime.fromisoformat(date)
    _term_override = date
    cfg()["term_start"] = date
    from game import external_log
    external_log.log("school", None, action="term_start", term_start=date)
    return {"term_start": date}


def room_window(gts: float) -> dict | None:
    """此刻教室是否在「课前 clear_before_minutes → 下课」窗口内：返回那节的 meta，否则 None。"""
    pre = int(cfg().get("clear_before_minutes", 10)) * 60
    for meta in lessons_for_date(_dt(gts).strftime("%Y-%m-%d")):
        if meta["start_ts"] - pre <= gts < meta["end_ts"]:
            return meta
    return None


def room_block(arena: str | None, mover: dict | None, gts: float):
    """寻路 / 移动进教室：窗口内非本节学生 → ("in_class", 下课 HH:MM)；否则 None。"""
    if arena != cfg().get("room"):
        return None
    meta = room_window(gts)
    if meta is None:
        return None
    if mover is not None and mover.get("agent_id") in meta["students"] and mover.get("controller") == "agent":
        return None
    return ("in_class", meta["end"])


def _room_door_outside() -> tuple[int, int] | None:
    from game import world_state as ws
    room = cfg().get("room")
    for e in ws._EDGES:
        if e.get("kind") == "door" and e["b"].get("arena") == room:
            return (e["a"]["x"], e["a"]["y"])
    return None


def _clear_room(gts: float, players: dict) -> None:
    """窗口内仍在教室里的非学生（含人类阿蝉）→ 离开物品、停走、移到教室门外一格，推提示。"""
    from game import world_state as ws, external_log
    meta = room_window(gts)
    if meta is None:
        return
    room = cfg().get("room")
    out = _room_door_outside()
    if out is None:
        return
    for p in list(players.values()):
        pos = p.get("position") or {}
        if ws.get_zone_at(pos.get("x", -1), pos.get("y", -1)).get("arena") != room:
            continue
        if p.get("agent_id") in meta["students"] and p.get("controller") == "agent":
            continue
        if p.get("usingObjectId"):
            ws.leave_object(p["id"], "class_clear")
        ws.stop_walk(p["id"], "stopped", "class_clear")
        ws.update_player_position(p["id"], out[0], out[1], "down")
        if p.get("state") in ("walking", "walking_over"):
            p["state"] = "idle"
        _say(p["id"], CLEAR_MSG)
        external_log.log("school", p["id"], action="clear_room", lesson_id=meta["lesson_id"], to={"x": out[0], "y": out[1]})


def chat_blocked(from_p: dict | None, target: dict | None) -> bool:
    """上课中的学生拒外人聊天邀请；同一节课在座的两个学生互邀放行。"""
    if not target or "in_class" not in (target.get("tags") or []):
        return False
    L = _lesson_for(target.get("agent_id"))
    if L is None:
        return False
    fa = (from_p or {}).get("agent_id")
    return not (fa and fa in L["seat"] and L["seat"][fa].get("left_early_at") is None)


# ── 课桌 / 在座 ───────────────────────────────────────────────────────────────
def _seated(players: dict) -> dict[str, str]:
    """agent_id -> player id：此刻坐在配置课桌上的人。"""
    desks = set(cfg().get("desks") or [])
    out = {}
    for p in players.values():
        if p.get("usingObjectId") in desks and p.get("agent_id"):
            out[p["agent_id"]] = p["id"]
    return out


def _player_of(players: dict, aid: str) -> dict | None:
    return next((p for p in players.values() if p.get("agent_id") == aid), None)


def _doze_roll(lesson_id: str, aid: str, i: int) -> bool:
    p = float(((cfg().get("doze") or {}).get("per_segment") or {}).get(aid, 0.0))
    if p <= 0:
        return False
    seed = (cfg().get("doze") or {}).get("seed", "class-v1")
    h = hashlib.sha256(f"{seed}|{_town()}|{lesson_id}|{aid}|{i}".encode()).digest()
    return int.from_bytes(h[:8], "big") / 2 ** 64 < p


# ── tick ──────────────────────────────────────────────────────────────────────
def on_tick(gts: float, players: dict) -> None:
    date = _dt(gts).strftime("%Y-%m-%d")
    _clear_room(gts, players)                                            # v1.4.3：课前 10 分钟起清场
    for lid in [k for k, v in _done.items() if v["date"] != date]:      # 跨日清（课末题窗口最多到下课后 10 分钟）
        _done.pop(lid, None)
    for meta in lessons_for_date(date):
        lid = meta["lesson_id"]
        if lid in _done:
            continue
        if lid not in _active:
            if meta["start_ts"] <= gts < meta["end_ts"]:
                _start(meta, gts)
            else:
                continue
        _advance(_active[lid], gts, players)
    for lid, L in list(_active.items()):                                 # 跨日 / 课表改了也要收尾
        if gts >= L["end_ts"]:
            _advance(L, gts, players)


def _start(meta: dict, gts: float) -> None:
    plan = _lesson_plan(meta)
    _active[meta["lesson_id"]] = {**meta, **plan, "pushed": 0, "seat": {}, "received": {}, "dozing": {}, "q_open": {}, "q_pushed": [], "finished": False,
                                  "plan_mtime": _lesson_mtime(meta["date"])}
    from game import external_log
    external_log.log("school", None, action="start", lesson_id=meta["lesson_id"], course=meta["course"], missing=plan["missing"])
    _push({"event": "start", "lesson_id": meta["lesson_id"], "course": meta["course"], "title": plan["title"], "start": meta["start"], "end": meta["end"]})


def _refresh_plan(L: dict) -> None:
    """A 课中重写课案（讲评课：截止后重写第 2–9 段）：文件 mtime 变了就重载，只换**还没推**的段与**还没推**的题；已推的不动（笔记以收到的为准）。"""
    mt = _lesson_mtime(L["date"])
    if mt is None or mt == L.get("plan_mtime"):
        return
    L["plan_mtime"] = mt
    plan = _lesson_plan(L, quiet=True)
    if plan["missing"]:
        return
    k = L["pushed"]
    L["segments"] = L["segments"][:k] + plan["segments"][k:]
    pushed = set(L["q_pushed"])
    L["questions"] = [q for q in L["questions"] if q["qid"] in pushed] + [q for q in plan["questions"] if q["qid"] not in pushed]
    L["homework_note"] = plan.get("homework_note")
    if k == 0:
        L["title"] = plan["title"]
    from game import external_log
    external_log.log("school", None, action="plan_reloaded", lesson_id=L["lesson_id"], from_segment=k + 1)


def _advance(L: dict, gts: float, players: dict) -> None:
    from game import world_state as ws
    seated = {a: pid for a, pid in _seated(players).items() if a in L["students"]}
    seg_s = int(cfg().get("segment_minutes", 10)) * 60
    late_s = int(cfg().get("late_after_minutes", 10)) * 60
    now_in = gts < L["end_ts"]
    # 入座 / 在座记录（只在课时段内）
    if now_in:
        for aid, pid in seated.items():
            s = L["seat"].setdefault(aid, {"first_ts": gts, "last_seen": gts, "left_early_at": None})
            s["last_seen"] = gts; s["left_early_at"] = None
        for aid, s in L["seat"].items():
            if aid not in seated and s.get("left_early_at") is None:
                s["left_early_at"] = s["last_seen"]
    # tag in_class / stateLabel
    cname = L["course_name"]
    for p in players.values():
        aid = p.get("agent_id")
        on = now_in and aid in seated and seated[aid] == p["id"]
        tags = p.setdefault("tags", [])
        if on and "in_class" not in tags:
            tags.append("in_class")
            p["stateLabel"] = f"{p.get('name')}在上{cname}"
        elif not on and "in_class" in tags and not _in_other_lesson(p, L):
            tags.remove("in_class")
    # 推讲授段
    n = len(L["segments"])
    due = min(n, int((min(gts, L["end_ts"] - 1) - L["start_ts"]) // seg_s) + 1) if gts >= L["start_ts"] else 0
    if L["pushed"] < due:
        _refresh_plan(L)                                                  # 推段前按 mtime 重读（A 讲评课 10:47 重写第 2–9 段）
    while L["pushed"] < due:
        i = L["pushed"] + 1
        _push_segment(L, i, seated, players)
        L["pushed"] = i
        for q in L["questions"]:
            if q["after_segment"] == i and q["qid"] not in L["q_pushed"]:
                _push_question(L, q, seated, seg_s)
    # 收尾
    if gts >= L["end_ts"] and not L["finished"]:
        _finish(L, players, late_s)


def _in_other_lesson(p: dict, L: dict) -> bool:
    return any(o is not L and not o["finished"] and p.get("agent_id") in o["seat"] and o["seat"][p["agent_id"]].get("left_early_at") is None for o in _active.values())


def _push_segment(L: dict, i: int, seated: dict, players: dict) -> None:
    from game import external_log
    text = L["segments"][i - 1]
    for aid in L["students"]:
        rec = L["received"].setdefault(aid, {})
        if aid not in seated:
            rec[str(i)] = "absent"
            continue
        pid = seated[aid]
        prev_slept = rec.get(str(i - 1)) == "slept"
        if _doze_roll(L["lesson_id"], aid, i):
            rec[str(i)] = "slept"
            L["dozing"][aid] = True
            external_log.log("school", pid, action="doze", lesson_id=L["lesson_id"], segment=i)
            _push({"event": "doze", "lesson_id": L["lesson_id"], "entity": pid, "segment": i})
            continue
        rec[str(i)] = "heard"
        L["dozing"][aid] = False
        L.setdefault("last_seg", {})[aid] = {"i": i, "text": text, "dozed_prev": prev_slept}
        _say(pid, (DOZE_PREFIX if prev_slept else "") + f"【{L['course_name']}】{text}")
    note = L.get("homework_note")
    if i == len(L["segments"]) and note and ((cfg().get("courses") or {}).get(L["course"]) or {}).get("required", True):
        for aid, pid in seated.items():
            if L["received"].get(aid, {}).get(str(i)) == "heard":
                _say(pid, f"【作业提醒】{note}")
    _push({"event": "segment", "lesson_id": L["lesson_id"], "segment": i})


def _push_question(L: dict, q: dict, seated: dict, seg_s: int) -> None:
    grace = int(cfg().get("end_question_grace_minutes", 10)) * 60
    deadline = (L["start_ts"] + q["after_segment"] * seg_s) if q["phase"] == "mid" else (L["end_ts"] + grace)
    L["q_open"][q["qid"]] = deadline
    L["q_pushed"].append(q["qid"])
    for aid, pid in seated.items():
        slept = L["received"].get(aid, {}).get(str(q["after_segment"])) == "slept"
        if slept:
            L["dozing"][aid] = False                                    # 被叫醒：打瞌睡只吞讲授不吞问题
        _say(pid, (DOZE_PREFIX if slept else "") + f"【提问 {q['qid']}】{q['text']}（用 answer 作答，qid: {q['qid']}）")   # v1.4.4：题面带 qid
    _push({"event": "question", "lesson_id": L["lesson_id"], "qid": q["qid"], "phase": q["phase"], "deadline": _iso(deadline)})
    try:                                                                # v1.4.4：推题进 external（之前只有 start / answer / doze / end）
        from game import external_log
        for aid, pid in seated.items():
            external_log.log("school", pid, action="question", lesson_id=L["lesson_id"], qid=q["qid"], phase=q["phase"],
                             deadline=_iso(deadline), agent=aid)
        if not seated:
            external_log.log("school", None, action="question", lesson_id=L["lesson_id"], qid=q["qid"], phase=q["phase"],
                             deadline=_iso(deadline), seated=0)
    except Exception:
        pass


def _finish(L: dict, players: dict, late_s: int) -> None:
    from game import world_state as ws, inventory, external_log
    L["finished"] = True
    seated = _seated(players)
    for aid in L["students"]:
        s = L["seat"].get(aid)
        if s is None:
            status = "absent"
        else:
            status = "present" if s["first_ts"] <= L["start_ts"] + late_s else "late"
        p = _player_of(players, aid)
        row = {"ts": _wall_iso(), "game_time": _iso(L["end_ts"]), "town": _town(), "lesson_id": L["lesson_id"], "course": L["course"],
               "agent_id": aid, "player": p["id"] if p else None, "status": status,
               "seated_at": _iso(s["first_ts"]) if s else None, "left_early_at": _iso(s["left_early_at"]) if s and s.get("left_early_at") else None}
        L.setdefault("attendance", {})[aid] = row
        _append("attendance.jsonl", row)
        if status != "absent" and p is not None:
            rec = L["received"].get(aid, {})
            segs = [{"i": i, "text": L["segments"][i - 1] if rec.get(str(i)) == "heard" else None,
                     "status": rec.get(str(i), "absent")} for i in range(1, len(L["segments"]) + 1)]
            meta = {"lesson_id": L["lesson_id"], "course": L["course"], "course_name": L["course_name"], "title": L["title"], "date": L["date"],
                    "owner": aid, "segments": segs}
            inventory.add(p, "class_notes", 1, meta=meta, expires_at=None)
        if aid in seated and p is not None and p["id"] == seated[aid]:
            ws.leave_object(p["id"], "class_over")
            _say(p["id"], f"下课了。《{L['title']}》的课堂笔记放进背包了。")
        elif status != "absent" and p is not None:
            _say(p["id"], f"《{L['title']}》下课了，课堂笔记放进背包了。")
        if p is not None and "in_class" in p.get("tags", []):
            p["tags"].remove("in_class")
    external_log.log("school", None, action="end", lesson_id=L["lesson_id"], attendance={a: r["status"] for a, r in L["attendance"].items()})
    _push({"event": "end", "lesson_id": L["lesson_id"], "attendance": {a: r["status"] for a, r in L["attendance"].items()}})
    _done[L["lesson_id"]] = L
    _active.pop(L["lesson_id"], None)


# ── 作答 ──────────────────────────────────────────────────────────────────────
def _find_question(qid: str, aid: str | None = None, lesson_id: str | None = None, gts: float | None = None):
    """qid 只要求**一节课内**唯一（A 的课案每节从 q1 编起）：带 lesson_id 就按它找；否则优先此刻窗口还开着的那题，再退到任一含此 qid 的课。"""
    cands = [(L, q) for L in list(_active.values()) + list(_done.values()) for q in L["questions"]
             if q["qid"] == qid and (aid is None or aid in L["students"]) and (lesson_id is None or L["lesson_id"] == lesson_id)]
    if gts is not None:
        open_now = [(L, q) for L, q in cands if q["qid"] in L["q_open"] and gts <= L["q_open"][q["qid"]]]
        if open_now:
            return max(open_now, key=lambda x: x[0]["start_ts"])
        pushed = [(L, q) for L, q in cands if q["qid"] in L["q_open"]]
        if pushed:
            return max(pushed, key=lambda x: x[0]["start_ts"])
    return cands[-1] if cands else (None, None)


def answer(player: dict, qid: str, text: str, lesson_id: str | None = None) -> tuple[dict | None, str | None, dict | None]:
    aid = player.get("agent_id")
    gts = _now_ts()
    L, q = _find_question(str(qid or ""), aid, lesson_id, gts)
    if L is None or q["qid"] not in L["q_open"]:
        mine = _lesson_for(aid) or next((x for x in reversed(list(_active.values())) if aid in x["seat"]), None)   # v1.4.4：告诉她现在能答哪几道
        open_qids = [x["qid"] for x in _open_questions(mine, aid, gts)] if mine else []
        return None, "unknown_question", {"qid": qid, "open_qids": open_qids,
                                          "message": f"没有这道题（qid: {qid}）。" + (f"现在能答的：{'、'.join(open_qids)}" if open_qids else "现在没有开着的题。")}
    seated = _seated({player["id"]: player})
    attended = aid in L["seat"]
    if not (aid in seated and not L["finished"]) and not (q["phase"] == "end" and attended):
        return None, "not_in_class", {"qid": qid, "lesson_id": L["lesson_id"]}
    if gts > L["q_open"][q["qid"]]:
        return None, "question_closed", {"qid": qid, "deadline": _iso(L["q_open"][q["qid"]])}
    key = f"{L['lesson_id']}|{q['qid']}|{aid}"
    if key in _answers:
        return None, "already_answered", {"qid": qid}
    t = (text or "").strip()
    if not t:
        return None, "empty_text", {"qid": qid}
    if len(t) > 500:
        t = t[:500]
    row = {"ts": _wall_iso(), "game_time": _iso(gts), "town": _town(), "lesson_id": L["lesson_id"], "course": L["course"], "qid": q["qid"],
           "phase": q["phase"], "agent_id": aid, "player": player["id"], "text": t, "answered_at_segment": L["pushed"],
           "late": gts > L["end_ts"]}
    _answers[key] = row
    _append("answers.jsonl", row)
    from game import external_log
    external_log.log("school", player["id"], action="answer", lesson_id=L["lesson_id"], qid=q["qid"], chars=len(t))
    return {"message": "答好了。" + (f"标准答案：{q['answer']}" if q.get("answer") else "这题下课后老师批。"), "qid": q["qid"], "lesson_id": L["lesson_id"],
            "correct_answer": q.get("answer"), "explanation": q.get("explanation"), "phase": q["phase"]}, None, None


# ── 视图 ──────────────────────────────────────────────────────────────────────
def _lesson_for(aid: str | None) -> dict | None:
    if not aid:
        return None
    for L in _active.values():
        if aid in L["students"] and not L["finished"] and aid in L["seat"] and L["seat"][aid].get("left_early_at") is None:
            return L
    return None


def _open_questions(L: dict, aid: str | None, gts: float) -> list[dict]:
    """此刻开着、她还没答的题（按课案顺序）。"""
    return [{"qid": q["qid"], "text": q["text"], "phase": q["phase"], "deadline": _iso(L["q_open"][q["qid"]])}
            for q in L["questions"]
            if q["qid"] in L["q_open"] and gts <= L["q_open"][q["qid"]] and f"{L['lesson_id']}|{q['qid']}|{aid}" not in _answers]


def lesson_view(player: dict) -> dict | None:
    """GET /player.lesson / perceive lesson：此刻在课桌上上课才有，否则 None。"""
    aid = player.get("agent_id")
    L = _lesson_for(aid)
    if L is None:
        return None
    gts = _now_ts()
    seg_s = int(cfg().get("segment_minutes", 10)) * 60
    last = (L.get("last_seg") or {}).get(aid)
    open_qs = _open_questions(L, aid, gts)
    pending_q = open_qs[-1] if open_qs else None                       # 照旧：最后一道开着没答的；全部见 questions[]（v1.4.4）
    s = L["seat"].get(aid)
    late_s = int(cfg().get("late_after_minutes", 10)) * 60
    nxt = L["start_ts"] + L["pushed"] * seg_s
    return {"lesson_id": L["lesson_id"], "course": L["course"], "course_name": L["course_name"], "title": L["title"],
            "start": L["start"], "end": L["end"], "segment_i": L["pushed"],
            "segment": {"i": last["i"], "text": last["text"]} if last else None,
            "dozed_prev": bool(last and last.get("dozed_prev")),
            "dozing": bool(L["dozing"].get(aid)),
            "question": pending_q,
            "questions": open_qs,
            "attendance": ("present" if s and s["first_ts"] <= L["start_ts"] + late_s else "late") if s else None,
            "next_segment_at": _iso(nxt) if L["pushed"] < len(L["segments"]) and nxt < L["end_ts"] else None}


def lesson_compact(player: dict) -> dict | None:
    v = lesson_view(player)
    return {k: v[k] for k in ("lesson_id", "course", "title", "dozing")} if v else None


def timetable_view() -> dict:
    c = cfg()
    from game.time_state import game_now_ts
    date = _dt(game_now_ts()).strftime("%Y-%m-%d")
    w = week_of(date)
    return {"schema": c.get("schema"), "term_start": c.get("term_start"), "term_start_source": "admin" if _term_override else ("env" if os.environ.get("SANDBOX_SCHOOL_TERM_START") else "config"),
            "weeks": c.get("weeks"), "week": w, "week_genre": week_genre(w),
            "courses": c.get("courses"), "timetable": c.get("timetable"), "lesson_minutes": c.get("lesson_minutes"),
            "segment_minutes": c.get("segment_minutes"), "segments_per_lesson": c.get("segments_per_lesson"),
            "late_after_minutes": c.get("late_after_minutes"), "students": c.get("students"), "elective_students": c.get("elective_students"),
            "room": c.get("room"), "desks": c.get("desks"), "homework_due": c.get("homework", {}).get("due")}


def today_view(player: dict | None) -> dict:
    gts = _now_ts()
    date = _dt(gts).strftime("%Y-%m-%d")
    aid = (player or {}).get("agent_id")
    w = week_of(date)
    out = []
    late_s = int(cfg().get("late_after_minutes", 10)) * 60
    for meta in lessons_for_date(date):
        L = _active.get(meta["lesson_id"]) or _done.get(meta["lesson_id"])
        status = "done" if (L and L["finished"]) or gts >= meta["end_ts"] else ("ongoing" if L else "upcoming")
        att = {}
        for a in meta["students"]:
            if L and L.get("attendance", {}).get(a):
                att[a] = L["attendance"][a]["status"]
            elif L and a in L["seat"]:
                att[a] = "present" if L["seat"][a]["first_ts"] <= meta["start_ts"] + late_s else "late"
            else:
                att[a] = "absent" if status == "done" else None
        out.append({"lesson_id": meta["lesson_id"], "course": meta["course"], "course_name": meta["course_name"],
                    "title": (L or {}).get("title") or meta["course_name"], "start": meta["start"], "end": meta["end"], "status": status,
                    "mine": aid in meta["students"], "my_attendance": att.get(aid) if aid else None, "attendance": att})
    hw = homework_view(aid, date) if aid else None
    return {"date": date, "week": w, "week_genre": week_genre(w), "lessons": out, "homework": hw}


def homework_view(aid: str, date: str) -> dict:
    w = week_of(date)
    due = due_ts_for_week(date)
    rows = sorted([s for s in _subs.values() if s["agent_id"] == aid and s["week"] == w], key=lambda s: s["first_ts"])
    return {"week": w, "due": _iso(due) if due else None, "count": len(rows),
            "submitted": [{"receipt_id": s["receipt_id"], "request_id": s["request_id"], "title": s["title"], "late": s["late"],
                           "audio": s["audio"], "at": _iso(s["first_ts"])} for s in rows]}


# ── 笔记 ──────────────────────────────────────────────────────────────────────
def notes_text(meta: dict) -> str:
    parts = [f"《{meta.get('title')}》课堂笔记（{meta.get('date')}，{meta.get('course_name') or course_name(meta.get('course', ''))}）"]
    for s in meta.get("segments") or []:
        if s.get("status") == "heard" and s.get("text"):
            parts.append(f"{s['i']}. {s['text']}")
        elif s.get("status") == "slept":
            parts.append(f"{s['i']}. ……（这段睡着了）")
        else:
            parts.append(f"{s['i']}. （没来）")
    return "\n".join(parts)


# ── 作业提交 ───────────────────────────────────────────────────────────────────
SHEET_KEYS = ("title", "genre", "scene", "mood", "form", "chords", "arrangement")


def _audio_of(meta: dict) -> str:
    if meta.get("status") == "final":
        return "final"
    if meta.get("proxy"):
        return "pending"
    return "none"


def _sheet_complete(meta: dict) -> bool:
    ok = all(str(meta.get(k) or "").strip() for k in SHEET_KEYS)
    return ok


def submit(player: dict, request_id: str | None) -> tuple[dict | None, str | None, dict | None]:
    from game import inventory
    aid = player.get("agent_id") or player["id"]
    gts = _now_ts()
    date = _dt(gts).strftime("%Y-%m-%d")
    w = week_of(date)
    cds = [e for e in inventory.ensure(player) if e.get("type") == "cd"]
    if request_id:
        cds = [e for e in cds if (e.get("meta") or {}).get("request_id") == request_id]
        if not cds:
            return None, "no_item", {"item": "cd", "request_id": request_id}
        entry = cds[0]
    else:
        fresh = [e for e in cds if (e.get("meta") or {}).get("request_id") not in _subs]
        if not cds:
            return None, "no_item", {"item": "cd"}
        entry = (fresh or cds)[-1]
    meta = dict(entry.get("meta") or {})
    rid = meta.get("request_id") or f"cd-{meta.get('title', '')}-{meta.get('created_at', '')}"
    if meta.get("status") == "redo":
        return None, "cd_redo", {"request_id": rid, "title": meta.get("title"), "message": "这首判了重做，交重做后的那张。"}
    prev = _subs.get(rid)
    due = due_ts_for_week(date)
    audio = _audio_of(meta)
    if prev is not None:
        if prev["week"] != w:
            return None, "already_submitted", {"request_id": rid, "receipt_id": prev["receipt_id"], "week": prev["week"]}
        prev["audio"] = audio; prev["meta"] = meta
        row = {"ts": _wall_iso(), "game_time": _iso(gts), "town": _town(), "action": "update", "week": w, "agent_id": aid, "request_id": rid,
               "title": meta.get("title"), "receipt_id": prev["receipt_id"], "late": prev["late"], "audio": audio,
               "creation_sheet_complete": _sheet_complete(meta), "meta": meta}
        _append("submissions.jsonl", row)
        _update_receipt(player, prev)
        return {"message": f"《{meta.get('title')}》的提交更新了（音频：{audio}）。", "receipt_id": prev["receipt_id"], "late": prev["late"],
                "due": _iso(due) if due else None, "audio": audio, "updated": True, "request_id": rid}, None, None
    late = bool(due and gts > due)
    receipt_id = f"hw-{date.replace('-', '')}-{secrets.token_hex(3)}"
    rec = {"week": w, "receipt_id": receipt_id, "agent_id": aid, "late": late, "audio": audio, "first_ts": gts, "title": meta.get("title"),
           "request_id": rid, "meta": meta}
    _subs[rid] = rec
    row = {"ts": _wall_iso(), "game_time": _iso(gts), "town": _town(), "action": "submit", "week": w, "agent_id": aid, "request_id": rid,
           "title": meta.get("title"), "receipt_id": receipt_id, "late": late, "audio": audio, "creation_sheet_complete": _sheet_complete(meta), "meta": meta}
    _append("submissions.jsonl", row)
    inventory.add(player, "homework_receipt", 1, meta={"receipt_id": receipt_id, "week": w, "request_id": rid, "title": meta.get("title"), "late": late,
                                                       "audio": audio, "due": _iso(due) if due else None, "submitted_at": _iso(gts)}, expires_at=None)
    from game import external_log
    external_log.log("school", player["id"], action="submit", request_id=rid, receipt_id=receipt_id, late=late, audio=audio)
    return {"message": f"《{meta.get('title')}》交上了" + ("（迟交）。" if late else "。") + f"回执 {receipt_id}。", "receipt_id": receipt_id,
            "late": late, "due": _iso(due) if due else None, "audio": audio, "updated": False, "request_id": rid}, None, None


def _update_receipt(player: dict, rec: dict) -> None:
    from game import inventory
    for e in inventory.ensure(player):
        if e.get("type") == "homework_receipt" and (e.get("meta") or {}).get("receipt_id") == rec["receipt_id"]:
            e["meta"] = {**e["meta"], "audio": rec["audio"]}


def on_cd_final(player: dict, meta: dict) -> None:
    """她 edit_item 把 CD 标 final：同一周的那条提交顺带更新 audio（跨周不更新）。"""
    rid = meta.get("request_id")
    rec = _subs.get(rid or "")
    if rec is None:
        return
    gts = _now_ts()
    if rec["week"] != week_of(_dt(gts).strftime("%Y-%m-%d")):
        return
    rec["audio"] = "final"; rec["meta"] = dict(meta)
    _append("submissions.jsonl", {"ts": _wall_iso(), "game_time": _iso(gts), "town": _town(), "action": "update", "week": rec["week"],
                                  "agent_id": rec["agent_id"], "request_id": rid, "title": meta.get("title"), "receipt_id": rec["receipt_id"],
                                  "late": rec["late"], "audio": "final", "creation_sheet_complete": _sheet_complete(meta), "meta": dict(meta), "via": "cd_final"})
    _update_receipt(player, rec)


# ── 评分回写 ───────────────────────────────────────────────────────────────────
def grade(players: dict, body: dict) -> tuple[dict | None, str | None]:
    from game.buff_tick import add_var
    aid = body.get("agent_id")
    p = _player_of(players, aid)
    g = str(body.get("grade") or "").upper()
    if g not in ("A", "B", "C"):
        return None, "bad_grade"
    kind = body.get("kind") or "writing"
    comment = str(body.get("comment") or "")[:200]
    row = {"ts": _wall_iso(), "game_time": _iso(_now_ts()), "town": _town(), "agent_id": aid, "kind": kind, "grade": g, "comment": comment,
           "lesson_id": body.get("lesson_id"), "qid": body.get("qid"), "receipt_id": body.get("receipt_id")}
    _append("grades.jsonl", row)
    label = {"writing": "写作课成绩", "homework": "作业成绩"}.get(kind, "成绩")
    if p is not None:
        _say(p["id"], f"{label}：{g}" + (f"，评语：{comment}" if comment else ""))
        if kind == "homework":
            d = float(((cfg().get("homework") or {}).get("grade_mood") or {}).get(g, 0))
            if d:
                add_var(p, "mood", d)
        _push({"event": "grade", "entity": p["id"], "kind": kind, "grade": g})
    return {"ok": True, "delivered": p is not None, **row}, None


# ── 检查点 ─────────────────────────────────────────────────────────────────────
def export_state() -> dict:
    return {"active": {k: dict(v) for k, v in _active.items()}, "done": {k: dict(v) for k, v in _done.items()},
            "answers": dict(_answers), "subs": {k: dict(v) for k, v in _subs.items()}, "term_start_override": _term_override}


def import_state(d: dict) -> None:
    global _term_override
    _active.clear(); _done.clear(); _answers.clear(); _subs.clear()
    _term_override = d.get("term_start_override")
    if _term_override:
        cfg()["term_start"] = _term_override
    _active.update({k: dict(v) for k, v in (d.get("active") or {}).items()})
    _done.update({k: dict(v) for k, v in (d.get("done") or {}).items()})
    _answers.update(d.get("answers") or {})
    _subs.update({k: dict(v) for k, v in (d.get("subs") or {}).items()})


def _reset_for_tests() -> None:
    global _term_override
    _active.clear(); _done.clear(); _answers.clear(); _subs.clear(); _lesson_cache.clear()
    _term_override = None
    reload_cfg()
