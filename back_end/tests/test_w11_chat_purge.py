"""W11 维护 Q2：结束的聊天邀请 / 关闭的房间按时限从内存清掉（JSONL 仍是永久记录）。"""
import time

from game import chat_state
from tests.conftest import join, place


def _pair(client):
    a = join(client, "a"); b = join(client, "b")
    place(a, 3, 5, "up"); place(b, 4, 5, "up")
    return a, b


def test_finished_requests_and_closed_rooms_are_purged(client, fake_clock):
    a, b = _pair(client)
    now0 = time.time()                                       # chat_state 的邀请 / 关房时刻用墙钟，不走 fake_clock
    rid = client.post("/chat/request", json={"from_entity_id": b, "to_entity_ids": [a], "greeting": "hi"}).json()["request_id"]
    client.post("/chat/respond", json={"entity_id": a, "request_id": rid, "accept": True, "message": "yo"})
    chat_state.tick(now=now0)                                                                                          # walking_over → 建房
    room = chat_state._chat_requests[rid].get("chat_room_id")
    assert room and chat_state._chat_rooms[room]["status"] == "active"
    client.post("/chat/exit", json={"entity_id": a, "chat_room_id": room})
    client.post("/chat/exit", json={"entity_id": b, "chat_room_id": room})                                             # 都走了才关房
    assert chat_state._chat_rooms[room]["status"] == "closed" and chat_state._chat_rooms[room]["closed_at"]
    # 拒绝的邀请（人类发起不受冷却）
    r2 = client.post("/chat/request", json={"from_entity_id": b, "to_entity_ids": [a], "greeting": "again"}).json()
    rid2 = r2["request_id"]
    resp = client.post("/chat/respond", json={"entity_id": a, "request_id": rid2, "accept": False, "message": "不聊"}).json()
    assert chat_state._chat_requests[rid2]["status"] == "rejected", (r2, resp)
    chat_state.tick(now=now0)
    assert rid in chat_state._chat_requests and rid2 in chat_state._chat_requests and room in chat_state._chat_rooms   # 还没到时限
    chat_state.tick(now=now0 + 3601)
    assert rid not in chat_state._chat_requests and rid2 not in chat_state._chat_requests                               # 1 h 后邀请清掉
    assert room in chat_state._chat_rooms and client.get(f"/chat/room/{room}").status_code == 200                      # 房间还在
    chat_state.tick(now=now0 + 86401)
    assert room not in chat_state._chat_rooms and room not in chat_state._MSG_SEQ_COUNTER                             # 24 h 后房间清掉
    # 活跃房间 / pending 邀请不受影响
    rid3 = client.post("/chat/request", json={"from_entity_id": b, "to_entity_ids": [a], "greeting": "x"}).json()["request_id"]
    chat_state.tick(now=time.time())                                                                                   # 刚发的 pending 不受影响
    assert rid3 in chat_state._chat_requests


def test_old_checkpoint_closed_room_without_closed_at(client, fake_clock):
    chat_state._chat_rooms["old"] = {"chat_room_id": "old", "participants": [], "messages": [], "events": [], "status": "closed"}
    chat_state.tick(now=fake_clock.t)
    assert chat_state._chat_rooms["old"]["closed_at"] == fake_clock.t                                                  # 第一次见到：从现在起算
    chat_state.tick(now=fake_clock.t + 86400)
    assert "old" not in chat_state._chat_rooms
