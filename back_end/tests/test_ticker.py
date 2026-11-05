"""B8：后台 tick 独立于客户端轮询；GET /world 只读。"""
import time

import pytest
from fastapi.testclient import TestClient

from game import ticker, time_state, world_state
from tests.conftest import BED_ID, BED_STAND, place, join, action


def _bed_user(client) -> str:
    pid = join(client)
    place(pid, *BED_STAND)
    res = action(client, pid, "use")
    assert res["success"], res
    assert world_state._players[pid]["usingObjectId"] == BED_ID
    return pid


def test_tick_once_applies_regen_without_any_world_poll(client, fake_clock):
    pid = _bed_user(client)
    p = world_state._players[pid]
    p["energy"] = 50.0
    ticker.tick_once(checkpoint=False)        # 建立基线
    fake_clock.advance(1.0)
    ticker.tick_once(checkpoint=False)
    # bed: energy_regen 1/游戏秒（减去 1 s 自然衰减 8/3600）
    assert p["energy"] == pytest.approx(51.0 - 8 / 3600, abs=1e-6)
    assert p["last_tick_ts"] == time_state.game_now_iso()


def test_tick_scales_with_speed(client, fake_clock):
    pid = _bed_user(client)
    p = world_state._players[pid]
    p["energy"] = 10.0                        # 不贴 0 边界，避免 decay 先 clamp
    ticker.tick_once(checkpoint=False)
    time_state.set_speed(60)
    fake_clock.advance(0.5)                   # 30 游戏秒
    ticker.tick_once(checkpoint=False)
    assert p["energy"] == pytest.approx(40.0 - 30 * 8 / 3600, abs=1e-6)


def test_paused_time_no_tick_effect(client, fake_clock):
    pid = _bed_user(client)
    p = world_state._players[pid]
    p["energy"] = 10.0
    ticker.tick_once(checkpoint=False)
    time_state.set_running(False)
    fake_clock.advance(100)
    ticker.tick_once(checkpoint=False)
    assert p["energy"] == 10.0


def test_get_world_is_read_only(client, fake_clock):
    pid = _bed_user(client)
    p = world_state._players[pid]
    p["energy"] = 10.0
    ticker.tick_once(checkpoint=False)
    fake_clock.advance(5)
    for _ in range(5):
        client.get("/world")
    assert p["energy"] == 10.0                # 轮询不推进
    ticker.tick_once(checkpoint=False)
    assert p["energy"] == pytest.approx(15.0 - 5 * 8 / 3600, abs=1e-6)  # 只有 tick 推进


def test_tick_cleans_stale_players(client, fake_clock):
    pid = join(client)
    world_state._last_seen[pid] = time.time() - world_state._PLAYER_TIMEOUT - 1
    ticker.tick_once(checkpoint=False)
    assert pid not in world_state._players


def test_tick_writes_checkpoint_every_interval(client, fake_clock, tmp_path):
    from game import persistence
    join(client)
    ticker.tick_once()
    assert persistence.db_path().exists()
    mtime = persistence.db_path().stat().st_mtime
    fake_clock.advance(persistence.CHECKPOINT_INTERVAL + 0.1)
    time.sleep(0.01)
    ticker.tick_once()
    assert persistence.db_path().stat().st_mtime >= mtime


def test_background_task_runs_under_lifespan():
    """真实事件循环：进入 lifespan 后不发任何请求，能量仍随真实时间变化。"""
    from main import app
    with TestClient(app) as c:
        assert ticker.is_running()
        pid = join(c)
        place(pid, *BED_STAND)
        assert action(c, pid, "use")["success"]
        p = world_state._players[pid]
        p["energy"] = 50.0
        time.sleep(0.7)                        # ≥ 3 个 tick
        assert p["energy"] > 50.0
        assert p["energy"] < 52.0              # 速率 1/s，不会离谱
    assert not ticker.is_running()
