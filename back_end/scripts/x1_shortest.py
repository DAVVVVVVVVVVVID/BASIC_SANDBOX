#!/usr/bin/env python3
"""X1 最短路表（A 的 judge --shortest 读）：按场景时刻、鲸仔身份，用沙盒同一套 BFS 算 docs/x1-shortest.json。
  cd back_end && uv run python scripts/x1_shortest.py [--map v1.2] [--out ../docs/x1-shortest.json]
场景起点 / 目标见 docs/x1-fixtures.md §1（v1.2 坐标）。N3 是问答无路；N5 先把 table_rest_1 挪到 (36,14) 再算。"""
import argparse, json, os, sys
from datetime import datetime
from pathlib import Path

ap = argparse.ArgumentParser(); ap.add_argument("--map", default="v1.2"); ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent.parent / "docs" / "x1-shortest.json"))
a = ap.parse_args()
os.environ["SANDBOX_MAP"] = a.map; os.environ.setdefault("SELF_SYNC", "0")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from game import world_state as ws, time_state
from game.time_state import GAME_TZ

SCENES = {"S01": ((9, 13), "fridge_home", "11:30"), "S02": ((30, 9), "bed_whale", "01:50"), "S03": ((43, 5), "arena:whale_room", "10:00"),
          "N1": ((4, 13), "fishing_spot_1", "10:00"), "N2": ((28, 14), "table_rest_1", "12:00"), "N3": None, "N4": ((28, 14), "fridge_home", "22:30"),
          "N5": ((28, 14), "table_rest_1", "12:30")}
if a.map == "v1":
    SCENES = {"S01": ((12, 26), "fridge_home", "11:30"), "S02": ((45, 19), "bed_whale", "01:50"), "S03": ((55, 13), "arena:whale_room", "10:00"),
              "N1": ((5, 25), "fishing_spot_1", "10:00"), "N2": ((41, 26), "table_rest_1", "12:00"), "N3": None, "N4": ((41, 26), "fridge_home", "22:30"),
              "N5": ((41, 26), "table_rest_1", "12:30")}


class Clk:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t


clk = Clk(); time_state.set_clock(clk); time_state.reset_time(); time_state.set_running(True)
whale = ws.create_player("鲸仔", controller="agent", profile={"agent_id": "whale"})
mover = ws._players[whale["id"]]
out = {}
for k, sc in SCENES.items():
    if sc is None:
        out[k] = None; continue
    start, target, hm = sc
    h, m = hm.split(":"); clk.t = datetime(2026, 11, 20, int(h), int(m), tzinfo=GAME_TZ).timestamp()
    if k == "N5":
        ws.move_object("table_rest_1", 36 if a.map != "v1" else 48, 14 if a.map != "v1" else 26)
    goals = ws.goal_tiles_for(to_arena=target.split(":", 1)[1]) if target.startswith("arena:") else ws.goal_tiles_for(to_object=target)
    r = ws.path_query(start, goals, mover=mover, ignore_locks=False)
    out[k] = r["length"] if r.get("reachable") else None
    if k == "N5":
        ws.restore_object()
Path(a.out).write_text(json.dumps(out, ensure_ascii=False) + "\n", encoding="utf-8")
print(a.map, out, "->", a.out)
