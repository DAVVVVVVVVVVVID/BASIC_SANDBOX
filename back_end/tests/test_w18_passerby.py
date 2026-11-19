"""商店第三期 · 路人顾客（world-v1.4.14；api-spec §12.32 / §12.35）。"""
from datetime import datetime

import pytest

from game import passerby, shops, world_state, ticker, fishing, food, inventory, persistence
from game.time_state import GAME_TZ
from tests.conftest import place
from tests.test_w9_map_v2 import _agent, v12  # noqa: F401


def _at(fake_clock, h, m=0):
    fake_clock.t = datetime(2026, 11, 20, h, m, tzinfo=GAME_TZ).timestamp()


def _tick(fake_clock, s=1.0):
    fake_clock.advance(s); ticker.tick_once(checkpoint=False)


def _run(fake_clock, pid, until, limit=4000, step=1.0):
    for _ in range(limit):
        _tick(fake_clock, step)
        if until():
            return True
    return False


def _spawn(purpose, x, y):
    with world_state.STATE_LOCK:
        return passerby.spawn(purpose, world_state.game_now_ts(), (x, y))


def test_grocery_buy_then_leave_and_despawn(client, v12, fake_clock):
    _at(fake_clock, 10)
    grocer = _agent(client, "npc_grocer"); place(grocer, 28, 21, "down")
    g0 = world_state._players[grocer]["gold"]
    counter = world_state.get_object_by_id("counter"); before = dict(counter["stock"])
    p = _spawn("grocery", 28, 26)
    pid = p["id"]
    assert pid.startswith("passerby_20261120_") and p["sprite"] in passerby.pcfg()["sprites"] and p["controller"] == "script" and p["role"] == "passerby"
    view = next(x for x in client.get("/world").json()["players"] if x["id"] == pid)
    assert view["sprite"] == p["sprite"] and view["role"] == "passerby"
    assert _run(fake_clock, pid, lambda: passerby._active.get(pid, {}).get("phase") == "leaving")
    sale = shops.ledger_view("grocery")["entries"][-1]
    assert sale["kind"] == "sale" and sale["who"] == pid and sum(before.values()) - sum(counter["stock"].values()) == sale["qty"]
    assert world_state._players[grocer]["gold"] == g0 + sale["amount"]
    assert _run(fake_clock, pid, lambda: pid not in world_state._players)            # 走回南门消失
    assert "passerby" not in str(client.get("/admin/metrics").json().get("accounts"))  # 不开经济账户


def test_closed_and_unattended_and_lost(client, v12, fake_clock):
    _at(fake_clock, 7)                                                                 # 杂货店 09:00 才开
    p = _spawn("grocery", 28, 26)
    assert _run(fake_clock, p["id"], lambda: passerby._active.get(p["id"], {}).get("phase") == "leaving")
    led = shops.ledger_view("grocery")["entries"][-1]
    assert led["kind"] == "lost" and led["ref"]["reason"] == "closed" and passerby._active[p["id"]]["result"] == "closed"


def test_fish_stall_buys_best_affordable(client, v12, fake_clock, monkeypatch):
    _at(fake_clock, 10)
    fisher = _agent(client, "npc_fisher")
    now = world_state.game_now_ts()
    cheap = fishing.new_fish("bleak", 1.0, "npc_fisher", now); dear = fishing.new_fish("golden_carp", 1.4, "npc_fisher", now)
    world_state.get_object_by_id("fish_stall")["listings"] = [cheap, dear]
    p = _spawn("fish_stall", 43, 3)
    p["gold"] = 70
    assert _run(fake_clock, p["id"], lambda: passerby._active.get(p["id"], {}).get("phase") == "leaving")
    left = world_state.get_object_by_id("fish_stall")["listings"]
    assert [m["fish_id"] for m in left] == [cheap["fish_id"]]                           # 预算内挑贵的（金鳞鲤 56）
    assert shops.ledger_view("fish_stall")["entries"][-1]["amount"] == 56


def test_restaurant_order_eat_leave(client, v12, fake_clock):
    _at(fake_clock, 12)
    owner = _agent(client, "npc_rest_owner"); place(owner, 40, 13, "up")
    food.store(world_state.get_object_by_id("fridge_rest"), "ingredients", 3, None)
    p = _spawn("restaurant", 34, 16)
    p["gold"] = 40
    pid = p["id"]
    assert _run(fake_clock, pid, lambda: passerby._active.get(pid, {}).get("phase") == "eating")
    assert shops.ledger_view("restaurant")["entries"][-1]["kind"] == "sale"
    assert _run(fake_clock, pid, lambda: passerby._active.get(pid, {}).get("phase") == "leaving", step=30)
    assert world_state._players[pid].get("usingObjectId") is None


def test_sprites_unique_names_unique_and_not_checkpointed(client, v12, fake_clock, tmp_path):
    _at(fake_clock, 10)
    ps = [_spawn("grocery", 20 + i, 30) for i in range(6)]
    assert len({p["sprite"] for p in ps}) == 6 and len({p["name"] for p in ps}) == 6
    assert _spawn("grocery", 27, 30)["sprite"] in passerby.pcfg()["sprites"]          # 第 7 个：6 套都在用也能分到
    db = tmp_path / "cp.sqlite"
    persistence.save_checkpoint(db)
    persistence.load_checkpoint(db)
    assert not [pid for pid in world_state._players if pid.startswith("passerby_")]
    w = _agent(client, "whale")
    q = _spawn("grocery", 26, 30)
    r = client.post("/chat/request", json={"from_entity_id": w, "to_entity_ids": [q["id"]], "greeting": "你好"}).json()
    assert r["success"] is False and r["reason"] == "passerby"


def test_schedule_only_when_enabled(client, v12, fake_clock, monkeypatch):
    _at(fake_clock, 7, 59)
    _tick(fake_clock, 1); _tick(fake_clock, 120)
    assert not passerby._active and passerby.view()["enabled"] is False
    monkeypatch.setenv("SANDBOX_PASSERSBY", "1")
    _at(fake_clock, 8, 0)
    assert _run(fake_clock, None, lambda: bool(passerby._active), limit=400, step=30)
    v = client.get("/admin/passersby").json()
    assert v["enabled"] and len(v["scheduled"]) >= 11 and v["active"]


def test_midday_start_skips_past_slots_and_staggers(client, v12, fake_clock, monkeypatch):
    """总控 11-19：主镇中途上线时，今天已过时段的路人不一下子全放进来。"""
    monkeypatch.setenv("SANDBOX_PASSERSBY", "1")
    _at(fake_clock, 15, 30)
    _tick(fake_clock, 1); _tick(fake_clock, 1)
    v = passerby.view()
    past = [i for i in passerby._sched["items"] if i["at_gts"] <= world_state.game_now_ts() - 2]
    assert past and all(i["done"] and i.get("skipped") for i in past) and len(passerby._active) == 0
    # 之后到点的照常一个一个来
    nxt = min(i["at_gts"] for i in passerby._sched["items"] if not i["done"])
    fake_clock.t = nxt + 1; ticker.tick_once(checkpoint=False)
    assert len(passerby._active) == 1
