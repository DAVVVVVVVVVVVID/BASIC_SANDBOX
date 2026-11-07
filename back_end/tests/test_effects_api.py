"""B13：GET /player/{id}/state、POST /player/{id}/effects、perceive 的 needs / closeness / recent_uses。"""
import pytest

from game import world_state
from game.needs import LABELS, TAG_LABELS, MOOD_LOW_LABEL
from tests.conftest import BED_ID, BED_STAND, BED_STAND2, join, action, place


def test_state_endpoint_shape(client):
    pid = join(client)
    s = client.get(f"/player/{pid}/state").json()
    assert set(s["vars"]) == {"fullness", "energy", "social", "fun", "mood"}
    for k in ("id", "mood_base", "emotion_tags", "closeness", "scene", "controller", "online",
              "agent_id", "last_tick_ts", "recent_uses"):
        assert k in s
    assert isinstance(s["last_tick_ts"], str)
    assert client.get("/player/ghost/state").status_code == 404


def test_effects_endpoint_applies_all_kinds_and_scene(client):
    pid = join(client)
    p = world_state._players[pid]
    p["social"] = 50.0; p["mood"] = 60.0
    body = {"scene": "live", "source": "live:viewer_arrived", "effects": [
        {"type": "instant_effect", "key": "social", "value": 12},
        {"type": "instant_effect", "key": "mood", "value": 4},
        {"type": "buff", "key": "emotion_tag", "tag": "smug", "mode": "timed", "duration": 40000},
        {"type": "closeness_delta", "target": "viewer_12345", "value": 3},
        {"type": "buff", "key": "fun_regen", "value": 0.5, "mode": "timed", "duration": 5000},
        {"type": "tag", "key": "streaming"},
        {"type": "instant_effect", "key": "not_a_var", "value": 1},
    ]}
    r = client.post(f"/player/{pid}/effects", json=body)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] and d["applied"] == 6 and d["skipped"] == 1
    st = d["state"]
    assert st["vars"]["social"] == 62.0 and st["vars"]["mood"] == 64.0
    assert st["scene"] == "live" and p["scene"] == "live"
    assert [t["key"] for t in st["emotion_tags"]] == ["smug"] and st["emotion_tags"][0]["remaining"] == 40000
    assert st["closeness"] == {"viewer_12345": 3.0}
    assert any(b["key"] == "fun_regen" and b["source"] == "live:viewer_arrived" for b in p["buffs"])
    assert "streaming" in p["tags"]


def test_effects_validation(client):
    pid = join(client)
    assert client.post(f"/player/{pid}/effects", json={"effects": [], "scene": "moon"}).status_code == 400
    assert client.post("/player/ghost/effects", json={"effects": []}).status_code == 404
    # 不带 scene 不切换
    client.post(f"/player/{pid}/effects", json={"effects": [{"type": "instant_effect", "key": "fun", "value": -1}]})
    assert world_state._players[pid]["scene"] == "sandbox"


def test_effects_clamp_and_hp_alias(client):
    pid = join(client)
    client.post(f"/player/{pid}/effects", json={"effects": [{"type": "instant_effect", "key": "hp", "value": 999}]})
    p = client.get(f"/player/{pid}").json()
    assert p["fullness"] == 100.0 and p["hp"] == 100.0


def test_perceive_needs_text_not_numbers(client):
    pid = join(client)
    p = world_state._players[pid]
    p.update({"fullness": 20.0, "energy": 12.0, "social": 5.0, "fun": 60.0, "mood": 30.0})
    p["emotion_tags"].append({"key": "smug", "value": 0.0, "mode": "timed", "remaining": 1000.0, "source": "t"})
    needs = client.get("/agent/perceive", params={"entity_id": pid}).json()["needs"]
    assert needs["fullness"] == LABELS["fullness"]["low"]
    assert needs["energy"] == LABELS["energy"]["critical"]
    assert needs["social"] == LABELS["social"]["emergency"]
    assert needs["fun"] == "还好"
    assert needs["mood"] == MOOD_LOW_LABEL
    assert needs["emotion_tags"] == [TAG_LABELS["smug"]]
    assert set(needs["hard"]) == {"energy<15", "social<15"}
    assert len(needs["lines"]) == 5
    for v in needs.values():                    # 不给数值
        assert not isinstance(v, (int, float))
    assert "recent_uses" in needs and "closeness" in needs


def test_perceive_closeness_tiers_and_recent_uses(client):
    me = join(client, "me"); other = join(client, "other"); far = join(client, "far")
    place(me, *BED_STAND); place(other, *BED_STAND2); place(far, 40, 30, "up")   # W10：use 后 me 躺到 (3,3)，other 站床另一侧
    world_state._players[me]["closeness"] = {other: 72.0}
    assert action(client, me, "use")["success"]
    r = client.get("/agent/perceive", params={"entity_id": me, "vision_size": 3}).json()
    assert r["needs"]["closeness"] == {other: {"name": "other", "tier": "很亲近"}}
    assert [p["id"] for p in r["players_in_view"]] == [other]
    assert r["needs"]["recent_uses"] == {BED_ID: 1}
    # 原有三块不变
    for k in ("arena_tree", "vision_tiles", "front_object"):
        assert k in r


def test_closeness_tier_boundaries():
    from game.needs import closeness_tier
    assert [closeness_tier(x) for x in (0, 14.9, 15, 39.9, 40, 69.9, 70, 100)] == \
        ["陌生", "陌生", "认识", "认识", "熟悉", "熟悉", "很亲近", "很亲近"]
