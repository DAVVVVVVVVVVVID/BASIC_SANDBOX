from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from game.time_state import game_now_iso
from fastapi.responses import JSONResponse
from models.world import WorldData
from game.world_state import get_world

router = APIRouter()
_FIELDS = ("tiles", "objects", "worldState", "players", "tiled", "zone_names", "map", "decor")


@router.get("/admin/path")
def admin_path(frm: str = Query(..., alias="from", description="x,y"), to: Optional[str] = Query(None, description="x,y"),
               to_object: Optional[str] = None, to_arena: Optional[str] = None,
               ignore_locks: bool = False, mover: Optional[str] = Query(None, description="按这个 player 的门禁算（agent_id / player id）")):
    """W11 维护（X1）：任意两格 / 到物品站位 / 到 arena 的 BFS 最短路（走 edges，按当前游戏时刻的营业时间与门禁）。只读。"""
    from game import world_state as ws_
    def _xy(s: str) -> tuple[int, int]:
        try:
            a, b = s.split(","); return int(a), int(b)
        except Exception:
            raise HTTPException(status_code=400, detail=f"bad coordinate: {s!r} (want x,y)")
    start = _xy(frm)
    if not ws_.is_tile_walkable(*start):
        raise HTTPException(status_code=400, detail=f"start {start} not walkable")
    goals = ws_.goal_tiles_for(_xy(to) if to else None, to_object, to_arena)
    if not goals:
        raise HTTPException(status_code=404, detail="no goal tiles (bad to / to_object / to_arena)")
    mv = None
    if mover:
        mv = ws_._players.get(mover) or next((p for p in ws_._players.values() if p.get("agent_id") == mover or p.get("name") == mover), None)
        if mv is None:
            mv = {"id": mover, "agent_id": mover, "name": mover, "controller": "agent"}     # 不在线也能按身份算门禁
    with ws_.STATE_LOCK:
        res = ws_.path_query(start, goals, mover=mv, ignore_locks=ignore_locks)
    return {"from": {"x": start[0], "y": start[1]}, "goals": len(goals), "ignore_locks": ignore_locks,
            "mover": mover, "game_time": game_now_iso(), "mapVersion": ws_.MAP_VERSION, **res}


@router.get("/world", response_model=WorldData)
def get_world_data(fields: Optional[str] = Query(default=None, description="逗号分隔，只回这些顶层字段，如 players,objects,worldState（E③ 瘦身）")):
    # 只读（B8）：时间推进与 buff tick 由后台 ticker 负责
    world = get_world()
    if fields:
        want = {f.strip() for f in fields.split(",") if f.strip() in _FIELDS}
        # 走同一个响应模型序列化（字段形状与全量一致），只保留请求的顶层键
        return JSONResponse(content=WorldData(**world).model_dump(include=want))
    return world
