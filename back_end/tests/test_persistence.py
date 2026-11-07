"""B2：SQLite 检查点，重启回填。"""
import json
import sqlite3

import pytest

from game import persistence, world_state, chat_state, time_state, ticker
from tests.conftest import BED_ID, BED_STAND, place, join, action


def _simulate_restart(fake_clock, downtime_s: float):
    """清空内存状态（像新进程），停机 downtime_s 后 load_checkpoint。"""
    world_state._reset_for_tests()
    chat_state._reset_for_tests()
    time_state._reset_for_tests()
    ticker._reset_for_tests()
    fake_clock.advance(downtime_s)
    return persistence.load_checkpoint()


def test_no_checkpoint_returns_none():
    assert persistence.load_checkpoint() is None


def test_roundtrip_players_objects_time(client, fake_clock):
    pid = join(client, "whale")
    assert action(client, pid, "move", {"direction": "right"})["success"]
    pos_before = dict(world_state._players[pid]["position"])
    place(pid, *BED_STAND)
    assert action(client, pid, "use")["success"]
    world_state._players[pid]["energy"] = 20.0
    world_state._players[pid]["closeness"] = {"achan": 72.0}
    time_state.set_speed(3)
    g_before = time_state.game_now_ts()
    use_start = world_state._use_start_times[pid]

    summary = persistence.save_checkpoint()
    assert summary["players"] == 1

    info = _simulate_restart(fake_clock, downtime_s=20)
    assert info is not None and info["players"] == 1

    p = world_state._players[pid]
    assert p["position"] == {"x": 3, "y": 3}          # W10：use 后躺在床格上
    assert p["usingObjectId"] == BED_ID
    assert p["state"] == "using"
    assert p["closeness"] == {"achan": 72.0}
    assert any(b["key"] == "energy_regen" for b in p["buffs"])
    obj = world_state.get_object_by_id(BED_ID)
    assert obj["userList"] == [pid] and obj["currentUsers"] == 1
    assert world_state._use_start_times[pid] == use_start
    # 时间连续：停机 20 真实秒 × speed 3
    assert time_state.get_time_state()["speed"] == 3
    assert time_state.game_now_ts() - g_before == pytest.approx(60)
    # 停机补算：20s × 3 = 60 游戏秒，上限 8h
    assert info["catch_up_game_ms"] == pytest.approx(60_000)
    # catch_up 后 bed energy_regen +25/h 减衰减 8/h，补 60 游戏秒
    persistence.catch_up(info["catch_up_game_ms"])
    assert p["energy"] == pytest.approx(20.0 + 60 * (25 - 8) / 3600, abs=0.01)
    # 重启后 GET /player 仍能读到她
    r = client.get(f"/player/{pid}")
    assert r.status_code == 200 and r.json()["usingObjectId"] == BED_ID


def test_restored_players_get_grace_period(client, fake_clock):
    pid = join(client)
    persistence.save_checkpoint()
    _simulate_restart(fake_clock, downtime_s=3600)
    ticker.tick_once(checkpoint=False)             # 第一个 tick 不能把她当 stale 清掉
    assert pid in world_state._players


def test_catch_up_capped_at_8_hours(client, fake_clock):
    persistence.save_checkpoint()
    _simulate_restart(fake_clock, downtime_s=48 * 3600)
    assert persistence.catch_up_game_ms(48 * 3600) == persistence.CATCH_UP_MAX_GAME_MS
    time_state.set_running(False)
    assert persistence.catch_up_game_ms(100) == 0.0


def test_chat_state_roundtrip(client, fake_clock):
    a = join(client, "a"); b = join(client, "b")
    r = client.post("/chat/request", json={"from_entity_id": a, "to_entity_ids": [b], "greeting": "hi"})
    rid = r.json()["request_id"]
    r = client.post("/chat/respond", json={"entity_id": b, "request_id": rid, "accept": True, "message": "yo"})
    assert r.json()["status"] == "walking_over"              # B9：先走过去
    chat_state.tick()                                        # 两人都在出生点、相邻 → 建房
    room = client.get(f"/chat/request/{rid}").json()["chat_room_id"]
    assert room
    client.post("/chat/message", json={"entity_id": a, "chat_room_id": room, "content": "第三句"})

    persistence.save_checkpoint()
    _simulate_restart(fake_clock, downtime_s=1)

    got = client.get(f"/chat/room/{room}", params={"entity_id": a}).json()
    assert got["status"] == "active"
    assert [m["content"] for m in got["messages"]] == ["hi", "yo", "第三句"]
    assert chat_state._MSG_SEQ_COUNTER[room] == 3
    assert chat_state._chat_requests[rid]["status"] == "active"
    assert world_state._players[a]["state"] == "talking"
    # seq 继续递增而不是从 0 重来
    assert chat_state.post_message(a, room, "x")["seq"] == 4


def test_old_schema_player_gets_defaults(client, fake_clock):
    pid = join(client)
    p = world_state._players[pid]
    for k in ("fullness", "social", "fun", "mood", "emotion_tags", "closeness", "controller", "last_tick_ts"):
        p.pop(k)
    p["hp"] = 33.0
    persistence.save_checkpoint()
    _simulate_restart(fake_clock, downtime_s=0)
    p = world_state._players[pid]
    assert p["fullness"] == 33.0 and p["hp"] == 33.0
    assert p["controller"] == "human" and p["closeness"] == {} and p["emotion_tags"] == []


def test_checkpoint_tables_exist_and_meta_written(client):
    join(client)
    persistence.save_checkpoint()
    conn = sqlite3.connect(persistence.db_path())
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"players", "object_runtime", "time_state", "chat_requests", "chat_rooms", "meta"} <= tables
    meta = dict(conn.execute("SELECT key, value FROM meta"))
    assert "last_tick_ts" in meta and meta["schema_version"] == "1"
    conn.close()


def test_admin_checkpoint_endpoint(client):
    join(client)
    r = client.post("/admin/checkpoint")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["players"] == 1
    assert persistence.db_path().exists()


def test_lifespan_restores_on_startup(fake_clock):
    """带 lifespan 的真实启动：有检查点就回填并启动 ticker；关停时写最后一份。"""
    from fastapi.testclient import TestClient
    from main import app
    from tests.conftest import join as _join
    with TestClient(app) as c:
        pid = _join(c, "w")
        place(pid, 5, 5, "down")
        c.post("/admin/checkpoint")
    world_state._reset_for_tests()
    with TestClient(app) as c:
        r = c.get(f"/player/{pid}")
        assert r.status_code == 200
        assert r.json()["position"] == {"x": 5, "y": 5}
