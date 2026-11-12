"""W8 Q0e：human 120 s 无输入标 away；away 不算在场、不接受邀请、ws 带 away；床类无冷却。"""
import json
import time

import pytest

from game import world_state, ticker, chat_state
from tests.conftest import BED_ID, BED_STAND, join, action, place


def _idle(pid, seconds=121):
    world_state._last_input[pid] = time.time() - seconds


def test_human_away_after_120s_and_input_clears(client, fake_clock):
    h = join(client, "阿蝉"); a = client.post("/player/join", json={"name": "w", "controller": "agent", "profile": {"agent_id": "whale"}}).json()["playerId"]
    ticker.tick_once(checkpoint=False)
    assert world_state._players[h]["away"] is False
    _idle(h, 119); ticker.tick_once(checkpoint=False)
    assert world_state._players[h]["away"] is False
    _idle(h, 121); _idle(a, 999); ticker.tick_once(checkpoint=False)
    assert world_state._players[h]["away"] is True and world_state._players[a]["away"] is False     # agent 永不 away
    p = client.get(f"/player/{h}").json()                        # GET /player 是人类心跳 = 输入 → 清 away
    assert p["away"] is False
    _idle(h); ticker.tick_once(checkpoint=False); assert world_state._players[h]["away"] is True
    action(client, h, "turn", {"direction": "up"})               # 动作也是输入
    assert world_state._players[h]["away"] is False
    _idle(h); ticker.tick_once(checkpoint=False)
    client.post(f"/player/{h}/heartbeat")
    assert world_state._players[h]["away"] is False


def test_away_player_not_present_in_perceive_nearby_and_cannot_be_invited(client):
    me = join(client, "me"); other = join(client, "other")
    place(me, 6, 9, "down"); place(other, 7, 9, "down")
    assert [p["id"] for p in client.get("/agent/perceive", params={"entity_id": me}).json()["players_in_view"]] == [other]
    assert [p["entity_id"] for p in client.get("/chat/nearby", params={"entity_id": me}).json()["players"]] == [other]
    _idle(other); ticker.tick_once(checkpoint=False)
    assert world_state._players[other]["away"] is True
    per = client.get("/agent/perceive", params={"entity_id": me}).json()
    assert per["players_in_view"] == [] and per["needs"]["closeness"] == {}
    assert client.get("/chat/nearby", params={"entity_id": me}).json()["players"] == []
    r = client.post("/chat/request", json={"from_entity_id": me, "to_entity_ids": [other], "greeting": "hi"}).json()
    assert r["success"] is False and r["reason"] == "target_away" and r["away"] == [other]
    # 自己 away 时发邀请：发邀请本身是输入 → 先清 away，再正常建请求
    _idle(me); ticker.tick_once(checkpoint=False); assert world_state._players[me]["away"] is True
    world_state._players[other]["away"] = False; world_state._last_input[other] = time.time()
    r = client.post("/chat/request", json={"from_entity_id": me, "to_entity_ids": [other], "greeting": "hi"}).json()
    assert r["success"] is True and world_state._players[me]["away"] is False
    # GET /world 与 /player 都带 away
    assert all("away" in p for p in client.get("/world").json()["players"])
    assert client.get(f"/player/{other}").json()["away"] is False


def test_ws_upsert_carries_away():
    from fastapi.testclient import TestClient
    from main import app
    with TestClient(app) as c:
        h = c.post("/player/join", json={"name": "h"}).json()["playerId"]
        with c.websocket_connect("/ws/world") as ws:
            snap = json.loads(ws.receive_text())
            assert snap["players"][0]["away"] is False
            _idle(h)
            t0 = time.time(); got = None
            while time.time() - t0 < 3 and got is None:
                m = json.loads(ws.receive_text())
                for u in m.get("players", {}).get("upsert", []) if m["type"] == "patch" else []:
                    if u["id"] == h and u.get("away") is True:
                        got = u
            assert got is not None


def test_beds_have_no_cooldown_but_others_do(client, fake_clock):
    from game.object_types import OBJECT_TYPES
    assert OBJECT_TYPES["bed"]["cooldown_s"] == 0 and OBJECT_TYPES["bed_21"]["cooldown_s"] == 0 and OBJECT_TYPES["fishing_spot"]["cooldown_s"] == 0   # v1.1：钓位也无冷却（每日 3 h 上限）
    pid = join(client, "w")
    place(pid, *BED_STAND)
    assert action(client, pid, "use")["success"]
    assert action(client, pid, "leave")["success"]
    res = action(client, pid, "use")                              # 床：立刻可再用
    assert res["success"], res
    assert world_state.object_cooldown_remaining(pid, BED_ID) == 0.0
    action(client, pid, "leave")
    from datetime import datetime
    from game.time_state import GAME_TZ
    fake_clock.t = datetime(2026, 11, 10, 12, 0, tzinfo=GAME_TZ).timestamp()
    place(pid, 52, 19, "right")
    assert action(client, pid, "use")["success"]; assert action(client, pid, "leave")["success"]
    assert action(client, pid, "use")["success"]                               # v1.1：钓位占用语义，立刻可回
    action(client, pid, "leave"); place(pid, 42, 35, "up")
    assert action(client, pid, "use")["success"]; assert action(client, pid, "leave")["success"]
    assert action(client, pid, "use")["reason"] == "object_cooldown"          # 浴缸仍 30 min
