from fastapi import APIRouter
from game.world_state import (
    get_player, get_player_profile, run_buff_tick,
    get_player_buffs, clear_player_buffs, force_reset_player_state,
)
from game.time_state import get_last_game_delta

router = APIRouter()


@router.get("/player")
def get_player_data():
    game_delta_ms = get_last_game_delta()
    run_buff_tick(game_delta_ms)
    data = get_player()
    data["profile"] = get_player_profile()
    return data


# ── 管理接口 ──────────────────────────────────────────────────────────────────

@router.get("/admin/player/buffs")
def admin_get_buffs():
    """返回玩家当前所有 buff。"""
    return {"buffs": get_player_buffs()}


@router.delete("/admin/player/buffs")
def admin_clear_buffs():
    """强制清除玩家所有 buff（不离开对象）。"""
    count = clear_player_buffs()
    return {"ok": True, "cleared": count}


@router.post("/admin/player/force-reset")
def admin_force_reset(body: dict = {}):
    """
    强制重置玩家状态：离开当前对象（若有）并清除所有 buff/tag。
    body: {"entity_id": "player_01"}  （可选，默认 player_01）
    """
    entity_id = body.get("entity_id", "player_01")
    summary = force_reset_player_state(entity_id)
    return {"ok": True, **summary}
