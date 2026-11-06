"""B9：walking_over（target_arena_id）、单人邀请超时、chat_cooldown、room_limit。"""
import time

import pytest

from game import chat_state, world_state, ticker
from tests.conftest import join, place


def _req(client, a, b, greeting="hi"):
    return client.post("/chat/request", json={"from_entity_id": a, "to_entity_ids": [b], "greeting": greeting}).json()


def _accept(client, b, rid, msg="ok"):
    return client.post("/chat/respond", json={"entity_id": b, "request_id": rid, "accept": True, "message": msg}).json()


def test_accept_enters_walking_over_with_target_arena(client):
    a = join(client, "a"); b = join(client, "b")
    place(a, 6, 9, "down"); place(b, 20, 10, "down")           # a 在小仓库，b 在厨房
    r = _req(client, a, b)
    assert r["success"] is True and r["request_id"]
    rid = r["request_id"]
    res = _accept(client, b, rid)
    assert res["status"] == "walking_over" and res["chat_room_id"] is None
    assert res["target_arena_id"] == "storage" and set(res["participants"]) == {a, b}
    st = client.get(f"/chat/request/{rid}").json()
    assert st["status"] == "walking_over" and st["target_arena_id"] == "storage" and st["chat_room_id"] is None
    for pid in (a, b):
        assert world_state._players[pid]["state"] == "walking_over"
        assert world_state._players[pid]["canMove"] is True            # 走过去期间可以移动
    # b 走到 a 旁边（同 arena、曼哈顿 ≤ 1）→ 下一个 tick 建房
    place(b, 7, 9, "left")
    assert world_state._players[b]["state"] == "walking_over"          # 移动不清掉 walking_over
    chat_state.tick()
    st = client.get(f"/chat/request/{rid}").json()
    assert st["status"] == "active" and st["chat_room_id"]
    room = client.get(f"/chat/room/{st['chat_room_id']}", params={"entity_id": a}).json()
    assert [m["content"] for m in room["messages"]] == ["hi", "ok"]
    for pid in (a, b):
        assert world_state._players[pid]["state"] == "talking"


def test_walking_over_same_arena_but_not_adjacent_waits_then_times_out(client):
    a = join(client, "a"); b = join(client, "b")
    place(a, 4, 9, "down"); place(b, 9, 9, "down")              # 同在小仓库，距离 5
    rid = _req(client, a, b)["request_id"]
    _accept(client, b, rid)
    chat_state.tick()
    assert chat_state._chat_requests[rid]["status"] == "walking_over"
    chat_state.tick(now=time.time() + chat_state.WALK_TIMEOUT + 1)   # 30 s 到 → 直接建房
    assert chat_state._chat_requests[rid]["status"] == "active"


def test_walking_over_participant_removed_expires(client):
    a = join(client, "a"); b = join(client, "b")
    place(a, 4, 9, "down"); place(b, 9, 9, "down")
    rid = _req(client, a, b)["request_id"]
    _accept(client, b, rid)
    client.delete(f"/player/{b}/leave")
    chat_state.tick(now=time.time() + 31)
    assert chat_state._chat_requests[rid]["status"] == "expired"
    assert world_state._players[a]["state"] == "idle"


def test_single_invite_times_out_after_60s(client):
    a = join(client, "a"); b = join(client, "b")
    rid = _req(client, a, b)["request_id"]
    chat_state.tick(now=time.time() + 59)
    assert client.get(f"/chat/request/{rid}").json()["status"] == "pending"
    chat_state.tick(now=time.time() + 61)
    assert client.get(f"/chat/request/{rid}").json()["status"] == "expired"
    assert client.get("/chat/pending", params={"entity_id": b}).json()["requests"] == []
    # 过期后再响应无效
    assert _accept(client, b, rid)["status"] == "rejected"


def test_multi_invite_timeout_with_one_acceptor_goes_walking_over(client):
    a = join(client, "a"); b = join(client, "b"); c = join(client, "c")
    rid = client.post("/chat/request", json={"from_entity_id": a, "to_entity_ids": [b, c], "greeting": "hey"}).json()["request_id"]
    assert _accept(client, b, rid)["status"] == "waiting"
    chat_state.tick(now=time.time() + 61)
    req = chat_state._chat_requests[rid]
    assert req["status"] == "walking_over" and set(req["participants"]) == {a, b} and c in req["rejected_ids"]


def test_ticker_drives_chat_tick(client, fake_clock):
    a = join(client, "a"); b = join(client, "b")
    rid = _req(client, a, b)["request_id"]
    _accept(client, b, rid)                                      # 两人同格 → 相邻
    ticker.tick_once(checkpoint=False)
    assert chat_state._chat_requests[rid]["status"] == "active"


def _make_room(client, a, b):
    rid = _req(client, a, b)["request_id"]
    _accept(client, b, rid)
    chat_state.tick()
    return client.get(f"/chat/request/{rid}").json()["chat_room_id"]


def _join_agent(client, name):
    pid = client.post("/player/join", json={"name": name, "controller": "agent", "profile": {"agent_id": name}}).json()["playerId"]
    place(pid, 6, 9, "down")
    return pid


def test_chat_cooldown_after_exit(client):
    # W6 任务 4：human 发起无冷却，所以这里用 agent 验证冷却
    a = _join_agent(client, "a"); b = _join_agent(client, "b"); c = _join_agent(client, "c")
    room = _make_room(client, a, b)
    assert client.post("/chat/exit", json={"entity_id": a, "chat_room_id": room}).json() == {"room_closed": False}
    # a 刚退出：本人 60 s 冷却
    r = _req(client, a, c)
    assert r["success"] is False and r["reason"] == "chat_cooldown" and r["request_id"] is None
    assert 59 <= r["cooldown_remaining"] <= 60
    # c 邀请 a 也被挡（受邀方冷却）
    assert _req(client, c, a)["reason"] == "chat_cooldown"
    # b 还在房间里没退出：b 本人无冷却，但 (a,b) 配对 15 s 内冷却
    client.post("/chat/exit", json={"entity_id": b, "chat_room_id": room})
    assert chat_state.chat_cooldown_remaining(b, [c]) == pytest.approx(60, abs=1)
    assert chat_state.chat_cooldown_remaining(b, [a], now=time.time() + 61) == 0.0
    assert chat_state.chat_cooldown_remaining(b, [a], now=time.time() + 50) > 0     # a 的 60 s 仍在
    # 配对冷却单独生效：假设 a、b 的本人冷却已过但配对 15 s 未过
    chat_state._last_chat_end.clear()
    chat_state._last_pair_end[frozenset((a, b))] = time.time()
    assert 14 <= chat_state.chat_cooldown_remaining(a, [b]) <= 15
    assert chat_state.chat_cooldown_remaining(a, [c]) == 0.0
    assert chat_state.chat_cooldown_remaining(a, [b], now=time.time() + 16) == 0.0


def test_room_limit_closes_room_and_frees_players(client):
    a = _join_agent(client, "a"); b = _join_agent(client, "b")
    room = _make_room(client, a, b)                              # 已有 2 条（招呼 + 回复）
    last = None
    for i in range(chat_state.MAX_MESSAGES - 2):
        last = client.post("/chat/message", json={"entity_id": a if i % 2 else b, "chat_room_id": room, "content": f"m{i}"}).json()
        if i < chat_state.MAX_MESSAGES - 3:
            assert last["room_closed"] is False
    assert last["room_closed"] is True and last["reason"] == "room_limit"
    r = client.get(f"/chat/room/{room}", params={"entity_id": a}).json()
    assert r["status"] == "closed" and r["participants"] == []
    assert [e["type"] for e in r["events"]] == ["room_limit"]
    assert len(r["messages"]) == chat_state.MAX_MESSAGES
    for pid in (a, b):
        p = world_state._players[pid]
        assert p["state"] == "idle" and not any(x["key"] == "chat_active" for x in p["buffs"])
    # 关闭后发言 404；双方都进入冷却
    assert client.post("/chat/message", json={"entity_id": a, "chat_room_id": room, "content": "x"}).status_code == 404
    assert _req(client, a, b)["reason"] == "chat_cooldown"


def test_cooldowns_survive_checkpoint(client):
    from game import persistence
    a = join(client, "a"); b = join(client, "b")
    room = _make_room(client, a, b)
    client.post("/chat/exit", json={"entity_id": a, "chat_room_id": room})
    persistence.save_checkpoint()
    chat_state._reset_for_tests(); world_state._reset_for_tests()
    persistence.load_checkpoint()
    assert chat_state.chat_cooldown_remaining(a, [b]) > 50
    assert chat_state._chat_requests and all("target_arena_id" in r for r in chat_state._chat_requests.values())


def test_request_status_shape_additive(client):
    a = join(client, "a"); b = join(client, "b")
    rid = _req(client, a, b)["request_id"]
    st = client.get(f"/chat/request/{rid}").json()
    assert {"request_id", "status", "chat_room_id", "accepted_ids", "rejected_ids"} <= set(st)   # 旧字段不变
    assert "target_arena_id" in st and "participants" in st
