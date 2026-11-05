"""现有对外接口形状回归（会话 C 按 docs/api-spec.md 对接）。"""
from tests.conftest import join, action


def test_world_shape(client):
    w = client.get("/world").json()
    assert {"tiles", "objects", "worldState", "players"} <= set(w)
    assert {"date", "time", "period", "running", "speed", "weather"} == set(w["worldState"])
    o = w["objects"][0]
    for k in ("id", "type", "prototype", "name", "position", "interactable", "effects", "currentUsers", "userList"):
        assert k in o


def test_player_lifecycle(client):
    pid = join(client, "Whale Kid")
    assert pid.startswith("whale_kid_")
    w = client.get("/world").json()
    assert [p["id"] for p in w["players"]] == [pid]
    assert {"id", "name", "position", "facing", "state"} <= set(w["players"][0])   # W2 加 controller / online
    assert client.delete(f"/player/{pid}/leave").json() == {"ok": True}
    assert client.get(f"/player/{pid}").status_code == 404


def test_join_rejects_empty_name(client):
    assert client.post("/player/join", json={"name": "  "}).status_code == 400


def test_move_and_turn(client):
    pid = join(client)
    start = client.get(f"/player/{pid}").json()["position"]
    res = action(client, pid, "move", {"direction": "right"})
    assert res["success"] and res["type"] == "move"
    assert res["result"]["position"] == {"x": start["x"] + 1, "y": start["y"]}
    res = action(client, pid, "turn", {"direction": "up"})
    assert res == {"success": True, "type": "turn", "result": {"facing": "up"}, "reason": None}


def test_unknown_action_400(client):
    pid = join(client)
    r = client.post("/action", json={"entityId": pid, "action": {"type": "fly", "payload": {}}})
    assert r.status_code == 400


def test_action_on_missing_player(client):
    res = action(client, "ghost", "move", {"direction": "up"})
    assert res["success"] is False and res["reason"] == "player_not_found"


def test_perceive_and_events(client):
    pid = join(client)
    r = client.get("/agent/perceive", params={"entity_id": pid})
    assert r.status_code == 200
    assert client.get("/events").status_code == 200


def test_admin_buffs(client):
    pid = join(client)
    # W2：decay 元 buff 常驻且不可清
    assert [b["key"] for b in client.get(f"/admin/player/{pid}/buffs").json()["buffs"]] == ["decay"]
    assert client.delete(f"/admin/player/{pid}/buffs").json() == {"ok": True, "cleared": 0}
    assert [b["key"] for b in client.get(f"/admin/player/{pid}/buffs").json()["buffs"]] == ["decay"]
    r = client.post("/admin/player/force-reset", json={"entity_id": pid}).json()
    assert r["ok"] is True
