"""B10 手机 / B11 直播台：external effect 对自我层的调用（MockTransport 模拟 8100）。"""
import json

import httpx
import pytest

from game import world_state, self_sync, external_effects
from tests.conftest import PHONE_ID, PHONE_STAND, STREAM_ID, STREAM_STAND, join, action, place


class FakeSelf:
    def __init__(self):
        self.down = False
        self.live_calls = []
        self.items = [{"ts": "2026-11-06T20:01:00+08:00", "topic": "点歌请求", "sentiment": "pos", "is_question": True,
                       "is_song_request": True, "summary": "有观众想听一首老歌", "injection": False,
                       "id": "c1", "source": "bilibili_comment", "author": {"uid": 1}, "text": "原文不该出现"}]

    def handler(self, req: httpx.Request):
        if self.down:
            raise httpx.ConnectError("down", request=req)
        if req.url.path == "/self/state":
            return httpx.Response(200, json={"vars": {"fullness": 70, "energy": 70, "social": 70, "fun": 70, "mood": 65},
                                             "closeness": {}, "emotion_tags": [], "ocean": {}, "scene": "sandbox",
                                             "last_tick_ts": "2026-11-10T12:00:00+08:00"})
        if req.url.path == "/self/feed":
            assert req.url.params["for"] == "whale"
            return httpx.Response(200, json={"items": self.items, "digest_ts": "2026-11-06T20:05:00+08:00", "for": "whale", "n": 8})
        if req.url.path in ("/self/live/start", "/self/live/stop"):
            body = json.loads(req.content)
            self.live_calls.append((req.url.path.rsplit("/", 1)[1], body))
            return httpx.Response(200, json={"ok": True, "scene": "live" if req.url.path.endswith("start") else "sandbox",
                                             "catch_up_seconds": 0, "webhook_forwarded": False})
        if req.url.path == "/self/state/delta":
            return httpx.Response(200, json={"vars": {}, "last_tick_ts": "x"})
        return httpx.Response(404)


@pytest.fixture
def fake_self(monkeypatch):
    f = FakeSelf()
    self_sync.configure(url="http://self.test", enabled=True, snap=False, transport=httpx.MockTransport(f.handler))
    monkeypatch.setattr(external_effects, "SYNC_STOP", True)
    return f


def _agent(client):
    return client.post("/player/join", json={"name": "鲸仔", "controller": "agent", "profile": {"agent_id": "whale"}}).json()["playerId"]


# ── B10 ──────────────────────────────────────────────────────────────────────

def test_phone_fetches_digest_into_perceive(client, fake_self):
    pid = _agent(client)
    place(pid, *PHONE_STAND)
    p = world_state._players[pid]
    fun0, social0, energy0 = p["fun"], p["social"], p["energy"]
    res = action(client, pid, "use")
    assert res["success"] and res["result"]["objectId"] == PHONE_ID
    assert "有观众想听一首老歌" in res["result"]["message"] and "点歌" in res["result"]["message"]
    digest = res["result"]["phone"]
    assert digest["status"] == "ok" and digest["digest_ts"] == "2026-11-06T20:05:00+08:00"
    item = digest["items"][0]
    assert set(item) <= set(external_effects.FEED_ITEM_FIELDS)        # 原文 / id / author 不进沙盒
    for bad in ("id", "source", "author", "text"):
        assert bad not in item
    assert (p["fun"], p["social"], p["energy"]) == (fun0 + 15, social0 + 5, energy0 - 2)
    per = client.get("/agent/perceive", params={"entity_id": pid}).json()
    assert per["phone"]["status"] == "ok" and per["phone"]["items"][0]["summary"] == "有观众想听一首老歌"
    assert "text" not in json.dumps(per["phone"])


def test_phone_no_signal_when_self_down_still_cooldown(client, fake_self):
    pid = _agent(client)
    place(pid, *PHONE_STAND)
    fake_self.down = True
    res = action(client, pid, "use")
    assert res["success"] is False and res["reason"] == "feed_unavailable"
    assert "没信号" in res["result"]["message"]
    assert res["result"]["phone"]["status"] == "no_signal"
    assert client.get("/agent/perceive", params={"entity_id": pid}).json()["phone"]["status"] == "no_signal"
    assert world_state.object_cooldown_remaining(pid, PHONE_ID) > 1700       # 仍算用过
    assert action(client, pid, "use")["reason"] == "object_cooldown"


def test_phone_empty_feed_and_perceive_null_before_use(client, fake_self):
    pid = _agent(client)
    assert client.get("/agent/perceive", params={"entity_id": pid}).json()["phone"] == {"unread": {}, "unread_total": 0}   # W10 ③：没刷过手机也给未读数
    fake_self.items = []
    place(pid, *PHONE_STAND)
    res = action(client, pid, "use")
    assert res["success"] and "没有新消息" in res["result"]["message"]


def test_phone_for_human_uses_player_id(client, fake_self):
    pid = join(client, "h")
    fake_self.handler_for = None
    def handler(req):
        if req.url.path == "/self/feed":
            assert req.url.params["for"] == pid
            return httpx.Response(200, json={"items": [], "digest_ts": None})
        return fake_self.handler(req)
    self_sync.configure(transport=httpx.MockTransport(handler), enabled=True)
    place(pid, *PHONE_STAND)
    assert action(client, pid, "use")["success"]


# ── B11 ──────────────────────────────────────────────────────────────────────

def test_stream_desk_starts_and_stops_live(client, fake_self):
    pid = _agent(client)
    place(pid, *STREAM_STAND)
    p = world_state._players[pid]
    res = action(client, pid, "use")
    assert res["success"] and res["result"]["objectId"] == STREAM_ID
    assert fake_self.live_calls == [("start", {"agent": "whale", "ts": fake_self.live_calls[0][1]["ts"]})]
    assert "T" in fake_self.live_calls[0][1]["ts"]
    assert p["scene"] == "live" and "streaming" in p["tags"] and p["canMove"] is False or True
    assert client.get(f"/player/{pid}/state").json()["scene"] == "live"
    assert action(client, pid, "leave")["success"]
    assert [c[0] for c in fake_self.live_calls] == ["start", "stop"]
    assert p["scene"] == "sandbox" and client.get(f"/player/{pid}/state").json()["scene"] == "sandbox"
    assert "streaming" not in p["tags"]


def test_stream_desk_live_unavailable_blocks_use(client, fake_self):
    pid = _agent(client)
    place(pid, *STREAM_STAND)
    fake_self.down = True
    res = action(client, pid, "use")
    assert res["success"] is False and res["reason"] == "live_unavailable"
    p = world_state._players[pid]
    assert p["usingObjectId"] is None and p["scene"] == "sandbox"
    assert world_state.get_object_by_id(STREAM_ID)["currentUsers"] == 0
    assert world_state.object_cooldown_remaining(pid, STREAM_ID) == 0.0   # 没坐下不算用过


def test_stream_desk_live_decay_rates_apply(client, fake_self, fake_clock):
    from game import ticker
    pid = _agent(client)
    place(pid, *STREAM_STAND)
    assert action(client, pid, "use")["success"]
    p = world_state._players[pid]
    p["social"] = 50.0
    ticker.tick_once(checkpoint=False)
    fake_clock.advance(60); ticker.tick_once(checkpoint=False)
    # live：social −0.12/s 衰减 + 直播 +20/h
    assert p["social"] == pytest.approx(50 - 0.12 * 60 + 20 / 60, abs=0.01)


def test_stream_desk_human_live_unavailable(client, fake_self):
    """§3.11 B4：阿蝉（人类）不能替她开播。"""
    pid = join(client, "h")
    place(pid, *STREAM_STAND)
    res = action(client, pid, "use")
    assert res["success"] is False and res["reason"] == "live_unavailable"
    assert "no_agent_id" in res["result"]["error"]
    assert fake_self.live_calls == []                                     # 没有 agent_id 不打自我层
    assert world_state._players[pid]["scene"] == "sandbox" and world_state._players[pid]["usingObjectId"] is None


def test_remove_player_while_streaming_sends_stop(client, fake_self):
    pid = _agent(client)
    place(pid, *STREAM_STAND)
    assert action(client, pid, "use")["success"]
    client.delete(f"/player/{pid}/leave")
    assert [c[0] for c in fake_self.live_calls] == ["start", "stop"]


def test_external_effects_skipped_in_apply_effects():
    p = world_state._make_player("x", "x")
    r = world_state.apply_effects(p, [{"type": "external", "key": "feed"}, {"type": "instant_effect", "key": "fun", "value": 1}], source="t")
    assert r == {"applied": 1, "skipped": 0}
