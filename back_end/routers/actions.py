from fastapi import APIRouter, HTTPException
from models.action import ActionRequest, ActionResponse
from models.world import Position
from game.world_state import (
    get_player, is_tile_walkable, update_player_position, update_player_facing,
    get_object_at, enter_object, leave_object,
)
from game.action_log import append_log

router = APIRouter()

_DIRECTION_DELTA = {
    "up":    (0, -1),
    "down":  (0,  1),
    "left":  (-1, 0),
    "right": (1,  0),
}


def _compute_facing(current: dict, target_x: int, target_y: int) -> str:
    dx = target_x - current["x"]
    dy = target_y - current["y"]
    if abs(dy) >= abs(dx):
        return "up" if dy < 0 else "down"
    return "left" if dx < 0 else "right"


def handle_move(entity_id: str, payload: dict) -> ActionResponse:
    current = get_player()["position"]
    direction = payload.get("direction")
    target_tile = payload.get("targetTile")

    if direction is not None:
        if direction not in _DIRECTION_DELTA:
            return ActionResponse(success=False, type="move", reason="invalid_direction")
        dx, dy = _DIRECTION_DELTA[direction]
        new_x = current["x"] + dx
        new_y = current["y"] + dy
        facing = direction
    elif target_tile is not None:
        new_x = target_tile["x"]
        new_y = target_tile["y"]
        facing = _compute_facing(current, new_x, new_y)
    else:
        return ActionResponse(success=False, type="move", reason="missing_direction_or_target")

    update_player_facing(facing)

    if not is_tile_walkable(new_x, new_y):
        return ActionResponse(
            success=False,
            type="move",
            reason="tile_not_walkable",
            result={"facing": facing},
        )

    update_player_position(new_x, new_y, facing)
    return ActionResponse(
        success=True,
        type="move",
        result={"facing": facing, "position": {"x": new_x, "y": new_y}, "state": "idle"},
    )


def handle_turn(entity_id: str, payload: dict) -> ActionResponse:
    direction = payload.get("direction")
    if direction not in _DIRECTION_DELTA:
        return ActionResponse(success=False, type="turn", reason="invalid_direction")
    update_player_facing(direction)
    return ActionResponse(success=True, type="turn", result={"facing": direction})


def handle_interact(entity_id: str, payload: dict) -> ActionResponse:
    player = get_player()
    pos    = player["position"]
    dx, dy = _DIRECTION_DELTA[player["facing"]]

    obj = get_object_at(pos["x"] + dx, pos["y"] + dy)
    if obj is None:
        return ActionResponse(success=False, type="interact", reason="no_object_in_front")

    return ActionResponse(
        success=True,
        type="interact",
        result={"message": obj["description"], "playerState": "interacting"},
    )


def handle_use(entity_id: str, payload: dict) -> ActionResponse:
    player = get_player()
    pos    = player["position"]
    dx, dy = _DIRECTION_DELTA[player["facing"]]

    obj = get_object_at(pos["x"] + dx, pos["y"] + dy)
    if obj is None:
        return ActionResponse(success=False, type="use", reason="no_object_in_front")

    if not obj.get("interactable", False):
        return ActionResponse(success=False, type="use", reason="not_interactable")

    if obj["currentUsers"] >= obj["maxUsers"]:
        return ActionResponse(
            success=False,
            type="use",
            reason="object_full",
            result={"currentUsers": obj["currentUsers"], "maxUsers": obj["maxUsers"]},
        )

    enter_object(obj["id"], entity_id)
    updated = get_player()
    return ActionResponse(
        success=True,
        type="use",
        result={
            "playerState":  updated["state"],
            "objectId":     obj["id"],
            "currentUsers": obj["currentUsers"],
            "maxUsers":     obj["maxUsers"],
        },
    )


def handle_leave(entity_id: str, payload: dict) -> ActionResponse:
    obj = leave_object(entity_id)
    if obj is None:
        return ActionResponse(success=False, type="leave", reason="not_using_any_object")

    return ActionResponse(
        success=True,
        type="leave",
        result={
            "playerState":  "idle",
            "objectId":     obj["id"],
            "currentUsers": obj["currentUsers"],
            "maxUsers":     obj["maxUsers"],
        },
    )


_HANDLERS = {
    "move":     handle_move,
    "turn":     handle_turn,
    "interact": handle_interact,
    "use":      handle_use,
    "leave":    handle_leave,
}


@router.post("/action", response_model=ActionResponse)
def dispatch(body: ActionRequest):
    handler = _HANDLERS.get(body.action.type)
    if handler is None:
        raise HTTPException(status_code=400, detail=f"unknown action type: {body.action.type}")
    result = handler(body.entityId, body.action.payload)
    if not body.skipLog:
        append_log(
            entity_id=body.entityId,
            action_type=body.action.type,
            payload=body.action.payload,
            success=result.success,
            reason=result.reason,
            label=body.logLabel,
        )
    return result
