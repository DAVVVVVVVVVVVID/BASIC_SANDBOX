from fastapi import APIRouter, HTTPException, Query
from game.world_state import (
    get_player,
    get_zone_at,
    get_tiles_in_square,
    get_objects_in_arena,
    get_cognitive_map,
    get_object_at,
    get_tiles_in_area,
    get_object_by_id,
    is_tile_walkable,
    get_recent_uses,
    get_phone_feed,
    _players,
)
from game.needs import needs_text, closeness_tier

router = APIRouter(prefix="/agent", tags=["agent"])

_DIRECTION_DELTA = {
    "up":    (0, -1),
    "down":  (0,  1),
    "left":  (-1, 0),
    "right": (1,  0),
}


def _find_in_cognitive_map(world_id: str | None, sector_id: str | None, arena_id: str | None) -> dict:
    """Look up human-readable names from the cognitive map."""
    result = {"world": None, "sector": None, "arena": None}
    if world_id is None:
        return result
    cmap = get_cognitive_map()
    for world in cmap.get("worlds", []):
        if world["id"] != world_id:
            continue
        result["world"] = {"id": world["id"], "name": world["name"]}
        if sector_id is None:
            return result
        for sector in world.get("sectors", []):
            if sector["id"] != sector_id:
                continue
            result["sector"] = {"id": sector["id"], "name": sector["name"]}
            if arena_id is None:
                return result
            for arena in sector.get("arenas", []):
                if arena["id"] != arena_id:
                    continue
                result["arena"] = {"id": arena["id"], "name": arena["name"]}
                return result
    return result


def _named(lookup_result, raw_id):
    """Use cognitive map name when available, fall back to raw ID."""
    if raw_id is None:
        return None
    if lookup_result:
        return lookup_result
    return {"id": raw_id, "name": raw_id}


@router.get("/perceive")
def perceive(
    entity_id: str = Query(default="player_01"),
    vision_size: int = Query(default=3, ge=1, le=21),
):
    # 偶数向上取奇，保证以自身为中心
    if vision_size % 2 == 0:
        vision_size += 1
    half = (vision_size - 1) // 2

    player = get_player(entity_id)
    if player is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"player not found: {entity_id}")
    pos = player["position"]
    facing = player["facing"]
    px, py = pos["x"], pos["y"]

    # ── 1. 整个 world 的语义树（§3.14：所有 sector → arenas → objects，current 标 sector 与 arena）──
    zone  = get_zone_at(px, py)
    names = _find_in_cognitive_map(zone["world"], zone["sector"], zone["arena"])
    cmap  = get_cognitive_map()

    from game.world_state import open_state
    def _obj_brief(o: dict) -> dict:
        is_open, opens_at = open_state(o)
        d = {"id": o["id"], "name": o["name"], "type": o["type"], "interactable": o["interactable"],
             "currentUsers": o["currentUsers"], "open": is_open, "opensAt": opens_at}
        if o.get("maxUsers") is not None:
            d["maxUsers"] = o["maxUsers"]
        if o.get("advertise"):
            d["advertise"] = o["advertise"] if is_open else {k: 0 for k in o["advertise"]}
        return d

    worlds_out: list[dict] = []
    current_sector_node = None
    for _w in cmap.get("worlds", []):
        sectors_out: list[dict] = []
        for _s in _w.get("sectors", []):
            arenas_out = []
            for am in _s.get("arenas", []):
                arenas_out.append({
                    "id":      am["id"],
                    "name":    am["name"],
                    "current": am["id"] == zone["arena"] and _s["id"] == zone["sector"],
                    "objects": [_obj_brief(o) for o in get_objects_in_arena(am["id"])],
                })
            node = {"id": _s["id"], "name": _s["name"], "current": _s["id"] == zone["sector"], "arenas": arenas_out}
            sectors_out.append(node)
            if node["current"]:
                current_sector_node = node
        worlds_out.append({"id": _w["id"], "name": _w["name"], "current": _w["id"] == zone["world"], "sectors": sectors_out})

    # 兼容旧形状：arena_tree = 所在 world 节点，带 sector（当前 sector）与 sectors（全部）
    my_world = next((w for w in worlds_out if w["current"]), worlds_out[0] if worlds_out else None)
    if my_world is not None:
        arena_tree = {**my_world, "sector": current_sector_node}
    else:
        arena_tree = None

    # ── 2. 视野 tile 列表 ─────────────────────────────────────────────────
    vision_tiles = []
    for tile in get_tiles_in_square(px, py, half):
        tx, ty = tile["x"], tile["y"]
        tile_zone = get_zone_at(tx, ty)
        obj_at = get_object_at(tx, ty)
        vision_tiles.append({
            "x":        tx,
            "y":        ty,
            "type":     tile["type"],
            "walkable": tile["walkable"],
            "world":    tile_zone.get("world"),
            "sector":   tile_zone.get("sector"),
            "arena":    tile_zone.get("arena"),
            "object":   {"id": obj_at["id"], "name": obj_at["name"]} if obj_at else None,
        })

    # ── 3. 正前方格子 ─────────────────────────────────────────────────────
    dx, dy = _DIRECTION_DELTA.get(facing, (0, 0))
    front_obj = get_object_at(px + dx, py + dy)
    front_object = {"id": front_obj["id"], "name": front_obj["name"]} if front_obj else None

    # ── 4. 需求值分档（B13）：只给文字不给数值 ───────────────────────────
    needs = needs_text(player)
    closeness_view: dict[str, dict] = {}
    players_in_view: list[dict] = []
    for pid, other in _players.items():
        if pid == entity_id:
            continue
        ox, oy = other["position"]["x"], other["position"]["y"]
        if abs(ox - px) <= half and abs(oy - py) <= half:
            players_in_view.append({"id": pid, "name": other.get("name", pid),
                                    "position": {"x": ox, "y": oy}, "state": other["state"]})
            closeness_view[pid] = {"name": other.get("name", pid),
                                   "tier": closeness_tier(float(player.get("closeness", {}).get(pid, 0.0)))}
    needs["closeness"] = closeness_view
    needs["recent_uses"] = get_recent_uses(entity_id)

    return {
        "arena_tree":      arena_tree,
        "current":         {"world": zone["world"], "sector": zone["sector"], "arena": zone["arena"],
                            "sector_name": (names["sector"] or {}).get("name"), "arena_name": (names["arena"] or {}).get("name")},
        "vision_tiles":    vision_tiles,
        "front_object":    front_object,
        "players_in_view": players_in_view,
        "needs":           needs,
        "phone":           get_phone_feed(entity_id),   # B10：最近一次刷手机的 digest（无则 null）
        "game":            _game_view(entity_id),       # B18：游戏机局内状态（无则 null）
    }


def _game_view(entity_id: str) -> dict | None:
    from game import external_effects
    p = _players.get(entity_id)
    if p is None or not p.get("game"):
        return None
    return external_effects.game_refresh(p)


@router.get("/arena-tiles")
def arena_tiles(arena_id: str = Query(...)):
    tiles = get_tiles_in_area("arena", arena_id)
    return {
        "arena_id": arena_id,
        "tiles": [{"x": t["x"], "y": t["y"]} for t in tiles],
    }


@router.get("/object-position")
def object_position(object_id: str = Query(...)):
    obj = get_object_by_id(object_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"object not found: {object_id}")

    obj_tile_set = {(t["x"], t["y"]) for t in obj["tiles"]}
    adjacent: list[dict] = []
    seen: set[tuple[int, int]] = set()
    for t in obj["tiles"]:
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            nx, ny = t["x"] + dx, t["y"] + dy
            if (nx, ny) not in obj_tile_set and (nx, ny) not in seen:
                seen.add((nx, ny))
                if is_tile_walkable(nx, ny):
                    adjacent.append({"x": nx, "y": ny})

    return {
        "object_id":      object_id,
        "position":       obj["position"],
        "tiles":          obj["tiles"],
        "adjacent_walkable": adjacent,
    }
