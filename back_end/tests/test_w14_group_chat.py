"""多人聊天 v1.1（world-v1.4.6，whale docs/systems/group-chat.md，主播 11-18）：POST /chat/join、每人 15 条（b10）、nearby_rooms。"""
import pytest

from game import chat_state, chat_profile, world_state
from tests.conftest import place
from tests.test_w9_map_v2 import _agent, v12  # noqa: F401


def _room(players_ids, greeting="嗨"):
    return chat_state._create_room(list(players_ids), world_state._players, greeting_from=players_ids[0], greeting_text=greeting)


def _join(client, pid, rid, greeting=None):
    body = {"entity_id": pid, "chat_room_id": rid}
    if greeting is not None:
        body["greeting"] = greeting
    r = client.post("/chat/join", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _say(client, pid, rid, text="嗯"):
    r = client.post("/chat/message", json={"entity_id": pid, "chat_room_id": rid, "content": text})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def b10():
    chat_profile.set_profile("b10")
    yield
    chat_profile._reset_for_tests()


def test_join_flow_distance_and_nearby_rooms(client, v12, b10):
    a, b, c, d, e = (_agent(client, f"ag{i}") for i in range(5))
    for pid, x in ((a, 3), (b, 4), (c, 6), (d, 7), (e, 9)):
        place(pid, x, 19, "up")
    rid = _room([a, b])
    # 4 格内看得到，2 格内才能进
    nr = {r["chat_room_id"]: r for r in client.get("/chat/nearby", params={"entity_id": d}).json()["rooms"]}
    assert nr[rid]["can_join"] is False and nr[rid]["reason"] == "too_far" and nr[rid]["count"] == 2
    assert [p["entity_id"] for p in nr[rid]["participants"]] == [a, b] and nr[rid]["last_message_preview"] == "嗨"
    assert client.get("/chat/nearby", params={"entity_id": e}).json()["rooms"] == []             # 5 格外看不到
    pv = client.get("/agent/perceive", params={"entity_id": c}).json()["needs"]["nearby_rooms"]
    assert pv[0]["chat_room_id"] == rid and pv[0]["can_join"] is True
    r = _join(client, d, rid)
    assert r["success"] is False and r["reason"] == "too_far" and r["distance"] == 3 and r["message"]
    # c 离 b 2 格：不需同意，直接进；greeting 作第一句、计条数
    r = _join(client, c, rid, greeting="我也来！")
    assert r["success"] and [p["entity_id"] for p in r["participants"]] == [a, b, c]
    assert r["my_count"] == 1 and r["my_limit"] == 15 and r["messages"][-1]["content"] == "我也来！" and r["messages"][-1]["from_name"]
    room = client.get(f"/chat/room/{rid}").json()
    assert any(ev["type"] == "player_join" and ev["entity_id"] == c for ev in room["events"]) and c in room["participants"]
    assert world_state._players[c]["state"] == "talking" and chat_state.room_of(c) == rid
    assert _join(client, c, rid)["reason"] == "already_in_room"
    # 进来以后 d 离 c 1 格 → 能进
    assert client.get("/chat/nearby", params={"entity_id": d}).json()["rooms"][0]["can_join"] is True


def test_join_rejections(client, v12, b10):
    ids = [_agent(client, f"p{i}") for i in range(9)]
    for i, pid in enumerate(ids):
        place(pid, 3 + i, 19, "up")
    rid = _room(ids[:2])
    assert _join(client, ids[2], "nope")["reason"] == "room_not_found"
    # 在别的房
    other = _room([ids[7], ids[8]])
    place(ids[7], 4, 20, "up")
    r = _join(client, ids[7], rid)
    assert r["reason"] == "in_other_room" and r["chat_room_id"] == other
    # 本人状态：直播 / 睡觉 / 勿扰（只挡 agent）/ 上课
    p2 = world_state._players[ids[2]]
    p2["scene"] = "live"; assert _join(client, ids[2], rid)["busy"] == "live"; p2["scene"] = "sandbox"
    p2["tags"] = ["sleeping"]; assert _join(client, ids[2], rid)["busy"] == "sleeping"; p2["tags"] = []
    p2["dnd"] = True; r = _join(client, ids[2], rid); assert r["reason"] == "busy" and r["busy"] == "dnd" and "勿扰" in r["message"]; p2["dnd"] = False
    p2["tags"] = ["in_class"]; assert _join(client, ids[2], rid)["reason"] == "in_class"; p2["tags"] = []
    # 房里的人 dnd 不影响别人加入（只看申请人）
    world_state._players[ids[0]]["dnd"] = True
    assert _join(client, ids[2], rid)["success"]
    # 满 6 人
    for pid in ids[3:6]:
        assert _join(client, pid, rid)["success"]
    assert len(chat_state._chat_rooms[rid]["participants"]) == 6
    r = _join(client, ids[6], rid)
    assert r["reason"] == "room_full" and r["count"] == 6
    # 关房后
    for pid in list(chat_state._chat_rooms[rid]["participants"]):
        client.post("/chat/exit", json={"entity_id": pid, "chat_room_id": rid})
    assert _join(client, ids[6], rid)["reason"] == "room_closed"


def test_human_dnd_can_join_and_cooldown_agent_only(client, v12, b10):
    a, b, ag = _agent(client, "a1"), _agent(client, "a2"), _agent(client, "a3")
    hum = client.post("/player/join", json={"name": "阿蝉", "controller": "human", "profile": {"agent_id": "achan"}}).json()["playerId"]
    for pid, x in ((a, 3), (b, 4), (ag, 5), (hum, 5)):
        place(pid, x, 19 if pid != hum else 20, "up")
    world_state._players[hum]["dnd"] = True
    rid = _room([a, b])
    chat_state._record_chat_end([ag, a])                                   # ag 刚和 a 聊完
    r = _join(client, ag, rid)
    assert r["reason"] == "chat_cooldown" and r["cooldown_remaining"] > 0
    chat_state._record_chat_end([hum, a])
    assert _join(client, hum, rid)["success"]                              # 人类：dnd 不挡、冷却免


def test_speaker_limit_b10_two_person_room(client, v12, b10):
    a, b = _agent(client, "s1"), _agent(client, "s2")
    place(a, 3, 19, "up"); place(b, 4, 19, "up")
    rid = _room([a, b])                                                    # a 的招呼已算 1 条
    for i in range(14):
        r = _say(client, a, rid, f"a{i}")
    assert r["my_count"] == 15 and r["my_limit"] == 15 and r["room_closed"] is False
    r = _say(client, a, rid)
    assert r["success"] is False and r["reason"] == "speaker_limit" and r["my_count"] == 15 and "15" in r["message"]
    for i in range(14):                                                    # 不再按房间总数 16 关
        r = _say(client, b, rid, f"b{i}")
        assert r["room_closed"] is False
    r = _say(client, b, rid, "最后一句")
    assert r["room_closed"] is True and r["reason"] == "speaker_limit_all" and r["my_count"] == 15
    assert chat_state._chat_rooms[rid]["status"] == "closed"


def test_exit_closes_when_rest_at_limit_and_rejoin_counts(client, v12, b10):
    a, b, c = _agent(client, "e1"), _agent(client, "e2"), _agent(client, "e3")
    for pid, x in ((a, 3), (b, 4), (c, 5)):
        place(pid, x, 19, "up")
    rid = _room([a, b])
    assert _join(client, c, rid)["success"]
    for _ in range(14):
        _say(client, a, rid)
    for _ in range(15):
        _say(client, b, rid)
    assert chat_state._chat_rooms[rid]["status"] == "active"              # c 还没到 15
    r = client.post("/chat/exit", json={"entity_id": c, "chat_room_id": rid}).json()
    assert r["room_closed"] is True and r["reason"] == "speaker_limit_all"
    # 另开一房：b 说满后退出再加回 → speaker_limit
    rid2 = _room([a, c])
    place(b, 4, 19, "up")
    chat_state._last_chat_end.pop(b, None); chat_state._last_pair_end.clear()
    assert _join(client, b, rid2)["success"]
    for _ in range(15):
        _say(client, b, rid2)
    client.post("/chat/exit", json={"entity_id": b, "chat_room_id": rid2})
    chat_state._last_chat_end.pop(b, None); chat_state._last_pair_end.clear()
    r = _join(client, b, rid2)
    assert r["reason"] == "speaker_limit" and r["my_count"] == 15


def test_b9_unchanged_room_total_16_and_join_works(client, v12):
    chat_profile.set_profile("b9")
    try:
        a, b, c = _agent(client, "n1"), _agent(client, "n2"), _agent(client, "n3")
        for pid, x in ((a, 3), (b, 4), (c, 5)):
            place(pid, x, 19, "up")
        rid = _room([a, b])
        r = _join(client, c, rid, greeting="我来了")
        assert r["success"] and r["my_limit"] is None
        for i in range(13):
            r = _say(client, (a, b, c)[i % 3], rid)
            assert r["room_closed"] is False and r["my_limit"] is None
        r = _say(client, a, rid)
        assert r["room_closed"] is True and r["reason"] == "room_limit"   # 1 招呼 + 1 加入招呼 + 14 = 16
    finally:
        chat_profile._reset_for_tests()
