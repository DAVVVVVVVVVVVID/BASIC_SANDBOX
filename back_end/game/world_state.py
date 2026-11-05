import copy
import json
import threading
import time
import uuid
from pathlib import Path
from game.object_types import OBJECT_TYPES
from game.buff_tick import set_var, NEED_VARS
from game.time_state import now_real

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
            "sprite":         t.get("sprite", ""),
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
_last_seen:        dict[str, float]         = {}

_PLAYER_TIMEOUT = 10.0  # 秒，超过此时间未心跳则自动清除

# 后台 ticker（事件循环线程）与 FastAPI 同步路由（线程池）会并发访问以上字典，
# 遍历 / 导出 / 增删 player 时持有此锁（B8）。
STATE_LOCK = threading.RLock()

# 七变量初值（ARCHITECTURE §3.1 B3 / 报告 §4.3 基线）
INITIAL_FULLNESS = 70.0
INITIAL_ENERGY   = 100.0
INITIAL_SOCIAL   = 60.0
INITIAL_FUN      = 60.0
MOOD_BASE        = 65.0


def mood_baseline(E: float = 50.0, N: float = 50.0) -> float:
    """mood 基线 = 65 + 0.2·(E−50) − 0.3·(N−50)（ARCHITECTURE §2.5）。"""
    return MOOD_BASE + 0.2 * (E - 50.0) - 0.3 * (N - 50.0)


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
        "emotion_tags":  [],
        "closeness":     {},
        "controller":    controller if controller in ("human", "agent") else "human",
        "last_tick_ts":  now_real(),
        "usingObjectId": None,
        "buffs":         [],
        "tags":          [],
        "canMove":       True,
        "canInteract":   True,
        "canUse":        True,
        "moveSpeed":     1.0,
    }


def _ensure_player_fields(player: dict) -> None:
    """给旧版（检查点里）的 player dict 补齐七变量字段，幂等。"""
    defaults = _make_player(player["id"], player.get("name", player["id"]))
    for k in ("fullness", "energy", "social", "fun", "mood", "emotion_tags",
              "closeness", "controller", "last_tick_ts"):
        if k not in player:
            player[k] = player.get("hp", defaults[k]) if k == "fullness" else defaults[k]
    player["hp"] = player["fullness"]


# ── 玩家生命周期 ──────────────────────────────────────────────────────────────

def create_player(name: str, controller: str = "human", profile: dict | None = None) -> dict:
    """创建新玩家，生成唯一 ID，返回玩家数据的深拷贝。

    controller / profile 为 B6 预留（W1 路由层尚不暴露，默认 human、E=N=50）。
    """
    safe = name[:12].lower().replace(" ", "_")
    player_id = f"{safe}_{uuid.uuid4().hex[:6]}"
    player = _make_player(player_id, name, controller, profile)
    with STATE_LOCK:
        _players[player_id] = player
        _pending_messages[player_id] = None
        _use_start_times[player_id]  = None
        _last_seen[player_id]        = time.time()
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
        _players.pop(player_id, None)
        _pending_messages.pop(player_id, None)
        _use_start_times.pop(player_id, None)
        _last_seen.pop(player_id, None)


def touch_player(player_id: str) -> None:
    """更新玩家心跳时间戳，表示该玩家仍在线。"""
    if player_id in _players:
        _last_seen[player_id] = time.time()


def _cleanup_stale_players() -> None:
    """清除超过 _PLAYER_TIMEOUT 秒未心跳的玩家。由后台 ticker 调用（B8）。"""
    now = time.time()
    with STATE_LOCK:
        stale = [pid for pid, ts in _last_seen.items() if now - ts > _PLAYER_TIMEOUT]
        for pid in stale:
            remove_player(pid)


# ── 公开访问函数 ──────────────────────────────────────────────────────────────

def get_world() -> dict:
    """只读（B8）：时间推进、buff tick、stale 清理都在后台 ticker 里。"""
    from game.time_state import get_time_state
    world_state = get_time_state()
    world_state["weather"] = _WEATHER
    return {
        "tiles":      _TILES,
        "objects":    _OBJECTS,
        "worldState": world_state,
        "players":    get_all_players_snapshot(),
        "tiled":      _MAP_DATA.get("tiled"),
    }


def get_player(player_id: str) -> dict | None:
    player = _players.get(player_id)
    if player is None:
        return None
    data = copy.deepcopy(player)
    data["hp"] = data.get("fullness", data.get("hp"))  # 别名兜底
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
            mode = e.get("mode", "persistent")
            new_buff = {
                "key":       e["key"],
                "value":     e.get("value", 0.0),
                "mode":      mode,
                "remaining": None if mode == "persistent" else e.get("duration", 0.0),
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
            # 对七变量通用 clamp（hp → fullness 别名），非需求变量忽略
            apply_var_delta(player, e["key"], e.get("value", 0.0))
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


def apply_var_delta(player: dict, key: str, value: float) -> None:
    """给 player 的某个需求变量加 value 并 clamp 到 0–100。"""
    from game.buff_tick import canonical_var
    var = canonical_var(key)
    if var is None:
        return
    set_var(player, var, player.get(var, 0.0) + float(value))


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
                {"id": aid, "name": _name("arena", aid)}
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
    now = now_real()          # 可注入的墙钟（time_state.set_clock），心跳 _last_seen 仍用 time.time()
    with STATE_LOCK:
        for player_id in list(_players.keys()):
            player = _players.get(player_id)
            if player is None:
                continue
            run_tick(player, delta, now_ts=now)
            _check_auto_leave(player_id)


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
            }
            for pid, p in _players.items()
        }
        objects = {
            o["id"]: {"currentUsers": o["currentUsers"], "userList": list(o["userList"])}
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
    with STATE_LOCK:
        _players.clear(); _pending_messages.clear(); _use_start_times.clear(); _last_seen.clear()
        for pid, row in (data.get("players") or {}).items():
            player = row["player"]
            _ensure_player_fields(player)
            _players[pid] = player
            _pending_messages[pid] = row.get("pending_message")
            _use_start_times[pid]  = row.get("use_start_time")
            _last_seen[pid] = now if grace_last_seen else (row.get("last_seen") or now)
        for o in _OBJECTS:
            rt = (data.get("objects") or {}).get(o["id"])
            if rt is None:
                o["currentUsers"] = 0
                o["userList"] = []
            else:
                o["userList"] = [u for u in rt.get("userList", []) if u in _players]
                o["currentUsers"] = len(o["userList"])
        return len(_players)


def _reset_for_tests() -> None:
    """清空全部运行时状态（测试用）。"""
    with STATE_LOCK:
        _players.clear(); _pending_messages.clear(); _use_start_times.clear(); _last_seen.clear()
        for o in _OBJECTS:
            o["currentUsers"] = 0
            o["userList"] = []
