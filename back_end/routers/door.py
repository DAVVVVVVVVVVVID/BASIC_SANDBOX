"""敲门回应 / 门状态（§3.40 / §3.41）。"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from game import doors
from game.world_state import STATE_LOCK

router = APIRouter(prefix="/door", tags=["door"])


class RespondBody(BaseModel):
    request_id: str
    entity_id: str
    text: Optional[str] = None       # 隔门喊一句（answered）
    decline: bool = False            # 明确拒绝（declined）


@router.post("/respond")
def door_respond(body: RespondBody):
    """主人回应敲门：喊话（text）或拒绝（decline）。开门请走到门内侧 POST /action open_door。"""
    with STATE_LOCK:
        r, reason = doors.respond(body.entity_id, body.request_id, body.text, body.decline)
    if reason == "player_not_found":
        raise HTTPException(status_code=404, detail=f"entity not found: {body.entity_id}")
    if reason == "unknown_request":
        raise HTTPException(status_code=404, detail=f"request not found: {body.request_id}")
    if reason:
        return {"success": False, "reason": reason, "request": None}
    return {"success": True, "reason": None, "request": r}


@router.get("/requests")
def door_requests(player: str):
    """主人：我家的待回应敲门；访客：我最近一次敲门；我的钥匙；此刻敞开的门。"""
    from game.world_state import _players
    p = _players.get(player)
    if p is None:
        raise HTTPException(status_code=404, detail=f"entity not found: {player}")
    return {"pending_knocks": doors.pending_for_owner(p), "door_request": doors.visitor_view(player), "keys": doors.keys_of(p), "open_doors": doors.open_doors_view()}
