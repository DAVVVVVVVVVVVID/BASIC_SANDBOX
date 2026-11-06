"""B5：advertise、成本项、hp→fullness、30 游戏分钟冷却、6 h 使用计数。"""
import pytest

from game import world_state
from game.object_types import OBJECT_TYPES
from tests.conftest import BED_ID, BED_STAND, BED_STAND2, DESK_ID, DESK_STAND, join, action, place


def test_object_types_have_advertise_and_cost_and_no_hp():
    for name, t in OBJECT_TYPES.items():
        if not t.get("interactable", True) or t.get("placeholder"):      # W9：装饰物与 v1.0 草图占位类型，数值待定稿
            continue
        assert isinstance(t.get("advertise"), dict), name
        keys = [e["key"] for e in t["effects"]]
        assert "hp" not in keys and "hp_regen" not in keys, name
        negative = [e for e in t["effects"]
                    if e["type"] in ("instant_effect", "buff") and isinstance(e.get("value"), (int, float))
                    and e["value"] < 0 and e["key"].split("_")[0] in ("fullness", "energy", "social", "fun", "mood")]
        assert negative, f"{name} 必须至少有一项成本"


def test_world_sends_advertise(client):
    objs = client.get("/world").json()["objects"]
    bed = next(o for o in objs if o["id"] == BED_ID)
    assert bed["advertise"] == {"energy": 80, "fun": 0}


def test_cooldown_blocks_reuse_then_expires(client, fake_clock):
    """W8 Q0e 起床类无冷却，用桌子验 30 min 冷却。"""
    pid = join(client)
    place(pid, *DESK_STAND)
    assert action(client, pid, "use")["success"]
    assert action(client, pid, "leave")["success"]
    res = action(client, pid, "use")
    assert res["success"] is False and res["reason"] == "object_cooldown"
    assert res["result"]["objectId"] == DESK_ID
    assert 1790 <= res["result"]["cooldownRemaining"] <= 1800
    fake_clock.advance(1801)                      # speed 1：1801 游戏秒后解锁
    assert action(client, pid, "use")["success"]
    assert world_state.get_recent_uses(pid) == {DESK_ID: 2}


def test_cooldown_is_per_object_and_per_player(client, fake_clock):
    a = join(client, "a"); b = join(client, "b")
    place(a, *BED_STAND); place(b, *BED_STAND2)      # 同一张床的另一侧
    assert action(client, a, "use")["success"]
    assert action(client, a, "leave")["success"]
    assert action(client, b, "use")["success"]       # b 不受 a 的冷却影响
    assert world_state.object_cooldown_remaining(a, "other_obj") == 0.0


def test_recent_uses_window_6h(client, fake_clock):
    pid = join(client)
    world_state.record_object_use(pid, "x")
    fake_clock.advance(5 * 3600)
    world_state.record_object_use(pid, "y")
    assert world_state.get_recent_uses(pid) == {"x": 1, "y": 1}
    fake_clock.advance(1.5 * 3600)
    assert world_state.get_recent_uses(pid) == {"y": 1}


def test_instant_object_applies_cost_and_cooldown(client, fake_clock):
    pid = join(client)
    fridge = world_state._build_objects([{"id": "fridge_t", "type": "fridge", "position": {"x": 3, "y": 4}}])[0]
    world_state._OBJECTS.append(fridge)
    try:
        place(pid, *BED_STAND)        # (3,5) 朝 up → (3,4) 现在是 fridge_t（_OBJECTS 顺序：床先匹配）
        world_state._OBJECTS.remove(fridge); world_state._OBJECTS.insert(0, fridge)
        p = world_state._players[pid]
        p["fun"] = 50.0
        res = action(client, pid, "use")
        assert res["success"] and res["result"]["objectId"] == "fridge_t"
        assert p["fullness"] == 100.0 and p["fun"] == pytest.approx(48.0, abs=1e-3)
        assert action(client, pid, "use")["reason"] == "object_cooldown"
        assert "reading" not in p["tags"]
    finally:
        world_state._OBJECTS.remove(fridge)


def test_cooldown_survives_checkpoint(client, fake_clock):
    from game import persistence, chat_state, time_state, ticker
    pid = join(client)
    place(pid, *DESK_STAND)
    assert action(client, pid, "use")["success"]
    persistence.save_checkpoint()
    world_state._reset_for_tests(); chat_state._reset_for_tests()
    persistence.load_checkpoint()
    assert world_state.object_cooldown_remaining(pid, DESK_ID) > 1700
    assert world_state.get_recent_uses(pid) == {DESK_ID: 1}
