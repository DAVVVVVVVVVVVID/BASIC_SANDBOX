"""W6 任务 4：作者（human）与鲸仔对话：发起无冷却，消息进 chat JSONL 且 controller=human。"""
import time

from game import chat_state, chat_log, world_state
from tests.conftest import join, place


def _whale(client):
    pid = client.post("/player/join", json={"name": "鲸仔", "controller": "agent", "profile": {"agent_id": "whale"}}).json()["playerId"]
    place(pid, 6, 9, "down")
    return pid


def test_human_initiates_without_cooldown_and_logged(client):
    w = _whale(client); me = join(client, "阿蝉")
    place(me, 7, 9, "left")
    rid = client.post("/chat/request", json={"from_entity_id": me, "to_entity_ids": [w], "greeting": "鲸仔，晚饭吃什么？"}).json()
    assert rid["success"]
    res = client.post("/chat/respond", json={"entity_id": w, "request_id": rid["request_id"], "accept": True, "message": "想吃鱼"}).json()
    assert res["status"] == "walking_over"
    chat_state.tick()
    room = client.get(f"/chat/request/{rid['request_id']}").json()["chat_room_id"]
    assert room
    client.post("/chat/message", json={"entity_id": me, "chat_room_id": room, "content": "那我去钓"})
    client.post("/chat/exit", json={"entity_id": me, "chat_room_id": room})
    # 作者刚退出：human 发起不受冷却约束，鲸仔（agent）发起仍受
    r2 = client.post("/chat/request", json={"from_entity_id": me, "to_entity_ids": [w], "greeting": "再聊两句"}).json()
    assert r2["success"] is True and r2["request_id"]
    r3 = client.post("/chat/request", json={"from_entity_id": w, "to_entity_ids": [me], "greeting": "等等"}).json()
    assert r3["success"] is False and r3["reason"] == "chat_cooldown"
    msgs = [m for m in chat_log.read_log(kind="message") if m["room_id"] == room]
    assert [(m["from_name"], m["text"], m["controller"]) for m in msgs] == \
        [("阿蝉", "鲸仔，晚饭吃什么？", "human"), ("鲸仔", "想吃鱼", "agent"), ("阿蝉", "那我去钓", "human")]
    assert all(m["town"] == "main" for m in msgs)
    assert client.get("/history/chat", params={"room": room, "kind": "message"}).json() == msgs
    # human 的 GET /player 仍刷心跳（E 操控页的老路径）
    world_state._last_seen[me] = 0
    client.get(f"/player/{me}")
    assert world_state._last_seen[me] > 0
