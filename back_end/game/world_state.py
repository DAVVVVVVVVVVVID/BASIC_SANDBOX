import copy
from game.map_data import MAP
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
    {"id": "tree_01",   "type": "tree",   "position": {"x": 20, "y": 3}},
    {"id": "well_01",   "type": "well",   "position": {"x": 14, "y": 13}},
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
        result.append({
            "id":              inst["id"],
            "type":            inst["type"],
            "name":            t["name"],
            "position":        inst["position"],
            "tiles":           tiles,
            "sprite":          t["sprite"],
            "interactable":    t["interactable"],
            "description":     t["description"],
            "maxUsers":        t["max_users"],
            "useStateLabel":   t["use_state_label"],
            "effects":         t["effects"],
            # 运行时状态
            "currentUsers":    0,
            "userList":        [],
        })
    return result


_OBJECTS = _build_objects(_OBJECTS_RAW)

# ── 从字符串地图生成 tile 列表 ────────────────────────────────────────────────

def _generate_tiles() -> list[dict]:
    tiles = []
    for y, row in enumerate(MAP):
        for x, ch in enumerate(row):
            tile_type = CHAR_TO_TYPE.get(ch, "grass")
            tiles.append({
                "x": x,
                "y": y,
                "type": tile_type,
                "walkable": TILE_TYPES[tile_type]["walkable_default"],
                "objectId": None,
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

_WORLD_STATE = {
    "date": "2001-12-30",
    "time": "08:00",
    "isDay": True,
    "weather": "sunny",
}

# tile 快速查询表
_TILE_LOOKUP: dict[tuple[int, int], dict] = {
    (t["x"], t["y"]): t for t in _TILES
}

# ── 可变玩家状态 ──────────────────────────────────────────────────────────────

_player = {
    "id":            "player_01",
    "position":      {"x": 2, "y": 2},
    "facing":        "down",
    "state":         "idle",
    "hp":            100,
    "energy":        80,
    "usingObjectId": None,   # 当前正在使用的 object id，None 表示未使用
}

# ── 公开访问函数 ──────────────────────────────────────────────────────────────

def get_world() -> dict:
    return {
        "tiles": _TILES,
        "objects": _OBJECTS,
        "worldState": _WORLD_STATE,
    }

def get_player() -> dict:
    return copy.deepcopy(_player)

def is_tile_walkable(x: int, y: int) -> bool:
    tile = _TILE_LOOKUP.get((x, y))
    return tile is not None and tile["walkable"]

def update_player_facing(facing: str) -> None:
    _player["facing"] = facing

def update_player_position(x: int, y: int, facing: str) -> None:
    _player["position"]["x"] = x
    _player["position"]["y"] = y
    _player["facing"] = facing
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
    """将实体加入对象的使用者列表，更新玩家状态。"""
    obj = get_object_by_id(obj_id)
    if obj is None:
        return
    if entity_id not in obj["userList"]:
        obj["userList"].append(entity_id)
        obj["currentUsers"] += 1
    label = obj["useStateLabel"].replace("{entity}", entity_id)
    _player["state"] = label
    _player["usingObjectId"] = obj_id

def leave_object(entity_id: str) -> dict | None:
    """将实体从当前使用的对象中移除，恢复玩家状态。返回离开的对象。"""
    obj_id = _player.get("usingObjectId")
    if obj_id is None:
        return None
    obj = get_object_by_id(obj_id)
    if obj and entity_id in obj["userList"]:
        obj["userList"].remove(entity_id)
        obj["currentUsers"] -= 1
    _player["state"] = "idle"
    _player["usingObjectId"] = None
    return obj
