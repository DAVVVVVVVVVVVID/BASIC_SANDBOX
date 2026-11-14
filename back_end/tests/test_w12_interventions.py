"""闭测周 §5.2：interventions.jsonl（A 格式 v1）沙盒侧自动记录。"""
import json, time

from game import world_state, interventions
from tests.conftest import action, place
from tests.test_w9_map_v2 import _agent, v12  # noqa: F401
from tests.test_w11_knock import _at, _tick


def _rows(d):
    out = []
    for f in sorted(d.glob("*.jsonl")):
        out += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    return out


def test_achan_rows_login_logout_qq_knock_chat_and_fixture(client, v12, fake_clock, tmp_path, monkeypatch):
    monkeypatch.setenv("SANDBOX_INTERVENTIONS_DIR", str(tmp_path)); monkeypatch.setenv("SANDBOX_TOWN", "bench"); monkeypatch.setenv("SANDBOX_SCENARIO", "1")
    interventions._reset_for_tests()
    _at(fake_clock, 15, 0)
    a = client.post("/player/join", json={"name": "阿蝉", "controller": "human", "profile": {"agent_id": "achan"}}).json()["playerId"]
    whale = _agent(client, "whale"); fisher = _agent(client, "npc_fisher")
    client.post("/action", json={"entityId": a, "action": {"type": "turn", "payload": {"direction": "left"}}})            # 首个动作 → 接管
    client.post("/qq/send", json={"entity_id": a, "to": "whale", "text": "今晚几点开播？"})
    place(fisher, 9, 18, "up"); place(a, 9, 13, "down")
    r = action(client, fisher, "knock", {"door_id": "door_home"}); assert r["success"]
    client.post("/door/respond", json={"request_id": r["result"]["request_id"], "entity_id": a, "text": "来了来了"})
    client.post("/admin/player/{}/dnd".format(a), json={"on": True})
    client.post("/admin/scenario", json={"label": "T1", "steps": [{"op": "set_time", "time": "16:00"}]})
    world_state._last_seen[a] = time.time() - 100; world_state._cleanup_stale_players()                                      # 已 dnd：不再重复记 logout
    rows = _rows(tmp_path)
    kinds = [r["kind"] for r in rows]
    assert kinds.count("achan_login") == 2 and [r["payload"]["via"] for r in rows if r["kind"] == "achan_login"] == ["join", "first_action"]
    qq = next(r for r in rows if r["kind"] == "achan_qq"); assert qq["payload"] == {"channel": "qq", "peer": "whale", "chars": 7, "group": False} and "今晚" not in json.dumps(qq, ensure_ascii=False)
    kn = next(r for r in rows if r["kind"] == "achan_knock"); assert kn["payload"]["action"] == "door_respond" and kn["payload"]["chars"] == 4 and kn["targets"] == ["npc_fisher"]
    assert [r["payload"]["reason"] for r in rows if r["kind"] == "achan_logout"] == ["admin_dnd_on"]
    st = next(r for r in rows if r["kind"] == "set_time"); assert st["payload"]["to"].endswith("16:00:00+08:00") and st["reversible"] is True
    fx = next(r for r in rows if r["kind"] == "fixture"); assert fx["ref"] == {"scenario": "T1"} and fx["payload"]["ops"] == ["set_time"]
    for r in rows:
        assert set(r) >= {"id", "ts", "town", "kind", "actor", "targets", "summary", "schema_version"} and r["town"] == "bench" and r["id"].startswith("iv-") and len(r["summary"]) <= 120
    assert all(r["actor"] == "streamer" for r in rows if r["kind"].startswith("achan_")) and all(r["actor"] == "system" for r in rows if r["kind"] in ("set_time", "fixture"))


def test_dir_resolves_to_run_data_town(tmp_path, monkeypatch):
    base = tmp_path / "run" / "data" / "sandbox"; base.mkdir(parents=True)
    monkeypatch.delenv("SANDBOX_INTERVENTIONS_DIR", raising=False); monkeypatch.setenv("SANDBOX_DATA_DIR", str(base)); monkeypatch.setenv("SANDBOX_TOWN", "main")
    assert interventions._dir() == tmp_path / "run" / "data" / "main" / "interventions"
    monkeypatch.setenv("SANDBOX_DATA_DIR", str(tmp_path / "run" / "data" / "bench" / "sandbox")); monkeypatch.setenv("SANDBOX_TOWN", "bench")
    assert interventions._dir() == tmp_path / "run" / "data" / "bench" / "interventions"
