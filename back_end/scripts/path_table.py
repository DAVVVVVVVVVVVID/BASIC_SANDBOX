#!/usr/bin/env python3
"""
v1 图最短路表（W11 维护，X1 实验给 A 算「步数 / 最短路」）：任意两格 / 物品站位 / arena 的 BFS 长度，走 edges，按给定游戏时刻的门禁。

  cd back_end && uv run python scripts/path_table.py --map v1.2 [--at 11:30] [--ignore-locks] [--as whale] \\
      --points 客厅=12,26 街道=45,19 码头=55,13 --objects fridge_home bed_whale fishing_spot_1 table_rest_1 counter --arenas whale_room dining \\
      [--pairs 客厅:fridge_home 码头:whale_room] [--format md|csv|json]

  --points  名字=x,y（起点 / 终点都可以）      --objects 物品 id（终点 = 它的 usePos 或相邻可走格；起点取第一个站位）
  --arenas  arena id（终点 = 该 arena 全部可走格；起点取第一个可走格）
  不给 --pairs 则输出所有点两两之间的矩阵。不起服务、不碰任何实例；也可对运行中的实例用 GET /admin/path?from=x,y&to=x,y。
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default="v1.2", help="game/maps/<name> 或目录（world-v1.2 起默认 v1.2）")
    ap.add_argument("--at", default=None, help="游戏时刻 HH:MM（营业时间 / 锁门按它算；缺省 12:00）")
    ap.add_argument("--ignore-locks", action="store_true")
    ap.add_argument("--as", dest="mover", default=None, help="按谁的门禁算（agent_id，如 whale / claudine）")
    ap.add_argument("--points", nargs="*", default=[])
    ap.add_argument("--objects", nargs="*", default=[])
    ap.add_argument("--arenas", nargs="*", default=[])
    ap.add_argument("--pairs", nargs="*", default=[])
    ap.add_argument("--format", default="md", choices=["md", "csv", "json"])
    args = ap.parse_args()

    map_dir = Path(args.map) if Path(args.map).is_dir() else HERE / "game" / "maps" / args.map
    os.environ["SANDBOX_MAP_DIR"] = str(map_dir)
    os.environ.setdefault("SANDBOX_DATA_DIR", "/tmp/path_table_data")
    sys.path.insert(0, str(HERE))
    from game import world_state as ws, time_state
    from game.time_state import GAME_TZ
    hh, mm = (args.at or "12:00").split(":")
    fixed = datetime(2026, 11, 10, int(hh), int(mm), tzinfo=GAME_TZ).timestamp()
    time_state.set_clock(lambda: fixed); time_state.reset_time()

    mover = {"id": args.mover, "agent_id": args.mover, "name": args.mover, "controller": "agent"} if args.mover else None
    nodes: dict[str, dict] = {}     # name -> {"start": (x,y), "goals": set}
    for p in args.points:
        name, xy = p.split("="); x, y = (int(v) for v in xy.split(","))
        nodes[name] = {"start": (x, y), "goals": {(x, y)}}
    for oid in args.objects:
        goals = ws.goal_tiles_for(to_object=oid)
        if not goals:
            print(f"[warn] object {oid}: no goal tiles", file=sys.stderr); continue
        nodes[oid] = {"start": sorted(goals)[0], "goals": goals}
    for aid in args.arenas:
        goals = ws.goal_tiles_for(to_arena=aid)
        if not goals:
            print(f"[warn] arena {aid}: no tiles", file=sys.stderr); continue
        nodes[aid] = {"start": sorted(goals)[0], "goals": goals}
    if not nodes:
        ap.error("give --points / --objects / --arenas")

    pairs = [tuple(p.split(":")) for p in args.pairs] or [(a, b) for a in nodes for b in nodes if a != b]
    rows = []
    for a, b in pairs:
        if a not in nodes or b not in nodes:
            print(f"[warn] unknown node in pair {a}:{b}", file=sys.stderr); continue
        r = ws.path_query(nodes[a]["start"], nodes[b]["goals"], mover=mover, ignore_locks=args.ignore_locks)
        rows.append({"from": a, "to": b, "start": list(nodes[a]["start"]), "length": r["length"], "reachable": r["reachable"]})
    meta = {"map": ws.MAP_VERSION, "at": args.at or "12:00", "ignore_locks": args.ignore_locks, "mover": args.mover}
    if args.format == "json":
        print(json.dumps({"meta": meta, "rows": rows}, ensure_ascii=False, indent=1)); return 0
    if args.format == "csv":
        print("from,to,length,reachable")
        for r in rows:
            print(f"{r['from']},{r['to']},{'' if r['length'] is None else r['length']},{int(r['reachable'])}")
        return 0
    names = list(nodes)
    print(f"最短路（步数，BFS 走 edges）· {meta['map']} · 游戏时刻 {meta['at']} · ignore_locks={meta['ignore_locks']} · as={meta['mover'] or '-'}")
    if args.pairs:
        print("| 从 | 到 | 步数 |\n|---|---|---|")
        for r in rows:
            print(f"| {r['from']} | {r['to']} | {r['length'] if r['reachable'] else '不可达'} |")
    else:
        table = {(r["from"], r["to"]): r for r in rows}
        print("| 从 \\ 到 | " + " | ".join(names) + " |"); print("|---" * (len(names) + 1) + "|")
        for a in names:
            cells = ["—" if a == b else (str(table[(a, b)]["length"]) if table[(a, b)]["reachable"] else "✗") for b in names]
            print(f"| {a} | " + " | ".join(cells) + " |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
