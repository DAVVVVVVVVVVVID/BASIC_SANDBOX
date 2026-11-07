import copy
import json
import os
import random
import threading
import time
import uuid
from pathlib import Path
from game.object_types import OBJECT_TYPES
from game.buff_tick import set_var, add_var, add_closeness, NEED_VARS, DECAY_BUFF, mood_baseline as _mood_baseline, apply_control_flags
from game.time_state import now_real, game_now_ts

# ── 从 JSON 加载地图数据 ──────────────────────────────────────────────────────
# SANDBOX_MAP_DIR：地图目录（默认 game/maps；m1c 用 game/maps/m1c），一机多镇可各用一张图
def _resolve_map_dir() -> Path:
    """SANDBOX_MAP_DIR（目录）优先；否则 SANDBOX_MAP=v1|m1c|legacy_v0（W11 冻结开关，game/maps/<name>）；否则默认 game/maps（v0）。"""
    base = Path(__file__).parent / "maps"
    if os.environ.get("SANDBOX_MAP_DIR"):
        return Path(os.environ["SANDBOX_MAP_DIR"])
    name = (os.environ.get("SANDBOX_MAP") or "").strip()
    if name and name not in ("v0", "default") and (base / name / "map.json").exists():
        return base / name
    return base


_MAP_DIR = _resolve_map_dir()
TOWN: str = os.environ.get("SANDBOX_TOWN", "main")      # 数据集每行带的镇名（towns.yaml 的 key）

# 地图数据（load_map 原地填充：已 import 这些名字的模块不会失效）
_MAP_DATA: dict = {}
_OBJECTS_RAW: list[dict] = []
_TILE_TYPES_RAW: dict[str, dict] = {}
_META: dict = {}
MAP_W: int = 0
MAP_H: int = 0
_TILE_ROWS: list[str] = []
_TILE_CHARS: dict = {}
_ZONE_CHARS: dict = {}
_WORLD_ROWS: list[str] = []
_SECTOR_ROWS: list[str] = []
_ARENA_ROWS: list[str] = []
TILE_TYPES: dict[str, dict] = {}
_OBJECTS: list[dict] = []
_ZONE_LOOKUP: dict[tuple[int, int], dict] = {}
_TILES: list[dict] = []
_TILE_LOOKUP: dict[tuple[int, int], dict] = {}
MAP_VERSION: str = ""
MAP_FORMAT: int = 1
_EVENTS: list[dict] = []
_WEATHER = "sunny"
# ── 地图格式 v2（W9）：连接边 / 楼层 / 场所访问规则 ──
_EDGES: list[dict] = []                                   # {id, kind, a:{arena,x,y}, b:{arena,x,y}, open_hours?, allow?, name?}
_FLOORS: dict[str, int] = {}                              # arena -> floor（默认 1）
_ACCESS: dict[str, dict] = {}                             # arena -> {owner:[...], locked:[["09:00","18:30"]], allow_when_locked:[...]}
_EDGE_BY_PAIR: dict[frozenset, dict] = {}                 # {(x,y),(x,y)} -> edge（门 / 路口：相邻两格之间）
_STAIRS: dict[tuple[int, int], list[tuple[tuple[int, int], dict]]] = {}   # 楼梯：非相邻邻接
_HOMES: dict[str, str] = {}                               # agent_id -> 家 arena（map.json homes，覆盖 AGENT_HOME_ARENA）
_ARENA_SECTOR: dict[str, str] = {}                        # arena -> sector（load_map 时建）


def sector_of_arena(arena: str | None) -> str | None:
    return _ARENA_SECTOR.get(arena or "")


def zone_display_name(level: str, zid: str) -> str:
    names = (_MAP_DATA.get("zone_names") or {}).get(level) or {}
    v = names.get(zid)
    return (v.get("name") if isinstance(v, dict) else v) or zid


def _initial_stock(obj_type: str) -> dict | None:
    from game.economy import initial_stock
    return initial_stock(obj_type)


# ── 运行时改物品（W11 维护：X1 N5「记忆过期」夹具）。只改内存：挪位 / 撤掉 / 恢复，重算 tiles / mapVersion；不进地图文件，重启即还原 ──
_OBJ_ORIG_POS: dict[str, dict] = {}        # id -> 最初位置 {x, y}（restore 用）
_REMOVED_OBJECTS: dict[str, dict] = {}     # id -> 撤掉的 raw inst


def _object_char() -> str:
    for ch, t in _TILE_CHARS.items():
        if t == "object":
            return ch
    return "a"


def _set_tile_char(x: int, y: int, ch: str) -> None:
    row = _TILE_ROWS[y]
    _TILE_ROWS[y] = row[:x] + ch + row[x + 1:]


def _floor_char_near(x: int, y: int) -> str:
    """物品挪走后脚下该是什么：取 4 邻里最近的可走格字符（同 arena 优先），兜底 'f'。"""
    from collections import deque
    arena = _ZONE_LOOKUP.get((x, y), {}).get("arena")
    seen = {(x, y)}; q = deque([(x, y)]); fallback = None
    while q:
        cx, cy = q.popleft()
        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            nx, ny = cx + dx, cy + dy
            if (nx, ny) in seen or not (0 <= nx < MAP_W and 0 <= ny < MAP_H):
                continue
            seen.add((nx, ny))
            ch = _TILE_ROWS[ny][nx]
            if TILE_TYPES.get(_TILE_CHARS.get(ch, "grass"), {}).get("walkable_default"):
                if _ZONE_LOOKUP.get((nx, ny), {}).get("arena") == arena:
                    return ch
                fallback = fallback or ch
            if len(seen) > 400:
                break
            q.append((nx, ny))
    return fallback or "f"


def _rebuild_objects_keep_runtime() -> None:
    old = {o["id"]: o for o in _OBJECTS}
    _OBJECTS[:] = _build_objects(_OBJECTS_RAW)
    for o in _OBJECTS:
        po = old.get(o["id"])
        if po is not None:
            o["userList"] = list(po["userList"]); o["currentUsers"] = po["currentUsers"]
            if po.get("stock") is not None:
                o["stock"] = dict(po["stock"])
    _TILES[:] = _generate_tiles()
    _TILE_LOOKUP.clear(); _TILE_LOOKUP.update({(t["x"], t["y"]): t for t in _TILES})
    global MAP_VERSION
    MAP_VERSION = _compute_map_version()
    refresh_shop_views()
    for p in _players.values():
        _ensure_valid_position(p)


def _kick_users(obj: dict) -> list[str]:
    kicked = []
    for uid in list(obj["userList"]):
        if uid in _players:
            leave_object(uid); kicked.append(uid)
    obj["userList"] = []; obj["currentUsers"] = 0
    return kicked


def _footprint(obj_type: str, x: int, y: int) -> list[tuple[int, int]]:
    w, h = OBJECT_TYPES[obj_type]["size"]
    return [(x + dx, y + dy) for dy in range(h) for dx in range(w)]


def move_object(obj_id: str, x: int, y: int) -> dict:
    """把物品挪到 (x, y)（左上角）。目标脚印必须全部是当前可走格且没人站着（或是它自己原来的格）。返回 {id, from, to, kicked}。"""
    with STATE_LOCK:
        obj = get_object_by_id(obj_id)
        if obj is None:
            raise ValueError(f"object not found: {obj_id}")
        own = {(t["x"], t["y"]) for t in obj["tiles"]}
        occupied = {(p["position"]["x"], p["position"]["y"]) for p in _players.values()}
        for tx, ty in _footprint(obj["type"], x, y):
            if not (0 <= tx < MAP_W and 0 <= ty < MAP_H):
                raise ValueError(f"target tile ({tx},{ty}) out of map")
            if (tx, ty) not in own and not is_tile_walkable(tx, ty):
                raise ValueError(f"target tile ({tx},{ty}) not walkable")
            if (tx, ty) in occupied:
                raise ValueError(f"player standing at ({tx},{ty})")
        kicked = _kick_users(obj)
        frm = dict(obj["position"])
        _OBJ_ORIG_POS.setdefault(obj_id, frm)
        for tx, ty in own:
            _set_tile_char(tx, ty, _floor_char_near(tx, ty))
        for tx, ty in _footprint(obj["type"], x, y):
            _set_tile_char(tx, ty, _object_char())
        for inst in _OBJECTS_RAW:
            if inst["id"] == obj_id:
                inst["position"] = {"x": x, "y": y}
        _rebuild_objects_keep_runtime()
        return {"id": obj_id, "from": frm, "to": {"x": x, "y": y}, "kicked": kicked, "mapVersion": MAP_VERSION}


def remove_object(obj_id: str) -> dict:
    """撤掉物品（脚下变地板）。返回 {id, position, kicked}。"""
    with STATE_LOCK:
        obj = get_object_by_id(obj_id)
        if obj is None:
            raise ValueError(f"object not found: {obj_id}")
        kicked = _kick_users(obj)
        _OBJ_ORIG_POS.setdefault(obj_id, dict(obj["position"]))
        for t in obj["tiles"]:
            _set_tile_char(t["x"], t["y"], _floor_char_near(t["x"], t["y"]))
        inst = next(i for i in _OBJECTS_RAW if i["id"] == obj_id)
        _REMOVED_OBJECTS[obj_id] = {**inst, "_stock": obj.get("stock"), "_index": _OBJECTS_RAW.index(inst)}   # 记原顺序：mapVersion 指纹按顺序算
        _OBJECTS_RAW[:] = [i for i in _OBJECTS_RAW if i["id"] != obj_id]
        _rebuild_objects_keep_runtime()
        return {"id": obj_id, "position": dict(obj["position"]), "kicked": kicked, "mapVersion": MAP_VERSION}


def restore_object(obj_id: str | None = None) -> dict:
    """恢复：撤掉的放回原位、挪过的挪回原位；不给 id = 全部。返回 {restored: [...]}。"""
    with STATE_LOCK:
        ids = [obj_id] if obj_id else sorted(set(_REMOVED_OBJECTS) | set(_OBJ_ORIG_POS))
        done = []
        for oid in ids:
            if oid in _REMOVED_OBJECTS:
                inst = _REMOVED_OBJECTS.pop(oid); stock = inst.pop("_stock", None); idx = inst.pop("_index", len(_OBJECTS_RAW))
                pos = _OBJ_ORIG_POS.get(oid, inst["position"])
                inst["position"] = dict(pos)
                for tx, ty in _footprint(inst["type"], pos["x"], pos["y"]):
                    _set_tile_char(tx, ty, _object_char())
                _OBJECTS_RAW.insert(min(idx, len(_OBJECTS_RAW)), inst)
                _rebuild_objects_keep_runtime()
                if stock is not None:
                    get_object_by_id(oid)["stock"] = stock; refresh_shop_views()
                _OBJ_ORIG_POS.pop(oid, None); done.append(oid)
            elif oid in _OBJ_ORIG_POS:
                pos = _OBJ_ORIG_POS[oid]
                cur = get_object_by_id(oid)
                if cur is not None and (cur["position"]["x"], cur["position"]["y"]) != (pos["x"], pos["y"]):
                    move_object(oid, pos["x"], pos["y"])
                _OBJ_ORIG_POS.pop(oid, None); done.append(oid)
        return {"restored": done, "mapVersion": MAP_VERSION}


def path_query(start: tuple[int, int], goals: set[tuple[int, int]], mover: dict | None = None,
               ignore_locks: bool = False) -> dict:
    """任意两格（或到一组目标格）的 BFS 长度（走 edges，按当前游戏时刻的门禁）。"""
    path = bfs_path(start, goals, mover=mover, ignore_locks=ignore_locks)
    if path is None:
        return {"reachable": False, "length": None, "path": None}
    return {"reachable": True, "length": len(path), "path": [{"x": x, "y": y} for x, y in path]}


def goal_tiles_for(to: tuple[int, int] | None = None, to_object: str | None = None, to_arena: str | None = None) -> set[tuple[int, int]]:
    """目标格集合：某格 / 某物品的使用站位（usePos 或相邻可走格）/ 某 arena 全部可走格。"""
    if to is not None:
        return {to}
    if to_object:
        o = get_object_by_id(to_object)
        if o is None:
            return set()
        if o.get("usePos"):
            walk = {(s["x"], s["y"]) for s in o["usePos"] if is_tile_walkable(s["x"], s["y"])}
            if walk:
                return walk                      # 桌类：站位在物品旁；床 / 沙发的站位就是物品格（不可走）→ 落到下面取相邻格
        goals = set()
        for t in o["tiles"]:
            for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                if is_tile_walkable(t["x"] + dx, t["y"] + dy):
                    goals.add((t["x"] + dx, t["y"] + dy))
        return goals
    if to_arena:
        return {(t["x"], t["y"]) for t in _TILES if t["walkable"] and t.get("arena") == to_arena}
    return set()


def _shop_listing(obj_type: str, stock: dict | None = None) -> list[dict] | None:
    from game.economy import shop_listing
    rows = shop_listing(obj_type, stock)
    if rows is None:
        return None
    return [{"type": r["item"], "item": r["item"], "name": r["name"], "price": r["price"], "sell": r["sell"], "stock": r["stock"]} for r in rows]


def refresh_shop_views() -> None:
    """W11：把当前库存写进物品的 shop[]（买卖 / 补货后调用）。"""
    for o in _OBJECTS:
        if o.get("shop") is not None:
            o["shop"] = _shop_listing(o["type"], o.get("stock"))


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
            "sprite":         t.get("sprite", ""),
            "interactable":   t["interactable"],
            "description":    t["description"],
            "effects":        t["effects"],
            "advertise":      t.get("advertise"),       # B5：Sims 式广告值 {var: 0–100}
            "usePos":         [{"x": x + dx, "y": y + dy} for dx, dy in t.get("use_pos", [])] or None,   # W10：使用者站位（绝对格，按使用顺序分配）
            "useFacing":      t.get("use_facing"),      # W10：使用者朝向（None = 按站位相对物品推）
            "shop":           _shop_listing(inst["type"], _initial_stock(inst["type"])),   # W10 ④：商店物品 [{type,item,name,price,sell,stock}]（非商店 None）
            "stock":          _initial_stock(inst["type"]),  # W11 ④：库存 {item: n}（商店 / 冰箱），其余 None
            "openHours":      t.get("open_hours"),      # B20：营业时间 [[start, end], ...]，None = 全天
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

def _compute_map_version() -> str:
    """地图静态内容的指纹（tiles 类型 / 可走 + 物品 id / 类型 / 位置），前端据此决定是否重拉 tiles（E③）。"""
    import hashlib
    h = hashlib.sha1()
    h.update(json.dumps([[t["type"], t["walkable"]] for t in _TILES]).encode())
    h.update(json.dumps([[o["id"], o["type"], o["position"]] for o in _OBJECTS], sort_keys=True).encode())
    return f"{_META.get('name', 'map')}@{h.hexdigest()[:12]}"


def _index_edges() -> None:
    _EDGE_BY_PAIR.clear(); _STAIRS.clear()
    for e in _EDGES:
        a = (int(e["a"]["x"]), int(e["a"]["y"])); b = (int(e["b"]["x"]), int(e["b"]["y"]))
        if abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1:
            _EDGE_BY_PAIR[frozenset((a, b))] = e
        else:                                             # 楼梯 / 传送：非相邻
            _STAIRS.setdefault(a, []).append((b, e))
            _STAIRS.setdefault(b, []).append((a, e))


def load_map(map_dir: Path | str) -> None:
    """加载（或切换）地图目录。原地更新所有模块级容器。"""
    global _MAP_DIR, MAP_W, MAP_H, MAP_VERSION, MAP_FORMAT
    _MAP_DIR = Path(map_dir)
    with open(_MAP_DIR / "map.json", encoding="utf-8") as f:
        data = json.load(f)
    with open(_MAP_DIR / "objects.json", encoding="utf-8") as f:
        objs_raw = json.load(f)
    with open(_MAP_DIR / "tile_types.json", encoding="utf-8") as f:
        tt_raw = json.load(f)
    _MAP_DATA.clear(); _MAP_DATA.update(data)
    _OBJECTS_RAW[:] = objs_raw
    _TILE_TYPES_RAW.clear(); _TILE_TYPES_RAW.update(tt_raw)
    _META.clear(); _META.update(data["meta"])
    MAP_W = _META["width"]; MAP_H = _META["height"]
    MAP_FORMAT = int(data.get("format", 1))
    _TILE_ROWS[:] = data["tiles"]
    _TILE_CHARS.clear(); _TILE_CHARS.update(data["tile_chars"])
    _ZONE_CHARS.clear(); _ZONE_CHARS.update(data["zone_chars"])
    _WORLD_ROWS[:] = data["world_map"]; _SECTOR_ROWS[:] = data["sector_map"]; _ARENA_ROWS[:] = data["arena_map"]
    TILE_TYPES.clear(); TILE_TYPES.update({name: {"walkable_default": d["walkable"]} for name, d in tt_raw.items()})
    _OBJECTS[:] = _build_objects(objs_raw)
    _ZONE_LOOKUP.clear(); _ZONE_LOOKUP.update(_build_zone_lookup())
    _ARENA_SECTOR.clear(); _ARENA_SECTOR.update({z["arena"]: z["sector"] for z in _ZONE_LOOKUP.values() if z.get("arena")})
    _TILES[:] = _generate_tiles()
    _TILE_LOOKUP.clear(); _TILE_LOOKUP.update({(t["x"], t["y"]): t for t in _TILES})
    _EVENTS[:] = data.get("events", [])
    _EDGES[:] = data.get("edges", [])
    _FLOORS.clear(); _FLOORS.update({k: int(v) for k, v in (data.get("floors") or {}).items()})
    _ACCESS.clear(); _ACCESS.update(data.get("access") or {})
    _HOMES.clear(); _HOMES.update(data.get("homes") or {})
    _index_edges()
    MAP_VERSION = _compute_map_version()


load_map(_MAP_DIR)

# ── 多玩家运行时状态 ──────────────────────────────────────────────────────────
_players:          dict[str, dict]          = {}
_pending_messages: dict[str, str | None]    = {}
_use_start_times:  dict[str, float | None]  = {}
_last_seen:        dict[str, float]         = {}

_PLAYER_TIMEOUT = 10.0  # 秒，超过此时间未心跳则自动清除（human 删除；agent 只标 online=False，B6）

# B10：每个 player 最近一次刷手机的 digest（perceive 的 phone 字段）
_phone_feed: dict[str, dict] = {}

# B5：物品使用记录（游戏秒）
_last_used:   dict[str, dict[str, float]]        = {}   # entity -> {obj_id: game_ts}
_use_history: dict[str, list[tuple[float, str]]] = {}   # entity -> [(game_ts, obj_id), ...]
OBJECT_COOLDOWN_S  = 30 * 60.0       # 同一物品 30 游戏分钟冷却（类型可用 cooldown_s 覆盖；床类为 0，W8 Q0e）
AWAY_AFTER_S       = 120.0           # W8 Q0e：人类玩家 120 s 无输入标 away（agent 永不 away）
_last_input: dict[str, float] = {}   # entity -> 最近一次「输入」（动作 / 心跳 / 聊天）的墙钟
RECENT_USES_WINDOW_S = 6 * 3600.0    # 6 游戏小时内使用次数（novelty 折减用）

# 后台 ticker（事件循环线程）与 FastAPI 同步路由（线程池）会并发访问以上字典，
# 遍历 / 导出 / 增删 player 时持有此锁（B8）。
STATE_LOCK = threading.RLock()

# SANDBOX_SEED（towns.yaml m1b 用）：沙盒目前没有随机游戏逻辑；种子只决定 player id 后缀的生成器，
# 使多镇对照里 join 顺序相同 → id 相同（假设）。未设置时用 uuid。
SANDBOX_SEED: int | None = int(os.environ["SANDBOX_SEED"]) if os.environ.get("SANDBOX_SEED", "").strip() else None
_id_rng = random.Random(SANDBOX_SEED) if SANDBOX_SEED is not None else None

# SEED 决定的地图随机要素（W6 任务 2，假设）：
# - 天气序列：每 6 游戏小时一段，由 (seed, 游戏日, 段) 决定；seed 为 None 时恒 sunny（与旧行为一致）
# - NPC 出生点：controller=agent 的玩家出生在其「家」arena 内由 (seed, agent_id) 决定的可走格；seed 为 None 时取该 arena 第一个可走格
WEATHER_SLOT_HOURS = 6
WEATHER_WEIGHTS = (("sunny", 6), ("cloudy", 3), ("rain", 1))
# agent_id 全线统一（04-npcs.md，11-07 定）：whale / achan / npc_xiaoqian / npc_rest_owner / npc_grocer / npc_fisher。
# 这里是 v0 图（map.json 没有 homes）时的兜底；npc_cook / npc_regular 等是 v0 旧别名，只为老检查点保留。
AGENT_HOME_ARENA = {"whale": "storage", "achan": "achan_room", "npc_grocer": "grocer_bedroom", "npc_fisher": "fisher_hut",
                    "npc_rest_owner": "cook_bedroom", "npc_xiaoqian": "regular_bedroom",
                    "npc_cook": "cook_bedroom", "npc_regular": "regular_bedroom",
                    "npc_teacher": "teacher_room", "npc_painter": "painter_room", "npc_herbalist": "herbalist_room"}


def weather_for(game_ts: float) -> str:
    """按 seed 与游戏时刻决定天气（确定性）。"""
    if SANDBOX_SEED is None:
        return "sunny"
    from game.time_state import GAME_TZ
    from datetime import datetime
    dt = datetime.fromtimestamp(game_ts, GAME_TZ)
    slot = dt.hour // WEATHER_SLOT_HOURS
    rng = random.Random(f"{SANDBOX_SEED}:{dt.date().isoformat()}:{slot}")
    names = [w for w, _ in WEATHER_WEIGHTS]; weights = [n for _, n in WEATHER_WEIGHTS]
    return rng.choices(names, weights=weights, k=1)[0]


def update_weather(game_ts: float) -> str:
    global _WEATHER
    _WEATHER = weather_for(game_ts)
    return _WEATHER


def spawn_point_for(agent_id: str | None) -> dict:
    """agent 的出生点：家 arena 内的可走格（seed 决定哪一格）；没有家 / 不是 agent → 地图出生点。"""
    start = _META["player_start"]
    arena = _HOMES.get(agent_id or "") or AGENT_HOME_ARENA.get(agent_id or "")
    if arena is None:
        return {"x": start["x"], "y": start["y"], "facing": start["facing"]}
    tiles = [t for t in get_walkable_tiles_in_area("arena", arena) if get_object_at(t["x"], t["y"]) is None]
    if not tiles:
        return {"x": start["x"], "y": start["y"], "facing": start["facing"]}
    tiles.sort(key=lambda t: (t["y"], t["x"]))
    if SANDBOX_SEED is None:
        t = tiles[0]
    else:
        t = random.Random(f"{SANDBOX_SEED}:spawn:{agent_id}").choice(tiles)
    return {"x": t["x"], "y": t["y"], "facing": "down"}

# 七变量初值（ARCHITECTURE §3.1 B3 / 报告 §4.3 基线）
INITIAL_FULLNESS = 70.0
INITIAL_ENERGY   = 100.0
INITIAL_SOCIAL   = 60.0
INITIAL_FUN      = 60.0
MOOD_BASE        = 65.0


def mood_baseline(E: float = 50.0, N: float = 50.0) -> float:
    """mood 基线 = 65 + 0.2·(E−50) − 0.3·(N−50)（ARCHITECTURE §2.5）。"""
    return _mood_baseline(E, N)


def _agent_id_for(name: str, profile: dict | None) -> str:
    """自我层 agent id：profile.agent_id 优先，否则 name 的 slug（假设）。"""
    profile = profile or {}
    aid = profile.get("agent_id") or profile.get("agent")
    if aid:
        return str(aid)
    return name[:12].lower().replace(" ", "_")


def _make_player(
    player_id: str,
    name: str,
    controller: str = "human",
    profile: dict | None = None,
) -> dict:
    profile = profile or {}
    E = float(profile.get("E", 50.0))
    N = float(profile.get("N", 50.0))
    fullness = INITIAL_FULLNESS
    controller = controller if controller in ("human", "agent") else "human"
    return {
        "id":            player_id,
        "name":          name,
        "position":      {"x": _META["player_start"]["x"], "y": _META["player_start"]["y"]},
        "facing":        _META["player_start"]["facing"],
        "state":         "idle",
        "stateLabel":    None,
        # ── 七变量（B3）。hp 是 fullness 的别名，过渡一个版本 ──
        "hp":            fullness,
        "fullness":      fullness,
        "energy":        INITIAL_ENERGY,
        "social":        INITIAL_SOCIAL,
        "fun":           INITIAL_FUN,
        "mood":          mood_baseline(E, N),
        "mood_base":     mood_baseline(E, N),       # mood 指数回归的基线（B4）
        "emotion_tags":  [],
        "closeness":     {},
        "controller":    controller,
        "online":        True,                       # B6：agent 10 s 无心跳只标 False，不删除
        "away":          False,                      # W8 Q0e：human 120 s 无输入 → True；agent 恒 False
        "scene":         "sandbox",                  # B4：衰减速率按 scene 切换（sandbox | live）
        "agent_id":      _agent_id_for(name, profile) if controller == "agent" else None,
        "last_tick_ts":  _iso_game_now(),
        "pos_seq":       0,
        "inventory":     [],                         # W10 ④：背包 [{item, qty, meta?}]，≤ 10 种
        "gold":          _initial_gold(_agent_id_for(name, profile) if controller == "agent" else None),   # W10 ④：金币（economy.json）
        "usingObjectId": None,
        "buffs":         [dict(DECAY_BUFF)],         # B4：自然衰减元 buff
        "tags":          [],
        "canMove":       True,
        "canInteract":   True,
        "canUse":        True,
        "moveSpeed":     1.0,
    }


def _initial_gold(agent_id: str | None) -> int:
    from game.economy import initial_gold
    return initial_gold(agent_id)


def _iso_game_now() -> str:
    from game.time_state import game_now_iso
    return game_now_iso()


def _ensure_player_fields(player: dict) -> None:
    """给旧版（检查点里）的 player dict 补齐新字段，幂等。"""
    defaults = _make_player(player["id"], player.get("name", player["id"]),
                            controller=player.get("controller", "human"))
    for k in ("fullness", "energy", "social", "fun", "mood", "mood_base", "emotion_tags",
              "closeness", "controller", "online", "away", "scene", "agent_id", "last_tick_ts", "pos_seq", "inventory", "gold"):
        if k not in player:
            player[k] = player.get("hp", defaults[k]) if k == "fullness" else defaults[k]
    if not isinstance(player["last_tick_ts"], str):          # W1 的 float → ISO
        from datetime import datetime
        from game.time_state import GAME_TZ
        player["last_tick_ts"] = datetime.fromtimestamp(float(player["last_tick_ts"]), GAME_TZ).isoformat(timespec="seconds")
    if not any(b.get("key") == "decay" for b in player.get("buffs", [])):
        player.setdefault("buffs", []).insert(0, dict(DECAY_BUFF))
    player["hp"] = player["fullness"]


# ── 玩家生命周期 ──────────────────────────────────────────────────────────────

def create_player(name: str, controller: str = "human", profile: dict | None = None) -> dict:
    """创建新玩家，生成唯一 ID，返回玩家数据的深拷贝。

    controller: "human" | "agent"（B6）；profile: {E, N, agent_id?}。
    agent 玩家会先从自我层 GET /self/state 种入七变量（不可达则用 §2.5 初值）。
    """
    safe = name[:12].lower().replace(" ", "_")
    suffix = f"{_id_rng.getrandbits(24):06x}" if _id_rng is not None else uuid.uuid4().hex[:6]
    player_id = f"{safe}_{suffix}"
    while player_id in _players:
        player_id = f"{safe}_{uuid.uuid4().hex[:6]}"
    player = _make_player(player_id, name, controller, profile)
    if player["controller"] == "agent":
        sp = spawn_point_for(player.get("agent_id"))
        player["position"] = {"x": sp["x"], "y": sp["y"]}; player["facing"] = sp["facing"]
        from game import self_sync
        self_sync.register(player_id, game_now_ts())
        self_sync.seed_player(player, game_now_ts())
    with STATE_LOCK:
        _players[player_id] = player
        from game import doors
        doors.issue_default_keys(player)                       # §3.41：按 owner / homes 发自家钥匙；人类控制者 1 把合租房钥匙
        _pending_messages[player_id] = None
        _use_start_times[player_id]  = None
        _last_seen[player_id]        = time.time()
        _last_used.setdefault(player_id, {})
        _use_history.setdefault(player_id, [])
        _last_input[player_id] = time.time()
    from game import state_log
    state_log.sample_now(player, "join")            # Q1：回放起点，消除 30 s 粒度歧义
    return copy.deepcopy(player)


def _position_valid(x: int, y: int) -> bool:
    """可走（或是某物品的使用者站位）且落在某个 arena 内（§3.14：换地图后旧坐标可能在墙里或在任何 arena 之外）。"""
    on_use_pos = any(any(s["x"] == x and s["y"] == y for s in (o.get("usePos") or [])) for o in _OBJECTS)
    return (is_tile_walkable(x, y) or on_use_pos) and _ZONE_LOOKUP.get((x, y), {}).get("arena") is not None


def _ensure_valid_position(player: dict) -> bool:
    """坐标非法 → 落回出生点并离开正在用的物品。返回是否重置。"""
    pos = player["position"]
    if _position_valid(pos["x"], pos["y"]):
        return False
    start = _META["player_start"]
    player["position"] = {"x": start["x"], "y": start["y"]}
    player["facing"] = start["facing"]
    if player.get("usingObjectId") is not None and player["id"] in _players:
        leave_object(player["id"])
    player["state"] = "idle" if player.get("state") in ("using", "walking", "walking_over") else player.get("state", "idle")
    player["stateLabel"] = None
    return True


def rejoin_player(player_id: str) -> dict | None:
    """B6：supervisor 重拉后用同一 player_id 续接。不存在返回 None。坐标非法落回出生点（§3.14）。"""
    with STATE_LOCK:
        player = _players.get(player_id)
        if player is None:
            return None
        player["online"] = True
        _ensure_valid_position(player)
        from game import state_log
        state_log.sample_now(player, "rejoin")
        _last_seen[player_id] = time.time()
        return copy.deepcopy(player)


def remove_player(player_id: str) -> None:
    """移除玩家，自动离开正在使用的对象并清理聊天室。"""
    with STATE_LOCK:
        if player_id not in _players:
            return
        # 先清理聊天室（必须在 _players 仍包含该 player 时执行，以便移除 buff）
        from game.chat_state import cleanup_player_chats
        cleanup_player_chats(player_id)
        leave_object(player_id)
        from game import doors
        if player_id in _players:
            doors.on_player_removed(_players[player_id])         # §3.41：钥匙回池
        _players.pop(player_id, None)
        _walks.pop(player_id, None)
        _pending_messages.pop(player_id, None)
        _use_start_times.pop(player_id, None)
        _last_seen.pop(player_id, None)
        _last_used.pop(player_id, None)
        _use_history.pop(player_id, None)
        _last_input.pop(player_id, None)
        _pre_use_pos.pop(player_id, None)
        _phone_feed.pop(player_id, None)
        _recent_events.pop(player_id, None)
    from game import self_sync
    self_sync.unregister(player_id)


def touch_player(player_id: str, human_only: bool = False) -> bool:
    """更新玩家心跳时间戳，表示该玩家仍在线。human_only=True 时 agent 不刷（E②：GET /player 对 agent 无副作用）。"""
    p = _players.get(player_id)
    if p is None:
        return False
    if human_only and p.get("controller") == "agent":
        return False
    _last_seen[player_id] = time.time()
    p["online"] = True
    mark_input(player_id)
    return True


def mark_input(player_id: str) -> None:
    """W8 Q0e：记录一次人类输入（动作 / 心跳 / 聊天），清 away。"""
    p = _players.get(player_id)
    if p is None:
        return
    _last_input[player_id] = time.time()
    if p.get("away"):
        p["away"] = False


def _update_away() -> None:
    """ticker 调：human 超过 AWAY_AFTER_S 无输入 → away=True。"""
    now = time.time()
    for pid, p in _players.items():
        if p.get("controller") == "agent":
            p["away"] = False
            continue
        last = _last_input.get(pid)
        p["away"] = bool(last is not None and now - last > AWAY_AFTER_S)


def is_present(player: dict) -> bool:
    """在场 = 在线且没 away（perceive / nearby / 邀请用）。"""
    return bool(player.get("online", True)) and not player.get("away", False)


def _cleanup_stale_players() -> None:
    """清除超过 _PLAYER_TIMEOUT 秒未心跳的玩家。由后台 ticker 调用（B8）。"""
    now = time.time()
    with STATE_LOCK:
        stale = [pid for pid, ts in _last_seen.items() if now - ts > _PLAYER_TIMEOUT]
        for pid in stale:
            p = _players.get(pid)
            if p is not None and p.get("controller") == "agent":
                p["online"] = False          # B6：她的身体留在原地，仍参与 tick
            else:
                remove_player(pid)


# ── 公开访问函数 ──────────────────────────────────────────────────────────────

def get_world() -> dict:
    """只读（B8）：时间推进、buff tick、stale 清理都在后台 ticker 里。"""
    from game.time_state import get_time_state
    world_state = get_time_state()
    world_state["weather"] = _WEATHER
    world_state["mapVersion"] = MAP_VERSION         # E③
    world_state["town"] = TOWN                      # W7 E：多镇代理
    gts = game_now_ts()
    return {
        "tiles":      _TILES,
        "objects":    [_object_view(o, gts) for o in _OBJECTS],
        "worldState": world_state,
        "players":    get_all_players_snapshot(),
        "tiled":      _MAP_DATA.get("tiled"),
        "zone_names": _MAP_DATA.get("zone_names", {}),   # W7 E：区域中文名，只读
        "map": map_graph_summary(),                      # W9：v2 的 edges / floors / access（v1 地图为空）
        "decor": _MAP_DATA.get("decor", []),             # W10：装饰层（小径 / 池塘 / 晾衣绳 / 花坛），不可交互
    }


def get_player(player_id: str) -> dict | None:
    player = _players.get(player_id)
    if player is None:
        return None
    data = copy.deepcopy(player)
    data["hp"] = data.get("fullness", data.get("hp"))  # 别名兜底
    from game.inventory import view as _inv_view
    data["inventory"] = _inv_view(player)             # W10 ④：[{type, name, class, count, meta?}]
    data["gold"] = int(player.get("gold", 0))
    data["walk"] = walk_view(player_id)                # §3.36：走路中 {remaining, path_len, eta_game_s, target, next, started_at}，否则 null
    from game import doors
    data["door_request"] = doors.visitor_view(player_id)      # §3.40：我最近一次敲门 {id, home, status: pending|accepted|declined|no_answer, expires_at…}
    data["pending_knocks"] = doors.pending_for_owner(player)  # §3.40：我家待回应的敲门 [{id, visitor, visitor_name, home, door, expires_at}]
    data["keys"] = doors.keys_of(player)                      # §3.41：持有的钥匙 [{door_id, name}]（也在 inventory 里，type key）
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
            "controller": p.get("controller", "human"),
            "online":     p.get("online", True),
            "away":       p.get("away", False),       # W8 Q0e
            "agent_id":   p.get("agent_id"),          # §3.11 A1：自我层 agent↔player 映射
            "stateLabel":    p.get("stateLabel"),      # E①
            "usingObjectId": p.get("usingObjectId"),   # E①
            "tags":          list(p.get("tags", [])),  # E①
            "pos_seq":       p.get("pos_seq", 0),      # E⑥：位置单调序号
            "gold":          int(p.get("gold", 0)),    # W10 ④
            "inventory":     _inv_view_safe(p),        # W10 ④：[{type, name, class, count}]
        }
        for p in _players.values()
    ]


def _inv_view_safe(p: dict) -> list[dict]:
    from game.inventory import view
    return view(p)


# ── B20：作息与营业时间 ───────────────────────────────────────────────────────

def _hm(s: str) -> int:
    h, m = s.split(":"); return int(h) * 60 + int(m)


def open_state(obj: dict, game_ts: float | None = None) -> tuple[bool, str | None]:
    """返回 (是否营业, 下次开门 "HH:MM" 或 None)。没有 openHours 的物品恒开。"""
    hours = obj.get("openHours")
    if not hours:
        return True, None
    from datetime import datetime
    from game.time_state import GAME_TZ
    ts = game_ts if game_ts is not None else game_now_ts()
    dt = datetime.fromtimestamp(ts, GAME_TZ)
    now_m = dt.hour * 60 + dt.minute
    spans = sorted((_hm(a), _hm(b)) for a, b in hours)
    for a, b in spans:
        if a <= now_m < b:
            return True, None
    nxt = next((a for a, _ in spans if a > now_m), spans[0][0])
    return False, f"{nxt // 60:02d}:{nxt % 60:02d}"


def _object_view(obj: dict, game_ts: float) -> dict:
    """GET /world 的物品视图：加 open / opensAt，关门时 advertise 全 0。"""
    is_open, opens_at = open_state(obj, game_ts)
    view = dict(obj)
    view["open"] = is_open
    view["opensAt"] = opens_at
    if not is_open and obj.get("advertise"):
        view["advertise"] = {k: 0 for k in obj["advertise"]}
    return view


def _kick_closed_objects() -> None:
    """营业结束：还在用的 player 自动离开（ticker 调）。"""
    gts = game_now_ts()
    for o in _OBJECTS:
        if not o.get("openHours") or not o["userList"]:
            continue
        if open_state(o, gts)[0]:
            continue
        for pid in list(o["userList"]):
            left = leave_object(pid)
            if left and pid in _pending_messages:
                _pending_messages[pid] = left.get("leaveMessage") or "营业结束了。"


# ── B5：冷却与使用计数 ────────────────────────────────────────────────────────

def object_cooldown_s(obj: dict) -> float:
    """类型级冷却：object_types.json 的 cooldown_s，缺省 OBJECT_COOLDOWN_S；床类为 0（W8 Q0e）。"""
    t = OBJECT_TYPES.get(obj.get("type"), {})
    return float(t.get("cooldown_s", OBJECT_COOLDOWN_S))


def object_cooldown_remaining(entity_id: str, obj_id: str) -> float:
    """同一物品冷却（默认 30 游戏分钟，床类 0）：返回剩余游戏秒，0 表示可用。"""
    last = _last_used.get(entity_id, {}).get(obj_id)
    if last is None:
        return 0.0
    obj = get_object_by_id(obj_id)
    cd = object_cooldown_s(obj) if obj else OBJECT_COOLDOWN_S
    return max(0.0, cd - (game_now_ts() - last))


def record_object_use(entity_id: str, obj_id: str) -> None:
    now = game_now_ts()
    _last_used.setdefault(entity_id, {})[obj_id] = now
    hist = _use_history.setdefault(entity_id, [])
    hist.append((now, obj_id))
    cutoff = now - RECENT_USES_WINDOW_S
    _use_history[entity_id] = [(t, o) for t, o in hist if t >= cutoff]


def set_phone_feed(entity_id: str, digest: dict) -> None:
    _phone_feed[entity_id] = digest


def get_phone_feed(entity_id: str) -> dict | None:
    return _phone_feed.get(entity_id)


def get_recent_uses(entity_id: str) -> dict[str, int]:
    """6 游戏小时内各物品使用次数（供 novelty 折减）。"""
    now = game_now_ts()
    cutoff = now - RECENT_USES_WINDOW_S
    counts: dict[str, int] = {}
    for t, o in _use_history.get(entity_id, []):
        if t >= cutoff:
            counts[o] = counts.get(o, 0) + 1
    return counts


def is_tile_walkable(x: int, y: int) -> bool:
    tile = _TILE_LOOKUP.get((x, y))
    return tile is not None and tile["walkable"]


# ── 地图 v2：边 / 楼层 / 访问规则（W9） ───────────────────────────────────────

def arena_floor(arena: str | None) -> int:
    return _FLOORS.get(arena or "", 1)


def _hours_state(hours: list | None, game_ts: float) -> tuple[bool, str | None]:
    """复用营业时间逻辑：返回 (在时段内, 下一次进入时段 'HH:MM')。"""
    if not hours:
        return True, None
    return open_state({"openHours": hours}, game_ts)


def _mover_ids(mover: dict | None) -> set[str]:
    if not mover:
        return set()
    return {x for x in (mover.get("agent_id"), mover.get("name"), mover.get("id")) if x}


def _allowed(allow: list | None, mover: dict | None, owners: list | None = None) -> bool:
    """allow 为空 = 所有人；含 "owner" 时按 owners 判；否则按 agent_id / name / id 匹配。"""
    if not allow:
        return True
    ids = _mover_ids(mover)
    for a in allow:
        if a == "*" or a == "all":
            return True
        if a == "human" and mover is not None and mover.get("controller", "human") == "human":   # §3.39 ①：人类控制者（操控页演阿蝉）
            return True
        if a == "owner" and owners and ids & set(owners):
            return True
        if a in ids:
            return True
    return False


def _edge_owners(edge: dict) -> set[str]:
    """§3.38：边的主人 = edge.owner ∪ 内侧（b）场所的 access.owner ∪ homes 里家在 b 场所的人。"""
    owners = set(edge.get("owner") or [])
    b_arena = (edge.get("b") or {}).get("arena")
    if b_arena:
        owners |= set((_ACCESS.get(b_arena) or {}).get("owner") or [])
        owners |= {aid for aid, ar in _HOMES.items() if ar == b_arena}
    return owners


def edge_block(edge: dict, mover: dict | None, game_ts: float, frm: tuple[int, int] | None = None) -> tuple[str, str | None] | None:
    """这条边此刻对 mover 是否不可过：None=可过；否则 ("closed"|"locked", opens_at)。
    §3.38：只管「进」（a→b），从内侧 b 出去任何人任何时候放行。
    §3.41（主播 11-08 定）：带 owner 的门默认锁——门敞开窗口内 ‖ 商店 open_hours 内 ‖ 持该门钥匙 → 过；其余 locked（商店打烊 → closed + opens_at）。
    不带 owner 的边（校门 / 校园楼门 / 楼梯）只看 open_hours 与 allow。frm = 出发格，None 当作「进」。"""
    from game import doors
    b_tile = ((edge.get("b") or {}).get("x"), (edge.get("b") or {}).get("y"))
    if frm is not None and tuple(frm) == b_tile:
        return None                                              # 出：总是放行
    is_open, opens_at = _hours_state(edge.get("open_hours"), game_ts)
    if doors.is_keyed(edge):
        if doors.is_open_window(edge["id"], game_ts):
            return None                                          # 有人从里面开了门
        if edge.get("open_hours") and is_open:
            return None                                          # 商店营业中
        if mover is not None and doors.holds_key(mover, edge["id"]):
            return None                                          # 持钥匙
        return ("closed", opens_at) if edge.get("open_hours") else ("locked", None)
    if not is_open:
        return ("closed", opens_at)
    if not _allowed(edge.get("allow"), mover, sorted(_edge_owners(edge))):
        return ("locked", None)
    return None


def arena_block(arena: str | None, mover: dict | None, game_ts: float) -> tuple[str, str | None] | None:
    """进入某场所此刻是否被访问规则挡住：None=可进；否则 ("locked", opens_at)。"""
    acc = _ACCESS.get(arena or "")
    if not acc:
        return None
    owners = acc.get("owner") or []
    if _mover_ids(mover) & set(owners):
        return None
    locked_spans = acc.get("locked")
    if locked_spans == "always" or locked_spans is True:
        ok = bool(acc.get("allow_when_locked")) and _allowed(acc.get("allow_when_locked"), mover, owners)
        return None if ok else ("locked", None)
    if not locked_spans:
        return None
    in_locked, _ = _hours_state(locked_spans, game_ts)
    if not in_locked:
        return None
    if acc.get("allow_when_locked") and _allowed(acc.get("allow_when_locked"), mover, owners):   # 空 = 锁定时谁也不能进（owner 除外）
        return None
    # 解锁时刻 = 当前锁定段的结束
    from datetime import datetime
    from game.time_state import GAME_TZ
    dt = datetime.fromtimestamp(game_ts, GAME_TZ); now_m = dt.hour * 60 + dt.minute
    for a, b in locked_spans:
        am, bm = _hm(a), _hm(b)
        if am <= now_m < bm:
            return ("locked", f"{bm // 60:02d}:{bm % 60:02d}")
    return ("locked", None)


def arena_cross_block(t1: tuple[int, int], t2: tuple[int, int], mover: dict | None, game_ts: float) -> tuple[str, str | None] | None:
    """跨场所（t1 的 arena → t2 的 arena）按目标场所访问规则判。
    §3.38 / §3.39「出门永远放行」的室内推广：mover 站在一个自己**本就不被允许**的场所里（闯入者 / 旧世界遗留），
    往同一 sector 的相邻场所走一律放行（这是在往外走），否则会被锁在屋里；出了门就回不来。"""
    a1 = _ZONE_LOOKUP.get(t1, {}).get("arena"); a2 = _ZONE_LOOKUP.get(t2, {}).get("arena")
    if a2 is None or a2 == a1:
        return None
    blk = arena_block(a2, mover, game_ts)
    if blk is None:
        return None
    s1 = _ZONE_LOOKUP.get(t1, {}).get("sector"); s2 = _ZONE_LOOKUP.get(t2, {}).get("sector")
    if a1 is not None and s1 == s2 and arena_block(a1, mover, game_ts) is not None:
        return None
    return blk


def crossing_block(t1: tuple[int, int], t2: tuple[int, int], mover: dict | None, game_ts: float) -> tuple[str, str | None] | None:
    """从 t1 走到 t2：相邻两格之间若有边按边判（有向，只判进）；跨场所再按目标场所访问规则判（含「往外走放行」）。"""
    e = _EDGE_BY_PAIR.get(frozenset((t1, t2)))
    if e is not None:
        b = edge_block(e, mover, game_ts, frm=t1)                # §3.38：有向——只判「进」
        if b:
            return b
    return arena_cross_block(t1, t2, mover, game_ts)


def neighbors(x: int, y: int, mover: dict | None = None, game_ts: float | None = None, ignore_locks: bool = False):
    """BFS 邻接：四邻可走格 + 楼梯边；返回 [(tile, block)]，block 为 None 或 (reason, opens_at)。"""
    ts = game_ts if game_ts is not None else game_now_ts()
    out = []
    for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        n = (x + dx, y + dy)
        if not is_tile_walkable(*n):
            continue
        blk = None if ignore_locks else crossing_block((x, y), n, mover, ts)
        out.append((n, blk))
    for n, e in _STAIRS.get((x, y), []):
        if not is_tile_walkable(*n):
            continue
        blk = None
        if not ignore_locks:
            blk = edge_block(e, mover, ts, frm=(x, y)) or arena_cross_block((x, y), n, mover, ts)
        out.append((n, blk))
    return out


def bfs_path(start: tuple[int, int], goals: set[tuple[int, int]], mover: dict | None = None,
             ignore_locks: bool = False) -> list[tuple[int, int]] | None:
    """走 edges 的 BFS：到 goals 中最近一格；已在 goals 内返回 []；不可达 None。"""
    from collections import deque
    if start in goals:
        return []
    ts = game_now_ts()
    q = deque([start]); parent = {start: None}
    while q:
        cur = q.popleft()
        for n, blk in neighbors(cur[0], cur[1], mover, ts, ignore_locks):
            if n in parent or blk is not None:
                continue
            parent[n] = cur
            if n in goals:
                path = [n]
                while parent[path[-1]] != start:
                    path.append(parent[path[-1]])
                return list(reversed(path))
            q.append(n)
    return None


def first_block_on_path(start: tuple[int, int], path: list[tuple[int, int]], mover: dict | None) -> tuple[str, str | None] | None:
    """沿路径找第一个被挡的穿越（给 locked / closed 的 reason 与 opens_at）。"""
    ts = game_now_ts()
    prev = start
    for n in path:
        blk = crossing_block(prev, n, mover, ts)
        if blk is None and abs(prev[0] - n[0]) + abs(prev[1] - n[1]) != 1:
            for m, e in _STAIRS.get(prev, []):
                if m == n:
                    blk = edge_block(e, mover, ts, frm=prev) or arena_cross_block(prev, n, mover, ts)
        if blk is not None:
            return blk
        prev = n
    return None


def door_states() -> list[dict]:
    """§3.41：带 owner 的门此刻状态（E 画锁 / 开）。"""
    from game import doors
    gts = game_now_ts()
    out = []
    for e in _EDGES:
        if not doors.is_keyed(e):
            continue
        is_open, opens_at = _hours_state(e.get("open_hours"), gts)
        out.append({"door_id": e["id"], "name": e.get("name"), "x": e["a"]["x"], "y": e["a"]["y"],
                    "open": doors.is_open_window(e["id"], gts) or bool(e.get("open_hours") and is_open),
                    "open_until": next((o["open_until"] for o in doors.open_doors_view() if o["door_id"] == e["id"]), None),
                    "keys": int(e.get("keys") or len(e.get("owner") or [])), "owners": list(e.get("owner") or [])})
    return out


def map_graph_summary() -> dict:
    """GET /world 的 v2 附加信息。"""
    return {"format": MAP_FORMAT, "edges": _EDGES, "floors": _FLOORS, "access": _ACCESS, "doors": door_states()}   # §3.41：门此刻开 / 锁


def update_player_facing(player_id: str, facing: str) -> None:
    if player_id in _players:
        _players[player_id]["facing"] = facing


# ── §3.36 走路：有路才动、按固定速度花游戏时间（主播 11-07 20:55 定） ──────────────────
WALK_TILE_SEC = float(os.environ.get("SANDBOX_WALK_TILE_SEC", "1.0"))     # 每格游戏秒（towns.yaml sandbox_env 可覆盖）
_walks: dict[str, dict] = {}        # pid -> {path:[(x,y)...], i, next_gts, started_gts, path_len, action, target, start}
_walk_log_enabled = True            # 回放时关掉（move_done 行不能写回正在重放的日志）


def start_walk(player_id: str, path: list[tuple[int, int]], action: str, target: dict | None = None) -> dict:
    """路径入队，state=walking；返回 {path_len, eta_game_s}。空路径 = 原地，不入队。调用方持 STATE_LOCK。"""
    p = _players[player_id]
    old = _walks.pop(player_id, None)
    if old is not None:
        _finish_walk(player_id, old, "stopped", "replaced", log=True)
    if not path:
        return {"path_len": 0, "eta_game_s": 0.0}
    gts = game_now_ts()
    _walks[player_id] = {"path": [tuple(t) for t in path], "i": 0, "next_gts": gts + WALK_TILE_SEC, "started_gts": gts,
                         "path_len": len(path), "action": action, "target": target,
                         "start": {"x": p["position"]["x"], "y": p["position"]["y"]}}
    p["state"] = "walking"
    return {"path_len": len(path), "eta_game_s": round(len(path) * WALK_TILE_SEC, 3)}


def walk_view(player_id: str) -> dict | None:
    w = _walks.get(player_id)
    if w is None:
        return None
    remaining = w["path_len"] - w["i"]
    return {"remaining": remaining, "path_len": w["path_len"], "eta_game_s": round(remaining * WALK_TILE_SEC, 3),
            "target": w.get("target"), "action": w["action"], "next": {"x": w["path"][w["i"]][0], "y": w["path"][w["i"]][1]} if remaining else None,
            "started_at": _iso_from_ts(w["started_gts"])}


def _iso_from_ts(ts: float) -> str:
    from game.time_state import _game_dt
    return _game_dt(ts).isoformat(timespec="seconds")


def _finish_walk(player_id: str, w: dict, outcome: str, reason: str | None, *, log: bool = True) -> dict:
    p = _players.get(player_id)
    gts = game_now_ts()
    row = {"outcome": outcome, "reason": reason, "position": dict(p["position"]) if p else None,
           "path_len": w["path_len"], "steps_done": w["i"], "game_s": round(gts - w["started_gts"], 3),
           "action": w["action"], "target": w.get("target"), "start": w.get("start")}
    if p is not None and p["state"] == "walking":
        p["state"] = "idle"
    if log and _walk_log_enabled:
        try:
            from game.action_log import append_log
            append_log(player_id, "move_done", row, success=(outcome == "arrived"), reason=None if outcome == "arrived" else reason)
        except Exception:
            pass
        try:
            from routers.ws import hub
            hub.push_action(player_id, "move_done", outcome == "arrived", reason=None if outcome == "arrived" else reason,
                            extra={"position": row["position"], "outcome": outcome, "path_len": w["path_len"], "steps_done": w["i"], "game_s": row["game_s"]})
        except Exception:
            pass
    return row


def stop_walk(player_id: str, outcome: str = "stopped", reason: str | None = None) -> dict | None:
    """就地停下（聊天接受 / leave / teleport / 新 move 替换）。没在走返回 None。调用方持 STATE_LOCK。"""
    w = _walks.pop(player_id, None)
    if w is None:
        return None
    return _finish_walk(player_id, w, outcome, reason)


def walk_tick(gts: float) -> int:
    """ticker 每 tick 调：到点就走一格；门锁 / 时段 / 不可走 / canMove=false → blocked；状态被别人改了（聊天 / use）→ stopped。返回推进的格数。"""
    moved = 0
    for pid, w in list(_walks.items()):
        p = _players.get(pid)
        if p is None:
            _walks.pop(pid, None); continue
        if p["state"] != "walking":                                   # 聊天接受（walking_over）/ use / talking 等改了状态 → 就地停
            _walks.pop(pid, None); _finish_walk(pid, w, "stopped", f"state:{p['state']}"); continue
        while gts >= w["next_gts"] and w["i"] < w["path_len"]:
            if not p.get("canMove", True):
                _walks.pop(pid, None); _finish_walk(pid, w, "blocked", "move_disabled"); break
            cur = (p["position"]["x"], p["position"]["y"]); nxt = w["path"][w["i"]]
            blk = None
            if not is_tile_walkable(*nxt):
                blk = ("tile_not_walkable", None)
            else:
                blk = crossing_block(cur, nxt, p, gts)
                if blk is None and abs(cur[0] - nxt[0]) + abs(cur[1] - nxt[1]) != 1:        # 楼梯
                    for m, e in _STAIRS.get(cur, []):
                        if m == nxt:
                            blk = edge_block(e, p, gts, frm=cur) or arena_cross_block(cur, nxt, p, gts)
            if blk is not None:
                _walks.pop(pid, None)
                row = _finish_walk(pid, w, "blocked", blk[0])
                row["opens_at"] = blk[1]
                break
            dx, dy = nxt[0] - cur[0], nxt[1] - cur[1]
            facing = ("left" if dx < 0 else "right") if abs(dx) >= abs(dy) and dx != 0 else ("up" if dy < 0 else "down")
            update_player_position(pid, nxt[0], nxt[1], facing)
            p["state"] = "walking"
            from game import doors
            doors.on_cross(pid, cur, nxt, gts)                   # §3.41：敞开窗口内进门的访客 → 敲门 opened
            w["i"] += 1; w["next_gts"] += WALK_TILE_SEC; moved += 1
            if w["i"] >= w["path_len"]:
                _walks.pop(pid, None); _finish_walk(pid, w, "arrived", None); break
    return moved


def update_player_position(player_id: str, x: int, y: int, facing: str) -> None:
    player = _players.get(player_id)
    if player is None:
        return
    if player["position"]["x"] != x or player["position"]["y"] != y:
        player["pos_seq"] = int(player.get("pos_seq", 0)) + 1      # E⑥
    player["position"]["x"] = x
    player["position"]["y"] = y
    player["facing"] = facing
    if player["state"] not in ("using", "walking_over", "talking"):   # walking_over 期间移动不改状态（B9）
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
    _use_start_game_ts[entity_id] = game_now_ts()
    _move_to_use_pos(player, obj)             # W10：坐进去 / 躺上去

    # continuous 物品：buff（persistent 到 leave 为止 / timed）、tag、以及进入时的一次性 instant_effect
    apply_effects(player, obj["effects"], source=obj_id)
    apply_control_flags(player)           # Q0c：no_move 等立刻生效，不等下一 tick
    if "live" in {e.get("key") for e in obj["effects"] if e.get("type") == "external"}:
        player["scene"] = "live"          # B11：直播中按 live 速率衰减


def apply_instant_object(obj_id: str, entity_id: str) -> None:
    player = _players.get(entity_id)
    if player is None:
        return
    obj = get_object_by_id(obj_id)
    if obj is None:
        return
    # instant 物品：instant_effect + timed buff + 一次性效果；persistent buff 与 tag 不挂（没有 leave 时机）
    apply_effects(player, [e for e in obj["effects"] if e.get("type") != "tag"],
                  source=obj_id, allow_persistent=False)


def apply_var_delta(player: dict, key: str, value: float) -> None:
    """给 player 的某个需求变量加 value 并 clamp 到 0–100。"""
    add_var(player, key, float(value))


_ONE_SHOT_KEYS = {"emotion_tag", "closeness_delta"}


def apply_effects(
    player: dict,
    effects: list[dict],
    source: str,
    scene: str | None = None,
    allow_persistent: bool = True,
    track: bool = True,
) -> dict:
    """
    与 object_types.json 同格式的 effect 列表落到 player（B4 / B5 / B13 共用管线）：
      {"type":"instant_effect","key":<var>,"value":v}                 立即 clamp 加
      {"type":"<var>_delta","value":v} / {"type":"buff","key":"<var>_delta"}   立即加
      {"type":"buff","key":"<var>_regen"|"no_move"|…,"mode":"persistent"|"timed","duration":ms}
      {"type":"buff"|"emotion_tag","key":"emotion_tag","tag":"smug","duration":ms}   进 emotion_tags
      {"type":"closeness_delta","target":id,"value":v}                 closeness[target] += v
      {"type":"tag","key":"sleeping"}                                  纯标记
    scene 非空时切换 player.scene（决定衰减速率）。返回摘要 {"applied": n, "skipped": n}。
    track=False（source="self"，§3.9 第 4 条）：需求值变化落本地但不进自我层 vars_delta。
    `external` 类效果由 external_effects 处理，这里跳过不计数。
    """
    from game.buff_tick import canonical_var, NEED_VARS as _VARS
    applied = skipped = 0
    if scene in ("sandbox", "live"):
        player["scene"] = scene
    for e in effects:
        etype = e.get("type")
        key   = e.get("key", "")
        value = float(e.get("value", 0.0) or 0.0)
        # 把 "<var>_delta" / "closeness_delta" / "emotion_tag" 作为 type 的写法归一成 buff 写法
        if etype in _ONE_SHOT_KEYS or (etype and etype.endswith("_delta") and canonical_var(etype[:-6])):
            key, etype = etype, "buff"
        if etype == "external":
            continue
        if etype == "instant_effect":
            if canonical_var(key) is None:
                skipped += 1; continue
            add_var(player, key, value, track=track); applied += 1
        elif etype == "tag":
            if key and key not in player["tags"]:
                player["tags"].append(key)
            applied += 1
        elif etype == "buff":
            if key == "emotion_tag":
                tag = e.get("tag") or e.get("value_str") or source
                duration = float(e.get("duration", 0.0) or 0.0)
                player["emotion_tags"] = [t for t in player.get("emotion_tags", []) if t["key"] != tag]
                player["emotion_tags"].append({"key": tag, "value": value, "mode": "timed",
                                               "remaining": duration if duration > 0 else None, "source": source})
                applied += 1
            elif key == "closeness_delta":
                target = e.get("target")
                if not target:
                    skipped += 1; continue
                add_closeness(player, str(target), value); applied += 1
            elif key.endswith("_delta") and canonical_var(key[:-6]):
                add_var(player, key[:-6], value, track=track); applied += 1
            else:
                mode = e.get("mode", "persistent")
                if mode == "persistent" and not allow_persistent:
                    skipped += 1; continue
                new_buff = {
                    "key":       key,
                    "value":     value,
                    "mode":      mode,
                    "remaining": None if mode == "persistent" else float(e.get("duration", 0.0) or 0.0),
                    "source":    source,
                }
                for extra in ("target", "tag"):
                    if extra in e:
                        new_buff[extra] = e[extra]
                player["buffs"] = [
                    b for b in player["buffs"]
                    if not (b["source"] == source and b["key"] == key)
                ]
                player["buffs"].append(new_buff)
                applied += 1
        else:
            skipped += 1
    return {"applied": applied, "skipped": skipped}


_RECENT_EVENTS_MAX = 50
_recent_events: dict[str, list[dict]] = {}     # entity -> 最近 /effects 推送（event / source / 时间）


def get_recent_events(entity_id: str) -> list[dict]:
    return list(_recent_events.get(entity_id, []))


def apply_effects_to_player(entity_id: str, effects: list[dict], scene: str | None,
                            source: str = "effects", event: str | None = None) -> dict | None:
    """B13：POST /player/{id}/effects 入口。返回 player 副本或 None。event（§3.11 A2）只记录，供两边日志对账。"""
    with STATE_LOCK:
        player = _players.get(entity_id)
        if player is None:
            return None
        from game.time_state import game_now_iso
        buf = _recent_events.setdefault(entity_id, [])
        buf.append({"event": event, "source": source, "scene": scene, "n_effects": len(effects), "game_time": game_now_iso()})
        if len(buf) > _RECENT_EVENTS_MAX:
            del buf[: len(buf) - _RECENT_EVENTS_MAX]
        from game import external_log
        external_log.log("effects_push", entity_id, source=source, event=event, scene=scene, effects=effects)
        # §3.9 第 4 条：自我层回推（source="self"）的变化不再上报，否则会被加两遍
        summary = apply_effects(player, effects, source=source, scene=scene, track=(source != "self"))
        apply_control_flags(player)
        return {"summary": summary, "player": copy.deepcopy(player)}


_pre_use_pos: dict[str, dict] = {}        # entity -> use 前的 {x, y, facing}（leave 时回去）
_use_start_game_ts: dict[str, float] = {}  # entity -> use 开始的游戏时刻（W11：compose / make_video 的时长门槛）


def use_elapsed_game_s(entity_id: str) -> float:
    t0 = _use_start_game_ts.get(entity_id)
    return 0.0 if t0 is None else max(0.0, game_now_ts() - t0)


def _facing_toward(fx: int, fy: int, obj: dict) -> str:
    """站位朝物品中心的方向。"""
    cx = sum(t["x"] for t in obj["tiles"]) / len(obj["tiles"]); cy = sum(t["y"] for t in obj["tiles"]) / len(obj["tiles"])
    dx, dy = cx - fx, cy - fy
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return "down"
    return ("left" if dx < 0 else "right") if abs(dx) > abs(dy) else ("up" if dy < 0 else "down")


def _move_to_use_pos(player: dict, obj: dict) -> None:
    """按物品 usePos 给使用者一个格（按使用顺序，已被占的跳过）；没有 usePos 的物品原地不动。"""
    spots = obj.get("usePos") or []
    if not spots:
        return
    taken = {(_players[u]["position"]["x"], _players[u]["position"]["y"]) for u in obj["userList"] if u != player["id"] and u in _players}
    spot = next((s for s in spots if (s["x"], s["y"]) not in taken), spots[-1])
    _pre_use_pos[player["id"]] = {"x": player["position"]["x"], "y": player["position"]["y"], "facing": player["facing"]}
    player["position"] = {"x": spot["x"], "y": spot["y"]}
    player["pos_seq"] = int(player.get("pos_seq", 0)) + 1
    player["facing"] = obj.get("useFacing") or _facing_toward(spot["x"], spot["y"], obj)


def _restore_pre_use_pos(player: dict) -> None:
    pre = _pre_use_pos.pop(player["id"], None)
    x, y = player["position"]["x"], player["position"]["y"]
    if pre is None:
        if not is_tile_walkable(x, y):                # 没记录（旧检查点）且站在物品格上 → 挪到相邻可走格
            for dx, dy in ((0, 1), (0, -1), (-1, 0), (1, 0)):
                if is_tile_walkable(x + dx, y + dy):
                    player["position"] = {"x": x + dx, "y": y + dy}
                    player["pos_seq"] = int(player.get("pos_seq", 0)) + 1
                    break
        return
    if (player["position"]["x"], player["position"]["y"]) != (pre["x"], pre["y"]) and is_tile_walkable(pre["x"], pre["y"]):
        player["position"] = {"x": pre["x"], "y": pre["y"]}
        player["pos_seq"] = int(player.get("pos_seq", 0)) + 1
    player["facing"] = pre["facing"]


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
    apply_control_flags(player)           # Q0c：leave 同一秒内即可 move（基线里四段寻路都卡在这）
    if obj:
        obj_tags = {e["key"] for e in obj["effects"] if e["type"] == "tag"}
        player["tags"] = [t for t in player["tags"] if t not in obj_tags]

    from game import production
    production.on_leave(player)           # W11：钓位 / 灶台状态清掉
    _use_start_game_ts.pop(entity_id, None)
    if obj and "live" in {e.get("key") for e in obj["effects"] if e.get("type") == "external"}:
        player["scene"] = "sandbox"       # B11：下播
        from game import external_effects, economy
        from game.time_state import game_now_iso
        external_effects.live_stop(player, game_now_iso())
        economy.synthetic_stream_income(player, obj_id)    # W11 ②：直播机未接前按 synthetic 入账
    if obj and "game" in {e.get("key") for e in obj["effects"] if e.get("type") == "external"}:
        from game import external_effects, external_log
        from game.time_state import game_now_iso
        external_effects.game_end(player, game_now_iso())        # B18 / W10-4b：POST /game/stop（不关服）
        g = player.get("game") or {}
        player["game"] = {**g, "status": "ended", "ended_at": game_now_iso(), "text": None,
                          "left_at_day": g.get("day"), "duration_s": None}
        if g.get("started_at"):
            try:
                from datetime import datetime as _dt
                player["game"]["duration_s"] = round((_dt.fromisoformat(game_now_iso()) - _dt.fromisoformat(g["started_at"])).total_seconds(), 1)
            except Exception:
                pass
        external_log.log("game", entity_id, object=obj_id, action="stop", left_at_day=g.get("day"), run_id=g.get("run_id"),
                         duration_s=player["game"]["duration_s"])

    player["state"]         = "idle"
    player["stateLabel"]    = None
    player["usingObjectId"] = None
    _use_start_times[entity_id] = None
    _restore_pre_use_pos(player)              # W10：回到 use 前站的格
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
    """
    动态从 map.json 构建语义树（worlds → sectors → arenas）。
    名称来自 zone_names 字段，缺失时 fallback 到 ID 本身。
    不再依赖 cognitive_map.py。
    """
    zone_names = _MAP_DATA.get("zone_names", {})

    def _name(layer: str, zone_id: str) -> str:
        return zone_names.get(layer, {}).get(zone_id, zone_id)

    world_to_sectors: dict[str, set] = {}
    sector_to_arenas: dict[str, set] = {}

    for wr, sr, ar in zip(_WORLD_ROWS, _SECTOR_ROWS, _ARENA_ROWS):
        for wc, sc, ac in zip(wr, sr, ar):
            world_id  = _ZONE_CHARS["world"].get(wc)
            sector_id = _ZONE_CHARS["sector"].get(sc)
            arena_id  = _ZONE_CHARS["arena"].get(ac)
            if world_id:
                world_to_sectors.setdefault(world_id, set())
                if sector_id:
                    world_to_sectors[world_id].add(sector_id)
            if sector_id:
                sector_to_arenas.setdefault(sector_id, set())
                if arena_id:
                    sector_to_arenas[sector_id].add(arena_id)

    worlds = []
    for world_id, sector_ids in world_to_sectors.items():
        sectors = []
        for sector_id in sorted(sector_ids):
            arena_ids = sector_to_arenas.get(sector_id, set())
            arenas = [
                {"id": aid, "name": _name("arena", aid), "floor": arena_floor(aid)}
                for aid in sorted(arena_ids)
            ]
            sectors.append({
                "id":     sector_id,
                "name":   _name("sector", sector_id),
                "arenas": arenas,
            })
        worlds.append({
            "id":      world_id,
            "name":    _name("world", world_id),
            "sectors": sectors,
        })

    return {"worlds": worlds}


def get_player_buffs(player_id: str) -> list:
    player = _players.get(player_id)
    if player is None:
        return []
    return copy.deepcopy(player["buffs"])


def clear_player_buffs(player_id: str) -> int:
    player = _players.get(player_id)
    if player is None:
        return 0
    kept = [b for b in player["buffs"] if b.get("source") == "decay"]
    count = len(player["buffs"]) - len(kept)
    player["buffs"] = kept
    apply_control_flags(player)
    return count


def force_reset_player_state(entity_id: str) -> dict:
    player = _players.get(entity_id)
    if player is None:
        return {"left_object": None, "cleared_buffs": 0}

    left_obj_id = None
    if player.get("usingObjectId"):
        obj = leave_object(entity_id)
        left_obj_id = obj["id"] if obj else None

    kept = [b for b in player["buffs"] if b.get("source") == "decay"]
    cleared_buffs = len(player["buffs"]) - len(kept)
    player["buffs"]         = kept
    apply_control_flags(player)
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
    from game import self_sync
    gts = game_now_ts()
    with STATE_LOCK:
        for player_id in list(_players.keys()):
            player = _players.get(player_id)
            if player is None:
                continue
            run_tick(player, delta, game_ts=gts)
            _check_auto_leave(player_id)
        walk_tick(gts)                                  # §3.36：按 1 格 / 游戏秒逐格推进
        self_sync.on_tick(gts, _players)
        from game import economy, production, commissions, qq
        economy.on_tick(gts, _players)                  # W10 ④：日薪 / 时薪按日程结算
        if economy.restock_tick(gts, _OBJECTS):         # W11 ④：商店 / 冰箱每日补货
            refresh_shop_views()
        production.on_tick(gts, _players)               # W11 ①：钓位出鱼、灶台出便当
        commissions.on_tick(gts)                        # W11 ①：每日委托
        qq.on_tick(gts, _players)                       # W11 ③：未读消息的亲密度惩罚
        from game import doors
        doors.on_tick(gts, _players)                    # §3.40：敲门超时 / 通行证失效
        update_weather(gts)
        _kick_closed_objects()
        from game import state_log
        from game.time_state import game_now_iso
        state_log.on_tick(gts, game_now_iso(), _players)


# ── 持久化：导出 / 回填（B2） ─────────────────────────────────────────────────

def export_runtime() -> dict:
    """导出 players（含 pending/use_start/last_seen 侧车）与 object 运行时字段。"""
    with STATE_LOCK:
        players = {
            pid: {
                "player":          copy.deepcopy(p),
                "pending_message": _pending_messages.get(pid),
                "use_start_time":  _use_start_times.get(pid),
                "last_seen":       _last_seen.get(pid),
                "last_used":       dict(_last_used.get(pid, {})),
                "use_history":     [list(x) for x in _use_history.get(pid, [])],
                "pre_use_pos":     _pre_use_pos.get(pid),            # W10：use 前站位
            }
            for pid, p in _players.items()
        }
        objects = {
            o["id"]: {"currentUsers": o["currentUsers"], "userList": list(o["userList"]), "stock": o.get("stock")}
            for o in _OBJECTS
        }
    return {"players": players, "objects": objects}


def import_runtime(data: dict, *, grace_last_seen: bool = True) -> int:
    """
    从检查点回填。返回回填的 player 数。
    grace_last_seen=True：把 last_seen 置为现在，给重启后的客户端 _PLAYER_TIMEOUT 秒重连窗口，
    否则停机超过 10 s 的 player 会在第一个 tick 被当作 stale 清掉。
    """
    now = time.time()
    from game import self_sync
    with STATE_LOCK:
        _players.clear(); _pending_messages.clear(); _use_start_times.clear(); _last_seen.clear()
        _last_used.clear(); _use_history.clear(); _pre_use_pos.clear()
        for pid, row in (data.get("players") or {}).items():
            player = row["player"]
            _ensure_player_fields(player)
            _players[pid] = player
            if _ensure_valid_position(player):            # 换地图后旧坐标非法 → 出生点
                row["use_start_time"] = None
            if player.get("state") == "walking":          # §3.36：走路队列不进检查点，重启后就地站住
                player["state"] = "idle"
            _pending_messages[pid] = row.get("pending_message")
            _use_start_times[pid]  = row.get("use_start_time")
            _last_seen[pid] = now if grace_last_seen else (row.get("last_seen") or now)
            _last_used[pid] = {k: float(v) for k, v in (row.get("last_used") or {}).items()}
            _last_input[pid] = now
            _use_history[pid] = [(float(t), o) for t, o in (row.get("use_history") or [])]
            if row.get("pre_use_pos"):
                _pre_use_pos[pid] = dict(row["pre_use_pos"])
            if player.get("controller") == "agent":
                self_sync.register(pid, game_now_ts())
        from game import state_log
        for p in _players.values():
            state_log.sample_now(p, "restore")        # Q1：回填后立即采样
        for o in _OBJECTS:
            rt = (data.get("objects") or {}).get(o["id"])
            if rt is None:
                o["currentUsers"] = 0
                o["userList"] = []
            else:
                o["userList"] = [u for u in rt.get("userList", []) if u in _players]
                o["currentUsers"] = len(o["userList"])
                if rt.get("stock") is not None and o.get("stock") is not None:      # W11：库存回填（新加的物品类型保留初值）
                    o["stock"] = dict(rt["stock"])
        refresh_shop_views()
        return len(_players)


def _reset_for_tests() -> None:
    """清空全部运行时状态（测试用）。"""
    with STATE_LOCK:
        _players.clear(); _pending_messages.clear(); _use_start_times.clear(); _last_seen.clear()
        _last_used.clear(); _use_history.clear(); _phone_feed.clear(); _recent_events.clear(); _last_input.clear(); _pre_use_pos.clear(); _use_start_game_ts.clear(); _walks.clear()
        global _walk_log_enabled
        _walk_log_enabled = True
        if _REMOVED_OBJECTS or _OBJ_ORIG_POS:
            restore_object()
        _REMOVED_OBJECTS.clear(); _OBJ_ORIG_POS.clear()
        for o in _OBJECTS:
            o["stock"] = _initial_stock(o["type"])
        refresh_shop_views()
        for o in _OBJECTS:
            o["currentUsers"] = 0
            o["userList"] = []
