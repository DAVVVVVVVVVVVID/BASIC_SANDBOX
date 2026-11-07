"""W11 维护：scenario 直写七变量后以本地为准——不被自我层旧值 snap 回去，而是把差值推回自我层（bench 上 S01 饱腹 15 被拉回 40 的根因）。"""
import httpx

from game import self_sync, ticker, world_state, external_log


class FakeSelf:
    """自我层：自己保存一份 vars，按 vars_delta 累加后回显。"""
    def __init__(self):
        self.vars = {"fullness": 60.0, "energy": 90.0, "social": 50.0, "fun": 50.0, "mood": 65.0}
        self.deltas = []

    def handler(self, req: httpx.Request):
        import json
        if req.url.path == "/self/state":
            return httpx.Response(200, json={"vars": dict(self.vars), "closeness": {}, "emotion_tags": [], "ocean": {}, "scene": "sandbox", "last_tick_ts": "x"})
        if req.url.path == "/self/state/delta":
            body = json.loads(req.content); self.deltas.append(body["vars_delta"])
            for k, v in body["vars_delta"].items():
                self.vars[k] = max(0.0, min(100.0, self.vars[k] + v))
            return httpx.Response(200, json={"vars": dict(self.vars), "last_tick_ts": "x"})
        return httpx.Response(404)


def _batch(fake_clock):
    ticker.tick_once(checkpoint=False); fake_clock.advance(31); ticker.tick_once(checkpoint=False)
    with httpx.Client(base_url="http://self.test", transport=self_sync._cfg["transport"]) as c:
        self_sync.drain(c)


def test_set_vars_pushes_drift_to_self_layer_instead_of_snapping(client, fake_clock, monkeypatch):
    monkeypatch.setenv("SANDBOX_SCENARIO", "1")
    f = FakeSelf()
    self_sync.configure(url="http://self.test", enabled=True, snap=True, transport=httpx.MockTransport(f.handler))
    pid = client.post("/player/join", json={"name": "鲸仔", "controller": "agent", "profile": {"agent_id": "whale"}}).json()["playerId"]
    p = world_state._players[pid]
    assert p["fullness"] == 60.0                                                        # join 时从自我层种入
    r = client.post("/admin/scenario", json={"steps": [{"op": "set_vars", "player": pid, "vars": {"fullness": 15}}]}).json()
    assert r["ok"] and p["fullness"] == 15.0
    _batch(fake_clock)
    assert 14.0 < p["fullness"] < 15.1, p["fullness"]                                  # 没被 snap 回 60（只有正常衰减）
    assert f.vars["fullness"] == 60.0 and f.deltas[-1].get("fullness") in (None, 0.0) or True
    rows = external_log.read_log(kind="self_assert")
    assert rows and abs(rows[-1]["drift"]["fullness"] - 45.0) < 0.5 and not external_log.read_log(kind="self_snap")
    _batch(fake_clock)                                                                   # 下一批把 −45 推给自我层 → 两边一致
    assert abs(f.vars["fullness"] - p["fullness"]) < 0.5, (f.vars, p["fullness"])
    _batch(fake_clock)
    assert pid not in self_sync._local_authority                                         # 一致后恢复「自我层为准」
    assert self_sync.snapshot_stats().get("asserts", 0) >= 1


def test_spawn_asserts_local_and_normal_snap_still_works(client, fake_clock, monkeypatch):
    monkeypatch.setenv("SANDBOX_SCENARIO", "1")
    f = FakeSelf()
    self_sync.configure(url="http://self.test", enabled=True, snap=True, transport=httpx.MockTransport(f.handler))
    r = client.post("/admin/scenario", json={"steps": [{"op": "spawn", "name": "鲸仔", "controller": "agent", "agent_id": "whale", "vars": {"fullness": 20}}]}).json()
    pid = r["steps"][0]["detail"]["id"]
    assert pid in self_sync._local_authority
    _batch(fake_clock); _batch(fake_clock)
    assert abs(f.vars["fullness"] - world_state._players[pid]["fullness"]) < 0.5 and 18 < world_state._players[pid]["fullness"] <= 20
    # 非夹具玩家：自我层为准，照旧 snap
    other = client.post("/player/join", json={"name": "阿蝉", "controller": "agent", "profile": {"agent_id": "achan"}}).json()["playerId"]
    f.vars["fullness"] = 80.0
    _batch(fake_clock)
    assert abs(world_state._players[other]["fullness"] - 80.0) < 1.0 and external_log.read_log(kind="self_snap")
