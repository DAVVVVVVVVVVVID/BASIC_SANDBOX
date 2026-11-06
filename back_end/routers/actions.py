import asyncio
from collections import deque
from fastapi import APIRouter, HTTPException
from models.action import ActionRequest, ActionResponse
from models.world import Position
from game.world_state import (
    get_player, is_tile_walkable, update_player_position, update_player_facing,
    get_object_at, enter_object, leave_object, apply_instant_object,
    get_walkable_tiles_in_area, object_cooldown_remaining, record_object_use,
    set_phone_feed, _players,
)
from game import external_effects
from game.time_state import game_now_iso
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


def _bfs_path_to_any(start_x: int, start_y: int, goals: set[tuple[int, int]]) -> list[tuple[int, int]] | None:
    """BFS 到 goals 中最近的一格，返回路径（不含起点，含终点）；已在 goals 内返回 []；不可达返回 None。"""
    if (start_x, start_y) in goals:
        return []
    queue: deque = deque([(start_x, start_y)])
    parent: dict[tuple[int, int], tuple[int, int] | None] = {(start_x, start_y): None}
    while queue:
        x, y = queue.popleft()
        for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
            n = (x + dx, y + dy)
            if n in parent or not is_tile_walkable(*n):
                continue
            parent[n] = (x, y)
            if n in goals:
                path = [n]
                while parent[path[-1]] != (start_x, start_y):
                    path.append(parent[path[-1]])
                return list(reversed(path))
            queue.append(n)
    return None


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

    # B5：同一物品 30 游戏分钟冷却
    remaining = object_cooldown_remaining(entity_id, obj["id"])
    if remaining > 0:
        return ActionResponse(
            success=False,
            type="use",
            reason="object_cooldown",
            result={"message": obj.get("failureMessage"), "objectId": obj["id"],
                    "cooldownRemaining": round(remaining, 1)},
        )

    ext = external_effects.external_keys(obj)

    if obj.get("prototype") == "instant":
        apply_instant_object(obj["id"], entity_id)
        record_object_use(entity_id, obj["id"])            # B10：没信号也算用过（有冷却）
        result = {"message": obj.get("successMessage"), "objectId": obj["id"]}
        if "feed" in ext:                                   # B10 手机：拉自我层信息流摘要
            digest = external_effects.fetch_feed(_players.get(entity_id, player), game_now_iso())
            set_phone_feed(entity_id, digest)
            text = external_effects.feed_text(digest)
            result["message"] = text
            result["phone"] = digest
            if digest["status"] != "ok":
                return ActionResponse(success=False, type="use", reason="feed_unavailable", result=result)
        return ActionResponse(success=True, type="use", result=result)

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

    if "live" in ext:                                       # B11 直播台：先开播，失败就不坐下
        live = external_effects.live_start(_players.get(entity_id, player), game_now_iso())
        if not live["ok"]:
            return ActionResponse(
                success=False, type="use", reason="live_unavailable",
                result={"message": obj.get("failureMessage"), "objectId": obj["id"], "error": live.get("error")},
            )

    enter_object(obj["id"], entity_id)
    record_object_use(entity_id, obj["id"])
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
    # §3.14：按 BFS 实际路程取最近的可达格（跨 sector 走门），而不是曼哈顿最近（可能隔着墙）
    path = _bfs_path_to_any(pos["x"], pos["y"], {(t["x"], t["y"]) for t in walkable})
    if path is None:
        return ActionResponse(success=False, type="move_to_area", reason="no_path")
    goal_x, goal_y = path[-1] if path else (pos["x"], pos["y"])

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

    if body.action.type == "move" and result.success:
        await asyncio.sleep(_get_move_interval(body.entityId))

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
