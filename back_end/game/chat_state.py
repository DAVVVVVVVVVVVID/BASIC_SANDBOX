"""
chat_state.py — 对话系统状态管理

维护两类状态：
  ChatRequest — 对话邀请（pending / active / rejected / expired）
  ChatRoom    — 聊天室（active / closed）
"""

import time
import uuid
from typing import Optional

from game import chat_log

# ── 内存状态 ─────────────────────────────────────────────────────────────────
_chat_requests: dict[str, dict] = {}   # request_id -> ChatRequest dict
_chat_rooms:    dict[str, dict] = {}   # chat_room_id -> ChatRoom dict

# B9 对话协议常量（依据 AI Town：INVITE_TIMEOUT 60 s / CONVERSATION_COOLDOWN 15 s /
# PLAYER_CONVERSATION_COOLDOWN 60 s / MAX_CONVERSATION_MESSAGES 8 → 这里双方各 8 取 16，假设）
_REQUEST_TIMEOUT      = 60.0   # 秒，所有邀请（单人 / 多人）统一超时
WALK_TIMEOUT          = 30.0   # 秒，walking_over 最长等待，到时直接建房
MEET_DISTANCE         = 1      # 曼哈顿距离 ≤ 1 视为「相邻」（假设）
CHAT_COOLDOWN_PLAYER  = 60.0   # 秒，退出对话后本人冷却
CHAT_COOLDOWN_PAIR    = 15.0   # 秒，同一对人之间冷却
MAX_MESSAGES          = 16     # 房间消息上限，达到后 room_limit 关闭
_MSG_SEQ_COUNTER: dict[str, int] = {}  # chat_room_id -> 最新 seq
_last_chat_end:  dict[str, float]       = {}   # entity -> 上次对话结束（墙钟）
_last_pair_end:  dict[frozenset, float] = {}   # {a, b} -> 上次这对人对话结束


# ── 内部工具 ──────────────────────────────────────────────────────────────────

def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _next_seq(room_id: str) -> int:
    _MSG_SEQ_COUNTER[room_id] = _MSG_SEQ_COUNTER.get(room_id, 0) + 1
    return _MSG_SEQ_COUNTER[room_id]


# ── ChatRequest ───────────────────────────────────────────────────────────────

def create_chat_request(
    from_entity_id: str,
    to_entity_ids: list[str],
    greeting: str,
) -> str:
    """创建对话邀请，返回 request_id。"""
    request_id = _new_id()
    _chat_requests[request_id] = {
        "request_id":       request_id,
        "from_entity_id":   from_entity_id,
        "to_entity_ids":    list(to_entity_ids),
        "greeting":         greeting,
        "status":           "pending",
        "accepted_ids":     [],
        "rejected_ids":     [],
        "accepted_messages": [],   # [{"entity_id": str, "message": str}, ...] 按接受顺序
        "chat_room_id":     None,
        "created_at":       time.time(),
        # B9 walking_over
        "participants":     None,
        "target_arena_id":  None,
        "walking_since":    None,
    }
    return request_id


def chat_cooldown_remaining(from_entity_id: str, to_entity_ids: list[str], now: float | None = None) -> float:
    """B9 ③：发起方 / 任一受邀方在 60 s 本人冷却内，或这对人在 15 s 配对冷却内 → 返回剩余秒数，0 = 可发起。"""
    now = now or time.time()
    worst = 0.0
    for eid in [from_entity_id, *to_entity_ids]:
        end = _last_chat_end.get(eid)
        if end is not None:
            worst = max(worst, CHAT_COOLDOWN_PLAYER - (now - end))
    for eid in to_entity_ids:
        end = _last_pair_end.get(frozenset((from_entity_id, eid)))
        if end is not None:
            worst = max(worst, CHAT_COOLDOWN_PAIR - (now - end))
    return max(0.0, worst)


def _record_chat_end(entity_ids: list[str], now: float | None = None) -> None:
    now = now or time.time()
    ids = list(dict.fromkeys(entity_ids))
    for eid in ids:
        _last_chat_end[eid] = now
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            _last_pair_end[frozenset((ids[i], ids[j]))] = now


def get_pending_requests_for(entity_id: str, players: dict) -> list[dict]:
    """返回该 entity_id 收到的待处理请求列表（含发起者名字）。"""
    result = []
    _expire_old_requests()
    for req in _chat_requests.values():
        if req["status"] != "pending":
            continue
        if entity_id not in req["to_entity_ids"]:
            continue
        if entity_id in req["accepted_ids"] or entity_id in req["rejected_ids"]:
            continue
        from_player = players.get(req["from_entity_id"], {})
        result.append({
            "request_id":     req["request_id"],
            "from_entity_id": req["from_entity_id"],
            "from_name":      from_player.get("name", req["from_entity_id"]),
            "greeting":       req["greeting"],
        })
    return result


def respond_to_request(
    entity_id: str,
    request_id: str,
    accept: bool,
    message: str,
    players: dict,
) -> dict:
    """
    响应对话请求。
    返回: {"chat_room_id": str|None, "status": "waiting"|"room_created"|"rejected"}
    """
    req = _chat_requests.get(request_id)
    if req is None or req["status"] != "pending":
        return {"chat_room_id": None, "status": "rejected"}

    if not accept:
        if entity_id not in req["rejected_ids"]:
            req["rejected_ids"].append(entity_id)
    else:
        if entity_id not in req["accepted_ids"]:
            req["accepted_ids"].append(entity_id)
            req.setdefault("accepted_messages", []).append(
                {"entity_id": entity_id, "message": message}
            )

    to_ids = req["to_entity_ids"]

    # 单人邀请：有人接受 → 进入 walking_over（B9 ①），拒绝直接返回
    if len(to_ids) == 1:
        if not accept:
            req["status"] = "rejected"
            chat_log.log_event("request_rejected", None, [req["from_entity_id"], entity_id], request_id=request_id)
            return {"chat_room_id": None, "status": "rejected"}
        return _start_walking_over(req, [req["from_entity_id"], entity_id], players)

    # 多人邀请：等待所有人响应
    all_responded = set(to_ids) <= (set(req["accepted_ids"]) | set(req["rejected_ids"]))
    if not all_responded:
        return {"chat_room_id": None, "status": "waiting"}

    # 所有人都已响应，将接受者 + 发起者放入聊天室
    accepted = req["accepted_ids"]
    if not accepted:
        req["status"] = "rejected"
        return {"chat_room_id": None, "status": "rejected"}

    return _start_walking_over(req, [req["from_entity_id"]] + accepted, players)


# ── B9 ①：walking_over ────────────────────────────────────────────────────────

def _arena_of(entity_id: str, players: dict) -> str | None:
    from game.world_state import _ZONE_LOOKUP
    p = players.get(entity_id)
    if p is None:
        return None
    pos = p["position"]
    return _ZONE_LOOKUP.get((pos["x"], pos["y"]), {}).get("arena")


def _start_walking_over(req: dict, participants: list[str], players: dict) -> dict:
    """接受后不立刻建房：双方走向发起者所在 arena（target_arena_id），相邻或 30 s 超时才建房。"""
    req["participants"] = list(participants)
    req["target_arena_id"] = _arena_of(req["from_entity_id"], players)
    req["walking_since"] = time.time()
    req["status"] = "walking_over"
    for eid in participants:
        p = players.get(eid)
        if p is not None and p["state"] in ("idle", "walking"):
            p["state"] = "walking_over"
    return {
        "chat_room_id":    None,
        "status":          "walking_over",
        "target_arena_id": req["target_arena_id"],
        "participants":    req["participants"],
    }


def _all_met(req: dict, players: dict) -> bool:
    """所有参与者都在 target_arena 内且与发起者曼哈顿距离 ≤ MEET_DISTANCE。"""
    host = players.get(req["from_entity_id"])
    if host is None:
        return False
    hx, hy = host["position"]["x"], host["position"]["y"]
    for eid in req["participants"]:
        p = players.get(eid)
        if p is None:
            return False
        if req["target_arena_id"] is not None and _arena_of(eid, players) != req["target_arena_id"]:
            return False
        if abs(p["position"]["x"] - hx) + abs(p["position"]["y"] - hy) > MEET_DISTANCE:
            return False
    return True


def _finish_walking_over(req: dict, players: dict) -> str | None:
    """建房；掉线 / 被删的参与者剔除，不足两人则 expired。"""
    participants = [eid for eid in req["participants"] if eid in players]
    for eid in req["participants"]:
        p = players.get(eid)
        if p is not None and p["state"] == "walking_over":
            p["state"] = "idle"
    if len(participants) < 2:
        req["status"] = "expired"
        chat_log.log_event("request_expired", None, req["participants"], request_id=req["request_id"], reason="participant_left")
        return None
    room_id = _create_room(
        participants=participants,
        players=players,
        greeting_from=req["from_entity_id"],
        greeting_text=req["greeting"],
        accept_msgs=req.get("accepted_messages", []),
    )
    req["chat_room_id"] = room_id
    req["status"] = "active"
    return room_id


def tick(now: float | None = None) -> None:
    """
    由后台 ticker 每 200 ms 调一次（也在 get_pending 前调）：
    - pending 超时 60 s（单人 / 多人统一，B9 ②）：未响应者视为拒绝；有接受者 → walking_over，否则 expired
    - walking_over：全员相邻或 30 s 超时 → 建房
    """
    now = now or time.time()
    from game.world_state import _players as players
    for req in list(_chat_requests.values()):
        if req["status"] == "pending":
            if now - req["created_at"] < _REQUEST_TIMEOUT:
                continue
            for eid in req["to_entity_ids"]:
                if eid not in req["accepted_ids"] and eid not in req["rejected_ids"]:
                    req["rejected_ids"].append(eid)
            if req["accepted_ids"]:
                _start_walking_over(req, [req["from_entity_id"]] + req["accepted_ids"], players)
            else:
                req["status"] = "expired"
                chat_log.log_event("request_expired", None, [req["from_entity_id"], *req["to_entity_ids"]], request_id=req["request_id"])
        elif req["status"] == "walking_over":
            if _all_met(req, players) or now - (req.get("walking_since") or now) >= WALK_TIMEOUT:
                _finish_walking_over(req, players)
    _purge_finished(now)


_REQUEST_KEEP_S = 3600.0        # 非 pending / walking_over 的邀请（expired / rejected / active→已建房）保留 1 h
_ROOM_KEEP_S    = 86400.0       # 关闭的房间保留 24 h（/chat/room/{id} 还能看；JSONL 是永久记录）


def _purge_finished(now: float) -> int:
    """W11 维护 Q2：结束的邀请 / 房间不再无限留在内存与检查点里。返回清掉的条数。"""
    n = 0
    for rid, req in list(_chat_requests.items()):
        if req["status"] in ("pending", "walking_over"):
            continue
        if now - float(req.get("created_at") or now) >= _REQUEST_KEEP_S:
            del _chat_requests[rid]; n += 1
    for room_id, room in list(_chat_rooms.items()):
        if room["status"] != "closed":
            continue
        closed_at = room.get("closed_at")
        if closed_at is None:                       # 旧检查点里的关闭房间没有时刻：从现在起算
            room["closed_at"] = now; continue
        if now - float(closed_at) >= _ROOM_KEEP_S:
            del _chat_rooms[room_id]; _MSG_SEQ_COUNTER.pop(room_id, None); n += 1
    return n


def _expire_old_requests() -> None:
    tick()


# ── ChatRoom ──────────────────────────────────────────────────────────────────

def _create_room(
    participants: list[str],
    players: dict,
    greeting_from: Optional[str] = None,
    greeting_text: Optional[str] = None,
    accept_msgs: Optional[list[dict]] = None,
) -> str:
    """创建聊天室，施加 chat_active buff，并写入招呼语和接受回复作为初始消息。"""
    room_id = _new_id()
    _chat_rooms[room_id] = {
        "chat_room_id": room_id,
        "participants": list(participants),
        "messages":     [],
        "events":       [],
        "status":       "active",
    }
    _MSG_SEQ_COUNTER[room_id] = 0

    chat_log.log_event("room_open", room_id, participants)
    # 发起者的招呼语作为第一条消息
    if greeting_from and greeting_text:
        seq = _next_seq(room_id)
        _chat_rooms[room_id]["messages"].append({
            "seq":            seq,
            "from_entity_id": greeting_from,
            "content":        greeting_text,
            "timestamp":      _now_iso(),
        })
        _log_msg(room_id, seq, greeting_from, greeting_text, players)

    # 接受者的回复，按接受顺序排列（只写入最终参与者的消息）
    participant_set = set(participants)
    for item in (accept_msgs or []):
        if item["entity_id"] in participant_set:
            seq = _next_seq(room_id)
            _chat_rooms[room_id]["messages"].append({
                "seq":            seq,
                "from_entity_id": item["entity_id"],
                "content":        item["message"],
                "timestamp":      _now_iso(),
            })
            _log_msg(room_id, seq, item["entity_id"], item["message"], players)

    # 对所有参与者施加 chat_active buff
    for eid in participants:
        _apply_chat_buff(eid, players)
    return room_id


def _log_msg(room_id: str, seq: int, from_id: str, text: str, players: dict) -> None:
    room = _chat_rooms.get(room_id, {})
    p = players.get(from_id, {})
    chat_log.log_message(room_id, seq, from_id, p.get("name", from_id),
                         [e for e in room.get("participants", []) if e != from_id], text, p.get("controller", "human"))


def _apply_chat_buff(entity_id: str, players: dict) -> None:
    player = players.get(entity_id)
    if player is None:
        return
    # 移除旧的 chat_active buff（如有）
    player["buffs"] = [b for b in player["buffs"] if b["key"] != "chat_active"]
    player["buffs"].append({
        "key":       "chat_active",
        "value":     0.0,
        "mode":      "persistent",
        "remaining": None,
        "source":    "chat_system",
    })
    player["canMove"]     = False
    player["canUse"]      = False
    player["state"]       = "talking"


def _remove_chat_buff(entity_id: str, players: dict) -> None:
    player = players.get(entity_id)
    if player is None:
        return
    player["buffs"] = [b for b in player["buffs"] if b["key"] != "chat_active"]
    player["canMove"]     = True
    player["canUse"]      = True
    if player["state"] == "talking":
        player["state"] = "idle"


def get_room(room_id: str, since_seq: int = 0) -> dict | None:
    room = _chat_rooms.get(room_id)
    if room is None:
        return None
    from game.world_state import _players as players
    msgs = [m for m in room["messages"] if m["seq"] > since_seq]
    evts = [e for e in room["events"]   if e["seq"] > since_seq]
    # 为消息补充 from_name
    enriched_msgs = []
    for m in msgs:
        p = players.get(m["from_entity_id"], {})
        enriched_msgs.append({**m, "from_name": p.get("name", m["from_entity_id"])})
    enriched_evts = []
    for e in evts:
        p = players.get(e.get("entity_id", ""), {})
        enriched_evts.append({**e, "name": p.get("name", e.get("entity_id", ""))})
    return {
        "status":       room["status"],
        "participants": room["participants"],
        "messages":     enriched_msgs,
        "events":       enriched_evts,
    }


def post_message(entity_id: str, room_id: str, content: str) -> dict | None:
    """在聊天室中发言，返回 {"seq": int} 或 None（房间不存在）。"""
    room = _chat_rooms.get(room_id)
    if room is None or room["status"] != "active":
        return None
    seq = _next_seq(room_id)
    room["messages"].append({
        "seq":            seq,
        "from_entity_id": entity_id,
        "content":        content,
        "timestamp":      _now_iso(),
    })
    from game.world_state import _players as players
    _log_msg(room_id, seq, entity_id, content, players)
    if len(room["messages"]) >= MAX_MESSAGES:               # B9 ④
        _close_room(room, players, reason="room_limit")
        return {"seq": seq, "room_closed": True, "reason": "room_limit"}
    return {"seq": seq, "room_closed": False}


def _close_room(room: dict, players: dict, reason: str) -> None:
    """关闭房间：写 event、给所有参与者解 buff、记冷却。"""
    seq = _next_seq(room["chat_room_id"])
    room["events"].append({
        "seq":       seq,
        "type":      reason,
        "entity_id": None,
        "timestamp": _now_iso(),
    })
    participants = list(room["participants"])
    for eid in participants:
        _remove_chat_buff(eid, players)
    _record_chat_end(participants)
    room["participants"] = []
    room["status"] = "closed"; room["closed_at"] = time.time()
    chat_log.log_event(reason, room["chat_room_id"], participants)
    if reason != "room_close":
        chat_log.log_event("room_close", room["chat_room_id"], participants, reason=reason)


def exit_room(entity_id: str, room_id: str) -> dict | None:
    """退出聊天室，返回 {"room_closed": bool} 或 None。"""
    room = _chat_rooms.get(room_id)
    if room is None:
        return None
    from game.world_state import _players as players
    # 从参与者列表中移除
    if entity_id in room["participants"]:
        room["participants"].remove(entity_id)
        seq = _next_seq(room_id)
        room["events"].append({
            "seq":       seq,
            "type":      "player_exit",
            "entity_id": entity_id,
            "timestamp": _now_iso(),
        })
    # 移除 buff，记冷却：本人 60 s；与仍在房间里的每个人 15 s 配对冷却（他们自己的 60 s 等他们退出时记）
    _remove_chat_buff(entity_id, players)
    now = time.time()
    _last_chat_end[entity_id] = now
    for other in room["participants"]:
        _last_pair_end[frozenset((entity_id, other))] = now
    chat_log.log_event("player_exit", room_id, [entity_id, *room["participants"]], entity=entity_id)
    # 若无人在场，关闭房间
    if not room["participants"]:
        room["status"] = "closed"; room["closed_at"] = time.time()
        chat_log.log_event("room_close", room_id, [entity_id], reason="all_left")
        return {"room_closed": True}
    return {"room_closed": False}


# ── 附近 Player 查询 ──────────────────────────────────────────────────────────

def cleanup_player_chats(entity_id: str) -> None:
    """player 被移除时调用，正确退出所有聊天室（必须在 _players 仍包含该 player 时调用）。"""
    from game.world_state import _players as players
    for room_id, room in list(_chat_rooms.items()):
        if room["status"] != "active":
            continue
        if entity_id not in room["participants"]:
            continue
        room["participants"].remove(entity_id)
        seq = _next_seq(room_id)
        room["events"].append({
            "seq":       seq,
            "type":      "player_exit",
            "entity_id": entity_id,
            "timestamp": _now_iso(),
        })
        _remove_chat_buff(entity_id, players)
        now = time.time()
        _last_chat_end[entity_id] = now
        for other in room["participants"]:
            _last_pair_end[frozenset((entity_id, other))] = now
        chat_log.log_event("player_exit", room_id, [entity_id, *room["participants"]], entity=entity_id, reason="player_removed")
        if not room["participants"]:
            room["status"] = "closed"; room["closed_at"] = time.time()
            chat_log.log_event("room_close", room_id, [entity_id], reason="all_left")


def get_nearby_players(entity_id: str, players: dict, zone_lookup: dict) -> list[dict]:
    """返回与 entity_id 处于同一 Arena 的其他 player 列表。"""
    me = players.get(entity_id)
    if me is None:
        return []
    pos = me["position"]
    my_arena = zone_lookup.get((pos["x"], pos["y"]), {}).get("arena")
    if my_arena is None:
        return []
    result = []
    for pid, p in players.items():
        if pid == entity_id:
            continue
        if p.get("away") or not p.get("online", True):            # W8 Q0e：away / 离线不算在场
            continue
        ppos = p["position"]
        p_arena = zone_lookup.get((ppos["x"], ppos["y"]), {}).get("arena")
        if p_arena == my_arena:
            result.append({
                "entity_id": pid,
                "name":      p.get("name", pid),
                "arena_id":  my_arena,
            })
    return result


# ── 持久化：导出 / 回填（B2） ─────────────────────────────────────────────────

def export_state() -> dict:
    import copy
    return {
        "requests": copy.deepcopy(_chat_requests),
        "rooms":    copy.deepcopy(_chat_rooms),
        "seq":      dict(_MSG_SEQ_COUNTER),
        "last_chat_end": dict(_last_chat_end),
        "last_pair_end": {"|".join(sorted(k)): v for k, v in _last_pair_end.items()},
    }


def import_state(data: dict) -> None:
    _chat_requests.clear(); _chat_rooms.clear(); _MSG_SEQ_COUNTER.clear()
    _last_chat_end.clear(); _last_pair_end.clear()
    if not data:
        return
    _chat_requests.update(data.get("requests") or {})
    for req in _chat_requests.values():                       # W2 之前的检查点补字段
        req.setdefault("participants", None); req.setdefault("target_arena_id", None); req.setdefault("walking_since", None)
    _chat_rooms.update(data.get("rooms") or {})
    _MSG_SEQ_COUNTER.update({k: int(v) for k, v in (data.get("seq") or {}).items()})
    _last_chat_end.update({k: float(v) for k, v in (data.get("last_chat_end") or {}).items()})
    _last_pair_end.update({frozenset(k.split("|")): float(v) for k, v in (data.get("last_pair_end") or {}).items()})


def reconcile_chat_buffs(players: dict) -> int:
    """Q0：检查点回填后，player 身上的 chat_active 必须对应一个 active 房间，否则清掉（state 回 idle）。返回修正数。"""
    in_room = {pid for room in _chat_rooms.values() if room["status"] == "active" for pid in room["participants"]}
    fixed = 0
    for pid, p in players.items():
        has = any(b.get("key") == "chat_active" for b in p.get("buffs", []))
        if has and pid not in in_room:
            _remove_chat_buff(pid, players); fixed += 1
        elif not has and pid in in_room:
            _apply_chat_buff(pid, players); fixed += 1
    return fixed


def _reset_for_tests() -> None:
    _chat_requests.clear(); _chat_rooms.clear(); _MSG_SEQ_COUNTER.clear()
    _last_chat_end.clear(); _last_pair_end.clear()
