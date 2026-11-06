"""W4 任务 1：§3.11 五处契约小修。"""
import importlib
import os

import pytest

from game import world_state
from tests.conftest import STREAM_STAND, join, action, place


def _agent(client, agent_id="whale"):
    return client.post("/player/join", json={"name": "鲸仔", "controller": "agent", "profile": {"agent_id": agent_id}}).json()["playerId"]


# ① players[] 带 agent_id
def test_world_players_carry_agent_id(client):
    a = _agent(client); h = join(client, "h")
    players = {p["id"]: p for p in client.get("/world").json()["players"]}
    assert players[a]["agent_id"] == "whale" and players[a]["controller"] == "agent"
    assert players[h]["agent_id"] is None
    assert {"id", "name", "position", "facing", "state", "controller", "online", "agent_id"} <= set(players[a])


# ② perceive.needs.closeness = {entity_id: {name, tier}}，不给数值
def test_perceive_closeness_is_name_tier_not_number(client):
    me = join(client, "me"); other = join(client, "other")
    place(me, 6, 9, "down"); place(other, 7, 9, "down")
    world_state._players[me]["closeness"] = {other: 45.5}
    needs = client.get("/agent/perceive", params={"entity_id": me}).json()["needs"]
    assert needs["closeness"] == {other: {"name": "other", "tier": "熟悉"}}
    def walk(x):
        if isinstance(x, dict):
            for v in x.values(): yield from walk(v)
        elif isinstance(x, list):
            for v in x: yield from walk(v)
        else:
            yield x
    assert not any(isinstance(v, (int, float)) and not isinstance(v, bool) for v in walk(needs["closeness"]))


# ③ 人类玩家用直播台 → live_unavailable（详见 test_external_effects.test_stream_desk_human_live_unavailable）
def test_human_stream_desk_live_unavailable_even_with_sync_off(client):
    pid = join(client, "achan")
    place(pid, *STREAM_STAND)
    res = action(client, pid, "use")
    assert res["success"] is False and res["reason"] == "live_unavailable"


# ④ CORS 白名单走环境变量
def test_cors_origins_from_env(monkeypatch):
    monkeypatch.setenv("SANDBOX_CORS_ORIGINS", "http://192.168.2.17:5173, http://localhost:5174")
    import main as m
    m2 = importlib.reload(m)
    cors = next(mw for mw in m2.app.user_middleware if mw.cls.__name__ == "CORSMiddleware")
    assert cors.kwargs["allow_origins"] == ["http://192.168.2.17:5173", "http://localhost:5174"]
    monkeypatch.delenv("SANDBOX_CORS_ORIGINS")
    m3 = importlib.reload(m2)
    cors = next(mw for mw in m3.app.user_middleware if mw.cls.__name__ == "CORSMiddleware")
    assert "http://localhost:5173" in cors.kwargs["allow_origins"]


def test_cors_header_applied(client, monkeypatch):
    r = client.options("/world", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
    r = client.options("/world", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") is None


# ⑤ /effects 接受并记录 event
def test_effects_accepts_and_records_event(client):
    pid = _agent(client)
    body = {"scene": "live", "source": "self", "event": "viewer_praised",
            "effects": [{"type": "instant_effect", "key": "mood", "value": 10},
                        {"type": "closeness_delta", "target": "viewer_12345", "value": 2},
                        {"type": "buff", "key": "emotion_tag", "tag": "smug", "mode": "timed", "duration": 40000}]}
    r = client.post(f"/player/{pid}/effects", json=body)
    assert r.status_code == 200
    d = r.json()
    assert d["event"] == "viewer_praised" and d["applied"] == 3
    st = client.get(f"/player/{pid}/state").json()
    assert st["recent_events"][-1]["event"] == "viewer_praised"
    assert st["recent_events"][-1]["source"] == "self" and st["recent_events"][-1]["n_effects"] == 3
    # 不带 event 也行（向后兼容）
    r = client.post(f"/player/{pid}/effects", json={"effects": []})
    assert r.status_code == 200 and r.json()["event"] is None
    assert len(client.get(f"/player/{pid}/state").json()["recent_events"]) == 2
