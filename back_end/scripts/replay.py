#!/usr/bin/env python3
"""
B19：从 seed + 行动 JSONL + 外部效果日志重放一天，末态与 state_log 最后一行对账（阈值 0.5）。

  cd back_end && uv run python scripts/replay.py --date 2026-11-06 --town main [--data-dir /home/shan-dw/Project/run/data/sandbox]
                                                 [--seed N] [--map-dir game/maps] [--until 2026-11-06T12:00:00+08:00] [--json]
seed / 地图缺省从该日 state 行的 seed / map_version 推断（map_version 对不上会警告）。只读输入目录；回放自身的日志写到临时目录。
"""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--town", default="main")
    ap.add_argument("--data-dir", default="/home/shan-dw/Project/run/data/sandbox")
    ap.add_argument("--seed", default=None)
    ap.add_argument("--map-dir", default=None)
    ap.add_argument("--until", default=None)
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-url", default=os.environ.get("SELF_URL", "http://127.0.0.1:8100"),
                    help="历史 state 行缺 mood_base 时，从自我层 GET /self/state 取各 agent 的 OCEAN 基线（SELF_TOKEN_RO）")
    ap.add_argument("--no-self", action="store_true")
    ap.add_argument("--start-kind", default=None, choices=[None, "join", "rejoin", "restore"], help="起点改为该类 state 行（Q1）")
    args = ap.parse_args()
    data_dir = Path(args.data_dir)
    state_file = data_dir / "state" / f"{args.date}.jsonl"
    seed = args.seed
    expected_mv = None
    if state_file.exists():
        for raw in state_file.read_text(encoding="utf-8").splitlines():
            if raw.strip():
                row = json.loads(raw)
                expected_mv = row.get("map_version")
                if seed is None and row.get("seed") is not None:
                    seed = str(row["seed"])
                break
    os.environ["SANDBOX_DATA_DIR"] = tempfile.mkdtemp(prefix="replay_")
    os.environ["SANDBOX_TOWN"] = args.town
    os.environ["SELF_SYNC"] = "0"
    if seed is not None:
        os.environ["SANDBOX_SEED"] = str(seed)
    if args.map_dir:
        os.environ["SANDBOX_MAP_DIR"] = str(Path(args.map_dir).resolve())
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from game import replay as rp, world_state
    from game.buff_tick import mood_baseline
    # 缺 mood_base 的 agent → 从自我层拿 ocean 算基线（只读 token，~/.env 兜底）
    mb: dict[str, float] = {}
    agents = set()
    if state_file.exists():
        for raw in state_file.read_text(encoding="utf-8").splitlines():
            if raw.strip():
                row = json.loads(raw)
                if row.get("agent_id") and row.get("mood_base") is None:
                    agents.add(row["agent_id"])
    if agents and not args.no_self:
        token = os.environ.get("SELF_TOKEN_RO") or os.environ.get("SELF_TOKEN")
        if not token and (Path.home() / ".env").exists():
            for line in (Path.home() / ".env").read_text().splitlines():
                if line.startswith("SELF_TOKEN_RO="):
                    token = line.split("=", 1)[1].strip().strip('"')
        import urllib.request
        for a in sorted(agents):
            try:
                req = urllib.request.Request(f"{args.self_url}/self/state?agent={a}", headers={"Authorization": f"Bearer {token}"} if token else {})
                with urllib.request.urlopen(req, timeout=5) as r:
                    oc = (json.load(r).get("ocean") or {})
                mb[a] = mood_baseline(oc.get("E", 50), oc.get("N", 50))
            except Exception as e:
                print(f"  (mood_base for {a} unavailable from self-layer: {e})")
    res = rp.replay(args.date, data_dir, until=args.until, threshold=args.threshold, mood_base_by_agent=mb, start_kind=args.start_kind)
    res["mood_base_from_self"] = mb
    res["town"] = args.town; res["seed"] = seed; res["map_version"] = world_state.MAP_VERSION; res["map_version_in_data"] = expected_mv
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2)); return 0 if res.get("ok") else 1
    if not res.get("ok") and res.get("error"):
        print(f"replay failed: {res['error']}"); return 1
    print(f"replay {args.town} {args.date}  window {res['window']['from']} → {res['window']['to']} ({res['window']['seconds']} s)")
    print(f"  seed={seed} map={res['map_version']}" + (f"  (data says {expected_mv} ⚠)" if expected_mv and expected_mv != res["map_version"] else ""))
    if res.get("mood_base_from_self"):
        print(f"  mood_base from self-layer persona (历史 state 行缺字段): {res['mood_base_from_self']}")
    print(f"  players={res['players']} state_rows={res['state_rows']} events={res['events']} applied={res['applied']} "
          f"actions_before_window_skipped={res['actions_before_window_skipped']}")
    if res["applied"].get("action_result_mismatch"):
        print(f"  ⚠ {res['applied']['action_result_mismatch']} 个动作重放结果与日志不一致，例如：{res['action_mismatches'][:3]}")
    print(f"  nondeterministic inputs in window: {len(res['nondeterministic'])}" +
          (f"  kinds={sorted({e['kind'] + ':' + str(e.get('op', '')) for e in res['nondeterministic']})}" if res["nondeterministic"] else ""))
    print(f"  {'player':22s} {'var':9s} {'replay':>9s} {'actual':>9s} {'diff':>8s}")
    for row in res["table"]:
        if "error" in row:
            print(f"  {row['player']:22s} {row['error']}"); continue
        for v in ("fullness", "energy", "social", "fun", "mood"):
            flag = "" if abs(row["diff"][v]) < res["threshold"] else "  ✗"
            print(f"  {row['player']:22s} {v:9s} {row['replay'][v]:9.3f} {row['actual'][v]:9.3f} {row['diff'][v]:+8.3f}{flag}")
    print(f"\nmax |diff| = {res['worst']}  (threshold {res['threshold']}) → {'PASS' if res['ok'] else 'FAIL'}")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
