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
)

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

    player = get_player()
    pos = player["position"]
    facing = player["facing"]
    px, py = pos["x"], pos["y"]

    # ── 1. Sector 语义树（含所在 sector 内全部 arenas 及其 objects）────────
    zone  = get_zone_at(px, py)
    names = _find_in_cognitive_map(zone["world"], zone["sector"], zone["arena"])
    cmap  = get_cognitive_map()

    # 从 cognitive map 中找到当前 sector 的完整 arena 列表
    sector_arenas_meta: list[dict] = []
    if zone["sector"]:
        for _w in cmap.get("worlds", []):
            if _w["id"] != zone["world"]:
                continue
            for _s in _w.get("sectors", []):
                if _s["id"] != zone["sector"]:
                    continue
                sector_arenas_meta = _s.get("arenas", [])
                break
            break

    # 为每个 arena 填充其 objects，并标记当前所在 arena
    arena_list: list[dict] = []
    for am in sector_arenas_meta:
        aid  = am["id"]
        objs = [
            {"id": o["id"], "name": o["name"], "interactable": o["interactable"]}
            for o in get_objects_in_arena(aid)
        ]
        arena_list.append({
            "id":      aid,
            "name":    am["name"],
            "current": aid == zone["arena"],   # 标记当前所在场所
            "objects": objs,
        })

    sector_node = {
        **_named(names["sector"], zone["sector"]),
        "arenas": arena_list,
    } if zone["sector"] else None

    world_node = {
        **_named(names["world"], zone["world"]),
        "sector": sector_node,
    } if zone["world"] else None

    arena_tree = world_node

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

    return {
        "arena_tree":   arena_tree,
        "vision_tiles": vision_tiles,
        "front_object": front_object,
    }


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
