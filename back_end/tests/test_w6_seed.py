"""W6 任务 2：SANDBOX_SEED 决定天气序列与 NPC 出生点；m1c 地图。"""
import json
from collections import deque
from datetime import datetime
from pathlib import Path

import pytest

from game import world_state, ticker
from game.time_state import GAME_TZ


def _ts(h, day=10):
    return datetime(2026, 11, day, h, tzinfo=GAME_TZ).timestamp()


def test_weather_sunny_without_seed_and_deterministic_with_seed(monkeypatch, client):
    monkeypatch.setattr(world_state, "SANDBOX_SEED", None)
    assert world_state.weather_for(_ts(3)) == "sunny" and world_state.weather_for(_ts(15)) == "sunny"
    monkeypatch.setattr(world_state, "SANDBOX_SEED", 2)
    seq = [world_state.weather_for(_ts(h)) for h in range(0, 24, 6) for _ in range(1)]
    seq2 = [world_state.weather_for(_ts(h)) for h in range(0, 24, 6)]
    assert seq == seq2 and all(w in ("sunny", "cloudy", "rain") for w in seq)
    # 同一段内不变，换 seed 多半不同（30 天 × 4 段全同的概率可忽略）
    assert world_state.weather_for(_ts(6)) == world_state.weather_for(_ts(11))
    monkeypatch.setattr(world_state, "SANDBOX_SEED", 3)
    seq3 = [world_state.weather_for(_ts(h, day=d)) for d in range(1, 29) for h in range(0, 24, 6)]
    monkeypatch.setattr(world_state, "SANDBOX_SEED", 2)
    seq2 = [world_state.weather_for(_ts(h, day=d)) for d in range(1, 29) for h in range(0, 24, 6)]
    assert seq2 != seq3
    # ticker 把它写进 worldState.weather
    world_state.update_weather(_ts(12))
    assert client.get("/world", params={"fields": "worldState"}).json()["worldState"]["weather"] == world_state.weather_for(_ts(12))


def test_agent_spawns_in_home_arena(client, monkeypatch):
    monkeypatch.setattr(world_state, "SANDBOX_SEED", None)
    for aid, arena in (("whale", "storage"), ("achan", "achan_room"), ("npc_cook", "cook_bedroom"), ("npc_fisher", "fisher_hut")):
        p = client.post("/player/join", json={"name": aid, "controller": "agent", "profile": {"agent_id": aid}}).json()["player"]
        z = world_state.get_zone_at(p["position"]["x"], p["position"]["y"])
        assert z["arena"] == arena, (aid, z)
        assert world_state.is_tile_walkable(p["position"]["x"], p["position"]["y"])
    h = client.post("/player/join", json={"name": "h"}).json()["player"]
    assert h["position"] == {"x": 6, "y": 9}                             # human 仍在地图出生点
    unknown = client.post("/player/join", json={"name": "x", "controller": "agent", "profile": {"agent_id": "nobody"}}).json()["player"]
    assert unknown["position"] == {"x": 6, "y": 9}


def test_spawn_point_depends_on_seed_but_stays_in_home(monkeypatch):
    monkeypatch.setattr(world_state, "SANDBOX_SEED", 1)
    a = world_state.spawn_point_for("npc_cook")
    monkeypatch.setattr(world_state, "SANDBOX_SEED", 1)
    assert world_state.spawn_point_for("npc_cook") == a
    pts = set()
    for seed in range(1, 12):
        monkeypatch.setattr(world_state, "SANDBOX_SEED", seed)
        sp = world_state.spawn_point_for("npc_cook")
        assert world_state.get_zone_at(sp["x"], sp["y"])["arena"] == "cook_bedroom"
        pts.add((sp["x"], sp["y"]))
    assert len(pts) > 1


def test_m1c_map_reachable_and_has_8_npc_homes():
    """m1c 地图（SANDBOX_MAP_DIR=game/maps/m1c）：按同一套可走规则 BFS，42 个物品全部可达，8 户都有床。"""
    root = Path(world_state.__file__).parent / "maps" / "m1c"
    m = json.loads((root / "map.json").read_text(encoding="utf-8"))
    objs = json.loads((root / "objects.json").read_text(encoding="utf-8"))
    types = json.loads((root / "tile_types.json").read_text(encoding="utf-8"))
    from game.object_types import OBJECT_TYPES
    walk = {(x, y) for y, row in enumerate(m["tiles"]) for x, ch in enumerate(row) if types[m["tile_chars"][ch]]["walkable"]}
    start = (m["meta"]["player_start"]["x"], m["meta"]["player_start"]["y"])
    seen = {start}; q = deque([start])
    while q:
        x, y = q.popleft()
        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            n = (x + dx, y + dy)
            if n in walk and n not in seen:
                seen.add(n); q.append(n)
    assert m["meta"]["height"] == 48 and len(objs) == 42
    for o in objs:
        w_, h_ = OBJECT_TYPES[o["type"]]["size"]
        tiles = [(o["position"]["x"] + dx, o["position"]["y"] + dy) for dy in range(h_) for dx in range(w_)]
        adj = {(tx + dx, ty + dy) for tx, ty in tiles for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0))}
        assert adj & seen, o["id"]
    sectors = set(m["zone_chars"]["sector"].values())
    assert {"teacher_house", "painter_house", "herbalist_house"} <= sectors
    beds = {o["id"] for o in objs if o["type"].startswith("bed")}
    assert {"bed_whale", "bed_achan", "bed_cook", "bed_grocer", "bed_fisher", "bed_regular", "bed_teacher", "bed_painter", "bed_herbalist"} <= beds
    assert m["zone_names"]["sector"]["teacher_house"] == "教书先生家"
