"""W6 任务 1：数据集字段、state 快照、/admin/export。"""
import json
from datetime import date

import pytest

from game import world_state, ticker, state_log
from game.paths import data_dir
from tests.conftest import BED_STAND, join, action, place


def test_action_and_chat_lines_carry_dataset_fields(client):
    a = join(client, "a"); b = join(client, "b")
    action(client, a, "turn", {"direction": "up"})
    row = json.loads((data_dir() / "actions" / f"{date.today().isoformat()}.jsonl").read_text().splitlines()[-1])
    assert row["town"] == world_state.TOWN == "main" and row["map_version"] == world_state.MAP_VERSION and "seed" in row
    place(a, 6, 9, "down"); place(b, 7, 9, "down")
    rid = client.post("/chat/request", json={"from_entity_id": a, "to_entity_ids": [b], "greeting": "hi"}).json()["request_id"]
    client.post("/chat/respond", json={"entity_id": b, "request_id": rid, "accept": True, "message": "yo"})
    from game import chat_state; chat_state.tick()
    row = json.loads((data_dir() / "chat" / f"{date.today().isoformat()}.jsonl").read_text().splitlines()[-1])
    assert row["town"] == "main" and row["map_version"] == world_state.MAP_VERSION and "seed" in row and row["kind"] == "message"


def test_state_samples_every_30_game_seconds(client, fake_clock):
    a = join(client, "a")
    ticker.tick_once(checkpoint=False)                 # 第一次 tick 没有 game_delta → 不采样
    fake_clock.advance(1); ticker.tick_once(checkpoint=False)        # 首样
    for _ in range(3):
        fake_clock.advance(31); ticker.tick_once(checkpoint=False)
    fake_clock.advance(5); ticker.tick_once(checkpoint=False)        # 不足 30 s 不采
    rows = state_log.read_log(player=a)
    assert len(rows) == 4
    r = rows[-1]
    assert set(r["vars"]) == {"fullness", "energy", "social", "fun", "mood"}
    for k in ("kind", "ts", "game_time", "town", "map_version", "seed", "player_id", "agent_id", "controller", "scene",
              "emotion_tags", "closeness", "online", "position", "using"):
        assert k in r, k
    assert r["kind"] == "sample" and r["controller"] == "human" and r["position"] == {"x": 6, "y": 9}
    assert state_log.read_log(date="1999-01-01") == []


def test_admin_export_counts_match_files(client, fake_clock):
    a = join(client, "a"); b = join(client, "b")
    for d in ("up", "down", "left"):
        action(client, a, "turn", {"direction": d})
    place(a, 6, 9, "down"); place(b, 7, 9, "down")
    rid = client.post("/chat/request", json={"from_entity_id": a, "to_entity_ids": [b], "greeting": "hi"}).json()["request_id"]
    client.post("/chat/respond", json={"entity_id": b, "request_id": rid, "accept": True, "message": "yo"})
    from game import chat_state; chat_state.tick()
    ticker.tick_once(checkpoint=False); fake_clock.advance(1); ticker.tick_once(checkpoint=False)
    today = date.today().isoformat()
    r = client.get("/admin/export", params={"date": today})
    assert r.status_code == 200
    d = r.json()
    assert d["schema"] == "sandbox-0.1" and d["town"] == "main" and d["map_version"] == world_state.MAP_VERSION and d["date"] == today
    counts = d["manifest"]["counts"]
    assert counts == {"actions": len(d["actions"]), "chat": len(d["chat"]), "state": len(d["state"]), "external": len(d["external"])}
    assert counts["actions"] == 3 and counts["chat"] == 3 and counts["state"] == 2 and counts["external"] == 0
    for kind in ("actions", "chat", "state"):
        fp = data_dir() / kind / f"{today}.jsonl"
        assert d["manifest"]["files"][kind]["exists"] and len(fp.read_text().splitlines()) == counts[kind]
        assert d["manifest"]["files"][kind]["bytes"] == fp.stat().st_size
    # kinds 过滤、空日期、坏日期
    only = client.get("/admin/export", params={"date": today, "kinds": "chat"}).json()
    assert "actions" not in only and only["manifest"]["counts"] == {"chat": 3}
    empty = client.get("/admin/export", params={"date": "2001-01-01"}).json()
    assert empty["manifest"]["counts"] == {"actions": 0, "chat": 0, "state": 0, "external": 0} and empty["actions"] == []
    assert client.get("/admin/export", params={"date": "20011-1-1"}).status_code == 400
    # 旧行（没有数据集字段）回填并标记
    fp = data_dir() / "actions" / f"{today}.jsonl"
    fp.write_text(fp.read_text() + json.dumps({"timestamp": "2026-11-06T00:00:00.000", "entityId": "old", "type": "turn", "payload": {},
                                               "success": True, "reason": None, "label": None, "game_time": None, "controller": "human"}) + "\n")
    d = client.get("/admin/export", params={"date": today, "kinds": "actions"}).json()
    assert d["manifest"]["backfilled_rows"] == 1 and d["actions"][-1]["backfilled"] is True and d["actions"][-1]["town"] == "main"
    assert all({"town", "map_version", "seed"} <= set(r) for r in d["actions"])


def test_export_backfills_state_tags_and_reports_field_sets(client, fake_clock):
    """W9 第 0 项：旧 state 行没有 tags / facing / mood_base → 导出按规范字段集回填；manifest 带 fields。"""
    from routers.player import EXPORT_FIELDS
    a = join(client, "a")
    today = date.today().isoformat()
    fp = data_dir() / "state" / f"{today}.jsonl"
    old_row = {"kind": "sample", "ts": "2026-11-06T00:00:00.000", "game_time": "2026-11-06T00:00:00+08:00", "town": "main",
               "map_version": "x", "seed": None, "player_id": "old", "agent_id": None, "controller": "human", "scene": "sandbox",
               "vars": {"fullness": 1, "energy": 2, "social": 3, "fun": 4, "mood": 5}, "emotion_tags": [], "closeness": {},
               "online": True, "position": {"x": 1, "y": 1}, "using": None}
    fp.write_text(fp.read_text() + json.dumps(old_row) + "\n")
    d = client.get("/admin/export", params={"date": today}).json()
    rows = d["state"]
    assert all(set(EXPORT_FIELDS["state"]) <= set(r) for r in rows)
    old = next(r for r in rows if r["player_id"] == "old")
    assert old["tags"] == [] and old["facing"] is None and old["mood_base"] is None and old["backfilled"] is True
    new = next(r for r in rows if r["player_id"] == a)
    assert "backfilled" not in new and isinstance(new["tags"], list) and new["kind"] == "join"
    assert all(set(EXPORT_FIELDS["actions"]) <= set(r) for r in d["actions"])
    assert d["manifest"]["fields"]["state"][-1] == "tags" and set(d["manifest"]["fields"]) == {"actions", "chat", "state", "external"}
