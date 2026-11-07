"""W8 Q0b：POST /admin/scenario 行为验收夹具——门禁与每个 op。"""
import json
from datetime import datetime

import pytest

from game import world_state, chat_state, time_state, external_log, state_log, ticker
from game.time_state import GAME_TZ
from tests.conftest import BED_ID, join, action, place


@pytest.fixture
def bench(monkeypatch):
    monkeypatch.setenv("SANDBOX_SCENARIO", "1")


def _run(client, steps, label="T"):
    r = client.post("/admin/scenario", json={"label": label, "steps": steps})
    assert r.status_code == 200, r.text
    return r.json()


def test_disabled_by_default(client, monkeypatch):
    monkeypatch.delenv("SANDBOX_SCENARIO", raising=False)
    assert client.post("/admin/scenario", json={"steps": [{"op": "reset"}]}).status_code == 403


def test_reset_set_time_spawn(client, bench, fake_clock):
    join(client, "leftover")
    r = _run(client, [
        {"op": "reset"},
        {"op": "set_time", "time": "11:30", "date": "2026-11-10"},
        {"op": "spawn", "name": "鲸仔", "agent_id": "whale", "x": 35, "y": 25, "facing": "up", "vars": {"fullness": 15}},
    ], label="S01")
    assert r["ok"] and len(r["steps"]) == 3
    assert r["world"]["time"]["time"] == "11:30:00" and r["world"]["time"]["date"] == "2026-11-10" and r["world"]["time"]["running"] is True
    assert len(r["world"]["players"]) == 1
    w = r["world"]["players"][0]
    assert w["name"] == "鲸仔" and w["position"] == {"x": 35, "y": 25} and w["vars"]["fullness"] == 15.0 and w["controller"] == "agent"
    assert world_state.get_zone_at(35, 25)["arena"] == "square"
    # 时间继续走
    fake_clock.advance(90)
    assert time_state.get_time_state()["time"] == "11:31:30"
    # 外部日志每步一条 scenario，受影响玩家立即采样
    rows = external_log.read_log(kind="scenario")
    assert [x["op"] for x in rows] == ["reset", "set_time", "spawn"] and rows[-1]["label"] == "S01" and rows[-1]["entity"] == w["id"]
    assert state_log.read_log(player=w["id"])[-1]["kind"] == "scenario"


def test_teleport_and_name_resolution(client, bench):
    pid = join(client, "阿蝉")
    r = _run(client, [{"op": "teleport", "player": "阿蝉", "x": 52, "y": 19, "facing": "right"}])
    assert r["ok"] and r["steps"][0]["detail"]["position"] == {"x": 52, "y": 19} and r["steps"][0]["detail"]["facing"] == "right"
    assert world_state._players[pid]["pos_seq"] == 1
    r = _run(client, [{"op": "teleport", "player": "阿蝉", "x": 2, "y": 2}])
    assert r["ok"] is False and "not walkable" in r["error"] and r["steps"] == []
    join(client, "阿蝉")                                           # 同名两个 → 歧义
    assert "ambiguous" in _run(client, [{"op": "teleport", "player": "阿蝉", "x": 6, "y": 9}])["error"]


def test_set_vars_effects_closeness(client, bench):
    pid = join(client, "w")
    r = _run(client, [
        {"op": "set_vars", "player": pid, "vars": {"fullness": 15, "hp": 15, "mood": 40}, "mood_base": 69.5, "scene": "live", "closeness": {"achan": 72}},
        {"op": "effects", "player": pid, "effects": [{"type": "instant_effect", "key": "fun", "value": -30},
                                                     {"type": "buff", "key": "emotion_tag", "tag": "smug", "mode": "timed", "duration": 40000}]},
    ])
    assert r["ok"]
    p = world_state._players[pid]
    assert p["fullness"] == 15.0 and p["hp"] == 15.0 and p["mood"] == 40.0 and p["mood_base"] == 69.5 and p["scene"] == "live"
    assert p["closeness"] == {"achan": 72.0} and p["fun"] == 30.0 and [t["key"] for t in p["emotion_tags"]] == ["smug"]
    assert "unknown vars" in _run(client, [{"op": "set_vars", "player": pid, "vars": {"luck": 1}}])["error"]
    # 直写不进 self-sync 待发池（track=False）
    from game import self_sync
    assert self_sync.snapshot_stats()["pending"].get(pid, {}) == {}


def test_occupy_sticky_blocks_other_and_survives_max_duration(client, bench, fake_clock):
    fake_clock.t = datetime(2026, 11, 10, 12, 0, tzinfo=GAME_TZ).timestamp()
    npc = join(client, "npc"); me = join(client, "me")
    r = _run(client, [{"op": "occupy", "player": npc, "object": BED_ID, "sticky": True}])
    assert r["ok"]
    d = r["steps"][0]["detail"]
    assert d["usingObjectId"] == BED_ID and d["state"] == "using"
    obj = world_state.get_object_by_id(BED_ID)
    assert obj["currentUsers"] == 1 and obj["userList"] == [npc]
    assert world_state._use_start_times[npc] is None                 # sticky：不自动离开
    place(me, 3, 5, "up")
    res = action(client, me, "use")
    assert res["success"] is False and res["reason"] == "object_full"   # S05：目标被占
    # 跳过营业时间 / 冷却：22:30 占餐桌也行
    _run(client, [{"op": "set_time", "time": "22:30"}])
    r = _run(client, [{"op": "occupy", "player": me, "object": "table_rest_1"}])
    assert r["ok"] and world_state._players[me]["usingObjectId"] == "table_rest_1"
    # 非 continuous / 满员 报错
    assert "only for continuous" in _run(client, [{"op": "occupy", "player": me, "object": "fridge_kitchen"}])["error"]
    assert "object_full" in _run(client, [{"op": "occupy", "player": me, "object": BED_ID}])["error"]
    r = _run(client, [{"op": "release", "player": npc}])
    assert r["ok"] and r["steps"][0]["detail"]["left"] == BED_ID and obj["currentUsers"] == 0


def test_occupy_stream_desk_sets_live_without_calling_self(client, bench):
    pid = client.post("/player/join", json={"name": "w", "controller": "agent", "profile": {"agent_id": "whale"}}).json()["playerId"]
    r = _run(client, [{"op": "occupy", "player": pid, "object": "stream_desk_whale"}])
    assert r["ok"] and world_state._players[pid]["scene"] == "live" and "streaming" in world_state._players[pid]["tags"]


def test_chat_ops_bypass_cooldown(client, bench):
    a = join(client, "a"); b = join(client, "b")
    place(a, 6, 9, "down"); place(b, 7, 9, "down")
    chat_state._last_chat_end[a] = __import__("time").time()        # a 本应在冷却
    r = _run(client, [{"op": "invite", "from": "a", "to": ["b"], "greeting": "昨天你干了什么？"}])
    rid = r["steps"][0]["detail"]["request_id"]
    assert rid and chat_state._chat_requests[rid]["status"] == "pending"
    r = _run(client, [{"op": "respond", "player": "b", "request_id": rid, "accept": True, "message": "钓鱼"}])
    d = r["steps"][0]["detail"]
    assert d["status"] == "walking_over" and d["status_now"] == "active" and d["chat_room_id"]
    room = d["chat_room_id"]
    r = _run(client, [{"op": "say", "player": "a", "room": room, "text": "然后呢"}, {"op": "exit_chat", "player": "a", "room": room}])
    assert r["ok"] and r["steps"][0]["detail"]["seq"] == 3 and r["steps"][1]["detail"]["room_closed"] is False
    got = client.get(f"/chat/room/{room}", params={"entity_id": b}).json()
    assert [m["content"] for m in got["messages"]] == ["昨天你干了什么？", "钓鱼", "然后呢"]
    assert "room not found" in _run(client, [{"op": "say", "player": "a", "room": "nope", "text": "x"}])["error"]


def test_remove_clear_cooldowns_and_unknown_op(client, bench, fake_clock):
    pid = join(client, "w")
    place(pid, 10, 4, "up"); assert action(client, pid, "use")["success"]; action(client, pid, "leave")   # desk_whale（床类无冷却）
    assert world_state.object_cooldown_remaining(pid, "desk_whale") > 0
    assert _run(client, [{"op": "clear_cooldowns", "player": pid}])["ok"]
    assert world_state.object_cooldown_remaining(pid, "desk_whale") == 0.0
    r = _run(client, [{"op": "remove", "player": pid}])
    assert r["ok"] and pid not in world_state._players
    r = _run(client, [{"op": "fly"}])
    assert r["ok"] is False and "unknown op" in r["error"]
    r = _run(client, [{"op": "remove", "player": "ghost"}])
    assert r["ok"] is False and "not found" in r["error"]


def test_s02_setup_end_to_end(client, bench):
    """S02：时间 01:50、放在街道、床可达。"""
    r = _run(client, [
        {"op": "reset"}, {"op": "set_time", "time": "01:50"},
        {"op": "spawn", "name": "鲸仔", "agent_id": "whale", "x": 20, "y": 19, "facing": "up"},
    ], label="S02")
    assert r["ok"]
    pid = r["world"]["players"][0]["id"]
    assert world_state.get_zone_at(20, 19)["arena"] == "road"
    res = action(client, pid, "move_to_area", {"area_type": "arena", "area_id": "storage"})
    assert res["success"]


def test_scenario_rows_replay_as_external_inputs(client, bench, fake_clock):
    """摆放是外部输入：回放按 scenario 行重现 set_vars / teleport。"""
    from game import replay as rp
    from game.paths import data_dir
    from datetime import date
    from routers import actions as actions_mod
    actions_mod.BASE_MOVE_INTERVAL = 0.0
    fake_clock.t = datetime(2026, 11, 10, 9, 0, tzinfo=GAME_TZ).timestamp()
    pid = client.post("/player/join", json={"name": "鲸仔", "controller": "agent", "profile": {"agent_id": "whale"}}).json()["playerId"]
    ticker.tick_once(checkpoint=False); fake_clock.advance(60); ticker.tick_once(checkpoint=False)
    _run(client, [{"op": "set_vars", "player": pid, "vars": {"energy": 20}}, {"op": "teleport", "player": pid, "x": 3, "y": 5, "facing": "up"}])
    assert action(client, pid, "use")["success"]
    for _ in range(60):
        fake_clock.advance(30); ticker.tick_once(checkpoint=False)
    res = rp.replay(date.today().isoformat(), data_dir(), threshold=0.5)
    row = next(x for x in res["table"] if x["player"] == pid)
    assert res["applied"].get("scenario") == 2 and row["max_abs"] < 0.5, row


def test_give_item_and_produce_ops(client, monkeypatch):
    """W11 维护：give_item / produce 两个 op（E 联调产出气泡用）。"""
    monkeypatch.setenv("SANDBOX_SCENARIO", "1")
    from game import inventory, world_state
    pid = client.post("/player/join", json={"name": "鲸仔"}).json()["playerId"]
    r = client.post("/admin/scenario", json={"steps": [
        {"op": "give_item", "player": pid, "item": "bread", "qty": 2},
        {"op": "produce", "player": pid, "via": "fishing", "item": "fish"},
        {"op": "give_item", "player": pid, "item": "unicorn"},
    ]}).json()
    assert r["ok"] is False and r["error"].startswith("step 2") and len(r["steps"]) == 2
    p = world_state._players[pid]
    assert inventory.count(p, "bread") == 2 and inventory.count(p, "fish") == 1
    assert world_state._pending_messages[pid] == "钓到一条鱼！"
