"""W8 Q1：join / rejoin / 回填立即采样；回放同秒动作无歧义；行动日志 objectId。"""
import json
import time
from datetime import date, datetime

import pytest

from game import world_state, state_log, persistence, chat_state
from game.time_state import GAME_TZ
from routers import actions as actions_mod
from tests.conftest import BED_ID, BED_STAND, join, action


def test_join_rejoin_restore_write_immediate_samples(client, fake_clock):
    pid = client.post("/player/join", json={"name": "w", "controller": "agent", "profile": {"agent_id": "whale"}}).json()["playerId"]
    rows = state_log.read_log(player=pid)
    assert [r["kind"] for r in rows] == ["join"] and rows[0]["vars"]["energy"] == 100.0 and rows[0]["mood_base"] == 65.0
    client.post("/player/rejoin", json={"playerId": pid})
    assert [r["kind"] for r in state_log.read_log(player=pid)] == ["join", "rejoin"]
    persistence.save_checkpoint()
    world_state._reset_for_tests(); chat_state._reset_for_tests(); state_log._reset_for_tests()
    persistence.load_checkpoint()
    assert [r["kind"] for r in state_log.read_log(player=pid)] == ["join", "rejoin", "restore"]
    # 立即采样把 30 s 节拍对齐：接下来 29 s 内不再采样
    from game import ticker
    ticker.tick_once(checkpoint=False); fake_clock.advance(20); ticker.tick_once(checkpoint=False)
    assert len(state_log.read_log(player=pid)) == 3
    fake_clock.advance(11); ticker.tick_once(checkpoint=False)
    assert len(state_log.read_log(player=pid)) == 4 and state_log.read_log(player=pid)[-1]["kind"] == "sample"


def test_action_log_carries_object_id(client):
    pid = join(client, "w")
    from tests.conftest import place
    place(pid, *BED_STAND)
    action(client, pid, "use"); action(client, pid, "turn", {"direction": "up"}); action(client, pid, "leave")
    hist = client.get("/history").json()
    assert [h["objectId"] for h in hist] == [BED_ID, None, BED_ID]
    assert client.get("/history/log").json()[0]["objectId"] == BED_ID


def test_replay_same_second_join_and_actions_unambiguous(client, fake_clock):
    """rejoin 立即采样后，同一游戏秒内连做瞬移 / 转向 / use，再睡 30 min、离开；从 rejoin 行起回放，末态差 < 0.5、动作结果零不一致。"""
    from game import replay as rp, ticker
    from game.paths import data_dir
    actions_mod.BASE_MOVE_INTERVAL = 0.0
    fake_clock.t = datetime(2026, 11, 10, 9, 0, tzinfo=GAME_TZ).timestamp()
    pid = client.post("/player/join", json={"name": "鲸仔", "controller": "agent", "profile": {"agent_id": "whale"}}).json()["playerId"]
    client.post(f"/player/{pid}/effects", json={"effects": [{"type": "instant_effect", "key": "energy", "value": -60}]})
    client.post("/player/rejoin", json={"playerId": pid})            # 起点行（同秒内紧接着动作）
    assert action(client, pid, "move", {"targetTile": {"x": BED_STAND[0], "y": BED_STAND[1]}})["success"]
    assert action(client, pid, "turn", {"direction": BED_STAND[2]})["success"]
    assert action(client, pid, "use")["success"]
    ticker.tick_once(checkpoint=False)
    for _ in range(60):
        fake_clock.advance(30); ticker.tick_once(checkpoint=False)
    assert action(client, pid, "leave")["success"]
    for _ in range(4):
        fake_clock.advance(30); ticker.tick_once(checkpoint=False)
    rows = state_log.read_log(player=pid)
    assert [r["kind"] for r in rows[:2]] == ["join", "rejoin"] and rows[1]["ts"] < rows[2]["ts"]
    res = rp.replay(date.today().isoformat(), data_dir(), threshold=0.5, start_kind="rejoin")
    row = next(r for r in res["table"] if r["player"] == pid)
    assert res["applied"]["action_result_mismatch"] == 0 and res["applied"]["actions"] == 4
    assert row["max_abs"] < 0.5, row
    # 同秒：rejoin 行与三步动作 game_time 相同，排序靠真实 ts
    acts = [a for a in client.get("/history/log").json() if a["entityId"] == pid]
    assert acts[0]["game_time"] == rows[1]["game_time"] and acts[0]["timestamp"] > rows[1]["ts"]


def test_replay_restore_sync_point(client, fake_clock):
    """重启回填（restore 行）把『正在用的物品』带回来：回放到该行对齐 using，之后走势一致。"""
    from game import replay as rp, ticker
    from game.paths import data_dir
    from tests.conftest import FRIDGE_STAND
    actions_mod.BASE_MOVE_INTERVAL = 0.0
    fake_clock.t = datetime(2026, 11, 10, 9, 0, tzinfo=GAME_TZ).timestamp()
    pid = client.post("/player/join", json={"name": "鲸仔", "controller": "agent", "profile": {"agent_id": "whale"}}).json()["playerId"]
    client.post(f"/player/{pid}/effects", json={"effects": [{"type": "instant_effect", "key": "energy", "value": -50}]})
    assert action(client, pid, "move", {"targetTile": {"x": BED_STAND[0], "y": BED_STAND[1]}})["success"]
    assert action(client, pid, "turn", {"direction": BED_STAND[2]})["success"]
    assert action(client, pid, "use")["success"]
    ticker.tick_once(checkpoint=False)
    for _ in range(20):
        fake_clock.advance(30); ticker.tick_once(checkpoint=False)
    persistence.save_checkpoint()
    # 「重启」：清状态、停机 5 分钟、回填（写 restore 行，仍在床上）
    world_state._reset_for_tests(); chat_state._reset_for_tests(); state_log._reset_for_tests()
    from game import ticker as tk; tk._reset_for_tests()
    fake_clock.advance(300)
    persistence.load_checkpoint()
    assert world_state._players[pid]["usingObjectId"] == BED_ID
    assert state_log.read_log(player=pid)[-1]["kind"] == "restore"
    ticker.tick_once(checkpoint=False)
    for _ in range(40):
        fake_clock.advance(30); ticker.tick_once(checkpoint=False)
    assert action(client, pid, "leave")["success"]
    for _ in range(4):
        fake_clock.advance(30); ticker.tick_once(checkpoint=False)
    res = rp.replay(date.today().isoformat(), data_dir(), threshold=0.5)
    row = next(r for r in res["table"] if r["player"] == pid)
    assert res["applied"].get("sync_rows") == 1 and res["applied"]["action_result_mismatch"] == 0
    assert row["max_abs"] < 0.5, row
