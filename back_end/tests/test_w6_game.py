"""W6 任务 3（B18）：游戏机 Object 用假 D 服务。"""
import json

import httpx
import pytest

from game import world_state, external_effects
from tests.conftest import join, action, place

CONSOLE_ID = "game_console_whale"      # (10,11)；站 (9,11) 朝 right
CONSOLE_STAND = (9, 11, "right")


class FakeBrain:
    def __init__(self):
        self.down = False
        self.events = []
        self.ticks = 1234

    def handler(self, req: httpx.Request):
        if self.down:
            raise httpx.ConnectError("down", request=req)
        if req.url.path == "/healthz":
            return httpx.Response(200, json={"ok": True, "ticks": self.ticks, "run_id": "run-7", "last_tick_age_s": 0.4})
        if req.url.path == "/event":
            self.events.append(json.loads(req.content))
            return httpx.Response(200, json={"ok": True})
        if req.url.path == "/metrics":
            return httpx.Response(200, json={"run_id": "run-7", "ticks": self.ticks, "day": 3, "phase": "day",
                                             "health": 120, "hunger": 88, "sanity": 150, "deaths": 0, "extra": "ignored"})
        return httpx.Response(404)


@pytest.fixture
def brain(monkeypatch):
    f = FakeBrain()
    monkeypatch.setattr(external_effects, "GAME_TRANSPORT", httpx.MockTransport(f.handler))
    monkeypatch.setattr(external_effects, "SYNC_STOP", True)
    return f


def _agent(client):
    pid = client.post("/player/join", json={"name": "鲸仔", "controller": "agent", "profile": {"agent_id": "whale"}}).json()["playerId"]
    place(pid, *CONSOLE_STAND)
    return pid


def test_console_type_and_map():
    from game.object_types import OBJECT_TYPES
    t = OBJECT_TYPES["game_console"]
    assert t["prototype"] == "continuous" and t["advertise"]["fun"] >= 80 and t["max_users"] == 1
    assert any(e["type"] == "external" and e["key"] == "game" for e in t["effects"])
    assert any(e["key"] == "energy_regen" and e["value"] < 0 for e in t["effects"])
    o = world_state.get_object_by_id(CONSOLE_ID)
    assert o and world_state.get_zone_at(o["position"]["x"], o["position"]["y"])["arena"] == "storage"


def test_use_starts_session_and_leave_ends(client, brain):
    pid = _agent(client)
    res = action(client, pid, "use")
    assert res["success"] and res["result"]["objectId"] == CONSOLE_ID
    assert res["result"]["stateLabel"] == "鲸仔 玩游戏中"
    p = client.get(f"/player/{pid}").json()
    assert p["state"] == "using" and "gaming" in p["tags"] and p["canMove"] is False  # W8 Q0c：no_move 立刻生效
    g = p["game"]
    assert g["status"] == "playing" and g["brain_run_id"] == "run-7" and g["day"] == 3 and g["phase"] == "day" and "extra" not in g
    assert brain.events == [{"type": "sandbox_session_start", "agent": "whale", "player_id": pid, "ts": g["started_at"], "tick": 1234}]
    st = client.get(f"/player/{pid}/state").json()
    assert st["game"]["status"] == "playing"
    per = client.get("/agent/perceive", params={"entity_id": pid}).json()
    assert per["game"]["status"] == "playing" and per["game"]["health"] == 120
    snap = next(x for x in client.get("/world").json()["players"] if x["id"] == pid)
    assert snap["stateLabel"] == "鲸仔 玩游戏中" and snap["usingObjectId"] == CONSOLE_ID
    assert action(client, pid, "leave")["success"]
    assert [e["type"] for e in brain.events] == ["sandbox_session_start", "sandbox_session_end"]
    assert brain.events[1]["started_at"] == g["started_at"] and brain.events[1]["player_id"] == pid
    p = client.get(f"/player/{pid}").json()
    assert p["game"]["status"] == "ended" and "ended_at" in p["game"] and "gaming" not in p["tags"]
    assert client.get("/agent/perceive", params={"entity_id": pid}).json()["game"]["status"] == "ended"


def test_brain_down_game_unavailable(client, brain):
    pid = _agent(client)
    brain.down = True
    res = action(client, pid, "use")
    assert res["success"] is False and res["reason"] == "game_unavailable" and "error" in res["result"]
    p = world_state._players[pid]
    assert p["usingObjectId"] is None and p.get("game") is None
    assert world_state.get_object_by_id(CONSOLE_ID)["currentUsers"] == 0
    assert world_state.object_cooldown_remaining(pid, CONSOLE_ID) == 0.0
    assert client.get("/agent/perceive", params={"entity_id": pid}).json()["game"] is None


def test_human_can_play_too_and_removal_ends_session(client, brain):
    pid = join(client, "achan")
    place(pid, *CONSOLE_STAND)
    assert action(client, pid, "use")["success"]
    assert brain.events[0]["agent"] == "achan"
    client.delete(f"/player/{pid}/leave")
    assert [e["type"] for e in brain.events] == ["sandbox_session_start", "sandbox_session_end"]


def test_metrics_failure_does_not_block(client, brain):
    pid = _agent(client)
    def handler(req):
        if req.url.path == "/metrics":
            return httpx.Response(500)
        return brain.handler(req)
    external_effects.GAME_TRANSPORT = httpx.MockTransport(handler)
    res = action(client, pid, "use")
    assert res["success"]
    g = world_state._players[pid]["game"]
    assert g["status"] == "playing" and "day" not in g
