"""敲门回应（§3.40）：POST /door/respond {request_id, entity_id, accept} —— 只限这家的主人。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from game import doors
from game.world_state import STATE_LOCK

router = APIRouter(prefix="/door", tags=["door"])


class RespondBody(BaseModel):
    request_id: str
    entity_id: str
    accept: bool


@router.post("/respond")
def door_respond(body: RespondBody):
    with STATE_LOCK:
        r, reason = doors.respond(body.entity_id, body.request_id, body.accept)
    if reason == "player_not_found":
        raise HTTPException(status_code=404, detail=f"entity not found: {body.entity_id}")
    if reason == "unknown_request":
        raise HTTPException(status_code=404, detail=f"request not found: {body.request_id}")
    if reason:
        return {"success": False, "reason": reason, "request": None}
    return {"success": True, "reason": None, "request": r}


@router.get("/requests")
def door_requests(player: str):
    """主人：我家的待回应敲门；访客：我最近一次敲门的状态。"""
    from game.world_state import _players
    p = _players.get(player)
    if p is None:
        raise HTTPException(status_code=404, detail=f"entity not found: {player}")
    return {"pending_knocks": doors.pending_for_owner(p), "door_request": doors.visitor_view(player), "door_passes": doors.passes_of(player)}
