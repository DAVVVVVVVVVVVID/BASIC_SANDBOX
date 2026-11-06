"""
routers/chat.py — 对话系统 API（Task 01）

端点：
  GET  /chat/nearby
  POST /chat/request
  GET  /chat/pending
  POST /chat/respond
  GET  /chat/room/{chat_room_id}
  POST /chat/message
  POST /chat/exit
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from game import chat_state
from game.world_state import _players as _players_dict, _ZONE_LOOKUP

router = APIRouter(prefix="/chat", tags=["chat"])


# ── Request / Response 模型 ───────────────────────────────────────────────────

class ChatRequestBody(BaseModel):
    from_entity_id: str
    to_entity_ids: list[str]
    greeting: str


class ChatRespondBody(BaseModel):
    entity_id: str
    request_id: str
    accept: bool
    message: str


class ChatMessageBody(BaseModel):
    entity_id: str
    chat_room_id: str
    content: str


class ChatExitBody(BaseModel):
    entity_id: str
    chat_room_id: str


# ── 1. 查询附近可对话 Player ──────────────────────────────────────────────────

@router.get("/nearby")
def get_nearby(entity_id: str):
    """返回与请求方处于同一 Arena 的其他 Player 列表。"""
    if entity_id not in _players_dict:
        raise HTTPException(status_code=404, detail=f"entity not found: {entity_id}")
    players = dict(_players_dict)
    nearby = chat_state.get_nearby_players(entity_id, players, _ZONE_LOOKUP)
    return {"players": nearby}


# ── 2. 发起对话请求 ───────────────────────────────────────────────────────────

@router.post("/request")
def post_chat_request(body: ChatRequestBody):
    """向一个或多个 Player 发起对话邀请，返回 request_id。"""
    if not body.to_entity_ids:
        raise HTTPException(status_code=400, detail="to_entity_ids cannot be empty")
    from game.world_state import mark_input, is_present
    mark_input(body.from_entity_id)
    from_player = _players_dict.get(body.from_entity_id, {})
    away = [t for t in body.to_entity_ids if t in _players_dict and not is_present(_players_dict[t])]
    if away:                                                    # W8 Q0e：away / 离线的人不接受邀请
        return {"request_id": None, "success": False, "reason": "target_away", "away": away}
    # B9 ③；W6 任务 4：human（作者 / 阿蝉）发起不受冷却约束（受邀 agent 的冷却也不拦人类的邀请）
    remaining = 0.0 if from_player.get("controller") == "human" else chat_state.chat_cooldown_remaining(body.from_entity_id, body.to_entity_ids)
    if remaining > 0:
        return {"request_id": None, "success": False, "reason": "chat_cooldown",
                "cooldown_remaining": round(remaining, 1)}
    request_id = chat_state.create_chat_request(
        from_entity_id=body.from_entity_id,
        to_entity_ids=body.to_entity_ids,
        greeting=body.greeting,
    )
    return {"request_id": request_id, "success": True}


# ── 2b. 查询对话请求状态 ──────────────────────────────────────────────────────

@router.get("/request/{request_id}")
def get_request_status(request_id: str):
    """查询对话请求当前状态（含 chat_room_id）。发起方用于轮询是否被接受。"""
    req = chat_state._chat_requests.get(request_id)
    if req is None:
        raise HTTPException(status_code=404, detail=f"request not found: {request_id}")
    chat_state.tick()
    return {
        "request_id":      req["request_id"],
        "status":          req["status"],              # pending | walking_over | active | rejected | expired
        "chat_room_id":    req["chat_room_id"],
        "accepted_ids":    req["accepted_ids"],
        "rejected_ids":    req["rejected_ids"],
        "target_arena_id": req.get("target_arena_id"),  # B9 ①（§3.9 C3 定名）
        "participants":    req.get("participants"),
    }


# ── 3. 查询待处理的对话请求 ───────────────────────────────────────────────────

@router.get("/pending")
def get_pending(entity_id: str):
    """返回该 entity_id 收到的待处理请求列表。"""
    players = dict(_players_dict)
    requests = chat_state.get_pending_requests_for(entity_id, players)
    return {"requests": requests}


# ── 4. 响应对话请求 ───────────────────────────────────────────────────────────

@router.post("/respond")
def respond(body: ChatRespondBody):
    """
    接受或拒绝对话请求。
    响应：
      - "rejected"     — 拒绝（或请求已不是 pending）
      - "waiting"      — 接受，但多人邀请还有人未响应
      - "walking_over" — 接受，双方走向 target_arena_id，相邻或 30 s 后建房（轮询 GET /chat/request/{id}）
    """
    from game.world_state import mark_input
    mark_input(body.entity_id)
    players = dict(_players_dict)
    result = chat_state.respond_to_request(
        entity_id=body.entity_id,
        request_id=body.request_id,
        accept=body.accept,
        message=body.message,
        players=_players_dict,   # 传原始引用以便修改 buff
    )
    return result


# ── 5. 查询聊天室状态 ─────────────────────────────────────────────────────────

@router.get("/room/{chat_room_id}")
def get_room(chat_room_id: str, entity_id: str = "", since_seq: int = 0):
    """
    获取聊天室状态（增量拉取）。
    since_seq: 只返回 seq > since_seq 的消息和事件。
    """
    room = chat_state.get_room(chat_room_id, since_seq=since_seq)
    if room is None:
        raise HTTPException(status_code=404, detail=f"chat room not found: {chat_room_id}")
    return room


# ── 6. 在聊天室发言 ───────────────────────────────────────────────────────────

@router.post("/message")
def post_message(body: ChatMessageBody):
    """在聊天室中发送一条消息。"""
    from game.world_state import mark_input
    mark_input(body.entity_id)
    result = chat_state.post_message(
        entity_id=body.entity_id,
        room_id=body.chat_room_id,
        content=body.content,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"chat room not found or closed: {body.chat_room_id}")
    return result


# ── 7. 退出聊天室 ─────────────────────────────────────────────────────────────

@router.post("/exit")
def exit_room(body: ChatExitBody):
    """退出聊天室，移除 chat_active buff，若房间空了则关闭。"""
    result = chat_state.exit_room(
        entity_id=body.entity_id,
        room_id=body.chat_room_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"chat room not found: {body.chat_room_id}")
    return result
