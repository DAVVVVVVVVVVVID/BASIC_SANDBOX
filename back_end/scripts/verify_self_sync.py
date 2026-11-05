#!/usr/bin/env python3
"""
与自我层联调：沙盒 agent player 的七变量 vs 自我层 GET /self/state，差值须 < 0.5。

用法：
  cd back_end
  # 对真实自我层（会话 A 的服务，默认 http://127.0.0.1:8100）：
  uv run python scripts/verify_self_sync.py --self-url http://127.0.0.1:8100 --seconds 120 --speed 60
  # 没有自我层时用内置参考实现（whale-self state.py 的移植）自测脚本本身：
  uv run python scripts/verify_self_sync.py --mock --seconds 120 --speed 60

流程：
  1. 以 SELF_URL 指向目标、SANDBOX_DATA_DIR 指向临时目录启动沙盒 uvicorn
  2. join 一个 controller=agent 的 player（agent_id=whale）→ 沙盒从自我层种入初值
  3. 调 speed（默认 60：真实 2 分钟 = 游戏 2 小时），期间推送两次事件、睡一次床
  4. 每隔若干秒对比 GET /player/{id}/state 与 GET /self/state，记录最大差值
  5. 结束时 max|diff| < 0.5 即通过
退出码 0 = 通过。
"""
import argparse
import json
import math
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BACK_END = Path(__file__).resolve().parent.parent
TZ = ZoneInfo(os.environ.get("SANDBOX_TZ", "Asia/Shanghai"))
OBJ_ID, STAND, FACE = "bed_whale", (3, 5), "up"   # 鲸仔房间的床：energy_regen +25/h，fun −1/h


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def http(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read() or b"null")


def wait_up(url, timeout=20):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            http("GET", url); return
        except Exception:
            time.sleep(0.2)
    raise SystemExit(f"not up: {url}")


# ── 内置参考自我层（移植 whale-self/whale_self/state.py 的 sandbox 规则） ──────
def run_mock(port: int):
    from fastapi import FastAPI, Request
    import uvicorn
    RATES = {"fullness": -12 / 3600, "energy": -8 / 3600, "social": -6 / 3600, "fun": -10 / 3600}
    OCEAN = {"E": 80, "N": 55}
    base = 65 + 0.2 * (OCEAN["E"] - 50) - 0.3 * (OCEAN["N"] - 50)
    doc = {"agent_id": "whale", "scene": "sandbox", "last_tick_ts": datetime.now(TZ).isoformat(timespec="seconds"),
           "vars": {"fullness": 70.0, "energy": 70.0, "social": 70.0, "fun": 70.0, "mood": round(base, 2)},
           "emotion_tags": [], "closeness": {"achan": 72.0}, "ocean": OCEAN,
           "thresholds": {"low": 25, "critical": 15, "emergency": 10}}
    clamp = lambda x: max(0.0, min(100.0, x))

    def night_seconds(a, b):
        tot, cur = 0.0, a
        while cur < b:
            nxt = (cur + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
            seg = min(nxt, b)
            if cur.hour < 6: tot += (seg - cur).total_seconds()
            cur = seg
        return tot

    def catch_up(now):
        last = datetime.fromisoformat(doc["last_tick_ts"])
        gap = (now - last).total_seconds()
        if gap <= 1.0: return
        dt = min(gap, 8 * 3600); start = now - timedelta(seconds=dt); v = doc["vars"]
        for k, r in RATES.items():
            ns = night_seconds(start, now) if k == "energy" else 0.0
            v[k] = clamp(v[k] + r * (dt - ns) + r * 1.5 * ns)
        v["mood"] = clamp(base + (v["mood"] - base) * math.pow(0.5, dt / 7200.0))
        for k in v: v[k] = round(v[k], 3)
        doc["last_tick_ts"] = now.isoformat(timespec="seconds")

    app = FastAPI()
    @app.get("/self/state")
    def state(agent: str = "whale"):
        catch_up(datetime.now(TZ)); return doc
    @app.post("/self/state/delta")
    async def delta(req: Request):
        b = await req.json(); now = datetime.fromisoformat(b["ts"]) if b.get("ts") else datetime.now(TZ)
        catch_up(now)
        for k, d in b.get("vars_delta", {}).items():
            if k in doc["vars"]: doc["vars"][k] = round(clamp(doc["vars"][k] + float(d)), 3)
        doc["last_tick_ts"] = now.isoformat(timespec="seconds")
        return {"vars": doc["vars"], "last_tick_ts": doc["last_tick_ts"]}
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def bfs(tiles, start, goal):
    from collections import deque
    walk = {(t["x"], t["y"]) for t in tiles if t["walkable"]}
    q = deque([(start, [])]); seen = {start}
    while q:
        (x, y), path = q.popleft()
        if (x, y) == goal: return path
        for dx, dy, d in ((0, -1, "up"), (0, 1, "down"), (-1, 0, "left"), (1, 0, "right")):
            n = (x + dx, y + dy)
            if n in walk and n not in seen: seen.add(n); q.append((n, path + [d]))
    raise SystemExit("no path")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-url", default=os.environ.get("SELF_URL", "http://127.0.0.1:8100"))
    ap.add_argument("--mock", action="store_true", help="用内置参考自我层代替真实服务")
    ap.add_argument("--seconds", type=float, default=120.0, help="真实观察秒数")
    ap.add_argument("--speed", type=float, default=30.0, help="沙盒倍率（30 → 2 分钟 = 1 游戏小时）")
    ap.add_argument("--agent", default="whale")
    args = ap.parse_args()

    self_url = args.self_url
    if args.mock:
        mport = free_port(); self_url = f"http://127.0.0.1:{mport}"
        threading.Thread(target=run_mock, args=(mport,), daemon=True).start()
        wait_up(f"{self_url}/self/state?agent={args.agent}")
        print(f"[mock self-layer] {self_url}")
    try:
        http("GET", f"{self_url}/self/state?agent={args.agent}")
    except Exception as e:
        print(f"self-layer unreachable at {self_url}: {e}\n（没有真实服务时加 --mock）"); return 2

    data_dir = Path(tempfile.mkdtemp(prefix="sandbox_selfsync_")); port = free_port(); base = f"http://127.0.0.1:{port}"
    env = {**os.environ, "SANDBOX_DATA_DIR": str(data_dir), "SELF_URL": self_url, "SELF_SYNC": "1"}
    log_path = data_dir / "sandbox.log"
    log_fh = open(log_path, "w")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--port", str(port), "--log-level", "info"],
                            cwd=BACK_END, env=env, stdout=log_fh, stderr=subprocess.STDOUT)
    worst = 0.0; worst_at = None; samples = 0; stats = {"sent": 0, "failed": 0}; batch_drift = final_worst = 99.0
    try:
        wait_up(f"{base}/world"); print(f"[sandbox] {base}  self={self_url}")
        remote0 = http("GET", f"{self_url}/self/state?agent={args.agent}")["vars"]
        j = http("POST", f"{base}/player/join", {"name": "鲸仔", "controller": "agent",
                                                  "profile": {"E": 80, "N": 55, "agent_id": args.agent}})
        pid = j["playerId"]; p = j["player"]
        qpid = urllib.parse.quote(pid)                     # 中文名 → URL 编码
        seeded = all(abs(p[k] - remote0[k]) < 0.01 for k in ("fullness", "energy", "social", "fun"))
        print(f"  seed from self-layer: {'OK ' if seeded else 'FAIL'} local={ {k: p[k] for k in ('fullness','energy','social','fun','mood')} }")
        # 走到床边并使用（regen 顶到 100 后，上报的增量 = 恰好抵消衰减的那部分）
        world = http("GET", f"{base}/world")
        for d in bfs(world["tiles"], (p["position"]["x"], p["position"]["y"]), STAND):
            http("POST", f"{base}/action", {"entityId": pid, "action": {"type": "move", "payload": {"direction": d}}})
        http("POST", f"{base}/action", {"entityId": pid, "action": {"type": "turn", "payload": {"direction": FACE}}})
        use = http("POST", f"{base}/action", {"entityId": pid, "action": {"type": "use", "payload": {}}})
        print(f"  use {OBJ_ID}: {'OK ' if use['success'] else 'FAIL ' + str(use.get('reason'))}")
        http("POST", f"{base}/time/speed", {"value": args.speed})

        batch_real_s = 30.0 / args.speed                   # 一批 = 30 游戏秒
        t0 = time.time(); pushed = set()
        while time.time() - t0 < args.seconds:
            time.sleep(5)
            el = time.time() - t0
            if el > args.seconds * 0.3 and "a" not in pushed:
                pushed.add("a")
                http("POST", f"{base}/player/{qpid}/effects", {"effects": [
                    {"type": "instant_effect", "key": "social", "value": 12}, {"type": "instant_effect", "key": "mood", "value": 4}]})
                print("  pushed: social +12, mood +4")
                time.sleep(batch_real_s + 1.0)                 # 事件在下一批才到自我层，等它发出去再采样
            if el > args.seconds * 0.6 and "b" not in pushed:
                pushed.add("b")
                http("POST", f"{base}/action", {"entityId": pid, "action": {"type": "leave", "payload": {}}})
                http("POST", f"{base}/player/{qpid}/effects", {"effects": [{"type": "instant_effect", "key": "fun", "value": -7}]})
                print(f"  left {OBJ_ID}; pushed: fun −7")
                time.sleep(batch_real_s + 1.0)
            http("GET", f"{base}/player/{qpid}")                      # 心跳
            local = http("GET", f"{base}/player/{qpid}/state")["vars"]
            remote = http("GET", f"{self_url}/self/state?agent={args.agent}")["vars"]
            diffs = {k: local[k] - remote[k] for k in local}
            w = max(abs(v) for v in diffs.values()); samples += 1
            if w > worst: worst, worst_at = w, diffs
            print(f"  t={el:5.0f}s  local={ {k: round(v,2) for k,v in local.items()} }  maxdiff={w:.3f}")
        # 判据 1：每批被自我层确认时，自我层返回的 vars 与发批瞬间的本地快照之差（沙盒侧记录）
        stats = http("GET", f"{base}/admin/self-sync")
        batch_drift = stats["drift_max"]
        print(f"  self-sync stats: sent={stats['sent']} failed={stats['failed']} resyncs={stats['resyncs']} "
              f"batch drift_max={batch_drift:.3f}")
        # 判据 2：结束时（已离开物品、最后一批已发出）两边直接读数之差
        time.sleep(batch_real_s + 1.0)
        local = http("GET", f"{base}/player/{qpid}/state")["vars"]
        remote = http("GET", f"{self_url}/self/state?agent={args.agent}")["vars"]
        final = {k: round(local[k] - remote[k], 3) for k in local}
        final_worst = max(abs(v) for v in final.values())
        print(f"  final direct diff: {final} (max {final_worst:.3f})")
        print(f"  （采样期间的瞬时 maxdiff={worst:.3f} 是批间延迟：物品 buff 的变化最多滞后 30 游戏秒才上报，"
              f"量级 = 速率 × 30 s；按批对账不受影响）")
    except Exception:
        proc.poll()
        if proc.returncode is not None:
            log_fh.flush()
            print(f"[sandbox exited rc={proc.returncode}] last log lines:")
            print("".join(open(log_path).readlines()[-40:]))
        raise
    finally:
        proc.terminate()
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired: proc.kill()
        log_fh.close()
        shutil.rmtree(data_dir, ignore_errors=True)
    ok = samples > 0 and stats["sent"] > 0 and stats["failed"] == 0 and batch_drift < 0.5 and final_worst < 0.5
    print(f"\nbatch drift_max={batch_drift:.3f}  final diff={final_worst:.3f}  (threshold 0.5, {samples} samples, "
          f"{stats['sent']} batches) → {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
