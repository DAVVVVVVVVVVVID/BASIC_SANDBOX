"""X4 B 项：SANDBOX_CHAT_PROFILE b9|ait|nolimit（max_messages / cooldown / creator_first / awkward / max_duration）、scenario say 无房间 / qq_send、三方房间语义、/admin/metrics 回显。"""
import time

from game import chat_state, chat_profile, world_state
from tests.conftest import join, action, place


def _pair(client, n=2):
    """发起者在中间 (4,5)，其他人贴着它（曼哈顿 ≤ 1），接受即建房。"""
    ids = [join(client, f"p{i}") for i in range(n)]
    spots = [(4, 5), (3, 5), (4, 6), (5, 5)]
    for pid, (x, y) in zip(ids, spots):
        place(pid, x, y, "up")
    return ids


def _open_room(client, a, b, greeting="hi", msg="yo"):
    rid = client.post("/chat/request", json={"from_entity_id": b, "to_entity_ids": [a], "greeting": greeting}).json()["request_id"]
    client.post("/chat/respond", json={"entity_id": a, "request_id": rid, "accept": True, "message": msg})
    chat_state.tick(now=time.time())
    return chat_state._chat_requests[rid]["chat_room_id"]


def test_profiles_values_and_metrics_echo(client, monkeypatch):
    assert chat_profile.current()["name"] == "b9" and chat_state.MAX_MESSAGES == 16 and chat_state.CHAT_COOLDOWN_PLAYER == 60 and chat_state.CHAT_COOLDOWN_PAIR == 15
    m = client.get("/admin/metrics").json()["chat_profile"]
    assert m["name"] == "b9" and m["max_messages"] == 16 and m["creator_first"] is False
    chat_profile.set_profile("ait")
    assert chat_state.MAX_MESSAGES == 8 and chat_state.WALK_TIMEOUT == 60 and chat_state.CHAT_COOLDOWN_PLAYER == 15 and chat_state.CHAT_COOLDOWN_PAIR == 60
    assert client.get("/admin/metrics").json()["chat_profile"]["name"] == "ait"
    chat_profile.set_profile("nolimit")
    assert chat_state.MAX_MESSAGES == 0
    # 环境变量 + overrides
    chat_profile._reset_for_tests()
    monkeypatch.setenv("SANDBOX_CHAT_PROFILE", "ait"); monkeypatch.setenv("SANDBOX_CHAT_OVERRIDES", '{"max_messages": 12}')
    assert chat_profile.current()["max_messages"] == 12 and chat_profile.current()["name"] == "ait"


def test_ait_eight_messages_and_creator_first_and_awkward(client):
    chat_profile.set_profile("ait")
    a, b = _pair(client)
    room = _open_room(client, a, b)                                   # b 发起（creator），招呼 + 接受回复 = 2 条
    assert chat_state._chat_rooms[room]["creator"] == b
    # creator_first：b 还没在房里说第一句（招呼算 b 的消息吗？—— 招呼就是 creator 的第一条，所以 a 可以说）
    r = client.post("/chat/message", json={"entity_id": a, "chat_room_id": room, "content": "我先说"}).json()
    assert r.get("seq")                                               # 招呼语已算 creator 开口
    # 构造一个 creator 没开口的房：清掉消息再试
    rm = chat_state._chat_rooms[room]; rm["messages"].clear(); rm["opened_at"] = time.time()
    r = client.post("/chat/message", json={"entity_id": a, "chat_room_id": room, "content": "我先说"}).json()
    assert r["success"] is False and r["reason"] == "creator_first" and r["wait_s"] > 50
    assert client.post("/chat/message", json={"entity_id": b, "chat_room_id": room, "content": "我来"}).json().get("seq")
    assert client.post("/chat/message", json={"entity_id": a, "chat_room_id": room, "content": "好"}).json().get("seq")
    # 8 条上限（含已有 2 条）
    for i in range(10):
        r = client.post("/chat/message", json={"entity_id": [a, b][i % 2], "chat_room_id": room, "content": f"m{i}"}).json()
        if r.get("room_closed"):
            break
    assert r.get("room_closed") and r["reason"] == "room_limit" and len(rm["messages"]) == 8
    # 冷却：本人 15、同一对 60（人类发起者免冷却，这里直接看函数）
    left = chat_state.chat_cooldown_remaining(a, [b])
    assert 55 < left <= 60, left                                           # 同一对 60 s 是最严的那条
    chat_state._last_pair_end.clear()
    left = chat_state.chat_cooldown_remaining(a, [b])
    assert 10 < left <= 15, left                                           # 只剩本人 15 s
    # awkward_timeout：60 s 没人说话 → 散
    room2 = None
    chat_state._last_chat_end.clear(); chat_state._last_pair_end.clear()
    room2 = _open_room(client, a, b, "again", "ok")
    chat_state.tick(now=time.time() + 30); assert chat_state._chat_rooms[room2]["status"] == "active"
    chat_state.tick(now=time.time() + 61); assert chat_state._chat_rooms[room2]["status"] == "closed"
    assert chat_state._chat_rooms[room2]["events"][-1]["type"] == "awkward_timeout"
    # max_duration 600 s
    chat_state._last_chat_end.clear(); chat_state._last_pair_end.clear()
    room3 = _open_room(client, a, b, "third", "ok")
    chat_state._chat_rooms[room3]["last_message_at"] = time.time() + 10_000       # 让 awkward 不触发
    chat_state.tick(now=time.time() + 601)
    assert chat_state._chat_rooms[room3]["status"] == "closed" and chat_state._chat_rooms[room3]["events"][-1]["type"] == "room_timeout"


def test_nolimit_has_no_cap_and_b9_keeps_16(client):
    chat_profile.set_profile("nolimit")
    a, b = _pair(client)
    room = _open_room(client, a, b)
    for i in range(40):
        r = client.post("/chat/message", json={"entity_id": [a, b][i % 2], "chat_room_id": room, "content": f"m{i}"}).json()
        assert r.get("room_closed") is False
    assert len(chat_state._chat_rooms[room]["messages"]) == 42
    chat_profile.set_profile("b9")
    assert chat_state.MAX_MESSAGES == 16


def test_three_party_room_semantics(client):
    a, b, c = _pair(client, 3)
    rid = client.post("/chat/request", json={"from_entity_id": a, "to_entity_ids": [b, c], "greeting": "都来"}).json()["request_id"]
    client.post("/chat/respond", json={"entity_id": b, "request_id": rid, "accept": True, "message": "来了"})
    client.post("/chat/respond", json={"entity_id": c, "request_id": rid, "accept": True, "message": "我也"})
    chat_state.tick(now=time.time())
    room = chat_state._chat_requests[rid]["chat_room_id"]
    rm = chat_state._chat_rooms[room]
    assert set(rm["participants"]) == {a, b, c} and len(rm["messages"]) == 3                       # 招呼 + 两条接受回复
    # 没有轮次：任何人随时可说；非参与者不能说
    assert client.post("/chat/message", json={"entity_id": c, "chat_room_id": room, "content": "插一句"}).json().get("seq")
    d = join(client, "d")
    assert client.post("/chat/message", json={"entity_id": d, "chat_room_id": room, "content": "我没被邀"}).json()["reason"] == "not_participant"
    # 一人退出后房间继续（两人）；再退一人剩 1 人仍 active（B9 现状）；最后一人退出 all_left
    r = client.post("/chat/exit", json={"entity_id": c, "chat_room_id": room}).json()
    assert r["room_closed"] is False and set(rm["participants"]) == {a, b}
    r = client.post("/chat/exit", json={"entity_id": b, "chat_room_id": room}).json()
    assert r["room_closed"] is False and rm["participants"] == [a] and rm["status"] == "active"
    assert client.post("/chat/message", json={"entity_id": a, "chat_room_id": room, "content": "都走了？"}).json().get("seq")
    assert client.post("/chat/exit", json={"entity_id": a, "chat_room_id": room}).json()["room_closed"] is True
    # room_limit 按房间消息总数计（三人共享 16）
    chat_state._last_chat_end.clear(); chat_state._last_pair_end.clear()
    rid = client.post("/chat/request", json={"from_entity_id": a, "to_entity_ids": [b, c], "greeting": "再来"}).json()["request_id"]
    for p in (b, c):
        client.post("/chat/respond", json={"entity_id": p, "request_id": rid, "accept": True, "message": "好"})
    chat_state.tick(now=time.time()); room = chat_state._chat_requests[rid]["chat_room_id"]
    n = 0
    for i in range(30):
        r = client.post("/chat/message", json={"entity_id": [a, b, c][i % 3], "chat_room_id": room, "content": f"m{i}"}).json()
        n += 1
        if r.get("room_closed"):
            break
    assert r["reason"] == "room_limit" and len(chat_state._chat_rooms[room]["messages"]) == 16 and n == 13


def test_scenario_say_without_room_and_qq_send(client, monkeypatch):
    monkeypatch.setenv("SANDBOX_SCENARIO", "1")
    a = join(client, "鲸仔"); x = client.post("/player/join", json={"name": "克劳蒂娜", "controller": "agent", "profile": {"agent_id": "claudine"}}).json()["playerId"]
    place(a, 41, 26, "up"); place(x, 41, 25, "down")
    r = client.post("/admin/scenario", json={"steps": [{"op": "say", "player": "克劳蒂娜", "text": "昨天你干了什么？"}]}).json()
    assert r["ok"] and r["steps"][0]["detail"]["heard_by"] == [a]
    assert client.get("/agent/perceive", params={"entity_id": a}).json()["nearby_speech"][0]["text"] == "昨天你干了什么？"
    r = client.post("/admin/scenario", json={"steps": [{"op": "qq_send", "from": "克劳蒂娜", "to": a, "text": "餐厅几点开门？"}]}).json()
    assert r["ok"] and r["steps"][0]["detail"]["kind"] == "text" and r["steps"][0]["detail"]["from"] == "claudine"
    assert client.get("/qq/inbox", params={"player": a}).json()["unread_total"] == 1
    r = client.post("/admin/scenario", json={"steps": [{"op": "qq_send", "from": "克劳蒂娜", "group": "g_live", "text": "群"}]}).json()
    assert r["ok"] is False and "not_member" in r["error"]
