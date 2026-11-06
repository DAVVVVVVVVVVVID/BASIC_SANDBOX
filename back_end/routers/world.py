from typing import Optional
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from models.world import WorldData
from game.world_state import get_world

router = APIRouter()
_FIELDS = ("tiles", "objects", "worldState", "players", "tiled", "zone_names", "map")


@router.get("/world", response_model=WorldData)
def get_world_data(fields: Optional[str] = Query(default=None, description="逗号分隔，只回这些顶层字段，如 players,objects,worldState（E③ 瘦身）")):
    # 只读（B8）：时间推进与 buff tick 由后台 ticker 负责
    world = get_world()
    if fields:
        want = {f.strip() for f in fields.split(",") if f.strip() in _FIELDS}
        # 走同一个响应模型序列化（字段形状与全量一致），只保留请求的顶层键
        return JSONResponse(content=WorldData(**world).model_dump(include=want))
    return world
