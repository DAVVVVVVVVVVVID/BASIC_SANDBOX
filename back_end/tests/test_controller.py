"""B6：JoinRequest.controller / profile、agent 不被清理只标 online=False、POST /player/rejoin。"""
import time

import pytest

from game import world_state, ticker
from tests.conftest import join, action


def _join_agent(client, name="鲸仔", profile=None):
    body = {"name": name, "controller": "agent"}
    if profile is not None:
        body["profile"] = profile
    r = client.post("/player/join", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_join_with_controller_and_profile(client):
    data = _join_agent(client, profile={"E": 80, "N": 55, "agent_id": "whale"})
    p = data["player"]
    assert p["controller"] == "agent" and p["online"] is True
    assert p["mood"] == pytest.approx(69.5) and p["mood_base"] == pytest.approx(69.5)
    assert p["agent_id"] == "whale"
    assert p["scene"] == "sandbox"


def test_join_defaults_and_validation(client):
    r = client.post("/player/join", json={"name": "h"}).json()
    assert r["player"]["controller"] == "human" and r["player"]["agent_id"] is None
    assert client.post("/player/join", json={"name": "x", "controller": "robot"}).status_code == 400
    # agent 不带 agent_id：取 name 的 slug（假设）
    assert _join_agent(client, name="Whale Kid")["player"]["agent_id"] == "whale_kid"


def test_stale_agent_marked_offline_not_removed(client):
    pid = _join_agent(client)["playerId"]
    hid = join(client, "human")
    for x in (pid, hid):
        world_state._last_seen[x] = time.time() - world_state._PLAYER_TIMEOUT - 1
    ticker.tick_once(checkpoint=False)
    assert hid not in world_state._players                 # 人类照旧踢出
    assert pid in world_state._players                     # 她还在原地
    assert world_state._players[pid]["online"] is False
    snap = client.get("/world").json()["players"]
    assert snap == [{**snap[0], "id": pid, "controller": "agent", "online": False}]


def test_offline_agent_keeps_ticking(client, fake_clock):
    pid = _join_agent(client)["playerId"]
    p = world_state._players[pid]
    world_state._last_seen[pid] = time.time() - 100
    ticker.tick_once(checkpoint=False)
    assert p["online"] is False
    f0 = p["fullness"]
    fake_clock.advance(600)
    ticker.tick_once(checkpoint=False)
    assert p["fullness"] == pytest.approx(f0 - 3 * 600 / 3600, abs=1e-6)       # world-v1.1：醒着 −3/h


def test_heartbeat_and_rejoin_restore_online(client):
    pid = _join_agent(client)["playerId"]
    world_state._players[pid]["online"] = False
    assert client.get(f"/player/{pid}").json()["online"] is False      # E②：agent 的 GET /player 不再是心跳
    hb = client.post(f"/player/{pid}/heartbeat").json()
    assert hb["ok"] is True and hb["online"] is True and world_state._players[pid]["online"] is True
    world_state._players[pid]["online"] = False
    world_state._last_seen[pid] = 0
    r = client.post("/player/rejoin", json={"playerId": pid})
    assert r.status_code == 200
    assert r.json()["playerId"] == pid and r.json()["player"]["online"] is True
    assert time.time() - world_state._last_seen[pid] < 5
    assert client.post("/player/rejoin", json={"playerId": "ghost"}).status_code == 404


def test_offline_agent_can_still_act_and_persists(client, fake_clock):
    from game import persistence, chat_state
    pid = _join_agent(client)["playerId"]
    world_state._players[pid]["online"] = False
    assert action(client, pid, "turn", {"direction": "left"})["success"]
    persistence.save_checkpoint()
    world_state._reset_for_tests(); chat_state._reset_for_tests()
    persistence.load_checkpoint()
    p = world_state._players[pid]
    assert p["controller"] == "agent" and p["online"] is False and p["facing"] == "left"
