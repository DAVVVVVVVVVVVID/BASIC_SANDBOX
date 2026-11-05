"""W3 任务 1–2：source=self 不计入 delta；物品每小时尺度；新地图。"""
import json
from datetime import datetime
from pathlib import Path

import httpx
import pytest

from game import world_state, self_sync, ticker, time_state
from game.object_types import OBJECT_TYPES
from game.buff_tick import run_tick
from game.time_state import GAME_TZ
from tests.conftest import BED_ID, BED_STAND, FRIDGE_ID, FRIDGE_STAND, join, action, place


def _ts(hour, day=10):
    return datetime(2026, 11, day, hour, tzinfo=GAME_TZ).timestamp()


# ── 任务 1：source=self ────────────────────────────────────────────────────────

def test_source_self_not_tracked_into_delta(client, fake_clock):
    calls = []
    def handler(req: httpx.Request):
        if req.url.path == "/self/state":
            return httpx.Response(200, json={"vars": {"fullness": 70, "energy": 70, "social": 70, "fun": 70, "mood": 65},
                                             "closeness": {}, "emotion_tags": [], "ocean": {}, "scene": "sandbox",
                                             "last_tick_ts": "2026-11-10T12:00:00+08:00"})
        calls.append(json.loads(req.content))
        return httpx.Response(200, json={"vars": calls[-1].get("vars_delta") and {"fullness": 70, "energy": 70, "social": 70, "fun": 70, "mood": 65} or
                                        {"fullness": 70, "energy": 70, "social": 70, "fun": 70, "mood": 65}, "last_tick_ts": "x"})
    self_sync.configure(url="http://self.test", enabled=True, snap=False, transport=httpx.MockTransport(handler))
    pid = client.post("/player/join", json={"name": "w", "controller": "agent", "profile": {"agent_id": "whale"}}).json()["playerId"]
    p = world_state._players[pid]
    # 自我层回推（source=self）：落本地，不进 pending
    r = client.post(f"/player/{pid}/effects", json={"source": "self", "effects": [
        {"type": "instant_effect", "key": "social", "value": 12}, {"type": "instant_effect", "key": "mood", "value": 4}]})
    assert r.status_code == 200 and p["social"] == 82.0 and p["mood"] == 69.0
    assert self_sync.snapshot_stats()["pending"][pid] == {}
    # 其他来源（直播服务直推 / 物品）照常进 pending
    client.post(f"/player/{pid}/effects", json={"source": "live", "effects": [{"type": "instant_effect", "key": "fun", "value": 3}]})
    assert self_sync.snapshot_stats()["pending"][pid] == {"fun": 3.0}
    # 下一批：只有 fun（先建基线 tick，再过 31 游戏秒出批）
    ticker.tick_once(checkpoint=False)
    fake_clock.advance(31); ticker.tick_once(checkpoint=False)
    with httpx.Client(base_url="http://self.test", transport=self_sync._cfg["transport"]) as c:
        self_sync.drain(c)
    assert len(calls) == 1 and set(calls[0]["vars_delta"]) == {"fun"}
    assert calls[0]["vars_delta"]["fun"] == pytest.approx(3.0)


# ── 任务 2：每小时尺度 ─────────────────────────────────────────────────────────

def test_object_rates_are_hourly_scale():
    """连续物品 *_regen 的绝对值 ≤ 30/h（点/秒 ≤ 30/3600）；instant 恢复量 ≤ 60。"""
    for name, t in OBJECT_TYPES.items():
        for e in t["effects"]:
            if e["type"] == "buff" and e["key"].endswith("_regen"):
                assert abs(e["value"]) <= 30 / 3600 + 1e-9, (name, e)
            if e["type"] == "instant_effect":
                assert abs(e["value"]) <= 60, (name, e)
        assert isinstance(t.get("advertise"), dict), name
    assert set(OBJECT_TYPES) >= {"bed", "bed_21", "bath", "fridge", "desk", "desk_12", "book", "phone", "stream_desk"}


def test_sleep_8h_restores_energy_from_0_to_about_100():
    """22:00 睡到 06:00：bed +25/h × 8 = 200，减去衰减 8/h（0–6 点 ×1.5）≈ 80 → 0 起步应回到 ≈ 100（clamp）。"""
    p = world_state._make_player("w", "w")
    p["energy"] = 0.0
    bed = OBJECT_TYPES["bed"]
    world_state.apply_effects(p, bed["effects"], source="bed_t")
    end = _ts(6, day=11)
    for i in range(1, 8 * 60 + 1):               # 每游戏分钟一步
        run_tick(p, 60_000.0, game_ts=end - 8 * 3600 + i * 60)
    assert p["energy"] >= 99.0, p["energy"]
    # 不 clamp 的净值：200 − (6h×8 + 2h×12)... 用 energy=0 且 regen 只 4 h 验证线性：
    p2 = world_state._make_player("w2", "w2"); p2["energy"] = 10.0   # 不贴 0 边界
    world_state.apply_effects(p2, bed["effects"], source="bed_t")
    for i in range(1, 4 * 60 + 1):
        run_tick(p2, 60_000.0, game_ts=_ts(16) + i * 60)     # 16:00–20:00 白天
    assert p2["energy"] == pytest.approx(10 + 4 * (25 - 8), abs=0.05)
    assert p2["fun"] == pytest.approx(60 - 4 * (10 + 1), abs=0.05)   # 睡觉 fun −1/h + 衰减 10/h


def test_meal_restores_about_a_third_of_daily_decay(client):
    pid = join(client)
    place(pid, *FRIDGE_STAND)
    p = world_state._players[pid]
    p["fullness"] = 20.0; p["energy"] = 50.0; p["fun"] = 50.0
    res = action(client, pid, "use")
    assert res["success"] and res["result"]["objectId"] == FRIDGE_ID
    assert p["fullness"] == 60.0 and p["energy"] == 55.0 and p["fun"] == 48.0


# ── B16 新地图 ────────────────────────────────────────────────────────────────

def test_new_map_layout_and_npc_homes():
    cmap = world_state.get_cognitive_map()
    sectors = {s["id"]: {a["id"] for a in s["arenas"]} for s in cmap["worlds"][0]["sectors"]}
    assert sectors["achan_house"] == {"storage", "achan_room", "kitchen"}
    for sec in ("cook_house", "grocer_house", "fisher_house", "regular_house"):
        assert sec in sectors
    assert {"road", "square", "park", "dock", "water"} <= sectors["outside"]
    names = world_state._MAP_DATA["zone_names"]
    assert names["sector"]["achan_house"] == "阿蝉家" and names["arena"]["storage"] == "小仓库"
    types = {o["type"] for o in world_state._OBJECTS}
    assert {"bed", "fridge", "desk", "book", "phone", "stream_desk"} <= types
    # 鲸仔房间齐全，出生点在里面
    storage = {o["type"] for o in world_state.get_objects_in_arena("storage")}
    assert {"bed", "desk", "book", "phone", "stream_desk"} <= storage
    sx, sy = world_state._META["player_start"]["x"], world_state._META["player_start"]["y"]
    assert world_state.get_zone_at(sx, sy)["arena"] == "storage" and world_state.is_tile_walkable(sx, sy)
    # 每个 NPC 家至少一张床
    for sec in ("cook_house", "grocer_house", "fisher_house", "regular_house"):
        beds = [o for a in sectors[sec] for o in world_state.get_objects_in_arena(a) if o["type"].startswith("bed")]
        assert beds, sec


def test_every_object_reachable_from_spawn():
    from collections import deque
    start = (world_state._META["player_start"]["x"], world_state._META["player_start"]["y"])
    seen = {start}; q = deque([start])
    while q:
        x, y = q.popleft()
        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            n = (x + dx, y + dy)
            if n not in seen and world_state.is_tile_walkable(*n):
                seen.add(n); q.append(n)
    for o in world_state._OBJECTS:
        adj = {(t["x"] + dx, t["y"] + dy) for t in o["tiles"] for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0))}
        assert adj & seen, f"{o['id']} unreachable"


def test_map_generator_is_deterministic(tmp_path):
    import subprocess, sys
    out = tmp_path / "maps"; out.mkdir()
    subprocess.run([sys.executable, str(Path(__file__).resolve().parent.parent / "scripts" / "gen_map.py"), "--out", str(out)],
                   check=True, capture_output=True)
    assert json.loads((out / "map.json").read_text()) == json.loads(Path(world_state._MAP_DIR / "map.json").read_text())
    assert json.loads((out / "objects.json").read_text()) == json.loads(Path(world_state._MAP_DIR / "objects.json").read_text())
