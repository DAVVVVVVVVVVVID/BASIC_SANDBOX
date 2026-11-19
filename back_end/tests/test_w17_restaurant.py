"""商店第二期 · 餐厅现点现做（world-v1.4.13；whale shops-system.md 主播 11-19 第 3 条）。"""
from datetime import datetime

import pytest

from game import shops, inventory, world_state, ticker, fishing, food
from game.time_state import GAME_TZ
from tests.conftest import action, place
from tests.test_w9_map_v2 import _agent, v12  # noqa: F401


def _at(fake_clock, h, m=0):
    fake_clock.t = datetime(2026, 11, 20, h, m, tzinfo=GAME_TZ).timestamp()


def _tick(fake_clock, s=1.0):
    fake_clock.advance(s); ticker.tick_once(checkpoint=False)


def _sit(client, pid):
    place(pid, 34, 12, "up")
    r = action(client, pid, "use")
    assert r["success"] and r["result"]["objectId"] == "table_rest_1", r
    return r


def _stock_fridge(item, n):
    food.store(world_state.get_object_by_id("fridge_rest"), item, n, None)


def test_order_flow_and_failures(client, v12, fake_clock):
    _at(fake_clock, 12)
    whale, owner = _agent(client, "whale"), _agent(client, "npc_rest_owner")
    pw, po = world_state._players[whale], world_state._players[owner]
    world_state.get_object_by_id("fridge_rest")["contents"] = []; food.refresh_stock(world_state.get_object_by_id("fridge_rest"))
    assert action(client, whale, "order", {"dish": "home_rice"})["reason"] == "not_at_table"
    _sit(client, whale)
    place(owner, 30, 20, "up")                                                     # 老板不在后厨
    r = action(client, whale, "order", {"dish": "home_rice"})
    assert r["reason"] == "owner_not_in_kitchen" and "后厨" in r["result"]["message"]
    place(owner, 40, 13, "up")
    r = action(client, whale, "order", {"dish": "home_rice"})
    assert r["reason"] == "no_ingredients" and r["result"]["missing"][0]["item"] == "ingredients"
    assert action(client, whale, "order", {"dish": "pizza"})["reason"] == "unknown_dish"
    _stock_fridge("ingredients", 2); inventory.add(po, "bread", 1)
    menu = {m["dish"]: m for m in client.get("/shop/menu").json()["menu"]}
    assert menu["home_rice"]["available"] and menu["tomato_noodle"]["available"] and not menu["dessert"]["available"] and menu["dessert"]["reason"] == "no_ingredients"
    assert not menu["fish_soup"]["available"]
    g0, go = pw["gold"], po["gold"]
    r = action(client, whale, "order", {"dish": "tomato_noodle"})
    assert r["success"] and r["result"]["price"] == 22 and pw["gold"] == g0 - 22 and po["gold"] == go + 22
    assert inventory.count(po, "bread") == 0 and world_state.get_object_by_id("fridge_rest")["stock"]["ingredients"] == 1
    assert client.get(f"/player/{whale}").json()["busy"]["kind"] == "waiting_order"
    bar = next(o for o in client.get("/world").json()["objects"] if o["id"] == "bar")
    assert bar["orders"][0]["dish"] == "tomato_noodle" and len(bar["menu"]) == 5
    assert action(client, whale, "order", {"dish": "home_rice"})["reason"] == "already_eating"
    pw["fullness"] = 30.0
    _tick(fake_clock, 1); _tick(fake_clock, 61)                                    # 1 游戏分钟后上菜 → 自动开吃
    b = client.get(f"/player/{whale}").json()["busy"]
    assert b["kind"] == "eating" and "番茄蛋面上来了" in (world_state._pending_messages.get(whale) or "") or b["kind"] == "eating"
    _tick(fake_clock, 20 * 60 + 5)
    assert pw["fullness"] == pytest.approx(30 + 45 - 0.05 * 22, abs=1.5) and client.get(f"/player/{whale}").json()["busy"] is None
    led = shops.ledger_view("restaurant")
    assert led["entries"][-1]["kind"] == "sale" and led["entries"][-1]["amount"] == 22 and led["entries"][-1]["item_name"] == "番茄蛋面"
    # 钱不够
    pw["gold"] = 5
    assert action(client, whale, "order", {"dish": "home_rice"})["reason"] == "insufficient_funds"


def test_catch_of_day_priced_by_fish_and_closed_hours(client, v12, fake_clock):
    _at(fake_clock, 12)
    whale, owner = _agent(client, "whale"), _agent(client, "npc_rest_owner")
    po = world_state._players[owner]
    place(owner, 40, 13, "up")
    m = fishing.new_fish("golden_carp", 1.5, "npc_fisher", world_state.game_now_ts())
    inventory.add(po, "fish", 1, meta=m)
    _sit(client, whale)
    r = action(client, whale, "order", {"dish": "catch_of_day"})
    assert r["success"] and r["result"]["price"] == 60 * 2 + 10 and "红烧金鳞鲤" in r["result"]["name"] and not [e for e in po["inventory"] if e["type"] == "fish"]
    action(client, whale, "leave")
    _at(fake_clock, 15)                                                            # 14:00–17:00 不营业
    place(whale, 34, 12, "up")
    r = action(client, whale, "use")
    if r["success"]:
        assert action(client, whale, "order", {"dish": "home_rice"})["reason"] == "shop_closed"
    else:
        assert r["reason"] in ("closed", "shop_closed", "object_closed")
