from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from game.world_state import (
    create_player, remove_player, get_player, touch_player, rejoin_player,
    get_player_buffs, clear_player_buffs, force_reset_player_state,
    apply_effects_to_player, get_recent_uses, get_recent_events, _players,
)

router = APIRouter()


class JoinRequest(BaseModel):
    name: str
    controller: str = "human"            # B6："human" | "agent"（与 AGENT_V2 join_player 同名）
    profile: Optional[dict] = None       # B6：{E, N, agent_id?}


class RejoinRequest(BaseModel):
    playerId: str


class EffectsRequest(BaseModel):
    effects: list[dict]                  # 与 object_types.json 同格式
    scene: Optional[str] = None          # "sandbox" | "live"，非空时切换衰减场景
    source: str = "effects"
    event: Optional[str] = None          # §3.11 A2：事件名（如 viewer_praised），只记录供对账


@router.post("/player/join")
def join(body: JoinRequest):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="name cannot be empty")
    if body.controller not in ("human", "agent"):
        raise HTTPException(status_code=400, detail="controller must be 'human' or 'agent'")
    player = create_player(body.name.strip(), controller=body.controller, profile=body.profile)
    return {"playerId": player["id"], "player": player}


@router.post("/player/rejoin")
def rejoin(body: RejoinRequest):
    """B6：agent 进程重拉后用同一 playerId 续接（置 online=True、刷新心跳）。"""
    player = rejoin_player(body.playerId)
    if player is None:
        raise HTTPException(status_code=404, detail=f"player not found: {body.playerId}")
    return {"playerId": player["id"], "player": player}


@router.delete("/player/{player_id}/leave")
def leave(player_id: str):
    remove_player(player_id)
    return {"ok": True}


@router.post("/player/{player_id}/heartbeat")
def heartbeat(player_id: str):
    """E②：显式心跳（任何 controller）。返回 online 与 last_tick_ts。agent 必须用它（或 rejoin）保持 online=true。"""
    if not touch_player(player_id):
        raise HTTPException(status_code=404, detail=f"player not found: {player_id}")
    p = _players[player_id]
    return {"ok": True, "online": p.get("online", True), "last_tick_ts": p.get("last_tick_ts")}


@router.get("/player/{player_id}")
def get_player_data(player_id: str):
    # E②：只对 controller=human 刷心跳（人类前端的老路径）；agent 的 GET 无在线副作用，心跳走 POST /player/{id}/heartbeat
    touch_player(player_id, human_only=True)
    player = get_player(player_id)
    if player is None:
        raise HTTPException(status_code=404, detail=f"player not found: {player_id}")
    return player


def _state_view(p: dict) -> dict:
    return {
        "id":           p["id"],
        "vars":         {k: p[k] for k in ("fullness", "energy", "social", "fun", "mood")},
        "mood_base":    p.get("mood_base"),
        "emotion_tags": p.get("emotion_tags", []),
        "closeness":    p.get("closeness", {}),
        "scene":        p.get("scene", "sandbox"),
        "controller":   p.get("controller", "human"),
        "online":       p.get("online", True),
        "agent_id":     p.get("agent_id"),
        "last_tick_ts": p.get("last_tick_ts"),
        "recent_uses":  get_recent_uses(p["id"]),
        "recent_events": get_recent_events(p["id"]),     # §3.11 A2：最近 /effects 推送的 event 记录
    }


@router.get("/player/{player_id}/state")
def get_player_state(player_id: str):
    """B13 ②：七变量原始数值 + last_tick_ts（给自我层同步与评测）。不刷新心跳、不清 pendingMessage。"""
    p = _players.get(player_id)
    if p is None:
        raise HTTPException(status_code=404, detail=f"player not found: {player_id}")
    return _state_view(p)


@router.post("/player/{player_id}/effects")
def post_player_effects(player_id: str, body: EffectsRequest):
    """B13 ③：推送与 object_types.json 同格式的 effect 列表（直播服务经自我层推「观众进入 +12 social」等）。"""
    if body.scene is not None and body.scene not in ("sandbox", "live"):
        raise HTTPException(status_code=400, detail="scene must be 'sandbox' or 'live'")
    res = apply_effects_to_player(player_id, body.effects, body.scene, source=body.source, event=body.event)
    if res is None:
        raise HTTPException(status_code=404, detail=f"player not found: {player_id}")
    return {"ok": True, **res["summary"], "event": body.event, "state": _state_view(res["player"])}


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


@router.post("/admin/checkpoint")
def admin_checkpoint():
    """立即写一份 SQLite 检查点（B2），返回摘要。"""
    from game.persistence import save_checkpoint
    return {"ok": True, **save_checkpoint()}


@router.get("/admin/metrics")
def admin_metrics():
    """运行指标：tick 耗时 / 间隔分位、玩家数、WebSocket 订阅数、进程 RSS（负载测试用）。"""
    import resource
    from game import ticker
    from game.world_state import _players
    try:
        from routers.ws import hub
        ws_clients = hub.client_count()
    except Exception:
        ws_clients = 0
    from game.world_state import SANDBOX_SEED, MAP_VERSION
    return {
        **ticker.metrics(),
        "seed": SANDBOX_SEED,
        "mapVersion": MAP_VERSION,
        "players": len(_players),
        "ws_clients": ws_clients,
        "rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 1),
    }


@router.get("/admin/self-sync")
def admin_self_sync():
    """自我层同步状态：发送 / 失败计数、最近 drift、待发 delta（联调用）。"""
    from game.self_sync import snapshot_stats
    return snapshot_stats()
