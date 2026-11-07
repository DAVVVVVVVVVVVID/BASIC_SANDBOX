"""§3.39（02-map §2.3）：合租房门禁——鲸仔房间她的、阿蝉可进；客厅 / 厨房两人；闺蜜小千放行；其他人 locked；出门照 §3.38 放行。"""
from datetime import datetime

from game import world_state
from game.time_state import GAME_TZ
from tests.conftest import action, place, walk_done, join
from tests.test_w9_map_v2 import v1  # noqa: F401


def _agent(client, aid, name=None):
    return client.post("/player/join", json={"name": name or aid, "controller": "agent", "profile": {"agent_id": aid}}).json()["playerId"]


def _at(fake_clock, h, m=0):
    fake_clock.t = datetime(2026, 11, 10, h, m, tzinfo=GAME_TZ).timestamp()


def _arena(pid):
    p = world_state._players[pid]["position"]
    return world_state.get_zone_at(p["x"], p["y"])["arena"]


def test_fisher_cannot_enter_home_but_residents_and_xiaoqian_can(client, v1, fake_clock):
    _at(fake_clock, 5, 40)
    fisher = _agent(client, "npc_fisher"); xq = _agent(client, "npc_xiaoqian"); achan = _agent(client, "achan"); whale = _agent(client, "whale")
    # 老渔夫从街道 go_to 厨房 → no_path / locked（卡在合租房大门外）
    place(fisher, 45, 19, "left")
    res = action(client, fisher, "go_to", {"target": "kitchen"})
    assert res["success"] is False and res["reason"] == "no_path" and res["result"]["blocked_reason"] == "locked", res
    assert res["result"]["blocked_at"] == {"x": 12, "y": 33}
    assert client.get("/admin/path", params={"from": "45,19", "to_arena": "whale_room", "mover": "npc_fisher"}).json()["reachable"] is False
    # 小千能进客厅、厨房、鲸仔房间
    place(xq, 45, 19, "left")
    res = action(client, xq, "go_to", {"target": "living_room"}); assert res["success"], res
    walk_done(xq, fake_clock); assert _arena(xq) == "living_room"
    assert action(client, xq, "go_to", {"target": "whale_room"})["success"]
    # 阿蝉能进鲸仔房间；鲸仔能进阿蝉房（19:00 后）
    place(achan, 12, 26, "down")
    res = action(client, achan, "go_to", {"target": "whale_room"}); assert res["success"], res
    walk_done(achan, fake_clock); assert _arena(achan) == "whale_room"
    # 老渔夫若已在厨房（旧世界遗留），能走出去（出门永远放行）
    place(fisher, 4, 29, "down")
    res = action(client, fisher, "go_to", {"target": "street"}); assert res["success"], res
    walk_done(fisher, fake_clock); assert _arena(fisher) == "street"
    # 回不来
    assert action(client, fisher, "go_to", {"target": "kitchen"})["reason"] == "no_path"
    # 鲸仔自己随时进出
    place(whale, 45, 19, "left")
    assert action(client, whale, "go_to", {"target": "kitchen"})["success"]
    # 人类玩家（操控页）不在名单：也进不去——出生在鲸仔房间，出来后回不去
    h = join(client, "h")
    assert _arena(h) == "whale_room"
    place(h, 12, 34, "up")
    assert action(client, h, "move", {"direction": "up"})["reason"] == "locked"                  # 人类单格直接给 locked


def test_all_house_doors_have_owner_and_access_rules_listed(client, v1):
    m = client.get("/world", params={"fields": "map"}).json()["map"]
    edges = {e["id"]: e for e in m["edges"]}
    assert edges["door_home"]["owner"] == ["whale", "achan"] and edges["door_home"]["allow"] == ["owner", "npc_xiaoqian"]
    for eid, owner in (("door_fisher", ["npc_fisher"]), ("door_xiaoqian", ["npc_xiaoqian"]), ("door_owners", ["npc_rest_owner", "npc_grocer"]),
                       ("door_restaurant", ["npc_rest_owner"]), ("door_grocery", ["npc_grocer"])):
        assert edges[eid]["owner"] == owner, eid                                                   # §3.39 ④：各家大门都有 owner
    acc = m["access"]
    assert acc["whale_room"] == {"owner": ["whale"], "locked": "always", "allow_when_locked": ["achan", "npc_xiaoqian"]}
    assert acc["living_room"]["owner"] == ["whale", "achan"] and acc["kitchen"]["allow_when_locked"] == ["npc_xiaoqian"]
    assert len(acc) == 11
