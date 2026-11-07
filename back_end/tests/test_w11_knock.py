"""§3.40 敲门：老渔夫敲合租房门 → 阿蝉在家清醒 → accept → 能进厨房、2 小时后不能；鲸仔在睡 → no_answer；decline；离家失效；检查点。"""
import json
from datetime import datetime

from game import world_state, ticker, doors, persistence
from game.action_log import read_log
from game.time_state import GAME_TZ
from tests.conftest import action, place, walk_done
from tests.test_w9_map_v2 import v1  # noqa: F401


def _agent(client, aid, name=None):
    return client.post("/player/join", json={"name": name or aid, "controller": "agent", "profile": {"agent_id": aid}}).json()["playerId"]


def _at(fake_clock, h, m=0):
    fake_clock.t = datetime(2026, 11, 10, h, m, tzinfo=GAME_TZ).timestamp()


def _tick(fake_clock, s=1.0):
    fake_clock.advance(s); ticker.tick_once(checkpoint=False)


def _arena(pid):
    p = world_state._players[pid]["position"]
    return world_state.get_zone_at(p["x"], p["y"])["arena"]


def test_knock_accept_gives_two_hour_pass(client, v1, fake_clock):
    _at(fake_clock, 10, 0)
    fisher = _agent(client, "npc_fisher", "老渔夫"); achan = _agent(client, "achan", "阿蝉")
    place(achan, 12, 26, "down")                                                             # 阿蝉在客厅、清醒
    place(fisher, 12, 35, "up")                                                              # 合租房大门外（a=(12,34)）
    assert action(client, fisher, "go_to", {"target": "kitchen"})["reason"] == "no_path"
    # 太远不能敲
    place(fisher, 20, 34, "up")
    r = action(client, fisher, "knock", {"door_id": "door_home"})
    assert r["success"] is False and r["reason"] == "too_far" and r["result"]["door"] == {"x": 12, "y": 34}
    place(fisher, 12, 35, "up")
    r = action(client, fisher, "knock", {"door_id": "door_home"})
    assert r["success"], r
    req = r["result"]["request"]
    assert req["status"] == "pending" and req["home"] == "home" and set(req["owners"]) == {"whale", "achan"} and req["door"]["id"] == "door_home"
    assert req["notified"] == [achan] and r["result"]["notified"] == [achan]
    # 主人侧
    pa = client.get(f"/player/{achan}").json()
    assert pa["pendingMessage"] == "老渔夫 在敲门。" and pa["pending_knocks"][0]["id"] == req["id"] and pa["pending_knocks"][0]["visitor_name"] == "老渔夫"
    per = client.get("/agent/perceive", params={"entity_id": achan}).json()
    assert per["knocks"] == [{"id": req["id"], "visitor_name": "老渔夫", "home_name": per["knocks"][0]["home_name"], "expires_at": req["expires_at"]}]
    # 访客侧
    pf = client.get(f"/player/{fisher}").json()
    assert pf["door_request"]["status"] == "pending" and pf["door_request"]["id"] == req["id"]
    assert client.get("/agent/perceive", params={"entity_id": fisher}).json()["door_request"]["status"] == "pending"
    assert action(client, fisher, "knock", {"door_id": "door_home"})["reason"] == "already_knocking"
    # 非主人不能回应；主人 accept
    assert client.post("/door/respond", json={"request_id": req["id"], "entity_id": fisher, "accept": True}).json()["reason"] == "not_owner"
    r2 = client.post("/door/respond", json={"request_id": req["id"], "entity_id": achan, "accept": True}).json()
    assert r2["success"] and r2["request"]["status"] == "accepted" and r2["request"]["responded_by"] == achan
    pf = client.get(f"/player/{fisher}").json()
    assert pf["door_request"]["status"] == "accepted" and pf["door_passes"][0]["home"] == "home" and pf["pendingMessage"] == "阿蝉 给你开了门。"
    assert client.get("/door/requests", params={"player": achan}).json()["pending_knocks"] == []
    # 能进厨房了
    r = action(client, fisher, "go_to", {"target": "kitchen"})
    assert r["success"], r
    walk_done(fisher, fake_clock); assert _arena(fisher) == "kitchen"
    assert client.get("/admin/path", params={"from": "4,29", "to_arena": "whale_room", "mover": fisher}).json()["reachable"]   # 这家所有 arena
    # 2 游戏小时后失效（人还在屋里 → 不被赶，但再出去就进不来）
    fake_clock.advance(2 * 3600 + 5); ticker.tick_once(checkpoint=False)
    assert client.get(f"/player/{fisher}").json()["door_passes"] == []
    place(fisher, 12, 35, "up")
    assert action(client, fisher, "go_to", {"target": "kitchen"})["reason"] == "no_path"
    rows = read_log(entity=fisher); kinds = [a["type"] for a in rows]
    assert sum(1 for a in rows if a["type"] == "knock" and a["success"]) == 1                 # 失败的 knock（too_far / already_knocking）也进日志
    assert "door_pass_granted" in kinds and "door_pass_expired" in kinds
    exp = [a for a in read_log(entity=fisher) if a["type"] == "door_pass_expired"][-1]
    assert exp["payload"]["reason"] == "timeout"
    assert [a for a in read_log(entity=achan) if a["type"] == "door_respond"][0]["payload"]["outcome"] == "accepted"


def test_no_answer_when_owner_sleeping_and_decline_and_leave_expires(client, v1, fake_clock):
    _at(fake_clock, 2, 0)
    fisher = _agent(client, "npc_fisher", "老渔夫"); whale = _agent(client, "whale", "鲸仔"); xq = _agent(client, "npc_xiaoqian", "小千")
    place(whale, 4, 24, "down"); world_state._players[whale]["tags"].append("sleeping")       # 鲸仔在家但在睡
    place(fisher, 12, 35, "up")
    r = action(client, fisher, "knock", {"target_tile": {"x": 12, "y": 33}})                 # 用门内一格也能指到家
    assert r["success"] and r["result"]["notified"] == []                                     # 没人清醒 → 没人收到
    assert client.get(f"/player/{whale}").json()["pendingMessage"] is None
    for _ in range(95):
        _tick(fake_clock, 1.0)
    pf = client.get(f"/player/{fisher}").json()
    assert pf["door_request"]["status"] == "no_answer" and pf["pendingMessage"] == "敲了半天没人应门。"
    row = [a for a in read_log(entity=fisher) if a["type"] == "door_respond"][-1]
    assert row["success"] is False and row["reason"] == "no_answer" and row["payload"]["outcome"] == "no_answer"
    # 醒了 → decline
    world_state._players[whale]["tags"].remove("sleeping")
    r = action(client, fisher, "knock", {"home": "home"})
    assert r["success"] and r["result"]["notified"] == [whale]
    rid = r["result"]["request_id"]
    r2 = client.post("/door/respond", json={"request_id": rid, "entity_id": whale, "accept": False}).json()
    assert r2["success"] and r2["request"]["status"] == "declined"
    assert client.get(f"/player/{fisher}").json()["door_request"]["status"] == "declined"
    assert client.post("/door/respond", json={"request_id": rid, "entity_id": whale, "accept": True}).json()["reason"] == "not_pending:declined"
    assert action(client, fisher, "go_to", {"target": "kitchen"})["reason"] == "no_path"
    # 小千本来就能进：knock 返回 already… 不是家门外 / 规则不同：小千是 allow 名单不是 owner → 允许敲但没必要；商店不走敲门
    place(xq, 51, 32, "up")
    assert action(client, xq, "knock", {"door_id": "door_restaurant"})["reason"] == "not_a_home"
    assert action(client, whale, "knock", {"door_id": "door_home"})["reason"] in ("is_owner", "already_inside")
    # accept 后进屋再离开 → 通行失效（先到为准）
    r = action(client, fisher, "knock", {"door_id": "door_home"})
    rid = r["result"]["request_id"]
    client.post("/door/respond", json={"request_id": rid, "entity_id": whale, "accept": True})
    assert action(client, fisher, "go_to", {"target": "living_room"})["success"]
    walk_done(fisher, fake_clock); assert _arena(fisher) == "living_room"
    _tick(fake_clock, 1.0)
    assert doors._passes[f"{fisher}:home"]["entered"] is True
    assert action(client, fisher, "go_to", {"target": "lane"})["success"]
    walk_done(fisher, fake_clock)
    _tick(fake_clock, 1.0)
    assert client.get(f"/player/{fisher}").json()["door_passes"] == []
    assert [a for a in read_log(entity=fisher) if a["type"] == "door_pass_expired"][-1]["payload"]["reason"] == "left"
    assert action(client, fisher, "go_to", {"target": "kitchen"})["reason"] == "no_path"


def test_pass_and_requests_survive_checkpoint(client, v1, fake_clock):
    _at(fake_clock, 10, 0)
    fisher = _agent(client, "npc_fisher"); achan = _agent(client, "achan")
    place(achan, 12, 26, "down"); place(fisher, 12, 35, "up")
    rid = action(client, fisher, "knock", {"door_id": "door_home"})["result"]["request_id"]
    client.post("/door/respond", json={"request_id": rid, "entity_id": achan, "accept": True})
    persistence.save_checkpoint()
    doors._reset_for_tests(); world_state._reset_for_tests()
    persistence.load_checkpoint()
    assert doors.has_pass(fisher, "home", world_state.game_now_ts())
    assert client.get(f"/player/{fisher}").json()["door_request"]["status"] == "accepted"
    assert action(client, fisher, "go_to", {"target": "kitchen"})["success"]
