"""v1.4.7：closeness 键统一 agent id（总控 11-17 定；真 bug：自我层按 agent id 播种的亲密度 perceive 看不见）。"""
from game import world_state, persistence
from game.buff_tick import add_closeness, closeness_key, get_closeness, normalize_closeness
from tests.conftest import place
from tests.test_w9_map_v2 import _agent, v12  # noqa: F401


def test_writes_use_agent_id_and_perceive_sees_seeded_value(client, v12):
    w, c = _agent(client, "whale"), _agent(client, "claudine")
    viewer = "viewer_abc"
    pw = world_state._players[w]
    pw["closeness"] = {"claudine": 75.0}                         # 自我层按 agent id 播种的形状
    place(w, 3, 19, "up"); place(c, 4, 19, "left")
    tiers = client.get("/agent/perceive", params={"entity_id": w}).json()["needs"]["closeness"]
    assert get_closeness(pw, c) == 75.0
    from game.needs import closeness_tier
    assert tiers[c]["tier"] == closeness_tier(75.0)               # 以前读 player id 键 → 0 档
    add_closeness(pw, c, 5.0)                                     # 传 player id 也记到 agent id 键
    add_closeness(pw, viewer, 2.0)                                # 观众账号照旧
    assert pw["closeness"] == {"claudine": 80.0, viewer: 2.0} and closeness_key(c) == "claudine"


def test_normalize_merges_old_player_id_keys(client, v12):
    w, c = _agent(client, "whale"), _agent(client, "claudine")
    merged = normalize_closeness({"claudine": 74.5, c: 16.6, "viewer_x": 3.0})
    assert set(merged) == {"claudine", "viewer_x"} and abs(merged["claudine"] - 91.1) < 1e-9 and merged["viewer_x"] == 3.0
    assert normalize_closeness({"claudine": 90.0, c: 30.0})["claudine"] == 100.0   # 上限截断


def test_checkpoint_roundtrip_normalizes(client, v12, tmp_path, monkeypatch):
    w, c = _agent(client, "whale"), _agent(client, "claudine")
    world_state._players[w]["closeness"] = {"claudine": 10.0, c: 5.0}
    db = tmp_path / "cp.sqlite"
    persistence.save_checkpoint(db)
    world_state._players[w]["closeness"] = {}
    persistence.load_checkpoint(db)
    assert world_state._players[w]["closeness"] == {"claudine": 15.0}


def test_admin_restore_player_keeps_id(client, v12, monkeypatch):
    """v1.4.7 全镇重置：按原 id 重建；agent 用原 id rejoin 续接；重复 → 409；有 token 时要鉴权。"""
    monkeypatch.setenv("SANDBOX_ADMIN_TOKEN", "t0k")
    body = {"player_id": "鲸仔_52f531", "name": "鲸仔", "controller": "agent", "profile": {"agent_id": "whale"}}
    assert client.post("/admin/player/restore", json=body).status_code == 401
    H = {"Authorization": "Bearer t0k"}
    r = client.post("/admin/player/restore", json=body, headers=H)
    assert r.status_code == 200, r.text
    p = r.json()["player"]
    assert p["id"] == "鲸仔_52f531" and p["agent_id"] == "whale" and p["online"] is False
    assert client.post("/admin/player/restore", json=body, headers=H).status_code == 409
    assert client.post("/player/rejoin", json={"playerId": "鲸仔_52f531"}).json()["player"]["online"] is True
    h = client.post("/admin/player/restore", headers=H, json={"player_id": "阿蝉_97b6d8", "name": "阿蝉", "controller": "human",
                                                              "profile": {"agent_id": "achan"}, "dnd": True}).json()["player"]
    assert h["dnd"] is True and h["dnd_auto"] is True and h["agent_id"] == "achan"
    r = client.post("/player/阿蝉_97b6d8/effects", json={"effects": [{"type": "closeness_delta", "target": "whale", "value": 85.0}], "source": "reset"})
    assert r.status_code == 200 and world_state._players["阿蝉_97b6d8"]["closeness"] == {"whale": 85.0}
