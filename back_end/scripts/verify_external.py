#!/usr/bin/env python3
"""
B10 / B11 对运行台自我层（8100）联调。自测沙盒起在 8001（或 --port），SANDBOX_DATA_DIR 用临时目录，不碰运行台 8000。

  cd back_end && uv run python scripts/verify_external.py [--self-url http://127.0.0.1:8100] [--port 8001] [--agent whale]

检查：
  1. join controller=agent（agent_id=whale）→ 从自我层种入
  2. 走到手机旁 use → result.phone.status（ok / no_signal）、perceive.phone 有 digest 且不含 id/source/author/text
  3. 走到直播台 use → 自我层 GET /self/state?agent=whale 的 scene == live，沙盒 /player/{id}/state 的 scene == live
  4. leave → 两边 scene 都回 sandbox
  5. 顺带读 whale-self data/ops/live.log 尾部（只读，若存在）
注意：会让运行台自我层上的该 agent 开播再下播一次（scene 切换会触发它的 catch_up），结束时已复原。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from verify_self_sync import bfs, wait_up  # noqa: E402

BACK_END = HERE.parent
PHONE = ("phone_whale", (10, 8), "up")
STREAM = ("stream_desk_whale", (3, 12), "down")
LIVE_LOG = Path("/home/shan-dw/Project/whale-self/data/ops/live.log")


def http(method, url, body=None, timeout=8):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"null")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-url", default=os.environ.get("SELF_URL", "http://127.0.0.1:8100"))
    ap.add_argument("--port", type=int, default=8001)
    ap.add_argument("--agent", default="whale")
    args = ap.parse_args()
    checks = []
    def check(name, ok, detail=""):
        checks.append(bool(ok)); print(f"  [{'OK ' if ok else 'FAIL'}] {name} {detail}")

    try:
        health = http("GET", f"{args.self_url}/health")
        print(f"[self-layer] {args.self_url} {health}")
    except Exception as e:
        print(f"self-layer unreachable: {e}"); return 2

    data_dir = Path(tempfile.mkdtemp(prefix="sandbox_ext_"))
    base = f"http://127.0.0.1:{args.port}"
    env = {**os.environ, "SANDBOX_DATA_DIR": str(data_dir), "SELF_URL": args.self_url, "SELF_SYNC": "1"}
    log_fh = open(data_dir / "sandbox.log", "w")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--port", str(args.port), "--log-level", "info"],
                            cwd=BACK_END, env=env, stdout=log_fh, stderr=subprocess.STDOUT)
    try:
        wait_up(f"{base}/world"); print(f"[sandbox] {base} data={data_dir}")
        remote0 = http("GET", f"{args.self_url}/self/state?agent={args.agent}")
        j = http("POST", f"{base}/player/join", {"name": "鲸仔", "controller": "agent", "profile": {"E": 80, "N": 55, "agent_id": args.agent}})
        pid = j["playerId"]; q = urllib.parse.quote(pid); p = j["player"]
        check("seeded from self-layer", all(abs(p[k] - remote0["vars"][k]) < 0.01 for k in ("fullness", "energy", "social", "fun")),
              f"local={ {k: round(p[k], 2) for k in ('fullness','energy','social','fun','mood')} } remote_scene={remote0['scene']}")
        world = http("GET", f"{base}/world")

        def walk_and_use(obj_id, stand, face):
            from verify_self_sync import walk_to
            walk_to(base, pid, stand)                                                  # §3.36：排队走，等到达
            http("POST", f"{base}/action", {"entityId": pid, "action": {"type": "turn", "payload": {"direction": face}}})
            return http("POST", f"{base}/action", {"entityId": pid, "action": {"type": "use", "payload": {}}})

        # ── B10 手机 ──
        feed = http("GET", f"{args.self_url}/self/feed?for={args.agent}&n=8")
        res = walk_and_use(*PHONE)
        phone = (res.get("result") or {}).get("phone") or {}
        check("phone use hits self-layer feed", phone.get("status") == "ok",
              f"success={res['success']} reason={res.get('reason')} status={phone.get('status')} items={len(phone.get('items', []))} (self-layer has {len(feed.get('items', []))})")
        print(f"      message: {res.get('result', {}).get('message')}")
        per = http("GET", f"{base}/agent/perceive?entity_id={q}")
        ph = per.get("phone") or {}
        check("perceive.phone has digest", ph.get("status") == "ok" and "items" in ph, f"keys={sorted(ph)}")
        leaked = [k for it in ph.get("items", []) for k in it if k not in ("ts", "topic", "sentiment", "is_question", "is_song_request", "summary", "injection")]
        check("no raw fields in perceive.phone", not leaked, str(leaked))

        # ── B11 直播台 ──
        res = walk_and_use(*STREAM)
        check("stream_desk use → live.start ok", res["success"] and res["result"]["objectId"] == STREAM[0],
              f"success={res['success']} reason={res.get('reason')} {res.get('result', {}).get('error', '')}")
        time.sleep(0.5)
        remote = http("GET", f"{args.self_url}/self/state?agent={args.agent}")
        local = http("GET", f"{base}/player/{q}/state")
        check("self-layer scene == live", remote["scene"] == "live", remote["scene"])
        check("sandbox scene == live", local["scene"] == "live", local["scene"])
        res = http("POST", f"{base}/action", {"entityId": pid, "action": {"type": "leave", "payload": {}}})
        check("leave stream_desk", res["success"])
        time.sleep(1.5)                                             # live.stop 在后台线程发
        remote = http("GET", f"{args.self_url}/self/state?agent={args.agent}")
        local = http("GET", f"{base}/player/{q}/state")
        check("self-layer scene back to sandbox", remote["scene"] == "sandbox", remote["scene"])
        check("sandbox scene back to sandbox", local["scene"] == "sandbox", local["scene"])
        if LIVE_LOG.exists():
            tail = LIVE_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-4:]
            print("  whale-self live.log tail:"); [print("      " + l) for l in tail]
        stats = http("GET", f"{base}/admin/self-sync")
        print(f"  self-sync: sent={stats['sent']} failed={stats['failed']} last_error={stats['last_error']}")
    finally:
        proc.terminate()
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired: proc.kill()
        log_fh.close()
        shutil.rmtree(data_dir, ignore_errors=True)
    print(f"\n{sum(checks)}/{len(checks)} checks passed → {'PASS' if all(checks) else 'FAIL'}")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
