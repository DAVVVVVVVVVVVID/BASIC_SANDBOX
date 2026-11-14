import asyncio
from collections import deque
from fastapi import APIRouter, HTTPException
from models.action import ActionRequest, ActionResponse
from models.world import Position
from game.world_state import (
    get_player, is_tile_walkable, update_player_position, update_player_facing,
    get_object_at, enter_object, leave_object, apply_instant_object,
    get_walkable_tiles_in_area, object_cooldown_remaining, record_object_use,
    set_phone_feed, open_state, _players,
)
from game import external_effects, external_log
from routers import economy_actions
from game.time_state import game_now_iso, game_now_ts
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


def _bfs_path(start_x: int, start_y: int, goal_x: int, goal_y: int, mover: dict | None = None) -> list[tuple[int, int]]:
    """BFS 求从 start 到 goal 的路径（走 edges，含楼梯；锁门不穿），返回途径坐标列表（不含起点，含终点）。"""
    from game.world_state import bfs_path
    return bfs_path((start_x, start_y), {(goal_x, goal_y)}, mover) or []


def _bfs_path_to_any(start_x: int, start_y: int, goals: set[tuple[int, int]], mover: dict | None = None) -> list[tuple[int, int]] | None:
    """BFS 到 goals 中最近的一格（走 edges）；已在 goals 内返回 []；不可达返回 None。"""
    from game.world_state import bfs_path
    return bfs_path((start_x, start_y), goals, mover)


def _blocked_reason(start: tuple[int, int], goals: set[tuple[int, int]], mover: dict | None):
    """不可达时区分 locked / closed（忽略锁能到）与 no_path。返回 (reason, opens_at)。"""
    from game.world_state import bfs_path, first_block_on_path
    p2 = bfs_path(start, goals, mover, ignore_locks=True)
    if p2 is None:
        return "no_path", None
    blk = first_block_on_path(start, p2, mover)
    if blk is None:
        return "no_path", None
    return blk


def _compute_facing(current: dict, target_x: int, target_y: int) -> str:
    dx = target_x - current["x"]
    dy = target_y - current["y"]
    if abs(dy) >= abs(dx):
        return "up" if dy < 0 else "down"
    return "left" if dx < 0 else "right"


def _blocked_detail(start: tuple[int, int], goals: set[tuple[int, int]], mover: dict | None) -> dict:
    """§3.36：no_path 时给首个阻塞原因与位置（忽略锁能到 → locked / closed + 格；否则纯 no_path）。"""
    from game.world_state import bfs_path, crossing_block, edge_block, arena_cross_block, game_now_ts, _STAIRS
    p2 = bfs_path(start, goals, mover, ignore_locks=True)
    if p2 is None:
        return {"blocked_reason": "no_path", "blocked_at": None, "opens_at": None}
    ts = game_now_ts(); prev = start
    for n in p2:
        blk = crossing_block(prev, n, mover, ts)
        if blk is None and abs(prev[0] - n[0]) + abs(prev[1] - n[1]) != 1:
            for m, e in _STAIRS.get(prev, []):
                if m == n:
                    blk = edge_block(e, mover, ts, frm=prev) or arena_cross_block(prev, n, mover, ts)
        if blk is not None:
            return {"blocked_reason": blk[0], "blocked_at": {"x": n[0], "y": n[1]}, "opens_at": blk[1]}
        prev = n
    return {"blocked_reason": "no_path", "blocked_at": None, "opens_at": None}


def _no_path(action_type: str, start: tuple[int, int], goals: set[tuple[int, int]], mover: dict | None, extra: dict | None = None) -> ActionResponse:
    d = _blocked_detail(start, goals, mover)
    return ActionResponse(success=False, type=action_type, reason="no_path", result={**d, **(extra or {})})


def _begin_walk(entity_id: str, action_type: str, path: list[tuple[int, int]], target: dict | None, extra: dict | None = None) -> ActionResponse:
    """§3.36：路径入队，立即返回 {state:"walking", path_len, eta_game_s, position}。空路径 = 已在目标。"""
    from game.world_state import start_walk, STATE_LOCK
    with STATE_LOCK:
        p = _players[entity_id]
        if path:
            update_player_facing(entity_id, _compute_facing(p["position"], path[0][0], path[0][1]))
        info = start_walk(entity_id, path, action_type, target)
        pos = dict(p["position"]); facing = p["facing"]
    return ActionResponse(success=True, type=action_type, result={
        "state": "walking" if path else "idle", "path_len": info["path_len"], "eta_game_s": info["eta_game_s"],
        "position": pos, "facing": facing, "target": target, **(extra or {})})


def _walking_guard(entity_id: str, action_type: str) -> ActionResponse | None:
    from game.world_state import _walks
    if entity_id in _walks:
        return ActionResponse(success=False, type=action_type, reason="walking",
                              result={"message": "还在走路，等到了再说。", **(get_player(entity_id) or {}).get("walk", {})})
    return None


def handle_move(entity_id: str, payload: dict) -> ActionResponse:
    player = get_player(entity_id)
    if player is None:
        return ActionResponse(success=False, type="move", reason="player_not_found")
    if not player.get("canMove", True):
        return ActionResponse(success=False, type="move", reason="move_disabled")
    current = player["position"]
    direction = payload.get("direction")
    target_tile = payload.get("targetTile")
    from game.world_state import crossing_block, game_now_ts, _players as _pl, stop_walk, STATE_LOCK

    if direction is not None:
        if direction not in _DIRECTION_DELTA:
            return ActionResponse(success=False, type="move", reason="invalid_direction")
        dx, dy = _DIRECTION_DELTA[direction]
        new_x, new_y = current["x"] + dx, current["y"] + dy
        facing = direction
    elif target_tile is not None:
        new_x, new_y = int(target_tile["x"]), int(target_tile["y"])
        facing = _compute_facing(current, new_x, new_y)
    else:
        return ActionResponse(success=False, type="move", reason="missing_direction_or_target")

    update_player_facing(entity_id, facing)
    if not is_tile_walkable(new_x, new_y):
        return ActionResponse(success=False, type="move", reason="tile_not_walkable", result={"facing": facing})

    if direction is not None and player.get("controller", "human") == "human":
        # §3.36：人类控制者单格 direction 免排队（键盘手感）；仍查门锁
        blk = crossing_block((current["x"], current["y"]), (new_x, new_y), _pl.get(entity_id), game_now_ts())
        if blk is not None:
            return ActionResponse(success=False, type="move", reason=blk[0], result={"facing": facing, "opens_at": blk[1]})
        with STATE_LOCK:
            stop_walk(entity_id, "stopped", "manual_move")
            update_player_position(entity_id, new_x, new_y, facing)
            from game import doors
            doors.on_cross(entity_id, (current["x"], current["y"]), (new_x, new_y), game_now_ts())
        return ActionResponse(success=True, type="move", result={"facing": facing, "position": {"x": new_x, "y": new_y}, "state": "idle"})

    # §3.36：其余一律先 BFS（逐边判锁与时段），有路入队按 1 格 / 游戏秒走，无路 no_path
    start = (current["x"], current["y"]); goal = (new_x, new_y)
    if start == goal:
        return ActionResponse(success=True, type="move", result={"facing": facing, "position": dict(current), "state": "idle", "path_len": 0, "eta_game_s": 0.0})
    path = _bfs_path_to_any(start[0], start[1], {goal}, _pl.get(entity_id))
    if path is None:
        return _no_path("move", start, {goal}, _pl.get(entity_id), {"facing": facing, "target": {"x": new_x, "y": new_y}})
    return _begin_walk(entity_id, "move", path, {"x": new_x, "y": new_y})


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
    g = _walking_guard(entity_id, "interact")                     # §3.36
    if g:
        return g
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
    g = _walking_guard(entity_id, "use")                          # §3.36
    if g:
        return g
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

    # B20：营业时间
    is_open, opens_at = open_state(obj)
    if not is_open:
        return ActionResponse(
            success=False, type="use", reason="closed",
            result={"message": f"{obj['name']}还没开门，{opens_at} 开。", "objectId": obj["id"], "opens_at": opens_at,
                    "openHours": obj.get("openHours")},
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

    from game.world_state import daily_limit_check
    dl = daily_limit_check(entity_id, obj)                     # world-v1.1 I-1：今天用够了
    if dl:
        return ActionResponse(success=False, type="use", reason="daily_limit",
                              result={"message": f"今天{obj['name']}用够了，{dl['resets_at']} 后再来。", "objectId": obj["id"], **dl})

    if obj.get("prototype") == "instant":
        if obj.get("contents") is not None:                                     # world-v1.1：冰箱是储物柜，use 只回内容与提示（无效果、无冷却）
            from game import food as _food
            cv = _food.contents_view(obj, game_now_ts())
            msg = ("冰箱空了，去杂货店买点食材吧。" if not cv else "冰箱里有：" + "、".join(f"{c['name']}×{c['count']}" for c in cv) + "。take 拿出来，到餐桌 eat。")
            return ActionResponse(success=True, type="use",
                                  result={"message": msg, "objectId": obj["id"], "contents": cv, "storage": {"capacity": _food.capacity(obj), "used": _food.used(obj)},
                                          "stock": dict(obj.get("stock") or {}), "empty": not cv})
        apply_instant_object(obj["id"], entity_id)
        record_object_use(entity_id, obj["id"])            # B10：没信号也算用过（有冷却）
        result = {"message": obj.get("successMessage"), "objectId": obj["id"]}
        if obj.get("stock") is not None:
            result["stock"] = dict(obj["stock"])
        if obj["type"] == "notice_board":                                        # W11 ①：公告栏读到委托
            from game import commissions
            result["commissions"] = commissions.open_items()
            if result["commissions"]:
                result["message"] = (result["message"] or "") + " 公告栏上有委托：" + "；".join(f"{c['client_name']}《{c['title']}》{c['fee']} 金币" for c in result["commissions"])
        if "feed" in ext:                                   # B10 手机：拉自我层信息流摘要
            digest = external_effects.fetch_feed(_players.get(entity_id, player), game_now_iso())
            set_phone_feed(entity_id, digest)
            external_log.log("feed", entity_id, object=obj["id"], status=digest["status"], items=len(digest.get("items") or []))
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
                "message":      f"{_FULL_NAME_CN.get(obj['name'], obj['name'])}有人在用（已满 {obj['currentUsers']}/{obj['maxUsers']}）。",   # v1.2.6：不再借用类型通用失败语（床的是「还不是睡觉的时候」，满员时误导）
                "currentUsers": obj["currentUsers"],
                "maxUsers":     obj["maxUsers"],
            },
        )

    # world-v1.1：餐厅坐下免费，点一顿在 eat {item:"meal"} 时扣钱（§1.1）

    if "live" in ext:                                       # B11 直播台：先开播，失败就不坐下
        live = external_effects.live_start(_players.get(entity_id, player), game_now_iso())
        external_log.log("live", entity_id, object=obj["id"], action="start", ok=live["ok"], error=live.get("error"))
        if not live["ok"]:
            return ActionResponse(
                success=False, type="use", reason="live_unavailable",
                result={"message": obj.get("failureMessage"), "objectId": obj["id"], "error": live.get("error")},
            )

    if "game" in ext:                                       # B18 / W10-4b 游戏机：energy ≥ 中才坐下；问 D 开局 / 接局，失败就不坐下
        if float(player.get("energy", 100.0)) < external_effects.GAME_ENERGY_MIN:
            return ActionResponse(success=False, type="use", reason="too_tired",
                                  result={"message": "太累了，先休息再玩。", "objectId": obj["id"], "energy_min": external_effects.GAME_ENERGY_MIN})
        g = external_effects.game_start(_players.get(entity_id, player), game_now_iso())
        external_log.log("game", entity_id, object=obj["id"], action="start", ok=g["ok"], error=g.get("error"), game=g.get("game"))
        if not g["ok"]:
            return ActionResponse(
                success=False, type="use", reason="game_unavailable",
                result={"message": obj.get("failureMessage"), "objectId": obj["id"], "error": g.get("error")},
            )
        _players[entity_id]["game"] = g["game"]

    from game import production as _prod
    pl = _players.get(entity_id, player)
    perr = _prod.on_enter(pl, obj, game_now_ts(), payload)     # W11 ① / v1.1：灶台按份扣食材并计时、钓位开始计时
    if perr:
        extra = pl.pop("_use_err", None) or {}
        msg = {"no_ingredients": "食材不够，先去杂货店买点。", "not_cookable": "这个不能下锅。"}.get(perr, obj.get("failureMessage"))
        return ActionResponse(success=False, type="use", reason=perr, result={"message": msg, "objectId": obj["id"], **extra})
    enter_object(obj["id"], entity_id)
    record_object_use(entity_id, obj["id"])
    updated = get_player(entity_id)
    result = {
        "message":      obj.get("successMessage"),
        "playerState":  updated["state"] if updated else "using",
        "stateLabel":   updated["stateLabel"] if updated else None,
        "objectId":     obj["id"],
        "currentUsers": obj["currentUsers"],
        "maxUsers":     obj["maxUsers"],
    }
    if obj["type"] == "stove":
        result["cooking"] = _prod.cooking_view(obj["id"], game_now_ts())
        if result["cooking"]:
            result["message"] = f"开火做 {result['cooking']['portions']} 份，{result['cooking']['ready_in_min']:.0f} 分钟后好。中途走就白费了。"
    if "feed" in ext:                                           # world-v1.1：手机改持续使用，进入时拉一次 feed 摘要
        digest = external_effects.fetch_feed(pl, game_now_iso())
        set_phone_feed(entity_id, digest)
        external_log.log("feed", entity_id, object=obj["id"], status=digest["status"], items=len(digest.get("items") or []))
        result["phone"] = digest
        result["message"] = external_effects.feed_text(digest) if digest["status"] == "ok" else result["message"]
    return ActionResponse(success=True, type="use", result=result)


def handle_leave(entity_id: str, payload: dict) -> ActionResponse:
    """
    Q0（W8）：离开正在使用的物品**永远放行**。no_use / no_move / chat_active 只约束去用别的物品或移动，
    否则「钓位 no_move + 对话 chat_active」会把人锁死（11-06 鲸仔卡在 fishing_spot_2 近两小时）。
    """
    if entity_id not in _players:
        return ActionResponse(success=False, type="leave", reason="player_not_found")
    from game.world_state import stop_walk, STATE_LOCK, _walks
    if entity_id in _walks and not _players[entity_id].get("usingObjectId"):          # §3.36：走路中 leave = 就地停下
        with STATE_LOCK:
            row = stop_walk(entity_id, "stopped", "leave")
        p = _players[entity_id]
        return ActionResponse(success=True, type="leave", result={"message": "停下了。", "stopped_walk": row, "position": dict(p["position"]),
                                                                  "playerState": p["state"], "canMove": p.get("canMove", True), "canUse": p.get("canUse", True)})
    obj = leave_object(entity_id)
    if obj is None:
        return ActionResponse(success=False, type="leave", reason="not_using_any_object")

    p = _players.get(entity_id) or {}
    return ActionResponse(
        success=True,
        type="leave",
        result={
            "playerState":  "idle",
            "stateLabel":   None,
            "objectId":     obj["id"],
            "currentUsers": obj["currentUsers"],
            "maxUsers":     obj["maxUsers"],
            "canMove":      p.get("canMove", True),      # Q0c：离开后立刻可动（无其他 no_move 来源时为 true）
            "canUse":       p.get("canUse", True),
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
    # §3.36：沿直线找最远能到的格（可走 + 此刻能穿），然后入队走过去
    from game.world_state import crossing_block, game_now_ts
    x, y = player["position"]["x"], player["position"]["y"]
    path: list[tuple[int, int]] = []
    for _ in range(steps):
        nx, ny = x + dx, y + dy
        if not is_tile_walkable(nx, ny) or crossing_block((x, y), (nx, ny), _players.get(entity_id), game_now_ts()) is not None:
            break
        x, y = nx, ny
        path.append((x, y))
    if not path:
        return ActionResponse(success=False, type="move_n", reason="tile_not_walkable", result={"facing": direction, "position": dict(player["position"]), "steps_taken": 0})
    return _begin_walk(entity_id, "move_n", path, {"x": x, "y": y}, {"steps_planned": len(path), "steps_taken": 0})


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
    mover  = _players.get(entity_id)
    # §3.14：按 BFS 实际路程取最近的可达格（跨 sector 走门 / 楼梯），而不是曼哈顿最近（可能隔着墙）
    goals = {(t["x"], t["y"]) for t in walkable}
    path = _bfs_path_to_any(pos["x"], pos["y"], goals, mover)
    if path is None:                                              # §3.36：no_path + 首个阻塞（locked / closed 带 opens_at 与格）
        return _no_path("move_to_area", (pos["x"], pos["y"]), goals, mover, {"area_type": area_type, "area_id": area_id})
    goal_x, goal_y = path[-1] if path else (pos["x"], pos["y"])
    return _begin_walk(entity_id, "move_to_area", path, {"x": goal_x, "y": goal_y, "area_type": area_type, "area_id": area_id},
                       {"area_type": area_type, "area_id": area_id})


# ── B12 freeform ─────────────────────────────────────────────────────────────
FREEFORM_COOLDOWN_S = 30.0          # 每实体 30 s 一次（墙钟；自我层那边另有一层）
FREEFORM_MAX_TEXT = 200
_last_freeform: dict[str, float] = {}


def handle_freeform(entity_id: str, payload: dict) -> ActionResponse:
    """
    自然语言动作：payload {text, target?: entity_id | object_id, context?}
    → 自我层 POST /self/adjudicate 裁决 → effects 经 apply_effects 落到本人（target=self）或对方 player（target=entity_id），
    narration 进双方 pendingMessage。reason 透传：injection / rate_limited / adjudication_unavailable / adjudication_failed。
    """
    import time as _time
    from game.world_state import _players, _pending_messages, STATE_LOCK, apply_effects
    player = _players.get(entity_id)
    if player is None:
        return ActionResponse(success=False, type="freeform", reason="player_not_found")
    text = str(payload.get("text") or "").strip()
    if not text:
        return ActionResponse(success=False, type="freeform", reason="missing_text")
    if len(text) > FREEFORM_MAX_TEXT:
        return ActionResponse(success=False, type="freeform", reason="text_too_long",
                              result={"max": FREEFORM_MAX_TEXT})
    now = _time.time()
    last = _last_freeform.get(entity_id)
    if last is not None and now - last < FREEFORM_COOLDOWN_S:
        return ActionResponse(success=False, type="freeform", reason="rate_limited",
                              result={"retry_after": round(FREEFORM_COOLDOWN_S - (now - last), 1)})
    _last_freeform[entity_id] = now

    target = payload.get("target")
    res = external_effects.adjudicate(player, text, target, payload.get("context"))
    narration = str(res.get("narration") or "")
    effects = res.get("effects") or []
    external_log.log("adjudication", entity_id, text=text, target=target, success=bool(res.get("success")),
                     reason=res.get("reason"), effects=effects, narration=narration)
    applied_self = applied_target = 0
    skipped = int(res.get("skipped") or 0)
    if res.get("success") or effects:
        with STATE_LOCK:
            mine = [e for e in effects if (e.get("target") in (None, "", "self", entity_id))]
            others = [e for e in effects if e.get("target") not in (None, "", "self", entity_id)]
            applied_self = apply_effects(player, mine, source="freeform")["applied"]
            for e in others:
                tp = _players.get(e["target"])
                if tp is None:
                    skipped += 1
                    continue
                applied_target += apply_effects(tp, [e], source="freeform")["applied"]
                _pending_messages[e["target"]] = narration or None
    if narration:
        _pending_messages[entity_id] = narration
        if target in _players and target != entity_id:
            _pending_messages[target] = narration

    result = {
        "narration": narration, "effects": effects, "applied": applied_self + applied_target, "skipped": skipped,
        "feasible": res.get("feasible"), "injection": bool(res.get("injection", False)),
    }
    for k in ("retry_after", "error"):
        if k in res:
            result[k] = res[k]
    reason = res.get("reason")
    return ActionResponse(success=bool(res.get("success")), type="freeform", reason=reason, result=result)


async def handle_go_to(entity_id: str, payload: dict) -> ActionResponse:
    """W9：`go_to` = move_to_area 的别名，payload {area_id | target, area_type?="arena"}。"""
    area_id = payload.get("area_id") or payload.get("target")
    res = await handle_move_to_area(entity_id, {"area_type": payload.get("area_type", "arena"), "area_id": area_id})
    return ActionResponse(success=res.success, type="go_to", reason=res.reason, result=res.result)


def handle_say(entity_id: str, payload: dict) -> ActionResponse:
    """Q6：曼哈顿 ≤ 2 格、同 sector 的在场玩家下一次 perceive 的 nearby_speech 里看到；不开房间。"""
    from game import speech
    from game.world_state import STATE_LOCK
    with STATE_LOCK:
        res, reason = speech.say(entity_id, str(payload.get("text") or ""))
    if reason:
        return ActionResponse(success=False, type="say", reason=reason)
    return ActionResponse(success=True, type="say", result=res)


def handle_open_door(entity_id: str, payload: dict) -> ActionResponse:
    """§3.41：站在门内侧相邻格的人开门（不需钥匙），敞开 60 游戏秒后自动落锁。"""
    from game import doors
    from game.world_state import STATE_LOCK
    g = _walking_guard(entity_id, "open_door")
    if g:
        return g
    with STATE_LOCK:
        info, reason, detail = doors.open_door(entity_id, payload.get("door_id") or payload.get("door") or "")
    if reason:
        return ActionResponse(success=False, type="open_door", reason=reason, result=detail)
    return ActionResponse(success=True, type="open_door", result={"message": f"把{info['name']}打开了。", **info})


def handle_knock(entity_id: str, payload: dict) -> ActionResponse:
    """§3.40：访客在上锁家门外敲门 {door_id | target_tile | home}。"""
    from game import doors
    from game.world_state import STATE_LOCK
    g = _walking_guard(entity_id, "knock")
    if g:
        return g
    with STATE_LOCK:
        req, reason, detail = doors.knock(entity_id, payload)
    if reason:
        return ActionResponse(success=False, type="knock", reason=reason, result=detail)
    return ActionResponse(success=True, type="knock", result={"message": "咚咚咚。", "request": req, "request_id": req["id"],
                                                             "expires_at": req["expires_at"], "door": req["door"], "home": req["home"], "notified": req["notified"]})


_HANDLERS = {
    "move":         handle_move,
    "move_n":       handle_move_n,
    "move_to_area": handle_move_to_area,
    "turn":         handle_turn,
    "interact":     handle_interact,
    "use":          handle_use,
    "leave":        handle_leave,
    "freeform":     handle_freeform,
    "go_to":        handle_go_to,
    # W10 ④ 金币与背包
    "buy":          economy_actions.handle_buy,
    "sell":         economy_actions.handle_sell,
    "eat":          economy_actions.handle_eat,
    "give":         economy_actions.handle_give,
    # W11 ①④
    "store":        economy_actions.handle_store,
    "take":         economy_actions.handle_take,
    "discard":      economy_actions.handle_discard,
    "copy_key":     economy_actions.handle_copy_key,
    "deliver":      economy_actions.handle_deliver,
    "burn_cd":      economy_actions.handle_burn_cd,
    "knock":        handle_knock,                 # §3.40
    "open_door":    handle_open_door,             # §3.41
    "say":          handle_say,                   # Q6 靠近即可说
    "compose":      economy_actions.handle_compose,
    "make_video":   economy_actions.handle_make_video,
}


# v1.2.6：满员提示用的中文名——几个老类型的 object_types name 还是英文（/world 输出的 name 不动，只在这句提示里换）
_FULL_NAME_CN = {"bed": "床", "bath": "浴缸", "fridge": "冰箱", "desk": "书桌", "book": "书架"}

@router.post("/action", response_model=ActionResponse)
async def dispatch(body: ActionRequest):
    handler = _HANDLERS.get(body.action.type)
    if handler is None:
        raise HTTPException(status_code=400, detail=f"unknown action type: {body.action.type}")
    from game.world_state import mark_input, takeover_on_action
    mark_input(body.entityId)                                   # W8 Q0e：任何动作都是输入
    takeover_on_action(body.entityId)                           # v1.3.4 ②：主播客户端的第一个动作 → 关 dnd（心跳不算）

    if asyncio.iscoroutinefunction(handler):
        result = await handler(body.entityId, body.action.payload)
    else:
        result = handler(body.entityId, body.action.payload)

    if body.action.type == "move" and result.success and (result.result or {}).get("state") == "idle" and (result.result or {}).get("path_len") is None:
        await asyncio.sleep(_get_move_interval(body.entityId))      # 人类单格移动的节拍；排队走路的请求立即返回

    # E⑦：/ws/world 的 action 事件（给前端一次性动画）
    try:
        from routers.ws import hub
        res = result.result or {}
        extra = {}
        if res.get("position"):
            extra["position"] = res.get("position")
        if res.get("objectId"):
            from game.world_state import get_object_by_id
            o = get_object_by_id(res["objectId"])
            extra["object_type"] = o["type"] if o else None               # E：前端不必再按 id 查
        for k in ("item", "item_name", "qty", "price", "gold_delta", "gold", "target", "target_name", "state", "path_len", "eta_game_s", "blocked_reason", "blocked_at"):   # W10 ④ / §3.36
            if k in res:
                extra[k] = res[k]
        hub.push_action(body.entityId, body.action.type, result.success, obj=res.get("objectId"), reason=result.reason, extra=extra or None)
        from game import interventions
        if body.action.type in ("knock", "open_door", "give") and interventions.is_streamer(_players.get(body.entityId)):   # 闭测 §5.2
            what = {"knock": "敲门", "open_door": "开门", "give": "给物"}[body.action.type]
            tg = [x for x in [res.get("target"), *(res.get("owners") or [])] if isinstance(x, str)] or ["*"]
            interventions.achan_knock(_players[body.entityId], what, tg, action=body.action.type, success=result.success, reason=result.reason,
                                      door=(res.get("door") or {}).get("id") if isinstance(res.get("door"), dict) else res.get("door_id"), home=res.get("home"), item=res.get("item"))
    except Exception:
        pass

    if not body.skipLog and not (body.action.type in ("knock", "open_door") and result.success):   # §3.40/41：成功时 doors 模块已写一行
        append_log(
            entity_id=body.entityId,
            action_type=body.action.type,
            payload=body.action.payload,
            success=result.success,
            reason=result.reason,
            label=body.logLabel,
            object_id=(result.result or {}).get("objectId"),
        )
    return result
