"""
敲门机制（§3.40，主播 11-08 06:50 定）。

- 家 = 含锁定访问规则（access.locked）的 sector：合租房 home、渔夫家、小千家、店主家。商店不是家（按营业时间）。
- 访客在家门外侧（离门 a 格 / 家的边界 ≤ 2 格、不在家里）`POST /action knock {door_id | target_tile | home}` →
  door_request {id, visitor, visitor_name, home, home_name, owners[], door{x,y,id}, created_at, expires_at(+90 游戏秒), status}；
  动作日志 `knock`；ws `{type:"knock", ...}`；在家且清醒（无 sleeping、scene≠live）的主人 pendingMessage「X 在敲门」、perceive.knocks[]。
- 主人 `POST /door/respond {request_id, entity_id, accept}`：accept → door_pass {visitor, home, expires_at(+2 游戏小时)}（访客离开该 sector 即失效，先到为准），
  走 edge_block / arena_block 同一判定；decline → declined；到期无人回应 → no_answer。
- 动作日志：knock / door_respond（含 no_answer）/ door_pass_granted / door_pass_expired；检查点 meta `doors`。
"""
import uuid

KNOCK_EXPIRE_S = 90.0        # 游戏秒
PASS_S = 2 * 3600.0          # 游戏秒
KNOCK_RANGE = 2              # 离门 / 家边界几格内可敲

_requests: dict[str, dict] = {}        # id -> request
_passes: dict[str, dict] = {}          # f"{visitor}:{home}" -> pass


# ── 家 / 主人 ──
def home_sectors() -> set[str]:
    from game import world_state as ws
    out = set()
    for arena, acc in ws._ACCESS.items():
        if acc.get("locked"):
            s = ws.sector_of_arena(arena)
            if s:
                out.add(s)
    return out


def home_owners(sector: str) -> set[str]:
    from game import world_state as ws
    owners: set[str] = set()
    for arena, acc in ws._ACCESS.items():
        if ws.sector_of_arena(arena) == sector:
            owners |= set(acc.get("owner") or [])
    for e in ws._EDGES:
        if ws._ZONE_LOOKUP.get((e["b"]["x"], e["b"]["y"]), {}).get("sector") == sector:
            owners |= set(e.get("owner") or [])
    for aid, arena in ws._HOMES.items():
        if ws.sector_of_arena(arena) == sector:
            owners.add(aid)
    return owners


def _is_owner(player: dict, sector: str) -> bool:
    from game.world_state import _mover_ids
    return bool(_mover_ids(player) & home_owners(sector))


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


# ── 敲门 ──
def knock(entity_id: str, payload: dict) -> tuple[dict | None, str | None, dict | None]:
    """返回 (request, None, None) 或 (None, reason, detail)。调用方持 STATE_LOCK。"""
    from game import world_state as ws
    p = ws._players.get(entity_id)
    if p is None:
        return None, "player_not_found", None
    pos = (p["position"]["x"], p["position"]["y"])
    door = None; sector = None
    if payload.get("door_id") or payload.get("door"):
        door = next((e for e in ws._EDGES if e["id"] == (payload.get("door_id") or payload.get("door"))), None)
        if door is None:
            return None, "unknown_door", None
        sector = ws._ZONE_LOOKUP.get((door["b"]["x"], door["b"]["y"]), {}).get("sector")
        anchor = (door["a"]["x"], door["a"]["y"])
    elif payload.get("target_tile") or payload.get("targetTile"):
        t = payload.get("target_tile") or payload.get("targetTile")
        sector = ws.get_zone_at(int(t["x"]), int(t["y"])).get("sector")
        anchor = (int(t["x"]), int(t["y"]))
    elif payload.get("home") or payload.get("target"):
        ref = payload.get("home") or payload.get("target")
        sector = ref if ref in {z.get("sector") for z in ws._ZONE_LOOKUP.values()} else ws.sector_of_arena(ref)
        anchor = None
    else:
        return None, "missing_door_or_target", None
    if not sector or sector not in home_sectors():
        return None, "not_a_home", {"sector": sector}
    if ws.get_zone_at(*pos).get("sector") == sector:
        return None, "already_inside", {"home": sector}
    if _is_owner(p, sector):
        return None, "is_owner", {"home": sector}
    if door is None:                                                     # 找离访客最近的这家的门（a 在外侧）
        cands = [e for e in ws._EDGES if ws._ZONE_LOOKUP.get((e["b"]["x"], e["b"]["y"]), {}).get("sector") == sector and e["kind"] != "stairs"]
        if cands:
            door = min(cands, key=lambda e: abs(e["a"]["x"] - pos[0]) + abs(e["a"]["y"] - pos[1]))
    if anchor is None and door is not None:
        anchor = (door["a"]["x"], door["a"]["y"])
    if anchor is None:
        return None, "no_door", {"home": sector}
    if max(abs(anchor[0] - pos[0]), abs(anchor[1] - pos[1])) > KNOCK_RANGE:
        return None, "too_far", {"home": sector, "door": {"x": anchor[0], "y": anchor[1]}, "range": KNOCK_RANGE}
    for r in _requests.values():
        if r["visitor"] == entity_id and r["home"] == sector and r["status"] == "pending":
            return None, "already_knocking", {"request_id": r["id"], "expires_at": r["expires_at"]}
    if has_pass(entity_id, sector, ws.game_now_ts()):
        return None, "already_has_pass", {"home": sector}
    gts = ws.game_now_ts()
    owners = sorted(home_owners(sector))
    req = {"id": f"k{uuid.uuid4().hex[:8]}", "visitor": entity_id, "visitor_name": p.get("name"), "visitor_account": p.get("agent_id") or entity_id,
           "home": sector, "home_name": ws.zone_display_name("sector", sector),
           "owners": owners, "door": {"id": door["id"] if door else None, "x": anchor[0], "y": anchor[1]},
           "created_at": ws._iso_from_ts(gts), "created_gts": gts, "expires_at": ws._iso_from_ts(gts + KNOCK_EXPIRE_S), "expires_gts": gts + KNOCK_EXPIRE_S,
           "status": "pending", "responded_by": None, "notified": []}
    _requests[req["id"]] = req
    for op in ws._players.values():
        if _is_owner(op, sector) and _at_home_awake(op, sector):
            ws._pending_messages[op["id"]] = f"{p.get('name')} 在敲门。"
            req["notified"].append(op["id"])
    _log(entity_id, "knock", {k: v for k, v in req.items() if k not in ("created_gts", "expires_gts")})
    _push({"type": "knock", "request_id": req["id"], "visitor": entity_id, "visitor_name": p.get("name"), "home": sector, "home_name": req["home_name"],
           "door": req["door"], "owners": owners, "expires_at": req["expires_at"], "notified": list(req["notified"])})
    return public_request(req), None, None


def public_request(r: dict) -> dict:
    return {k: v for k, v in r.items() if k not in ("created_gts", "expires_gts")}


# ── 回应 ──
def respond(entity_id: str, request_id: str, accept: bool) -> tuple[dict | None, str | None]:
    """主人回应。返回 (request, None) 或 (None, reason)。调用方持 STATE_LOCK。"""
    from game import world_state as ws
    p = ws._players.get(entity_id)
    if p is None:
        return None, "player_not_found"
    r = _requests.get(request_id)
    if r is None:
        return None, "unknown_request"
    if not _is_owner(p, r["home"]):
        return None, "not_owner"
    if r["status"] != "pending":
        return None, f"not_pending:{r['status']}"
    gts = ws.game_now_ts()
    r["status"] = "accepted" if accept else "declined"; r["responded_by"] = entity_id; r["responded_at"] = ws._iso_from_ts(gts)
    _log(entity_id, "door_respond", {"request_id": r["id"], "visitor": r["visitor"], "home": r["home"], "outcome": r["status"]})
    if accept:
        grant_pass(r["visitor"], r["home"], gts, by=entity_id, request_id=r["id"])
    _push({"type": "door", "event": r["status"], "request_id": r["id"], "visitor": r["visitor"], "visitor_name": r["visitor_name"],
           "home": r["home"], "by": entity_id, "door": r["door"]})
    v = ws._players.get(r["visitor"])
    if v is not None:
        ws._pending_messages[r["visitor"]] = (f"{p.get('name')} 给你开了门。" if accept else f"{p.get('name')} 没让你进。")
    return public_request(r), None


def grant_pass(visitor: str, home: str, gts: float, by: str | None = None, request_id: str | None = None) -> dict:
    from game import world_state as ws
    ps = {"visitor": visitor, "home": home, "granted_at": ws._iso_from_ts(gts), "expires_at": ws._iso_from_ts(gts + PASS_S), "expires_gts": gts + PASS_S,
          "by": by, "request_id": request_id, "entered": False}
    _passes[f"{visitor}:{home}"] = ps
    _log(visitor, "door_pass_granted", {k: v for k, v in ps.items() if k != "expires_gts"})
    return ps


def has_pass(entity_id: str | None, sector: str | None, gts: float) -> bool:
    if not entity_id or not sector:
        return False
    ps = _passes.get(f"{entity_id}:{sector}")
    return ps is not None and gts < ps["expires_gts"]


def passes_of(entity_id: str) -> list[dict]:
    return [{k: v for k, v in ps.items() if k != "expires_gts"} for ps in _passes.values() if ps["visitor"] == entity_id]


def _expire_pass(key: str, reason: str) -> None:
    ps = _passes.pop(key, None)
    if ps is None:
        return
    _log(ps["visitor"], "door_pass_expired", {"home": ps["home"], "reason": reason, "granted_at": ps["granted_at"]})
    _push({"type": "door", "event": "pass_expired", "visitor": ps["visitor"], "home": ps["home"], "reason": reason})


# ── 查询 ──
def visitor_view(entity_id: str) -> dict | None:
    """访客的最近一次敲门：{id, home, home_name, status, expires_at, responded_by}。"""
    mine = [r for r in _requests.values() if r["visitor"] == entity_id]
    if not mine:
        return None
    r = max(mine, key=lambda x: x["created_gts"])
    return {"id": r["id"], "home": r["home"], "home_name": r["home_name"], "status": r["status"], "expires_at": r["expires_at"],
            "responded_by": r.get("responded_by"), "door": r["door"]}


def pending_for_owner(player: dict) -> list[dict]:
    out = []
    for r in _requests.values():
        if r["status"] == "pending" and _is_owner(player, r["home"]):
            out.append({"id": r["id"], "visitor": r["visitor"], "visitor_name": r["visitor_name"], "home": r["home"], "home_name": r["home_name"],
                        "door": r["door"], "expires_at": r["expires_at"]})
    return out


# ── tick ──
def on_tick(gts: float, players: dict) -> None:
    """到期无人回应 → no_answer；通行证到期或访客离家 → 失效。调用方持 STATE_LOCK。"""
    from game import world_state as ws
    for r in _requests.values():
        if r["status"] == "pending" and gts >= r["expires_gts"]:
            r["status"] = "no_answer"
            _log(r["visitor"], "door_respond", {"request_id": r["id"], "visitor": r["visitor"], "home": r["home"], "outcome": "no_answer"},
                 success=False, reason="no_answer")
            _push({"type": "door", "event": "no_answer", "request_id": r["id"], "visitor": r["visitor"], "visitor_name": r["visitor_name"], "home": r["home"], "door": r["door"]})
            if r["visitor"] in players:
                ws._pending_messages[r["visitor"]] = "敲了半天没人应门。"
    for key, ps in list(_passes.items()):
        if gts >= ps["expires_gts"]:
            _expire_pass(key, "timeout"); continue
        v = players.get(ps["visitor"])
        if v is None:
            _expire_pass(key, "left"); continue
        inside = ws.get_zone_at(v["position"]["x"], v["position"]["y"]).get("sector") == ps["home"]
        if inside:
            ps["entered"] = True
        elif ps["entered"]:
            _expire_pass(key, "left")
    # 过期很久的记录清掉（保留 1 游戏小时供查询）
    for rid, r in list(_requests.items()):
        if r["status"] != "pending" and gts - r["expires_gts"] > 3600:
            del _requests[rid]


def export_state() -> dict:
    return {"requests": {k: dict(v) for k, v in _requests.items()}, "passes": {k: dict(v) for k, v in _passes.items()}}


def import_state(d: dict) -> None:
    _requests.clear(); _passes.clear()
    _requests.update(d.get("requests") or {}); _passes.update(d.get("passes") or {})


def _reset_for_tests() -> None:
    _requests.clear(); _passes.clear()
