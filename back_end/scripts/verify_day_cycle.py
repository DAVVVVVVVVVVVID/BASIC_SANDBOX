#!/usr/bin/env python3
"""
X5 ③ 日驱动核验：对一个 bench 实例（SANDBOX_SCENARIO=1）把倍速拉到 --speed，从 07:50 跑满一个游戏日，记录
08:00 冰箱 / 商店补货、日薪时薪结算、餐厅 / 杂货店 open 切换的实际触发时刻，出一张表并 PASS/FAIL。跑完恢复倍速、删掉测试玩家。

  cd back_end && uv run python scripts/verify_day_cycle.py --base http://127.0.0.1:8091 [--speed 600]
"""
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request


def http(base, m, p, b=None):
    r = urllib.request.Request(base + p, data=json.dumps(b).encode() if b is not None else None, method=m, headers={"content-type": "application/json"})
    with urllib.request.urlopen(r, timeout=10) as x:
        return json.loads(x.read())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8091")
    ap.add_argument("--speed", type=float, default=600.0, help="倍速；600 → 一个游戏日 144 s 墙钟")
    ap.add_argument("--poll", type=float, default=0.15)
    a = ap.parse_args()
    B = a.base
    old_speed = http(B, "GET", "/world?fields=worldState")["worldState"]["speed"]
    ids = {}
    for aid, name in (("achan", "阿蝉"), ("npc_xiaoqian", "小千"), ("npc_grocer", "杂货店老板娘"), ("npc_rest_owner", "餐厅老板"), ("npc_fisher", "老渔夫")):
        ids[aid] = http(B, "POST", "/player/join", {"name": name, "controller": "agent", "profile": {"agent_id": aid}})["playerId"]
    from datetime import date, timedelta
    tomorrow = (date.fromisoformat(http(B, "GET", "/world?fields=worldState")["worldState"]["date"]) + timedelta(days=1)).isoformat()
    http(B, "POST", "/admin/scenario", {"steps": [{"op": "set_time", "time": "07:50", "date": tomorrow},           # 明天：补货 / 日薪的日键一定是新的
                                                   {"op": "set_fridge", "id": "fridge_home", "qty": 0},
                                                   {"op": "set_stock", "shop": "counter", "item": "bread", "qty": 3}]})
    gold0 = {aid: http(B, "GET", f"/player/{urllib.parse.quote(pid)}")["gold"] for aid, pid in ids.items()}
    pid2aid = {pid: aid for aid, pid in ids.items()}
    http(B, "POST", "/time/speed", {"value": a.speed})
    events = []; last = {}
    t0 = time.time(); seen_day_end = False; start_date = None
    try:
        while time.time() - t0 < (24 * 3600 / a.speed) + 20:
            w = http(B, "GET", "/world?fields=worldState,objects,players")
            ws_ = w["worldState"]; hm = ws_["time"][:5]
            if start_date is None:
                start_date = ws_["date"]
            objs = {o["id"]: o for o in w["objects"]}
            snap = {"fridge": objs["fridge_home"]["stock"]["ingredients"], "bread": objs["counter"]["stock"]["bread"],
                    "rest_open": objs["table_rest_1"]["open"], "groc_open": objs["counter"]["open"]}
            for p in w["players"]:
                if p["id"] in pid2aid:
                    snap[f"gold:{pid2aid[p['id']]}"] = p["gold"]
            for k, v in snap.items():
                if last.get(k) != v:
                    if k in last:
                        events.append((ws_["date"], hm, k, last[k], v))
                    last[k] = v
            if ws_["date"] != start_date and hm >= "07:50":
                seen_day_end = True; break
            time.sleep(a.poll)
    finally:
        http(B, "POST", "/time/speed", {"value": old_speed})
        for pid in ids.values():
            try:
                urllib.request.urlopen(urllib.request.Request(B + f"/player/{urllib.parse.quote(pid)}/leave", method="DELETE")).read()
            except Exception:
                pass
    print(f"| 游戏日 | 时刻 | 项 | 之前 | 之后 |\n|---|---|---|---|---|")
    for d, hm, k, a_, b_ in events:
        print(f"| {d} | {hm} | {k} | {a_} | {b_} |")
    def at(k, want, lo, hi):
        hits = [hm for _, hm, kk, _, v in events if kk == k and v == want and lo <= hm <= hi]
        return hits[0] if hits else None
    checks = {
        "08:00 冰箱 +2": at("fridge", 2, "08:00", "08:08"),
        "08:00 商店补到水位": at("bread", 10, "08:00", "08:08"),
        "09:00 杂货店开": at("groc_open", True, "09:00", "09:08"), "20:00 杂货店关": at("groc_open", False, "20:00", "20:08"),
        "11:00 餐厅开": at("rest_open", True, "11:00", "11:08"), "14:00 餐厅关": at("rest_open", False, "14:00", "14:08"),
        "17:00 餐厅开": at("rest_open", True, "17:00", "17:08"), "21:00 餐厅关": at("rest_open", False, "21:00", "21:08"),
        "18:30 阿蝉日薪": at("gold:achan", gold0["achan"] + 150, "18:30", "18:38"),
        "20:00 老板娘日薪": at("gold:npc_grocer", gold0["npc_grocer"] + 100, "20:00", "20:08"),
        "21:00 餐厅老板日薪": at("gold:npc_rest_owner", gold0["npc_rest_owner"] + 100, "21:00", "21:08"),
        "17:00 渔夫日薪": at("gold:npc_fisher", gold0["npc_fisher"] + 80, "17:00", "17:08"),
        "小千 4 次时薪": (last.get("gold:npc_xiaoqian") == gold0["npc_xiaoqian"] + 48) or None,
        "跑满一日": seen_day_end or None,
    }
    ok = all(v for v in checks.values())
    print("\n" + "\n".join(f"  [{'OK ' if v else 'FAIL'}] {k} {v if isinstance(v, str) else ''}" for k, v in checks.items()))
    print(f"\n{sum(1 for v in checks.values() if v)}/{len(checks)} checks passed → {'PASS' if ok else 'FAIL'}  (speed ×{a.speed}, wall {time.time() - t0:.0f}s)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
