import asyncio
from collections import deque
from fastapi import APIRouter, HTTPException
from models.action import ActionRequest, ActionResponse
from models.world import Position
from game.world_state import (
    get_player, is_tile_walkable, update_player_position, update_player_facing,
    get_object_at, enter_object, leave_object, apply_instant_object,
    get_walkable_tiles_in_area,
)
from game.action_log import append_log

BASE_MOVE_INTERVAL = 0.3  # 秒，与前端 BASE_MOVE_INTERVAL=300ms 对齐

router = APIRouter()

_DIRECTION_DELTA = {
    "up":    (0, -1),
    "down":  (0,  1),
    "left":  (-1, 0),
    "right": (1,  0),
}


def _get_move_interval(entity_id: str) -> float:
    player = get_player(entity_id)
    speed = player["moveSpeed"] if player else 1.0
    return BASE_MOVE_INTERVAL / max(0.1, speed)


def _bfs_path(start_x: int, start_y: int, goal_x: int, goal_y: int) -> list[tuple[int, int]]:
    """BFS 求从 start 到 goal 的路径，返回途径坐标列表（不含起点，含终点）。"""
    if start_x == goal_x and start_y == goal_y:
        return []
    queue: deque = deque([(start_x, start_y, [])])
    visited = {(start_x, start_y)}
    while queue:
        x, y, path = queue.popleft()
        for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
            nx, ny = x + dx, y + dy
            if (nx, ny) in visited:
                continue
            new_path = path + [(nx, ny)]
            if nx == goal_x and ny == goal_y:
                return new_path
            if is_tile_walkable(nx, ny):
                visited.add((nx, ny))
                queue.append((nx, ny, new_path))
    return []


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
    player = get_player(entity_id)
    if player and any(b["key"] == "chat_active" for b in player.get("buffs", [])):
        return ActionResponse(success=False, type="leave", reason="use_disabled")
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


async def handle_move_n(entity_id: str, payload: dict) -> ActionResponse:
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

    interval = _get_move_interval(entity_id)
    x, y = player["position"]["x"], player["position"]["y"]
    steps_taken = 0
    for _ in range(steps):
        nx, ny = x + dx, y + dy
        if not is_tile_walkable(nx, ny):
            break
        x, y = nx, ny
        steps_taken += 1
        update_player_position(entity_id, x, y, direction)
        await asyncio.sleep(interval)

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


async def handle_move_to_area(entity_id: str, payload: dict) -> ActionResponse:
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

    pos    = player["position"]
    target = min(walkable, key=lambda t: abs(t["x"] - pos["x"]) + abs(t["y"] - pos["y"]))
    goal_x, goal_y = target["x"], target["y"]

    path = _bfs_path(pos["x"], pos["y"], goal_x, goal_y)
    if not path and (pos["x"] != goal_x or pos["y"] != goal_y):
        return ActionResponse(success=False, type="move_to_area", reason="no_path")

    interval = _get_move_interval(entity_id)
    prev_x, prev_y = pos["x"], pos["y"]
    facing = _compute_facing(pos, goal_x, goal_y)
    for step_x, step_y in path:
        facing = _compute_facing({"x": prev_x, "y": prev_y}, step_x, step_y)
        update_player_position(entity_id, step_x, step_y, facing)
        prev_x, prev_y = step_x, step_y
        await asyncio.sleep(interval)

    return ActionResponse(
        success=True,
        type="move_to_area",
        result={
            "facing":    facing,
            "position":  {"x": goal_x, "y": goal_y},
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
async def dispatch(body: ActionRequest):
    handler = _HANDLERS.get(body.action.type)
    if handler is None:
        raise HTTPException(status_code=400, detail=f"unknown action type: {body.action.type}")

    if asyncio.iscoroutinefunction(handler):
        result = await handler(body.entityId, body.action.payload)
    else:
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
