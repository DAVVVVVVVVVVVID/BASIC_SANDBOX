"""
门禁 = 钥匙物品 + 敲门 + 从内侧开门（§3.41，主播 11-08 07:30 定；替换 §3.39 白名单与 §3.40 远程放行）。

- 钥匙：物品 type "key"，meta {door_id, name}。每扇带 owner 的门有固定把数（edge.keys，缺省 = owner 数；door_home 3 把：鲸仔、阿蝉、人类控制者进场自带 1）。
  join / spawn 时按 owner / homes 发自家钥匙（每把只发一次，持有人被删除时钥匙回池）；只能当面 give，QQ 不可传。
- 门默认锁：出门永远放行 ‖ 门敞开窗口内放行 ‖ 商店门 open_hours 内放行 ‖ 持该门钥匙放行；其余 locked（商店打烊无钥匙 → closed + opens_at）。
- open_door {door_id}：站在门内侧相邻格的任何人、不需钥匙；敞开 60 游戏秒后自动落锁（日志 door_locked，ws door closed）。
- knock / door_request（90 游戏秒）沿用；主人 POST /door/respond {request_id, entity_id, text | decline} 喊话（answered）或拒绝（declined）；
  访客在敞开窗口内跨过那扇门 → opened；无动静到期 → no_answer。
"""
import uuid

KNOCK_EXPIRE_S = 90.0
OPEN_S = 60.0
KNOCK_RANGE = 2

_requests: dict[str, dict] = {}
_open: dict[str, dict] = {}            # door_id -> {"until_gts", "by", "opened_at"}
_issued: dict[str, dict[str, str]] = {}   # door_id -> {slot: holder player id}；slot = owner 账号，或 "human:<pid>"（余下的把数给人类控制者）


# ── 门 / 家 / 主人 ──
def _edges():
    from game import world_state as ws
    return ws._EDGES


def door(door_id: str) -> dict | None:
    return next((e for e in _edges() if e["id"] == door_id), None)


def is_keyed(edge: dict) -> bool:
    return bool(edge.get("owner")) and edge.get("kind") != "stairs"


def is_shop_door(edge: dict) -> bool:
    return bool(edge.get("open_hours")) and is_keyed(edge)


def door_sector(edge: dict) -> str | None:
    from game import world_state as ws
    return ws._ZONE_LOOKUP.get((edge["b"]["x"], edge["b"]["y"]), {}).get("sector")


def home_sectors() -> set[str]:
    return {s for e in _edges() if is_keyed(e) and not is_shop_door(e) for s in [door_sector(e)] if s}


def home_owners(sector: str) -> set[str]:
    from game import world_state as ws
    owners: set[str] = set()
    for arena, acc in ws._ACCESS.items():
        if ws.sector_of_arena(arena) == sector:
            owners |= set(acc.get("owner") or [])
    for e in _edges():
        if door_sector(e) == sector:
            owners |= set(e.get("owner") or [])
    for aid, arena in ws._HOMES.items():
        if ws.sector_of_arena(arena) == sector:
            owners.add(aid)
    return owners


def _is_owner(player: dict, sector: str) -> bool:
    from game.world_state import _mover_ids
    return bool(_mover_ids(player) & home_owners(sector))


def _inside(player: dict, sector: str) -> bool:
    from game import world_state as ws
    pos = player["position"]
    return ws.get_zone_at(pos["x"], pos["y"]).get("sector") == sector


def _at_home_awake(player: dict, sector: str) -> bool:
    from game import world_state as ws
    pos = player["position"]
    return (ws.get_zone_at(pos["x"], pos["y"]).get("sector") == sector and "sleeping" not in player.get("tags", [])
            and player.get("scene", "sandbox") != "live" and ws.is_present(player))


def _log(entity: str, kind: str, payload: dict, success: bool = True, reason: str | None = None) -> None:
    try:
        from game.action_log import append_log
        append_log(entity, kind, payload, success=success, reason=reason)
    except Exception:
        pass


def _push(ev: dict) -> None:
    try:
        from routers.ws import hub
        hub.push_event(ev)
    except Exception:
        pass


# ── 钥匙 ──
def key_name(edge: dict) -> str:
    return f"{edge.get('name') or edge['id']}钥匙"


def holds_key(mover: dict | None, door_id: str) -> bool:
    """持钥匙？有背包的真实玩家看物品；只有身份的假 mover（/admin/path mover=whale、path_table）按「主人默认有自家钥匙」算。"""
    if not mover:
        return False
    if "inventory" in mover:
        from game.inventory import find
        return find(mover, "key", door_id=door_id) is not None
    from game.world_state import _mover_ids
    e = door(door_id)
    return bool(e and _mover_ids(mover) & set(e.get("owner") or []))


def issue_key(player: dict, edge: dict, slot: str, why: str = "default") -> bool:
    """按槽位发一把钥匙（总数固定 edge.keys：owner 各占一槽，余下的槽给人类控制者）。返回是否发出。"""
    from game.inventory import add, find
    if find(player, "key", door_id=edge["id"]) is not None:
        return False
    slots = _issued.setdefault(edge["id"], {})
    total = int(edge.get("keys") or len(edge.get("owner") or []) or 1)
    owners = list(edge.get("owner") or [])
    if slot in slots:
        return False                                             # 这把已经发出（在别人手里）
    if slot not in owners:                                       # 人类槽：只能用 owner 之外剩下的把数
        if sum(1 for s in slots if s not in owners) >= max(0, total - len(owners)):
            return False
    if len(slots) >= total:
        return False
    if add(player, "key", 1, meta={"door_id": edge["id"], "name": key_name(edge)}) is not None:
        return False
    slots[slot] = player["id"]
    _log(player["id"], "key_issued", {"door_id": edge["id"], "name": key_name(edge), "slot": slot, "why": why})
    return True


def migrate_keys(players: dict) -> dict[str, list[str]]:
    """启动迁移（§3.41 补）：加载检查点后，对每个 agent 玩家按同一规则补发自家钥匙（身份槽已发过的不重发，幂等）；
    人类控制者不在这里发——下次 join 领剩余把数。返回 {player_id: [door_id]}。"""
    got = {}
    for p in players.values():
        if p.get("controller", "human") != "agent":
            continue
        ids = issue_default_keys(p, why="migrate")
        if ids:
            got[p["id"]] = ids
    return got


def issue_default_keys(player: dict, why: str = "default") -> list[str]:
    """join / spawn：agent 按 owner / homes 发自家门的钥匙；人类控制者发一把合租房大门钥匙（演阿蝉）。"""
    from game import world_state as ws
    from game.world_state import _mover_ids
    got = []
    ids = _mover_ids(player)
    home_arena = ws._HOMES.get(player.get("agent_id") or "")
    home_sector = ws.sector_of_arena(home_arena) if home_arena else None
    for e in _edges():
        if not is_keyed(e):
            continue
        owners = list(e.get("owner") or [])
        slot = next((o for o in owners if o in ids), None)
        if slot is None and home_sector is not None and door_sector(e) == home_sector and not is_shop_door(e) and player.get("agent_id"):
            slot = player["agent_id"]                            # homes 里住这家但不在 owner 名单：按身份占槽（名单外不额外加把数）
            if slot not in owners:
                slot = None
        if slot is None and player.get("controller", "human") == "human" and e["id"] == "door_home":
            slot = f"human:{player['id']}"
        if slot and issue_key(player, e, slot, why=why):
            got.append(e["id"])
    return got


def transfer_key(giver: dict, target: dict, door_id: str) -> str | None:
    """give：实物转交。返回失败 reason 或 None。"""
    from game.inventory import find, remove_entry, add
    entry = find(giver, "key", door_id=door_id)
    if entry is None:
        return "no_item"
    if find(target, "key", door_id=door_id) is not None:
        return "already_has_key"
    err = add(target, "key", 1, meta=dict(entry.get("meta") or {}))
    if err:
        return err
    remove_entry(giver, entry, 1)
    slots = _issued.setdefault(door_id, {})
    for s, h in list(slots.items()):
        if h == giver["id"]:
            slots[s] = target["id"]; break
    return None


def on_player_removed(player: dict) -> None:
    """持钥匙的人被删除：钥匙回池（下次该身份 join 再发）。"""
    for door_id, slots in _issued.items():
        for s, h in list(slots.items()):
            if h == player["id"]:
                del slots[s]


def keys_of(player: dict) -> list[dict]:
    return [{"door_id": (e.get("meta") or {}).get("door_id"), "name": (e.get("meta") or {}).get("name")} for e in player.get("inventory", []) if e.get("type") == "key"]


# ── 门的开关 ──
def is_open_window(door_id: str, gts: float) -> bool:
    o = _open.get(door_id)
    return o is not None and gts < o["until_gts"]


def open_door(entity_id: str, door_id: str) -> tuple[dict | None, str | None, dict | None]:
    """站在门内侧（b 格或其四邻、且在门内 sector）的任何人开门，不需钥匙；60 游戏秒后自动落锁。调用方持 STATE_LOCK。"""
    from game import world_state as ws
    p = ws._players.get(entity_id)
    if p is None:
        return None, "player_not_found", None
    e = door(door_id)
    if e is None:
        return None, "unknown_door", None
    if not is_keyed(e):
        return None, "not_lockable", {"door_id": door_id}
    b = (e["b"]["x"], e["b"]["y"]); pos = (p["position"]["x"], p["position"]["y"])
    inside_sector = door_sector(e)
    if pos != b and (max(abs(pos[0] - b[0]), abs(pos[1] - b[1])) > 1 or ws.get_zone_at(*pos).get("sector") != inside_sector):
        return None, "not_inside_door", {"door_id": door_id, "inside": {"x": b[0], "y": b[1]}}
    gts = ws.game_now_ts()
    _open[door_id] = {"until_gts": gts + OPEN_S, "by": entity_id, "opened_at": ws._iso_from_ts(gts)}
    info = {"door_id": door_id, "name": e.get("name"), "open_until": ws._iso_from_ts(gts + OPEN_S), "open_s": OPEN_S, "x": e["a"]["x"], "y": e["a"]["y"], "by": entity_id}
    _log(entity_id, "open_door", info)
    _push({"type": "door", "event": "opened", **info})
    # 等在门外的访客：告知
    for r in _requests.values():
        if r["status"] in ("pending", "answered") and r["door"].get("id") == door_id:
            if r["visitor"] in ws._players:
                ws._pending_messages[r["visitor"]] = f"{p.get('name')} 把门打开了。"
    return info, None, None


def on_cross(entity_id: str, t1: tuple[int, int], t2: tuple[int, int], gts: float) -> None:
    """有人跨过了一扇门（走路 / 人类单格）：若是敞开窗口内进门的访客且有未结的敲门 → status opened。"""
    from game import world_state as ws
    e = ws._EDGE_BY_PAIR.get(frozenset((t1, t2)))
    if e is None or not is_keyed(e) or (t2[0], t2[1]) != (e["b"]["x"], e["b"]["y"]):
        return
    for r in _requests.values():
        if r["visitor"] == entity_id and r["status"] in ("pending", "answered") and r["door"].get("id") == e["id"]:
            r["status"] = "opened"; r["responded_at"] = ws._iso_from_ts(gts)
            _log(entity_id, "door_respond", {"request_id": r["id"], "visitor": entity_id, "home": r["home"], "outcome": "opened"})
            _push({"type": "door", "event": "visitor_entered", "request_id": r["id"], "visitor": entity_id, "visitor_name": r["visitor_name"], "home": r["home"], "door": r["door"]})


# ── 敲门 ──
def knock(entity_id: str, payload: dict) -> tuple[dict | None, str | None, dict | None]:
    from game import world_state as ws
    p = ws._players.get(entity_id)
    if p is None:
        return None, "player_not_found", None
    pos = (p["position"]["x"], p["position"]["y"])
    d = None; sector = None; anchor = None
    if payload.get("door_id") or payload.get("door"):
        d = door(payload.get("door_id") or payload.get("door"))
        if d is None:
            return None, "unknown_door", None
        sector = door_sector(d); anchor = (d["a"]["x"], d["a"]["y"])
    elif payload.get("target_tile") or payload.get("targetTile"):
        t = payload.get("target_tile") or payload.get("targetTile")
        sector = ws.get_zone_at(int(t["x"]), int(t["y"])).get("sector"); anchor = (int(t["x"]), int(t["y"]))
    elif payload.get("home") or payload.get("target"):
        ref = payload.get("home") or payload.get("target")
        sector = ref if ref in {z.get("sector") for z in ws._ZONE_LOOKUP.values()} else ws.sector_of_arena(ref)
    else:
        return None, "missing_door_or_target", None
    if not sector or sector not in home_sectors():
        return None, "not_a_home", {"sector": sector}
    if ws.get_zone_at(*pos).get("sector") == sector:
        return None, "already_inside", {"home": sector}
    if d is None:
        cands = [e for e in _edges() if is_keyed(e) and not is_shop_door(e) and door_sector(e) == sector]
        if cands:
            d = min(cands, key=lambda e: abs(e["a"]["x"] - pos[0]) + abs(e["a"]["y"] - pos[1]))
    if d is None:
        return None, "no_door", {"home": sector}
    if anchor is None:
        anchor = (d["a"]["x"], d["a"]["y"])
    if holds_key(p, d["id"]):
        return None, "has_key", {"door_id": d["id"]}
    if max(abs(anchor[0] - pos[0]), abs(anchor[1] - pos[1])) > KNOCK_RANGE:
        return None, "too_far", {"home": sector, "door": {"x": anchor[0], "y": anchor[1]}, "range": KNOCK_RANGE}
    for r in _requests.values():
        if r["visitor"] == entity_id and r["home"] == sector and r["status"] in ("pending", "answered"):
            return None, "already_knocking", {"request_id": r["id"], "status": r["status"], "expires_at": r["expires_at"]}
    gts = ws.game_now_ts()
    owners = sorted(home_owners(sector))
    req = {"id": f"k{uuid.uuid4().hex[:8]}", "visitor": entity_id, "visitor_name": p.get("name"), "visitor_account": p.get("agent_id") or entity_id,
           "home": sector, "home_name": ws.zone_display_name("sector", sector), "owners": owners,
           "door": {"id": d["id"], "name": d.get("name"), "x": anchor[0], "y": anchor[1], "inside": {"x": d["b"]["x"], "y": d["b"]["y"]}},
           "created_at": ws._iso_from_ts(gts), "created_gts": gts, "expires_at": ws._iso_from_ts(gts + KNOCK_EXPIRE_S), "expires_gts": gts + KNOCK_EXPIRE_S,
           "status": "pending", "responded_by": None, "answers": [], "notified": []}
    _requests[req["id"]] = req
    for op in ws._players.values():
        if op["id"] != entity_id and _at_home_awake(op, sector):                  # §3.41 补：屋内所有清醒者（不限 owner）
            ws._pending_messages[op["id"]] = f"{p.get('name')} 在敲门。"
            req["notified"].append(op["id"])
    _log(entity_id, "knock", public_request(req))
    _push({"type": "knock", "request_id": req["id"], "visitor": entity_id, "visitor_name": p.get("name"), "home": sector, "home_name": req["home_name"],
           "door": req["door"], "owners": owners, "expires_at": req["expires_at"], "notified": list(req["notified"])})
    return public_request(req), None, None


def public_request(r: dict) -> dict:
    return {k: v for k, v in r.items() if k not in ("created_gts", "expires_gts")}


def respond(entity_id: str, request_id: str, text: str | None, decline: bool) -> tuple[dict | None, str | None]:
    """主人隔门喊一句（answered，续 90 秒）或拒绝（declined）。调用方持 STATE_LOCK。"""
    from game import world_state as ws
    p = ws._players.get(entity_id)
    if p is None:
        return None, "player_not_found"
    r = _requests.get(request_id)
    if r is None:
        return None, "unknown_request"
    if not _inside(p, r["home"]):
        return None, "not_inside"                                # §3.41 补：屋内任何人都可应门（人类演阿蝉站在客厅即可）
    if r["status"] not in ("pending", "answered"):
        return None, f"not_pending:{r['status']}"
    if not decline and not (text or "").strip():
        return None, "text_required"
    gts = ws.game_now_ts()
    r["responded_by"] = entity_id; r["responded_at"] = ws._iso_from_ts(gts)
    if decline:
        r["status"] = "declined"
        msg = f"{p.get('name')} 没让你进。"
    else:
        r["status"] = "answered"; r["answers"].append({"by": entity_id, "text": text.strip(), "at": r["responded_at"]})
        r["expires_gts"] = gts + KNOCK_EXPIRE_S; r["expires_at"] = ws._iso_from_ts(r["expires_gts"])
        msg = f"{p.get('name')}：{text.strip()}"
    _log(entity_id, "door_respond", {"request_id": r["id"], "visitor": r["visitor"], "home": r["home"], "outcome": r["status"], "text": None if decline else text.strip()})
    _push({"type": "door", "event": r["status"], "request_id": r["id"], "visitor": r["visitor"], "visitor_name": r["visitor_name"], "home": r["home"],
           "by": entity_id, "by_name": p.get("name"), "text": None if decline else text.strip(), "door": r["door"]})
    if r["visitor"] in ws._players:
        ws._pending_messages[r["visitor"]] = msg
    return public_request(r), None


# ── 查询 ──
def visitor_view(entity_id: str) -> dict | None:
    mine = [r for r in _requests.values() if r["visitor"] == entity_id]
    if not mine:
        return None
    r = max(mine, key=lambda x: x["created_gts"])
    return {"id": r["id"], "home": r["home"], "home_name": r["home_name"], "status": r["status"], "expires_at": r["expires_at"],
            "responded_by": r.get("responded_by"), "answers": list(r.get("answers") or []), "door": r["door"]}


def pending_for_owner(player: dict) -> list[dict]:
    """屋内的人（或这家主人）看到的待回应敲门。"""
    return [{"id": r["id"], "visitor": r["visitor"], "visitor_name": r["visitor_name"], "home": r["home"], "home_name": r["home_name"],
             "door": r["door"], "status": r["status"], "expires_at": r["expires_at"]}
            for r in _requests.values() if r["status"] in ("pending", "answered") and (_inside(player, r["home"]) or _is_owner(player, r["home"]))]


def open_doors_view() -> list[dict]:
    from game import world_state as ws
    gts = ws.game_now_ts()
    return [{"door_id": k, "open_until": ws._iso_from_ts(o["until_gts"]), "by": o["by"]} for k, o in _open.items() if gts < o["until_gts"]]


# ── tick ──
def on_tick(gts: float, players: dict) -> None:
    from game import world_state as ws
    for r in _requests.values():
        if r["status"] == "pending" and gts >= r["expires_gts"]:
            r["status"] = "no_answer"
            _log(r["visitor"], "door_respond", {"request_id": r["id"], "visitor": r["visitor"], "home": r["home"], "outcome": "no_answer"}, success=False, reason="no_answer")
            _push({"type": "door", "event": "no_answer", "request_id": r["id"], "visitor": r["visitor"], "visitor_name": r["visitor_name"], "home": r["home"], "door": r["door"]})
            if r["visitor"] in players:
                ws._pending_messages[r["visitor"]] = "敲了半天没人应门。"
        elif r["status"] == "answered" and gts >= r["expires_gts"]:
            r["status"] = "closed"                     # 喊过话但没开门：到期结束，访客 door_request 保留 answers
    for door_id, o in list(_open.items()):
        if gts >= o["until_gts"]:
            del _open[door_id]
            e = door(door_id)
            _log(o["by"], "door_locked", {"door_id": door_id, "name": e.get("name") if e else None, "opened_at": o["opened_at"]})
            _push({"type": "door", "event": "closed", "door_id": door_id, "name": e.get("name") if e else None,
                   "x": e["a"]["x"] if e else None, "y": e["a"]["y"] if e else None})
    for rid, r in list(_requests.items()):
        if r["status"] not in ("pending", "answered") and gts - r["expires_gts"] > 3600:
            del _requests[rid]


def export_state() -> dict:
    return {"requests": {k: dict(v) for k, v in _requests.items()}, "open": {k: dict(v) for k, v in _open.items()},
            "issued": {k: dict(v) for k, v in _issued.items()}}


def import_state(d: dict) -> None:
    _requests.clear(); _open.clear(); _issued.clear()
    _requests.update(d.get("requests") or {}); _open.update(d.get("open") or {})
    _issued.update({k: dict(v) for k, v in (d.get("issued") or {}).items()})


def _reset_for_tests() -> None:
    _requests.clear(); _open.clear(); _issued.clear()
