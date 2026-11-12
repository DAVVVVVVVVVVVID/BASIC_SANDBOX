"""
任务 6：每 30 游戏秒 POST /self/state/delta；不可达时累积重发；两边数值差 < 0.5。

对端用 httpx.MockTransport 跑一份 whale-self/whale_self/state.py 的参考移植（decay / catch_up / apply_delta），
与沙盒实现相互独立：沙盒按 200 ms 连续衰减 + 上报非衰减变化，自我层按批 catch_up 再加 delta。
"""
import json
import math
from datetime import datetime, timedelta

import httpx
import pytest

from game import self_sync, world_state, ticker, time_state
from game.time_state import GAME_TZ
from tests.conftest import BED_ID, BED_STAND, join, action, place

# ── 参考自我层（移植自 whale-self state.py，sandbox/live 两套速率） ─────────────
RATES = {   # world-v1.1 needs.json：醒着；live 饱腹再 −3；asleep 另一套；working 精力再 −3（参考模型按 delta 里的 asleep / working 标记）
    "sandbox": {"fullness": -3 / 3600, "energy": -3 / 3600, "social": -2 / 3600, "fun": -2 / 3600},
    "live":    {"fullness": -6 / 3600, "energy": -3 / 3600, "social": -2 / 3600, "fun": -2 / 3600},
    "asleep":  {"fullness": -1.5 / 3600, "energy": 0.0, "social": 0.0, "fun": 0.0},
}
WORK_EXTRA = -3 / 3600
HALF = {"sandbox": 7200.0, "live": 70.0}


def _night_seconds(start: datetime, end: datetime) -> float:
    total = 0.0; cur = start
    while cur < end:
        nxt = (cur + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        seg = min(nxt, end)
        if cur.hour in range(0, 6):
            total += (seg - cur).total_seconds()
        cur = seg
    return total


def _clamp(x): return max(0.0, min(100.0, x))


class RefSelfLayer:
    def __init__(self, now: datetime, now_fn=None, ocean=None, vars_=None, closeness=None):
        self.now_fn = now_fn or (lambda: now)   # GET /self/state 返回前先 catch_up 到「现在」（与真实服务一致）
        self.ocean = ocean or {"E": 80, "N": 55}
        self.doc = {
            "agent_id": "whale", "scene": "sandbox",
            "last_tick_ts": now.isoformat(timespec="seconds"),
            "vars": dict(vars_ or {"fullness": 70.0, "energy": 70.0, "social": 70.0, "fun": 70.0, "mood": 69.5}),
            "emotion_tags": [], "closeness": dict(closeness or {"achan": 72.0}), "ocean": self.ocean,
            "thresholds": {"low": 25, "critical": 15, "emergency": 10},
        }
        self.down = False
        self.calls: list[dict] = []

    def base(self):
        return 65 + 0.2 * (self.ocean["E"] - 50) - 0.3 * (self.ocean["N"] - 50)

    def decay(self, start: datetime, end: datetime):
        dt = (end - start).total_seconds()
        if dt <= 0:
            return
        v = self.doc["vars"]; scene = self.doc["scene"]
        rates = RATES["asleep"] if self.doc.get("asleep") else RATES[scene]
        for k, r in rates.items():
            if k == "energy" and self.doc.get("working"):
                r = r + WORK_EXTRA
            d = r * dt
            v[k] = _clamp(v[k] + d)
        b = self.base()
        v["mood"] = _clamp(b + (v["mood"] - b) * math.pow(0.5, dt / HALF[scene]))
        for k in v:
            v[k] = round(v[k], 3)

    def catch_up(self, now: datetime):
        last = datetime.fromisoformat(self.doc["last_tick_ts"])
        gap = (now - last).total_seconds()
        if gap > 1.0:
            self.decay(now - timedelta(seconds=min(gap, 8 * 3600)), now)
            self.doc["last_tick_ts"] = now.isoformat(timespec="seconds")

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("self-layer down", request=request)
        if request.method == "GET" and request.url.path == "/self/state":
            self.catch_up(self.now_fn())
            return httpx.Response(200, json=self.doc)
        if request.method == "POST" and request.url.path == "/self/state/delta":
            body = json.loads(request.content)
            self.calls.append(body)
            now = datetime.fromisoformat(body["ts"])
            self.catch_up(now)
            if body.get("scene"):
                self.doc["scene"] = body["scene"]
            self.doc["asleep"] = bool(body.get("asleep")); self.doc["working"] = bool(body.get("working"))
            for k, d in body["vars_delta"].items():
                self.doc["vars"][k] = round(_clamp(self.doc["vars"][k] + float(d)), 3)
            self.doc["last_tick_ts"] = now.isoformat(timespec="seconds")
            return httpx.Response(200, json={"vars": self.doc["vars"], "last_tick_ts": self.doc["last_tick_ts"]})
        return httpx.Response(404, json={"error": "not_found"})


def _now_dt(fake_clock) -> datetime:
    return datetime.fromtimestamp(fake_clock.t, GAME_TZ)


@pytest.fixture
def ref(fake_clock):
    # 从 23:00 开始，两小时后跨到次日 01:00，覆盖夜间倍率
    fake_clock.t = datetime(2026, 11, 10, 23, 0, tzinfo=GAME_TZ).timestamp()
    time_state.reset_time(); time_state.set_running(True)
    layer = RefSelfLayer(_now_dt(fake_clock), now_fn=lambda: _now_dt(fake_clock))
    self_sync.configure(url="http://self.test", enabled=True, snap=True,
                        transport=httpx.MockTransport(layer.handler))
    return layer


def _join_agent(client, name="鲸仔"):
    return client.post("/player/join", json={"name": name, "controller": "agent",
                                              "profile": {"E": 50, "N": 50, "agent_id": "whale"}}).json()


def _client():
    return httpx.Client(base_url="http://self.test", transport=self_sync._cfg["transport"])


def _simulate(client, fake_clock, ref, seconds: int, step_s: float = 1.0, hook=None):
    """逐秒 tick；每出一批就同步 drain（模拟发送线程）。"""
    with _client() as c:
        t = 0.0
        while t < seconds:
            fake_clock.advance(step_s); t += step_s
            ticker.tick_once(checkpoint=False)
            if hook:
                hook(t)
            self_sync.drain(c)


def _diff(player: dict, ref: RefSelfLayer, now: datetime) -> dict:
    ref.catch_up(now)
    return {k: abs(player[k] - ref.doc["vars"][k]) for k in self_sync.VARS}


def test_seed_from_self_state_on_join(client, ref):
    data = _join_agent(client)
    p = data["player"]
    assert p["energy"] == 70.0 and p["social"] == 70.0 and p["fun"] == 70.0      # 自我层的值，不是 §2.5 初值
    assert p["mood"] == 69.5 and p["mood_base"] == pytest.approx(69.5)           # ocean → 基线
    assert p["closeness"] == {"achan": 72.0}
    assert self_sync.stats["seeded"] == 1
    assert self_sync.is_registered(data["playerId"])
    # human 不种、不登记
    h = join(client, "h")
    assert not self_sync.is_registered(h)


def test_batches_every_30_game_seconds_with_only_non_decay_delta(client, ref, fake_clock):
    pid = _join_agent(client)["playerId"]
    _simulate(client, fake_clock, ref, 95)
    assert len(ref.calls) == 3
    b = ref.calls[0]
    assert b["agent"] == "whale" and b["scene"] == "sandbox" and b["source"] == "sandbox_tick"
    assert datetime.fromisoformat(b["ts"]).tzinfo is not None
    assert b["vars_delta"] == {}                        # 只有衰减 → 不上报变化
    assert self_sync.stats["sent"] == 3 and self_sync.stats["failed"] == 0
    assert self_sync.stats["drift_max"] < 0.01


def test_two_hours_with_objects_and_effects_drift_below_half(client, ref, fake_clock):
    """床上睡 40 分钟（energy_regen 并 clamp 到 100）、中途两次直播事件推送、跨夜间倍率；两边差 < 0.5。"""
    pid = _join_agent(client)["playerId"]
    p = world_state._players[pid]
    place(pid, *BED_STAND)
    assert action(client, pid, "use")["success"]
    events = {
        600:  [{"type": "instant_effect", "key": "social", "value": 12}, {"type": "instant_effect", "key": "mood", "value": 4}],
        2400: "leave",
        4000: [{"type": "instant_effect", "key": "fun", "value": -7}, {"type": "instant_effect", "key": "fullness", "value": 25}],
    }

    def hook(t):
        ev = events.get(int(t))
        if ev == "leave":
            assert action(client, pid, "leave")["success"]
        elif ev:
            assert client.post(f"/player/{pid}/effects", json={"effects": ev}).status_code == 200

    _simulate(client, fake_clock, ref, 7200, hook=hook)
    diffs = _diff(p, ref, _now_dt(fake_clock))
    assert max(diffs.values()) < 0.5, diffs
    assert self_sync.stats["sent"] == 240 and self_sync.stats["failed"] == 0
    assert self_sync.stats["resyncs"] == 0                  # 没触发纠偏也在 0.5 内
    assert p["energy"] < 100 and p["fullness"] > 40           # 场景确实动了
    # 确认上报里确实带了物品 / 事件的非衰减增量
    assert any(c["vars_delta"].get("energy", 0) > 0 for c in ref.calls)
    assert any(abs(c["vars_delta"].get("social", 0) - 12) < 1e-6 for c in ref.calls)


def test_unreachable_then_recover_merges_pending(client, ref, fake_clock):
    pid = _join_agent(client)["playerId"]
    p = world_state._players[pid]
    place(pid, *BED_STAND)
    assert action(client, pid, "use")["success"]
    p["energy"] = 30.0
    ref.doc["vars"]["energy"] = 30.0
    ref.down = True
    _simulate(client, fake_clock, ref, 120)
    assert self_sync.stats["failed"] >= 1 and self_sync.stats["sent"] == 0
    assert p["energy"] > 100 - 1 or p["energy"] > 30         # 本地照常 tick
    pend = self_sync.snapshot_stats()["pending"][pid]
    assert pend.get("energy", 0) > 0.3                         # 失败批已合回 pending（bed +10/h × 120 s ≈ 0.33，v1.1）
    ref.down = False
    _simulate(client, fake_clock, ref, 31)
    assert self_sync.stats["sent"] >= 1
    sent_energy = sum(c["vars_delta"].get("energy", 0) for c in ref.calls)
    assert sent_energy > 0.3                                   # 累积的增量一次补发
    diffs = _diff(p, ref, _now_dt(fake_clock))
    assert max(diffs.values()) < 0.5, diffs


def test_snap_corrects_local_when_remote_diverges(client, ref, fake_clock):
    pid = _join_agent(client)["playerId"]
    p = world_state._players[pid]
    ref.doc["vars"]["fun"] = p["fun"] + 5.0                   # 自我层另有事件写入（例如直播服务）
    _simulate(client, fake_clock, ref, 31)
    assert self_sync.stats["resyncs"] == 1
    assert abs(p["fun"] - ref.doc["vars"]["fun"]) < 0.5
    self_sync.configure(snap=False)
    ref.doc["vars"]["fun"] = p["fun"] + 5.0
    _simulate(client, fake_clock, ref, 31)
    assert self_sync.stats["resyncs"] == 1                    # 关掉 snap 只记录 drift
    assert self_sync.stats["drift_max"] >= 4.9


def test_live_scene_rates_agree(client, ref, fake_clock):
    pid = _join_agent(client)["playerId"]
    p = world_state._players[pid]
    client.post(f"/player/{pid}/effects", json={"scene": "live", "effects": []})
    _simulate(client, fake_clock, ref, 300)
    assert ref.doc["scene"] == "live"
    diffs = _diff(p, ref, _now_dt(fake_clock))
    assert max(diffs.values()) < 0.5, diffs
    assert p["fullness"] < 70 - 0.4                           # v1.1：live 下饱腹 −6/h（300 s ≈ 0.5），social 同醒着


def test_restart_reseeds_from_self(client, ref, fake_clock):
    from game import persistence, chat_state
    pid = _join_agent(client)["playerId"]
    _simulate(client, fake_clock, ref, 61)
    persistence.save_checkpoint()
    world_state._reset_for_tests(); chat_state._reset_for_tests(); self_sync._reset_for_tests()
    self_sync.configure(url="http://self.test", enabled=True, transport=httpx.MockTransport(ref.handler))
    fake_clock.advance(3600)
    info = persistence.load_checkpoint()
    persistence.catch_up(info["catch_up_game_ms"])
    assert persistence.seed_agents_from_self() == 1
    p = world_state._players[pid]
    diffs = _diff(p, ref, _now_dt(fake_clock))
    assert max(diffs.values()) < 0.5, diffs
    assert self_sync.is_registered(pid)


def test_admin_self_sync_endpoint(client, ref):
    r = client.get("/admin/self-sync").json()
    for k in ("sent", "failed", "seeded", "drift_max", "drift_last", "last_error", "pending", "queue", "self_url", "enabled"):
        assert k in r


def test_disabled_sync_is_noop(client):
    self_sync.configure(enabled=False)
    data = _join_agent(client)
    assert data["player"]["energy"] == 100.0                  # §2.5 初值，没种
    assert self_sync.stats["seeded"] == 0 and self_sync.stats["sent"] == 0
