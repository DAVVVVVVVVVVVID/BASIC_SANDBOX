"""钓鱼 + 鱼摊 v1（world-v1.4.8；whale docs/systems/fishing-system.md 主播 11-19 三段）。"""
import random
from datetime import datetime

import pytest

from game import fishing, inventory, world_state, ticker
from game.time_state import GAME_TZ
from tests.conftest import action, place
from tests.test_w9_map_v2 import _agent, v12  # noqa: F401

DAY = 86400.0


def _at(fake_clock, h, m=0, d=20):
    fake_clock.t = datetime(2026, 11, d, h, m, tzinfo=GAME_TZ).timestamp()


def _tick(fake_clock, s=1.0):
    fake_clock.advance(s); ticker.tick_once(checkpoint=False)


def _force(monkeypatch, who="default", **probs):
    oc = fishing.cfg()["outcome"][who]
    for k in ("empty", "junk", "fish"):
        monkeypatch.setitem(oc, k, float(probs.get(k, 0.0)))


def _fish_entries(p):
    return [e for e in inventory.ensure(p) if e.get("type") == "fish" and e.get("meta")]


def test_weight_distribution_and_tier_split():
    r = random.Random(7)
    ws = [fishing._weight(r) for _ in range(4000)]
    assert min(ws) >= 0.3 and max(ws) <= 3.0 and abs(sum(ws) / len(ws) - 1.2) < 0.03
    assert abs(sum(w > fishing.cfg()["weight"]["p90"] for w in ws) / len(ws) - 0.10) < 0.02      # P90 ≈ 1.713
    tiers = [fishing._pick(r, fishing.cfg()["tier_p"]["npc_fisher"]) for _ in range(20000)]
    assert abs(tiers.count("rare") / 20000 - 0.12) < 0.01 and 0.005 < tiers.count("legend") / 20000 < 0.016
    sp_by_tier = {}
    for k, v in fishing.cfg()["species"].items():
        sp_by_tier.setdefault(v["tier"], []).append(v["name"])
    assert len(sp_by_tier["common"]) == 4 and len(sp_by_tier["rare"]) == 3 and "星斑鳇" in sp_by_tier["legend"] and "老船长" not in str(fishing.cfg()["species"])


def test_cast_outcomes_rewards_and_fisher_rules(client, v12, fake_clock, monkeypatch):
    _at(fake_clock, 10)
    whale, fisher = _agent(client, "whale"), _agent(client, "npc_fisher")
    pw, pf = world_state._players[whale], world_state._players[fisher]
    now = world_state.game_now_ts()
    # 普通人：垃圾 → 物品 + 心情 −1
    _force(monkeypatch, junk=1.0); pw["mood"] = 50.0
    c = fishing.cast(pw, "fishing_spot_1", 1, now)
    assert c["result"] == "junk" and c["item"] in fishing.cfg()["junk"] and inventory.count(pw, c["item"]) == 1 and pw["mood"] == pytest.approx(49.0)
    # 老渔夫：没有垃圾；空竿 心情 −1、钓鱼时社交 +1/h（每竿 +1/3）
    _force(monkeypatch, "npc_fisher", empty=1.0); pf["mood"] = 50.0; pf["social"] = 40.0
    c = fishing.cast(pf, "fishing_spot_1", 2, now)
    assert c["result"] == "empty" and pf["mood"] == pytest.approx(49.0) and pf["social"] == pytest.approx(40.0 + 1 / 3, abs=1e-6)
    # 鱼：普通 +1；稀有 +4 心情 +5 乐趣；传说 +10/+10 + 兴奋 2h；超 P90 再 +3
    _force(monkeypatch, fish=1.0)
    for tier, mood, fun in (("common", 1, 0), ("rare", 4, 5), ("legend", 10, 10)):
        monkeypatch.setitem(fishing.cfg()["tier_p"], "default", {"common": 0, "rare": 0, "legend": 0, tier: 1.0})
        monkeypatch.setattr(fishing, "_weight", lambda r: 1.0)
        fishing._records.clear(); fishing._records["whale"] = {"best": {"species": "crucian", "name": "鲫鱼", "weight": 9.0, "at": None}, "by_species": {}}
        pw["mood"] = 50.0; pw["fun"] = 50.0; pw["emotion_tags"] = []
        c = fishing.cast(pw, "fishing_spot_1", 3, now)
        assert c["result"] == "fish" and c["fish"]["tier"] == tier and c["big"] is False and c["record_break"] is False
        assert pw["mood"] == pytest.approx(50 + mood) and pw["fun"] == pytest.approx(50 + fun)
        assert any(t.get("key") == "excited" for t in pw["emotion_tags"]) == (tier == "legend")
    monkeypatch.setattr(fishing, "_weight", lambda r: 2.0)
    monkeypatch.setitem(fishing.cfg()["tier_p"], "default", {"common": 1.0, "rare": 0, "legend": 0})
    pw["mood"] = 50.0
    c = fishing.cast(pw, "fishing_spot_1", 4, now)
    assert c["big"] is True and pw["mood"] == pytest.approx(50 + 1 + 3)
    # 每日上限：老渔夫 10 h，其他人 3 h
    assert world_state.daily_limit_s("fishing_spot", fisher) == 600 * 60 and world_state.daily_limit_s("fishing_spot", whale) == 180 * 60
    v = client.get(f"/player/{whale}").json()["fishing"]
    assert v["casts_today"] == 5 and v["last_cast"]["cast_no"] == c["cast_no"] and len(v["recent_casts"]) == 5


def test_records_initial_table_and_break(client, v12, fake_clock, monkeypatch):
    _at(fake_clock, 10)
    fisher, achan = _agent(client, "npc_fisher"), client.post("/player/join", json={"name": "阿蝉", "controller": "human", "profile": {"agent_id": "achan"}}).json()["playerId"]
    pf = world_state._players[fisher]
    rec = client.get(f"/player/{fisher}").json()["fishing"]["record"]
    assert rec["best"]["name"] == "金鳞鲤" and rec["best"]["weight"] == 2.2 and rec["by_species"] == {"golden_carp": 2.2}
    assert client.get(f"/player/{achan}").json()["fishing"]["record"]["best"] is None
    _force(monkeypatch, "npc_fisher", fish=1.0)
    monkeypatch.setitem(fishing.cfg()["tier_p"], "npc_fisher", {"common": 1.0, "rare": 0, "legend": 0})
    monkeypatch.setattr(fishing, "_weight", lambda r: 2.0)
    c = fishing.cast(pf, "fishing_spot_1", 1, world_state.game_now_ts())
    assert c["record_break"] is False and c["species_record"] is True                      # 2.0 < 2.2 总纪录不破，鱼种纪录新
    monkeypatch.setattr(fishing, "_weight", lambda r: 2.6)
    pf["mood"] = 50.0; pf["emotion_tags"] = []
    c = fishing.cast(pf, "fishing_spot_1", 2, world_state.game_now_ts())
    assert c["record_break"] is True and c["record"]["old"]["weight"] == 2.2 and c["record"]["new"]["weight"] == 2.6
    assert pf["mood"] == pytest.approx(50 + 1 + 3 + 8) and any(t.get("key") == "excited" for t in pf["emotion_tags"])
    assert "破纪录" in world_state._pending_messages[fisher]
    # 检查点往返
    st = fishing.export_state(); fishing.import_state(st)
    assert fishing.record_of(pf)["best"]["weight"] == 2.6


def test_freshness_fridge_half_speed_eat_and_cook(client, v12, fake_clock, monkeypatch):
    _at(fake_clock, 10)
    fisher = _agent(client, "npc_fisher"); pf = world_state._players[fisher]
    now = world_state.game_now_ts()
    a = fishing.new_fish("small_bass", 1.2, "npc_fisher", now); b = fishing.new_fish("eel", 1.2, "npc_fisher", now)
    inventory.add(pf, "fish", 1, meta=a); inventory.add(pf, "fish", 1, meta=b)
    # 冰箱：放 b 进去
    place(fisher, 40, 3, "up")
    r = action(client, fisher, "store", {"item": "fish", "fish_id": b["fish_id"], "object_id": "fridge_fisher"})
    assert r["success"] and r["result"]["contents"][-1]["meta"]["species"] == "eel"
    _tick(fake_clock, 4 * DAY)                                                              # 4 日：常温 → 不新鲜；冰箱里只走 2 日 → 仍新鲜
    fishing.refresh(world_state.game_now_ts(), world_state._players, world_state._OBJECTS, force=True)
    fa = _fish_entries(pf)[0]["meta"]; fb = next(c for c in world_state.get_object_by_id("fridge_fisher")["contents"] if c.get("meta"))["meta"]
    assert fa["freshness"] == "stale" and fb["freshness"] == "fresh" and fb["age_days"] == pytest.approx(2.0, abs=0.05)
    r = action(client, fisher, "take", {"item": "fish", "fish_id": b["fish_id"], "object_id": "fridge_fisher"})
    assert r["success"] and len(_fish_entries(pf)) == 2
    # 吃：黄鳝不能生吃；不新鲜的小鲈鱼生吃按 50% 掷坏肚子
    place(fisher, 38, 5, "up"); assert action(client, fisher, "use")["success"]
    r = action(client, fisher, "eat", {"item": "fish", "fish_id": b["fish_id"]})
    assert r["reason"] == "cannot_eat_raw" and "鳝丝面" in r["result"]["message"]
    monkeypatch.setitem(fishing.cfg()["freshness"], "stale_raw_sick_p", 1.0)
    pf["energy"] = 60.0
    r = action(client, fisher, "eat", {"item": "fish", "fish_id": a["fish_id"]})
    assert r["success"] and r["result"]["sick"] is True and pf["energy"] == pytest.approx(50.0, abs=0.01) and r["result"]["gain"] == {"fullness": 8.0}
    action(client, fisher, "leave")
    # 料理：黄鳝 → 鳝丝面（新鲜），效果按重量；1 日保质
    place(fisher, 38, 3, "up"); assert action(client, fisher, "use", {"item": "fish", "fish_id": b["fish_id"]})["success"]
    _tick(fake_clock, 21 * 60)
    dish = next(e for e in inventory.ensure(pf) if e["type"] == "fish_dish")
    assert dish["meta"]["name"] == "鳝丝面（新鲜）" and dish["expires_at"] - world_state.game_now_ts() <= DAY
    assert fishing.dish_plan(dish)["gain"] == {"fullness": 32.0, "energy": 5.0}
    stale = fishing.dish_meta({**fishing.new_fish("crucian", 2.4, "x", now), "age_s": 4 * DAY}, now)
    assert stale["name"] == "鲫鱼汤（不新鲜）" and fishing.dish_plan({"meta": stale})["gain"] == {"fullness": pytest.approx(25 * 2 * 0.7), "mood": pytest.approx(3 * 2 * 0.7)}


def test_stall_listing_buy_spoil_return_and_exchange(client, v12, fake_clock, monkeypatch):
    _at(fake_clock, 10)
    fisher, whale = _agent(client, "npc_fisher"), _agent(client, "whale")
    pf, pw = world_state._players[fisher], world_state._players[whale]
    now = world_state.game_now_ts()
    f1 = fishing.new_fish("golden_carp", 1.5, "npc_fisher", now); f2 = fishing.new_fish("crucian", 1.0, "npc_fisher", now)
    inventory.add(pf, "fish", 1, meta=f1); inventory.add(pf, "fish", 1, meta=f2)
    # 不再每日刷鱼
    assert not client.get("/world").json()["objects"] or next(o for o in client.get("/world").json()["objects"] if o["id"] == "fish_stall")["listings"] == []
    place(fisher, 42, 2, "up")
    g0 = pf["gold"]
    r = action(client, fisher, "sell", {"item": "fish"})                                    # 老渔夫在自家摊 = 上货
    assert r["success"] and len(r["result"]["listed"]) == 2 and pf["gold"] == g0 and _fish_entries(pf) == []
    ls = {l["listing_id"]: l for l in next(o for o in client.get("/world").json()["objects"] if o["id"] == "fish_stall")["listings"]}
    assert ls[f1["fish_id"]]["price"] == round(40 * 1.5) and ls[f2["fish_id"]]["price"] == 12
    place(whale, 41, 1, "right")
    r = action(client, whale, "buy", {"item": "fish", "listing_id": f1["fish_id"], "object_id": "fish_stall"})
    assert r["success"] and r["result"]["total"] == 60 and pw["gold"] == 3000 - 60 and pf["gold"] == g0 + 60
    assert _fish_entries(pw)[0]["meta"]["fish_id"] == f1["fish_id"]
    # 摊上剩的鲫鱼放到变质 → 自动下架退回老渔夫背包
    _tick(fake_clock, 6.1 * DAY)
    fishing.refresh(world_state.game_now_ts(), world_state._players, world_state._OBJECTS, force=True)
    stall = world_state.get_object_by_id("fish_stall")
    assert stall["listings"] == [] and _fish_entries(pf)[0]["meta"]["freshness"] == "spoiled" and "变质" in world_state._pending_messages[fisher]
    # 变质不能卖；杂货店换鱼饵
    place(fisher, 42, 2, "up")
    assert action(client, fisher, "sell", {"item": "fish", "fish_id": f2["fish_id"]})["reason"] == "spoiled"
    place(fisher, 28, 23, "up")
    _at(fake_clock, 10, d=27)
    r = action(client, fisher, "exchange", {"item": "fish"})
    assert r["success"] and inventory.count(pf, "bait") == 1 and _fish_entries(pf) == []
    inventory.add(pf, "junk_boot", 1)
    assert action(client, fisher, "exchange", {"item": "junk_boot"})["success"] and inventory.count(pf, "bait") == 2


def test_use_stall_shows_listings(client, v12, fake_clock):
    _at(fake_clock, 10)
    fisher, whale = _agent(client, "npc_fisher"), _agent(client, "whale")
    m = fishing.new_fish("bleak", 1.1, "npc_fisher", world_state.game_now_ts())
    world_state.get_object_by_id("fish_stall")["listings"] = [m]
    place(whale, 42, 2, "up")
    r = action(client, whale, "use")
    assert r["success"] and r["result"]["listings"][0]["listing_id"] == m["fish_id"] and "白条 1.10 kg" in r["result"]["message"]
    pv = client.get("/agent/perceive", params={"entity_id": whale}).json()
    assert pv["fishing"]["record"]["best"]["name"] == "鲫鱼" and pv["fishing"]["casts_today"] == 0


def test_scenario_set_fishing_record(client, v12, fake_clock, monkeypatch):
    monkeypatch.setenv("SANDBOX_SCENARIO", "1")
    _at(fake_clock, 10)
    fisher = _agent(client, "npc_fisher")
    r = client.post("/admin/scenario", json={"steps": [{"op": "set_fishing_record", "player": fisher, "weight": 1.0}]}).json()
    assert r["ok"] and r["steps"][0]["detail"]["record"]["best"]["weight"] == 1.0 and r["steps"][0]["detail"]["record"]["best"]["name"] == "金鳞鲤"
    _force(monkeypatch, "npc_fisher", fish=1.0)
    monkeypatch.setattr(fishing, "_weight", lambda r: 1.3)
    assert fishing.cast(world_state._players[fisher], "fishing_spot_1", 1, world_state.game_now_ts())["record_break"] is True
    r = client.post("/admin/scenario", json={"steps": [{"op": "set_fishing_record", "player": fisher, "clear": True}]}).json()
    assert r["steps"][0]["detail"]["record"]["best"]["weight"] == 2.2


def test_occupy_spot_still_casts_v1410(client, v12, fake_clock, monkeypatch):
    """C 11-19：scenario occupy 坐上钓位不走 on_enter，以前一竿都不出；现在 tick 补登记。"""
    monkeypatch.setenv("SANDBOX_SCENARIO", "1")
    _at(fake_clock, 7)
    fisher = _agent(client, "npc_fisher")
    _force(monkeypatch, "npc_fisher", fish=1.0)
    r = client.post("/admin/scenario", json={"steps": [{"op": "occupy", "player": fisher, "object": "fishing_spot_1"}]}).json()
    assert r["ok"]
    _tick(fake_clock, 1); _tick(fake_clock, 1)                  # ticker 第一下只立锚点；第二下 production.on_tick 补登记
    _tick(fake_clock, 20 * 60)
    _tick(fake_clock, 20 * 60)
    v = client.get("/agent/perceive", params={"entity_id": fisher}).json()["fishing"]
    assert v["casts_today"] == 2 and v["spot"] == "fishing_spot_1" and len(_fish_entries(world_state._players[fisher])) == 2
