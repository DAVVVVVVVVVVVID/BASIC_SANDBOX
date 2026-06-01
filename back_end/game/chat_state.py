"""
chat_state.py — 对话系统状态管理

维护两类状态：
  ChatRequest — 对话邀请（pending / active / rejected / expired）
  ChatRoom    — 聊天室（active / closed）
"""

import time
import uuid
from typing import Optional

# ── 内存状态 ─────────────────────────────────────────────────────────────────
_chat_requests: dict[str, dict] = {}   # request_id -> ChatRequest dict
_chat_rooms:    dict[str, dict] = {}   # chat_room_id -> ChatRoom dict

_REQUEST_TIMEOUT = 60.0   # 秒，多人邀请超时时间
_MSG_SEQ_COUNTER: dict[str, int] = {}  # chat_room_id -> 最新 seq


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
    }
    return request_id


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

    # 单人邀请：有人接受立即建房，拒绝直接返回
    if len(to_ids) == 1:
        if not accept:
            req["status"] = "rejected"
            return {"chat_room_id": None, "status": "rejected"}
        room_id = _create_room(
            participants=[req["from_entity_id"], entity_id],
            players=players,
            greeting_from=req["from_entity_id"],
            greeting_text=req["greeting"],
            accept_msgs=req.get("accepted_messages", []),
        )
        req["chat_room_id"] = room_id
        req["status"] = "active"
        return {
            "chat_room_id": room_id,
            "status":       "room_created",
            "participants": _chat_rooms[room_id]["participants"],
        }

    # 多人邀请：等待所有人响应
    all_responded = set(to_ids) <= (set(req["accepted_ids"]) | set(req["rejected_ids"]))
    if not all_responded:
        return {"chat_room_id": None, "status": "waiting"}

    # 所有人都已响应，将接受者 + 发起者放入聊天室
    accepted = req["accepted_ids"]
    if not accepted:
        req["status"] = "rejected"
        return {"chat_room_id": None, "status": "rejected"}

    participants = [req["from_entity_id"]] + accepted
    room_id = _create_room(
        participants=participants,
        players=players,
        greeting_from=req["from_entity_id"],
        greeting_text=req["greeting"],
        accept_msgs=req.get("accepted_messages", []),
    )
    req["chat_room_id"] = room_id
    req["status"] = "active"
    return {
        "chat_room_id": room_id,
        "status":       "room_created",
        "participants": _chat_rooms[room_id]["participants"],
    }


def _expire_old_requests() -> None:
    """超时的多人邀请：未响应者视为拒绝，若有接受者则创建聊天室。"""
    now = time.time()
    from game.world_state import _players as players
    for req in list(_chat_requests.values()):
        if req["status"] != "pending":
            continue
        if len(req["to_entity_ids"]) <= 1:
            continue
        if now - req["created_at"] < _REQUEST_TIMEOUT:
            continue
        # 超时：未响应的视为拒绝
        for eid in req["to_entity_ids"]:
            if eid not in req["accepted_ids"] and eid not in req["rejected_ids"]:
                req["rejected_ids"].append(eid)
        accepted = req["accepted_ids"]
        if accepted:
            participants = [req["from_entity_id"]] + accepted
            room_id = _create_room(
                participants=participants,
                players=players,
                greeting_from=req["from_entity_id"],
                greeting_text=req["greeting"],
                accept_msgs=req.get("accepted_messages", []),
            )
            req["chat_room_id"] = room_id
            req["status"] = "active"
        else:
            req["status"] = "expired"


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

    # 发起者的招呼语作为第一条消息
    if greeting_from and greeting_text:
        seq = _next_seq(room_id)
        _chat_rooms[room_id]["messages"].append({
            "seq":            seq,
            "from_entity_id": greeting_from,
            "content":        greeting_text,
            "timestamp":      _now_iso(),
        })

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

    # 对所有参与者施加 chat_active buff
    for eid in participants:
        _apply_chat_buff(eid, players)
    return room_id


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
    return {"seq": seq}


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
    # 移除 buff
    _remove_chat_buff(entity_id, players)
    # 若无人在场，关闭房间
    if not room["participants"]:
        room["status"] = "closed"
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
        if not room["participants"]:
            room["status"] = "closed"


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
        ppos = p["position"]
        p_arena = zone_lookup.get((ppos["x"], ppos["y"]), {}).get("arena")
        if p_arena == my_arena:
            result.append({
                "entity_id": pid,
                "name":      p.get("name", pid),
                "arena_id":  my_arena,
            })
    return result
