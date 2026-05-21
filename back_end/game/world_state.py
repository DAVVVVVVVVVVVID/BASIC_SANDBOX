import copy
import time
from game.maps.map_data   import MAP
from game.maps.world_map  import WORLD_MAP,  WORLD_CHARS
from game.maps.sector_map import SECTOR_MAP, SECTOR_CHARS
from game.maps.arena_map  import ARENA_MAP,  ARENA_CHARS
from game.object_types import OBJECT_TYPES

# ── 地图尺寸（从地图字符串自动推导）─────────────────────────────────────────
MAP_H = len(MAP)
MAP_W = len(MAP[0])

# ── TileType 定义表 ───────────────────────────────────────────────────────────
# 新增 tile 类型：在此表里加一条记录
TILE_TYPES: dict[str, dict] = {
    "grass":          {"walkable_default": True},
    "wall":           {"walkable_default": False},
    "floor":          {"walkable_default": True},
    "floor_occupied": {"walkable_default": False},
}

# ── 字符 → tile 类型映射 ──────────────────────────────────────────────────────
# 新增字符：在此加一条，同时在 TILE_TYPES 加对应类型
CHAR_TO_TYPE: dict[str, str] = {
    "#": "wall",
    ".": "grass",
    "f": "floor",
    "F": "floor_occupied",
}

# ── Object 实例列表 ───────────────────────────────────────────────────────────
# 每条只需 id、type、position，tiles/name/sprite/description 全部从 OBJECT_TYPES 自动补全

_OBJECTS_RAW = [
    {"id": "sofa_01",   "type": "sofa",   "position": {"x": 5,  "y": 1}},
    {"id": "bed_01",    "type": "bed",    "position": {"x": 3,  "y": 1}},
    {"id": "book_01",   "type": "book",   "position": {"x": 1,  "y": 6}},
    {"id": "cook_01",   "type": "cook",   "position": {"x": 9,  "y": 6}},
    {"id": "desk_01",   "type": "desk",   "position": {"x": 1,  "y": 1}},
    {"id": "bath_01",   "type": "bath",   "position": {"x": 8,  "y": 1}},
    {"id": "toilet_01", "type": "toilet", "position": {"x": 9,  "y": 1}},
    {"id": "sink_01",   "type": "sink",   "position": {"x": 10, "y": 1}},
]


def _build_objects(raw: list[dict]) -> list[dict]:
    """将实例列表与类型定义合并，自动生成 tiles footprint 及运行时状态。"""
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
            # 运行时状态
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

# ── 从字符串地图生成 tile 列表 ────────────────────────────────────────────────

def _build_zone_lookup() -> dict[tuple[int, int], dict]:
    """从三张区域图派生 (x, y) → {world, sector, arena} 查找表，并做一致性校验。"""
    lookup: dict[tuple[int, int], dict] = {}

    for y, row in enumerate(WORLD_MAP):
        for x, ch in enumerate(row):
            world  = WORLD_CHARS.get(ch)
            sector = SECTOR_CHARS.get(SECTOR_MAP[y][x])
            arena  = ARENA_CHARS.get(ARENA_MAP[y][x])

            # 一致性校验：有 arena 必须有 sector，有 sector 必须有 world
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
    for y, row in enumerate(MAP):
        for x, ch in enumerate(row):
            tile_type = CHAR_TO_TYPE.get(ch, "grass")
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

_EVENTS = [
    {
        "id": "exit",
        "tiles": [{"x": 11, "y": 4}],
        "description": "前面的区域之后再来探索吧。",
    },
]

_WEATHER = "sunny"

# ── 运行时全局变量 ─────────────────────────────────────────────────────────────
_pending_message: str | None = None   # 下次 GET /player 时带出并清除
_use_start_time:  float | None = None # continuous 对象进入时的时间戳（秒）

# tile 快速查询表
_TILE_LOOKUP: dict[tuple[int, int], dict] = {
    (t["x"], t["y"]): t for t in _TILES
}

# ── 静态角色档案 ──────────────────────────────────────────────────────────────

_player_profile = {
    "id":   "player_01",
    "name": "玩家",
    "age":  25,
}

# ── 可变玩家状态 ──────────────────────────────────────────────────────────────

_player = {
    "id":            "player_01",
    "position":      {"x": 2, "y": 2},
    "facing":        "down",
    "state":         "idle",       # 枚举：idle / walking / requesting_talk / talking / using
    "stateLabel":    None,         # 展示文字，仅 state == "using" 时有值
    "hp":            100.0,
    "energy":        80.0,
    "usingObjectId": None,
    "buffs":         [],           # Buff 实例列表，含 key/value/mode/remaining/source
    "tags":          [],           # tag 字符串列表
    # 状态控制字段（每 tick 重置，buff handler 可覆盖）
    "canMove":       True,
    "canInteract":   True,
    "canUse":        True,
    "moveSpeed":     1.0,
}

# ── 公开访问函数 ──────────────────────────────────────────────────────────────

def get_world() -> dict:
    from game.time_state import get_time_state
    world_state = get_time_state()
    world_state["weather"] = _WEATHER
    return {
        "tiles": _TILES,
        "objects": _OBJECTS,
        "worldState": world_state,
    }

def get_player() -> dict:
    global _pending_message
    data = copy.deepcopy(_player)
    data["pendingMessage"] = _pending_message
    _pending_message = None
    return data

def get_player_profile() -> dict:
    return copy.deepcopy(_player_profile)

def is_tile_walkable(x: int, y: int) -> bool:
    tile = _TILE_LOOKUP.get((x, y))
    return tile is not None and tile["walkable"]

def update_player_facing(facing: str) -> None:
    _player["facing"] = facing

def update_player_position(x: int, y: int, facing: str) -> None:
    _player["position"]["x"] = x
    _player["position"]["y"] = y
    _player["facing"] = facing
    if _player["state"] != "using":
        _player["state"] = "idle"

def set_tile_type(x: int, y: int, new_type: str) -> None:
    """运行时修改某个 tile 的类型与可行走状态。"""
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
    """将实体加入 continuous 对象的使用者列表，更新玩家状态、stateLabel，创建 buff 和 tag。"""
    global _use_start_time
    obj = get_object_by_id(obj_id)
    if obj is None:
        return
    if entity_id not in obj["userList"]:
        obj["userList"].append(entity_id)
        obj["currentUsers"] += 1
    name = _player_profile["name"]
    _player["state"]         = "using"
    _player["stateLabel"]    = obj["useStateLabel"].replace("{entity}", name)
    _player["usingObjectId"] = obj_id

    _use_start_time = time.time() if obj.get("maxDuration") is not None else None

    for e in obj["effects"]:
        if e["type"] == "buff":
            new_buff = {
                "key":       e["key"],
                "value":     e.get("value", 0.0),
                "mode":      e["mode"],
                "remaining": None if e["mode"] == "persistent" else e.get("duration", 0.0),
                "source":    obj_id,
            }
            _player["buffs"] = [
                b for b in _player["buffs"]
                if not (b["source"] == obj_id and b["key"] == e["key"])
            ]
            _player["buffs"].append(new_buff)
        elif e["type"] == "tag":
            if e["key"] not in _player["tags"]:
                _player["tags"].append(e["key"])


def apply_instant_object(obj_id: str, entity_id: str) -> None:
    """应用 instant 对象的效果（instant_effect + timed buff），不改变玩家状态。"""
    obj = get_object_by_id(obj_id)
    if obj is None:
        return
    for e in obj["effects"]:
        if e["type"] == "instant_effect":
            key   = e["key"]
            value = e.get("value", 0.0)
            if key == "energy":
                _player["energy"] = max(0.0, min(100.0, _player["energy"] + value))
            elif key == "hp":
                _player["hp"] = max(0.0, min(100.0, _player["hp"] + value))
        elif e["type"] == "buff" and e.get("mode") == "timed":
            new_buff = {
                "key":       e["key"],
                "value":     e.get("value", 0.0),
                "mode":      "timed",
                "remaining": e.get("duration", 0.0),
                "source":    obj_id,
            }
            _player["buffs"] = [
                b for b in _player["buffs"]
                if not (b["source"] == obj_id and b["key"] == e["key"])
            ]
            _player["buffs"].append(new_buff)


def leave_object(entity_id: str) -> dict | None:
    """将实体从当前使用的对象中移除，清除 persistent buff，恢复玩家状态。返回离开的对象。"""
    global _use_start_time
    obj_id = _player.get("usingObjectId")
    if obj_id is None:
        return None
    obj = get_object_by_id(obj_id)
    if obj and entity_id in obj["userList"]:
        obj["userList"].remove(entity_id)
        obj["currentUsers"] -= 1

    _player["buffs"] = [
        b for b in _player["buffs"]
        if not (b["mode"] == "persistent" and b["source"] == obj_id)
    ]
    if obj:
        obj_tags = {e["key"] for e in obj["effects"] if e["type"] == "tag"}
        _player["tags"] = [t for t in _player["tags"] if t not in obj_tags]

    _player["state"]         = "idle"
    _player["stateLabel"]    = None
    _player["usingObjectId"] = None
    _use_start_time          = None
    return obj


def get_tile_at(x: int, y: int) -> dict | None:
    return _TILE_LOOKUP.get((x, y))

def get_zone_at(x: int, y: int) -> dict:
    """Return {world, sector, arena} ID strings for a tile, any may be None."""
    return _ZONE_LOOKUP.get((x, y), {"world": None, "sector": None, "arena": None})

def get_tiles_in_square(cx: int, cy: int, half: int) -> list[dict]:
    """Return all tiles within a square of side (2*half+1) centered on (cx, cy)."""
    result = []
    for dy in range(-half, half + 1):
        for dx in range(-half, half + 1):
            tile = _TILE_LOOKUP.get((cx + dx, cy + dy))
            if tile is not None:
                result.append(tile)
    return result

def get_objects_in_arena(arena_id: str) -> list[dict]:
    """Return all objects whose anchor position belongs to the given arena."""
    result = []
    for obj in _OBJECTS:
        pos = obj["position"]
        zone = _ZONE_LOOKUP.get((pos["x"], pos["y"]), {})
        if zone.get("arena") == arena_id:
            result.append(obj)
    return result

def get_tiles_in_area(area_type: str, area_id: str) -> list[dict]:
    """Return all tiles belonging to a given world / sector / arena."""
    return [
        t for t in _TILES
        if _ZONE_LOOKUP.get((t["x"], t["y"]), {}).get(area_type) == area_id
    ]

def get_walkable_tiles_in_area(area_type: str, area_id: str) -> list[dict]:
    """Return walkable tiles in the given area."""
    return [t for t in get_tiles_in_area(area_type, area_id) if t["walkable"]]

def get_cognitive_map() -> dict:
    from game.maps.cognitive_map import COGNITIVE_MAP
    return COGNITIVE_MAP

def get_player_buffs() -> list:
    """返回当前 buff 列表的深拷贝。"""
    import copy
    return copy.deepcopy(_player["buffs"])

def clear_player_buffs() -> int:
    """强制清除所有 buff，返回清除数量。"""
    count = len(_player["buffs"])
    _player["buffs"] = []
    return count

def force_reset_player_state(entity_id: str) -> dict:
    """
    强制重置玩家状态：
    - 若正在使用对象，先执行 leave_object
    - 清除所有剩余 buff 和 tag
    - 状态归 idle
    返回操作摘要。
    """
    left_obj_id = None
    if _player.get("usingObjectId"):
        obj = leave_object(entity_id)
        left_obj_id = obj["id"] if obj else None

    cleared_buffs = len(_player["buffs"])
    _player["buffs"] = []
    _player["tags"]  = []
    _player["state"]         = "idle"
    _player["stateLabel"]    = None
    _player["usingObjectId"] = None
    return {"left_object": left_obj_id, "cleared_buffs": cleared_buffs}

def _check_auto_leave() -> None:
    """检测 continuous 对象的 max_duration 是否到期，到期则自动触发 leave_object。"""
    global _pending_message
    if _player.get("usingObjectId") is None or _use_start_time is None:
        return
    obj = get_object_by_id(_player["usingObjectId"])
    if obj is None:
        return
    max_duration = obj.get("maxDuration")
    if max_duration is None:
        return
    if time.time() - _use_start_time >= max_duration:
        left = leave_object("player_01")
        if left:
            _pending_message = left.get("leaveMessage")


def run_buff_tick(delta: float) -> None:
    """在 _player 上执行一次 buff tick，并检测 max_duration 自动退出。"""
    from game.buff_tick import run_tick
    run_tick(_player, delta)
    _check_auto_leave()
