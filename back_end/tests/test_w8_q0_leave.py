"""W8 Q0：任何物品 use 后 leave 必须成功——含重启回填、重复 use、对话中（chat_active）三条路径。"""
from datetime import datetime

import pytest

from game import world_state, persistence, chat_state, ticker
from game.time_state import GAME_TZ
from tests.conftest import join, action, place

# 所有可被 use 的 continuous 物品及其站位（map.json）
STANDS = {
    "bed_whale": (3, 5, "up"), "stream_desk_whale": (3, 12, "down"), "desk_whale": (10, 4, "up"),
    "game_console_whale": (9, 11, "right"), "bed_achan": (13, 4, "up"), "desk_kitchen": (19, 11, "down"),
    "bed_cook": (33, 9, "up"), "desk_cook": (42, 13, "down"), "bed_grocer": (17, 29, "down"),
    "bed_fisher": (47, 23, "left"), "bed_regular": (32, 33, "left"), "desk_regular": (37, 36, "down"),
    "bath_regular": (42, 35, "up"), "table_rest_1": (46, 33, "up"), "table_rest_2": (50, 33, "up"),
    "bench_square_1": (32, 26, "up"), "bench_square_2": (38, 26, "up"),
    "fishing_spot_1": (52, 17, "right"), "fishing_spot_2": (52, 19, "right"),
}
CONTINUOUS = [o["id"] for o in world_state._OBJECTS if o["prototype"] == "continuous"]


@pytest.fixture(autouse=True)
def noon_and_stubs(fake_clock, monkeypatch):
    fake_clock.t = datetime(2026, 11, 10, 12, 30, tzinfo=GAME_TZ).timestamp()      # 餐馆 / 钓位 / 柜台都营业
    from game import external_effects
    monkeypatch.setattr(external_effects, "live_start", lambda p, iso: {"ok": True})
    monkeypatch.setattr(external_effects, "live_stop", lambda p, iso: None)
    monkeypatch.setattr(external_effects, "game_start", lambda p, iso: {"ok": True, "game": {"status": "playing", "started_at": iso}})
    monkeypatch.setattr(external_effects, "game_end", lambda p, iso: None)


def _agent(client):
    pid = client.post("/player/join", json={"name": "鲸仔", "controller": "agent", "profile": {"agent_id": "whale"}}).json()["playerId"]
    return pid


def test_every_continuous_object_is_covered():
    assert set(CONTINUOUS) == set(STANDS), set(CONTINUOUS) ^ set(STANDS)


@pytest.mark.parametrize("obj_id", sorted(STANDS))
def test_use_then_leave_always_succeeds(client, fake_clock, obj_id):
    pid = _agent(client)
    place(pid, *STANDS[obj_id])
    res = action(client, pid, "use")
    assert res["success"], (obj_id, res)
    _tick(fake_clock)                                            # no_use / no_move 生效后
    from game.object_types import OBJECT_TYPES
    has_no_use = any(e.get("key") == "no_use" for e in OBJECT_TYPES[world_state.get_object_by_id(obj_id)["type"]]["effects"])
    assert world_state._players[pid]["canUse"] is (not has_no_use)   # 带 no_use 的物品确实在挡 use，leave 仍要放行
    p = world_state._players[pid]
    assert p["usingObjectId"] == obj_id
    res = action(client, pid, "leave")
    assert res["success"] and res["result"]["objectId"] == obj_id, (obj_id, res)
    assert p["usingObjectId"] is None and world_state.get_object_by_id(obj_id)["currentUsers"] == 0


def _tick(fake_clock, n=2):
    """跑出真实的 tick（第一次只建基线）。"""
    for _ in range(n):
        fake_clock.advance(0.2); ticker.tick_once(checkpoint=False)


def test_leave_while_in_chat_succeeds(client, fake_clock):
    """钓位 no_move + 对话 chat_active：11-06 的死锁组合。"""
    a = _agent(client); b = join(client, "阿蝉")
    place(a, 52, 19, "right"); place(b, 51, 19, "right")
    rid = client.post("/chat/request", json={"from_entity_id": b, "to_entity_ids": [a], "greeting": "hi"}).json()["request_id"]
    client.post("/chat/respond", json={"entity_id": a, "request_id": rid, "accept": True, "message": "ok"})
    chat_state.tick()
    assert client.get(f"/chat/request/{rid}").json()["status"] == "active"
    p = world_state._players[a]
    assert any(x["key"] == "chat_active" for x in p["buffs"])
    _tick(fake_clock)                                            # 线上每 200 ms 一个 tick 会复位 canUse（chat_active 没有 handler）
    assert action(client, a, "use")["success"]                   # 对话中 use 钓位（当天就是这样）
    _tick(fake_clock)
    assert action(client, a, "move", {"direction": "left"})["reason"] == "move_disabled"   # 钓鱼不能走：预期
    res = action(client, a, "leave")                              # 但必须能离开
    assert res["success"] and res["result"]["objectId"] == "fishing_spot_2"
    assert p["usingObjectId"] is None


def test_leave_after_restart_succeeds(client, fake_clock):
    pid = _agent(client)
    place(pid, 52, 19, "right")
    assert action(client, pid, "use")["success"]
    persistence.save_checkpoint()
    world_state._reset_for_tests(); chat_state._reset_for_tests(); ticker._reset_for_tests()
    persistence.load_checkpoint()
    p = world_state._players[pid]
    assert p["usingObjectId"] == "fishing_spot_2" and any(b["key"] == "no_use" for b in p["buffs"])
    _tick(fake_clock)
    assert p["canUse"] is False
    res = action(client, pid, "leave")
    assert res["success"] and p["usingObjectId"] is None


def test_reuse_same_object_then_leave(client, fake_clock):
    pid = _agent(client)
    place(pid, 52, 19, "right")
    assert action(client, pid, "use")["success"]
    _tick(fake_clock)
    res2 = action(client, pid, "use")                             # 对正在用的物品再次 use（no_use 生效时会被挡；不影响 leave）
    obj = world_state.get_object_by_id("fishing_spot_2")
    assert obj["currentUsers"] == 1 and obj["userList"].count(pid) == 1   # 不重复计数
    res = action(client, pid, "leave")
    assert res["success"] and world_state._players[pid]["usingObjectId"] is None and obj["currentUsers"] == 0


def test_restore_drops_stale_chat_active(client):
    """回填时没有活跃房间却挂着 chat_active → 清掉；有房间但没 buff → 补上。"""
    pid = _agent(client)
    p = world_state._players[pid]
    p["buffs"].append({"key": "chat_active", "value": 0.0, "mode": "persistent", "remaining": None, "source": "chat_system"})
    p["state"] = "talking"
    persistence.save_checkpoint()
    world_state._reset_for_tests(); chat_state._reset_for_tests()
    persistence.load_checkpoint()
    p = world_state._players[pid]
    assert not any(b["key"] == "chat_active" for b in p["buffs"]) and p["state"] == "idle"


def test_leave_without_object_and_unknown_player(client):
    pid = join(client, "h")
    assert action(client, pid, "leave")["reason"] == "not_using_any_object"
    assert action(client, "ghost", "leave")["reason"] == "player_not_found"
