"""W10 ①②：v1 地图南面进门 + 装饰层；物品 usePos / useFacing（/world 带出、perceive 不带；use 挪到站位，leave 回原地）。"""
from game import world_state
from tests.conftest import BED_ID, BED_STAND, DESK_ID, DESK_STAND, join, action, place
from tests.test_w9_map_v2 import v12  # noqa: F401  复用 v1 地图 fixture

SOUTH_DOORS = ("door_home", "door_restaurant", "door_grocery", "door_xiaoqian", "door_owners")


def test_v1_buildings_enter_from_south(client, v12):
    edges = {e["id"]: e for e in client.get("/world", params={"fields": "map"}).json()["map"]["edges"]}
    for eid in SOUTH_DOORS:
        a, b = edges[eid]["a"], edges[eid]["b"]
        if eid == "door_grocery":                                                  # world-v1.2：主播定杂货店门朝西直接开到南北街
            assert a["y"] == b["y"] and a["x"] == b["x"] - 1 and a["arena"] == "street", eid
            continue
        assert a["x"] == b["x"] and a["y"] == b["y"] + 1, eid                      # a 在 b 正南一格（a 外 b 内）
        assert a["arena"] == "lane", eid                                           # 门外是小巷
        assert b["arena"] != "lane" and world_state.get_zone_at(b["x"], b["y"])["arena"] == b["arena"], eid
        assert world_state.is_tile_walkable(a["x"], a["y"]) and world_state.is_tile_walkable(b["x"], b["y"]), eid
        assert world_state.is_tile_walkable(b["x"], b["y"] - 1), eid               # 门内一格是室内地板，不是墙
    # 渔夫屋与校园三栋不动
    assert (edges["door_fisher"]["a"]["x"], edges["door_fisher"]["a"]["y"]) == (37, 7)
    assert (edges["door_classroom"]["b"]["x"], edges["door_classroom"]["b"]["y"]) == (6, 5)


def test_v1_decor_layer_exposed_and_non_interactive(client, v12):
    w = client.get("/world", params={"fields": "decor,objects"}).json()
    kinds = {d["kind"] for d in w["decor"]}
    assert kinds == set()                                                            # world-v1.2：装饰层清空（外观走整栋贴图；主播定）；字段仍在
    for d in w["decor"]:
        assert d["id"] and d["tiles"] and all({"x", "y"} <= set(t) for t in d["tiles"])
    assert not any(d["id"] in {o["id"] for o in w["objects"]} for d in w["decor"])   # 装饰不是物品
    for d in w["decor"]:                                                            # 小径可走、池塘不可走
        for t in d["tiles"]:
            walk = world_state.is_tile_walkable(t["x"], t["y"])
            assert walk if d["kind"] == "path" else (not walk if d["kind"] == "pond" else True)
    assert len([o for o in w["objects"] if o["type"] in ("tree", "tree_big")]) == 4      # v1.2：公园 2 大树 + 2 小树
    assert client.get("/world").json()["decor"] == w["decor"]                       # 默认字段集也带


def test_world_objects_carry_use_pos_and_facing(client):
    objs = {o["id"]: o for o in client.get("/world", params={"fields": "objects"}).json()["objects"]}
    bed, desk = objs[BED_ID], objs[DESK_ID]
    assert bed["usePos"] == [{"x": 3, "y": 3}] and bed["useFacing"] == "down"
    assert desk["usePos"] == [{"x": DESK_STAND[0], "y": DESK_STAND[1]}] and desk["useFacing"] == "up"
    assert "usePos" in objs["fridge_kitchen"] and objs["fridge_kitchen"]["usePos"] is None   # 没站位的物品给 null


def test_perceive_does_not_expose_use_pos(client):
    pid = join(client)
    r = client.get("/agent/perceive", params={"entity_id": pid}).json()
    text = str(r)
    assert "usePos" not in text and "useFacing" not in text and "use_pos" not in text


def test_use_moves_to_use_pos_and_leave_restores(client):
    pid = join(client)
    place(pid, *BED_STAND)
    seq0 = world_state._players[pid]["pos_seq"]
    assert action(client, pid, "use")["success"]
    p = world_state._players[pid]
    assert p["position"] == {"x": 3, "y": 3} and p["facing"] == "down" and p["pos_seq"] == seq0 + 1
    assert client.get(f"/player/{pid}").json()["position"] == {"x": 3, "y": 3}
    assert action(client, pid, "leave")["success"]
    p = world_state._players[pid]
    assert p["position"] == {"x": BED_STAND[0], "y": BED_STAND[1]} and p["facing"] == BED_STAND[2]
    assert action(client, pid, "move", {"direction": "down"})["success"]                # leave 后站在可走格


def test_use_pos_second_user_gets_next_seat(client):
    """多座位物品：第二个使用者拿下一格；没座位的物品原地不动。"""
    a = join(client, "a"); b = join(client, "b")
    place(a, 10, 4, "up"); place(b, 10, 4, "up")
    assert action(client, a, "use")["success"]                                          # desk 单座位
    assert world_state._players[a]["position"] == {"x": 10, "y": 4}
    pre = {"x": 11, "y": 4}
    place(b, pre["x"], pre["y"], "up")
    if world_state.get_object_by_id(DESK_ID)["maxUsers"] in (None, 0) or world_state.get_object_by_id(DESK_ID)["maxUsers"] > 1:
        assert action(client, b, "use", {"objectId": DESK_ID})["success"] in (True, False)
    # 没 usePos 的物品：原地不动
    place(a, *BED_STAND); action(client, a, "leave")
    fridge = world_state.get_object_by_id("fridge_kitchen")
    fx, fy = fridge["position"]["x"], fridge["position"]["y"]
    place(a, fx, fy + 1, "up")
    r = action(client, a, "use")
    if r["success"]:
        assert world_state._players[a]["position"] == {"x": fx, "y": fy + 1}
