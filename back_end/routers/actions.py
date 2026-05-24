from fastapi import APIRouter, HTTPException
from models.action import ActionRequest, ActionResponse
from models.world import Position
import random
from game.world_state import (
    get_player, is_tile_walkable, update_player_position, update_player_facing,
    get_object_at, enter_object, leave_object, apply_instant_object,
    get_walkable_tiles_in_area,
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
    player = get_player(entity_id)
    if player is None:
        return ActionResponse(success=False, type="move", reason="player_not_found")
    if not player.get("canMove", True):
        return ActionResponse(success=False, type="move", reason="move_disabled")
    current = player["position"]
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

    update_player_facing(entity_id, facing)

    if not is_tile_walkable(new_x, new_y):
        return ActionResponse(
            success=False,
            type="move",
            reason="tile_not_walkable",
            result={"facing": facing},
        )

    update_player_position(entity_id, new_x, new_y, facing)
    return ActionResponse(
        success=True,
        type="move",
        result={"facing": facing, "position": {"x": new_x, "y": new_y}, "state": "idle"},
    )


def handle_turn(entity_id: str, payload: dict) -> ActionResponse:
    direction = payload.get("direction")
    if direction not in _DIRECTION_DELTA:
        return ActionResponse(success=False, type="turn", reason="invalid_direction")
    update_player_facing(entity_id, direction)
    return ActionResponse(success=True, type="turn", result={"facing": direction})


def handle_interact(entity_id: str, payload: dict) -> ActionResponse:
    player = get_player(entity_id)
    if player is None:
        return ActionResponse(success=False, type="interact", reason="player_not_found")
    if not player.get("canInteract", True):
        return ActionResponse(success=False, type="interact", reason="interact_disabled")
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
    player = get_player(entity_id)
    if player is None:
        return ActionResponse(success=False, type="use", reason="player_not_found")
    if not player.get("canUse", True):
        return ActionResponse(success=False, type="use", reason="use_disabled")
    pos    = player["position"]
    dx, dy = _DIRECTION_DELTA[player["facing"]]

    obj = get_object_at(pos["x"] + dx, pos["y"] + dy)
    if obj is None:
        return ActionResponse(success=False, type="use", reason="no_object_in_front")

    if not obj.get("interactable", False):
        return ActionResponse(
            success=False,
            type="use",
            reason="not_interactable",
            result={"message": obj.get("failureMessage")},
        )

    if obj.get("prototype") == "instant":
        apply_instant_object(obj["id"], entity_id)
        return ActionResponse(
            success=True,
            type="use",
            result={
                "message":  obj.get("successMessage"),
                "objectId": obj["id"],
            },
        )

    # continuous
    if obj["currentUsers"] >= obj["maxUsers"]:
        return ActionResponse(
            success=False,
            type="use",
            reason="object_full",
            result={
                "message":      obj.get("failureMessage"),
                "currentUsers": obj["currentUsers"],
                "maxUsers":     obj["maxUsers"],
            },
        )

    enter_object(obj["id"], entity_id)
    updated = get_player(entity_id)
    return ActionResponse(
        success=True,
        type="use",
        result={
            "message":      obj.get("successMessage"),
            "playerState":  updated["state"] if updated else "using",
            "stateLabel":   updated["stateLabel"] if updated else None,
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
            "stateLabel":   None,
            "objectId":     obj["id"],
            "currentUsers": obj["currentUsers"],
            "maxUsers":     obj["maxUsers"],
        },
    )


def handle_move_n(entity_id: str, payload: dict) -> ActionResponse:
    player = get_player(entity_id)
    if player is None:
        return ActionResponse(success=False, type="move_n", reason="player_not_found")
    if not player.get("canMove", True):
        return ActionResponse(success=False, type="move_n", reason="move_disabled")

    direction = payload.get("direction")
    steps = payload.get("steps", 1)

    if direction not in _DIRECTION_DELTA:
        return ActionResponse(success=False, type="move_n", reason="invalid_direction")
    if not isinstance(steps, int) or steps < 1:
        return ActionResponse(success=False, type="move_n", reason="invalid_steps")

    dx, dy = _DIRECTION_DELTA[direction]
    update_player_facing(entity_id, direction)

    x, y = player["position"]["x"], player["position"]["y"]
    steps_taken = 0
    for _ in range(steps):
        nx, ny = x + dx, y + dy
        if not is_tile_walkable(nx, ny):
            break
        x, y = nx, ny
        steps_taken += 1

    if steps_taken > 0:
        update_player_position(entity_id, x, y, direction)

    return ActionResponse(
        success=steps_taken > 0,
        type="move_n",
        reason=None if steps_taken > 0 else "tile_not_walkable",
        result={
            "facing": direction,
            "position": {"x": x, "y": y},
            "steps_taken": steps_taken,
        },
    )


def handle_move_to_area(entity_id: str, payload: dict) -> ActionResponse:
    player = get_player(entity_id)
    if player is None:
        return ActionResponse(success=False, type="move_to_area", reason="player_not_found")
    if not player.get("canMove", True):
        return ActionResponse(success=False, type="move_to_area", reason="move_disabled")

    area_type = payload.get("area_type")
    area_id   = payload.get("area_id")

    if area_type not in ("arena", "sector", "world"):
        return ActionResponse(success=False, type="move_to_area", reason="invalid_area_type")
    if not area_id:
        return ActionResponse(success=False, type="move_to_area", reason="missing_area_id")

    walkable = get_walkable_tiles_in_area(area_type, area_id)
    if not walkable:
        return ActionResponse(success=False, type="move_to_area", reason="no_walkable_tiles")

    target  = random.choice(walkable)
    new_x, new_y = target["x"], target["y"]
    facing  = _compute_facing(player["position"], new_x, new_y)

    update_player_position(entity_id, new_x, new_y, facing)
    return ActionResponse(
        success=True,
        type="move_to_area",
        result={
            "facing":    facing,
            "position":  {"x": new_x, "y": new_y},
            "area_type": area_type,
            "area_id":   area_id,
        },
    )


_HANDLERS = {
    "move":         handle_move,
    "move_n":       handle_move_n,
    "move_to_area": handle_move_to_area,
    "turn":         handle_turn,
    "interact":     handle_interact,
    "use":          handle_use,
    "leave":        handle_leave,
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
