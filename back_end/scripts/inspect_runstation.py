#!/usr/bin/env python3
"""
七天长跑巡检（W7 任务 3）：读运行台日志（只读）+ GET /admin/metrics，输出一行 markdown 表格行。

  cd back_end && uv run python scripts/inspect_runstation.py [--log /home/shan-dw/Project/run/data/sandbox.log] [--base http://127.0.0.1:8000] [--date 2026-11-06]
"""
import argparse
import json
import re
import sys
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default="/home/shan-dw/Project/run/data/sandbox.log")
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--data-dir", default="/home/shan-dw/Project/run/data/sandbox")
    args = ap.parse_args()
    lines = Path(args.log).read_text(encoding="utf-8", errors="replace").splitlines() if Path(args.log).exists() else []
    status = Counter()
    for l in lines:
        m = re.search(r'" (\d{3}) ', l)
        if m:
            status[m.group(1)[0] + "xx"] += 1
    tracebacks = sum(1 for l in lines if "Traceback" in l)
    errors = sum(1 for l in lines if "ERROR" in l or " 500 " in l)
    auth = sum(1 for l in lines if " 401 " in l or " 403 " in l)
    try:
        with urllib.request.urlopen(f"{args.base}/admin/metrics", timeout=5) as r:
            m = json.load(r)
    except Exception as e:
        m = {"error": str(e)}
    rows = {}
    for kind in ("actions", "chat", "state", "external"):
        fp = Path(args.data_dir) / kind / f"{args.date}.jsonl"
        rows[kind] = len(fp.read_text(encoding="utf-8").splitlines()) if fp.exists() else 0
    tick = m.get("tick_gap_ms", {}); dur = m.get("tick_duration_ms", {})
    print(f"| {args.date} | {len(lines)} | 2xx {status.get('2xx', 0)} / 4xx {status.get('4xx', 0)} / 5xx {status.get('5xx', 0)} | "
          f"{tracebacks} / {errors} / {auth} | {tick.get('p95', '-')} / {tick.get('max', '-')} ms | {dur.get('p95', '-')} / {dur.get('max', '-')} ms | "
          f"{m.get('rss_mb', '-')} MB | {m.get('players', '-')} / {m.get('ws_clients', '-')} | "
          f"{rows['actions']} / {rows['chat']} / {rows['state']} / {rows['external']} | {m.get('mapVersion', '-')} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
