#!/usr/bin/env python3
"""
一机多实例空跑（W6 任务 2）：用 run_town.sh 起 N 个沙盒实例（临时端口 + 临时数据目录，SELF_SYNC=0），
每个各 join 1 个 agent（有衰减 tick），其余不打请求；每 30 s 采 GET /admin/metrics（tick 间隔 p95 / 耗时）与 RSS。
判据：每实例 tick_gap p95 ≤ 210 ms（目标 200 ms 的 5%）。

  cd back_end && uv run python scripts/multi_soak.py --instances 8 --minutes 30 [--out /tmp/soak/multi.log] [--map-dir game/maps/m1c]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from verify_self_sync import free_port, wait_up  # noqa: E402
from soak import rss_mb  # noqa: E402

AGENTS = ["whale", "achan", "npc_cook", "npc_grocer", "npc_fisher", "npc_regular", "npc_teacher", "npc_painter"]


def http(method, url, body=None, timeout=5):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"null")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instances", type=int, default=8)
    ap.add_argument("--minutes", type=float, default=30)
    ap.add_argument("--out", default="/tmp/soak/multi.log")
    ap.add_argument("--map-dir", default=None)
    ap.add_argument("--gap-p95-max", type=float, default=210.0)
    args = ap.parse_args()
    out = open(args.out, "a")
    log = lambda s: (print(s, file=out, flush=True), print(s, flush=True))
    insts = []
    for i in range(args.instances):
        port = free_port(); data = Path(tempfile.mkdtemp(prefix=f"town{i}_"))
        cmd = [str(HERE / "run_town.sh"), "--port", str(port), "--data", str(data), "--no-sync", "--seed", str(i + 1),
               "--env", f"SANDBOX_TOWN=t{i}"]
        if args.map_dir:
            cmd += ["--env", f"SANDBOX_MAP_DIR={Path(args.map_dir).resolve()}"]
        subprocess.run(cmd, check=True, capture_output=True, cwd=HERE.parent)
        insts.append({"i": i, "port": port, "data": data, "base": f"http://127.0.0.1:{port}", "samples": []})
    log(f"=== multi soak {args.instances} x {args.minutes}min start {time.strftime('%H:%M:%S')} map={args.map_dir or 'default'} ===")
    try:
        for ins in insts:
            wait_up(f"{ins['base']}/world", timeout=60)
            ins["pid"] = int((ins["data"] / "sandbox.pid").read_text().strip())
            aid = AGENTS[ins["i"] % len(AGENTS)]
            ins["player"] = http("POST", f"{ins['base']}/player/join", {"name": aid, "controller": "agent", "profile": {"agent_id": aid}})["playerId"]
        log(f"all up: ports={[i['port'] for i in insts]} pids={[i['pid'] for i in insts]}")
        t0 = time.time()
        while time.time() - t0 < args.minutes * 60:
            time.sleep(30)
            for ins in insts:
                try:
                    m = http("GET", f"{ins['base']}/admin/metrics")
                    uv_pid = ins["pid"]
                    # run_town 用 `uv run uvicorn`：pid 文件是 uv 的，RSS 看子进程
                    rss = max([rss_mb(uv_pid)] + [rss_mb(int(c)) for c in subprocess.run(["pgrep", "-P", str(uv_pid)], capture_output=True, text=True).stdout.split()])
                    ins["samples"].append({"t": round(time.time() - t0), "gap_p95": m["tick_gap_ms"]["p95"], "gap_max": m["tick_gap_ms"]["max"],
                                           "dur_p95": m["tick_duration_ms"]["p95"], "rss": round(rss, 1), "ticks": m["tick_count"]})
                except Exception as e:
                    ins["samples"].append({"t": round(time.time() - t0), "error": str(e)})
            el = round(time.time() - t0)
            worst = max((s.get("gap_p95", 0) for i in insts for s in i["samples"][-1:]), default=0)
            log(f"t={el:5d}s worst gap_p95={worst:.1f}ms rss=" + ",".join(f"{i['samples'][-1].get('rss', -1)}" for i in insts))
    finally:
        rows = []
        for ins in insts:
            s = [x for x in ins["samples"] if "gap_p95" in x]
            row = {"i": ins["i"], "port": ins["port"], "samples": len(s),
                   "gap_p95_median": sorted(x["gap_p95"] for x in s)[len(s) // 2] if s else None,
                   "gap_p95_max": max((x["gap_p95"] for x in s), default=None), "gap_max": max((x["gap_max"] for x in s), default=None),
                   "dur_p95_max": max((x["dur_p95"] for x in s), default=None),
                   "rss_first": s[0]["rss"] if s else None, "rss_last": s[-1]["rss"] if s else None,
                   "errors": sum(1 for x in ins["samples"] if "error" in x)}
            rows.append(row); log(f"[inst {ins['i']}] {json.dumps(row)}")
            try:
                subprocess.run(["pkill", "-P", str(ins["pid"])], capture_output=True); os.kill(ins["pid"], 15)
            except Exception:
                pass
            shutil.rmtree(ins["data"], ignore_errors=True)
        ok = all(r["gap_p95_max"] is not None and r["gap_p95_max"] <= args.gap_p95_max and r["errors"] == 0 for r in rows)
        log(f"=== multi soak end: {len(rows)} instances, all gap_p95 ≤ {args.gap_p95_max} ms: {ok} ===")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
