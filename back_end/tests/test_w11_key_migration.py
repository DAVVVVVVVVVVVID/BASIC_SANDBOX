"""§3.41 补：加载旧检查点（玩家没经过 join 领钥匙）后补发自家钥匙，幂等；scenario spawn 的鲸仔也拿到 door_home 钥匙（X1 S02）。"""
from game import world_state, doors, persistence, inventory
from tests.conftest import join
from tests.test_w9_map_v2 import v12  # noqa: F401


def _agent(client, aid, name=None):
    return client.post("/player/join", json={"name": name or aid, "controller": "agent", "profile": {"agent_id": aid}}).json()["playerId"]


def test_checkpoint_without_keys_gets_migrated_once(client, v12):
    whale = _agent(client, "whale"); achan = _agent(client, "achan"); fisher = _agent(client, "npc_fisher"); h = join(client, "主播")
    # 模拟「钥匙前」的检查点：清掉背包里的钥匙与发放记录
    for pid in (whale, achan, fisher, h):
        world_state._players[pid]["inventory"] = []
    doors._reset_for_tests()
    persistence.save_checkpoint()
    world_state._reset_for_tests(); doors._reset_for_tests()
    persistence.load_checkpoint()
    keys = {pid: [k["door_id"] for k in doors.keys_of(world_state._players[pid])] for pid in (whale, achan, fisher, h)}
    assert keys[whale] == ["door_home"] and keys[achan] == ["door_home"] and keys[fisher] == ["door_fisher"]
    assert keys[h] == []                                                                  # 人类不在迁移里，下次 join 领
    assert doors._issued["door_home"] == {"whale": whale, "achan": achan}
    assert client.get("/admin/path", params={"from": "45,19", "to_arena": "whale_room", "mover": whale}).json()["reachable"]
    rows = [a for a in __import__("game.action_log", fromlist=["x"]).read_log(entity=whale) if a["type"] == "key_issued"]
    assert rows[-1]["payload"]["why"] == "migrate"
    # 再启动一次：不重发
    persistence.save_checkpoint(); world_state._reset_for_tests(); doors._reset_for_tests(); persistence.load_checkpoint()
    assert inventory.count(world_state._players[whale], "key") == 1 and doors._issued["door_home"] == {"whale": whale, "achan": achan}
    # 人类重新 join 领剩余那把
    h2 = join(client, "主播2")
    assert [k["door_id"] for k in doors.keys_of(world_state._players[h2])] == ["door_home"]


def test_scenario_spawn_gives_whale_her_key(client, v12, monkeypatch):
    monkeypatch.setenv("SANDBOX_SCENARIO", "1")
    r = client.post("/admin/scenario", json={"steps": [{"op": "spawn", "name": "鲸仔", "controller": "agent", "agent_id": "whale", "x": 45, "y": 19}]}).json()
    pid = r["steps"][0]["detail"]["id"]
    assert [k["door_id"] for k in client.get(f"/player/{pid}").json()["keys"]] == ["door_home"]
    assert client.get("/admin/path", params={"from": "45,19", "to_object": "bed_whale", "mover": pid}).json()["reachable"]   # S02 回家睡觉有路
