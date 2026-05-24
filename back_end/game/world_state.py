import copy
import json
import time
import uuid
from pathlib import Path
from game.object_types import OBJECT_TYPES

# ── 从 JSON 加载地图数据 ──────────────────────────────────────────────────────
_MAP_DIR = Path(__file__).parent / "maps"

with open(_MAP_DIR / "map.json", encoding="utf-8") as _f:
    _MAP_DATA = json.load(_f)

with open(_MAP_DIR / "objects.json", encoding="utf-8") as _f:
    _OBJECTS_RAW: list[dict] = json.load(_f)

with open(_MAP_DIR / "tile_types.json", encoding="utf-8") as _f:
    _TILE_TYPES_RAW: dict[str, dict] = json.load(_f)

_META       = _MAP_DATA["meta"]
MAP_W: int  = _META["width"]
MAP_H: int  = _META["height"]
_TILE_ROWS  = _MAP_DATA["tiles"]
_TILE_CHARS = _MAP_DATA["tile_chars"]
_ZONE_CHARS = _MAP_DATA["zone_chars"]
_WORLD_ROWS  = _MAP_DATA["world_map"]
_SECTOR_ROWS = _MAP_DATA["sector_map"]
_ARENA_ROWS  = _MAP_DATA["arena_map"]

# ── TileType 定义表 ───────────────────────────────────────────────────────────
TILE_TYPES: dict[str, dict] = {
    name: {"walkable_default": defn["walkable"]}
    for name, defn in _TILE_TYPES_RAW.items()
}


def _build_objects(raw: list[dict]) -> list[dict]:
    result = []
    for inst in raw:
        t = OBJECT_TYPES[inst["type"]]
        w, h = t["size"]
        x, y = inst["position"]["x"], inst["position"]["y"]
        tiles = [{"x": x + dx, "y": y + dy} for dy in range(h) for dx in range(w)]
        obj: dict = {
            "id":             inst["id"],
            "type":           inst["type"],
            "prototype":      t["prototype"],
            "name":           t["name"],
            "position":       inst["position"],
            "tiles":          tiles,
            "sprite":         t["sprite"],
            "interactable":   t["interactable"],
            "description":    t["description"],
            "effects":        t["effects"],
            "successMessage": t["success_message"],
            "failureMessage": t["failure_message"],
            "currentUsers":   0,
            "userList":       [],
        }
        if t["prototype"] == "continuous":
            obj["maxUsers"]      = t["max_users"]
            obj["useStateLabel"] = t["use_state_label"]
            obj["maxDuration"]   = t.get("max_duration")
            obj["leaveMessage"]  = t.get("leave_message")
        result.append(obj)
    return result


_OBJECTS = _build_objects(_OBJECTS_RAW)


def _build_zone_lookup() -> dict[tuple[int, int], dict]:
    lookup: dict[tuple[int, int], dict] = {}
    world_chars  = _ZONE_CHARS["world"]
    sector_chars = _ZONE_CHARS["sector"]
    arena_chars  = _ZONE_CHARS["arena"]

    for y, row in enumerate(_WORLD_ROWS):
        for x, ch in enumerate(row):
            world  = world_chars.get(ch)
            sector = sector_chars.get(_SECTOR_ROWS[y][x])
            arena  = arena_chars.get(_ARENA_ROWS[y][x])

            if arena and not sector:
                raise ValueError(f"Zone map inconsistency at ({x},{y}): arena='{arena}' but sector is None")
            if sector and not world:
                raise ValueError(f"Zone map inconsistency at ({x},{y}): sector='{sector}' but world is None")

            if world or sector or arena:
                lookup[(x, y)] = {"world": world, "sector": sector, "arena": arena}

    return lookup


_ZONE_LOOKUP = _build_zone_lookup()


def _generate_tiles() -> list[dict]:
    tiles = []
    for y, row in enumerate(_TILE_ROWS):
        for x, ch in enumerate(row):
            tile_type = _TILE_CHARS.get(ch, "grass")
            zone = _ZONE_LOOKUP.get((x, y), {})
            tiles.append({
                "x": x,
                "y": y,
                "type": tile_type,
                "walkable": TILE_TYPES[tile_type]["walkable_default"],
                "objectId": None,
                "world":  zone.get("world"),
                "sector": zone.get("sector"),
                "arena":  zone.get("arena"),
            })

    local_lookup = {(t["x"], t["y"]): t for t in tiles}
    for obj in _OBJECTS:
        for pos in obj["tiles"]:
            tile = local_lookup.get((pos["x"], pos["y"]))
            if tile:
                tile["objectId"] = obj["id"]

    return tiles


_TILES = _generate_tiles()
_EVENTS: list[dict] = _MAP_DATA["events"]
_WEATHER = "sunny"

_TILE_LOOKUP: dict[tuple[int, int], dict] = {
    (t["x"], t["y"]): t for t in _TILES
}

# ── 多玩家运行时状态 ──────────────────────────────────────────────────────────
_players:          dict[str, dict]          = {}
_pending_messages: dict[str, str | None]    = {}
_use_start_times:  dict[str, float | None]  = {}


def _make_player(player_id: str, name: str) -> dict:
    return {
        "id":            player_id,
        "name":          name,
        "position":      {"x": _META["player_start"]["x"], "y": _META["player_start"]["y"]},
        "facing":        _META["player_start"]["facing"],
        "state":         "idle",
        "stateLabel":    None,
        "hp":            100.0,
        "energy":        80.0,
        "usingObjectId": None,
        "buffs":         [],
        "tags":          [],
        "canMove":       True,
        "canInteract":   True,
        "canUse":        True,
        "moveSpeed":     1.0,
    }


# ── 玩家生命周期 ──────────────────────────────────────────────────────────────

def create_player(name: str) -> dict:
    """创建新玩家，生成唯一 ID，返回玩家数据的深拷贝。"""
    safe = name[:12].lower().replace(" ", "_")
    player_id = f"{safe}_{uuid.uuid4().hex[:6]}"
    player = _make_player(player_id, name)
    _players[player_id] = player
    _pending_messages[player_id] = None
    _use_start_times[player_id]  = None
    return copy.deepcopy(player)


def remove_player(player_id: str) -> None:
    """移除玩家，自动离开正在使用的对象。"""
    if player_id not in _players:
        return
    leave_object(player_id)
    _players.pop(player_id, None)
    _pending_messages.pop(player_id, None)
    _use_start_times.pop(player_id, None)


# ── 公开访问函数 ──────────────────────────────────────────────────────────────

def get_world() -> dict:
    from game.time_state import get_time_state, get_last_game_delta
    delta = get_last_game_delta()
    if delta > 0:
        _run_buff_tick_all(delta)
    world_state = get_time_state()
    world_state["weather"] = _WEATHER
    return {
        "tiles":      _TILES,
        "objects":    _OBJECTS,
        "worldState": world_state,
        "players":    get_all_players_snapshot(),
    }


def get_player(player_id: str) -> dict | None:
    player = _players.get(player_id)
    if player is None:
        return None
    data = copy.deepcopy(player)
    data["pendingMessage"] = _pending_messages.get(player_id)
    _pending_messages[player_id] = None
    return data


def get_all_players_snapshot() -> list[dict]:
    return [
        {
            "id":       p["id"],
            "name":     p["name"],
            "position": copy.deepcopy(p["position"]),
            "facing":   p["facing"],
            "state":    p["state"],
        }
        for p in _players.values()
    ]


def is_tile_walkable(x: int, y: int) -> bool:
    tile = _TILE_LOOKUP.get((x, y))
    return tile is not None and tile["walkable"]


def update_player_facing(player_id: str, facing: str) -> None:
    if player_id in _players:
        _players[player_id]["facing"] = facing


def update_player_position(player_id: str, x: int, y: int, facing: str) -> None:
    player = _players.get(player_id)
    if player is None:
        return
    player["position"]["x"] = x
    player["position"]["y"] = y
    player["facing"] = facing
    if player["state"] != "using":
        player["state"] = "idle"


def set_tile_type(x: int, y: int, new_type: str) -> None:
    tile = _TILE_LOOKUP.get((x, y))
    if tile and new_type in TILE_TYPES:
        tile["type"] = new_type
        tile["walkable"] = TILE_TYPES[new_type]["walkable_default"]


def get_events() -> list:
    return _EVENTS


def get_object_by_id(object_id: str) -> dict | None:
    return next((o for o in _OBJECTS if o["id"] == object_id), None)


def get_object_at(x: int, y: int) -> dict | None:
    for o in _OBJECTS:
        if any(p["x"] == x and p["y"] == y for p in o["tiles"]):
            return o
    return None


def enter_object(obj_id: str, entity_id: str) -> None:
    player = _players.get(entity_id)
    if player is None:
        return
    obj = get_object_by_id(obj_id)
    if obj is None:
        return
    if entity_id not in obj["userList"]:
        obj["userList"].append(entity_id)
        obj["currentUsers"] += 1
    player["state"]         = "using"
    player["stateLabel"]    = obj["useStateLabel"].replace("{entity}", player["name"])
    player["usingObjectId"] = obj_id
    _use_start_times[entity_id] = time.time() if obj.get("maxDuration") is not None else None

    for e in obj["effects"]:
        if e["type"] == "buff":
            new_buff = {
                "key":       e["key"],
                "value":     e.get("value", 0.0),
                "mode":      e["mode"],
                "remaining": None if e["mode"] == "persistent" else e.get("duration", 0.0),
                "source":    obj_id,
            }
            player["buffs"] = [
                b for b in player["buffs"]
                if not (b["source"] == obj_id and b["key"] == e["key"])
            ]
            player["buffs"].append(new_buff)
        elif e["type"] == "tag":
            if e["key"] not in player["tags"]:
                player["tags"].append(e["key"])


def apply_instant_object(obj_id: str, entity_id: str) -> None:
    player = _players.get(entity_id)
    if player is None:
        return
    obj = get_object_by_id(obj_id)
    if obj is None:
        return
    for e in obj["effects"]:
        if e["type"] == "instant_effect":
            key   = e["key"]
            value = e.get("value", 0.0)
            if key == "energy":
                player["energy"] = max(0.0, min(100.0, player["energy"] + value))
            elif key == "hp":
                player["hp"] = max(0.0, min(100.0, player["hp"] + value))
        elif e["type"] == "buff" and e.get("mode") == "timed":
            new_buff = {
                "key":       e["key"],
                "value":     e.get("value", 0.0),
                "mode":      "timed",
                "remaining": e.get("duration", 0.0),
                "source":    obj_id,
            }
            player["buffs"] = [
                b for b in player["buffs"]
                if not (b["source"] == obj_id and b["key"] == e["key"])
            ]
            player["buffs"].append(new_buff)


def leave_object(entity_id: str) -> dict | None:
    player = _players.get(entity_id)
    if player is None:
        return None
    obj_id = player.get("usingObjectId")
    if obj_id is None:
        return None
    obj = get_object_by_id(obj_id)
    if obj and entity_id in obj["userList"]:
        obj["userList"].remove(entity_id)
        obj["currentUsers"] -= 1

    player["buffs"] = [
        b for b in player["buffs"]
        if not (b["mode"] == "persistent" and b["source"] == obj_id)
    ]
    if obj:
        obj_tags = {e["key"] for e in obj["effects"] if e["type"] == "tag"}
        player["tags"] = [t for t in player["tags"] if t not in obj_tags]

    player["state"]         = "idle"
    player["stateLabel"]    = None
    player["usingObjectId"] = None
    _use_start_times[entity_id] = None
    return obj


def get_tile_at(x: int, y: int) -> dict | None:
    return _TILE_LOOKUP.get((x, y))


def get_zone_at(x: int, y: int) -> dict:
    return _ZONE_LOOKUP.get((x, y), {"world": None, "sector": None, "arena": None})


def get_tiles_in_square(cx: int, cy: int, half: int) -> list[dict]:
    result = []
    for dy in range(-half, half + 1):
        for dx in range(-half, half + 1):
            tile = _TILE_LOOKUP.get((cx + dx, cy + dy))
            if tile is not None:
                result.append(tile)
    return result


def get_objects_in_arena(arena_id: str) -> list[dict]:
    result = []
    for obj in _OBJECTS:
        pos = obj["position"]
        zone = _ZONE_LOOKUP.get((pos["x"], pos["y"]), {})
        if zone.get("arena") == arena_id:
            result.append(obj)
    return result


def get_tiles_in_area(area_type: str, area_id: str) -> list[dict]:
    return [
        t for t in _TILES
        if _ZONE_LOOKUP.get((t["x"], t["y"]), {}).get(area_type) == area_id
    ]


def get_walkable_tiles_in_area(area_type: str, area_id: str) -> list[dict]:
    return [t for t in get_tiles_in_area(area_type, area_id) if t["walkable"]]


def get_cognitive_map() -> dict:
    from game.maps.cognitive_map import COGNITIVE_MAP
    return COGNITIVE_MAP


def get_player_buffs(player_id: str) -> list:
    player = _players.get(player_id)
    if player is None:
        return []
    return copy.deepcopy(player["buffs"])


def clear_player_buffs(player_id: str) -> int:
    player = _players.get(player_id)
    if player is None:
        return 0
    count = len(player["buffs"])
    player["buffs"] = []
    return count


def force_reset_player_state(entity_id: str) -> dict:
    player = _players.get(entity_id)
    if player is None:
        return {"left_object": None, "cleared_buffs": 0}

    left_obj_id = None
    if player.get("usingObjectId"):
        obj = leave_object(entity_id)
        left_obj_id = obj["id"] if obj else None

    cleared_buffs = len(player["buffs"])
    player["buffs"]         = []
    player["tags"]          = []
    player["state"]         = "idle"
    player["stateLabel"]    = None
    player["usingObjectId"] = None
    return {"left_object": left_obj_id, "cleared_buffs": cleared_buffs}


# ── 内部：buff tick ───────────────────────────────────────────────────────────

def _check_auto_leave(player_id: str) -> None:
    player = _players.get(player_id)
    if player is None:
        return
    if player.get("usingObjectId") is None or _use_start_times.get(player_id) is None:
        return
    obj = get_object_by_id(player["usingObjectId"])
    if obj is None:
        return
    max_duration = obj.get("maxDuration")
    if max_duration is None:
        return
    if time.time() - _use_start_times[player_id] >= max_duration:
        left = leave_object(player_id)
        if left:
            _pending_messages[player_id] = left.get("leaveMessage")


def _run_buff_tick_all(delta: float) -> None:
    from game.buff_tick import run_tick
    for player_id in list(_players.keys()):
        run_tick(_players[player_id], delta)
        _check_auto_leave(player_id)
