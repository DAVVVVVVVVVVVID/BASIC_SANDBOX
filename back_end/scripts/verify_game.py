#!/usr/bin/env python3
"""
B18 / W10-4b 对 D 的 brain 正式接口（默认 http://127.0.0.1:8110）真实联调一局：自测沙盒起临时端口，鲸仔 use 游戏机 → leave。
验证：GET /game/state 可达 → use 成功（alive 的局直接接；否则 POST /game/start 后轮询到 alive）→ stateLabel 玩游戏中、
     player.game.status=playing、perceive.game 有 day/phase/text → leave → brain 的 ws /events 收到 game_stop_requested。

  cd back_end && uv run python scripts/verify_game.py [--game-url http://127.0.0.1:8110]
"""
import argparse
import asyncio
import json
import os
import shutil
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
from verify_self_sync import free_port, wait_up  # noqa: E402

BACK_END = HERE.parent
CONSOLE = ("game_console_whale", (9, 11), "right")


def http(method, url, body=None, timeout=10):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"null")


def listen_events(ws_url: str, seen: list, stop: threading.Event):
    import websockets

    async def go():
        try:
            async with websockets.connect(ws_url, max_size=None) as ws:
                while not stop.is_set():
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=0.5)
                    except asyncio.TimeoutError:
                        continue
                    try:
                        seen.append(json.loads(raw))
                    except Exception:
                        pass
        except Exception as e:
            seen.append({"_error": str(e)})
    asyncio.run(go())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-url", default=os.environ.get("GAME_URL", "http://127.0.0.1:8110"))
    args = ap.parse_args()
    checks = []
    def check(name, ok, detail=""):
        checks.append(bool(ok)); print(f"  [{'OK ' if ok else 'FAIL'}] {name} {detail}")
    try:
        hz = http("GET", f"{args.game_url}/game/state"); print(f"[brain] {args.game_url} state: alive={hz.get('alive')} run_id={hz.get('run_id')} day={hz.get('day')}")
    except Exception as e:
        print(f"brain unreachable: {e}"); return 2
    seen: list = []; stop = threading.Event()
    threading.Thread(target=listen_events, args=(args.game_url.replace("http", "ws", 1) + "/events", seen, stop), daemon=True).start()
    time.sleep(1.0)
    n0 = len(seen)

    data_dir = Path(tempfile.mkdtemp(prefix="sandbox_game_")); port = free_port(); base = f"http://127.0.0.1:{port}"
    env = {**os.environ, "SANDBOX_DATA_DIR": str(data_dir), "GAME_URL": args.game_url, "SELF_SYNC": "0"}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--port", str(port), "--log-level", "warning"],
                            cwd=BACK_END, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_up(f"{base}/world"); print(f"[sandbox] {base}")
        pid = http("POST", f"{base}/player/join", {"name": "鲸仔", "controller": "agent", "profile": {"agent_id": "whale"}})["playerId"]
        q = urllib.parse.quote(pid)
        # 直接放到游戏机旁（出生点就在小仓库，走两步即可）
        me = http("GET", f"{base}/player/{q}")
        sys.path.insert(0, str(HERE)); from verify_self_sync import bfs
        world = http("GET", f"{base}/world")
        for d in bfs(world["tiles"], (me["position"]["x"], me["position"]["y"]), CONSOLE[1]):
            http("POST", f"{base}/action", {"entityId": pid, "action": {"type": "move", "payload": {"direction": d}}})
        http("POST", f"{base}/action", {"entityId": pid, "action": {"type": "turn", "payload": {"direction": CONSOLE[2]}}})
        res = http("POST", f"{base}/action", {"entityId": pid, "action": {"type": "use", "payload": {}}})
        check("use game_console", res["success"] and res["result"]["objectId"] == CONSOLE[0], f"reason={res.get('reason')} {res.get('result', {}).get('error', '')}")
        check("stateLabel 玩游戏中", (res.get("result") or {}).get("stateLabel") == "鲸仔 玩游戏中", str((res.get("result") or {}).get("stateLabel")))
        p = http("GET", f"{base}/player/{q}")
        g = p.get("game") or {}
        check("player.game.status == playing", g.get("status") == "playing", json.dumps(g, ensure_ascii=False)[:200])
        per = http("GET", f"{base}/agent/perceive?entity_id={q}")
        check("perceive.game 带 brain 指标", (per.get("game") or {}).get("status") == "playing" and any(k in per["game"] for k in ("day", "run_id", "alive")),
              str({k: per.get("game", {}).get(k) for k in ("run_id", "how", "alive", "day", "phase", "health", "text")}))
        time.sleep(1.0)
        if g.get("how") != "joined":
            starts = [e for e in seen[n0:] if isinstance(e, dict) and json.dumps(e, ensure_ascii=False).find("game_start_requested") >= 0]
            check("brain /events 收到 game_start_requested", bool(starts), str(starts[:1])[:200])
        else:
            print("  [info] 已有 alive 的局，直接接着玩（不发 /game/start）")
        res = http("POST", f"{base}/action", {"entityId": pid, "action": {"type": "leave", "payload": {}}})
        check("leave", res["success"])
        time.sleep(1.5)
        ends = [e for e in seen[n0:] if isinstance(e, dict) and json.dumps(e, ensure_ascii=False).find("game_stop_requested") >= 0]
        check("brain /events 收到 game_stop_requested", bool(ends), str(ends[:1])[:200])
        p = http("GET", f"{base}/player/{q}")
        check("player.game.status == ended", (p.get("game") or {}).get("status") == "ended", str({k: (p.get("game") or {}).get(k) for k in ("left_at_day", "duration_s")}))
        print(f"  brain state after: alive={http('GET', f'{args.game_url}/game/state').get('alive')}")
    finally:
        stop.set()
        proc.terminate()
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired: proc.kill()
        shutil.rmtree(data_dir, ignore_errors=True)
    print(f"\n{sum(checks)}/{len(checks)} checks passed → {'PASS' if all(checks) else 'FAIL'}")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
