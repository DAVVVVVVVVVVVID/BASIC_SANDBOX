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
from tests.test_w9_map_v2 import v12  # noqa: F401
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
def test_fishing_rolls_every_interval_and_bait(client, v12, fake_clock, monkeypatch):
    _at(fake_clock, 10, 0)
    whale = _agent(client, "whale")
    place(whale, 45, 3, "up")
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
def test_stove_consumes_ingredients_and_produces_bento_after_30min(client, v12, fake_clock):
    """world-v1.1 §1.1：灶台按份——use {item, qty} 立即扣 n 份，20 + 10×(n−1) 分钟后产 n 份家常菜（带保质期 3 天）；中途走白费；吃要到餐桌。"""
    _at(fake_clock, 10, 0)
    whale = _agent(client, "whale")
    place(whale, 3, 16, "up")
    r = action(client, whale, "use")
    assert r["success"] is False and r["reason"] == "no_ingredients" and r["result"]["have"] == 0    # 没食材不开火
    p = world_state._players[whale]
    inventory.add(p, "ingredients", 3)
    r = action(client, whale, "use", {"item": "ingredients", "qty": 2})
    assert r["success"] and inventory.count(p, "ingredients") == 1
    assert r["result"]["cooking"]["portions"] == 2 and r["result"]["cooking"]["product"] == "home_meal" and r["result"]["cooking"]["ready_in_min"] == 30
    stove = next(o for o in client.get("/world", params={"fields": "objects"}).json()["objects"] if o["id"] == "stove")
    assert stove["cooking"]["by"] == whale and stove["cooking"]["ready_at"].endswith("10:30:00+08:00") and stove["work"] is True
    assert "working" in p["tags"] and "cooking" in p["tags"]
    fake_clock.advance(20 * 60); _tick(fake_clock, 1)
    assert inventory.count(p, "home_meal") == 0
    fake_clock.advance(10 * 60 + 5); _tick(fake_clock, 1)                                # 满 30 分钟 → 家常菜 ×2
    assert inventory.count(p, "home_meal") == 2
    assert next(e for e in p["inventory"] if e["type"] == "home_meal")["expires_at"] == pytest.approx(fake_clock.t + 3 * 86400, abs=5)
    fake_clock.advance(10 * 60); _tick(fake_clock, 1)
    assert inventory.count(p, "home_meal") == 2                                          # 只产一次
    action(client, whale, "leave")
    assert "working" not in p["tags"]
    # 提前走：食材耗了、没菜（ws cook_cancelled）
    place(whale, 3, 16, "up")
    assert action(client, whale, "use")["success"] and inventory.count(p, "ingredients") == 0   # 无冷却
    fake_clock.advance(5 * 60); _tick(fake_clock, 1)
    assert action(client, whale, "leave")["success"] and inventory.count(p, "home_meal") == 2
    # 吃：不在餐桌不行；到合租房餐桌 15 分钟 +40
    assert action(client, whale, "eat", {"item": "home_meal"})["reason"] == "not_at_table"
    place(whale, 7, 12, "up"); assert action(client, whale, "use")["success"]
    p["fullness"] = 30.0
    r = action(client, whale, "eat", {"item": "home_meal"})
    assert r["success"] and r["result"]["duration_s"] == 900 and inventory.count(p, "home_meal") == 1
    fake_clock.advance(900); _tick(fake_clock, 1)
    assert p["fullness"] == pytest.approx(70 - 3 * 902 / 3600, abs=0.05) and client.get(f"/player/{whale}").json()["busy"] is None
    # 直播中不能吃
    p["tags"].append("streaming")
    assert action(client, whale, "eat", {"item": "home_meal"})["reason"] == "streaming"


# ── ① compose / make_video / 委托 ──
def test_compose_requires_pc_music_and_time_then_deliver_commission(client, v12, fake_clock, monkeypatch):
    monkeypatch.setitem(economy.cfg()["commissions"], "daily_p", 0.0)                    # 这里不要自动出单
    _at(fake_clock, 10, 0)
    whale = _agent(client, "whale", "鲸仔"); owner = _agent(client, "npc_rest_owner", "餐厅老板")
    place(whale, 24, 3, "up")
    assert action(client, whale, "compose", {"title": "夜航"})["reason"] == "need_object"
    assert action(client, whale, "use")["success"]
    r = action(client, whale, "compose", {"title": "夜航"})
    assert r["success"] is False and r["reason"] == "not_ready" and r["result"]["ready_in_min"] == 30
    fake_clock.advance(31 * 60); _tick(fake_clock, 1)
    cm = client.post("/admin/commission", json={"client": "餐厅老板", "title": "店里要一首背景歌", "fee": 200}).json()["commission"]
    assert cm["client"] == "npc_rest_owner" and cm["status"] == "open" and cm["fee"] == 200
    assert client.get("/commissions").json()["count"] == 1
    r = action(client, whale, "compose", {"title": "夜航", "commission_id": cm["id"], "text": "歌词由 C 填"})
    assert r["success"] and r["result"]["item"] == "cd" and r["result"]["meta"]["title"] == "夜航" and r["result"]["meta"]["commission_id"] == cm["id"]   # v1.1 Q-5：实体 CD
    p = world_state._players[whale]
    assert inventory.count(p, "cd") == 1
    # 再刻一张：10 分钟，busy kind burning；中途不离开
    assert action(client, whale, "burn_cd", {"title": "不存在"})["reason"] == "no_item"
    rb = action(client, whale, "burn_cd", {})
    assert rb["success"] and rb["result"]["duration_s"] == 600 and client.get(f"/player/{whale}").json()["busy"]["kind"] == "burning"
    assert action(client, whale, "burn_cd", {})["reason"] == "already_burning"
    fake_clock.advance(601); _tick(fake_clock, 1)
    assert inventory.count(p, "cd") == 2 and client.get(f"/player/{whale}").json()["busy"] is None and "burning" not in p["tags"]
    # 公告栏读到委托
    action(client, whale, "leave"); place(whale, 19, 11, "up")
    nb = action(client, whale, "use")
    assert nb["success"] and nb["result"]["commissions"][0]["id"] == cm["id"] and "委托" in nb["result"]["message"]
    # 交付：give 给委托人 → 酬金 + 亲密度 +15
    place(whale, 3, 19, "up"); place(owner, 4, 19, "left")
    gold0 = p["gold"]
    r = action(client, whale, "give", {"target": owner, "item": "cd"})
    assert r["success"] and r["result"]["commission"]["status"] == "delivered" and r["result"]["gold_delta"] == 200
    assert p["gold"] == gold0 + 200 and world_state._players[owner]["closeness"][whale] == 15.0
    assert inventory.count(world_state._players[owner], "cd") == 1 and inventory.count(p, "cd") == 1      # 还剩刻的那张
    assert client.get("/commissions").json()["count"] == 0 and client.get("/commissions", params={"status": "all"}).json()["count"] == 1
    assert [x for x in _ledger() if x.get("source") == "song_fee"][0]["delta"] == 200
    # 没有委托时 give cd 只是转交
    r = action(client, whale, "give", {"target": owner, "item": "cd"})
    assert r["success"] and "commission" not in r["result"] and inventory.count(p, "cd") == 0


def test_make_video_on_pc_and_daily_commission_refresh(client, v12, fake_clock, monkeypatch):
    monkeypatch.setitem(economy.cfg()["commissions"], "daily_p", 1.0)
    _at(fake_clock, 7, 50)
    achan = _agent(client, "achan")
    place(achan, 6, 31, "up")                                                             # pc_achan（pc_desk）
    assert action(client, achan, "use")["success"]
    r = action(client, achan, "make_video", {"title": "周报"})
    assert r["reason"] == "not_ready" and r["result"]["ready_in_min"] == 60
    fake_clock.advance(61 * 60); _tick(fake_clock, 1)
    r = action(client, achan, "make_video", {"title": "周报"})
    assert r["success"] and r["result"]["item"] == "script" and inventory.count(world_state._players[achan], "script") == 1
    # 每日 08:00 委托刷新：daily_p=1 → 出一单；同日不再出
    assert client.get("/commissions").json()["count"] == 1                               # 08:50 的 tick 已经出了一单
    cm = client.get("/commissions").json()["commissions"][0]
    assert cm["source"] == "daily" and cm["client"] in economy.cfg()["commissions"]["clients"] and 100 <= cm["fee"] <= 200     # v1.1 M-6
    from datetime import datetime as _dt
    assert (_dt.fromisoformat(cm["expires_at"]) - _dt.fromisoformat(cm["created_at"])).total_seconds() == 3 * 86400           # 3 天后过期
    _tick(fake_clock, 1)
    assert client.get("/commissions").json()["count"] == 1


# ── ② 直播收入 ──
def test_stream_income_formula_and_synthetic_on_leave(client, fake_self):
    whale = _agent(client, "whale")
    r = client.post("/admin/income", json={"entity_id": whale, "source": "stream", "viewers_total": 2000, "gifts_rmb": 7}).json()
    assert r["delta"] == 17 and r["synthetic"] is False and r["viewers_total"] == 2000               # v1.1 M-2：2000 × 0.005 + 7
    assert client.post("/admin/income", json={"entity_id": whale, "source": "stream", "viewers_avg": 400, "gifts": 3}).json()["delta"] == 5   # 旧字段同公式
    assert client.post("/admin/income", json={"entity_id": whale, "source": "tip"}).status_code == 400   # 没 amount
    place(whale, *STREAM_STAND)
    assert action(client, whale, "use")["success"]
    n0 = len(_ledger())
    assert action(client, whale, "leave")["success"]
    rows = _ledger()[n0:]
    assert len(rows) == 1 and rows[0]["source"] == "stream" and rows[0]["synthetic"] is True and 5 <= rows[0]["delta"] <= 35
    assert 1000 <= rows[0]["viewers_total"] <= 3000 and 0 <= rows[0]["gifts_rmb"] <= 20                 # v1.1：合成观众 1000–3000、礼物 0–20
    assert rows[0]["shop"] == STREAM_ID and world_state._players[whale]["gold"] == 3000 + 17 + 5 + rows[0]["delta"]
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
    assert shop["gift"]["stock"] == 0 and shop["bread"]["stock"] == 8
    _at(fake_clock, 8, 30); _tick(fake_clock, 1)                                          # 次日（这里直接拨到 08:30，另一天的 key）→ 补到水位
    assert counter["stock"]["gift"] == 3
    _at(fake_clock, 9, 0); _tick(fake_clock, 1)
    assert counter["stock"]["gift"] == 3                                                  # 同日只补一次（买走的不会再补）
    o = next(o for o in client.get("/world", params={"fields": "objects"}).json()["objects"] if o["id"] == "counter_grocer")
    assert o["stock"]["gift"] == 3 and {x["type"]: x for x in o["shop"]}["gift"]["stock"] == 3


def test_fridge_stock_empty_store_and_restock(client, fake_clock, monkeypatch):
    """world-v1.1：冰箱 = 存储（contents 按叠带保质期、容量 20、不自动补货）；use 只回内容；store / take 搬叠；检查点保留。"""
    from game import food
    _at(fake_clock, 7, 0)
    whale = _agent(client, "whale"); p = world_state._players[whale]
    fridge = world_state.get_object_by_id("fridge_kitchen")
    assert fridge["stock"] == {"home_meal": 4} and fridge["storage"] == {"capacity": 20, "used": 4}          # NPC / 测试图默认 4 份饭
    place(whale, fridge["position"]["x"], fridge["position"]["y"] + 1, "up")
    r = action(client, whale, "use")
    assert r["success"] and r["result"]["empty"] is False and r["result"]["contents"][0]["expires_in_days"] == 3 and fridge["stock"] == {"home_meal": 4}
    # take：拿 2 份出来，保质期跟着走
    r = action(client, whale, "take", {"item": "home_meal", "qty": 2})
    assert r["success"] and r["result"]["stock"] == {"home_meal": 2} and inventory.count(p, "home_meal") == 2
    assert p["inventory"][0]["expires_at"] == pytest.approx(fridge["contents"][0]["expires_at"], abs=1)
    assert action(client, whale, "take", {"item": "fish"})["reason"] == "not_in_storage"
    # store：食材 / 食物都能放；容量 20
    inventory.add(p, "ingredients", 20); inventory.add(p, "gift", 1)
    r = action(client, whale, "store", {"item": "ingredients", "qty": 6})
    assert r["success"] and r["result"]["stock"] == {"home_meal": 2, "ingredients": 6} and inventory.count(p, "ingredients") == 14
    r = action(client, whale, "store", {"item": "ingredients", "qty": 14})
    assert r["success"] and r["result"]["qty"] == 12 and r["result"]["storage"] == {"capacity": 20, "used": 20}   # 只放得下 12
    assert action(client, whale, "store", {"item": "ingredients", "qty": 1})["reason"] == "storage_full"
    assert action(client, whale, "store", {"item": "gift"})["reason"] == "not_storable"
    objs = {o["id"]: o for o in client.get("/world", params={"fields": "objects"}).json()["objects"]}
    assert {c["item"]: c["count"] for c in objs["fridge_kitchen"]["contents"]} == {"home_meal": 2, "ingredients": 18}
    assert all("expires_at" in c and c["expires_in_days"] in (3, 5) for c in objs["fridge_kitchen"]["contents"])
    # 不自动补货：08:00 过后不变
    _at(fake_clock, 8, 1); _tick(fake_clock, 1)
    assert fridge["stock"] == {"home_meal": 2, "ingredients": 18}
    # 检查点保留内容（含保质期）
    exp0 = fridge["contents"][0]["expires_at"]
    persistence.save_checkpoint(); world_state._reset_for_tests()
    assert world_state.get_object_by_id("fridge_kitchen")["stock"] == {"home_meal": 4}
    persistence.load_checkpoint()
    f2 = world_state.get_object_by_id("fridge_kitchen"); p = world_state._players[whale]      # 回填后是新的 dict
    assert f2["stock"] == {"home_meal": 2, "ingredients": 18} and f2["contents"][0]["expires_at"] == pytest.approx(exp0, abs=1)
    # 保鲜：饭菜 3 天（从 16:00 装进去起算）→ 4 天后已变坏食（背包里的 2 份也坏），食材 5 天还没到
    fake_clock.advance(4 * 86400); _tick(fake_clock, 1)
    assert f2["stock"] == {"spoiled_food": 2, "ingredients": 18} and inventory.count(p, "spoiled_food") == 2 and inventory.count(p, "home_meal") == 0
    assert action(client, whale, "discard", {"item": "spoiled_food", "qty": 2})["success"] and inventory.count(p, "spoiled_food") == 0


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
