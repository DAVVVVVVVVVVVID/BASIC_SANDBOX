from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from game.world_state import (
    create_player, remove_player, get_player, touch_player,
    get_player_buffs, clear_player_buffs, force_reset_player_state,
)

router = APIRouter()


class JoinRequest(BaseModel):
    name: str


@router.post("/player/join")
def join(body: JoinRequest):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="name cannot be empty")
    player = create_player(body.name.strip())
    return {"playerId": player["id"], "player": player}


@router.delete("/player/{player_id}/leave")
def leave(player_id: str):
    remove_player(player_id)
    return {"ok": True}


@router.get("/player/{player_id}")
def get_player_data(player_id: str):
    touch_player(player_id)
    player = get_player(player_id)
    if player is None:
        raise HTTPException(status_code=404, detail=f"player not found: {player_id}")
    return player


# ── 管理接口 ──────────────────────────────────────────────────────────────────

@router.get("/admin/player/{player_id}/buffs")
def admin_get_buffs(player_id: str):
    return {"buffs": get_player_buffs(player_id)}


@router.delete("/admin/player/{player_id}/buffs")
def admin_clear_buffs(player_id: str):
    count = clear_player_buffs(player_id)
    return {"ok": True, "cleared": count}


@router.post("/admin/player/force-reset")
def admin_force_reset(body: dict = {}):
    entity_id = body.get("entity_id")
    if not entity_id:
        raise HTTPException(status_code=400, detail="entity_id required")
    summary = force_reset_player_state(entity_id)
    return {"ok": True, **summary}
