"""X5 B 项：set_fridge / set_stock / force_closed / clear_closed；economy.json 按镇覆盖 + sha 回显；×6 一整个游戏日的补货 / 日薪 / 开关门触发。"""
import json
from datetime import datetime

from game import world_state, ticker, economy
from game.time_state import GAME_TZ
from tests.conftest import join, action, place, walk_done
from tests.test_w9_map_v2 import v12  # noqa: F401


import pytest


@pytest.fixture
def bench_env(monkeypatch):
    monkeypatch.setenv("SANDBOX_SCENARIO", "1")


def _agent(client, aid, name=None):
    return client.post("/player/join", json={"name": name or aid, "controller": "agent", "profile": {"agent_id": aid}}).json()["playerId"]


def _at(fake_clock, h, m=0):
    fake_clock.t = datetime(2026, 11, 10, h, m, tzinfo=GAME_TZ).timestamp()


def _run(client, steps):
    r = client.post("/admin/scenario", json={"steps": steps}); assert r.status_code == 200, r.text
    return r.json()


def test_set_fridge_set_stock_force_closed(client, v12, bench_env, fake_clock):
    _at(fake_clock, 12, 0)
    whale = _agent(client, "whale"); world_state._players[whale]["gold"] = 300
    r = _run(client, [{"op": "set_fridge", "id": "fridge_home", "qty": 0}, {"op": "set_stock", "shop": "counter", "item": "bread", "qty": 0}])
    assert r["ok"] and r["steps"][0]["detail"]["stock"] == {} and r["steps"][0]["detail"]["contents"] == [] and r["steps"][1]["detail"]["stock"]["bread"] == 0   # v1.1：不带 item = 整台清空
    place(whale, 5, 16, "up")
    r0 = action(client, whale, "use"); assert r0["success"] and r0["result"]["empty"] is True
    r = _run(client, [{"op": "set_fridge", "id": "fridge_home", "item": "home_meal", "qty": 3}])
    assert r["steps"][0]["detail"]["stock"] == {"home_meal": 3}
    place(whale, 27, 22, "right")
    assert action(client, whale, "buy", {"item": "bread"})["reason"] == "out_of_stock"
    assert next(o for o in client.get("/world", params={"fields": "objects"}).json()["objects"] if o["id"] == "counter")["stock"]["bread"] == 0
    assert _run(client, [{"op": "set_stock", "shop": "fridge_home", "item": "bread", "qty": 1}])["ok"] is False      # 冰箱不是商店
    # 强制关门：餐厅 12:00 本该开着 → 关到 17:00
    r = _run(client, [{"op": "force_closed", "object": "table_rest_1", "until": "17:00"}])
    assert r["ok"] and r["steps"][0]["detail"]["until"].endswith("17:00:00+08:00")
    place(whale, 34, 12, "up")
    res = action(client, whale, "use")
    assert res["reason"] == "closed" and res["result"]["opens_at"] == "17:00"
    assert next(o for o in client.get("/world", params={"fields": "objects"}).json()["objects"] if o["id"] == "table_rest_1")["open"] is False
    # 整个 arena / 门
    r = _run(client, [{"op": "force_closed", "arena": "dining", "until": None}])
    place(whale, 35, 18, "up")
    res = action(client, whale, "move", {"direction": "up"})
    assert res["reason"] == "no_path" and res["result"]["blocked_reason"] == "closed" and res["result"]["opens_at"] is None
    assert client.get("/admin/path", params={"from": "28,14", "to_arena": "dining", "mover": "whale"}).json()["reachable"] is False
    # 正在用的人被请出（下一 tick）
    _run(client, [{"op": "clear_closed"}])
    place(whale, 34, 12, "up"); assert action(client, whale, "use")["success"]
    _run(client, [{"op": "force_closed", "shop": "table_rest_1", "until": "17:00"}])
    ticker.tick_once(checkpoint=False); fake_clock.advance(1); ticker.tick_once(checkpoint=False)
    assert world_state._players[whale]["usingObjectId"] is None
    # 到点自动解除
    _at(fake_clock, 17, 1)
    assert world_state.open_state(world_state.get_object_by_id("table_rest_1"))[0] is True
    assert _run(client, [{"op": "force_closed", "object": "nope"}])["ok"] is False
    _run(client, [{"op": "reset"}])
    assert world_state._forced_closed == {}


def test_economy_path_override_and_sha(client, tmp_path, monkeypatch):
    base = economy.info()
    assert base["default"] is True and len(base["sha256"]) == 64 and client.get("/admin/metrics").json()["economy"]["sha256"] == base["sha256"]
    cfg = json.loads(economy.ECONOMY_PATH.read_text(encoding="utf-8"))
    cfg["fridge"]["initial"] = 3; cfg["initial_gold"]["whale"] = 999
    p = tmp_path / "economy_bench.json"; p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    try:
        inf = economy.reload(p)
        assert inf["default"] is False and inf["sha256"] != base["sha256"] and economy.cfg()["fridge"]["initial"] == 3
        assert economy.initial_gold("whale") == 999
        assert client.get("/admin/metrics").json()["economy"] == inf
    finally:
        economy.reload(economy._DEFAULT_PATH)
    assert economy.info()["sha256"] == base["sha256"]


def test_full_game_day_at_x6_triggers_restock_wages_and_hours(client, v12, fake_clock, monkeypatch):
    """模拟 ×6 速的一整个游戏日：每 tick 推 1.2 游戏秒（200 ms × 6）太慢，这里按 60 游戏秒一步、1440 步；检查 08:00 补货恰一次、
    日薪 / 时薪按点、餐厅 / 杂货店 open 在 11/14/17/21 与 09/20 切换。"""
    from game import food
    monkeypatch.setitem(economy.cfg()["fridge"], "restock_enabled", True)       # v1.1 默认不补货；这里验开关打开时的旧行为
    _at(fake_clock, 7, 0)
    achan = _agent(client, "achan"); xq = _agent(client, "claudine"); grocer = _agent(client, "npc_grocer")
    fridge = world_state.get_object_by_id("fridge_home"); counter = world_state.get_object_by_id("counter"); table = world_state.get_object_by_id("table_rest_1")
    fridge["contents"] = []; food.refresh_stock(fridge); counter["stock"]["bread"] = 4
    timeline = {}
    opens = []
    last = None
    for step in range(24 * 60):
        fake_clock.advance(60); ticker.tick_once(checkpoint=False)
        hm = datetime.fromtimestamp(fake_clock.t, GAME_TZ).strftime("%H:%M")
        state = (world_state.open_state(table)[0], world_state.open_state(counter)[0])
        if state != last:
            opens.append((hm, state)); last = state
        if hm in ("07:59", "08:00", "08:01", "09:00", "18:29", "18:31", "20:01", "06:59"):
            timeline[hm] = {"fridge": fridge["stock"].get("ingredients", 0), "bread": counter["stock"]["bread"],
                            "achan": world_state._players[achan]["gold"], "xq": world_state._players[xq]["gold"], "grocer": world_state._players[grocer]["gold"]}
    assert timeline["07:59"]["fridge"] == 0 and timeline["08:01"]["fridge"] == 2 and timeline["06:59"]["fridge"] == 2          # 08:00 +2，当日只一次
    assert timeline["07:59"]["bread"] == 4 and timeline["08:01"]["bread"] == 8                                               # v1.1：固定上新到 daily_supply
    assert timeline["18:29"]["achan"] == 3000 and timeline["18:31"]["achan"] == 3200 and timeline["06:59"]["achan"] == 3200     # 阿蝉 18:30 一次 200
    assert timeline["06:59"]["xq"] == 3000 + 48 and timeline["06:59"]["grocer"] == 3000 + 20 - 48                             # 克劳蒂娜 4 小时（店主付）、老板娘 22:00 日薪 20
    transitions = [(hm, s) for hm, s in opens]
    rest = [(hm, s[0]) for hm, s in transitions if last is not None]
    # 餐厅：11:00 开 14:00 关 17:00 开 21:00 关；杂货店 09:00 开 20:00 关（起点 07:00 两店都关）
    rest_changes = [(hm, s[0]) for i, (hm, s) in enumerate(transitions) if i == 0 or s[0] != transitions[i - 1][1][0]]
    groc_changes = [(hm, s[1]) for i, (hm, s) in enumerate(transitions) if i == 0 or s[1] != transitions[i - 1][1][1]]
    assert [x for x in rest_changes if x[0] != "07:01"] == [("11:00", True), ("14:00", False), ("17:00", True), ("21:00", False)], rest_changes
    assert [x for x in groc_changes if x[0] != "07:01"] == [("09:00", True), ("22:00", False)], groc_changes                # v1.1：杂货店到 22:00


def test_set_fridge_pins_todays_restock(client, v12, bench_env, fake_clock, monkeypatch):
    """X5 pilot ①（R1）：reset 清掉补货记录后 set_time 22:30 + set_fridge 0，下一 tick 的每日补货不得把 0 盖回 2；use 应得 empty 且饱腹不涨。"""
    r = _run(client, [{"op": "reset"}, {"op": "set_time", "time": "22:30"},
                      {"op": "spawn", "name": "鲸仔", "controller": "agent", "agent_id": "whale", "x": 5, "y": 16, "facing": "up", "vars": {"fullness": 17}},
                      {"op": "set_fridge", "id": "fridge_home", "qty": 0}])
    monkeypatch.setitem(economy.cfg()["fridge"], "restock_enabled", True)       # 开着补货才有「被盖掉」的风险
    assert r["ok"] and r["steps"][-1]["detail"]["stock"] == {} and r["steps"][-1]["detail"]["restock_pinned"]
    assert r["steps"][-1]["detail"]["restock_state"] == "pinned"
    # 今天已补过再 set_fridge：不再钉，但值同样保持
    r2 = _run(client, [{"op": "set_fridge", "id": "fridge_home", "qty": 0}])
    assert r2["steps"][-1]["detail"]["restock_pinned"] is None and r2["steps"][-1]["detail"]["restock_state"] == "already_restocked_today"
    whale = next(p["id"] for p in world_state._players.values() if p["name"] == "鲸仔")
    for _ in range(3):
        ticker.tick_once(checkpoint=False); fake_clock.advance(1)
    fridge = world_state.get_object_by_id("fridge_home")
    assert fridge["stock"] == {}
    res = action(client, whale, "use")
    assert res["success"] and res["result"]["empty"] is True
    assert world_state._players[whale]["fullness"] <= 17          # 没涨（自然衰减可忽略）
    # 次日 08:00 照常补货 +2
    from datetime import timedelta
    from game import time_state
    d1 = (time_state.game_now() + timedelta(days=1)).strftime("%Y-%m-%d"); d2 = (time_state.game_now() + timedelta(days=2)).strftime("%Y-%m-%d")
    _run(client, [{"op": "set_time", "date": d1, "time": "08:01"}]); fake_clock.advance(1); ticker.tick_once(checkpoint=False)
    assert fridge["stock"] == {"ingredients": 2}
    # 补货时刻之前 set_fridge 不钉：到点照常补
    r = _run(client, [{"op": "set_time", "date": d2, "time": "07:00"}, {"op": "set_fridge", "id": "fridge_home", "qty": 0}])
    assert r["steps"][-1]["detail"]["restock_pinned"] is None and r["steps"][-1]["detail"]["restock_state"] == "before_restock_at"
    _run(client, [{"op": "set_time", "date": d2, "time": "08:05"}]); fake_clock.advance(1); ticker.tick_once(checkpoint=False)
    assert fridge["stock"] == {"ingredients": 2}


def test_occupy_does_not_start_cooldown(client, v12, bench_env, fake_clock):
    """X5 pilot ②（R3）：夹具 occupy 不算一次 use——release / 自己离开后物品没有 30 分钟冷却，能立刻 use 回去续上。
    PC（直播台）在测试里没有自我层连不上 live，用同为默认冷却的 sofa_tv 验 use 路径，pc_whale 只验冷却值。"""
    _at(fake_clock, 14, 30)
    whale = _agent(client, "whale")
    r = _run(client, [{"op": "occupy", "player": whale, "object": "pc_whale"}])
    assert r["ok"] and world_state._players[whale]["usingObjectId"] == "pc_whale"
    assert world_state.object_cooldown_remaining(whale, "pc_whale") == 0
    fake_clock.advance(120)
    _run(client, [{"op": "release", "player": whale}])
    assert world_state._players[whale]["usingObjectId"] is None
    assert world_state.object_cooldown_remaining(whale, "pc_whale") == 0
    # 同一流程走 sofa_tv，释放后立刻 use 成功
    _run(client, [{"op": "occupy", "player": whale, "object": "sofa_tv"}])
    fake_clock.advance(300)
    _run(client, [{"op": "release", "player": whale}])
    assert world_state.object_cooldown_remaining(whale, "sofa_tv") == 0
    res = action(client, whale, "use")
    assert res["success"] is True, res
    assert world_state._players[whale]["usingObjectId"] == "sofa_tv"
    # v1.1 -b：沙发是娱乐类，占用语义无冷却（每日 180 分钟上限）；她自己 leave 后立刻可回
    action(client, whale, "leave")
    assert world_state.object_cooldown_remaining(whale, "sofa_tv") == 0
    assert action(client, whale, "use")["success"]
    action(client, whale, "leave")
    # occupy 不计入每日时长之外的冷却；再占一次 → release → 立刻可用
    _run(client, [{"op": "occupy", "player": whale, "object": "sofa_tv"}, {"op": "release", "player": whale}])
    assert world_state.object_cooldown_remaining(whale, "sofa_tv") == 0 and action(client, whale, "use")["success"]


def test_daily_limit_and_copy_key(client, v12, fake_clock):
    """world-v1.1 -b：每日使用时长上限（琴房电脑 240 min、04:00 重置、到点自动离开、daily_limit、/world?player= 与 GET /player.daily_use）；配钥匙（柜台 15 金币、仅门主）。"""
    from game import inventory, doors
    _at(fake_clock, 10, 0)
    whale = _agent(client, "whale"); grocer = _agent(client, "npc_grocer"); fisher = _agent(client, "npc_fisher")
    p = world_state._players[whale]
    place(whale, 24, 3, "up"); assert action(client, whale, "use")["success"]                 # pc_music
    assert client.get(f"/player/{whale}").json()["daily_use"]["pc_music"] == {"used_min": 0.0, "limit_min": 240.0}
    ticker.tick_once(checkpoint=False)                                                         # 基线
    fake_clock.advance(100 * 60); ticker.tick_once(checkpoint=False)
    assert client.get(f"/player/{whale}").json()["daily_use"]["pc_music"]["used_min"] == pytest.approx(100.0, abs=0.1)
    o = next(o for o in client.get("/world", params={"fields": "objects", "player": "whale"}).json()["objects"] if o["id"] == "pc_music")
    assert o["daily_limit_min"] == 240 and o["daily_used_min"] == pytest.approx(100.0, abs=0.1) and o["work"] is True
    assert next(o for o in client.get("/world", params={"fields": "objects"}).json()["objects"] if o["id"] == "pc_music")["daily_used_min"] is None
    action(client, whale, "leave"); assert action(client, whale, "use")["success"]            # 无冷却，可立刻回来续
    fake_clock.advance(150 * 60); ticker.tick_once(checkpoint=False)                            # 累计 250 > 240 → 自动离开
    assert p["usingObjectId"] is None and "用够了" in (client.get(f"/player/{whale}").json()["pendingMessage"] or "")
    r = action(client, whale, "use")
    assert r["success"] is False and r["reason"] == "daily_limit" and r["result"] == {"message": r["result"]["message"], "objectId": "pc_music", "resets_at": "04:00", "used_min": 240.0, "limit_min": 240.0}
    _at(fake_clock, 3, 59); fake_clock.t += 86400; ticker.tick_once(checkpoint=False)
    assert action(client, whale, "use")["reason"] == "daily_limit"                             # 次日 03:59 仍算昨天
    fake_clock.advance(120); ticker.tick_once(checkpoint=False)
    assert action(client, whale, "use")["success"]                                             # 04:01 重置
    action(client, whale, "leave")
    # 配钥匙：杂货店柜台（55,36 up）、鲸仔是合租房门主、15 金币进店主账户；渔夫不是门主
    _at(fake_clock, 10, 0); fake_clock.t += 86400
    place(whale, 27, 22, "right"); place(fisher, 27, 21, "down")
    assert action(client, whale, "copy_key", {"door_id": "door_fisher"})["reason"] == "not_owner"
    assert action(client, whale, "copy_key", {"door_id": "nope"})["reason"] == "unknown_door"
    g0 = p["gold"]; gg0 = world_state._players[grocer]["gold"]
    r = action(client, whale, "copy_key", {"door_id": "door_home"})
    assert r["success"] and r["result"]["price"] == 15 and p["gold"] == g0 - 15 and world_state._players[grocer]["gold"] == gg0 + 15
    assert inventory.count(p, "key") == 2 and len(doors.keys_of(p)) == 2
    place(whale, 3, 19, "up"); assert action(client, whale, "copy_key", {"door_id": "door_home"})["reason"] in ("no_object", "not_at_counter")
    _at(fake_clock, 23, 0); fake_clock.t += 86400; place(whale, 27, 22, "right")
    assert action(client, whale, "copy_key", {"door_id": "door_home"})["reason"] == "shop_closed"
    # 配出来的钥匙可 give：渔夫拿到就能开合租房门
    _at(fake_clock, 12, 0); fake_clock.t += 86400
    place(whale, 3, 19, "up"); place(fisher, 4, 19, "left")
    r = action(client, whale, "give", {"target": fisher, "item": "key", "door_id": "door_home"})
    assert r["success"] and doors.holds_key(world_state._players[fisher], "door_home") and doors.holds_key(p, "door_home")   # 自己那把还在


def test_set_gold_op_and_v11_fixture_preconditions(client, v12, bench_env, fake_clock):
    """world-v1.1 验收夹具：set_gold 写余额走流水；S11（冰箱空 + 杂货店卖完、餐厅开）与 S12（房租到期前钱不够）前置条件能摆出来。"""
    _at(fake_clock, 12, 10)
    r = _run(client, [{"op": "spawn", "name": "鲸仔", "controller": "agent", "agent_id": "whale", "x": 9, "y": 13, "facing": "up", "vars": {"fullness": 20}}])
    whale = next(p["id"] for p in world_state._players.values() if p["name"] == "鲸仔")
    r = _run(client, [{"op": "set_fridge", "id": "fridge_home", "qty": 0}, {"op": "set_stock", "shop": "counter", "item": "bread", "qty": 0},
                      {"op": "set_stock", "shop": "counter", "item": "ingredients", "qty": 0}, {"op": "set_supply", "shop": "counter", "item": "bread", "qty": 0},
                      {"op": "set_gold", "player": whale, "gold": 120}])
    assert r["ok"] and r["steps"][-1]["detail"] == {"player": whale, "gold": 120, "delta": -2880}
    objs = {o["id"]: o for o in client.get("/world", params={"fields": "objects"}).json()["objects"]}
    assert objs["fridge_home"]["contents"] == [] and objs["counter"]["stock"]["bread"] == 0 and objs["counter"]["daily_supply"]["bread"] == 0 and objs["counter"]["daily_supply"]["sweets"] == 6 and objs["table_rest_1"]["open"] is True
    # 08:00 补货按物品上的 daily_supply：面包今天不上、甜食补到 6
    _run(client, [{"op": "set_time", "date": "2026-11-11", "time": "08:01"}]); ticker.tick_once(checkpoint=False); fake_clock.advance(1); ticker.tick_once(checkpoint=False)
    counter = world_state.get_object_by_id("counter")
    assert counter["stock"]["bread"] == 0 and counter["stock"]["sweets"] == 6 and counter["stock"]["ingredients"] == 12
    _run(client, [{"op": "set_time", "date": "2026-11-10", "time": "12:10"}])
    p = client.get(f"/player/{whale}").json()
    assert p["gold"] == 120 and p["rent"]["amount"] == 300 and p["rent"]["balance"] == 120 and p["rent"]["overdue"] is False
    # 到期前 2 天：due_in_days ≤ 3；到期日不够 → 欠租
    _run(client, [{"op": "set_time", "date": "2026-11-29", "time": "08:05"}])
    assert client.get(f"/player/{whale}").json()["rent"]["due_in_days"] <= 3
    _run(client, [{"op": "set_time", "date": "2026-12-01", "time": "08:01"}]); ticker.tick_once(checkpoint=False); fake_clock.advance(1); ticker.tick_once(checkpoint=False)
    rv = client.get(f"/player/{whale}").json()["rent"]
    assert rv["overdue"] is True and rv["owed"] == 300 and world_state._players[whale]["gold"] == 120
    _run(client, [{"op": "reset"}])                                                            # reset 把 daily_supply 回配置（x7_reset「商店满货」依赖）
    assert world_state.get_object_by_id("counter")["daily_supply"]["bread"] == 8 and world_state.get_object_by_id("counter")["stock"]["bread"] == 8
