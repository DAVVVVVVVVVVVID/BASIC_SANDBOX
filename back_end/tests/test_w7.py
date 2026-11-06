"""W7：B20 营业时间、外部效果日志、E 字段、回放。"""
import json
from datetime import datetime, date
from pathlib import Path

import pytest

from game import world_state, external_log, ticker, state_log, buff_tick
from game.time_state import GAME_TZ
from routers import actions as actions_mod
from tests.conftest import join, action, place

TABLE_ID, TABLE_STAND = "table_rest_1", (46, 33, "up")
COUNTER_ID, COUNTER_STAND = "counter_grocer", (25, 24, "right")
FISH_ID, FISH_STAND = "fishing_spot_1", (52, 17, "right")


def _ts(h, m=0, day=10):
    return datetime(2026, 11, day, h, m, tzinfo=GAME_TZ).timestamp()


# ── B20 ─────────────────────────────────────────────────────────────────────

def test_open_state_rules():
    table = world_state.get_object_by_id(TABLE_ID); counter = world_state.get_object_by_id(COUNTER_ID); fish = world_state.get_object_by_id(FISH_ID)
    bed = world_state.get_object_by_id("bed_whale")
    assert world_state.open_state(table, _ts(12)) == (True, None)
    assert world_state.open_state(table, _ts(15)) == (False, "17:00")
    assert world_state.open_state(table, _ts(22)) == (False, "11:00")          # 跨到明天第一段
    assert world_state.open_state(table, _ts(10, 59)) == (False, "11:00") and world_state.open_state(table, _ts(13, 59)) == (True, None)
    assert world_state.open_state(counter, _ts(8)) == (False, "09:00") and world_state.open_state(counter, _ts(19, 59)) == (True, None)
    assert world_state.open_state(fish, _ts(5)) == (False, "06:00") and world_state.open_state(fish, _ts(6)) == (True, None)
    assert world_state.open_state(bed, _ts(3)) == (True, None)                 # 无营业时间恒开


def test_closed_use_returns_closed_with_opens_at(client, fake_clock):
    fake_clock.t = _ts(15, 30)
    pid = join(client, "h"); place(pid, *TABLE_STAND)
    res = action(client, pid, "use")
    assert res["success"] is False and res["reason"] == "closed"
    assert res["result"]["opens_at"] == "17:00" and res["result"]["objectId"] == TABLE_ID and "17:00" in res["result"]["message"]
    assert res["result"]["openHours"] == [["11:00", "14:00"], ["17:00", "21:00"]]
    assert world_state.object_cooldown_remaining(pid, TABLE_ID) == 0.0           # 没用成不计冷却
    fake_clock.t = _ts(17, 0)
    assert action(client, pid, "use")["success"]


def test_world_and_perceive_show_open_and_zero_advertise(client, fake_clock):
    fake_clock.t = _ts(15, 30)
    objs = {o["id"]: o for o in client.get("/world").json()["objects"]}
    assert objs[TABLE_ID]["open"] is False and objs[TABLE_ID]["opensAt"] == "17:00"
    assert objs[TABLE_ID]["advertise"] == {"fullness": 0, "social": 0, "fun": 0}
    assert objs[COUNTER_ID]["open"] is True and objs[COUNTER_ID]["opensAt"] is None and objs[COUNTER_ID]["advertise"]["fullness"] > 0
    assert objs["bed_whale"]["open"] is True and objs["bed_whale"]["openHours"] is None
    pid = join(client, "h")
    tree = client.get("/agent/perceive", params={"entity_id": pid}).json()["arena_tree"]
    dining = next(a for s in tree["sectors"] for a in s["arenas"] if a["id"] == "dining")
    t = next(o for o in dining["objects"] if o["id"] == TABLE_ID)
    assert t["open"] is False and t["opensAt"] == "17:00" and set(t["advertise"].values()) == {0}
    fake_clock.t = _ts(12)
    objs = {o["id"]: o for o in client.get("/world").json()["objects"]}
    assert objs[TABLE_ID]["open"] is True and objs[TABLE_ID]["advertise"]["fullness"] == 55
    # 原始 _OBJECTS 的 advertise 没被改掉
    assert world_state.get_object_by_id(TABLE_ID)["advertise"]["fullness"] == 55


def test_closing_time_kicks_users(client, fake_clock):
    fake_clock.t = _ts(13, 59)
    pid = join(client, "h"); place(pid, *TABLE_STAND)
    assert action(client, pid, "use")["success"]
    ticker.tick_once(checkpoint=False)
    fake_clock.advance(120); ticker.tick_once(checkpoint=False)                 # 14:01 关门
    p = client.get(f"/player/{pid}").json()
    assert p["usingObjectId"] is None and p["state"] == "idle" and p["pendingMessage"]
    assert world_state.get_object_by_id(TABLE_ID)["currentUsers"] == 0


def test_ws_objects_carry_open(client):
    from routers.ws import _dynamic_state
    st = _dynamic_state()
    assert "open" in st["objects"][TABLE_ID] and st["objects"]["bed_whale"]["open"] is True


# ── 外部效果日志 ─────────────────────────────────────────────────────────────

def test_external_log_records_pushes_time_and_adjudication(client):
    pid = client.post("/player/join", json={"name": "w", "controller": "agent", "profile": {"agent_id": "whale"}}).json()["playerId"]
    client.post(f"/player/{pid}/effects", json={"source": "self", "event": "praised", "effects": [{"type": "instant_effect", "key": "mood", "value": 10}]})
    client.post("/time/speed", json={"value": 5}); client.post("/time/toggle"); client.post("/time/reset")
    rows = external_log.read_log(date=date.today().isoformat())
    kinds = [(r["kind"], r.get("op")) for r in rows]
    assert kinds == [("effects_push", None), ("nondeterministic", "time_speed"), ("nondeterministic", "time_toggle"), ("nondeterministic", "time_reset")]
    e = rows[0]
    assert e["entity"] == pid and e["source"] == "self" and e["event"] == "praised" and e["effects"][0]["key"] == "mood"
    for k in ("ts", "game_time", "town", "map_version", "seed"):
        assert k in e
    assert rows[1]["speed"] == 5.0
    exp = client.get("/admin/export", params={"date": date.today().isoformat(), "kinds": "external"}).json()
    assert exp["manifest"]["counts"] == {"external": 4} and len(exp["external"]) == 4


def test_external_log_seed_and_snap(client, fake_clock):
    import httpx
    from game import self_sync
    def handler(req):
        if req.url.path == "/self/state":
            return httpx.Response(200, json={"vars": {"fullness": 70, "energy": 70, "social": 70, "fun": 70, "mood": 65},
                                             "closeness": {"achan": 72}, "emotion_tags": [], "ocean": {}, "scene": "sandbox", "last_tick_ts": "x"})
        return httpx.Response(200, json={"vars": {"fullness": 75, "energy": 70, "social": 70, "fun": 70, "mood": 65}, "last_tick_ts": "x"})
    self_sync.configure(url="http://self.test", enabled=True, snap=True, transport=httpx.MockTransport(handler))
    pid = client.post("/player/join", json={"name": "w", "controller": "agent", "profile": {"agent_id": "whale"}}).json()["playerId"]
    ticker.tick_once(checkpoint=False); fake_clock.advance(31); ticker.tick_once(checkpoint=False)
    with httpx.Client(base_url="http://self.test", transport=self_sync._cfg["transport"]) as c:
        self_sync.drain(c)
    rows = external_log.read_log(kind="self_seed") + external_log.read_log(kind="self_snap")
    assert rows[0]["kind"] == "self_seed" and rows[0]["vars"]["energy"] == 70.0 and rows[0]["closeness"] == {"achan": 72.0}
    assert rows[1]["kind"] == "self_snap" and abs(rows[1]["drift"]["fullness"] - 5.0) < 0.2


# ── E 字段 ──────────────────────────────────────────────────────────────────

def test_world_zone_names_and_town(client):
    w = client.get("/world").json()
    assert w["zone_names"]["sector"]["achan_house"] == "阿蝉家" and w["zone_names"]["arena"]["storage"] == "小仓库"
    assert w["worldState"]["town"] == "main"
    slim = client.get("/world", params={"fields": "zone_names,worldState"}).json()
    assert set(slim) == {"zone_names", "worldState"}


def test_ws_action_event_has_object_type():
    import time
    from fastapi.testclient import TestClient
    from main import app
    from tests.conftest import BED_STAND, BED_ID
    with TestClient(app) as c:
        pid = c.post("/player/join", json={"name": "w"}).json()["playerId"]
        with c.websocket_connect("/ws/world") as ws:
            json.loads(ws.receive_text())
            place(pid, *BED_STAND)
            c.post("/action", json={"entityId": pid, "action": {"type": "use", "payload": {}}})
            t0 = time.time(); ev = None
            while time.time() - t0 < 3 and ev is None:
                m = json.loads(ws.receive_text())
                if m["type"] == "action":
                    ev = m
    assert ev["object"] == BED_ID and ev["object_type"] == "bed"


def test_tile_gids_override_applied():
    t = world_state._MAP_DATA["tiled"]
    assert t["tilesets"][0]["imageSource"] == "gen/tiles.png" and t["tilesets"][0]["tilecount"] == 18


# ── B19 回放 ────────────────────────────────────────────────────────────────

def test_replay_synthetic_day_matches_state_log(client, fake_clock, tmp_path):
    """合成 2 小时：睡觉 / 吃饭 / effects 推送 / 切倍率 / 切 live；回放末态与 state_log 差 < 0.5。"""
    from game import replay as rp
    from game.paths import data_dir
    from tests.conftest import BED_STAND, BED_ID, FRIDGE_STAND
    fake_clock.t = _ts(8, 0)
    actions_mod.BASE_MOVE_INTERVAL = 0.0
    pid = client.post("/player/join", json={"name": "鲸仔", "controller": "agent", "profile": {"agent_id": "whale"}}).json()["playerId"]
    p = world_state._players[pid]
    # 初值通过会进 external 日志的 /effects 改（直接改 _players 不进日志，回放复现不了）
    client.post(f"/player/{pid}/effects", json={"source": "test", "effects": [
        {"type": "instant_effect", "key": "fullness", "value": -30}, {"type": "instant_effect", "key": "energy", "value": -70},
        {"type": "instant_effect", "key": "fun", "value": -40}]})
    ticker.tick_once(checkpoint=False)
    def run(seconds, step=10):
        for _ in range(int(seconds // step)):
            fake_clock.advance(step); ticker.tick_once(checkpoint=False)
    run(60)                                                       # 首样
    def goto(stand):                                              # 用会进日志的动作移动（回放要能复现位置）
        x, y, face = stand
        assert action(client, pid, "move", {"targetTile": {"x": x, "y": y}})["success"]
        assert action(client, pid, "turn", {"direction": face})["success"]
    goto(BED_STAND); assert action(client, pid, "use")["success"]            # 睡
    run(1800)
    client.post(f"/player/{pid}/effects", json={"source": "self", "event": "praised", "effects": [
        {"type": "instant_effect", "key": "mood", "value": 8}, {"type": "buff", "key": "emotion_tag", "tag": "smug", "mode": "timed", "duration": 40000}]})
    run(1200)
    assert action(client, pid, "leave")["success"]
    run(10)                                                       # 下一个 tick 复位 canUse
    client.post("/time/speed", json={"value": 3})                 # 不确定性事件（回放按 game_time，不受影响）
    goto(FRIDGE_STAND); assert action(client, pid, "use")["success"]       # 吃
    run(900)
    client.post(f"/player/{pid}/effects", json={"scene": "live", "effects": [{"type": "instant_effect", "key": "social", "value": 12}]})
    run(600)
    client.post(f"/player/{pid}/effects", json={"scene": "sandbox", "effects": []})
    for d in ("up", "down", "left", "right"):
        action(client, pid, "move", {"direction": d})
    run(2700)
    last = state_log.read_log(player=pid)[-1]
    today = date.today().isoformat()
    src = Path(data_dir())
    # 回放：另起干净状态（同进程，同 seed=None、同地图）
    res = rp.replay(today, src, threshold=0.5)
    assert res["ok"], res["table"]
    row = next(r for r in res["table"] if r["player"] == pid)
    assert row["max_abs"] < 0.5 and row["actual"] == {k: round(float(last["vars"][k]), 3) for k in ("fullness", "energy", "social", "fun", "mood")}
    assert res["applied"]["actions"] >= 11 and res["applied"]["effects_push"] == 4 and res["applied"]["action_result_mismatch"] == 0
    assert [e["op"] for e in res["nondeterministic"] if e["kind"] == "nondeterministic"] == ["time_speed"]
    assert row["replay"]["fullness"] == pytest.approx(row["actual"]["fullness"], abs=0.5)
