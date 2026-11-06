"""B17：GET /ws/world 只读推送——snapshot 与 GET /world 一致，patch 跟随玩家 / 物品 / 聊天变化。"""
import json
import time

import pytest
from fastapi.testclient import TestClient

from game import world_state, chat_state
from tests.conftest import BED_ID, BED_STAND, place, action


def _recv(ws, want_type, timeout=3.0, pred=None):
    """收消息直到遇到 want_type（且 pred 为真），其余丢弃（heartbeat 等）。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        msg = json.loads(ws.receive_text())
        if msg["type"] == want_type and (pred is None or pred(msg)):
            return msg
    raise AssertionError(f"no {want_type} within {timeout}s")


@pytest.fixture
def live():
    from main import app
    with TestClient(app) as c:
        yield c


def test_snapshot_matches_get_world(live):
    pid = live.post("/player/join", json={"name": "w", "controller": "agent", "profile": {"agent_id": "whale"}}).json()["playerId"]
    with live.websocket_connect("/ws/world") as ws:
        snap = json.loads(ws.receive_text())
        assert snap["type"] == "snapshot" and "T" in snap["ts"]
        world = live.get("/world").json()
        for k in ("tiles", "objects", "players"):
            assert snap[k] == world[k], k
        assert {k: v for k, v in snap["worldState"].items() if k != "time"} == {k: v for k, v in world["worldState"].items() if k != "time"}
        assert snap["players"][0]["agent_id"] == "whale"


def test_patches_follow_player_object_and_chat_changes(live):
    a = live.post("/player/join", json={"name": "a"}).json()["playerId"]
    with live.websocket_connect("/ws/world") as ws:
        _recv(ws, "snapshot")
        # 新玩家 → upsert
        b = live.post("/player/join", json={"name": "b"}).json()["playerId"]
        p = _recv(ws, "patch", pred=lambda m: any(x["id"] == b for x in m.get("players", {}).get("upsert", [])))
        up = next(x for x in p["players"]["upsert"] if x["id"] == b)
        assert set(up) == {"id", "name", "position", "facing", "state", "controller", "online", "agent_id"}
        # 移动 → position 变化
        action(live, a, "move", {"direction": "right"})
        p = _recv(ws, "patch", pred=lambda m: any(x["id"] == a for x in m.get("players", {}).get("upsert", [])))
        assert next(x for x in p["players"]["upsert"] if x["id"] == a)["position"] == live.get(f"/player/{a}").json()["position"]
        # 用床 → objects 变化 + state=using
        place(a, *BED_STAND)
        assert action(live, a, "use")["success"]
        p = _recv(ws, "patch", pred=lambda m: any(o["id"] == BED_ID for o in m.get("objects", [])))
        assert next(o for o in p["objects"] if o["id"] == BED_ID) == {"id": BED_ID, "currentUsers": 1, "userList": [a]}
        # 聊天 → chat 推送（含招呼与回复），事件也推
        rid = live.post("/chat/request", json={"from_entity_id": b, "to_entity_ids": [a], "greeting": "hi"}).json()["request_id"]
        place(b, *BED_STAND)
        live.post("/chat/respond", json={"entity_id": a, "request_id": rid, "accept": True, "message": "yo"})
        p = _recv(ws, "patch", pred=lambda m: "chat" in m)
        contents = [c["content"] for c in p["chat"] if c["kind"] == "message"]
        assert contents == ["hi", "yo"]
        room = p["chat"][0]["chat_room_id"]
        assert set(p["chat"][0]["participants"]) == {a, b} and p["chat"][0]["from_name"] == "b"
        live.post("/chat/message", json={"entity_id": a, "chat_room_id": room, "content": "第三句"})
        p = _recv(ws, "patch", pred=lambda m: "chat" in m)
        assert [c["content"] for c in p["chat"]] == ["第三句"]
        live.post("/chat/exit", json={"entity_id": a, "chat_room_id": room})
        p = _recv(ws, "patch", pred=lambda m: any(c["kind"] == "event" for c in m.get("chat", [])))
        assert [c["type"] for c in p["chat"] if c["kind"] == "event"] == ["player_exit"]
        # 玩家离开 → remove
        live.delete(f"/player/{b}/leave")
        p = _recv(ws, "patch", pred=lambda m: b in m.get("players", {}).get("remove", []))
        assert b in p["players"]["remove"]


def test_ws_is_read_only_and_ignores_client_messages(live):
    a = live.post("/player/join", json={"name": "a"}).json()["playerId"]
    pos = live.get(f"/player/{a}").json()["position"]
    with live.websocket_connect("/ws/world") as ws:
        _recv(ws, "snapshot")
        ws.send_text(json.dumps({"type": "action", "entityId": a, "action": {"type": "move", "payload": {"direction": "up"}}}))
        ws.send_text("garbage")
        time.sleep(0.3)
        assert live.get(f"/player/{a}").json()["position"] == pos      # 没有任何写入
        # 连接仍然活着：时间推进会带来 worldState.time patch 或 heartbeat
        msg = json.loads(ws.receive_text())
        assert msg["type"] in ("patch", "heartbeat")


def test_time_patch_only_changed_fields(live):
    with live.websocket_connect("/ws/world") as ws:
        _recv(ws, "snapshot")
        p = _recv(ws, "patch", pred=lambda m: "worldState" in m)
        assert set(p["worldState"]) <= {"time", "period", "date"}
        live.post("/time/speed", json={"value": 7})
        p = _recv(ws, "patch", pred=lambda m: "speed" in m.get("worldState", {}))
        assert p["worldState"]["speed"] == 7.0


def test_multiple_clients_and_metrics(live):
    with live.websocket_connect("/ws/world") as w1, live.websocket_connect("/ws/world") as w2:
        _recv(w1, "snapshot"); _recv(w2, "snapshot")
        assert live.get("/admin/metrics").json()["ws_clients"] == 2
        pid = live.post("/player/join", json={"name": "x"}).json()["playerId"]
        for w in (w1, w2):
            _recv(w, "patch", pred=lambda m: any(x["id"] == pid for x in m.get("players", {}).get("upsert", [])))
    time.sleep(0.2)
    m = live.get("/admin/metrics").json()
    assert m["ws_clients"] == 0 and m["tick_count"] > 0 and "tick_duration_ms" in m and "tick_gap_ms" in m
