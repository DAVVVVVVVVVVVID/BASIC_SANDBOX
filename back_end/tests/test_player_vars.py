"""B3：七变量、hp 别名、通用 clamp。"""
import pytest

from game import world_state, buff_tick
from game.buff_tick import run_tick
from tests.conftest import BED_STAND, join, action, place

SEVEN = ("fullness", "energy", "social", "fun", "mood", "emotion_tags", "closeness")


def test_get_player_returns_seven_vars_and_alias(client):
    pid = join(client)
    p = client.get(f"/player/{pid}").json()
    for k in SEVEN + ("controller", "last_tick_ts", "hp"):
        assert k in p, k
    assert p["fullness"] == 70.0 and p["hp"] == p["fullness"]
    assert p["energy"] == 100.0
    assert p["social"] == 60.0 and p["fun"] == 60.0
    assert p["mood"] == 65.0
    assert p["emotion_tags"] == [] and p["closeness"] == {}
    assert p["controller"] == "human"
    assert isinstance(p["last_tick_ts"], str) and "T" in p["last_tick_ts"]   # ISO 8601（§3.7 裁定 3）
    # 旧字段仍在
    for k in ("id", "position", "facing", "state", "stateLabel", "usingObjectId", "buffs", "tags",
              "canMove", "canInteract", "canUse", "moveSpeed", "pendingMessage"):
        assert k in p


def test_join_response_has_seven_vars(client):
    r = client.post("/player/join", json={"name": "w"}).json()
    assert {"playerId", "player"} <= set(r)
    assert all(k in r["player"] for k in SEVEN)


def test_pydantic_player_model_accepts_dict(client):
    from models.player import Player
    pid = join(client)
    Player(**client.get(f"/player/{pid}").json())


def test_mood_baseline_formula():
    assert world_state.mood_baseline() == 65.0
    assert world_state.mood_baseline(E=80, N=55) == pytest.approx(65 + 0.2 * 30 - 0.3 * 5)
    p = world_state._make_player("x", "x", profile={"E": 80, "N": 55})
    assert p["mood"] == pytest.approx(69.5)
    assert world_state._make_player("y", "y", controller="agent")["controller"] == "agent"


def test_generic_clamp_and_alias():
    p = world_state._make_player("x", "x")
    world_state.apply_var_delta(p, "hp", 50)        # hp → fullness
    assert p["fullness"] == 100.0 and p["hp"] == 100.0
    world_state.apply_var_delta(p, "fullness", -130)
    assert p["fullness"] == 0.0 and p["hp"] == 0.0
    world_state.apply_var_delta(p, "social", 15)
    world_state.apply_var_delta(p, "fun", -70)
    world_state.apply_var_delta(p, "mood", 100)
    assert (p["social"], p["fun"], p["mood"]) == (75.0, 0.0, 100.0)
    world_state.apply_var_delta(p, "unknown_key", 5)   # 忽略
    assert "unknown_key" not in p


def test_instant_object_uses_generic_clamp(client):
    """注入一个 fridge（fullness +40 / energy +5 / fun −2）验证 instant_effect 走通用路径。"""
    pid = join(client)
    fridge = world_state._build_objects([{"id": "fridge_test", "type": "fridge", "position": {"x": 0, "y": 0}}])[0]
    world_state._OBJECTS.append(fridge)
    try:
        p = world_state._players[pid]
        p["energy"] = 97.0; p["fun"] = 50.0
        world_state.apply_instant_object("fridge_test", pid)
        assert p["fullness"] == 100.0 and p["hp"] == 100.0   # 70+40 clamp
        assert p["energy"] == 100.0                           # 97+5 clamp
        assert p["fun"] == 48.0
    finally:
        world_state._OBJECTS.remove(fridge)


def test_hp_regen_handler_keeps_alias_in_sync():
    p = world_state._make_player("x", "x")
    p["buffs"].append({"key": "hp_regen", "value": -2.0, "mode": "persistent", "remaining": None, "source": "t"})
    p["buffs"] = [b for b in p["buffs"] if b["key"] != "decay"]   # 只看 hp_regen
    run_tick(p, 1000.0, game_ts=1_800_000_000.0)
    assert p["fullness"] == 68.0 and p["hp"] == 68.0
    assert p["last_tick_ts"].startswith("2027-01-15T")


def test_emotion_tags_expire_like_timed_buffs():
    p = world_state._make_player("x", "x")
    p["emotion_tags"].append({"key": "smug", "value": 0.0, "mode": "timed", "remaining": 500.0, "source": "praise"})
    run_tick(p, 200.0)
    assert p["emotion_tags"][0]["remaining"] == 300.0
    run_tick(p, 400.0)
    assert p["emotion_tags"] == []


def test_use_bed_still_works_end_to_end(client):
    pid = join(client)
    place(pid, *BED_STAND)
    res = action(client, pid, "use")
    assert res["success"] and res["result"]["playerState"] == "using"
    p = client.get(f"/player/{pid}").json()
    assert p["state"] == "using" and "sleeping" in p["tags"]
    res = action(client, pid, "leave")
    assert res["success"]
