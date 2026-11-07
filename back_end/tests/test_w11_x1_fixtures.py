"""W11 维护（X1）：scenario move_object / remove_object / restore_object，GET /admin/path，path_query。"""
import pytest

from game import world_state
from tests.conftest import join, action, place
from tests.test_w9_map_v2 import v1  # noqa: F401


@pytest.fixture
def bench(monkeypatch):
    monkeypatch.setenv("SANDBOX_SCENARIO", "1")


def _run(client, steps):
    r = client.post("/admin/scenario", json={"label": "x1", "steps": steps})
    assert r.status_code == 200, r.text
    return r.json()


def test_move_remove_restore_object(client, v1, bench):
    mv0 = world_state.MAP_VERSION
    t1 = world_state.get_object_by_id("table_rest_1")
    assert t1["position"] == {"x": 48, "y": 23} and not world_state.is_tile_walkable(48, 23)
    r = _run(client, [{"op": "move_object", "id": "table_rest_1", "to": {"x": 48, "y": 26}}])
    assert r["ok"], r
    t1 = world_state.get_object_by_id("table_rest_1")
    assert t1["position"] == {"x": 48, "y": 26} and t1["tiles"] == [{"x": 48, "y": 26}, {"x": 49, "y": 26}]
    assert world_state.is_tile_walkable(48, 23) and world_state.is_tile_walkable(49, 23)          # 原地变地板
    assert not world_state.is_tile_walkable(48, 26) and world_state.get_object_at(49, 26)["id"] == "table_rest_1"
    assert t1["usePos"][0] == {"x": 48, "y": 27}                                                      # 站位跟着挪
    assert world_state.MAP_VERSION != mv0                                                             # 前端据此重拉
    w = client.get("/world", params={"fields": "objects,worldState"}).json()
    assert next(o for o in w["objects"] if o["id"] == "table_rest_1")["position"] == {"x": 48, "y": 26} and w["worldState"]["mapVersion"] != mv0
    # 撤掉吧台
    r = _run(client, [{"op": "remove_object", "id": "bar"}])
    assert r["ok"] and world_state.get_object_by_id("bar") is None and world_state.is_tile_walkable(51, 25)
    assert "bar" not in {o["id"] for o in client.get("/world", params={"fields": "objects"}).json()["objects"]}
    # 不合法目标：墙 / 有人站着 / 不存在
    assert _run(client, [{"op": "move_object", "id": "table_rest_2", "to": {"x": 46, "y": 22}}])["ok"] is False
    pid = join(client, "h"); place(pid, 50, 26, "up")
    assert _run(client, [{"op": "move_object", "id": "table_rest_2", "to": {"x": 50, "y": 26}}])["ok"] is False
    assert _run(client, [{"op": "remove_object", "id": "ghost"}])["ok"] is False
    # 恢复全部
    r = _run(client, [{"op": "restore_object"}])
    assert r["ok"] and set(r["steps"][0]["detail"]["restored"]) == {"table_rest_1", "bar"}
    assert world_state.get_object_by_id("table_rest_1")["position"] == {"x": 48, "y": 23}
    assert world_state.get_object_by_id("bar")["position"] == {"x": 51, "y": 25} and not world_state.is_tile_walkable(51, 25)
    assert world_state.is_tile_walkable(48, 26) and world_state.MAP_VERSION == mv0                    # 指纹回到原值


def test_move_kicks_user_and_reset_restores(client, v1, bench, fake_clock):
    from tests.test_w9_map_v2 import _at
    _at(fake_clock, 12, 0)
    pid = join(client, "h"); place(pid, 48, 24, "up")
    world_state._players[pid]["gold"] = 100
    assert action(client, pid, "use")["success"] and world_state._players[pid]["usingObjectId"] == "table_rest_1"
    r = _run(client, [{"op": "move_object", "id": "table_rest_1", "to": {"x": 48, "y": 26}}])
    assert r["ok"] and r["steps"][0]["detail"]["kicked"] == [pid]
    p = world_state._players[pid]
    assert p["usingObjectId"] is None and world_state.is_tile_walkable(p["position"]["x"], p["position"]["y"])
    _run(client, [{"op": "reset"}])
    assert world_state.get_object_by_id("table_rest_1")["position"] == {"x": 48, "y": 23}


def test_admin_path_endpoint(client, v1, fake_clock):
    from tests.test_w9_map_v2 import _at
    _at(fake_clock, 12, 0)
    r = client.get("/admin/path", params={"from": "55,13", "to_arena": "whale_room"}).json()           # 码头 → 鲸仔房间
    assert r["reachable"] and r["length"] > 30 and r["path"][-1] in [{"x": t["x"], "y": t["y"]} for t in world_state._TILES if t.get("arena") == "whale_room"]
    r2 = client.get("/admin/path", params={"from": "12,26", "to_object": "fridge_home"}).json()        # 客厅 → 冰箱站位
    assert r2["reachable"] and 0 < r2["length"] < 30 and r2["goals"] >= 1
    r3 = client.get("/admin/path", params={"from": "55,13", "to": "55,13"}).json()
    assert r3["reachable"] and r3["length"] == 0
    _at(fake_clock, 22, 30)
    closed = client.get("/admin/path", params={"from": "41,26", "to_object": "table_rest_1"}).json()    # 22:30 餐厅关门
    assert closed["reachable"] is False
    assert client.get("/admin/path", params={"from": "41,26", "to_object": "table_rest_1", "ignore_locks": "true"}).json()["reachable"]
    assert client.get("/admin/path", params={"from": "2,21", "to": "5,25"}).status_code == 400            # 起点是墙
    assert client.get("/admin/path", params={"from": "x", "to": "5,25"}).status_code == 400
    assert client.get("/admin/path", params={"from": "55,13", "to_object": "nope"}).status_code == 404
    # 锁门：小千家只有小千能进
    _at(fake_clock, 12, 0)
    assert client.get("/admin/path", params={"from": "16,42", "to_arena": "xiaoqian_room"}).json()["reachable"] is False
    assert client.get("/admin/path", params={"from": "16,42", "to_arena": "xiaoqian_room", "mover": "npc_xiaoqian"}).json()["reachable"] is True
