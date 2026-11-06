"""W5 任务 1：聊天 append-only JSONL，与 ws chat 推送一致，重启不丢。"""
import json
import time

import pytest
from fastapi.testclient import TestClient

from game import chat_state, chat_log, world_state, persistence
from game.paths import data_dir
from tests.conftest import join, place


def _lines():
    out = []
    for f in sorted((data_dir() / "chat").glob("*.jsonl")):
        out += [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    return out


def _room(client, a, b):
    rid = client.post("/chat/request", json={"from_entity_id": a, "to_entity_ids": [b], "greeting": "hi"}).json()["request_id"]
    client.post("/chat/respond", json={"entity_id": b, "request_id": rid, "accept": True, "message": "yo"})
    chat_state.tick()
    return client.get(f"/chat/request/{rid}").json()["chat_room_id"]


def test_messages_and_events_written_one_line_each(client):
    a = join(client, "a"); b = client.post("/player/join", json={"name": "b", "controller": "agent", "profile": {"agent_id": "whale"}}).json()["playerId"]
    room = _room(client, a, b)
    client.post("/chat/message", json={"entity_id": b, "chat_room_id": room, "content": "第三句"})
    client.post("/chat/exit", json={"entity_id": a, "chat_room_id": room})
    client.post("/chat/exit", json={"entity_id": b, "chat_room_id": room})
    rows = _lines()
    kinds = [(r["kind"], r.get("event")) for r in rows]
    assert kinds == [("event", "room_open"), ("message", None), ("message", None), ("message", None),
                     ("event", "player_exit"), ("event", "player_exit"), ("event", "room_close")]
    msgs = [r for r in rows if r["kind"] == "message"]
    assert [m["text"] for m in msgs] == ["hi", "yo", "第三句"]
    assert msgs[0] == {**msgs[0], "room_id": room, "seq": 1, "from": a, "from_name": "a", "to": [b], "controller": "human"}
    assert msgs[2]["controller"] == "agent" and msgs[2]["to"] == [a]
    for r in rows:
        assert "ts" in r and "game_time" in r and "T" in r["game_time"]
    assert rows[-1]["reason"] == "all_left"
    # 只读回放
    got = client.get("/history/chat", params={"room": room}).json()
    assert got == rows
    assert [r["text"] for r in client.get("/history/chat", params={"kind": "message"}).json()] == ["hi", "yo", "第三句"]
    assert client.get("/history/chat", params={"since": "2999-01-01"}).json() == []


def test_room_limit_and_expiry_events(client):
    a = join(client, "a"); b = join(client, "b"); c = join(client, "c")
    room = _room(client, a, b)
    for i in range(chat_state.MAX_MESSAGES - 2):
        client.post("/chat/message", json={"entity_id": a if i % 2 else b, "chat_room_id": room, "content": f"m{i}"})
    ev = [r["event"] for r in _lines() if r["kind"] == "event"]
    assert ev[-2:] == ["room_limit", "room_close"]
    assert len([r for r in _lines() if r["kind"] == "message" and r["room_id"] == room]) == chat_state.MAX_MESSAGES
    rid = client.post("/chat/request", json={"from_entity_id": c, "to_entity_ids": [a], "greeting": "x"}).json()
    # a 在冷却 → 直接拒绝（不产生请求）；用 c→b 之外的新人：c 邀请 c? 用过期路径
    chat_state._last_chat_end.clear(); chat_state._last_pair_end.clear()
    rid = client.post("/chat/request", json={"from_entity_id": c, "to_entity_ids": [a], "greeting": "x"}).json()["request_id"]
    chat_state.tick(now=time.time() + 61)
    last = _lines()[-1]
    assert last["event"] == "request_expired" and last["request_id"] == rid and set(last["participants"]) == {c, a}
    rid2 = client.post("/chat/request", json={"from_entity_id": c, "to_entity_ids": [b], "greeting": "x"}).json()["request_id"]
    client.post("/chat/respond", json={"entity_id": b, "request_id": rid2, "accept": False, "message": ""})
    assert _lines()[-1]["event"] == "request_rejected"


def test_jsonl_matches_ws_chat_stream():
    from main import app
    with TestClient(app) as c:
        a = c.post("/player/join", json={"name": "a"}).json()["playerId"]
        b = c.post("/player/join", json={"name": "b"}).json()["playerId"]
        with c.websocket_connect("/ws/world") as ws:
            json.loads(ws.receive_text())
            room = _room(c, a, b)
            c.post("/chat/message", json={"entity_id": a, "chat_room_id": room, "content": "第三句"})
            c.post("/chat/exit", json={"entity_id": b, "chat_room_id": room})
            got = []
            t0 = time.time()
            while time.time() - t0 < 3 and len(got) < 4:
                m = json.loads(ws.receive_text())
                if m["type"] == "patch" and "chat" in m:
                    got += m["chat"]
        ws_msgs = [(x["seq"], x["content"], x["from_name"]) for x in got if x["kind"] == "message"]
        ws_events = [x["type"] for x in got if x["kind"] == "event"]
        log_msgs = [(r["seq"], r["text"], r["from_name"]) for r in chat_log.read_log(kind="message") if r["room_id"] == room]
        assert ws_msgs == log_msgs == [(1, "hi", "a"), (2, "yo", "b"), (3, "第三句", "a")]
        assert ws_events == ["player_exit"]
        assert [r["event"] for r in chat_log.read_log(kind="event") if r.get("room_id") == room][:2] == ["room_open", "player_exit"]


def test_chat_log_survives_restart(client):
    a = join(client, "a"); b = join(client, "b")
    room = _room(client, a, b)
    n = len(_lines())
    persistence.save_checkpoint()
    world_state._reset_for_tests(); chat_state._reset_for_tests(); chat_log._reset_for_tests()
    persistence.load_checkpoint()
    assert len(_lines()) == n                                             # 文件原样
    assert client.get("/history/chat", params={"room": room, "kind": "message"}).json()[0]["text"] == "hi"
    # 重启后继续写同一 room，seq 接着来
    client.post("/chat/message", json={"entity_id": a, "chat_room_id": room, "content": "重启后"})
    last = _lines()[-1]
    assert last["text"] == "重启后" and last["seq"] == 3


def test_truncated_line_skipped(client):
    a = join(client, "a"); b = join(client, "b")
    _room(client, a, b)
    f = next((data_dir() / "chat").glob("*.jsonl"))
    with open(f, "a", encoding="utf-8") as fh:
        fh.write('{"kind": "message", "ts": "2026-11-06T00:00:00.000"')
    assert len(chat_log.read_log()) == 3
