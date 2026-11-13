"""§3.36（主播 11-07 20:55）：移动必须有路、按 1 格 / 游戏秒花时间；walking 状态；no_path 带首个阻塞；move_done 日志；聊天 / leave 就地停。"""
import json
from datetime import datetime

from game import world_state, ticker, chat_state
from game.action_log import read_log
from game.time_state import GAME_TZ
from tests.conftest import join, action, place, walk_done, BED_STAND, BED_ID
from tests.test_w9_map_v2 import v12  # noqa: F401


def _agent(client, aid, name=None):
    return client.post("/player/join", json={"name": name or aid, "controller": "agent", "profile": {"agent_id": aid}}).json()["playerId"]


def _at(fake_clock, h, m=0):
    fake_clock.t = datetime(2026, 11, 10, h, m, tzinfo=GAME_TZ).timestamp()


def _tick(fake_clock, s=1.0):
    fake_clock.advance(s); ticker.tick_once(checkpoint=False)


def test_target_tile_walks_one_tile_per_game_second_and_logs_move_done(client, fake_clock):
    pid = _agent(client, "whale")
    place(pid, 4, 3, "down")
    r = action(client, pid, "move", {"targetTile": {"x": 4, "y": 9}})                      # 6 格直线
    assert r["success"] and r["result"]["state"] == "walking" and r["result"]["path_len"] == 6 and r["result"]["eta_game_s"] == 6.0
    assert r["result"]["position"] == {"x": 4, "y": 3}                                        # 请求立即返回，人还没动
    p = client.get(f"/player/{pid}").json()
    assert p["state"] == "walking" and p["walk"] == {**p["walk"], "remaining": 6, "path_len": 6, "eta_game_s": 6.0, "next": {"x": 4, "y": 4}}
    ticker.tick_once(checkpoint=False)
    _tick(fake_clock, 0.5); assert world_state._players[pid]["position"] == {"x": 4, "y": 3}      # 0.5 s：还没到 1 格
    _tick(fake_clock, 0.6); assert world_state._players[pid]["position"] == {"x": 4, "y": 4}      # 1.1 s：第 1 格
    _tick(fake_clock, 2.0); assert world_state._players[pid]["position"] == {"x": 4, "y": 6}      # 3.1 s：第 3 格（一 tick 补两格）
    assert client.get(f"/player/{pid}").json()["walk"]["remaining"] == 3
    _tick(fake_clock, 10.0)
    p = client.get(f"/player/{pid}").json()
    assert p["position"] == {"x": 4, "y": 9} and p["state"] == "idle" and p["walk"] is None and p["facing"] == "down"
    done = [a for a in read_log(entity=pid) if a["type"] == "move_done"]
    assert len(done) == 1 and done[0]["success"] is True
    pl = done[0]["payload"]
    assert pl["outcome"] == "arrived" and pl["position"] == {"x": 4, "y": 9} and pl["path_len"] == 6 and pl["steps_done"] == 6 and pl["action"] == "move"
    assert 6.0 <= pl["game_s"] <= 14.0 and pl["start"] == {"x": 4, "y": 3}


def test_walk_speed_env_and_human_direction_immediate(client, fake_clock, monkeypatch):
    monkeypatch.setattr(world_state, "WALK_TILE_SEC", 2.0)                                   # SANDBOX_WALK_TILE_SEC
    pid = _agent(client, "whale"); place(pid, 4, 3, "down")
    r = action(client, pid, "move", {"targetTile": {"x": 4, "y": 5}})
    assert r["result"]["eta_game_s"] == 4.0
    ticker.tick_once(checkpoint=False); _tick(fake_clock, 1.5)
    assert world_state._players[pid]["position"] == {"x": 4, "y": 3}
    _tick(fake_clock, 0.6)
    assert world_state._players[pid]["position"] == {"x": 4, "y": 4}
    # 人类单格 direction 免排队（立即到位）；人类 targetTile 也排队
    h = join(client, "h"); place(h, 4, 3, "down")
    r = action(client, h, "move", {"direction": "down"})
    assert r["success"] and r["result"]["state"] == "idle" and world_state._players[h]["position"] == {"x": 4, "y": 4}
    r = action(client, h, "move", {"targetTile": {"x": 4, "y": 8}})
    assert r["result"]["state"] == "walking" and world_state._players[h]["state"] == "walking"
    r = action(client, h, "move", {"direction": "up"})                                            # 走路中按方向键：就地改手动
    assert r["success"] and world_state._players[h]["position"] == {"x": 4, "y": 3} and h not in world_state._walks
    assert [a["payload"]["outcome"] for a in read_log(entity=h) if a["type"] == "move_done"] == ["stopped"]
    # agent 单格 direction 也排队（1 格 / 1 游戏秒）
    r = action(client, pid, "move", {"direction": "down"})
    assert r["success"] and r["result"]["state"] == "walking" and r["result"]["path_len"] == 1


def test_no_path_and_locked_blocked_detail(client, v12, fake_clock):
    whale = _agent(client, "whale")
    _at(fake_clock, 10, 0)
    place(whale, 9, 13, "down")
    r = action(client, whale, "move", {"targetTile": {"x": 4, "y": 31}})                         # 阿蝉房（2F，09–18:30 锁）
    assert r["success"] is False and r["reason"] == "no_path"
    assert r["result"]["blocked_reason"] == "locked" and r["result"]["blocked_at"] == {"x": 3, "y": 30} and r["result"]["opens_at"] == "18:30"
    assert world_state._players[whale]["state"] == "idle" and whale not in world_state._walks
    r = action(client, whale, "move", {"targetTile": {"x": 47, "y": 5}})                         # 河里：不可走
    assert r["reason"] == "tile_not_walkable"
    r = action(client, whale, "move_to_area", {"area_type": "arena", "area_id": "fisher_bedroom"})  # 常锁
    assert r["reason"] == "no_path" and r["result"]["blocked_reason"] == "locked" and r["result"]["opens_at"] is None
    # 走着走着门关了 → blocked：10:59 出发去校园图书馆……（用餐厅：13:58 出发，门 14:00 关）
    _at(fake_clock, 13, 59); fake_clock.advance(50)                                                 # 13:59:50 出发，门 14:00 关，16 格走不完
    place(whale, 28, 14, "right")
    r = action(client, whale, "move_to_area", {"area_type": "arena", "area_id": "dining"})
    assert r["success"] and r["result"]["path_len"] > 10
    _tick(fake_clock, 1.0)
    for _ in range(90):
        _tick(fake_clock, 1.0)
        if whale not in world_state._walks:
            break
    done = [a for a in read_log(entity=whale) if a["type"] == "move_done"][-1]
    assert done["success"] is False and done["payload"]["outcome"] == "blocked" and done["reason"] == "closed"
    assert world_state._players[whale]["state"] == "idle" and 0 < done["payload"]["steps_done"] < done["payload"]["path_len"]


def test_use_interact_rejected_while_walking_and_leave_stops(client, fake_clock):
    pid = _agent(client, "whale"); place(pid, 3, 9, "up")
    r = action(client, pid, "move", {"targetTile": {"x": 3, "y": 5}})
    assert r["success"]
    assert action(client, pid, "use")["reason"] == "walking" and action(client, pid, "interact")["reason"] == "walking"
    ticker.tick_once(checkpoint=False); _tick(fake_clock, 1.2)
    assert world_state._players[pid]["position"] == {"x": 3, "y": 8}
    r = action(client, pid, "leave")                                                                 # 走路中 leave = 就地停
    assert r["success"] and r["result"]["stopped_walk"]["outcome"] == "stopped" and r["result"]["position"] == {"x": 3, "y": 8}
    assert world_state._players[pid]["state"] == "idle" and pid not in world_state._walks
    assert action(client, pid, "leave")["reason"] == "not_using_any_object"
    # 新 move 替换旧路径：旧路径记 stopped/replaced
    action(client, pid, "move", {"targetTile": {"x": 3, "y": 5}})
    r = action(client, pid, "move", {"targetTile": {"x": 5, "y": 8}})
    assert r["success"] and client.get(f"/player/{pid}").json()["walk"]["target"] == {"x": 5, "y": 8}
    outcomes = [(a["payload"]["outcome"], a["payload"]["reason"]) for a in read_log(entity=pid) if a["type"] == "move_done"]
    assert outcomes[-1] == ("stopped", "replaced")
    walk_done(pid, fake_clock)
    assert world_state._players[pid]["position"] == {"x": 5, "y": 8}


def test_chat_accept_mid_walk_stops_in_place(client, fake_clock):
    a = _agent(client, "whale", "鲸仔"); b = join(client, "b")
    place(a, 3, 9, "up"); place(b, 3, 10, "up")
    action(client, a, "move", {"targetTile": {"x": 3, "y": 5}})
    ticker.tick_once(checkpoint=False); _tick(fake_clock, 1.2)
    assert world_state._players[a]["position"] == {"x": 3, "y": 8} and world_state._players[a]["state"] == "walking"
    rid = client.post("/chat/request", json={"from_entity_id": b, "to_entity_ids": [a], "greeting": "hi"}).json()["request_id"]
    resp = client.post("/chat/respond", json={"entity_id": a, "request_id": rid, "accept": True, "message": "yo"}).json()
    assert resp["status"] in ("walking_over", "room_created")
    _tick(fake_clock, 1.0)                                                                           # 下一 tick：走路队列发现状态变了 → 就地停
    assert a not in world_state._walks and world_state._players[a]["position"] == {"x": 3, "y": 8}
    done = [x for x in read_log(entity=a) if x["type"] == "move_done"][-1]
    assert done["payload"]["outcome"] == "stopped" and done["payload"]["reason"].startswith("state:") and done["payload"]["steps_done"] == 1


def test_move_n_and_go_to_queue(client, fake_clock):
    pid = _agent(client, "whale"); place(pid, 4, 3, "down")
    r = action(client, pid, "move_n", {"direction": "down", "steps": 3})
    assert r["success"] and r["result"]["state"] == "walking" and r["result"]["steps_planned"] == 3 and r["result"]["target"] == {"x": 4, "y": 6}
    walk_done(pid, fake_clock)
    assert world_state._players[pid]["position"] == {"x": 4, "y": 6}
    r = action(client, pid, "go_to", {"target": "square"})
    assert r["success"] and r["type"] == "go_to" and r["result"]["state"] == "walking" and r["result"]["area_id"] == "square"
    walk_done(pid, fake_clock)
    pos = world_state._players[pid]["position"]
    assert world_state.get_zone_at(pos["x"], pos["y"])["arena"] == "square"
    assert [x["payload"]["action"] for x in read_log(entity=pid) if x["type"] == "move_done"] == ["move_n", "move_to_area"]


def test_teleport_cancels_walk_and_ws_action_carries_walk_fields(client, fake_clock, monkeypatch):
    monkeypatch.setenv("SANDBOX_SCENARIO", "1")
    pid = _agent(client, "whale"); place(pid, 4, 3, "down")
    action(client, pid, "move", {"targetTile": {"x": 4, "y": 9}})
    r = client.post("/admin/scenario", json={"steps": [{"op": "teleport", "player": pid, "x": 10, "y": 10, "facing": "up"}]}).json()
    assert r["ok"] and pid not in world_state._walks and world_state._players[pid]["state"] == "idle"
    assert [x["payload"]["reason"] for x in read_log(entity=pid) if x["type"] == "move_done"] == ["teleport"]
