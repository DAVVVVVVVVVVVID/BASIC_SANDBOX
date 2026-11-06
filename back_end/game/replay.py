"""
B19 可复现回放（W7）。

输入（同一天、同一镇的三份 JSONL）：
  actions/<date>.jsonl   行动（含 game_time、payload）
  external/<date>.jsonl  外部效果 / 不确定性（self_seed / self_snap / effects_push / adjudication / feed / live / game / nondeterministic）
  state/<date>.jsonl     七变量快照（每 player 每 30 游戏秒）——只用作「起点」与「对账」
再加 seed 与地图（由调用方在 import game.* 之前设 SANDBOX_SEED / SANDBOX_MAP_DIR / SANDBOX_DATA_DIR）。

做法：假时钟；每个 player 从其第一条 state 行起步（vars / position / scene / using），按游戏时间把行动与外部效果合成
一条时间线，事件之间以 1 游戏秒步进跑同一套 buff tick；外部调用（feed / live / game）按日志里的 ok 结果打桩，不打网络。
末态与 state 最后一行逐变量作差（阈值 0.5）。凡是让重放不确定的输入都列在 nondeterministic 里。
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

VARS = ("fullness", "energy", "social", "fun", "mood")


def _ts(iso: str) -> float:
    return datetime.fromisoformat(iso).timestamp()


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            out.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return out


class _FakeClock:
    def __init__(self, t: float):
        self.t = t

    def __call__(self) -> float:
        return self.t


def replay(date: str, data_dir: Path, until: str | None = None, step_s: float = 1.0, threshold: float = 0.5,
           mood_base_by_agent: dict[str, float] | None = None, start_kind: str | None = None) -> dict:
    """mood_base_by_agent：历史 state 行没有 mood_base 时按 agent_id 补（来自自我层 persona 的 OCEAN 基线）。
    start_kind：起点改为该 player 最后一条此 kind（join / rejoin / restore）的行（默认第一条任意行）。"""
    from game import world_state, time_state, self_sync, external_effects, buff_tick
    from routers import actions as actions_mod

    actions = [a for a in _load(data_dir / "actions" / f"{date}.jsonl") if a.get("game_time")]
    external = [e for e in _load(data_dir / "external" / f"{date}.jsonl") if e.get("game_time")]
    # 第四个输入：聊天 JSONL 的房间事件（对话期间 chat_active 让 move / use / leave 失败，影响物品使用时长）
    chat_events = [c for c in _load(data_dir / "chat" / f"{date}.jsonl")
                   if c.get("kind") == "event" and c.get("game_time") and c.get("event") in ("room_open", "player_exit", "room_close", "room_limit")]
    states = _load(data_dir / "state" / f"{date}.jsonl")
    if not states:
        return {"ok": False, "error": "no state samples for that date", "date": date}

    # 起点：每个 player 的第一条 state 行；终点：最后一条
    until_ts = _ts(until) if until else None
    if until_ts is not None:
        states = [r for r in states if _ts(r["game_time"]) <= until_ts]
        if not states:
            return {"ok": False, "error": "no state samples before --until", "date": date}
    first: dict[str, dict] = {}
    last: dict[str, dict] = {}
    for r in states:
        if start_kind:
            if r.get("kind") == start_kind:
                first[r["player_id"]] = r
        else:
            first.setdefault(r["player_id"], r)
        last[r["player_id"]] = r
    if start_kind:
        last = {pid: r for pid, r in last.items() if pid in first}
        if not first:
            return {"ok": False, "error": f"no state rows of kind {start_kind}", "date": date}
    t_start = min(_ts(r["game_time"]) for r in first.values())
    t_end = max(_ts(r["game_time"]) for r in last.values())
    if until:
        t_end = min(t_end, _ts(until))

    # 环境：假时钟、无自我层、外部调用打桩
    world_state._reset_for_tests()
    clock = _FakeClock(t_start)
    time_state.set_clock(clock); time_state.reset_time(); time_state.set_running(True)
    self_sync.configure(enabled=False)
    external_effects.SYNC_STOP = True
    external_effects.fetch_feed = lambda player, iso: {"status": "ok", "items": [], "digest_ts": None, "fetched_at": iso, "for": player.get("agent_id")}
    external_effects.live_start = lambda player, iso: {"ok": True, "resp": {}}
    external_effects.live_stop = lambda player, iso: None
    external_effects.game_start = lambda player, iso: {"ok": True, "game": {"status": "playing", "started_at": iso}}
    external_effects.game_end = lambda player, iso: None
    external_effects.adjudicate = lambda *a, **k: {"success": False, "narration": "", "effects": [], "reason": "adjudication_unavailable"}
    actions_mod.BASE_MOVE_INTERVAL = 0.0
    actions_mod._last_freeform.clear()
    import time as _time
    real_time = _time.time                  # 先存真墙钟，finally 必还原
    world_state.time.time = clock           # _check_auto_leave / 心跳用的墙钟也走假时钟
    try:
        return _replay_body(date, actions, external, states, first, last, t_start, t_end, clock, step_s, threshold,
                            world_state, time_state, buff_tick, actions_mod, mood_base_by_agent or {}, chat_events)
    finally:
        time_state.set_clock(None)
        world_state.time.time = real_time


def _replay_body(date, actions, external, states, first, last, t_start, t_end, clock, step_s, threshold,
                 world_state, time_state, buff_tick, actions_mod, mood_base_by_agent, chat_events) -> dict:
    import asyncio

    # 历史 state 行没有 facing：用该 player 第一条 state 行之前最后一次成功的 turn / 方向 move 推断
    facing_hint: dict[str, str] = {}
    for a in actions:
        pid = a["entityId"]
        if pid not in first or _ts(a["game_time"]) > _ts(first[pid]["game_time"]):
            continue
        d = (a.get("payload") or {}).get("direction")
        if a["type"] in ("turn", "move", "move_n") and d in ("up", "down", "left", "right") and (a["type"] == "turn" or a.get("success")):
            facing_hint[pid] = d

    def spawn(pid: str, r: dict) -> None:
        p = world_state._make_player(pid, pid.rsplit("_", 1)[0], controller=r.get("controller", "human"),
                                     profile={"agent_id": r.get("agent_id")} if r.get("agent_id") else None)
        for v in VARS:
            buff_tick.set_var(p, v, float(r["vars"][v]), track=False)
        if r.get("mood_base") is not None:
            p["mood_base"] = float(r["mood_base"])
        elif r.get("agent_id") in mood_base_by_agent:
            p["mood_base"] = float(mood_base_by_agent[r["agent_id"]])
        p["scene"] = r.get("scene", "sandbox")
        p["position"] = dict(r["position"]); p["closeness"] = dict(r.get("closeness") or {})
        p["online"] = r.get("online", True)
        facing = r.get("facing") or facing_hint.get(pid)
        if facing in ("up", "down", "left", "right"):
            p["facing"] = facing
        with world_state.STATE_LOCK:
            world_state._players[pid] = p
            world_state._pending_messages[pid] = None; world_state._use_start_times[pid] = None
            world_state._last_seen[pid] = clock.t; world_state._last_used.setdefault(pid, {}); world_state._use_history.setdefault(pid, [])
        if r.get("using"):
            world_state.enter_object(r["using"], pid)
    players_in_window = set(first)

    # 时间线：同一游戏秒内按真实毫秒时间戳排序（Q1：join/rejoin/restore 立即采样 + 真实 ts 排序 → 同秒动作无歧义）
    def _real(rec: dict) -> str:
        return rec.get("ts") or rec.get("timestamp") or ""
    events: list[tuple[float, str, int, str, dict]] = []
    for a in actions:
        t = _ts(a["game_time"])
        pid = a["entityId"]
        if pid not in players_in_window or t > t_end:
            continue
        fr = first[pid]
        if (t, _real(a)) < (_ts(fr["game_time"]), _real(fr)):   # 快照之前的动作已含在快照里
            continue
        events.append((t, _real(a), 1, "action", a))
    for pid, r in first.items():
        events.append((_ts(r["game_time"]), _real(r), 0, "spawn", {"player_id": pid, "row": r}))
    # 同步点（W8 Q1）：窗口内后续的 join / rejoin / restore 行记录了重启回填 / 续接那一刻的真实状态
    # （vars、scene、正在用的物品、位置），回放到该时刻按行对齐——重启本身不是动作，没有这一步无法复现
    sync_rows = 0
    for r in states:
        pid = r["player_id"]
        if r.get("kind") in ("join", "rejoin", "restore") and pid in first and r is not first[pid]:
            t = _ts(r["game_time"])
            if t <= t_end:
                events.append((t, _real(r), 0, "sync", {"player_id": pid, "row": r})); sync_rows += 1
    for e in external:
        t = _ts(e["game_time"])
        if t_start <= t <= t_end:
            events.append((t, _real(e), 1, "external", e))
    for c in chat_events:
        t = _ts(c["game_time"])
        if t_start <= t <= t_end:
            events.append((t, _real(c), 1, "chat", c))
    for pid, r in last.items():                                  # 在每个 player 最后一条 state 行的时刻截取回放值
        events.append((_ts(r["game_time"]), _real(r), 2, "capture", {"player_id": pid}))
    events.sort(key=lambda x: (x[0], x[1], x[2]))
    captured: dict[str, dict] = {}
    nondet = [e for _, _, _, k, e in events if k == "external" and e["kind"] in ("nondeterministic", "self_snap", "self_seed")]
    skipped_actions = sum(1 for a in actions if _ts(a["game_time"]) < t_start)

    def advance_to(t: float):
        while clock.t + step_s <= t:
            clock.t += step_s
            world_state._run_buff_tick_all(step_s * 1000.0)
        if clock.t < t:
            dt = t - clock.t; clock.t = t
            world_state._run_buff_tick_all(dt * 1000.0)

    applied = {"actions": 0, "effects_push": 0, "self_seed": 0, "self_snap": 0, "adjudication": 0, "skipped": 0,
               "action_result_mismatch": 0}
    mismatches: list[dict] = []
    for t, _, _, kind, e in events:
        advance_to(t)
        if kind == "spawn":
            spawn(e["player_id"], e["row"]); continue
        if kind == "sync":
            sp = world_state._players.get(e["player_id"]); r = e["row"]
            if sp is None:
                spawn(e["player_id"], r); continue
            for v in VARS:
                buff_tick.set_var(sp, v, float(r["vars"][v]), track=False)
            if r.get("mood_base") is not None:
                sp["mood_base"] = float(r["mood_base"])
            sp["scene"] = r.get("scene", sp.get("scene", "sandbox")); sp["position"] = dict(r["position"])
            if r.get("facing") in ("up", "down", "left", "right"):
                sp["facing"] = r["facing"]
            if sp.get("usingObjectId") != r.get("using"):
                if sp.get("usingObjectId"):
                    world_state.leave_object(e["player_id"])
                if r.get("using"):
                    world_state.enter_object(r["using"], e["player_id"])
            applied["sync_rows"] = applied.get("sync_rows", 0) + 1
            continue
        if kind == "capture":
            cp = world_state._players.get(e["player_id"])
            if cp is not None:
                captured[e["player_id"]] = {v: float(cp[v]) for v in VARS}
            continue
        if kind == "chat":
            from game import chat_state
            ev = e.get("event")
            if ev == "room_open":
                for pid in e.get("participants") or []:
                    if pid in world_state._players:
                        chat_state._apply_chat_buff(pid, world_state._players)
            elif ev == "player_exit":
                pid = e.get("entity")
                if pid in world_state._players:
                    chat_state._remove_chat_buff(pid, world_state._players)
            elif ev in ("room_close", "room_limit"):
                for pid in e.get("participants") or []:
                    if pid in world_state._players:
                        chat_state._remove_chat_buff(pid, world_state._players)
            applied["chat_events"] = applied.get("chat_events", 0) + 1
            continue
        if kind == "action":
            handler = actions_mod._HANDLERS.get(e["type"])
            if handler is None or e["entityId"] not in world_state._players:
                applied["skipped"] += 1; continue
            if e["type"] == "freeform":
                continue                                    # 效果由 external 的 adjudication 行给
            res = handler(e["entityId"], e.get("payload") or {})
            if asyncio.iscoroutine(res):
                res = asyncio.run(res)
            applied["actions"] += 1
            if bool(res.success) != bool(e.get("success", True)):
                applied["action_result_mismatch"] += 1
                if len(mismatches) < 20:
                    mismatches.append({"game_time": e["game_time"], "entity": e["entityId"], "type": e["type"],
                                       "logged": e.get("success"), "logged_reason": e.get("reason"),
                                       "replay": res.success, "replay_reason": res.reason})
        else:
            k = e["kind"]; pid = e.get("entity")
            p = world_state._players.get(pid) if pid else None
            if k == "self_seed" and p is not None:
                for v in VARS:
                    if v in (e.get("vars") or {}):
                        buff_tick.set_var(p, v, float(e["vars"][v]), track=False)
                if e.get("closeness") is not None:
                    p["closeness"] = dict(e["closeness"])
                if e.get("mood_base") is not None:
                    p["mood_base"] = float(e["mood_base"])
                applied["self_seed"] += 1
            elif k == "self_snap" and p is not None:
                for v, d in (e.get("drift") or {}).items():
                    buff_tick.add_var(p, v, float(d), track=False)
                applied["self_snap"] += 1
            elif k == "effects_push" and p is not None:
                world_state.apply_effects(p, e.get("effects") or [], source=e.get("source") or "effects", scene=e.get("scene"), track=False)
                applied["effects_push"] += 1
            elif k == "scenario":
                op = e.get("op"); args = e.get("args") or {}; res_ = e.get("result") or {}
                if op in ("set_vars", "teleport", "occupy", "release", "spawn", "remove", "effects"):
                    target = world_state._players.get(pid) if pid else None
                    if op == "spawn" and res_ and pid not in world_state._players:
                        spawn(pid, {"vars": res_.get("vars", {}), "position": res_.get("position", {"x": 6, "y": 9}),
                                    "controller": res_.get("controller", "agent"), "agent_id": args.get("agent_id"),
                                    "scene": res_.get("scene", "sandbox"), "facing": res_.get("facing"), "online": True})
                    elif op == "remove" and target is not None:
                        world_state.remove_player(pid)
                    elif target is not None:
                        if op == "set_vars":
                            for v, val in (args.get("vars") or {}).items():
                                buff_tick.set_var(target, v, float(val), track=False)
                            if args.get("mood_base") is not None:
                                target["mood_base"] = float(args["mood_base"])
                            if args.get("scene") in ("sandbox", "live"):
                                target["scene"] = args["scene"]
                        elif op == "teleport":
                            if target.get("usingObjectId"):
                                world_state.leave_object(pid)
                            world_state.update_player_position(pid, int(args["x"]), int(args["y"]), args.get("facing") or target["facing"])
                        elif op == "occupy":
                            if res_.get("position"):
                                target["position"] = dict(res_["position"]); target["facing"] = res_.get("facing", target["facing"])
                            world_state.enter_object(args["object"], pid)
                            if args.get("sticky"):
                                world_state._use_start_times[pid] = None
                        elif op == "release":
                            world_state.leave_object(pid)
                        elif op == "effects":
                            world_state.apply_effects(target, args.get("effects") or [], source="scenario", scene=args.get("scene"), track=False)
                applied["scenario"] = applied.get("scenario", 0) + 1
            elif k == "adjudication" and p is not None:
                effs = e.get("effects") or []
                mine = [x for x in effs if x.get("target") in (None, "", "self", pid)]
                world_state.apply_effects(p, mine, source="freeform", track=False)
                for x in effs:
                    tgt = x.get("target")
                    if tgt and tgt not in ("self", pid) and tgt in world_state._players:
                        world_state.apply_effects(world_state._players[tgt], [x], source="freeform", track=False)
                applied["adjudication"] += 1
    advance_to(t_end)

    # 对账
    table = []
    worst = 0.0
    for pid, r in last.items():
        p = captured.get(pid)
        if p is None:
            table.append({"player": pid, "error": "missing after replay"}); worst = 99; continue
        row = {"player": pid, "agent_id": r.get("agent_id"), "at": r["game_time"], "diff": {}, "replay": {}, "actual": {}}
        for v in VARS:
            d = float(p[v]) - float(r["vars"][v])
            row["diff"][v] = round(d, 3); row["replay"][v] = round(float(p[v]), 3); row["actual"][v] = round(float(r["vars"][v]), 3)
            worst = max(worst, abs(d))
        row["max_abs"] = round(max(abs(x) for x in row["diff"].values()), 3)
        table.append(row)
    return {
        "ok": worst < threshold, "threshold": threshold, "worst": round(worst, 3), "date": date,
        "window": {"from": datetime.fromtimestamp(t_start, time_state.GAME_TZ).isoformat(timespec="seconds"),
                   "to": datetime.fromtimestamp(t_end, time_state.GAME_TZ).isoformat(timespec="seconds"),
                   "seconds": round(t_end - t_start)},
        "players": sorted(players_in_window), "state_rows": len(states), "events": len(events), "applied": applied,
        "actions_before_window_skipped": skipped_actions, "nondeterministic": nondet, "table": table,
        "action_mismatches": mismatches,
    }
