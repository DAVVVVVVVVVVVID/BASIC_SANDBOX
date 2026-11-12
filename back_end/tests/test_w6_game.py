"""W6 任务 3（B18）：游戏机 Object 用假 D 服务。"""
import json

import httpx
import pytest

from game import world_state, external_effects
from tests.conftest import join, action, place

CONSOLE_ID = "game_console_whale"      # (10,11)；站 (9,11) 朝 right
CONSOLE_STAND = (9, 11, "right")


class FakeBrain:
    """D 的 brain 正式接口（report-D.md 5b）：/game/state、/game/start、/game/stop；/healthz /event /metrics 仍在。"""
    def __init__(self):
        self.down = False
        self.events = []            # 收到的 /game/start、/game/stop、/event 请求体（按序）
        self.alive = True
        self.run_id = "run-7"
        self.start_latency_polls = 0   # /game/start 后需要多少次 /game/state 轮询才 alive
        self.state_calls = 0

    def handler(self, req: httpx.Request):
        if self.down:
            raise httpx.ConnectError("down", request=req)
        if req.url.path == "/game/state":
            self.state_calls += 1
            if self.start_latency_polls > 0:
                self.start_latency_polls -= 1
                if self.start_latency_polls == 0:
                    self.alive = True
            return httpx.Response(200, json={"game": "dst", "run_id": self.run_id, "server": "RUNNING", "alive": self.alive,
                                             "tick_age_s": 0.4, "deaths": 0, "day": 3, "phase": "day", "time_in_phase": 0.3,
                                             "health": 120, "hunger": 88, "sanity": 150, "is_in_light": True, "pos": {"x": 1, "z": 2},
                                             "inventory": [{"prefab": "axe", "count": 1}], "goal": "找食物", "latest_png": "/tmp/x.png",
                                             "usd_today": 0.01, "extra": "ignored"})
        if req.url.path == "/game/start":
            self.events.append({"path": "/game/start", **json.loads(req.content or b"{}")})
            self.run_id = "run-8"
            if self.start_latency_polls == 0:
                self.alive = True
            return httpx.Response(200, json={"ok": True, "how": "regenerated", "previous_run_id": "run-7", "poll": "/game/state"})
        if req.url.path == "/game/stop":
            self.events.append({"path": "/game/stop", **json.loads(req.content or b"{}")})
            return httpx.Response(200, json={"ok": True, "run_id": self.run_id, "shutdown": False, "state": {}})
        if req.url.path == "/healthz":
            return httpx.Response(200, json={"ok": True, "ticks": 1234, "run_id": self.run_id})
        if req.url.path == "/event":
            self.events.append({"path": "/event", **json.loads(req.content)})
            return httpx.Response(200, json={"ok": True})
        if req.url.path == "/metrics":
            return httpx.Response(200, json={"run_id": self.run_id, "day": 3})
        return httpx.Response(404)


@pytest.fixture
def brain(monkeypatch):
    f = FakeBrain()
    monkeypatch.setattr(external_effects, "GAME_TRANSPORT", httpx.MockTransport(f.handler))
    monkeypatch.setattr(external_effects, "SYNC_STOP", True)
    monkeypatch.setattr(external_effects, "GAME_POLL_S", 0.0)
    monkeypatch.setattr(external_effects, "GAME_START_TIMEOUT_S", 2.0)
    return f


def _agent(client):
    pid = client.post("/player/join", json={"name": "鲸仔", "controller": "agent", "profile": {"agent_id": "whale"}}).json()["playerId"]
    place(pid, *CONSOLE_STAND)
    return pid


def test_console_type_and_map():
    from game.object_types import OBJECT_TYPES
    t = OBJECT_TYPES["game_console"]
    assert t["prototype"] == "continuous" and t["advertise"]["fun"] >= 50 and t["max_users"] == 1
    assert any(e["type"] == "external" and e["key"] == "game" for e in t["effects"])
    assert any(e["key"] == "fun_regen" and abs(e["value"] - 20 / 3600) < 1e-6 for e in t["effects"])    # world-v1.1：玩 +20/h，娱乐不耗精力
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
    assert g["how"] == "joined" and g["alive"] is True and g["goal"] == "找食物" and g["latest_png"] == "/tmp/x.png"
    assert g["text"] == "饥荒第 3 天白天，HP 120，正在找食物"
    assert brain.events == []                                   # 已 alive 的局直接接着玩，不重开
    st = client.get(f"/player/{pid}/state").json()
    assert st["game"]["status"] == "playing"
    per = client.get("/agent/perceive", params={"entity_id": pid}).json()
    assert per["game"]["status"] == "playing" and per["game"]["health"] == 120
    snap = next(x for x in client.get("/world").json()["players"] if x["id"] == pid)
    assert snap["stateLabel"] == "鲸仔 玩游戏中" and snap["usingObjectId"] == CONSOLE_ID
    assert action(client, pid, "leave")["success"]
    assert brain.events == [{"path": "/game/stop", "by": "sandbox", "shutdown": False}]   # 存档不关服
    p = client.get(f"/player/{pid}").json()
    assert p["game"]["status"] == "ended" and "ended_at" in p["game"] and "gaming" not in p["tags"]
    assert p["game"]["left_at_day"] == 3 and p["game"]["duration_s"] is not None and p["game"]["text"] is None
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
    brain.alive = False                                          # 没有活着的局 → 开新局
    assert action(client, pid, "use")["success"]
    assert brain.events[0] == {"path": "/game/start", "by": "sandbox"}
    assert world_state._players[pid]["game"]["how"] == "regenerated" and world_state._players[pid]["game"]["brain_run_id"] == "run-8"
    client.delete(f"/player/{pid}/leave")
    assert [e["path"] for e in brain.events] == ["/game/start", "/game/stop"]


def test_start_polls_until_alive_and_times_out(client, brain):
    pid = _agent(client)
    brain.alive = False; brain.start_latency_polls = 3                      # 开局后第 3 次轮询才 alive
    res = action(client, pid, "use")
    assert res["success"] and brain.state_calls >= 3 and world_state._players[pid]["game"]["alive"] is True
    assert action(client, pid, "leave")["success"]
    # 永远不 alive → 超时 game_unavailable（测试里超时 2 s、轮询 0 s）；先清掉这台机子的冷却
    world_state._last_used.clear()
    brain.alive = False; brain.start_latency_polls = 10**9
    res = action(client, pid, "use")
    assert res["success"] is False and res["reason"] == "game_unavailable" and res["result"]["error"] == "start_timeout"
    assert world_state._players[pid]["usingObjectId"] is None


def test_use_requires_energy_mid(client, brain):
    pid = _agent(client)
    world_state._players[pid]["energy"] = 20.0
    res = action(client, pid, "use")
    assert res["success"] is False and res["reason"] == "too_tired" and brain.events == []
    world_state._players[pid]["energy"] = 40.0
    assert action(client, pid, "use")["success"]


def test_state_refresh_failure_keeps_old_values(client, brain):
    pid = _agent(client)
    assert action(client, pid, "use")["success"]
    brain.down = True
    per = client.get("/agent/perceive", params={"entity_id": pid}).json()
    assert per["game"]["status"] == "playing" and per["game"]["day"] == 3                   # 刷新失败保留旧值
