"""W9：地图格式 v2（edges / floors / access）。world-v1.2 起测试图切到 game/maps/v1.2（紧凑版，id 与 v1 一致）；v1 草图文件保留给 X1–X6 复现。"""
import json
from datetime import datetime
from pathlib import Path

import pytest

from game import world_state
from game.time_state import GAME_TZ
from routers import actions as actions_mod
from tests.conftest import join, action, place, walk_done

V1 = Path(world_state.__file__).parent / "maps" / "v1"
V12 = Path(world_state.__file__).parent / "maps" / "v1.2"
DEFAULT = Path(world_state.__file__).parent / "maps"


def _load(monkeypatch, fake_clock, path):
    world_state.load_map(path)
    monkeypatch.setattr(actions_mod, "BASE_MOVE_INTERVAL", 0.0)
    fake_clock.t = datetime(2026, 11, 10, 12, 0, tzinfo=GAME_TZ).timestamp()
    yield
    world_state.load_map(DEFAULT)


@pytest.fixture
def v12(monkeypatch, fake_clock):
    """world-v1.2 紧凑图（测试默认）。"""
    yield from _load(monkeypatch, fake_clock, V12)


@pytest.fixture
def v1(monkeypatch, fake_clock):
    """v1.0 草图（保留，X1–X6 复现 / 旧图回归）。"""
    yield from _load(monkeypatch, fake_clock, V1)


def _at(fake_clock, h, m=0):
    fake_clock.t = datetime(2026, 11, 10, h, m, tzinfo=GAME_TZ).timestamp()


def _agent(client, aid, name=None):
    return client.post("/player/join", json={"name": name or aid, "controller": "agent", "profile": {"agent_id": aid}}).json()["playerId"]


def test_v1_map_still_loads(client, v1):
    assert world_state.MAP_FORMAT == 2 and world_state.MAP_W == 64 and world_state.MAP_H == 48 and len(world_state._OBJECTS) == 68 and len(world_state._EDGES) == 12


def test_v1_map_loads_format2_and_world_exposes_graph(client, v12):
    assert world_state.MAP_FORMAT == 2 and world_state.MAP_W == 50 and world_state.MAP_H == 37
    assert len(world_state._OBJECTS) == 70 and len(world_state._EDGES) == 12   # world-v1.2：去掉草坪装饰树，+2 大树 +3 路灯；v1.2.3：+12 件室外装饰（灌木 / 花坛 / 垃圾桶 / 邮筒 / 侧向长椅）；v1.2.5：−2 公园长椅
    w = client.get("/world", params={"fields": "map,zone_names,worldState"}).json()
    assert w["map"]["format"] == 2 and w["map"]["floors"] == {"achan_room": 2}
    assert {e["kind"] for e in w["map"]["edges"]} == {"door", "gate", "stairs"}
    assert w["map"]["access"]["achan_room"]["locked"] == [["09:00", "18:30"]]
    assert w["zone_names"]["sector"]["home"] == "合租房" and w["worldState"]["mapVersion"].startswith("鲸鱼大学城")
    tree = client.get("/agent/perceive", params={"entity_id": join(client, "h")}).json()["arena_tree"]
    floors = {a["id"]: a["floor"] for s in tree["sectors"] for a in s["arenas"]}
    assert floors["achan_room"] == 2 and floors["whale_room"] == 1
    assert {s["id"] for s in tree["sectors"]} == {"outside", "university", "fisher_house", "home", "restaurant", "grocery", "claudine_house", "owners_house"}


def test_spawn_points_follow_bible(client, v12):
    for aid, arena in (("whale", "whale_room"), ("achan", "achan_room"), ("npc_fisher", "fisher_bedroom"),
                       ("claudine", "claudine_room"), ("npc_rest_owner", "owner_rest_room"), ("npc_grocer", "owner_grocer_room")):
        p = client.post("/player/join", json={"name": aid, "controller": "agent", "profile": {"agent_id": aid}}).json()["player"]
        assert world_state.get_zone_at(p["position"]["x"], p["position"]["y"])["arena"] == arena, aid
    h = client.post("/player/join", json={"name": "h"}).json()["player"]
    assert world_state.get_zone_at(h["position"]["x"], h["position"]["y"])["arena"] == "whale_room"      # 2.5：鲸仔房间出生


def test_all_objects_reachable_including_2f(client, v12):
    """忽略锁（当 owner）从鲸仔房间出发，52 个物品全部有相邻可达格——含 2F 阿蝉房（经楼梯边）。"""
    start = (world_state._META["player_start"]["x"], world_state._META["player_start"]["y"])
    reach = {start}
    from collections import deque
    q = deque([start])
    while q:
        cur = q.popleft()
        for n, _ in world_state.neighbors(cur[0], cur[1], None, None, ignore_locks=True):
            if n not in reach:
                reach.add(n); q.append(n)
    assert any(world_state.get_zone_at(*t)["arena"] == "achan_room" for t in reach)                 # 2F 可达
    for o in world_state._OBJECTS:
        adj = {(t["x"] + dx, t["y"] + dy) for t in o["tiles"] for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0))}
        assert adj & reach, o["id"]


def test_achan_room_locked_0900_1830_for_whale_open_after(client, v12, fake_clock):
    whale = _agent(client, "whale"); achan = _agent(client, "achan")
    _at(fake_clock, 10, 0)
    res = action(client, whale, "move_to_area", {"area_type": "arena", "area_id": "achan_room"})
    assert res["success"] is False and res["reason"] == "no_path"                                   # §3.36：无路统一 no_path，首个阻塞在 result
    assert res["result"]["blocked_reason"] == "locked" and res["result"]["opens_at"] == "18:30" and res["result"]["blocked_at"] == {"x": 3, "y": 30}
    res = action(client, whale, "go_to", {"target": "achan_room"})                                # 别名
    assert res["type"] == "go_to" and res["reason"] == "no_path" and res["result"]["blocked_reason"] == "locked" and res["result"]["opens_at"] == "18:30"
    # 阿蝉本人（owner）锁定时段也能进，且路径经过楼梯边（1F (10,16) → 2F (3,30)）
    place(achan, 9, 12, "down")
    res = action(client, achan, "move_to_area", {"area_type": "arena", "area_id": "achan_room"})
    assert res["success"], res
    walk_done(achan, fake_clock)
    pos = world_state._players[achan]["position"]
    assert world_state.get_zone_at(pos["x"], pos["y"])["arena"] == "achan_room"
    # 19:00 鲸仔能上楼
    _at(fake_clock, 19, 0)
    res = action(client, whale, "move_to_area", {"area_type": "arena", "area_id": "achan_room"})
    assert res["success"], res
    walk_done(whale, fake_clock)
    pos = world_state._players[whale]["position"]
    assert world_state.get_zone_at(pos["x"], pos["y"])["arena"] == "achan_room" and world_state.arena_floor("achan_room") == 2
    # 单步 move 跨楼梯：站在 (10,16) 不能靠相邻走上去（非相邻），BFS 才走楼梯；下楼 move_to_area 回客厅
    res = action(client, whale, "move_to_area", {"area_type": "arena", "area_id": "living_room"})
    assert res["success"]
    walk_done(whale, fake_clock)
    pos = world_state._players[whale]["position"]
    assert world_state.get_zone_at(pos["x"], pos["y"])["arena"] == "living_room"


def test_single_step_into_locked_room_is_locked(client, v12, fake_clock):
    whale = _agent(client, "whale")
    _at(fake_clock, 10, 0)
    place(whale, 10, 16, "down")
    # 楼梯是非相邻边，单步 move 走不上去；用 move_to_area 得 locked。换一个相邻锁门：渔夫家门 (36,7)→(36,6)
    place(whale, 36, 7, "up")
    res = action(client, whale, "move", {"direction": "up"})
    assert res["success"] is False and res["reason"] == "no_path" and res["result"]["blocked_reason"] == "locked" and res["result"]["blocked_at"] == {"x": 36, "y": 6}
    fisher = _agent(client, "npc_fisher")
    place(fisher, 36, 7, "up")
    res = action(client, fisher, "move", {"direction": "up"})                                         # owner 可进（agent 单格也排队，1 格）
    assert res["success"] and res["result"]["state"] == "walking" and res["result"]["path_len"] == 1
    walk_done(fisher, fake_clock)
    assert world_state._players[fisher]["position"] == {"x": 36, "y": 6}
    res = action(client, whale, "move_to_area", {"area_type": "arena", "area_id": "fisher_bedroom"})
    assert res["reason"] == "no_path" and res["result"]["blocked_reason"] == "locked" and res["result"]["opens_at"] is None   # 常锁，无开门时间


def test_school_gate_and_building_hours(client, v12, fake_clock):
    whale = _agent(client, "whale")
    place(whale, 20, 9, "up")
    _at(fake_clock, 23, 30)
    res = action(client, whale, "move", {"direction": "up"})                                        # (20,8) 主街
    assert res["success"]; walk_done(whale, fake_clock)
    res = action(client, whale, "move", {"direction": "up"})                                        # (20,7) 校门，23:00 关
    assert res["success"] is False and res["reason"] == "no_path" and res["result"]["blocked_reason"] == "closed" and res["result"]["opens_at"] == "06:00"
    res = action(client, whale, "move_to_area", {"area_type": "arena", "area_id": "library"})
    assert res["reason"] == "no_path" and res["result"]["blocked_reason"] == "closed" and res["result"]["opens_at"] == "06:00"
    _at(fake_clock, 8, 30)                                                                            # 校门开，图书馆 9 点才开
    res = action(client, whale, "move_to_area", {"area_type": "arena", "area_id": "library"})
    assert res["reason"] == "no_path" and res["result"]["blocked_reason"] == "closed" and res["result"]["opens_at"] == "09:00"
    assert action(client, whale, "move_to_area", {"area_type": "arena", "area_id": "music_room"})["success"]   # 8 点开
    walk_done(whale, fake_clock)
    _at(fake_clock, 9, 30)
    assert action(client, whale, "move_to_area", {"area_type": "arena", "area_id": "library"})["success"]
    walk_done(whale, fake_clock)
    pos = world_state._players[whale]["position"]
    assert world_state.get_zone_at(pos["x"], pos["y"])["arena"] == "library"


def test_restaurant_door_hours_and_no_path(client, v12, fake_clock):
    whale = _agent(client, "whale")
    place(whale, 28, 13, "right")
    _at(fake_clock, 15, 0)
    res = action(client, whale, "move_to_area", {"area_type": "arena", "area_id": "dining"})
    assert res["reason"] == "no_path" and res["result"]["blocked_reason"] == "closed" and res["result"]["opens_at"] == "17:00"
    _at(fake_clock, 12, 0)
    assert action(client, whale, "move_to_area", {"area_type": "arena", "area_id": "dining"})["success"]
    walk_done(whale, fake_clock)
    assert action(client, whale, "move_to_area", {"area_type": "arena", "area_id": "water"})["reason"] == "no_walkable_tiles"


def test_legacy_map_unaffected():
    """默认（legacy v0）图：format 1、无边，寻路行为不变。"""
    assert world_state.MAP_FORMAT == 1 and world_state._EDGES == [] and world_state._ACCESS == {}
    assert world_state.MAP_VERSION.startswith("阿蝉家与小镇")
