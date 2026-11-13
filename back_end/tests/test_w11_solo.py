"""X7 A1「只有她」模式（SANDBOX_SOLO=1）：NPC 身体不在，买 / 点餐 / 配钥匙 / QQ / 日薪照常；委托放到门口 / 柜台即交付（deliver）；非 solo 不许。"""
import pytest

from game import world_state, economy, inventory, commissions
from datetime import datetime
from game.time_state import GAME_TZ
from tests.conftest import action, place
from tests.test_w9_map_v2 import v1  # noqa: F401


def _agent(client, aid):
    return client.post("/player/join", json={"name": aid, "controller": "agent", "profile": {"agent_id": aid}}).json()["playerId"]


def test_solo_checklist_and_drop_delivery(client, v1, fake_clock, monkeypatch):
    monkeypatch.setattr(world_state, "SOLO", True)
    fake_clock.t = datetime(2026, 11, 10, 12, 10, tzinfo=GAME_TZ).timestamp()
    whale = _agent(client, "whale"); p = world_state._players[whale]
    assert len(world_state._players) == 1 and client.get("/admin/metrics").json()["solo"] is True
    # 买：钱进店主账户（没开户的店主只记账户，不发日薪）
    place(whale, 55, 36, "up")
    assert action(client, whale, "buy", {"item": "bread", "qty": 2})["success"] and economy.balance("npc_grocer") == 3010
    # 配钥匙照常
    assert action(client, whale, "copy_key", {"door_id": "door_home"})["success"] and economy.balance("npc_grocer") == 3025
    # 餐厅点餐不需要厨师在场
    place(whale, 48, 24, "up"); assert action(client, whale, "use")["success"]
    r = action(client, whale, "eat", {"item": "meal"}); assert r["success"] and economy.balance("npc_rest_owner") == 3020
    action(client, whale, "leave")
    # QQ 发给不在的小千：入信箱、没人回
    assert client.post("/qq/send", json={"entity_id": whale, "to": "npc_xiaoqian", "text": "在吗"}).json()["success"]
    # 委托：当面 give 没有对象 → 放到餐厅门口 / 柜台即交付
    cm = client.post("/admin/commission", json={"client": "餐厅老板", "title": "店歌", "fee": 150}).json()["commission"]
    inventory.add(p, "cd", 1, meta={"title": "夜航", "commission_id": cm["id"]}, expires_at=None)
    place(whale, 12, 26, "up")
    r = action(client, whale, "deliver", {})
    assert r["success"] is False and r["reason"] == "not_at_drop_point" and r["result"]["drop_points"]["npc_rest_owner"] == ["door_restaurant", "bar"]
    place(whale, 51, 31, "up")                                                             # 餐厅门外格（door_restaurant a=(51,31)）
    g0 = p["gold"]
    r = action(client, whale, "deliver", {})
    assert r["success"] and r["result"]["commission"]["status"] == "delivered" and r["result"]["commission"]["via"] == "drop" and r["result"]["gold_delta"] == 150
    assert p["gold"] == g0 + 150 and inventory.count(p, "cd") == 0 and client.get("/commissions").json()["count"] == 0
    assert action(client, whale, "deliver", {})["reason"] == "no_open_commission"
    # 非 solo：deliver 不许，仍当面 give
    monkeypatch.setattr(world_state, "SOLO", False)
    client.post("/admin/commission", json={"client": "餐厅老板", "title": "第二首", "fee": 120})
    inventory.add(p, "cd", 1, meta={"title": "二"}, expires_at=None)
    assert action(client, whale, "deliver", {})["reason"] == "not_solo"
