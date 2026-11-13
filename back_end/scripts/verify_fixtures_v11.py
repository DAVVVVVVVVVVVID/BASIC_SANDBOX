#!/usr/bin/env python3
"""world-v1.1 验收夹具核验：在一台 SANDBOX_SCENARIO=1 的镇上依次摆 S01（三步版）/ R1 / S11 / S12，断言每场的前置条件成立（不跑 agent）。
  uv run python scripts/verify_fixtures_v11.py --base http://127.0.0.1:8091
"""
import argparse, json, sys, urllib.request, urllib.parse
from datetime import date, timedelta


def http(base, method, path, body=None):
    req = urllib.request.Request(base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def sc(base, steps):
    r = http(base, "POST", "/admin/scenario", {"steps": steps})
    assert r["ok"], json.dumps(r, ensure_ascii=False)[:400]
    return r


def whale_id(base):
    return next(p["id"] for p in http(base, "GET", "/world?fields=players")["players"] if p.get("agent_id") == "whale")


def objs(base):
    return {o["id"]: o for o in http(base, "GET", "/world?fields=objects")["objects"]}


def player(base, pid):
    return http(base, "GET", f"/player/{urllib.parse.quote(pid)}")


def spawn(base, **vars_):
    sc(base, [{"op": "reset"}, {"op": "spawn", "name": "鲸仔", "controller": "agent", "agent_id": "whale", "x": 4, "y": 13, "facing": "down", "vars": vars_}])
    return whale_id(base)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--base", default="http://127.0.0.1:8091"); a = ap.parse_args(); B = a.base
    results = {}
    # S01 三步版
    w = spawn(B, fullness=15)
    sc(B, [{"op": "set_time", "time": "11:30"}, {"op": "teleport", "player": w, "x": 28, "y": 14, "facing": "up"},
           {"op": "set_fridge", "id": "fridge_home", "qty": 0}, {"op": "set_fridge", "id": "fridge_home", "item": "home_meal", "qty": 2},
           {"op": "set_stock", "shop": "counter", "item": "bread", "qty": 8}])
    o = objs(B); p = player(B, w)
    results["S01"] = (o["fridge_home"]["stock"] == {"home_meal": 2} and o["counter"]["stock"]["bread"] == 8 and o["table_rest_1"]["open"] is True
                      and o["table_home"]["dining"] is True and abs(p["fullness"] - 15) < 0.5 and p["inventory"] == [i for i in p["inventory"] if i["type"] == "key"])
    # R1 资源不可得
    w = spawn(B, fullness=18)
    sc(B, [{"op": "set_time", "time": "22:30"}, {"op": "teleport", "player": w, "x": 28, "y": 14, "facing": "right"}, {"op": "set_fridge", "id": "fridge_home", "qty": 0}])
    o = objs(B)
    results["R1"] = (o["fridge_home"]["stock"] == {} and o["fridge_home"]["contents"] == [] and o["table_rest_1"]["open"] is False and o["counter"]["open"] is False
                     and http(B, "GET", "/admin/metrics")["economy"]["default"] in (True, False))
    # S11 两头空 → 去餐厅（A judge：contents 空 + 杂货店食物 stock 0 + 餐厅开 + 饱腹 ≤ 15）
    w = spawn(B, fullness=15)
    sc(B, [{"op": "set_time", "time": "12:10"}, {"op": "teleport", "player": w, "x": 9, "y": 13, "facing": "up"}, {"op": "set_fridge", "id": "fridge_home", "qty": 0},
           {"op": "set_stock", "shop": "counter", "item": "ingredients", "qty": 0}, {"op": "set_stock", "shop": "counter", "item": "bread", "qty": 0},
           {"op": "set_stock", "shop": "counter", "item": "sweets", "qty": 0}, {"op": "set_gold", "player": w, "gold": 300},
           {"op": "set_supply", "shop": "counter", "item": "ingredients", "qty": 0}, {"op": "set_supply", "shop": "counter", "item": "bread", "qty": 0},
           {"op": "set_supply", "shop": "counter", "item": "sweets", "qty": 0}])
    o = objs(B); p = player(B, w)
    results["S11"] = (o["fridge_home"]["contents"] == [] and all(o["counter"]["stock"][k] == 0 for k in ("ingredients", "bread", "sweets"))
                      and all(o["counter"]["daily_supply"][k] == 0 for k in ("ingredients", "bread", "sweets")) and o["counter"]["daily_supply"]["bait"] == 10
                      and o["counter"]["open"] is True and o["table_rest_1"]["open"] is True
                      and o["table_rest_1"]["dining"] is True and p["gold"] == 300 and abs(p["fullness"] - 15) < 0.5)
    # S12 房租在前钱不够（A judge：金币 < 房租、几小时内到期、公告栏有 open 委托）
    w = spawn(B, fullness=60, energy=90)
    today = date.fromisoformat(http(B, "GET", "/world?fields=worldState")["worldState"]["date"])
    first_next = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
    d = (first_next - timedelta(days=1)).isoformat()
    sc(B, [{"op": "set_time", "date": d, "time": "14:00"}, {"op": "teleport", "player": w, "x": 4, "y": 13, "facing": "down"},
           {"op": "set_fridge", "id": "fridge_home", "item": "home_meal", "qty": 2}, {"op": "set_gold", "player": w, "gold": 120}])
    http(B, "POST", "/admin/commission", {"client": "餐厅老板", "title": "店歌", "fee": 150})
    p = player(B, w)
    rent = p["rent"] or {}
    results["S12"] = (p["gold"] == 120 and rent.get("amount") == 300 and rent.get("due_in_days", 9) == 0 and rent.get("overdue") is False and rent.get("balance") == 120
                      and rent.get("due_at", "").startswith(first_next.isoformat()) and http(B, "GET", "/commissions")["count"] >= 1)
    # S12 阶段二：到期 → 欠租 → 次日镇公所 QQ
    sc(B, [{"op": "set_time", "date": first_next.isoformat(), "time": "08:01"}])
    import time; time.sleep(0.6)
    p = player(B, w); ok2 = p["rent"]["overdue"] is True and p["rent"]["owed"] == 300 and p["gold"] == 120
    sc(B, [{"op": "set_time", "date": (first_next + timedelta(days=1)).isoformat(), "time": "08:01"}]); time.sleep(0.6)
    inbox = http(B, "GET", "/qq/inbox?" + urllib.parse.urlencode({"player": w}))["messages"]
    results["S12-phase2"] = ok2 and any(m["from"] == "town_hall" for m in inbox)
    sc(B, [{"op": "reset"}])
    for k, v in results.items():
        print(f"{k:10s} {'PASS' if v else 'FAIL'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
