#!/usr/bin/env python3
"""
稳定性复现（W3 任务 6）：长时间驱动沙盒进程，监控它是否意外退出。

  cd back_end
  uv run python scripts/soak.py --minutes 30 --rounds 3 [--backend-dir /tmp/sandbox_soak_e7a036a/back_end] [--out soak.log]

每轮：起内置参考自我层（verify_self_sync.run_mock）+ 沙盒（临时 SANDBOX_DATA_DIR），join 1 个 agent + 1 个 human，
每秒随机动作（move / turn / use / leave / effects / chat），每 2 s 读 world / player / perceive，每 10 s 检查点与 self-sync 统计，
每 5 分钟切一次倍率；每秒 poll 进程，每 30 s 记 RSS。进程退出 → 立刻把 sandbox.log 尾部写进结果。
"""
import argparse
import json
import os
import random
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from verify_self_sync import run_mock, free_port, wait_up  # noqa: E402

DIRS = ("up", "down", "left", "right")


def http(method, url, body=None, timeout=5):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"null")


def rss_mb(pid: int) -> float:
    try:
        for line in open(f"/proc/{pid}/status"):
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024.0
    except Exception:
        pass
    return -1.0


def one_round(idx: int, minutes: float, backend_dir: Path, self_url: str, out) -> dict:
    data_dir = Path(tempfile.mkdtemp(prefix=f"sandbox_soak_{idx}_"))
    port = free_port(); base = f"http://127.0.0.1:{port}"
    log_path = data_dir / "sandbox.log"; log_fh = open(log_path, "w")
    env = {**os.environ, "SANDBOX_DATA_DIR": str(data_dir), "SELF_URL": self_url, "SELF_SYNC": "1"}
    uv_python = backend_dir / ".venv" / "bin" / "python"
    proc = subprocess.Popen([str(uv_python), "-m", "uvicorn", "main:app", "--port", str(port), "--log-level", "info"],
                            cwd=backend_dir, env=env, stdout=log_fh, stderr=subprocess.STDOUT)
    res = {"round": idx, "port": port, "pid": proc.pid, "exit": None, "requests": 0, "errors": 0,
           "rss_mb": [], "started": time.strftime("%H:%M:%S")}
    print(f"[round {idx}] sandbox pid={proc.pid} port={port} data={data_dir}", file=out, flush=True)
    try:
        wait_up(f"{base}/world")
        a = http("POST", f"{base}/player/join", {"name": "鲸仔", "controller": "agent",
                                                 "profile": {"E": 80, "N": 55, "agent_id": "whale"}})["playerId"]
        h = http("POST", f"{base}/player/join", {"name": "human"})["playerId"]
        qa, qh = urllib.parse.quote(a), urllib.parse.quote(h)
        t0 = time.time(); last_rss = 0; last_speed = 0; tick = 0
        while time.time() - t0 < minutes * 60:
            if proc.poll() is not None:
                res["exit"] = proc.returncode; break
            tick += 1
            try:
                for pid, q in ((a, qa), (h, qh)):
                    r = random.random()
                    if r < 0.5:
                        http("POST", f"{base}/action", {"entityId": pid, "action": {"type": "move", "payload": {"direction": random.choice(DIRS)}}})
                    elif r < 0.65:
                        http("POST", f"{base}/action", {"entityId": pid, "action": {"type": "turn", "payload": {"direction": random.choice(DIRS)}}})
                    elif r < 0.8:
                        http("POST", f"{base}/action", {"entityId": pid, "action": {"type": "use", "payload": {}}})
                    elif r < 0.9:
                        http("POST", f"{base}/action", {"entityId": pid, "action": {"type": "leave", "payload": {}}})
                    else:
                        http("POST", f"{base}/player/{q}/effects", {"effects": [{"type": "instant_effect", "key": random.choice(["fun", "social", "mood"]), "value": random.uniform(-3, 3)}]})
                    res["requests"] += 1
                if tick % 2 == 0:
                    http("GET", f"{base}/world"); http("GET", f"{base}/player/{qa}"); http("GET", f"{base}/player/{qh}")
                    http("GET", f"{base}/agent/perceive?entity_id={qa}&vision_size=5"); res["requests"] += 4
                if tick % 7 == 0:
                    http("GET", f"{base}/chat/nearby?entity_id={qa}")
                    rid = http("POST", f"{base}/chat/request", {"from_entity_id": a, "to_entity_ids": [h], "greeting": "hi"})["request_id"]
                    http("POST", f"{base}/chat/respond", {"entity_id": h, "request_id": rid, "accept": random.random() < 0.7, "message": "ok"})
                    res["requests"] += 3
                if tick % 10 == 0:
                    http("POST", f"{base}/admin/checkpoint"); http("GET", f"{base}/admin/self-sync"); http("GET", f"{base}/history")
                    res["requests"] += 3
                    # 退出所有活跃房间，避免 chat_active 永久锁住
                    for pid in (a, h):
                        p = http("GET", f"{base}/player/{urllib.parse.quote(pid)}")
                        if p["state"] == "talking":
                            http("POST", f"{base}/admin/player/force-reset", {"entity_id": pid})
                            http("DELETE", f"{base}/admin/player/{urllib.parse.quote(pid)}/buffs")
                if time.time() - last_speed > 300:
                    last_speed = time.time()
                    http("POST", f"{base}/time/speed", {"value": random.choice([1, 10, 60])})
            except Exception as e:
                res["errors"] += 1
                print(f"[round {idx}] t={time.time()-t0:6.0f}s request error: {e}", file=out, flush=True)
                if proc.poll() is not None:
                    res["exit"] = proc.returncode; break
            if time.time() - last_rss > 30:
                last_rss = time.time()
                res["rss_mb"].append(round(rss_mb(proc.pid), 1))
            time.sleep(1.0)
        if res["exit"] is None and proc.poll() is not None:
            res["exit"] = proc.returncode
    finally:
        log_fh.flush()
        if res["exit"] is not None:
            print(f"[round {idx}] *** SANDBOX EXITED rc={res['exit']} *** log tail:", file=out, flush=True)
            print("".join(open(log_path).readlines()[-60:]), file=out, flush=True)
            shutil.copy(log_path, Path(out.name).with_suffix(f".round{idx}.sandbox.log"))
        else:
            # 正常收尾：看日志里有没有 Traceback / ERROR
            lines = open(log_path).read().splitlines()
            bad = [l for l in lines if "Traceback" in l or "ERROR" in l or "Exception" in l]
            res["log_errors"] = len(bad)
            if bad:
                print(f"[round {idx}] log contains {len(bad)} error lines, first: {bad[:3]}", file=out, flush=True)
            proc.terminate()
            try: proc.wait(timeout=10)
            except subprocess.TimeoutExpired: proc.kill()
        log_fh.close()
        shutil.rmtree(data_dir, ignore_errors=True)
    res["ended"] = time.strftime("%H:%M:%S")
    print(f"[round {idx}] done: {json.dumps(res, ensure_ascii=False)}", file=out, flush=True)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=30)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--backend-dir", default=str(HERE.parent))
    ap.add_argument("--out", default="soak.log")
    args = ap.parse_args()
    mport = free_port(); self_url = f"http://127.0.0.1:{mport}"
    threading.Thread(target=run_mock, args=(mport,), daemon=True).start()
    wait_up(f"{self_url}/self/state?agent=whale")
    out = open(args.out, "a")
    print(f"=== soak start {time.strftime('%Y-%m-%d %H:%M:%S')} backend={args.backend_dir} mock_self={self_url} "
          f"{args.rounds}x{args.minutes}min ===", file=out, flush=True)
    results = [one_round(i + 1, args.minutes, Path(args.backend_dir), self_url, out) for i in range(args.rounds)]
    exits = [r for r in results if r["exit"] is not None]
    print(f"=== soak end: {len(results)} rounds, unexpected exits: {len(exits)} ===", file=out, flush=True)
    return 1 if exits else 0


if __name__ == "__main__":
    sys.exit(main())
