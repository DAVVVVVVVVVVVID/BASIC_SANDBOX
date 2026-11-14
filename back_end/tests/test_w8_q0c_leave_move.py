"""W8 Q0c：leave 后同一秒内 move 必须成功；use 后 no_move 立刻生效；清 buff 后立刻可动。"""
import pytest

from game import world_state
from tests.conftest import BED_ID, BED_STAND, join, action, place

NO_MOVE_OBJECTS = [(o["id"], o["type"]) for o in world_state._OBJECTS if o["prototype"] == "continuous"]
STANDS = {
    "bed_whale": (3, 5, "up"), "stream_desk_whale": (3, 12, "down"), "desk_whale": (10, 4, "up"),
    "game_console_whale": (9, 11, "right"), "bed_achan": (13, 4, "up"), "desk_kitchen": (19, 11, "down"),
    "bed_cook": (33, 9, "up"), "desk_cook": (42, 13, "down"), "bed_grocer": (17, 29, "down"),
    "bed_fisher": (47, 23, "left"), "bed_regular": (32, 33, "left"), "desk_regular": (37, 36, "down"),
    "bath_regular": (42, 35, "up"), "table_rest_1": (46, 33, "up"), "table_rest_2": (50, 33, "up"),
    "bench_square_1": (32, 26, "up"), "bench_square_2": (38, 26, "up"),
    "fishing_spot_1": (52, 17, "right"), "fishing_spot_2": (52, 19, "right"),
}


@pytest.fixture(autouse=True)
def stubs(fake_clock, monkeypatch):
    from datetime import datetime
    from game.time_state import GAME_TZ
    from game import external_effects
    fake_clock.t = datetime(2026, 11, 10, 12, 30, tzinfo=GAME_TZ).timestamp()
    monkeypatch.setattr(external_effects, "live_start", lambda p, iso, *a, **k: {"ok": True})
    monkeypatch.setattr(external_effects, "live_stop", lambda p, iso, *a, **k: None)
    monkeypatch.setattr(external_effects, "game_start", lambda p, iso: {"ok": True, "game": {"status": "playing", "started_at": iso}})
    monkeypatch.setattr(external_effects, "game_end", lambda p, iso, *a, **k: None)


def _free_dir(x, y):
    for d, (dx, dy) in (("left", (-1, 0)), ("right", (1, 0)), ("down", (0, 1)), ("up", (0, -1))):
        if world_state.is_tile_walkable(x + dx, y + dy) and world_state.get_object_at(x + dx, y + dy) is None:
            return d
    return None


@pytest.mark.parametrize("obj_id", sorted(STANDS))
def test_leave_then_move_same_second(client, obj_id):
    """不经过任何 tick：use → leave → move 必须成功；use 后立刻 move 必须 move_disabled（物品带 no_move 时）。"""
    pid = join(client, "w")
    x, y, face = STANDS[obj_id]
    place(pid, x, y, face)
    assert action(client, pid, "use")["success"], obj_id
    p = world_state._players[pid]
    from game.object_types import OBJECT_TYPES
    has_no_move = any(e.get("key") == "no_move" for e in OBJECT_TYPES[world_state.get_object_by_id(obj_id)["type"]]["effects"])
    if has_no_move:
        assert p["canMove"] is False                                  # 立刻生效，不等 tick
        assert action(client, pid, "move", {"direction": _free_dir(x, y)})["reason"] == "move_disabled"
    res = action(client, pid, "leave")
    assert res["success"] and res["result"]["canMove"] is True and res["result"]["canUse"] is True
    assert p["canMove"] is True and p["canUse"] is True and p["moveSpeed"] == 1.0
    d = _free_dir(x, y)
    mv = action(client, pid, "move", {"direction": d})
    assert mv["success"], (obj_id, d, mv)


def test_leave_then_move_to_area_same_second(client):
    pid = join(client, "w")
    place(pid, *BED_STAND)
    assert action(client, pid, "use")["success"]
    assert action(client, pid, "leave")["success"]
    res = action(client, pid, "move_to_area", {"area_type": "arena", "area_id": "kitchen"})
    assert res["success"], res


def test_admin_clear_and_force_reset_restore_flags(client):
    pid = join(client, "w")
    place(pid, *BED_STAND)
    assert action(client, pid, "use")["success"]
    p = world_state._players[pid]
    assert p["canMove"] is False
    client.post("/admin/player/force-reset", json={"entity_id": pid})
    assert p["canMove"] is True and action(client, pid, "move", {"direction": "down"})["success"]
    world_state._last_used.clear()                                # 同一张床 30 min 冷却
    place(pid, *BED_STAND); assert action(client, pid, "use")["success"]
    assert p["canMove"] is False
    client.delete(f"/admin/player/{pid}/buffs")
    assert p["canMove"] is True


def test_effects_push_no_move_applies_immediately(client):
    pid = join(client, "w")
    client.post(f"/player/{pid}/effects", json={"effects": [{"type": "buff", "key": "no_move", "mode": "timed", "duration": 5000}]})
    assert world_state._players[pid]["canMove"] is False
    assert action(client, pid, "move", {"direction": "down"})["reason"] == "move_disabled"
