import copy
from game.map_data import MAP

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
        footprint = obj.get("tiles") or [obj["position"]]
        for pos in footprint:
            tile = local_lookup.get((pos["x"], pos["y"]))
            if tile:
                tile["objectId"] = obj["id"]

    return tiles


_OBJECTS = [
    {
        "id": "tree_01",
        "name": "老橡树",
        "position": {"x": 20, "y": 3},
        "interactable": True,
        "description": "一棵粗壮的老橡树，树皮上刻着一些符文。",
    },
    {
        "id": "well_01",
        "name": "古老的水井",
        "position": {"x": 14, "y": 13},
        "interactable": True,
        "description": "井水清澈，似乎深不见底。",
    },
    {
        "id": "sofa_01",
        "name": "沙发",
        "position": {"x": 5, "y": 1},
        "tiles": [{"x": 5, "y": 1}, {"x": 6, "y": 1}],
        "sprite": "sofa",
        "interactable": True,
        "description": "一张舒适的沙发，坐上去软绵绵的。",
    },
    {
        "id": "bed_01",
        "name": "床",
        "position": {"x": 3, "y": 1},
        "tiles": [
            {"x": 3, "y": 1}, {"x": 4, "y": 1},
            {"x": 3, "y": 2}, {"x": 4, "y": 2},
            {"x": 3, "y": 3}, {"x": 4, "y": 3},
        ],
        "sprite": "bed",
        "interactable": True,
        "description": "一张整洁的单人床。",
    },
    {
        "id": "book_01",
        "name": "书",
        "position": {"x": 1, "y": 6},
        "tiles": [{"x": 1, "y": 6}, {"x": 2, "y": 6}, {"x": 3, "y": 6}],
        "sprite": "book",
        "interactable": True,
        "description": "一本厚厚的书，封面上写着看不懂的文字。",
    },
    {
        "id": "cook_01",
        "name": "炉灶",
        "position": {"x": 9, "y": 6},
        "tiles": [{"x": 9, "y": 6}, {"x": 10, "y": 6}],
        "sprite": "cook",
        "interactable": True,
        "description": "炉火正旺，锅里咕嘟咕嘟地冒着热气。",
    },
    {
        "id": "desk_01",
        "name": "书桌",
        "position": {"x": 1, "y": 1},
        "tiles": [{"x": 1, "y": 1}, {"x": 2, "y": 1}],
        "sprite": "desk",
        "interactable": True,
        "description": "一张木制书桌，桌面上摆着一些文件。",
    },
    {
        "id": "bath_01",
        "name": "浴缸",
        "position": {"x": 8, "y": 1},
        "tiles": [{"x": 8, "y": 1}, {"x": 8, "y": 2}],
        "sprite": "bath",
        "interactable": True,
        "description": "一个白色的浴缸，里面的水还是温热的。",
    },
    {
        "id": "toilet_01",
        "name": "马桶",
        "position": {"x": 9, "y": 1},
        "sprite": "toilet",
        "interactable": True,
        "description": "一个干净的马桶。",
    },
    {
        "id": "sink_01",
        "name": "洗手台",
        "position": {"x": 10, "y": 1},
        "sprite": "sink",
        "interactable": True,
        "description": "一个白色的洗手台，水龙头锃光瓦亮。",
    },
]

_TILES = _generate_tiles()

_EVENTS = [
    {
        "id": "event_entrance",
        "tiles": [{"x": 2, "y": 2}, {"x": 3, "y": 2}],
        "description": "你来到了村庄入口。",
    },
    {
        "id": "event_well_area",
        "tiles": [{"x": 14, "y": 14}, {"x": 15, "y": 13}],
        "description": "这里弥漫着一股神秘的气息。",
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
    "id": "player_01",
    "position": {"x": 2, "y": 2},
    "facing": "down",
    "state": "idle",
    "hp": 100,
    "energy": 80,
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
        footprint = o.get("tiles") or [o["position"]]
        if any(p["x"] == x and p["y"] == y for p in footprint):
            return o
    return None
