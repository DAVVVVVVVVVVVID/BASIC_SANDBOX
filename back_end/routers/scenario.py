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
  occupy         {player, object, sticky?:false}     让玩家占住某物品（跳过距离 / 冷却 / 营业时间 / 外部调用）；sticky=true 关掉 max_duration 自动离开
  release        {player}                            离开正在用的物品
  invite         {from, to:[...], greeting}          代某玩家发邀请（跳过冷却）→ 返回 request_id
  respond        {player, request_id, accept, message}
  say            {player, room, text}
  exit_chat      {player, room}
  clear_cooldowns {player?}                          清物品冷却与对话冷却
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
    return _brief(world_state._players[pid])


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
    return _brief(p)


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
        world_state.record_object_use(p["id"], obj["id"])
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
    pid = _resolve(step.get("player"))
    res = chat_state.post_message(pid, step.get("room") or "", step.get("text") or "")
    if res is None:
        raise StepError("room not found or closed")
    return res


def op_exit_chat(step: dict) -> dict:
    pid = _resolve(step.get("player"))
    res = chat_state.exit_room(pid, step.get("room") or "")
    if res is None:
        raise StepError("room not found")
    return res


def op_clear_cooldowns(step: dict) -> dict:
    with world_state.STATE_LOCK:
        if step.get("player"):
            pid = _resolve(step["player"])
            world_state._last_used.pop(pid, None); world_state._use_history.pop(pid, None)
            chat_state._last_chat_end.pop(pid, None)
            for k in [k for k in chat_state._last_pair_end if pid in k]:
                chat_state._last_pair_end.pop(k, None)
        else:
            world_state._last_used.clear(); world_state._use_history.clear()
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


OPS = {
    "reset": op_reset, "set_time": op_set_time, "spawn": op_spawn, "remove": op_remove, "teleport": op_teleport,
    "set_vars": op_set_vars, "effects": op_effects, "occupy": op_occupy, "release": op_release,
    "invite": op_invite, "respond": op_respond, "say": op_say, "exit_chat": op_exit_chat, "clear_cooldowns": op_clear_cooldowns,
    "give_item": op_give_item, "produce": op_produce,          # W11 维护
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
