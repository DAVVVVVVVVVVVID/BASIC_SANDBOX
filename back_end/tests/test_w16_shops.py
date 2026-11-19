"""商店第一期（world-v1.4.11；docs/shops-phase1-sandbox.md）：周叔进货 / 账本 / 换鱼饵 pay|donate / 变质物 2 日消失。"""
from datetime import datetime

import pytest

from game import shops, inventory, world_state, ticker, economy, persistence
from game.time_state import GAME_TZ
from tests.conftest import action, place
from tests.test_w9_map_v2 import _agent, v12  # noqa: F401

DAY = 86400.0


def _at(fake_clock, d, h, m=0):
    fake_clock.t = datetime(2026, 11, d, h, m, tzinfo=GAME_TZ).timestamp()


def _tick(fake_clock, s=1.0):
    fake_clock.advance(s); ticker.tick_once(checkpoint=False)


def _qq(client, frm, text):
    r = client.post("/qq/send", json={"from": frm, "to": "supplier_zhou", "text": text})
    assert r.status_code == 200, r.text
    return r.json()


def _last_from_zhou(client, pid):
    msgs = [m for m in client.get("/qq/inbox", params={"player": pid}).json()["messages"] if m["from"] == "supplier_zhou"]
    return msgs[-1] if msgs else None


def test_parse_order_variants():
    got = {r["item"]: r["qty"] for r in shops.parse_order("明天要面包 10、食材×12，再来六袋甜食，礼物2个，鱼饵十五")}
    assert got == {"bread": 10, "ingredients": 12, "sweets": 6, "gift": 2, "bait": 15}
    assert shops.parse_order("今天天气不错") == []


def test_quote_confirm_deliver_cap_refund_and_ledger(client, v12, fake_clock):
    _at(fake_clock, 20, 10)
    grocer, cl, whale = _agent(client, "npc_grocer"), _agent(client, "claudine"), _agent(client, "whale")
    pg = world_state._players[grocer]
    g0 = pg["gold"]
    # 别人发：只回一句
    _qq(client, whale, "面包 10")
    assert "只跟杂货店" in _last_from_zhou(client, whale)["text"]
    # 小克代下单 → 报价单（meta.order）
    _qq(client, cl, "明天要面包 10、食材 12、甜食 6")
    m = _last_from_zhou(client, cl)
    o = m["meta"]["order"]
    assert o["status"] == "quoted" and o["goods"] == 10 * 3 + 12 * 4 + 6 * 3 and o["freight"] == 10 and o["total"] == 106 and o["payer"] == "npc_grocer"
    assert "回复「确认」" in m["text"] and o["deliver_at"].startswith("2026-11-21T07:30")
    pv = client.get("/agent/perceive", params={"entity_id": cl}).json()
    assert [x["order_id"] for x in pv["orders_pending"]] == [o["order_id"]]
    assert client.get("/agent/perceive", params={"entity_id": whale}).json()["orders_pending"] is None
    # 确认 → 扣店主账户（小克代下单也扣店主）
    _qq(client, cl, "确认！")
    o2 = _last_from_zhou(client, cl)["meta"]["order"]
    assert o2["status"] == "confirmed" and pg["gold"] == g0 - 106
    counter = world_state.get_object_by_id("counter")
    wh = next(x for x in client.get("/world").json()["objects"] if x["id"] == "counter")["warehouse"]
    assert wh["capacity"] == 40 and wh["incoming"][0]["order_id"] == o["order_id"] and wh["incoming"][0]["eta"].startswith("2026-11-21T07:30")
    # 再下一单面包 40 → 送达时超上限退款
    _qq(client, grocer, "面包 40"); _qq(client, grocer, "好")
    assert pg["gold"] == g0 - 106 - (40 * 3 + 10)
    bread0 = int(counter["stock"].get("bread", 0)); ing0 = int(counter["stock"].get("ingredients", 0))
    _at(fake_clock, 21, 7, 29); _tick(fake_clock, 1); _tick(fake_clock, 1)
    assert int(counter["stock"].get("bread", 0)) == bread0                                   # 07:30 前没到
    _at(fake_clock, 21, 7, 31); _tick(fake_clock, 1); _tick(fake_clock, 1)
    assert counter["stock"]["bread"] == 40 and counter["stock"]["ingredients"] == min(40, ing0 + 12)
    over = bread0 + 10 + 40 - 40
    assert pg["gold"] == g0 - 106 - 130 + over * 3                                            # 超出部分退款
    assert "货到了" in _last_from_zhou(client, cl)["text"]
    led = client.get("/shops/counter/ledger", params={"days": 2}).json()
    kinds = [e["kind"] for e in led["entries"]]
    assert kinds.count("purchase") == 4 and kinds.count("freight") == 2 and "refund" in kinds and led["name"] == "杂货店"
    assert led["days"][0]["cost"] == 106 + 130 and led["days"][-1]["revenue"] == over * 3


def test_cutoff_2200_goes_day_after_tomorrow_and_expiry(client, v12, fake_clock):
    _at(fake_clock, 20, 22, 10)
    grocer = _agent(client, "npc_grocer")
    _qq(client, grocer, "面包 5")
    o = _last_from_zhou(client, grocer)["meta"]["order"]
    assert o["deliver_at"].startswith("2026-11-22T07:30")
    _at(fake_clock, 20, 22, 45); _tick(fake_clock, 1); _tick(fake_clock, 1)                   # 30 分钟没确认 → 作废
    assert shops.orders_view(status="expired")[0]["order_id"] == o["order_id"]
    _qq(client, grocer, "确认")
    assert "没有等你确认" in _last_from_zhou(client, grocer)["text"]
    _qq(client, grocer, "嗯嗯")
    assert "没看懂" in _last_from_zhou(client, grocer)["text"]


def test_sales_ledger_permissions_and_read_ledger(client, v12, fake_clock):
    _at(fake_clock, 20, 10)
    grocer, cl, whale = _agent(client, "npc_grocer"), _agent(client, "claudine"), _agent(client, "whale")
    place(whale, 28, 23, "up")
    assert action(client, whale, "buy", {"item": "bread", "qty": 2})["success"]
    r = action(client, cl, "read_ledger", {"shop": "grocery"})
    assert r["success"] and r["result"]["entries"][-1]["kind"] == "sale" and r["result"]["entries"][-1]["qty"] == 2 and r["result"]["days"][-1]["revenue"] == 10
    assert action(client, whale, "read_ledger", {"shop": "grocery"})["reason"] == "no_permission"
    assert action(client, grocer, "read_ledger", {})["success"]                                  # 不带 shop = 自己那本
    assert client.get("/shops/bar/ledger").json()["shop"] == "restaurant" and client.get("/shops/nope/ledger").status_code == 404


def test_exchange_pay_and_donate_and_spoiled_vanish(client, v12, fake_clock):
    _at(fake_clock, 20, 10)
    grocer, whale = _agent(client, "npc_grocer"), _agent(client, "whale")
    pw, pg = world_state._players[whale], world_state._players[grocer]
    place(whale, 28, 23, "up")
    inventory.add(pw, "junk_can", 2)
    g0, gg = pw["gold"], pg["gold"]
    r = action(client, whale, "exchange", {"item": "junk_can"})
    assert r["success"] and inventory.count(pw, "bait") == 1 and pw["gold"] == g0 - 1 and pg["gold"] == gg + 1
    counter = world_state.get_object_by_id("counter"); b0 = int(counter["stock"].get("bait", 0))
    r = action(client, whale, "exchange", {"item": "junk_can", "mode": "donate"})
    assert r["success"] and inventory.count(pw, "bait") == 1 and counter["stock"]["bait"] == b0 + 1 and pw["gold"] == g0 - 1
    kinds = [e["kind"] for e in shops.ledger_view("grocery")["entries"]]
    assert kinds.count("recycle") == 2
    # 坏掉的食物：变质后 2 日自动消失
    inventory.add(pw, "bread", 1, expires_at=world_state.game_now_ts() + 60)
    _tick(fake_clock, 120); _tick(fake_clock, 1)
    assert inventory.count(pw, "spoiled_food") == 1
    _tick(fake_clock, 2 * DAY + 60); _tick(fake_clock, 1)
    assert inventory.count(pw, "spoiled_food") == 0 and "扔掉" in (world_state._pending_messages.get(whale) or "")


def test_checkpoint_roundtrip_and_legacy_stall_stock_cleared(client, v12, fake_clock, tmp_path):
    _at(fake_clock, 20, 10)
    grocer = _agent(client, "npc_grocer")
    _qq(client, grocer, "面包 3")
    world_state.get_object_by_id("fish_stall")["stock"] = {"fish": 6}
    db = tmp_path / "cp.sqlite"
    persistence.save_checkpoint(db)
    shops.import_state(None)
    persistence.load_checkpoint(db)
    assert len(shops.orders_view()) == 1 and world_state.get_object_by_id("fish_stall")["stock"].get("fish") is None


def test_admin_shop_stock_edit(client, v12, fake_clock, monkeypatch):
    monkeypatch.setenv("SANDBOX_ADMIN_TOKEN", "t0k")
    _at(fake_clock, 20, 10)
    body = {"object": "counter", "item": "ingredients", "qty": 12, "reason": "测试补料"}
    assert client.post("/admin/shop/stock", json=body).status_code == 401
    world_state.get_object_by_id("counter")["stock"]["ingredients"] = 0
    r = client.post("/admin/shop/stock", json=body, headers={"Authorization": "Bearer t0k"}).json()
    assert r["before"] == 0 and r["after"] == 12 and world_state.get_object_by_id("counter")["stock"]["ingredients"] == 12
    assert shops.ledger_view("grocery")["entries"][-1]["kind"] == "adjust"


def test_admin_stock_fridge_contents_v1417(client, v12, fake_clock, monkeypatch):
    monkeypatch.setenv("SANDBOX_ADMIN_TOKEN", "t0k")
    _at(fake_clock, 20, 10)
    fr = world_state.get_object_by_id("fridge_rest"); fr["contents"] = []
    H = {"Authorization": "Bearer t0k"}
    r = client.post("/admin/shop/stock", json={"object": "fridge_rest", "item": "ingredients", "qty": 4, "reason": "测试"}, headers=H).json()
    assert r["before"] == 0 and r["after"] == 4 and fr["stock"]["ingredients"] == 4 and fr["contents"][0]["expires_at"] is not None
    r = client.post("/admin/shop/stock", json={"object": "fridge_rest", "item": "ingredients", "qty": 1}, headers=H).json()
    assert r["after"] == 1 and shops.ledger_view("restaurant")["entries"][-1]["kind"] == "adjust"
