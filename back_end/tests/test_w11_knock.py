"""§3.41 敲门：克劳蒂娜敲合租房门 → 鲸仔在家清醒收到 → 喊话 answered → 走到门内侧 open_door → 克劳蒂娜进（opened）→ 60 秒后落锁；
鲸仔在睡 → no_answer；decline；屋内无钥匙者可开门；检查点。"""
from datetime import datetime

from game import world_state, ticker, doors, persistence
from game.action_log import read_log
from game.time_state import GAME_TZ
from tests.conftest import action, place, walk_done
from tests.test_w9_map_v2 import v12  # noqa: F401


def _agent(client, aid, name=None):
    return client.post("/player/join", json={"name": name or aid, "controller": "agent", "profile": {"agent_id": aid}}).json()["playerId"]


def _at(fake_clock, h, m=0):
    fake_clock.t = datetime(2026, 11, 10, h, m, tzinfo=GAME_TZ).timestamp()


def _tick(fake_clock, s=1.0):
    fake_clock.advance(s); ticker.tick_once(checkpoint=False)


def _arena(pid):
    p = world_state._players[pid]["position"]
    return world_state.get_zone_at(p["x"], p["y"])["arena"]


def test_knock_answer_open_door_enter_and_relock(client, v12, fake_clock):
    _at(fake_clock, 10, 0)
    xq = _agent(client, "claudine", "克劳蒂娜"); whale = _agent(client, "whale", "鲸仔")
    place(whale, 9, 13, "down"); place(xq, 9, 19, "up")
    assert action(client, xq, "go_to", {"target": "living_room"})["reason"] == "no_path"
    r = action(client, xq, "knock", {"door_id": "door_home"})
    assert r["success"], r
    req = r["result"]["request"]; rid = req["id"]
    assert req["status"] == "pending" and req["notified"] == [whale] and req["door"]["inside"] == {"x": 9, "y": 17}
    assert client.get(f"/player/{whale}").json()["pendingMessage"] == "克劳蒂娜 在敲门。"
    assert client.get("/agent/perceive", params={"entity_id": whale}).json()["knocks"][0]["visitor_name"] == "克劳蒂娜"
    # 主人隔门喊一句
    assert client.post("/door/respond", json={"request_id": rid, "entity_id": whale}).json()["reason"] == "text_required"
    r2 = client.post("/door/respond", json={"request_id": rid, "entity_id": whale, "text": "等一下"}).json()
    assert r2["success"] and r2["request"]["status"] == "answered" and r2["request"]["answers"][0]["text"] == "等一下"
    pv = client.get(f"/player/{xq}").json()
    assert pv["pendingMessage"] == "鲸仔：等一下" and pv["door_request"]["status"] == "answered"
    # 开门：不在门内侧 → not_inside_door；走到门内侧 (12,33) 开门
    r3 = action(client, whale, "open_door", {"door_id": "door_home"})
    assert r3["success"] is False and r3["reason"] == "not_inside_door" and r3["result"]["inside"] == {"x": 9, "y": 17}
    assert action(client, whale, "move", {"targetTile": {"x": 9, "y": 16}})["success"]
    walk_done(whale, fake_clock)
    r3 = action(client, whale, "open_door", {"door_id": "door_home"})
    assert r3["success"] and r3["result"]["open_s"] == 60 and r3["result"]["door_id"] == "door_home"
    assert client.get(f"/player/{xq}").json()["pendingMessage"] == "鲸仔 把门打开了。"
    assert client.get("/world", params={"fields": "map"}).json()["map"]["doors"][0]["open"] is True or any(d["door_id"] == "door_home" and d["open"] for d in client.get("/world", params={"fields": "map"}).json()["map"]["doors"])
    # 敞开窗口内克劳蒂娜能进，进门那一步记 opened
    res = action(client, xq, "go_to", {"target": "living_room"}); assert res["success"], res
    walk_done(xq, fake_clock); assert _arena(xq) == "living_room"
    assert client.get(f"/player/{xq}").json()["door_request"]["status"] == "opened"
    assert [a["payload"]["outcome"] for a in read_log(entity=xq) if a["type"] == "door_respond"] == ["opened"]
    # 60 秒后自动落锁：日志 door_locked；克劳蒂娜出去后再进不来
    fake_clock.advance(61); ticker.tick_once(checkpoint=False)
    assert [a for a in read_log(entity=whale) if a["type"] == "door_locked"][-1]["payload"]["door_id"] == "door_home"
    assert not next(d for d in client.get("/world", params={"fields": "map"}).json()["map"]["doors"] if d["door_id"] == "door_home")["open"]
    assert action(client, xq, "go_to", {"target": "street"})["success"]
    walk_done(xq, fake_clock)
    assert action(client, xq, "go_to", {"target": "living_room"})["reason"] == "no_path"
    kinds = [a["type"] for a in read_log(entity=whale)]
    assert "door_respond" in kinds and "open_door" in kinds and "door_locked" in kinds
    assert sum(1 for a in read_log(entity=xq) if a["type"] == "knock" and a["success"]) == 1


def test_no_answer_decline_and_insider_without_key_can_open(client, v12, fake_clock):
    _at(fake_clock, 2, 0)
    fisher = _agent(client, "npc_fisher", "老渔夫"); whale = _agent(client, "whale", "鲸仔"); xq = _agent(client, "claudine", "克劳蒂娜")
    place(whale, 4, 13, "down"); world_state._players[whale]["tags"].append("sleeping")
    place(fisher, 9, 19, "up")
    r = action(client, fisher, "knock", {"target_tile": {"x": 9, "y": 17}})
    assert r["success"] and r["result"]["notified"] == []
    for _ in range(95):
        _tick(fake_clock, 1.0)
    pf = client.get(f"/player/{fisher}").json()
    assert pf["door_request"]["status"] == "no_answer" and pf["pendingMessage"] == "敲了半天没人应门。"
    # 醒了 → decline
    world_state._players[whale]["tags"].remove("sleeping")
    r = action(client, fisher, "knock", {"home": "home"}); rid = r["result"]["request_id"]
    r2 = client.post("/door/respond", json={"request_id": rid, "entity_id": whale, "decline": True}).json()
    assert r2["success"] and r2["request"]["status"] == "declined" and client.get(f"/player/{fisher}").json()["pendingMessage"] == "鲸仔 没让你进。"
    assert client.post("/door/respond", json={"request_id": rid, "entity_id": whale, "text": "x"}).json()["reason"] == "not_pending:declined"
    assert client.post("/door/respond", json={"request_id": rid, "entity_id": fisher, "text": "x"}).json()["reason"] == "not_inside"
    # 商店不走敲门；有钥匙的人不用敲
    place(xq, 35, 19, "up")
    assert action(client, xq, "knock", {"door_id": "door_restaurant"})["reason"] == "not_a_home"
    place(whale, 9, 19, "up")
    assert action(client, whale, "knock", {"door_id": "door_home"})["reason"] == "has_key"
    # 屋里没钥匙的访客（克劳蒂娜被放进来了）能从内侧开门、也能出去
    place(xq, 9, 17, "down")
    assert action(client, xq, "open_door", {"door_id": "door_home"})["success"]
    assert action(client, xq, "move", {"direction": "down"})["success"]                               # 出门（本来就永远放行）
    # 商店门：打烊后店主钥匙直接过，外人 closed
    _at(fake_clock, 23, 0)
    owner = _agent(client, "npc_rest_owner")
    place(owner, 35, 18, "up"); assert action(client, owner, "move", {"direction": "up"})["success"]
    walk_done(owner, fake_clock)
    place(fisher, 35, 18, "up"); r = action(client, fisher, "move", {"direction": "up"})
    assert r["reason"] == "no_path" and r["result"]["blocked_reason"] == "closed" and r["result"]["opens_at"] == "11:00"
    # 店主在店里：开自家门 → 不在门内侧 → 拒
    assert action(client, owner, "open_door", {"door_id": "door_owners"})["reason"] == "not_inside_door"
    # §3.41 补：屋内任何人（人类演阿蝉站在客厅）都能被通知、能应门
    from tests.conftest import join
    h = join(client, "主播")
    place(h, 9, 13, "down"); place(fisher, 9, 19, "up"); world_state._players[whale]["position"].update({"x": 28, "y": 13})
    r = action(client, fisher, "knock", {"door_id": "door_home"})
    assert r["success"] and r["result"]["notified"] == [h]
    assert client.post("/door/respond", json={"request_id": r["result"]["request_id"], "entity_id": h, "text": "来了来了"}).json()["success"]
    assert client.get(f"/player/{fisher}").json()["pendingMessage"] == "主播：来了来了"


def test_doors_state_survives_checkpoint(client, v12, fake_clock):
    _at(fake_clock, 10, 0)
    whale = _agent(client, "whale"); xq = _agent(client, "claudine")
    place(whale, 9, 17, "down"); place(xq, 9, 19, "up")
    rid = action(client, xq, "knock", {"door_id": "door_home"})["result"]["request_id"]
    assert action(client, whale, "open_door", {"door_id": "door_home"})["success"]
    persistence.save_checkpoint()
    doors._reset_for_tests(); world_state._reset_for_tests()
    persistence.load_checkpoint()
    assert doors.is_open_window("door_home", world_state.game_now_ts()) and rid in doors._requests
    assert [k["door_id"] for k in client.get(f"/player/{whale}").json()["keys"]] == ["door_home"]     # 钥匙在背包里，随玩家进检查点
    assert doors._issued["door_home"] == {"whale": whale}
    whale2 = _agent(client, "whale", "鲸仔2")
    assert client.get(f"/player/{whale2}").json()["keys"] == []                                        # 已发出的不重发
