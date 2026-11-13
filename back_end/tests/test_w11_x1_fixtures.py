"""W11 维护（X1）：scenario move_object / remove_object / restore_object，GET /admin/path，path_query。"""
import pytest

from game import world_state
from tests.conftest import join, action, place
from tests.test_w9_map_v2 import v12  # noqa: F401


@pytest.fixture
def bench(monkeypatch):
    monkeypatch.setenv("SANDBOX_SCENARIO", "1")


def _run(client, steps):
    r = client.post("/admin/scenario", json={"label": "x1", "steps": steps})
    assert r.status_code == 200, r.text
    return r.json()


def test_move_remove_restore_object(client, v12, bench):
    mv0 = world_state.MAP_VERSION
    t1 = world_state.get_object_by_id("table_rest_1")
    assert t1["position"] == {"x": 34, "y": 11} and not world_state.is_tile_walkable(34, 11)
    r = _run(client, [{"op": "move_object", "id": "table_rest_1", "to": {"x": 36, "y": 14}}])
    assert r["ok"], r
    t1 = world_state.get_object_by_id("table_rest_1")
    assert t1["position"] == {"x": 36, "y": 14} and t1["tiles"] == [{"x": 36, "y": 14}, {"x": 37, "y": 14}]
    assert world_state.is_tile_walkable(34, 11) and world_state.is_tile_walkable(35, 11)          # 原地变地板
    assert not world_state.is_tile_walkable(36, 14) and world_state.get_object_at(37, 14)["id"] == "table_rest_1"
    assert t1["usePos"][0] == {"x": 36, "y": 15}                                                      # 站位跟着挪
    assert world_state.MAP_VERSION != mv0                                                             # 前端据此重拉
    w = client.get("/world", params={"fields": "objects,worldState"}).json()
    assert next(o for o in w["objects"] if o["id"] == "table_rest_1")["position"] == {"x": 36, "y": 14} and w["worldState"]["mapVersion"] != mv0
    # 撤掉吧台
    r = _run(client, [{"op": "remove_object", "id": "bar"}])
    assert r["ok"] and world_state.get_object_by_id("bar") is None and world_state.is_tile_walkable(37, 11)
    assert "bar" not in {o["id"] for o in client.get("/world", params={"fields": "objects"}).json()["objects"]}
    # 不合法目标：墙 / 有人站着 / 不存在
    assert _run(client, [{"op": "move_object", "id": "table_rest_2", "to": {"x": 33, "y": 11}}])["ok"] is False
    pid = join(client, "h"); place(pid, 36, 13, "up")
    assert _run(client, [{"op": "move_object", "id": "table_rest_2", "to": {"x": 36, "y": 13}}])["ok"] is False
    assert _run(client, [{"op": "remove_object", "id": "ghost"}])["ok"] is False
    # 恢复全部
    r = _run(client, [{"op": "restore_object"}])
    assert r["ok"] and set(r["steps"][0]["detail"]["restored"]) == {"table_rest_1", "bar"}
    assert world_state.get_object_by_id("table_rest_1")["position"] == {"x": 34, "y": 11}
    assert world_state.get_object_by_id("bar")["position"] == {"x": 37, "y": 11} and not world_state.is_tile_walkable(37, 11)
    assert world_state.is_tile_walkable(36, 14) and world_state.MAP_VERSION == mv0                    # 指纹回到原值


def test_move_kicks_user_and_reset_restores(client, v12, bench, fake_clock):
    from tests.test_w9_map_v2 import _at
    _at(fake_clock, 12, 0)
    pid = join(client, "h"); place(pid, 34, 12, "up")
    world_state._players[pid]["gold"] = 100
    assert action(client, pid, "use")["success"] and world_state._players[pid]["usingObjectId"] == "table_rest_1"
    r = _run(client, [{"op": "move_object", "id": "table_rest_1", "to": {"x": 36, "y": 14}}])
    assert r["ok"] and r["steps"][0]["detail"]["kicked"] == [pid]
    p = world_state._players[pid]
    assert p["usingObjectId"] is None and world_state.is_tile_walkable(p["position"]["x"], p["position"]["y"])
    _run(client, [{"op": "reset"}])
    assert world_state.get_object_by_id("table_rest_1")["position"] == {"x": 34, "y": 11}


def test_admin_path_endpoint(client, v12, fake_clock):
    from tests.test_w9_map_v2 import _at
    _at(fake_clock, 12, 0)
    r = client.get("/admin/path", params={"from": "43,5", "to_arena": "whale_room", "mover": "whale"}).json()   # 码头 → 鲸仔房间（§3.39 家里按身份算）
    assert r["reachable"] and r["length"] > 30 and r["path"][-1] in [{"x": t["x"], "y": t["y"]} for t in world_state._TILES if t.get("arena") == "whale_room"]
    r2 = client.get("/admin/path", params={"from": "9,13", "to_object": "fridge_home", "mover": "whale"}).json()   # 客厅 → 冰箱站位（§3.39 家里按鲸仔身份算）
    assert r2["reachable"] and 0 < r2["length"] < 30 and r2["goals"] >= 1
    r3 = client.get("/admin/path", params={"from": "43,5", "to": "43,5"}).json()
    assert r3["reachable"] and r3["length"] == 0
    _at(fake_clock, 22, 30)
    closed = client.get("/admin/path", params={"from": "28,14", "to_object": "table_rest_1"}).json()    # 22:30 餐厅关门
    assert closed["reachable"] is False
    assert client.get("/admin/path", params={"from": "28,14", "to_object": "table_rest_1", "ignore_locks": "true"}).json()["reachable"]
    assert client.get("/admin/path", params={"from": "2,10", "to": "4,13"}).status_code == 400            # 起点是墙
    assert client.get("/admin/path", params={"from": "x", "to": "5,25"}).status_code == 400
    assert client.get("/admin/path", params={"from": "43,5", "to_object": "nope"}).status_code == 404
    # 锁门：小千家只有小千能进
    _at(fake_clock, 12, 0)
    assert client.get("/admin/path", params={"from": "16,26", "to_arena": "xiaoqian_room"}).json()["reachable"] is False
    assert client.get("/admin/path", params={"from": "16,26", "to_arena": "xiaoqian_room", "mover": "npc_xiaoqian"}).json()["reachable"] is True
