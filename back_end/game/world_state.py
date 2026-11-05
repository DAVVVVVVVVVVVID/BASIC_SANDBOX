import copy
import json
import threading
import time
import uuid
from pathlib import Path
from game.object_types import OBJECT_TYPES
from game.buff_tick import set_var, add_var, add_closeness, NEED_VARS, DECAY_BUFF, mood_baseline as _mood_baseline
from game.time_state import now_real, game_now_ts

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
            "advertise":      t.get("advertise"),       # B5：Sims 式广告值 {var: 0–100}
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

_PLAYER_TIMEOUT = 10.0  # 秒，超过此时间未心跳则自动清除（human 删除；agent 只标 online=False，B6）

# B5：物品使用记录（游戏秒）
_last_used:   dict[str, dict[str, float]]        = {}   # entity -> {obj_id: game_ts}
_use_history: dict[str, list[tuple[float, str]]] = {}   # entity -> [(game_ts, obj_id), ...]
OBJECT_COOLDOWN_S  = 30 * 60.0       # 同一物品 30 游戏分钟冷却
RECENT_USES_WINDOW_S = 6 * 3600.0    # 6 游戏小时内使用次数（novelty 折减用）

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
        "scene":         "sandbox",                  # B4：衰减速率按 scene 切换（sandbox | live）
        "agent_id":      _agent_id_for(name, profile) if controller == "agent" else None,
        "last_tick_ts":  _iso_game_now(),
        "usingObjectId": None,
        "buffs":         [dict(DECAY_BUFF)],         # B4：自然衰减元 buff
        "tags":          [],
        "canMove":       True,
        "canInteract":   True,
        "canUse":        True,
        "moveSpeed":     1.0,
    }


def _iso_game_now() -> str:
    from game.time_state import game_now_iso
    return game_now_iso()


def _ensure_player_fields(player: dict) -> None:
    """给旧版（检查点里）的 player dict 补齐新字段，幂等。"""
    defaults = _make_player(player["id"], player.get("name", player["id"]),
                            controller=player.get("controller", "human"))
    for k in ("fullness", "energy", "social", "fun", "mood", "mood_base", "emotion_tags",
              "closeness", "controller", "online", "scene", "agent_id", "last_tick_ts"):
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
    player_id = f"{safe}_{uuid.uuid4().hex[:6]}"
    player = _make_player(player_id, name, controller, profile)
    if player["controller"] == "agent":
        from game import self_sync
        self_sync.register(player_id, game_now_ts())
        self_sync.seed_player(player, game_now_ts())
    with STATE_LOCK:
        _players[player_id] = player
        _pending_messages[player_id] = None
        _use_start_times[player_id]  = None
        _last_seen[player_id]        = time.time()
        _last_used.setdefault(player_id, {})
        _use_history.setdefault(player_id, [])
    return copy.deepcopy(player)


def rejoin_player(player_id: str) -> dict | None:
    """B6：supervisor 重拉后用同一 player_id 续接。不存在返回 None。"""
    with STATE_LOCK:
        player = _players.get(player_id)
        if player is None:
            return None
        player["online"] = True
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
        _players.pop(player_id, None)
        _pending_messages.pop(player_id, None)
        _use_start_times.pop(player_id, None)
        _last_seen.pop(player_id, None)
        _last_used.pop(player_id, None)
        _use_history.pop(player_id, None)
    from game import self_sync
    self_sync.unregister(player_id)


def touch_player(player_id: str) -> None:
    """更新玩家心跳时间戳，表示该玩家仍在线。"""
    p = _players.get(player_id)
    if p is not None:
        _last_seen[player_id] = time.time()
        p["online"] = True


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
            "controller": p.get("controller", "human"),
            "online":     p.get("online", True),
        }
        for p in _players.values()
    ]


# ── B5：冷却与使用计数 ────────────────────────────────────────────────────────

def object_cooldown_remaining(entity_id: str, obj_id: str) -> float:
    """同一物品 30 游戏分钟冷却：返回剩余游戏秒，0 表示可用。"""
    last = _last_used.get(entity_id, {}).get(obj_id)
    if last is None:
        return 0.0
    return max(0.0, OBJECT_COOLDOWN_S - (game_now_ts() - last))


def record_object_use(entity_id: str, obj_id: str) -> None:
    now = game_now_ts()
    _last_used.setdefault(entity_id, {})[obj_id] = now
    hist = _use_history.setdefault(entity_id, [])
    hist.append((now, obj_id))
    cutoff = now - RECENT_USES_WINDOW_S
    _use_history[entity_id] = [(t, o) for t, o in hist if t >= cutoff]


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

    # continuous 物品：buff（persistent 到 leave 为止 / timed）、tag、以及进入时的一次性 instant_effect
    apply_effects(player, obj["effects"], source=obj_id)


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
        if etype == "instant_effect":
            if canonical_var(key) is None:
                skipped += 1; continue
            add_var(player, key, value); applied += 1
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
                add_var(player, key[:-6], value); applied += 1
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


def apply_effects_to_player(entity_id: str, effects: list[dict], scene: str | None, source: str = "effects") -> dict | None:
    """B13：POST /player/{id}/effects 入口。返回 player 副本或 None。"""
    with STATE_LOCK:
        player = _players.get(entity_id)
        if player is None:
            return None
        summary = apply_effects(player, effects, source=source, scene=scene)
        return {"summary": summary, "player": copy.deepcopy(player)}


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
    kept = [b for b in player["buffs"] if b.get("source") == "decay"]
    count = len(player["buffs"]) - len(kept)
    player["buffs"] = kept
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
        self_sync.on_tick(gts, _players)


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
    from game import self_sync
    with STATE_LOCK:
        _players.clear(); _pending_messages.clear(); _use_start_times.clear(); _last_seen.clear()
        _last_used.clear(); _use_history.clear()
        for pid, row in (data.get("players") or {}).items():
            player = row["player"]
            _ensure_player_fields(player)
            _players[pid] = player
            _pending_messages[pid] = row.get("pending_message")
            _use_start_times[pid]  = row.get("use_start_time")
            _last_seen[pid] = now if grace_last_seen else (row.get("last_seen") or now)
            _last_used[pid] = {k: float(v) for k, v in (row.get("last_used") or {}).items()}
            _use_history[pid] = [(float(t), o) for t, o in (row.get("use_history") or [])]
            if player.get("controller") == "agent":
                self_sync.register(pid, game_now_ts())
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
        _last_used.clear(); _use_history.clear()
        for o in _OBJECTS:
            o["currentUsers"] = 0
            o["userList"] = []
