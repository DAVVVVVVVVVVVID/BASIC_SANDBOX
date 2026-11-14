#!/usr/bin/env python3
"""X7 每天独立起：把一台 SANDBOX_SCENARIO=1 的镇复位到 world-v1.1.1 初始状态并断言。
  uv run python scripts/x7_reset.py --base http://127.0.0.1:8091 --date 2026-11-20 [--wipe-data <sandbox 数据目录>]
复位 = reset（冰箱 6 饭 + 4 食材、补货 / 日薪 / 房租 / 委托 / 门禁 / 说话归零、时间回真实）→ set_time <date> 04:00 → spawn 鲸仔（账户开 3,000）
       → 站床边 + occupy bed_whale（tags sleeping）。--wipe-data 先删检查点与 data/* 日志（镇要先停）。
"""
import argparse, json, shutil, sys, urllib.request, urllib.parse
from pathlib import Path


def http(base, method, path, body=None):
    req = urllib.request.Request(base + path, method=method, data=json.dumps(body).encode() if body is not None else None, headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8091"); ap.add_argument("--date", required=True, help="游戏日 YYYY-MM-DD（04:00 起）")
    ap.add_argument("--wipe-data", default=None, help="镇的 sandbox 数据目录：先删 checkpoint.sqlite 与 data/{actions,chat,state,external,qq,economy}（镇须已停）")
    a = ap.parse_args(); B = a.base
    if a.wipe_data:
        d = Path(a.wipe_data)
        for f in list(d.glob("checkpoint*.sqlite*")):
            f.unlink()
        for sub in ("actions", "chat", "state", "external", "qq", "economy", "dream"):
            shutil.rmtree(d / sub, ignore_errors=True)
        print("wiped", d)
    r = http(B, "POST", "/admin/scenario", {"steps": [
        {"op": "reset"}, {"op": "set_time", "date": a.date, "time": "04:00"},
        {"op": "spawn", "name": "鲸仔", "controller": "agent", "agent_id": "whale", "x": 3, "y": 13, "facing": "up"},
    ]})
    assert r["ok"], json.dumps(r, ensure_ascii=False)[:400]
    w = r["steps"][-1]["detail"]["id"]
    r = http(B, "POST", "/admin/scenario", {"steps": [{"op": "occupy", "player": w, "object": "bed_whale"}]})
    assert r["ok"], r
    objs = {o["id"]: o for o in http(B, "GET", "/world?fields=objects")["objects"]}
    p = http(B, "GET", f"/player/{urllib.parse.quote(w)}")
    ws_ = http(B, "GET", "/world?fields=worldState")["worldState"]
    m = http(B, "GET", "/admin/metrics")
    checks = {
        "时间 04:00 当日": ws_["date"] == a.date and ws_["time"].startswith("04:00"),
        "冰箱 6 饭 + 4 食材": objs["fridge_home"]["stock"] == {"home_meal": 6, "ingredients": 4},
        "NPC 家冰箱 4 饭": all(objs[f]["stock"] == {"home_meal": 4} for f in ("fridge_fisher", "fridge_claudine", "fridge_owners", "fridge_rest")),
        "商店满货": objs["counter"]["stock"] == objs["counter"]["daily_supply"] and objs["fish_stall"]["stock"] == {"fish": 6},
        "鲸仔 3000 / 账户": p["gold"] == 3000 and m["accounts"].get("whale") == 3000,
        "无委托": http(B, "GET", "/commissions")["count"] == 0,
        "在床上睡着": p["usingObjectId"] == "bed_whale" and "sleeping" in p["tags"],
        "背包只有钥匙": [i["type"] for i in p["inventory"]] == ["key"],
        "房租未欠": (p["rent"] or {}).get("overdue") is False,
        "只有她（solo）": m.get("solo") is True or len(http(B, "GET", "/world?fields=players")["players"]) == 1,
    }
    for k, v in checks.items():
        print(f"{'PASS' if v else 'FAIL'}  {k}")
    print(json.dumps({"player_id": w, "solo": m.get("solo"), "accounts": m["accounts"], "mapVersion": m["mapVersion"]}, ensure_ascii=False))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
