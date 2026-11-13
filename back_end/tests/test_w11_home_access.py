"""§3.41：门禁 = 钥匙物品。无钥匙 no_path/locked；有钥匙直接过；spawn / join 发自家钥匙；人类自带合租房钥匙；屋内无钥匙者可出；give 转交钥匙。"""
from datetime import datetime

from game import world_state, doors, inventory
from game.time_state import GAME_TZ
from tests.conftest import action, place, walk_done, join
from tests.test_w9_map_v2 import v12  # noqa: F401


def _agent(client, aid, name=None):
    return client.post("/player/join", json={"name": name or aid, "controller": "agent", "profile": {"agent_id": aid}}).json()["playerId"]


def _at(fake_clock, h, m=0):
    fake_clock.t = datetime(2026, 11, 10, h, m, tzinfo=GAME_TZ).timestamp()


def _arena(pid):
    p = world_state._players[pid]["position"]
    return world_state.get_zone_at(p["x"], p["y"])["arena"]


def test_keys_issued_on_join_and_gate_doors(client, v12, fake_clock):
    _at(fake_clock, 5, 40)
    fisher = _agent(client, "npc_fisher"); xq = _agent(client, "npc_xiaoqian"); achan = _agent(client, "achan"); whale = _agent(client, "whale")
    assert [k["door_id"] for k in client.get(f"/player/{whale}").json()["keys"]] == ["door_home"]
    assert [k["door_id"] for k in client.get(f"/player/{achan}").json()["keys"]] == ["door_home"]
    assert [k["door_id"] for k in client.get(f"/player/{fisher}").json()["keys"]] == ["door_fisher"]
    assert [k["door_id"] for k in client.get(f"/player/{xq}").json()["keys"]] == ["door_xiaoqian"]
    inv = client.get(f"/player/{whale}").json()["inventory"]
    assert inv == [{"type": "key", "name": "钥匙", "class": "key", "count": 1, "meta": {"door_id": "door_home", "name": "合租房大门钥匙"}}]
    # 老渔夫没合租房钥匙：街道 go_to 厨房 → no_path/locked，卡在大门
    place(fisher, 30, 9, "left")
    res = action(client, fisher, "go_to", {"target": "kitchen"})
    assert res["success"] is False and res["reason"] == "no_path" and res["result"]["blocked_reason"] == "locked" and res["result"]["blocked_at"] == {"x": 9, "y": 17}
    # 小千没钥匙也进不去（白名单没了）
    place(xq, 30, 9, "left")
    assert action(client, xq, "go_to", {"target": "living_room"})["reason"] == "no_path"
    # 鲸仔 / 阿蝉有钥匙直接过
    place(whale, 30, 9, "left")
    res = action(client, whale, "go_to", {"target": "kitchen"}); assert res["success"], res
    walk_done(whale, fake_clock); assert _arena(whale) == "kitchen"
    place(achan, 9, 18, "up")
    assert action(client, achan, "move", {"direction": "up"})["success"]
    # 家内房间不再单独锁：老渔夫被放进客厅后能到厨房 / 鲸仔房间
    place(fisher, 9, 13, "down")
    assert action(client, fisher, "go_to", {"target": "whale_room"})["success"]
    # 屋内无钥匙者可出
    assert action(client, fisher, "go_to", {"target": "street"})["success"]
    walk_done(fisher, fake_clock); assert _arena(fisher) == "street"
    assert action(client, fisher, "go_to", {"target": "kitchen"})["reason"] == "no_path"
    # /admin/path 只给身份：主人按「默认有自家钥匙」算
    assert client.get("/admin/path", params={"from": "30,9", "to_arena": "kitchen", "mover": "whale"}).json()["reachable"]
    assert client.get("/admin/path", params={"from": "30,9", "to_arena": "kitchen", "mover": "npc_fisher"}).json()["reachable"] is False
    # 钥匙总数固定：鲸仔再 join 一个同身份不会多发；3 把 = 鲸仔、阿蝉、人类
    whale2 = _agent(client, "whale", "鲸仔2")
    assert client.get(f"/player/{whale2}").json()["keys"] == []
    h = join(client, "主播")
    assert [k["door_id"] for k in client.get(f"/player/{h}").json()["keys"]] == ["door_home"]
    h2 = join(client, "路人")
    assert client.get(f"/player/{h2}").json()["keys"] == []                                        # 第 3 把发完了
    place(h, 9, 18, "up")
    assert action(client, h, "move", {"direction": "up"})["success"]                                 # 人类单格有钥匙直接过
    place(h2, 9, 18, "up")
    assert action(client, h2, "move", {"direction": "up"})["reason"] == "locked"


def test_give_key_and_removed_holder_returns_key(client, v12, fake_clock):
    _at(fake_clock, 10, 0)
    whale = _agent(client, "whale", "鲸仔"); fisher = _agent(client, "npc_fisher", "老渔夫")
    place(whale, 3, 19, "up"); place(fisher, 4, 19, "left")
    r = action(client, whale, "give", {"target": fisher, "item": "key"})                             # 只有一把时不用指 door_id
    assert r["success"] and r["result"]["door_id"] == "door_home" and r["result"]["item"] == "key"
    assert client.get(f"/player/{whale}").json()["keys"] == [] and [k["door_id"] for k in client.get(f"/player/{fisher}").json()["keys"]] == ["door_fisher", "door_home"]
    assert action(client, whale, "give", {"target": fisher, "item": "key", "door_id": "door_home"})["reason"] == "no_item"
    assert action(client, fisher, "give", {"target": whale, "item": "key"})["reason"] == "door_id_required"   # 老渔夫有两把：要指明
    place(fisher, 9, 18, "up")
    assert action(client, fisher, "move", {"direction": "up"})["success"]                            # 拿到钥匙就能进
    place(whale, 9, 18, "up")
    assert action(client, whale, "move", {"direction": "up"})["reason"] == "no_path"                # 鲸仔把钥匙给人了，自己进不去
    # 持钥匙的人被删除 → 钥匙回池 → 鲸仔再 join 能再领
    client.delete(f"/player/{fisher}/leave")
    whale_b = _agent(client, "whale", "鲸仔B")
    assert [k["door_id"] for k in client.get(f"/player/{whale_b}").json()["keys"]] == ["door_home"]
    # 钥匙不能走 QQ（实物）
    assert client.post("/qq/send", json={"entity_id": whale_b, "to": "achan", "kind": "file", "file_ref": {"item": "key"}}).json()["reason"] == "files_not_supported"   # v1.1：QQ 不传任何文件


def test_map_doors_and_access_shape(client, v12):
    m = client.get("/world", params={"fields": "map"}).json()["map"]
    edges = {e["id"]: e for e in m["edges"]}
    assert edges["door_home"]["owner"] == ["whale", "achan"] and edges["door_home"]["keys"] == 3 and "allow" not in edges["door_home"]
    for eid, owner in (("door_fisher", ["npc_fisher"]), ("door_xiaoqian", ["npc_xiaoqian"]), ("door_owners", ["npc_rest_owner", "npc_grocer"]),
                       ("door_restaurant", ["npc_rest_owner"]), ("door_grocery", ["npc_grocer"])):
        assert edges[eid]["owner"] == owner and edges[eid]["keys"] == len(owner), eid
    acc = m["access"]
    assert all("locked" not in a for k, a in acc.items() if k != "achan_room") and acc["achan_room"]["locked"] == [["09:00", "18:30"]]
    d = {x["door_id"]: x for x in m["doors"]}
    assert set(d) == {"door_home", "door_fisher", "door_xiaoqian", "door_owners", "door_restaurant", "door_grocery"}
    assert d["door_home"]["open"] is False and d["door_home"]["keys"] == 3 and d["door_home"]["x"] == 9
