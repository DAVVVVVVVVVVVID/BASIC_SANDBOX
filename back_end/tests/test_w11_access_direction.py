"""§3.38（主播 11-07 定）：营业时间 / 门锁只管「进」不管「出」；主人随时双向放行。"""
from datetime import datetime

from game import world_state
from game.time_state import GAME_TZ
from tests.conftest import action, place, walk_done
from tests.test_w9_map_v2 import v12  # noqa: F401


def _agent(client, aid, name=None):
    return client.post("/player/join", json={"name": name or aid, "controller": "agent", "profile": {"agent_id": aid}}).json()["playerId"]


def _at(fake_clock, h, m=0):
    fake_clock.t = datetime(2026, 11, 10, h, m, tzinfo=GAME_TZ).timestamp()


def test_owner_can_go_home_after_closing_and_guest_can_leave_but_not_enter(client, v12, fake_clock):
    _at(fake_clock, 21, 30)                                                                   # 餐厅 21:00 打烊
    owner = _agent(client, "npc_rest_owner"); guest = _agent(client, "whale")
    # 店主：从吧台位 (51,26) 回卧室可达（走 (51,30)→(51,31) 出门，再绕到自家南门）
    r = client.get("/admin/path", params={"from": "37,12", "to_arena": "owner_rest_room", "mover": "npc_rest_owner"}).json()
    assert r["reachable"], r
    place(owner, 37, 12, "down")
    res = action(client, owner, "move_to_area", {"area_type": "arena", "area_id": "owner_rest_room"})
    assert res["success"], res
    walk_done(owner, fake_clock)
    pos = world_state._players[owner]["position"]
    assert world_state.get_zone_at(pos["x"], pos["y"])["arena"] == "owner_rest_room"
    # 店主打烊后还能回店里（owner 随时双向）
    res = action(client, owner, "move_to_area", {"area_type": "arena", "area_id": "dining"})
    assert res["success"], res
    # 客人：在店里能出去
    place(guest, 36, 17, "down")
    res = action(client, guest, "move", {"direction": "down"})                              # (51,30) 内 → (51,31) 外
    assert res["success"] and res["result"]["state"] == "walking", res
    walk_done(guest, fake_clock)
    assert world_state._players[guest]["position"] == {"x": 36, "y": 18}
    # 客人：打烊后进不来
    res = action(client, guest, "move", {"direction": "up"})
    assert res["success"] is False and res["reason"] == "no_path" and res["result"]["blocked_reason"] == "closed" and res["result"]["opens_at"] == "11:00"
    assert client.get("/admin/path", params={"from": "36,18", "to_arena": "dining", "mover": "whale"}).json()["reachable"] is False
    # 从店里深处出发也能走到街上（整条路只有「出」）
    place(guest, 34, 12, "up")
    res = action(client, guest, "move_to_area", {"area_type": "arena", "area_id": "square"})
    assert res["success"], res


def test_locked_home_guest_can_exit_and_grocer_owner_both_ways(client, v12, fake_clock):
    _at(fake_clock, 12, 0)
    whale = _agent(client, "whale"); grocer = _agent(client, "npc_grocer")
    # 小千家常锁（allow owner）：外人被带进去后也能出来
    place(whale, 16, 25, "down")                                                               # 小千家门内侧
    res = action(client, whale, "move", {"direction": "down"})
    assert res["success"], res
    walk_done(whale, fake_clock)
    assert world_state._players[whale]["position"] == {"x": 16, "y": 26}
    res = action(client, whale, "move", {"direction": "up"})                                   # 进不去
    assert res["reason"] == "no_path" and res["result"]["blocked_reason"] == "locked"
    # 杂货店 20:00 关门后老板娘仍可进出
    _at(fake_clock, 22, 0)
    place(grocer, 21, 22, "right")
    assert action(client, grocer, "move", {"direction": "right"})["success"]                    # v1.2：杂货店门朝西，从南北街向右进
    walk_done(grocer, fake_clock)
    assert world_state._players[grocer]["position"] == {"x": 22, "y": 22}
    assert action(client, grocer, "move", {"direction": "left"})["success"]
    place(whale, 21, 22, "right")
    assert action(client, whale, "move", {"direction": "right"})["result"]["blocked_reason"] == "closed"
    # 边上的 owner 字段进了地图
    edges = {e["id"]: e for e in client.get("/world", params={"fields": "map"}).json()["map"]["edges"]}
    assert edges["door_restaurant"]["owner"] == ["npc_rest_owner"] and edges["door_grocery"]["owner"] == ["npc_grocer"]
