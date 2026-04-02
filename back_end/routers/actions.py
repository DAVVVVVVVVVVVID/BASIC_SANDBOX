from fastapi import APIRouter, HTTPException
from models.action import MoveRequest, MoveResponse, TurnRequest, TurnResponse, InteractRequest, InteractResponse
from game.world_state import (
    get_player, is_tile_walkable, update_player_position, update_player_facing,
    get_object_at,
)

router = APIRouter()

_DIRECTION_DELTA = {
    "up":    (0, -1),
    "down":  (0,  1),
    "left":  (-1, 0),
    "right": (1,  0),
}


def _compute_facing(current: dict, target_x: int, target_y: int) -> str:
    """根据当前位置到目标位置的偏移计算朝向（取主轴方向）。"""
    dx = target_x - current["x"]
    dy = target_y - current["y"]
    if abs(dy) >= abs(dx):
        return "up" if dy < 0 else "down"
    return "left" if dx < 0 else "right"


@router.post("/action/move", response_model=MoveResponse)
def move(body: MoveRequest):
    current = get_player()["position"]

    if body.direction is not None:
        dx, dy = _DIRECTION_DELTA[body.direction]
        new_x = current["x"] + dx
        new_y = current["y"] + dy
        facing = body.direction
    elif body.targetTile is not None:
        new_x = body.targetTile.x
        new_y = body.targetTile.y
        facing = _compute_facing(current, new_x, new_y)
    else:
        raise HTTPException(status_code=400, detail="direction 或 targetTile 必须提供其中一个")

    # 无论是否可行走，先更新朝向
    update_player_facing(facing)

    if not is_tile_walkable(new_x, new_y):
        return MoveResponse(success=False, facing=facing, reason="tile_not_walkable")

    update_player_position(new_x, new_y, facing)
    return MoveResponse(
        success=True,
        facing=facing,
        position={"x": new_x, "y": new_y},
        state="idle",
    )


@router.post("/action/turn", response_model=TurnResponse)
def turn(body: TurnRequest):
    update_player_facing(body.direction)
    return TurnResponse(facing=body.direction)


_FACING_DELTA = {
    "up":    (0, -1),
    "down":  (0,  1),
    "left":  (-1, 0),
    "right": (1,  0),
}


@router.post("/action/interact", response_model=InteractResponse)
def interact(body: InteractRequest):
    player = get_player()
    pos    = player["position"]
    dx, dy = _FACING_DELTA[player["facing"]]

    front_x = pos["x"] + dx
    front_y = pos["y"] + dy

    obj = get_object_at(front_x, front_y)
    if obj is None:
        return InteractResponse(success=False, reason="no_object_in_front")

    return InteractResponse(
        success=True,
        message=obj["description"],
        playerState="interacting",
    )
