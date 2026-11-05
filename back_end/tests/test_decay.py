"""B4：handler 工厂、decay 元 buff、一游戏小时数值对账、catch_up 分段上限。"""
from datetime import datetime

import pytest

from game import buff_tick as bt, world_state
from game.buff_tick import run_tick, catch_up_tick, EFFECT_HANDLERS
from game.time_state import GAME_TZ


def _ts(hour: int, minute: int = 0, day: int = 10) -> float:
    return datetime(2026, 11, day, hour, minute, tzinfo=GAME_TZ).timestamp()


def _player(**over) -> dict:
    p = world_state._make_player("w", "w")
    p.update({"fullness": 70.0, "hp": 70.0, "energy": 100.0, "social": 60.0, "fun": 60.0,
              "mood": 75.0, "mood_base": 65.0, "closeness": {"achan": 72.0}})
    p.update(over)
    return p


def _run(p: dict, seconds: float, end_ts: float, step_ms: float = 200.0) -> None:
    n = int(seconds * 1000 / step_ms)
    start = end_ts - seconds
    for i in range(1, n + 1):
        run_tick(p, step_ms, game_ts=start + i * step_ms / 1000.0)


def test_handler_factory_keys():
    for v in bt.NEED_VARS:
        assert f"{v}_regen" in EFFECT_HANDLERS and f"{v}_delta" in EFFECT_HANDLERS
    for k in ("emotion_tag", "closeness_delta", "decay", "hp_regen", "no_move", "move_speed"):
        assert k in EFFECT_HANDLERS


def test_new_player_has_decay_meta_buff():
    p = world_state._make_player("x", "x")
    assert [b for b in p["buffs"] if b["key"] == "decay" and b["source"] == "decay" and b["mode"] == "persistent"]


def test_one_game_hour_daytime_reconciliation():
    """12:00–13:00（无夜间倍率）：fullness −12、energy −8、social −6、fun −10、mood 半衰期 120 min、closeness −1/天。"""
    p = _player()
    _run(p, 3600, _ts(13))
    assert p["fullness"] == pytest.approx(58.0, abs=1e-6)
    assert p["hp"] == p["fullness"]
    assert p["energy"] == pytest.approx(92.0, abs=1e-6)
    assert p["social"] == pytest.approx(54.0, abs=1e-6)
    assert p["fun"] == pytest.approx(50.0, abs=1e-6)
    assert p["mood"] == pytest.approx(65 + 10 * 0.5 ** 0.5, abs=1e-6)
    assert p["closeness"]["achan"] == pytest.approx(72 - 1 / 24, abs=1e-6)
    assert p["last_tick_ts"] == datetime.fromtimestamp(_ts(13), GAME_TZ).isoformat(timespec="seconds")


def test_night_energy_multiplier():
    p = _player()
    _run(p, 3600, _ts(3))                 # 02:00–03:00 全在凌晨
    assert p["energy"] == pytest.approx(88.0, abs=1e-6)
    p = _player()
    _run(p, 3600, _ts(6, 30))             # 05:30–06:30：半小时夜间
    assert p["energy"] == pytest.approx(100 - 8 * 0.5 * 1.5 - 8 * 0.5, abs=1e-6)


def test_night_seconds_helper():
    assert bt.night_seconds(_ts(23), _ts(1, day=11)) == pytest.approx(3600)
    assert bt.night_seconds(_ts(12), _ts(13)) == 0


def test_live_scene_rates():
    p = _player(scene="live", social=60.0, mood=75.0)
    _run(p, 60, _ts(12, 1))
    assert p["social"] == pytest.approx(60 - 0.12 * 60, abs=1e-6)
    assert p["mood"] == pytest.approx(65 + 10 * 0.5 ** (60 / 70), abs=1e-6)
    assert p["fullness"] == pytest.approx(70 - 12 / 60, abs=1e-6)   # 其余速率同 sandbox


def test_mood_relaxes_toward_profile_baseline():
    p = _player(mood=50.0, mood_base=69.5)
    _run(p, 120 * 60, _ts(14), step_ms=1000)
    assert p["mood"] == pytest.approx(69.5 - 19.5 / 2, abs=1e-6)


def test_decay_does_not_notify_sync_hook():
    seen = []
    bt.ON_VAR_CHANGE = lambda pid, var, d: seen.append((var, d))
    try:
        p = _player(energy=50.0)
        _run(p, 10, _ts(12), step_ms=1000)
        assert seen == []
        p["buffs"].append({"key": "energy_regen", "value": 1.0, "mode": "persistent", "remaining": None, "source": "bed"})
        run_tick(p, 1000, game_ts=_ts(12, 1))
        assert [v for v, _ in seen] == ["energy"] and seen[0][1] == pytest.approx(1.0)
    finally:
        from game import self_sync
        bt.ON_VAR_CHANGE = self_sync.track


def test_one_shot_delta_and_closeness_and_emotion_tag_buffs():
    p = _player()
    p["buffs"] += [
        {"key": "social_delta", "value": 12.0, "mode": "persistent", "remaining": None, "source": "t"},
        {"key": "closeness_delta", "value": 5.0, "mode": "persistent", "remaining": None, "source": "t", "target": "achan"},
        {"key": "emotion_tag", "value": 0.0, "mode": "timed", "remaining": 40_000.0, "source": "t", "tag": "smug"},
    ]
    run_tick(p, 200, game_ts=_ts(12))
    assert p["social"] == pytest.approx(72.0, abs=1e-3)
    assert p["closeness"]["achan"] == pytest.approx(77.0, abs=1e-3)
    assert [t["key"] for t in p["emotion_tags"]] == ["smug"]
    run_tick(p, 200, game_ts=_ts(12))           # 一次性项已消费并移除，不重复加
    assert p["social"] == pytest.approx(72.0, abs=1e-2)
    assert {b["key"] for b in p["buffs"]} == {"decay"}
    run_tick(p, 40_000, game_ts=_ts(12, 1))
    assert p["emotion_tags"] == []


def test_catch_up_caps_fullness_energy_at_4h_others_8h():
    p = _player(fullness=70.0, energy=100.0, social=60.0, fun=90.0, mood=65.0)
    end = _ts(20)                               # 12:00–20:00，无夜间
    r = catch_up_tick(p, 8 * 3600 * 1000, end)
    assert r == {"full_ms": 4 * 3600 * 1000, "partial_ms": 4 * 3600 * 1000}
    assert p["fullness"] == pytest.approx(70 - 12 * 4, abs=1e-4)    # 只扣 4 h
    assert p["energy"] == pytest.approx(100 - 8 * 4, abs=1e-4)
    assert p["social"] == pytest.approx(60 - 6 * 8, abs=1e-4)       # 扣满 8 h
    assert p["fun"] == pytest.approx(90 - 10 * 8, abs=1e-4)
    assert p["closeness"]["achan"] == pytest.approx(72 - 8 / 24, abs=1e-4)


def test_catch_up_total_capped_at_8h_and_short_downtime_full():
    p = _player(fullness=70.0, social=60.0)
    catch_up_tick(p, 30 * 3600 * 1000, _ts(20))
    assert p["social"] == pytest.approx(12.0, abs=1e-4)
    p = _player(fullness=70.0)
    catch_up_tick(p, 3600 * 1000, _ts(13))
    assert p["fullness"] == pytest.approx(58.0, abs=1e-4)


def test_catch_up_second_phase_keeps_object_buffs_but_does_not_apply_them():
    p = _player(energy=50.0)
    p["buffs"].append({"key": "energy_regen", "value": 0.01, "mode": "persistent", "remaining": None, "source": "bed"})
    catch_up_tick(p, 8 * 3600 * 1000, _ts(20))
    # 前 4 h：regen +0.01×14400=144（clamp 100）−32 衰减…；后 4 h 不碰 energy
    assert 0 < p["energy"] <= 100
    assert any(b["key"] == "energy_regen" for b in p["buffs"])


def test_admin_clear_keeps_decay(client):
    from tests.conftest import join
    pid = join(client)
    client.delete(f"/admin/player/{pid}/buffs")
    assert [b["key"] for b in world_state._players[pid]["buffs"]] == ["decay"]
    client.post("/admin/player/force-reset", json={"entity_id": pid})
    assert [b["key"] for b in world_state._players[pid]["buffs"]] == ["decay"]
