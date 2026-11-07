"""W11 ①②③④⑤：产出链（钓位 / 灶台 / compose / make_video）、委托交付、直播 synthetic 收入、QQ 亲密度、库存与补货、冰箱、SANDBOX_MAP。"""
import json
import os
from datetime import date, datetime
from pathlib import Path

import httpx
import pytest

from game import world_state, ticker, economy, inventory, production, commissions, persistence, external_effects, self_sync
from game.paths import data_dir
from game.time_state import GAME_TZ
from tests.conftest import join, action, place, STREAM_STAND, STREAM_ID
from tests.test_w9_map_v2 import v1  # noqa: F401
from tests.test_external_effects import fake_self  # noqa: F401


def _at(fake_clock, h, m=0):
    fake_clock.t = datetime(2026, 11, 10, h, m, tzinfo=GAME_TZ).timestamp()


def _agent(client, aid, name=None):
    return client.post("/player/join", json={"name": name or aid, "controller": "agent", "profile": {"agent_id": aid}}).json()["playerId"]


def _tick(fake_clock, s=1.0):
    ticker.tick_once(checkpoint=False); fake_clock.advance(s); ticker.tick_once(checkpoint=False)


def _ledger():
    fp = data_dir() / "economy" / f"{date.today().isoformat()}.jsonl"
    return [json.loads(l) for l in fp.read_text(encoding="utf-8").splitlines()] if fp.exists() else []


def _external():
    fp = data_dir() / "external" / f"{date.today().isoformat()}.jsonl"
    return [json.loads(l) for l in fp.read_text(encoding="utf-8").splitlines()] if fp.exists() else []


# ── ① 钓位 ──
def test_fishing_rolls_every_interval_and_bait(client, v1, fake_clock, monkeypatch):
    _at(fake_clock, 10, 0)
    whale = _agent(client, "whale")
    place(whale, 57, 12, "up")
    cfg = economy.cfg()["production"]["fishing"]
    monkeypatch.setitem(cfg, "p", 1.0); monkeypatch.setitem(cfg, "p_bait", 1.0)
    assert action(client, whale, "use")["success"]
    _tick(fake_clock, 1)
    p = world_state._players[whale]
    assert inventory.count(p, "fish") == 0
    fake_clock.advance(40 * 60); _tick(fake_clock, 1)                                    # 40 分钟：掷一次（p=1 必中）
    assert inventory.count(p, "fish") == 1
    assert world_state._pending_messages[whale] == "钓到一条鱼！"
    rows = [r for r in _external() if r["kind"] == "produce"]
    assert rows and rows[-1]["via"] == "fishing" and rows[-1]["item"] == "fish" and rows[-1]["bait"] is False
    inventory.add(p, "bait", 1)
    fake_clock.advance(40 * 60); _tick(fake_clock, 1)                                    # 有鱼饵：消耗 1，走 p_bait
    assert inventory.count(p, "fish") == 2 and inventory.count(p, "bait") == 0
    assert [r for r in _external() if r["kind"] == "produce"][-1]["bait"] is True
    monkeypatch.setitem(cfg, "p", 0.0)
    fake_clock.advance(40 * 60); _tick(fake_clock, 1)
    assert inventory.count(p, "fish") == 2                                               # p=0 不中
    assert action(client, whale, "leave")["success"] and whale not in production._fish


# ── ① 灶台 ──
def test_stove_consumes_ingredients_and_produces_bento_after_30min(client, v1, fake_clock):
    _at(fake_clock, 10, 0)
    whale = _agent(client, "whale")
    place(whale, 8, 30, "up")
    r = action(client, whale, "use")
    assert r["success"] is False and r["reason"] == "no_ingredients"                     # 没食材不开火
    p = world_state._players[whale]
    inventory.add(p, "ingredients", 2)
    assert action(client, whale, "use")["success"] and inventory.count(p, "ingredients") == 1
    fake_clock.advance(20 * 60); _tick(fake_clock, 1)
    assert inventory.count(p, "bento") == 0
    fake_clock.advance(10 * 60 + 5); _tick(fake_clock, 1)                                # 满 30 分钟 → 便当 ×2
    assert inventory.count(p, "bento") == 2
    fake_clock.advance(10 * 60); _tick(fake_clock, 1)
    assert inventory.count(p, "bento") == 2                                              # 只产一次
    action(client, whale, "leave")
    # 提前走：食材耗了、没便当
    place(whale, 8, 30, "up"); world_state._last_used.clear()
    assert action(client, whale, "use")["success"] and inventory.count(p, "ingredients") == 0
    fake_clock.advance(5 * 60); _tick(fake_clock, 1)
    assert action(client, whale, "leave")["success"] and inventory.count(p, "bento") == 2
    assert action(client, whale, "eat", {"item": "bento"})["success"]                    # 便当随处吃


# ── ① compose / make_video / 委托 ──
def test_compose_requires_pc_music_and_time_then_deliver_commission(client, v1, fake_clock, monkeypatch):
    monkeypatch.setitem(economy.cfg()["commissions"], "daily_p", 0.0)                    # 这里不要自动出单
    _at(fake_clock, 10, 0)
    whale = _agent(client, "whale", "鲸仔"); owner = _agent(client, "npc_rest_owner", "餐厅老板")
    place(whale, 34, 3, "up")
    assert action(client, whale, "compose", {"title": "夜航"})["reason"] == "need_object"
    assert action(client, whale, "use")["success"]
    r = action(client, whale, "compose", {"title": "夜航"})
    assert r["success"] is False and r["reason"] == "not_ready" and r["result"]["ready_in_min"] == 30
    fake_clock.advance(31 * 60); _tick(fake_clock, 1)
    cm = client.post("/admin/commission", json={"client": "餐厅老板", "title": "店里要一首背景歌", "fee": 200}).json()["commission"]
    assert cm["client"] == "npc_rest_owner" and cm["status"] == "open" and cm["fee"] == 200
    assert client.get("/commissions").json()["count"] == 1
    r = action(client, whale, "compose", {"title": "夜航", "commission_id": cm["id"], "text": "歌词由 C 填"})
    assert r["success"] and r["result"]["item"] == "song" and r["result"]["meta"]["title"] == "夜航" and r["result"]["meta"]["commission_id"] == cm["id"]
    p = world_state._players[whale]
    assert inventory.count(p, "song") == 1
    # 公告栏读到委托
    action(client, whale, "leave"); place(whale, 28, 18, "up")
    nb = action(client, whale, "use")
    assert nb["success"] and nb["result"]["commissions"][0]["id"] == cm["id"] and "委托" in nb["result"]["message"]
    # 交付：give 给委托人 → 酬金 + 亲密度 +15
    place(whale, 10, 10, "up"); place(owner, 11, 10, "left")
    gold0 = p["gold"]
    r = action(client, whale, "give", {"target": owner, "item": "song"})
    assert r["success"] and r["result"]["commission"]["status"] == "delivered" and r["result"]["gold_delta"] == 200
    assert p["gold"] == gold0 + 200 and world_state._players[owner]["closeness"][whale] == 15.0
    assert inventory.count(world_state._players[owner], "song") == 1 and inventory.count(p, "song") == 0
    assert client.get("/commissions").json()["count"] == 0 and client.get("/commissions", params={"status": "all"}).json()["count"] == 1
    assert [x for x in _ledger() if x["source"] == "song_fee"][0]["delta"] == 200
    # 没有委托时 give song 只是转交
    inventory.add(p, "song", 1, meta={"title": "无主"})
    r = action(client, whale, "give", {"target": owner, "item": "song"})
    assert r["success"] and "commission" not in r["result"]


def test_make_video_on_pc_and_daily_commission_refresh(client, v1, fake_clock, monkeypatch):
    monkeypatch.setitem(economy.cfg()["commissions"], "daily_p", 1.0)
    _at(fake_clock, 7, 50)
    achan = _agent(client, "achan")
    place(achan, 8, 38, "up")                                                             # pc_achan（pc_desk）
    assert action(client, achan, "use")["success"]
    r = action(client, achan, "make_video", {"title": "周报"})
    assert r["reason"] == "not_ready" and r["result"]["ready_in_min"] == 60
    fake_clock.advance(61 * 60); _tick(fake_clock, 1)
    r = action(client, achan, "make_video", {"title": "周报"})
    assert r["success"] and r["result"]["item"] == "script" and inventory.count(world_state._players[achan], "script") == 1
    # 每日 08:00 委托刷新：daily_p=1 → 出一单；同日不再出
    assert client.get("/commissions").json()["count"] == 1                               # 08:50 的 tick 已经出了一单
    cm = client.get("/commissions").json()["commissions"][0]
    assert cm["source"] == "daily" and cm["client"] in economy.cfg()["commissions"]["clients"] and 150 <= cm["fee"] <= 300
    _tick(fake_clock, 1)
    assert client.get("/commissions").json()["count"] == 1


# ── ② 直播收入 ──
def test_stream_income_formula_and_synthetic_on_leave(client, fake_self):
    whale = _agent(client, "whale")
    r = client.post("/admin/income", json={"entity_id": whale, "source": "stream", "viewers_avg": 40, "gifts": 7}).json()
    assert r["delta"] == 27 and r["synthetic"] is False and r["viewers_avg"] == 40                 # 40 × 0.5 + 7
    assert client.post("/admin/income", json={"entity_id": whale, "source": "tip"}).status_code == 400   # 没 amount
    place(whale, *STREAM_STAND)
    assert action(client, whale, "use")["success"]
    n0 = len(_ledger())
    assert action(client, whale, "leave")["success"]
    rows = _ledger()[n0:]
    assert len(rows) == 1 and rows[0]["source"] == "stream" and rows[0]["synthetic"] is True and 20 <= rows[0]["delta"] <= 60
    assert rows[0]["shop"] == STREAM_ID and world_state._players[whale]["gold"] == 300 + 27 + rows[0]["delta"]
    # 直播机接上后关掉 synthetic
    economy.cfg()["live_income"]["synthetic"] = False
    try:
        world_state._last_used.clear()
        assert action(client, whale, "use")["success"]
        n1 = len(_ledger()); action(client, whale, "leave")
        assert len(_ledger()) == n1
    finally:
        economy.cfg()["live_income"]["synthetic"] = True


# ── ③ QQ 亲密度 ──
def test_qq_unread_penalty_and_read_reply_bonus(client, fake_clock, monkeypatch):
    from game import buff_tick
    monkeypatch.setattr(buff_tick, "CLOSENESS_PER_DAY", 0.0)                             # 关掉自然衰减，只看 QQ 的加减
    _at(fake_clock, 9, 0)
    whale = _agent(client, "whale"); achan = _agent(client, "achan")
    world_state._players[achan]["closeness"][whale] = 50.0
    client.post("/qq/send", json={"entity_id": achan, "to": "whale", "text": "在吗"})
    fake_clock.advance(2 * 3600 - 60); _tick(fake_clock, 1)
    assert world_state._players[achan]["closeness"][whale] == 50.0                       # 2 小时内不扣
    fake_clock.advance(2 * 3600); _tick(fake_clock, 1)                                   # 约 3h59m 未读 → 已过 2h 阈值 1 小时 → −1
    assert world_state._players[achan]["closeness"][whale] == 49.0
    fake_clock.advance(10 * 3600); _tick(fake_clock, 1)                                  # 再过 10 小时：日上限 −5
    assert world_state._players[achan]["closeness"][whale] == 45.0
    # 读 → 阿蝉对鲸仔 +1；回 → 再 +1
    client.post("/qq/read", json={"entity_id": whale})
    assert world_state._players[achan]["closeness"][whale] == 46.0
    client.post("/qq/send", json={"entity_id": whale, "to": "achan", "text": "在"})
    assert world_state._players[achan]["closeness"][whale] == 47.0
    # 群消息不计；已读不再扣
    client.post("/qq/send", json={"entity_id": achan, "group": "g_live", "text": "群里说"})
    fake_clock.advance(6 * 3600); _tick(fake_clock, 1)
    assert world_state._players[achan]["closeness"][whale] == 47.0


# ── ④ 库存与补货、冰箱 ──
def test_shop_stock_out_of_stock_and_daily_restock(client, fake_clock):
    _at(fake_clock, 10, 0)
    whale = _agent(client, "whale")
    world_state._players[whale]["gold"] = 1000
    place(whale, 26, 25, "up")
    counter = world_state.get_object_by_id("counter_grocer")
    assert counter["stock"]["gift"] == 3
    assert action(client, whale, "buy", {"item": "gift", "qty": 3})["success"] and counter["stock"]["gift"] == 0
    r = action(client, whale, "buy", {"item": "gift"})
    assert r["success"] is False and r["reason"] == "out_of_stock" and r["result"]["stock"] == 0
    shop = {x["type"]: x for x in next(o for o in client.get("/world", params={"fields": "objects"}).json()["objects"] if o["id"] == "counter_grocer")["shop"]}
    assert shop["gift"]["stock"] == 0 and shop["bread"]["stock"] == 10
    _at(fake_clock, 8, 30); _tick(fake_clock, 1)                                          # 次日（这里直接拨到 08:30，另一天的 key）→ 补到水位
    assert counter["stock"]["gift"] == 3
    _at(fake_clock, 9, 0); _tick(fake_clock, 1)
    assert counter["stock"]["gift"] == 3                                                  # 同日只补一次（买走的不会再补）
    o = next(o for o in client.get("/world", params={"fields": "objects"}).json()["objects"] if o["id"] == "counter_grocer")
    assert o["stock"]["gift"] == 3 and {x["type"]: x for x in o["shop"]}["gift"]["stock"] == 3


def test_fridge_stock_empty_store_and_restock(client, fake_clock):
    _at(fake_clock, 7, 0)
    whale = _agent(client, "whale")
    fridge = world_state.get_object_by_id("fridge_kitchen")
    assert fridge["stock"] == {"ingredients": 2}
    place(whale, fridge["position"]["x"], fridge["position"]["y"] + 1, "up")
    assert action(client, whale, "use")["success"] and fridge["stock"]["ingredients"] == 1
    world_state._last_used.clear()
    r = action(client, whale, "use"); assert r["success"] and r["result"]["stock"] == {"ingredients": 0}
    world_state._last_used.clear()
    r = action(client, whale, "use")
    assert r["success"] is False and r["reason"] == "empty"
    # store：放食材进去（不超过 4）
    inventory.add(world_state._players[whale], "ingredients", 6)
    r = action(client, whale, "store", {"qty": 6})
    assert r["success"] and r["result"]["stock"] == {"ingredients": 4} and inventory.count(world_state._players[whale], "ingredients") == 2
    assert action(client, whale, "store", {"qty": 1})["reason"] == "storage_full"
    assert action(client, whale, "store", {"item": "fish"})["reason"] == "not_storable"
    # 08:00 补 2 份不超过 4
    fridge["stock"]["ingredients"] = 3
    _at(fake_clock, 8, 1); _tick(fake_clock, 1)
    assert fridge["stock"]["ingredients"] == 4
    # 检查点保留库存
    persistence.save_checkpoint(); world_state._reset_for_tests()
    assert world_state.get_object_by_id("fridge_kitchen")["stock"] == {"ingredients": 2}
    persistence.load_checkpoint()
    assert world_state.get_object_by_id("fridge_kitchen")["stock"] == {"ingredients": 4}


# ── ⑤ 地图开关 ──
def test_sandbox_map_env_resolves_v1(monkeypatch):
    base = Path(world_state.__file__).parent / "maps"
    monkeypatch.delenv("SANDBOX_MAP_DIR", raising=False)
    monkeypatch.setenv("SANDBOX_MAP", "v1")
    assert world_state._resolve_map_dir() == base / "v1"
    monkeypatch.setenv("SANDBOX_MAP", "v0")
    assert world_state._resolve_map_dir() == base
    monkeypatch.setenv("SANDBOX_MAP", "nope")
    assert world_state._resolve_map_dir() == base
    monkeypatch.setenv("SANDBOX_MAP_DIR", str(base / "m1c"))
    assert world_state._resolve_map_dir() == base / "m1c"                                 # 显式目录优先
