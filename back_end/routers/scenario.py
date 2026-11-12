"""
行为验收台夹具（W8 Q0b，docs/behavior-acceptance.md「分工 B」）：POST /admin/scenario 一次把世界摆成指定状态。

只在环境变量 SANDBOX_SCENARIO=1 的实例开放（运行台主镇不开；townctl 的 bench 镇开），否则 403。
body: {"label": "S01", "steps": [ {op, ...}, ... ]}，按序执行，遇错即停（HTTP 200，ok=false，error 指出第几步）。
每步都写 external 日志（kind=scenario），受影响玩家立即写一行 state（kind=scenario），所以摆放对回放 / 数据集可见。

op 一览（player 字段可填 id 或唯一的 name）：
  reset          {}                                   清空所有玩家 / 对话 / 物品占用 / 冷却 / 待发同步，时间回真实当前
  set_time       {time:"11:30", date?:"YYYY-MM-DD", speed?:1, running?:true}   游戏时间拨到（锚点重设，之后照常走）
  spawn          {name, agent_id?, controller?:"agent", x?, y?, facing?, vars?}  放一个玩家（默认 agent；不传坐标→出生点）
  remove         {player}
  teleport       {player, x, y, facing?}             必须是可走格
  set_vars       {player, vars:{fullness,energy,social,fun,mood}, mood_base?, scene?, closeness?}  七变量直写
  effects        {player, effects:[...], scene?}     与 /effects 同格式（source="scenario"）
  occupy         {player, object, sticky?:false}     让玩家占住某物品（跳过距离 / 冷却 / 营业时间 / 外部调用；不记冷却，解除后可立刻再用）；sticky=true 关掉 max_duration 自动离开
  release        {player}                            离开正在用的物品
  invite         {from, to:[...], greeting}          代某玩家发邀请（跳过冷却）→ 返回 request_id
  respond        {player, request_id, accept, message}
  say            {player, room, text}
  exit_chat      {player, room}
  clear_cooldowns {player?}                          清物品冷却、每日使用时长（v1.1）与对话冷却
  set_gold       {player, gold}                      把余额写成 gold（流水 adjust，账户同步；v1.1 验收 S12）
  set_supply     {shop, item, qty}                   写商店当日上新量 daily_supply（08:00 补货按它；S11 清零杂货店食物）
"""

import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from game import world_state, chat_state, time_state, external_log, state_log, self_sync

router = APIRouter()
VARS = ("fullness", "energy", "social", "fun", "mood")


class ScenarioRequest(BaseModel):
    label: str | None = None
    steps: list[dict[str, Any]]


def enabled() -> bool:
    return os.environ.get("SANDBOX_SCENARIO", "0") in ("1", "true", "True")


class StepError(Exception):
    pass


def _resolve(ref: str | None) -> str:
    """player 引用：id 或唯一 name。"""
    if not ref:
        raise StepError("player required")
    if ref in world_state._players:
        return ref
    hits = [pid for pid, p in world_state._players.items() if p.get("name") == ref]
    if len(hits) == 1:
        return hits[0]
    raise StepError(f"player not found or ambiguous: {ref}")


def _player(ref: str) -> dict:
    return world_state._players[_resolve(ref)]


def _brief(p: dict) -> dict:
    return {"id": p["id"], "name": p["name"], "controller": p.get("controller"), "position": dict(p["position"]),
            "facing": p["facing"], "state": p["state"], "usingObjectId": p.get("usingObjectId"), "scene": p.get("scene"),
            "vars": {k: round(float(p[k]), 3) for k in VARS}}


# ── ops ──────────────────────────────────────────────────────────────────────

def op_reset(step: dict) -> dict:
    with world_state.STATE_LOCK:
        for pid in list(world_state._players):
            world_state.remove_player(pid)
        world_state._reset_for_tests()
        chat_state._reset_for_tests()
        from game import economy, production, commissions, doors, speech
        economy._reset_for_tests(); production._reset_for_tests(); commissions._reset_for_tests(); doors._reset_for_tests(); speech._reset_for_tests()   # X5：补货 / 日薪已付记录等一起归零
    time_state.reset_time()
    if step.get("running") is not None:
        time_state.set_running(bool(step["running"]))
    return {"players": 0, "time": time_state.get_time_state()}


def op_set_time(step: dict) -> dict:
    from datetime import datetime
    t = step.get("time")
    if not t:
        raise StepError("time required (HH:MM or HH:MM:SS)")
    now = time_state.game_now()
    date = step.get("date") or now.strftime("%Y-%m-%d")
    parts = [int(x) for x in t.split(":")]
    while len(parts) < 3:
        parts.append(0)
    target = datetime(*[int(x) for x in date.split("-")], parts[0], parts[1], parts[2], tzinfo=time_state.GAME_TZ)
    with world_state.STATE_LOCK:
        time_state._state["anchor_real"] = time_state.now_real()
        time_state._state["anchor_game"] = target.timestamp()
        if step.get("speed") is not None:
            time_state._state["speed"] = max(time_state.MIN_SPEED, float(step["speed"]))
        if step.get("running") is not None:
            time_state._state["running"] = bool(step["running"])
        world_state.update_weather(time_state.game_now_ts())
    return time_state.get_time_state()


def op_spawn(step: dict) -> dict:
    name = step.get("name")
    if not name:
        raise StepError("name required")
    controller = step.get("controller", "agent")
    profile = dict(step.get("profile") or {})
    if step.get("agent_id"):
        profile["agent_id"] = step["agent_id"]
    player = world_state.create_player(name, controller=controller, profile=profile or None)
    pid = player["id"]
    if step.get("x") is not None and step.get("y") is not None:
        op_teleport({"player": pid, "x": step["x"], "y": step["y"], "facing": step.get("facing")})
    if step.get("vars"):
        op_set_vars({"player": pid, "vars": step["vars"]})
    from game import self_sync
    self_sync.assert_local(pid)                       # W11 维护：夹具摆的值以本地为准，不被自我层旧值 snap 回去
    pushed = self_sync.push_local_now(world_state._players[pid], world_state.game_now_ts())   # 并立刻推给自我层，开局即一致
    return {**_brief(world_state._players[pid]), "self_push": pushed}


def op_remove(step: dict) -> dict:
    pid = _resolve(step.get("player"))
    world_state.remove_player(pid)
    return {"removed": pid}


def op_teleport(step: dict) -> dict:
    p = _player(step.get("player"))
    x, y = int(step["x"]), int(step["y"])
    if not world_state.is_tile_walkable(x, y):
        raise StepError(f"tile ({x},{y}) not walkable")
    facing = step.get("facing") or p["facing"]
    if facing not in ("up", "down", "left", "right"):
        raise StepError("facing must be up/down/left/right")
    with world_state.STATE_LOCK:
        if p.get("usingObjectId"):
            world_state.leave_object(p["id"])
        world_state.stop_walk(p["id"], "stopped", "teleport")      # §3.36
        world_state.update_player_position(p["id"], x, y, facing)
        p["state"] = "idle" if p["state"] in ("walking", "walking_over") else p["state"]
    return _brief(p)


def op_set_vars(step: dict) -> dict:
    from game.buff_tick import set_var
    p = _player(step.get("player"))
    vars_ = step.get("vars") or {}
    bad = [k for k in vars_ if k not in VARS and k != "hp"]
    if bad:
        raise StepError(f"unknown vars: {bad}")
    with world_state.STATE_LOCK:
        for k, v in vars_.items():
            set_var(p, k, float(v), track=False)
        if step.get("mood_base") is not None:
            p["mood_base"] = float(step["mood_base"])
        if step.get("scene") in ("sandbox", "live"):
            p["scene"] = step["scene"]
        if isinstance(step.get("closeness"), dict):
            p["closeness"] = {k: float(v) for k, v in step["closeness"].items()}
    from game import self_sync
    self_sync.assert_local(p["id"])                   # W11 维护：见 self_sync.assert_local
    pushed = self_sync.push_local_now(p, world_state.game_now_ts())
    return {**_brief(p), "self_push": pushed}


def op_effects(step: dict) -> dict:
    pid = _resolve(step.get("player"))
    res = world_state.apply_effects_to_player(pid, step.get("effects") or [], step.get("scene"), source="scenario", event=step.get("event"))
    return {**res["summary"], "player": _brief(res["player"])}


def op_occupy(step: dict) -> dict:
    p = _player(step.get("player"))
    obj = world_state.get_object_by_id(step.get("object") or "")
    if obj is None:
        raise StepError(f"object not found: {step.get('object')}")
    if obj.get("prototype") != "continuous":
        raise StepError("occupy only for continuous objects")
    if p["id"] not in obj["userList"] and obj["currentUsers"] >= (obj.get("maxUsers") or 1):
        raise StepError("object_full")
    with world_state.STATE_LOCK:
        if p.get("usingObjectId") and p["usingObjectId"] != obj["id"]:
            world_state.leave_object(p["id"])
        # 站到相邻可走格、面向物品（有则）；没有相邻格也直接进入
        for t in obj["tiles"]:
            for dx, dy, face in ((0, 1, "up"), (0, -1, "down"), (1, 0, "left"), (-1, 0, "right")):
                sx, sy = t["x"] + dx, t["y"] + dy
                if world_state.is_tile_walkable(sx, sy):
                    world_state.update_player_position(p["id"], sx, sy, face)
                    break
            else:
                continue
            break
        world_state.enter_object(obj["id"], p["id"])
        if obj.get("externalKeysApplied"):
            pass
        for e in obj["effects"]:                       # external：直播台 / 游戏机只做本地状态，不打外部服务
            if e.get("type") == "external" and e.get("key") == "live":
                p["scene"] = "live"
        # X5 pilot ②：夹具驱动的占用不算「用过」——不记冷却 / 使用史，并清掉这件物品已有的冷却，解除后她能立刻回来续上
        world_state._last_used.get(p["id"], {}).pop(obj["id"], None)
        if step.get("sticky"):
            world_state._use_start_times[p["id"]] = None   # 不触发 max_duration 自动离开
    return _brief(p)


def op_release(step: dict) -> dict:
    p = _player(step.get("player"))
    with world_state.STATE_LOCK:
        obj = world_state.leave_object(p["id"])
    return {"left": obj["id"] if obj else None, "player": _brief(p)}


def op_invite(step: dict) -> dict:
    frm = _resolve(step.get("from"))
    tos = [_resolve(t) for t in (step.get("to") or [])]
    if not tos:
        raise StepError("to required")
    rid = chat_state.create_chat_request(frm, tos, step.get("greeting") or "")
    return {"request_id": rid, "from": frm, "to": tos}


def op_respond(step: dict) -> dict:
    pid = _resolve(step.get("player"))
    res = chat_state.respond_to_request(pid, step.get("request_id") or "", bool(step.get("accept", True)),
                                        step.get("message") or "", world_state._players)
    if step.get("tick", True):
        chat_state.tick()
    req = chat_state._chat_requests.get(step.get("request_id") or "")
    return {**res, "status_now": req["status"] if req else None, "chat_room_id": req["chat_room_id"] if req else None}


def op_say(step: dict) -> dict:
    """{player, text, room?}：有 room 走房间发言；没 room 走 Q6 的「靠近即可说」（X4 say / GA 变体的脚本小千）。"""
    pid = _resolve(step.get("player"))
    if not step.get("room"):
        from game import speech
        with world_state.STATE_LOCK:
            res, reason = speech.say(pid, str(step.get("text") or ""))
        if reason:
            raise StepError(f"say: {reason}")
        return res
    res = chat_state.post_message(pid, step.get("room") or "", step.get("text") or "")
    if res is None:
        raise StepError("room not found or closed")
    if res.get("error"):
        raise StepError(f"say: {res['error']}")
    return res


def _parse_until(step: dict) -> float | None:
    """until: "HH:MM"（今天 / 已过则明天）| ISO | null（直到清除）。"""
    from datetime import datetime, timedelta
    from game.time_state import GAME_TZ, game_now
    u = step.get("until")
    if u in (None, "", "null"):
        return None
    if isinstance(u, str) and len(u) in (5,) and ":" in u:
        h, m = u.split(":"); now = game_now()
        t = now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
        if t <= now:
            t += timedelta(days=1)
        return t.timestamp()
    return datetime.fromisoformat(str(u)).timestamp()


def _pin_restock_today(obj: dict) -> str | None:
    """X5 pilot ①：夹具写过的库存就是「今天补货后的水位」——若当前游戏时刻已过该物品的 restock_at，把今天的补货记为已做，
    否则 reset 清掉补货记录后下一 tick 会立刻补货把夹具值盖掉（R1 set_fridge 0 → 冰箱又有 2 份）。
    返回 (被钉住的 key 或 None, 状态)：pinned / already_restocked_today（今天已补过，夹具值同样保持）/ before_restock_at（到点会补）。"""
    from game import economy
    from game.time_state import _game_dt
    dt = _game_dt(world_state.game_now_ts()); day = dt.strftime("%Y-%m-%d"); hm = dt.strftime("%H:%M")
    s = economy.shop_for(obj["type"])
    at = (s or {}).get("restock_at") if s is not None else economy.cfg().get("fridge", {}).get("restock_at", "08:00")
    key = f"{obj['id']}:{day}"
    if hm < (at or "08:00"):
        return None, "before_restock_at"              # 今天还没到补货时刻：到点会照常补（夹具值会被补上去）
    if key in economy._restocked:
        return None, "already_restocked_today"        # 今天已补过（例如 set_time 与 set_fridge 之间插进了一个 tick）：夹具值直接保持
    economy._restocked[key] = hm
    return key, "pinned"                              # 本次把今天的补货记为已做


def op_set_fridge(step: dict) -> dict:
    """X5：直接写冰箱库存 {id, qty}（含 0）；当天已过补货时刻则同时钉住今天的补货（直到次日 restock_at 或下一次 set_fridge）。"""
    from game.economy import cfg
    obj = world_state.get_object_by_id(step.get("id") or step.get("object") or "fridge_home")
    if obj is None or obj["type"] != "fridge":
        raise StepError(f"fridge not found: {step.get('id')}")
    from game import food, inventory
    item = step.get("item") or cfg().get("fridge", {}).get("consumes", "ingredients")
    if inventory.item_def(item) is None:
        raise StepError(f"unknown item: {item}")
    with world_state.STATE_LOCK:
        qty = max(0, int(step.get("qty", 0)))
        if "item" not in step:                                       # 不带 item：整台冰箱 = qty 份默认食材（qty 0 = 清空，R1「资源不可得」）
            obj["contents"] = []
        elif step.get("clear", True):                                # 带 item：只重写这一种（其他种类不动）
            obj["contents"] = [c for c in (obj.get("contents") or []) if c["item"] != item]
        if qty:
            food.store(obj, item, qty, inventory.expires_at_for(item, world_state.game_now_ts()))
        food.refresh_stock(obj)
        pinned, state = _pin_restock_today(obj)
    return {"id": obj["id"], "stock": dict(obj["stock"]), "contents": food.contents_view(obj, world_state.game_now_ts()), "restock_pinned": pinned, "restock_state": state}


def op_set_supply(step: dict) -> dict:
    """world-v1.1 验收夹具（S11）：写商店某物品的当日上新量 daily_supply（08:00 补货按它；0 = 今天不上这货），stock 不动（要清今日剩余另用 set_stock）。"""
    from game import inventory
    obj = world_state.get_object_by_id(step.get("shop") or step.get("object") or "")
    if obj is None or obj.get("daily_supply") is None:
        raise StepError(f"shop not found: {step.get('shop')}")
    item = step.get("item") or ""
    if inventory.item_def(item) is None:
        raise StepError(f"unknown item: {item}")
    with world_state.STATE_LOCK:
        obj["daily_supply"][item] = max(0, int(step.get("qty", 0)))
    return {"shop": obj["id"], "daily_supply": dict(obj["daily_supply"]), "stock": dict(obj["stock"])}


def op_set_gold(step: dict) -> dict:
    """world-v1.1 验收夹具：直接把某玩家余额写成 gold（走 ledger kind adjust，账户同步；R6「房租到期前钱不够」用）。"""
    from game import economy
    p = _player(step.get("player"))
    target = int(step.get("gold", 0))
    with world_state.STATE_LOCK:
        delta = target - int(p.get("gold", 0))
        if delta:
            economy.ledger("adjust", p, delta, source="scenario", label=step.get("label") or "set_gold")
    return {"player": p["id"], "gold": int(p["gold"]), "delta": delta}


def op_set_stock(step: dict) -> dict:
    """X5：写商店库存 {shop, item, qty}（shop = 物品 id，如 counter / fish_stall）。"""
    from game import inventory
    obj = world_state.get_object_by_id(step.get("shop") or step.get("object") or "")
    if obj is None or obj.get("stock") is None or obj.get("shop") is None:
        raise StepError(f"shop not found: {step.get('shop')}")
    item = step.get("item") or ""
    if inventory.item_def(item) is None:
        raise StepError(f"unknown item: {item}")
    with world_state.STATE_LOCK:
        obj["stock"][item] = max(0, int(step.get("qty", 0)))
        pinned, state = _pin_restock_today(obj)
        world_state.refresh_shop_views()
    return {"shop": obj["id"], "stock": dict(obj["stock"]), "restock_pinned": pinned, "restock_state": state}


def op_force_closed(step: dict) -> dict:
    """X5：强制关门 {object | door_id | arena | shop, until: "HH:MM" | ISO | null}，不等真实时钟：
    物品 use → closed（opens_at = until）；所在 arena / 门边进入 → no_path/closed；正在用的人下一 tick 被请出（现有 _kick_closed_objects）。
    直到 until 到点自动解除；clear_closed 或 reset 也解除。"""
    key = step.get("object") or step.get("door_id") or step.get("arena") or step.get("shop") or step.get("sector")
    if not key:
        raise StepError("object | door_id | arena | shop required")
    known = {o["id"] for o in world_state._OBJECTS} | {e["id"] for e in world_state._EDGES} | set(world_state._ARENA_SECTOR) | set(world_state._ARENA_SECTOR.values())
    if key not in known:
        raise StepError(f"unknown key: {key}")
    until = _parse_until(step)
    with world_state.STATE_LOCK:
        world_state.force_closed(key, until)
    return {"key": key, "until": world_state._iso_from_ts(until) if until else None}


def op_clear_closed(step: dict) -> dict:
    with world_state.STATE_LOCK:
        return {"cleared": world_state.clear_forced(step.get("key"))}


def op_qq_send(step: dict) -> dict:
    """X4 C-QQ：代脚本角色发 QQ {from, to | group, text, kind?, file_ref?}。"""
    from game import qq
    frm = _resolve(step.get("from") or step.get("player"))
    to = step.get("to")
    if to and to not in qq._groups:
        try:
            to = _resolve(to)
        except StepError:
            pass                                               # 账号 / 显示名由 qq.resolve_account 再认
    msg, reason = qq.send(frm, to=to, group=step.get("group"), kind=step.get("kind") or ("file" if step.get("file_ref") else "text"),
                          text=step.get("text"), file_ref=step.get("file_ref"))
    if reason:
        raise StepError(f"qq_send: {reason}")
    return msg


def op_exit_chat(step: dict) -> dict:
    pid = _resolve(step.get("player"))
    res = chat_state.exit_room(pid, step.get("room") or "")
    if res is None:
        raise StepError("room not found")
    return res


def op_self_events(step: dict) -> dict:
    """X2 M3 夹具：把合成事件写进自我层（走 self_sync 的 /self/events，带 SELF_TOKEN）。
    {agent?="whale", rows:[{fid, type: event|chat|recognition, description, keywords[], importance, rel_day?|ts?, hm?="12:00",
                           what/how/why 或 body, voice?, scene?}], index_sync?=true}
    keywords 末尾自动加 "fixture" 与 fid（与 A 的 behavior_fixtures.py 同约定，A 的 --reset 能删）。rel_day = 相对今天（自我层 / 游戏日）的天数，-7 = 七天前。
    自我层关闭 / 不可达 → 步骤失败（C 改用 A 的种子脚本吃 docs/x2-m3-events.json）。"""
    from game import self_sync
    from game.time_state import game_now
    if not self_sync.enabled():
        raise StepError("self_sync disabled: write docs/x2-m3-events.json via A's seed script instead")
    agent = step.get("agent") or "whale"
    rows = step.get("rows") or []
    if not rows:
        raise StepError("rows required")
    today = game_now().date()
    written = []; errors = []
    with self_sync._client() as c:
        for i, r in enumerate(rows, 1):
            fid = r.get("fid") or f"fx-X2-{i:02d}"
            if r.get("ts"):
                ts = r["ts"]
            else:
                from datetime import timedelta
                day = today + timedelta(days=int(r.get("rel_day", 0)))
                ts = f"{day}T{r.get('hm', '12:00')}:00+08:00"
            body = r.get("body") or f"## What\n{r.get('what', '')}\n\n## How\n{r.get('how', '')}\n\n## Why\n{r.get('why', '')}\n"
            typ = r.get("type", "event")
            payload = {"agent": agent, "type": typ, "scene": r.get("scene", "sandbox"), "description": r["description"],
                       "keywords": list(r.get("keywords") or []) + ["fixture", fid], "importance": int(r.get("importance", 5)),
                       "source": "inferred" if typ == "recognition" else "observed", "ts": ts, "body": body, "voice": r.get("voice", "")}
            try:
                resp = c.post("/self/events", json=payload, timeout=60)
                resp.raise_for_status()
                written.append({"fid": fid, "ts": ts, "path": (resp.json() or {}).get("path")})
            except Exception as e:
                errors.append({"fid": fid, "error": str(e)})
        sync = None
        if step.get("index_sync", True) and written:
            try:
                sync = c.post("/self/index/sync", params={"agent": agent}, timeout=60).json()
            except Exception as e:
                sync = {"error": str(e)}
    if errors and not written:
        raise StepError(f"self_events: all failed: {errors[0]['error']}")
    return {"agent": agent, "written": written, "errors": errors, "index_sync": sync}


def op_clear_cooldowns(step: dict) -> dict:
    with world_state.STATE_LOCK:
        if step.get("player"):
            pid = _resolve(step["player"])
            world_state._last_used.pop(pid, None); world_state._use_history.pop(pid, None); world_state._daily_use.pop(pid, None)
            chat_state._last_chat_end.pop(pid, None)
            for k in [k for k in chat_state._last_pair_end if pid in k]:
                chat_state._last_pair_end.pop(k, None)
        else:
            world_state._last_used.clear(); world_state._use_history.clear(); world_state._daily_use.clear()
            chat_state._last_chat_end.clear(); chat_state._last_pair_end.clear()
    return {"ok": True}


def op_give_item(step: dict) -> dict:
    """W11 维护：直接往背包放物品（E 联调 buy / sell / store / give 用）。{player, item, qty?=1, meta?}。"""
    from game import inventory
    p = _player(step.get("player"))
    item = step.get("item") or ""
    if inventory.item_def(item) is None:
        raise StepError(f"unknown item: {item}")
    with world_state.STATE_LOCK:
        err = inventory.add(p, item, int(step.get("qty") or 1), meta=step.get("meta"))
    if err:
        raise StepError(err)
    return {"player": p["id"], "inventory": inventory.view(p)}


def op_produce(step: dict) -> dict:
    """W11 维护：模拟一次产出（ws produce 事件 + external produce 行 + pendingMessage）。{player, via?=fishing, item?=fish, qty?=1}。"""
    from game import inventory, production
    p = _player(step.get("player"))
    item = step.get("item") or "fish"; via = step.get("via") or "fishing"; qty = int(step.get("qty") or 1)
    if inventory.item_def(item) is None:
        raise StepError(f"unknown item: {item}")
    with world_state.STATE_LOCK:
        err = inventory.add(p, item, qty)
        if err:
            raise StepError(err)
        production._notify(p, via, item, qty, object=step.get("object"), scenario=True)
    return {"player": p["id"], "via": via, "item": item, "qty": qty, "inventory": inventory.view(p)}


def op_move_object(step: dict) -> dict:
    """X1 N5：物品挪位 {id, to:{x,y}} 或 {id, x, y}。目标脚印须可走且没人站着；正在用的人被请离。"""
    to = step.get("to") or {}
    x = to.get("x", step.get("x")); y = to.get("y", step.get("y"))
    if x is None or y is None:
        raise StepError("to {x, y} required")
    try:
        return world_state.move_object(step.get("id") or step.get("object") or "", int(x), int(y))
    except ValueError as e:
        raise StepError(str(e))


def op_remove_object(step: dict) -> dict:
    """X1 N5：撤掉物品 {id}（脚下变地板，restore_object 放回）。"""
    try:
        return world_state.remove_object(step.get("id") or step.get("object") or "")
    except (ValueError, StopIteration):
        raise StepError(f"object not found: {step.get('id') or step.get('object')}")


def op_restore_object(step: dict) -> dict:
    """恢复 {id?}：撤掉的放回、挪过的挪回；不给 id = 全部（reset 也会做）。"""
    return world_state.restore_object(step.get("id") or step.get("object"))


OPS = {
    "reset": op_reset, "set_time": op_set_time, "spawn": op_spawn, "remove": op_remove, "teleport": op_teleport,
    "set_vars": op_set_vars, "effects": op_effects, "occupy": op_occupy, "release": op_release,
    "invite": op_invite, "respond": op_respond, "say": op_say, "exit_chat": op_exit_chat, "clear_cooldowns": op_clear_cooldowns,
    "give_item": op_give_item, "produce": op_produce,          # W11 维护
    "move_object": op_move_object, "remove_object": op_remove_object, "restore_object": op_restore_object,   # X1 N5
    "self_events": op_self_events,                                                                           # X2 M3
    "qq_send": op_qq_send,                                                                                   # X4 C-QQ
    "set_fridge": op_set_fridge, "set_stock": op_set_stock, "set_gold": op_set_gold, "set_supply": op_set_supply, "force_closed": op_force_closed, "clear_closed": op_clear_closed,   # X5
}
_SAMPLE_OPS = {"spawn", "teleport", "set_vars", "effects", "occupy", "release", "give_item", "produce"}


@router.post("/admin/scenario")
def admin_scenario(body: ScenarioRequest):
    if not enabled():
        raise HTTPException(status_code=403, detail="scenario fixture disabled (set SANDBOX_SCENARIO=1 on a bench instance)")
    results = []
    for i, step in enumerate(body.steps):
        op = step.get("op")
        fn = OPS.get(op or "")
        if fn is None:
            return {"ok": False, "label": body.label, "error": f"step {i}: unknown op {op!r}", "steps": results}
        try:
            detail = fn(step)
        except StepError as e:
            return {"ok": False, "label": body.label, "error": f"step {i} ({op}): {e}", "steps": results}
        except Exception as e:
            return {"ok": False, "label": body.label, "error": f"step {i} ({op}): {type(e).__name__}: {e}", "steps": results}
        # 数据集 / 回放可见：外部日志 + 受影响玩家立即采样
        entity = None
        for key in ("player", "from"):
            if step.get(key):
                try:
                    entity = _resolve(step[key])
                except StepError:
                    entity = None
        if op == "spawn" and isinstance(detail, dict):
            entity = detail.get("id")
        external_log.log("scenario", entity, label=body.label, step=i, op=op, args={k: v for k, v in step.items() if k != "op"},
                         result=detail if isinstance(detail, dict) and len(str(detail)) < 2000 else None)
        if op in _SAMPLE_OPS and entity in world_state._players:
            state_log.sample_now(world_state._players[entity], "scenario")
        results.append({"op": op, "ok": True, "detail": detail})
    return {
        "ok": True, "label": body.label, "steps": results,
        "world": {"time": time_state.get_time_state(), "players": [_brief(p) for p in world_state._players.values()]},
    }
