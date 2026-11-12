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
        # world-v1.1：物品不再各带精力 / 饱腹成本，成本统一由 needs.json 的衰减（醒 −3 / 工作再 −3 / 直播再 −3）承担
        for e in t["effects"]:
            if e["type"] == "buff" and e["key"] in ("energy_regen", "fullness_regen") and e.get("value", 0) < 0:
                raise AssertionError(f"{name} 不该再自带精力 / 饱腹成本")


def test_world_sends_advertise(client):
    objs = client.get("/world").json()["objects"]
    bed = next(o for o in objs if o["id"] == BED_ID)
    assert bed["advertise"] == {"energy": 80}


def test_cooldown_blocks_reuse_then_expires(client, fake_clock):
    """W8 Q0e 起床类无冷却，用桌子验 30 min 冷却。"""
    """v1.1：书桌等工作 / 娱乐类改占用语义无冷却；这里用浴缸（bath，仍 30 分钟）验冷却机制本身。"""
    pid = join(client)
    place(pid, 42, 35, "up")                      # bath_regular
    assert action(client, pid, "use")["success"]
    assert action(client, pid, "leave")["success"]
    res = action(client, pid, "use")
    assert res["success"] is False and res["reason"] == "object_cooldown"
    assert res["result"]["objectId"] == "bath_regular"
    assert 1790 <= res["result"]["cooldownRemaining"] <= 1800
    fake_clock.advance(1801)                      # speed 1：1801 游戏秒后解锁
    assert action(client, pid, "use")["success"]
    assert world_state.get_recent_uses(pid) == {"bath_regular": 2}
    # 书桌（work 类）：立刻可再用
    action(client, pid, "leave"); place(pid, *DESK_STAND)
    assert action(client, pid, "use")["success"] and action(client, pid, "leave")["success"] and action(client, pid, "use")["success"]


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
    """瞬时物品（书架 book：fun +60 / energy −2）：效果 + 30 分钟冷却。冰箱 v1.1 起是储物柜，无效果无冷却。"""
    pid = join(client)
    book = world_state._build_objects([{"id": "book_t", "type": "book", "position": {"x": 3, "y": 4}}])[0]
    world_state._OBJECTS.append(book)
    try:
        place(pid, *BED_STAND)        # (3,5) 朝 up → (3,4) 现在是 book_t（_OBJECTS 顺序：床先匹配）
        world_state._OBJECTS.remove(book); world_state._OBJECTS.insert(0, book)
        p = world_state._players[pid]
        p["fun"] = 30.0; e0 = p["energy"]
        res = action(client, pid, "use")
        assert res["success"] and res["result"]["objectId"] == "book_t"
        assert p["fun"] == pytest.approx(90.0, abs=1e-3) and p["energy"] == pytest.approx(e0 - 2, abs=1e-3)
        assert action(client, pid, "use")["reason"] == "object_cooldown"
        assert "reading" not in p["tags"]
    finally:
        world_state._OBJECTS.remove(book)


def test_cooldown_survives_checkpoint(client, fake_clock):
    from game import persistence, chat_state, time_state, ticker
    pid = join(client)
    place(pid, 42, 35, "up")                      # bath_regular（v1.1 书桌无冷却）
    assert action(client, pid, "use")["success"]
    world_state._daily_use[pid] = {"phone": {"day": world_state.daily_key(world_state.game_now_ts()), "used_s": 600.0}}
    persistence.save_checkpoint()
    world_state._reset_for_tests(); chat_state._reset_for_tests()
    persistence.load_checkpoint()
    assert world_state.object_cooldown_remaining(pid, "bath_regular") > 1700
    assert world_state.get_recent_uses(pid) == {"bath_regular": 1}
    assert world_state.daily_used_s(pid, "phone") == 600.0          # v1.1：每日用量也进检查点
