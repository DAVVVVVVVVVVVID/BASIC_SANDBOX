"""W10 ④ 金币与背包：初始金币、/world shop[]、buy/sell/eat/give、insufficient_funds、营业时间、/admin/income、日薪时薪、
餐厅吃饭扣款、state 行 gold、经济 JSONL 与导出、检查点。数值全来自 economy.json / items.json。"""
import json
import pytest
from datetime import date, datetime

from game import world_state, ticker, economy, inventory, persistence
from game.paths import data_dir
from game.time_state import GAME_TZ
from tests.conftest import join, action, place

COUNTER = "counter_grocer"          # (26,24)；站 (26,25) 朝 up
COUNTER_STAND = (26, 25, "up")
TABLE = "table_rest_1"              # (46,32)-(47,32)；站 (46,33) 朝 up


def _at(fake_clock, h, m=0):
    fake_clock.t = datetime(2026, 11, 10, h, m, tzinfo=GAME_TZ).timestamp()


def _agent(client, aid, name=None):
    return client.post("/player/join", json={"name": name or aid, "controller": "agent", "profile": {"agent_id": aid}}).json()["playerId"]


def _tick(fake_clock, s=1.0):
    ticker.tick_once(checkpoint=False); fake_clock.advance(s); ticker.tick_once(checkpoint=False)


def _ledger():
    fp = data_dir() / "economy" / f"{date.today().isoformat()}.jsonl"
    return [json.loads(l) for l in fp.read_text(encoding="utf-8").splitlines()] if fp.exists() else []


def test_initial_gold_from_config_and_exposed(client):
    cfg = economy.cfg()["initial_gold"]
    whale = _agent(client, "whale"); achan = _agent(client, "achan"); h = join(client, "h")
    assert client.get(f"/player/{whale}").json()["gold"] == cfg["whale"] == 3000          # v1.1 M-1：全员 3000
    assert client.get(f"/player/{achan}").json()["gold"] == cfg["achan"] == 3000
    assert client.get(f"/player/{h}").json()["gold"] == cfg["default"]
    snap = {p["id"]: p for p in client.get("/world", params={"fields": "players"}).json()["players"]}
    assert snap[whale]["gold"] == 3000 and snap[whale]["inventory"] == []


def test_world_objects_carry_shop_listing(client):
    objs = {o["id"]: o for o in client.get("/world", params={"fields": "objects"}).json()["objects"]}
    shop = objs[COUNTER]["shop"]
    assert [r["type"] for r in shop] == ["bait", "bread", "gift", "ingredients", "sweets"]
    bread = next(r for r in shop if r["type"] == "bread")
    assert bread == {"type": "bread", "item": "bread", "name": "面包", "price": 5, "sell": None, "stock": 8}    # v1.1：每日上新 8
    assert objs[COUNTER]["daily_supply"]["bread"] == 8 and objs[COUNTER]["restock_at"] == "08:00"
    assert objs[TABLE]["shop"] is None and objs[COUNTER]["openHours"] == [["09:00", "22:00"]]              # v1.1：杂货店到 22:00


def test_buy_eat_sell_and_insufficient_funds(client, fake_clock):
    _at(fake_clock, 10, 0)
    whale = _agent(client, "whale", "鲸仔"); grocer = _agent(client, "npc_grocer", "杂货店老板")
    place(whale, *COUNTER_STAND); place(grocer, 25, 24, "right")
    r = action(client, whale, "buy", {"item": "bread", "qty": 2})
    assert r["success"] and r["result"]["gold_delta"] == -10 and r["result"]["gold"] == 2990 and r["result"]["item_name"] == "面包"
    assert r["result"]["inventory"] == [{"type": "bread", "name": "面包", "class": "food", "count": 2}]
    assert client.get(f"/player/{grocer}").json()["gold"] == 3000 + 10                        # 老板入账
    # object_id 写法 + item_id 写法
    r = action(client, whale, "buy", {"object_id": COUNTER, "item_id": "sweets"})
    assert r["success"] and client.get(f"/player/{whale}").json()["gold"] == 2984
    assert action(client, whale, "buy", {"item": "fish"})["reason"] == "not_for_sale"        # 杂货店不卖鱼
    assert action(client, whale, "buy", {"item": "unicorn"})["reason"] == "unknown_item"
    # 钱不够
    world_state._players[whale]["gold"] = 20
    r = action(client, whale, "buy", {"item": "gift"})
    assert r["success"] is False and r["reason"] == "insufficient_funds" and r["result"]["price"] == 25 and r["result"]["gold"] == 20
    # 吃（world-v1.1）：只能坐在餐桌类上吃；长椅是简餐处；面包 5 分钟线性 +20
    world_state._players[whale]["fullness"] = 40.0
    place(whale, 10, 10, "up")
    assert action(client, whale, "eat", {"item": "bread"})["reason"] == "not_at_table"
    place(whale, 32, 26, "up"); assert action(client, whale, "use")["success"]                 # bench_square_1
    r = action(client, whale, "eat", {"item": "bread"})
    assert r["success"] and r["result"]["duration_s"] == 300 and r["result"]["gain"] == {"fullness": 20.0} and inventory.count(world_state._players[whale], "bread") == 1
    assert action(client, whale, "eat", {"item": "bread"})["reason"] == "already_eating"
    pv = client.get(f"/player/{whale}").json()
    assert pv["busy"]["kind"] == "eating" and pv["busy"]["item"] == "bread" and "eating" in pv["tags"]
    ticker.tick_once(checkpoint=False); fake_clock.advance(150); ticker.tick_once(checkpoint=False)
    assert world_state._players[whale]["fullness"] == pytest.approx(40 + 10 - 3 * 150 / 3600, abs=0.05)   # 吃一半涨一半（减衰减）
    fake_clock.advance(160); ticker.tick_once(checkpoint=False)
    assert client.get(f"/player/{whale}").json()["busy"] is None and world_state._players[whale]["fullness"] == pytest.approx(60 - 3 * 310 / 3600, abs=0.05)
    assert action(client, whale, "eat", {"item": "gift"})["reason"] == "not_edible"
    assert action(client, whale, "eat", {"item": "home_meal"})["reason"] == "no_item"
    assert action(client, whale, "eat", {"item": "ingredients"})["reason"] == "not_allowed_here"          # 长椅不许吃生食材
    action(client, whale, "leave")
    # 卖：杂货店不收；（鱼摊 / 吧台收鱼在 v1 地图，这里只验 reason）
    place(whale, *COUNTER_STAND)
    assert action(client, whale, "sell", {"item": "bread"})["reason"] == "not_buying"
    # 流水
    kinds = [(r["kind"], r["account"], r["delta"]) for r in _ledger()]
    assert kinds == [("buy", "whale", -10), ("income", "npc_grocer", 10), ("buy", "whale", -6), ("income", "npc_grocer", 6)]
    assert all(r["balance"] is not None and r["town"] == "main" for r in _ledger())
    d = client.get("/admin/export", params={"date": date.today().isoformat(), "kinds": "economy"}).json()
    assert d["manifest"]["counts"] == {"economy": 4} and d["economy"][0]["item"] == "bread"


def test_shop_hours_and_no_shop(client, fake_clock):
    whale = _agent(client, "whale")
    place(whale, *COUNTER_STAND)
    _at(fake_clock, 22, 30)
    r = action(client, whale, "buy", {"item": "bread"})
    assert r["success"] is False and r["reason"] == "shop_closed" and r["result"]["opens_at"] == "09:00"
    _at(fake_clock, 9, 30)
    assert action(client, whale, "buy", {"item": "bread"})["success"]
    place(whale, 10, 10, "up")
    assert action(client, whale, "buy", {"item": "bread"})["reason"] == "no_object"
    assert action(client, whale, "buy", {"object_id": COUNTER, "item": "bread"})["reason"] == "object_too_far"


def test_give_gift_and_inventory_limit(client, monkeypatch):
    whale = _agent(client, "whale", "鲸仔"); achan = _agent(client, "achan", "阿蝉")
    place(whale, 10, 10, "up"); place(achan, 11, 10, "left")
    inventory.add(world_state._players[whale], "gift", 2)
    world_state._players[achan]["mood"] = 60.0
    r = action(client, whale, "give", {"target": "achan", "item": "gift"})
    assert r["success"] and r["result"]["target"] == achan and r["result"]["target_name"] == "阿蝉"
    assert r["result"]["target_effects"] == {"closeness": 8.0, "mood": 65.0}
    assert world_state._players[achan]["closeness"][whale] == 8.0
    assert inventory.count(world_state._players[achan], "gift") == 1 and inventory.count(world_state._players[whale], "gift") == 1
    place(achan, 20, 10, "left")
    assert action(client, whale, "give", {"target": achan, "item": "gift"})["reason"] == "target_too_far"
    assert action(client, whale, "give", {"target": "ghost", "item": "gift"})["reason"] == "target_not_found"
    place(achan, 11, 10, "left")
    assert action(client, whale, "give", {"target": achan, "item": "fish"})["reason"] == "no_item"
    # ≤ MAX_KINDS 种（目录正好 10 种，这里把上限临时压到 3 验证满包）
    p = world_state._players[whale]
    monkeypatch.setattr(inventory, "MAX_KINDS", 3)
    assert inventory.add(p, "bread", 1) is None and inventory.add(p, "fish", 1) is None          # gift + bread + fish = 3 种
    assert inventory.add(p, "image", 1) == "inventory_full" and inventory.add(p, "bread", 2) is None   # 已有的种类还能加
    inventory.add(world_state._players[achan], "bread", 1)                                            # achan：gift + bread
    assert action(client, whale, "give", {"target": achan, "item": "fish"})["success"]                # 第 3 种，正好满
    inventory.add(p, "bait", 1)
    r = action(client, whale, "give", {"target": achan, "item": "bait"})
    assert r["success"] is False and r["reason"] == "inventory_full" and inventory.count(p, "bait") == 1   # 对方满包，自己不扣


def test_restaurant_meal_charges_and_insufficient_funds(client, fake_clock):
    _at(fake_clock, 12, 0)
    whale = _agent(client, "whale"); owner = _agent(client, "npc_rest_owner")
    place(whale, 46, 33, "up"); place(owner, 50, 30, "up")
    r = action(client, whale, "use")
    assert r["success"] and r["result"]["objectId"] == TABLE
    assert client.get(f"/player/{whale}").json()["gold"] == 3000                                           # v1.1：坐下免费
    r = action(client, whale, "eat", {"item": "meal"})                                                     # 点一顿：开吃扣 20、30 分钟 +45 心情 +5
    assert r["success"] and r["result"]["price"] == 20 and r["result"]["duration_s"] == 1800 and r["result"]["gain"] == {"fullness": 45.0, "mood": 5.0}
    assert client.get(f"/player/{whale}").json()["gold"] == 3000 - 20 and client.get(f"/player/{owner}").json()["gold"] == 3000 + 20
    action(client, whale, "leave")
    assert client.get(f"/player/{whale}").json()["busy"] is None                                           # 离桌 = 中断
    world_state._players[whale]["gold"] = 5
    world_state._last_used.clear()
    assert action(client, whale, "use")["success"]
    r = action(client, whale, "eat", {"item": "meal"})
    assert r["success"] is False and r["reason"] == "insufficient_funds" and r["result"]["price"] == 20
    assert world_state._players[whale]["usingObjectId"] == TABLE                                           # 仍坐着
    action(client, whale, "leave"); place(whale, 32, 26, "up"); assert action(client, whale, "use")["success"]
    assert action(client, whale, "eat", {"item": "meal"})["reason"] == "not_allowed_here"                  # 长椅点不了菜


def test_admin_income_and_wages_by_schedule(client, fake_clock):
    _at(fake_clock, 12, 0)
    whale = _agent(client, "whale"); achan = _agent(client, "achan"); xq = _agent(client, "npc_xiaoqian")
    r = client.post("/admin/income", json={"entity_id": whale, "amount": 200, "source": "song_fee", "label": "《夜航》酬金"}).json()
    assert r["ok"] and r["balance"] == 3200 and r["account"] == "whale"
    r = client.post("/admin/income", json={"account": "whale", "amount": -30, "source": "adjust"}).json()
    assert r["balance"] == 3170
    assert client.post("/admin/income", json={"account": "nobody", "amount": 1}).status_code == 404
    _tick(fake_clock, 1)
    assert world_state._players[xq]["gold"] == 3000 and world_state._players[achan]["gold"] == 3000
    # 小千周一至周五 13–17 点时薪 12（11-10 周二）：到 15:30 应结 2 小时（14 点、15 点整点）；到 17:05 共 4 小时；之后不再发；钱从店主（没上线）账户扣
    _at(fake_clock, 15, 30); _tick(fake_clock, 1)
    assert world_state._players[xq]["gold"] == 3000 + 24 and economy.balance("npc_grocer") == 3000 - 24
    _at(fake_clock, 17, 5); _tick(fake_clock, 1)
    assert world_state._players[xq]["gold"] == 3000 + 48 and economy.balance("npc_grocer") == 3000 - 48
    # 阿蝉 18:30 日薪 200：18:00 还没发，18:31 发一次，之后同一天不再发
    _at(fake_clock, 18, 0); _tick(fake_clock, 1)
    assert world_state._players[achan]["gold"] == 3000 and world_state._players[xq]["gold"] == 3048
    _at(fake_clock, 18, 31); _tick(fake_clock, 1)
    assert world_state._players[achan]["gold"] == 3200
    _at(fake_clock, 19, 0); _tick(fake_clock, 1); _tick(fake_clock, 1)
    assert world_state._players[achan]["gold"] == 3200
    wage_rows = [r for r in _ledger() if r["kind"] == "wage"]
    assert [(r["account"], r["delta"]) for r in wage_rows] == [("npc_xiaoqian", 12)] * 4 + [("achan", 200)]
    assert [(r["account"], r["delta"], r["offline"]) for r in _ledger() if r["kind"] == "wage_paid"] == [("npc_grocer", -12, True)] * 4
    # 老板娘上线：接着用自己的账户（离线扣过的钱不回来）
    grocer = _agent(client, "npc_grocer")
    assert world_state._players[grocer]["gold"] == 3000 - 48
    # 周末不结时薪
    _at(fake_clock, 15, 30); fake_clock.t += 4 * 86400; _tick(fake_clock, 1)          # 11-14 周六
    assert world_state._players[xq]["gold"] == 3048
    # state 行带 gold
    from game import state_log
    row = state_log._row(world_state._players[whale], "2026-11-10T18:00:00+08:00")
    assert row["gold"] == 3170


def test_checkpoint_keeps_gold_inventory_and_paid(client, fake_clock):
    _at(fake_clock, 18, 31)
    achan = _agent(client, "achan")
    _tick(fake_clock, 1)
    inventory.add(world_state._players[achan], "bread", 3)
    assert world_state._players[achan]["gold"] == 3200
    persistence.save_checkpoint()
    world_state._reset_for_tests(); economy._reset_for_tests()
    persistence.load_checkpoint()
    p = world_state._players[achan]
    assert p["gold"] == 3200 and inventory.count(p, "bread") == 3
    _at(fake_clock, 19, 0); _tick(fake_clock, 1)
    assert p["gold"] == 3200                                                                  # 已付记录也在检查点里，不重复发薪
