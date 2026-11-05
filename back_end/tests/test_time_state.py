"""B7：真实起点 + 倍率。"""
from datetime import datetime

from game import time_state as ts
from tests.conftest import FakeClock


def _parse(state: dict) -> datetime:
    return datetime.fromisoformat(f"{state['date']}T{state['time']}")


def test_defaults_speed_and_running():
    s = ts.get_time_state()
    assert s["speed"] == 1.0
    assert s["running"] is True   # 默认运行，后台 ticker 才能推进
    assert set(s) == {"date", "time", "period", "running", "speed"}


def test_first_start_uses_real_date(fake_clock):
    real = datetime.fromtimestamp(fake_clock.t, tz=ts.GAME_TZ)
    s = ts.get_time_state()
    assert s["date"] == real.strftime("%Y-%m-%d")
    assert s["time"] == real.strftime("%H:%M:%S")


def test_time_follows_wall_clock_at_speed_1(fake_clock):
    t0 = ts.game_now_ts()
    fake_clock.advance(90)
    assert ts.game_now_ts() - t0 == 90


def test_advance_time_returns_game_delta_and_keeps_signature(fake_clock):
    assert ts.advance_time(200) == 200.0
    ts.set_speed(60)
    assert ts.advance_time(200) == 200.0 * 60
    assert ts.get_last_game_delta() == 12000.0
    ts.set_running(False)
    assert ts.advance_time(200) == 0.0


def test_speed_change_is_continuous(fake_clock):
    t0 = ts.game_now_ts()
    fake_clock.advance(10)                 # +10 游戏秒
    ts.set_speed(60)                       # 重锚
    assert ts.game_now_ts() - t0 == 10
    fake_clock.advance(10)                 # +600 游戏秒
    assert ts.game_now_ts() - t0 == 610
    ts.set_speed(1)
    fake_clock.advance(5)
    assert ts.game_now_ts() - t0 == 615


def test_pause_freezes_and_resume_continues(fake_clock):
    t0 = ts.game_now_ts()
    fake_clock.advance(3)
    ts.set_running(False)
    fake_clock.advance(100)
    assert ts.game_now_ts() - t0 == 3
    ts.set_running(True)
    fake_clock.advance(2)
    assert ts.game_now_ts() - t0 == 5


def test_min_speed_clamped(fake_clock):
    assert ts.set_speed(0.1) == ts.MIN_SPEED


def test_period_boundaries():
    assert ts._calc_period(5.99) == "night"
    assert ts._calc_period(6) == "morning"
    assert ts._calc_period(8) == "day"
    assert ts._calc_period(19.99) == "day"
    assert ts._calc_period(20) == "dusk"
    assert ts._calc_period(22) == "night"


def test_export_import_survives_restart_with_downtime(fake_clock):
    ts.set_speed(2)
    fake_clock.advance(10)
    g_before = ts.game_now_ts()
    snapshot = ts.export_state()

    # 模拟进程重启：状态清空、停机 30 秒后回填
    ts._reset_for_tests()
    fake_clock.advance(30)
    ts.import_state(snapshot)
    assert ts.get_time_state()["speed"] == 2
    # running=True：停机期间游戏时间按倍率自然流逝，连续无跳变
    assert ts.game_now_ts() - g_before == 60


def test_paused_state_does_not_drift_across_restart(fake_clock):
    ts.set_running(False)
    g = ts.game_now_ts()
    snap = ts.export_state()
    ts._reset_for_tests()
    fake_clock.advance(1000)
    ts.import_state(snap)
    assert ts.game_now_ts() == g
    assert ts.get_time_state()["running"] is False


def test_reset_time_returns_to_real_now(fake_clock):
    ts.set_speed(10)
    fake_clock.advance(100)
    ts.reset_time()
    assert ts.game_now_ts() == fake_clock.t
    assert ts.get_time_state()["speed"] == ts.DEFAULT_SPEED


def test_time_router_shapes(client, fake_clock):
    r = client.post("/time/speed", json={"value": 5})
    assert r.json() == {"speed": 5.0}
    r = client.post("/time/toggle")
    assert set(r.json()) == {"date", "time", "period", "running", "speed"}
    assert r.json()["running"] is False
    r = client.post("/time/reset")
    assert r.json()["speed"] == 1.0
    w = client.get("/world").json()["worldState"]
    assert set(w) == {"date", "time", "period", "running", "speed", "weather"}
