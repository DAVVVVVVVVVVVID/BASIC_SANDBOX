#!/usr/bin/env python3
"""
kill -9 后重启续跑验证（B2 / B7 验收），可反复运行。

流程：
  1. 用临时 SANDBOX_DATA_DIR 启动 uvicorn（随机端口）
  2. join → BFS 走到 desk_12 旁 use（continuous，energy_regen −1）→ 调 speed=3
  3. POST /admin/checkpoint（也可等 5 s 自动检查点）
  4. kill -9 进程，等 DOWNTIME 秒
  5. 重新启动，检查：player 还在、位置相同、usingObjectId 相同、桌子的 userList 含她、
     游戏时间 ≈ 停机前 + 停机时长 × speed、能量按停机时长补算、speed 仍为 3、
     /history 仍可读、JSONL 行数一致、重启后还能 leave
用法：
  cd back_end && uv run python scripts/verify_restart.py [--downtime 6] [--keep-data]
退出码 0 = 全部通过。
"""
import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path

BACK_END = Path(__file__).resolve().parent.parent
# 目标物品：desk_12（continuous，energy_regen −1 / 游戏秒）——从出生点 (10,17) BFS 21 步可达，
# 使用中能量下降，重启 catch_up 的效果肉眼可见。
OBJ_ID = "desk_12_1780401844257"
STAND = (4, 2)
FACE = "up"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def http(method: str, url: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read() or b"null")


def wait_up(base: str, timeout: float = 20.0) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            http("GET", f"{base}/world")
            return
        except Exception:
            time.sleep(0.2)
    raise SystemExit("server did not come up")


def start_server(port: int, data_dir: Path) -> subprocess.Popen:
    env = {**os.environ, "SANDBOX_DATA_DIR": str(data_dir)}
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--port", str(port), "--log-level", "warning"],
        cwd=BACK_END, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def game_dt(ws: dict) -> datetime:
    return datetime.fromisoformat(f"{ws['date']}T{ws['time']}")


def act(base, pid, type_, payload=None):
    return http("POST", f"{base}/action", {"entityId": pid, "action": {"type": type_, "payload": payload or {}}})


def bfs_directions(tiles: list[dict], start: tuple[int, int], goal: tuple[int, int]) -> list[str]:
    """用 GET /world 的 tiles 做 BFS，返回方向序列。"""
    from collections import deque
    walkable = {(t["x"], t["y"]) for t in tiles if t["walkable"]}
    q = deque([(start, [])]); seen = {start}
    while q:
        (x, y), path = q.popleft()
        if (x, y) == goal:
            return path
        for dx, dy, d in ((0, -1, "up"), (0, 1, "down"), (-1, 0, "left"), (1, 0, "right")):
            n = (x + dx, y + dy)
            if n in seen or n not in walkable:
                continue
            seen.add(n); q.append((n, path + [d]))
    raise SystemExit(f"no path {start} -> {goal}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--downtime", type=float, default=6.0, help="kill -9 后等待秒数")
    ap.add_argument("--keep-data", action="store_true")
    args = ap.parse_args()

    data_dir = Path(tempfile.mkdtemp(prefix="sandbox_verify_"))
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    checks: list[tuple[str, bool, str]] = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))
        print(f"  [{'OK ' if ok else 'FAIL'}] {name} {detail}")

    proc = start_server(port, data_dir)
    try:
        wait_up(base)
        print(f"[1] server up on {port}, data_dir={data_dir}")

        pid = http("POST", f"{base}/player/join", {"name": "whale"})["playerId"]
        world = http("GET", f"{base}/world")
        me = http("GET", f"{base}/player/{pid}")
        path = bfs_directions(world["tiles"], (me["position"]["x"], me["position"]["y"]), STAND)
        for d in path:                                  # 逐格 move，每步也写一行 JSONL
            r = act(base, pid, "move", {"direction": d})
            assert r["success"], r
        act(base, pid, "turn", {"direction": FACE})
        me = http("GET", f"{base}/player/{pid}")
        check(f"walked to {STAND}", (me["position"]["x"], me["position"]["y"]) == STAND, str(me["position"]))
        use = act(base, pid, "use")
        check("use desk", use["success"] and use["result"]["objectId"] == OBJ_ID, use.get("reason") or "")
        http("POST", f"{base}/time/speed", {"value": 3})
        time.sleep(1.0)                                 # 让能量先掉一点

        before_p = http("GET", f"{base}/player/{pid}")
        before_w = http("GET", f"{base}/world")["worldState"]
        n_log_before = len(http("GET", f"{base}/history/log"))
        ck = http("POST", f"{base}/admin/checkpoint")
        check("checkpoint written", ck["ok"] and ck["players"] == 1, str(ck.get("path")))
        t_kill = time.time()

        print(f"[2] kill -9 pid={proc.pid}")
        proc.send_signal(signal.SIGKILL)
        proc.wait()
        time.sleep(args.downtime)

        print("[3] restart")
        port2 = free_port()
        base = f"http://127.0.0.1:{port2}"
        proc = start_server(port2, data_dir)
        wait_up(base)
        t_up = time.time()

        after_p = http("GET", f"{base}/player/{pid}")
        after_w = http("GET", f"{base}/world")["worldState"]
        check("player survives", after_p["id"] == pid)
        check("position continues", after_p["position"] == before_p["position"], str(after_p["position"]))
        check("still using desk", after_p["usingObjectId"] == OBJ_ID and after_p["state"] == "using",
              f"{after_p['usingObjectId']} / {after_p['state']}")
        desk = next(o for o in http("GET", f"{base}/world")["objects"] if o["id"] == OBJ_ID)
        check("desk userList restored", desk["userList"] == [pid] and desk["currentUsers"] == 1, str(desk["userList"]))
        check("speed restored", after_w["speed"] == 3.0, str(after_w["speed"]))
        check("seven vars present", all(k in after_p for k in
              ("fullness", "energy", "social", "fun", "mood", "emotion_tags", "closeness", "controller", "last_tick_ts")))
        # desk energy_regen −1/游戏秒：停机 downtime × 3 游戏秒应被 catch_up 补算
        drop = before_p["energy"] - after_p["energy"]
        check("energy caught up over downtime (≈ downtime × speed)", drop >= args.downtime * 3.0 * 0.8,
              f"{before_p['energy']:.1f} -> {after_p['energy']:.1f} (drop {drop:.1f})")
        check("hp is fullness alias", after_p["hp"] == after_p["fullness"], f"{after_p['hp']:.1f}")

        real_elapsed = t_up - t_kill
        game_elapsed = (game_dt(after_w) - game_dt(before_w)).total_seconds()
        expected = real_elapsed * 3.0
        check("game time continuous (≈ real × speed)", abs(game_elapsed - expected) <= 3 * 3.0 + 2,
              f"game +{game_elapsed:.0f}s, expected ≈ {expected:.0f}s")

        hist = http("GET", f"{base}/history/log")
        check("JSONL action log intact", len(hist) == n_log_before and n_log_before >= len(path) + 2, f"{len(hist)} lines")
        check("GET /history shape", isinstance(http("GET", f"{base}/history"), list))

        # 重启后仍可继续行动
        leave = act(base, pid, "leave")
        check("can act after restart (leave desk)", leave["success"])
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        if not args.keep_data:
            shutil.rmtree(data_dir, ignore_errors=True)

    failed = [c for c in checks if not c[1]]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
