"""X5 B 项：set_fridge / set_stock / force_closed / clear_closed；economy.json 按镇覆盖 + sha 回显；×6 一整个游戏日的补货 / 日薪 / 开关门触发。"""
import json
from datetime import datetime

from game import world_state, ticker, economy
from game.time_state import GAME_TZ
from tests.conftest import join, action, place, walk_done
from tests.test_w9_map_v2 import v1  # noqa: F401


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


def test_set_fridge_set_stock_force_closed(client, v1, bench_env, fake_clock):
    _at(fake_clock, 12, 0)
    whale = _agent(client, "whale"); world_state._players[whale]["gold"] = 300
    r = _run(client, [{"op": "set_fridge", "id": "fridge_home", "qty": 0}, {"op": "set_stock", "shop": "counter", "item": "bread", "qty": 0}])
    assert r["ok"] and r["steps"][0]["detail"]["stock"] == {"ingredients": 0} and r["steps"][1]["detail"]["stock"]["bread"] == 0
    place(whale, 3, 30, "up")
    assert action(client, whale, "use")["reason"] == "empty"
    place(whale, 55, 36, "up")
    assert action(client, whale, "buy", {"item": "bread"})["reason"] == "out_of_stock"
    assert next(o for o in client.get("/world", params={"fields": "objects"}).json()["objects"] if o["id"] == "counter")["stock"]["bread"] == 0
    assert _run(client, [{"op": "set_stock", "shop": "fridge_home", "item": "bread", "qty": 1}])["ok"] is False      # 冰箱不是商店
    # 强制关门：餐厅 12:00 本该开着 → 关到 17:00
    r = _run(client, [{"op": "force_closed", "object": "table_rest_1", "until": "17:00"}])
    assert r["ok"] and r["steps"][0]["detail"]["until"].endswith("17:00:00+08:00")
    place(whale, 48, 24, "up")
    res = action(client, whale, "use")
    assert res["reason"] == "closed" and res["result"]["opens_at"] == "17:00"
    assert next(o for o in client.get("/world", params={"fields": "objects"}).json()["objects"] if o["id"] == "table_rest_1")["open"] is False
    # 整个 arena / 门
    r = _run(client, [{"op": "force_closed", "arena": "dining", "until": None}])
    place(whale, 51, 31, "up")
    res = action(client, whale, "move", {"direction": "up"})
    assert res["reason"] == "no_path" and res["result"]["blocked_reason"] == "closed" and res["result"]["opens_at"] is None
    assert client.get("/admin/path", params={"from": "41,26", "to_arena": "dining", "mover": "whale"}).json()["reachable"] is False
    # 正在用的人被请出（下一 tick）
    _run(client, [{"op": "clear_closed"}])
    place(whale, 48, 24, "up"); assert action(client, whale, "use")["success"]
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


def test_full_game_day_at_x6_triggers_restock_wages_and_hours(client, v1, fake_clock):
    """模拟 ×6 速的一整个游戏日：每 tick 推 1.2 游戏秒（200 ms × 6）太慢，这里按 60 游戏秒一步、1440 步；检查 08:00 补货恰一次、
    日薪 / 时薪按点、餐厅 / 杂货店 open 在 11/14/17/21 与 09/20 切换。"""
    _at(fake_clock, 7, 0)
    achan = _agent(client, "achan"); xq = _agent(client, "npc_xiaoqian"); grocer = _agent(client, "npc_grocer")
    fridge = world_state.get_object_by_id("fridge_home"); counter = world_state.get_object_by_id("counter"); table = world_state.get_object_by_id("table_rest_1")
    fridge["stock"]["ingredients"] = 0; counter["stock"]["bread"] = 4
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
            timeline[hm] = {"fridge": fridge["stock"]["ingredients"], "bread": counter["stock"]["bread"],
                            "achan": world_state._players[achan]["gold"], "xq": world_state._players[xq]["gold"], "grocer": world_state._players[grocer]["gold"]}
    assert timeline["07:59"]["fridge"] == 0 and timeline["08:01"]["fridge"] == 2 and timeline["06:59"]["fridge"] == 2          # 08:00 +2，当日只一次
    assert timeline["07:59"]["bread"] == 4 and timeline["08:01"]["bread"] == 10                                              # 商店补到水位
    assert timeline["18:29"]["achan"] == 2000 and timeline["18:31"]["achan"] == 2150 and timeline["06:59"]["achan"] == 2150     # 阿蝉 18:30 一次
    assert timeline["06:59"]["xq"] == 400 + 48 and timeline["06:59"]["grocer"] == 3100                                        # 小千 4 小时、老板娘 20:00
    transitions = [(hm, s) for hm, s in opens]
    rest = [(hm, s[0]) for hm, s in transitions if last is not None]
    # 餐厅：11:00 开 14:00 关 17:00 开 21:00 关；杂货店 09:00 开 20:00 关（起点 07:00 两店都关）
    rest_changes = [(hm, s[0]) for i, (hm, s) in enumerate(transitions) if i == 0 or s[0] != transitions[i - 1][1][0]]
    groc_changes = [(hm, s[1]) for i, (hm, s) in enumerate(transitions) if i == 0 or s[1] != transitions[i - 1][1][1]]
    assert [x for x in rest_changes if x[0] != "07:01"] == [("11:00", True), ("14:00", False), ("17:00", True), ("21:00", False)], rest_changes
    assert [x for x in groc_changes if x[0] != "07:01"] == [("09:00", True), ("20:00", False)], groc_changes
