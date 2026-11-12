"""W5 任务 0（§3.14 事故）：perceive 整树、move_to_area 跨 sector、入场落点。"""
import pytest

from game import world_state, persistence, chat_state
from routers import actions as actions_mod
from tests.conftest import walk_done, BED_ID, join, action, place


@pytest.fixture(autouse=True)
def fast_moves(monkeypatch):
    monkeypatch.setattr(actions_mod, "BASE_MOVE_INTERVAL", 0.0)   # 测试里不等 300 ms 步进

SQUARE = (35, 25)          # 广场（室外 sector outside / arena square）


def _tree(client, pid):
    return client.get("/agent/perceive", params={"entity_id": pid}).json()


def test_outdoor_perceive_sees_whole_world_and_bed(client):
    pid = join(client, "h")
    place(pid, *SQUARE, "down")
    r = _tree(client, pid)
    tree = r["arena_tree"]
    assert r["current"] == {"world": "town", "sector": "outside", "arena": "square", "sector_name": "小镇", "arena_name": "广场"}
    sectors = {s["id"]: s for s in tree["sectors"]}
    assert {"outside", "achan_house", "cook_house", "grocer_house", "fisher_house", "regular_house", "restaurant"} <= set(sectors)
    assert sectors["outside"]["current"] is True and sectors["achan_house"]["current"] is False
    storage = next(a for a in sectors["achan_house"]["arenas"] if a["id"] == "storage")
    ids = {o["id"] for o in storage["objects"]}
    assert BED_ID in ids and {"desk_whale", "phone_whale", "stream_desk_whale"} <= ids
    bed = next(o for o in storage["objects"] if o["id"] == BED_ID)
    assert bed["type"] == "bed" and bed["maxUsers"] == 1 and bed["currentUsers"] == 0 and bed["advertise"] == {"energy": 80}
    square = next(a for a in sectors["outside"]["arenas"] if a["id"] == "square")
    assert square["current"] is True and {o["type"] for o in square["objects"]} == {"bench"}
    assert sum(a["current"] for s in tree["sectors"] for a in s["arenas"]) == 1
    # 旧字段仍在：sector = 当前 sector 节点
    assert tree["sector"]["id"] == "outside" and tree["id"] == "town" and tree["current"] is True
    # 全部 30 个物品都在树里
    assert sum(len(a["objects"]) for s in tree["sectors"] for a in s["arenas"]) == len(world_state._OBJECTS)


def test_indoor_perceive_marks_current_sector_and_arena(client):
    pid = join(client, "w")                        # 出生点在小仓库
    tree = _tree(client, pid)["arena_tree"]
    cur = [(s["id"], a["id"]) for s in tree["sectors"] for a in s["arenas"] if a["current"]]
    assert cur == [("achan_house", "storage")]
    assert [s["id"] for s in tree["sectors"] if s["current"]] == ["achan_house"]


def test_move_to_area_crosses_sectors(client, fake_clock):
    pid = join(client, "h")
    place(pid, *SQUARE, "down")
    res = action(client, pid, "move_to_area", {"area_type": "arena", "area_id": "storage"})
    assert res["success"], res
    assert res["result"]["state"] == "walking" and res["result"]["path_len"] > 0            # §3.36：先排队，再按 1 格 / 游戏秒走
    p = client.get(f"/player/{pid}").json()
    assert p["state"] == "walking" and p["walk"]["remaining"] == res["result"]["path_len"]
    used = walk_done(pid, fake_clock)
    assert used >= res["result"]["path_len"] - 1
    p = client.get(f"/player/{pid}").json()
    assert p["state"] == "idle" and p["walk"] is None
    assert world_state.get_zone_at(p["position"]["x"], p["position"]["y"])["arena"] == "storage"
    # 再去餐馆大堂（另一个 sector）
    res = action(client, pid, "move_to_area", {"area_type": "arena", "area_id": "dining"})
    assert res["success"]
    walk_done(pid, fake_clock)
    p = client.get(f"/player/{pid}").json()
    assert world_state.get_zone_at(p["position"]["x"], p["position"]["y"])["arena"] == "dining"
    # sector 级
    assert action(client, pid, "move_to_area", {"area_type": "sector", "area_id": "fisher_house"})["success"]
    walk_done(pid, fake_clock)


def test_move_to_area_picks_reachable_not_manhattan_nearest(client, fake_clock):
    """小仓库 (10,9) 到阿蝉房间：曼哈顿最近的格在墙后，必须绕门 (11,9)。"""
    pid = join(client, "h")
    place(pid, 4, 3, "down")
    res = action(client, pid, "move_to_area", {"area_type": "arena", "area_id": "achan_room"})
    assert res["success"]
    assert world_state.get_zone_at(res["result"]["target"]["x"], res["result"]["target"]["y"])["arena"] == "achan_room"
    walk_done(pid, fake_clock)
    p = world_state._players[pid]["position"]
    assert world_state.get_zone_at(p["x"], p["y"])["arena"] == "achan_room"


def test_every_arena_reachable_from_spawn_by_move_to_area(client):
    pid = join(client, "h")
    cmap = world_state.get_cognitive_map()
    for s in cmap["worlds"][0]["sectors"]:
        for a in s["arenas"]:
            if a["id"] == "water":
                continue
            res = action(client, pid, "move_to_area", {"area_type": "arena", "area_id": a["id"]}, skipLog=True)
            assert res["success"], (a["id"], res)


def test_rejoin_with_invalid_position_lands_on_spawn(client):
    pid = client.post("/player/join", json={"name": "w", "controller": "agent", "profile": {"agent_id": "whale"}}).json()["playerId"]
    p = world_state._players[pid]
    p["position"] = {"x": 0, "y": 0}                   # 旧地图坐标：现在是墙外草地？(0,0) 是 grass 且 arena=grass → 合法
    assert world_state._position_valid(0, 0)
    p["position"] = {"x": 2, "y": 2}                   # 阿蝉家外墙：不可走
    r = client.post("/player/rejoin", json={"playerId": pid}).json()
    start = world_state._META["player_start"]
    assert r["player"]["position"] == {"x": start["x"], "y": start["y"]}
    p["position"] = {"x": 55, "y": 5}                  # 河里
    client.post("/player/rejoin", json={"playerId": pid})
    assert p["position"] == {"x": start["x"], "y": start["y"]}


def test_checkpoint_restore_fixes_invalid_position(client, fake_clock):
    pid = join(client, "w")
    p = world_state._players[pid]
    p["position"] = {"x": 2, "y": 2}
    persistence.save_checkpoint()
    world_state._reset_for_tests(); chat_state._reset_for_tests()
    persistence.load_checkpoint()
    start = world_state._META["player_start"]
    assert world_state._players[pid]["position"] == {"x": start["x"], "y": start["y"]}
    # 合法坐标不动
    world_state._players[pid]["position"] = {"x": 35, "y": 25}
    persistence.save_checkpoint()
    world_state._reset_for_tests(); chat_state._reset_for_tests()
    persistence.load_checkpoint()
    assert world_state._players[pid]["position"] == {"x": 35, "y": 25}


def test_arena_tiles_any_arena(client):
    for aid in ("storage", "dining", "dock"):
        r = client.get("/agent/arena-tiles", params={"arena_id": aid}).json()
        assert r["arena_id"] == aid and len(r["tiles"]) > 0
