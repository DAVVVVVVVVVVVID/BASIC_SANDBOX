"""W5 任务 2：E 的 7 条。"""
import json
import time

import pytest
from fastapi.testclient import TestClient

from game import world_state
from tests.conftest import BED_ID, BED_STAND, join, action, place


# ① players[] 加 stateLabel / usingObjectId / tags
def test_players_carry_state_label_using_tags(client):
    pid = join(client, "w")
    place(pid, *BED_STAND)
    assert action(client, pid, "use")["success"]
    p = next(x for x in client.get("/world").json()["players"] if x["id"] == pid)
    assert p["usingObjectId"] == BED_ID and p["stateLabel"] and "sleeping" in p["tags"]
    action(client, pid, "leave")
    p = next(x for x in client.get("/world").json()["players"] if x["id"] == pid)
    assert p["usingObjectId"] is None and p["stateLabel"] is None and p["tags"] == []


# ② 心跳
def test_get_player_no_side_effect_for_agent_but_heartbeat_endpoint(client):
    a = client.post("/player/join", json={"name": "w", "controller": "agent", "profile": {"agent_id": "whale"}}).json()["playerId"]
    h = join(client, "h")
    world_state._players[a]["online"] = False; world_state._last_seen[a] = 0
    world_state._players[h]["online"] = False; world_state._last_seen[h] = 0
    assert client.get(f"/player/{a}").json()["online"] is False and world_state._last_seen[a] == 0   # agent：纯只读
    assert client.get(f"/player/{h}").json()["online"] is True and world_state._last_seen[h] > 0     # human：老路径仍刷
    r = client.post(f"/player/{a}/heartbeat").json()
    assert r["ok"] and r["online"] is True and world_state._last_seen[a] > 0 and "last_tick_ts" in r
    assert client.post("/player/ghost/heartbeat").status_code == 404
    assert client.get(f"/player/{a}/state").status_code == 200                                      # /state 一直只读


# ③ /world 瘦身 + mapVersion
def test_world_fields_and_map_version(client):
    full = client.get("/world").json()
    assert full["worldState"]["mapVersion"].startswith("阿蝉家与小镇@")
    slim = client.get("/world", params={"fields": "players,objects,worldState"}).json()
    assert set(slim) == {"players", "objects", "worldState"}
    assert slim["worldState"] == full["worldState"] or {k: v for k, v in slim["worldState"].items() if k != "time"} == {k: v for k, v in full["worldState"].items() if k != "time"}
    assert slim["objects"] == full["objects"] and slim["players"] == full["players"]
    assert len(json.dumps(slim)) < len(json.dumps(full)) / 5
    assert set(client.get("/world", params={"fields": "worldState,bogus"}).json()) == {"worldState"}
    assert set(client.get("/world", params={"fields": "players"}).json()) == {"players"}


# ⑤ tiled
def test_map_has_tiled_layers(client):
    w = client.get("/world").json()
    t = w["tiled"]
    assert t["tilesets"][0]["imageSource"] == "gen/tiles.png"          # W7：E 交付的 tile_gids.json 的 _tileset
    assert t["tilesets"][0]["name"] == "whale_gen_tiles" and set(t["layers"][0]["data"]) <= {1, 7, 9, 11, 18}
    assert [l["name"] for l in t["layers"]] == ["ground", "structures"]
    assert all(len(l["data"]) == 60 * 40 and l["width"] == 60 and l["height"] == 40 for l in t["layers"])
    assert all(g > 0 for g in t["layers"][0]["data"])


# ⑥ pos_seq
def test_pos_seq_monotonic(client):
    pid = join(client, "w")
    p0 = client.get(f"/player/{pid}").json()
    assert p0["pos_seq"] == 0
    action(client, pid, "turn", {"direction": "up"})                 # 转向不动序号
    assert client.get(f"/player/{pid}").json()["pos_seq"] == 0
    action(client, pid, "move", {"direction": "right"})
    action(client, pid, "move", {"direction": "left"})
    p = client.get(f"/player/{pid}").json()
    assert p["pos_seq"] == 2
    assert next(x for x in client.get("/world").json()["players"] if x["id"] == pid)["pos_seq"] == 2
    res = action(client, pid, "move", {"direction": "up"})            # 撞墙不动 → 不增
    seq_after = client.get(f"/player/{pid}").json()["pos_seq"]
    assert seq_after == (3 if res["success"] else 2)


# ④⑦ ws：chat from_name（已在 test_ws 覆盖）、action 事件
def test_ws_action_events():
    from main import app
    with TestClient(app) as c:
        pid = c.post("/player/join", json={"name": "w"}).json()["playerId"]
        with c.websocket_connect("/ws/world") as ws:
            json.loads(ws.receive_text())
            place(pid, *BED_STAND)
            c.post("/action", json={"entityId": pid, "action": {"type": "use", "payload": {}}})
            c.post("/action", json={"entityId": pid, "action": {"type": "move", "payload": {"direction": "up"}}})
            events = []
            t0 = time.time()
            while time.time() - t0 < 3 and len(events) < 2:
                m = json.loads(ws.receive_text())
                if m["type"] == "action":
                    events.append(m)
        assert events[0] == {**events[0], "type": "action", "entity": pid, "action": "use", "object": BED_ID, "success": True, "reason": None}
        assert "T" in events[0]["ts"]
        assert events[1]["action"] == "move" and events[1]["success"] is False and events[1]["reason"] in ("move_disabled", "tile_not_walkable")


# 任务 4：SANDBOX_SEED
def test_seed_makes_player_ids_deterministic(monkeypatch):
    import random
    monkeypatch.setattr(world_state, "_id_rng", random.Random(7))
    a = world_state.create_player("x")["id"]
    monkeypatch.setattr(world_state, "_id_rng", random.Random(7))
    world_state._players.pop(a)
    b = world_state.create_player("x")["id"]
    assert a == b
    monkeypatch.setattr(world_state, "_id_rng", None)
    assert world_state.create_player("x")["id"] != a


def test_metrics_report_seed_and_map_version(client):
    m = client.get("/admin/metrics").json()
    assert "seed" in m and m["mapVersion"] == world_state.MAP_VERSION
