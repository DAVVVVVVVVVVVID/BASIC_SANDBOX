#!/usr/bin/env python3
"""
B17 对账：订阅 GET /ws/world 60 s，把 snapshot + patch 叠成本地模型，每秒与轮询 GET /world 比较。

  cd back_end && uv run python scripts/verify_ws.py [--seconds 60] [--base http://127.0.0.1:8001]
不给 --base 时自起一个临时端口的沙盒（临时 SANDBOX_DATA_DIR，SELF_SYNC=0），并用两名玩家制造移动 / 使用 / 聊天。
比较项：players[]（全部字段）、objects 的 currentUsers / userList、worldState 的 date / period / running / speed / weather，
time 允许 ≤ 2 s 差。每次比较前先停 0.4 s 让推送追平（推送 ≤ 10 Hz）。退出码 0 = 60 次比较全部一致。
"""
import argparse
import asyncio
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import websockets

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from verify_self_sync import free_port, wait_up  # noqa: E402

BACK_END = HERE.parent
DIRS = ("up", "down", "left", "right")


def http(method, url, body=None, timeout=5):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"null")


class Model:
    def __init__(self, snap: dict):
        self.world_state = dict(snap["worldState"])
        self.players = {p["id"]: p for p in snap["players"]}
        self.objects = {o["id"]: {"currentUsers": o["currentUsers"], "userList": list(o["userList"])} for o in snap["objects"]}
        self.chat = []
        self.patches = 0

    def apply(self, msg: dict):
        if msg["type"] != "patch":
            return
        self.patches += 1
        self.world_state.update(msg.get("worldState", {}))
        for p in msg.get("players", {}).get("upsert", []):
            self.players[p["id"]] = p
        for pid in msg.get("players", {}).get("remove", []):
            self.players.pop(pid, None)
        for o in msg.get("objects", []):
            self.objects[o["id"]] = {"currentUsers": o["currentUsers"], "userList": list(o["userList"])}
        self.chat += msg.get("chat", [])

    def compare(self, world: dict) -> list[str]:
        diffs = []
        polled = {p["id"]: p for p in world["players"]}
        if polled != self.players:
            diffs.append(f"players: ws={sorted(self.players)} poll={sorted(polled)} " +
                         str([(k, self.players.get(k), polled.get(k)) for k in set(self.players) | set(polled) if self.players.get(k) != polled.get(k)][:2]))
        for o in world["objects"]:
            mine = self.objects.get(o["id"])
            if mine != {"currentUsers": o["currentUsers"], "userList": list(o["userList"])}:
                diffs.append(f"object {o['id']}: ws={mine} poll={o['currentUsers']}/{o['userList']}")
        ws_ = world["worldState"]
        for k in ("date", "period", "running", "speed", "weather"):
            if self.world_state.get(k) != ws_[k]:
                diffs.append(f"worldState.{k}: ws={self.world_state.get(k)} poll={ws_[k]}")
        try:
            dt = abs((datetime.fromisoformat(f"{ws_['date']}T{ws_['time']}") -
                      datetime.fromisoformat(f"{self.world_state['date']}T{self.world_state['time']}")).total_seconds())
            if dt > 2.0:
                diffs.append(f"worldState.time drift {dt:.1f}s")
        except Exception as e:
            diffs.append(f"time parse: {e}")
        return diffs


async def run(base: str, seconds: float, drive: bool) -> int:
    ws_url = base.replace("http", "ws", 1) + "/ws/world"
    pids = []
    if drive:
        for name in ("甲", "乙"):
            pids.append(http("POST", f"{base}/player/join", {"name": name})["playerId"])
    checks = 0; bad = 0; model = None; msgs = 0
    async with websockets.connect(ws_url, max_size=None) as ws:
        snap = json.loads(await ws.recv())
        assert snap["type"] == "snapshot", snap["type"]
        model = Model(snap)
        print(f"snapshot: {len(snap['tiles'])} tiles, {len(snap['objects'])} objects, {len(snap['players'])} players")

        async def pump():
            nonlocal msgs
            async for raw in ws:
                msgs += 1
                model.apply(json.loads(raw))
        pump_task = asyncio.create_task(pump())
        t0 = time.time(); room = None; i = 0
        try:
            while time.time() - t0 < seconds:
                i += 1
                if drive:
                    for pid in pids:
                        r = random.random()
                        act = {"type": "move", "payload": {"direction": random.choice(DIRS)}} if r < 0.7 else \
                              {"type": "turn", "payload": {"direction": random.choice(DIRS)}} if r < 0.85 else \
                              {"type": "use", "payload": {}} if r < 0.95 else {"type": "leave", "payload": {}}
                        http("POST", f"{base}/action", {"entityId": pid, "action": act})
                        http("GET", f"{base}/player/{urllib.parse.quote(pid)}")
                    if i % 10 == 3:
                        if room is None:
                            rid = http("POST", f"{base}/chat/request", {"from_entity_id": pids[0], "to_entity_ids": [pids[1]], "greeting": f"hi {i}"})
                            if rid.get("request_id"):
                                http("POST", f"{base}/chat/respond", {"entity_id": pids[1], "request_id": rid["request_id"], "accept": True, "message": "ok"})
                                await asyncio.sleep(0.3)
                                st = http("GET", f"{base}/chat/request/{rid['request_id']}")
                                room = st.get("chat_room_id")
                        else:
                            http("POST", f"{base}/chat/message", {"entity_id": pids[0], "chat_room_id": room, "content": f"m{i}"})
                            if i % 30 == 3:
                                http("POST", f"{base}/chat/exit", {"entity_id": pids[0], "chat_room_id": room})
                                http("POST", f"{base}/chat/exit", {"entity_id": pids[1], "chat_room_id": room})
                                room = None
                    if i % 20 == 0:
                        http("POST", f"{base}/time/speed", {"value": random.choice([1, 2, 5])})
                await asyncio.sleep(0.4)                              # 等推送追平（≤ 10 Hz）
                world = http("GET", f"{base}/world")
                await asyncio.sleep(0.15)
                diffs = model.compare(world)
                checks += 1
                if diffs:
                    bad += 1
                    print(f"  t={time.time()-t0:5.1f}s MISMATCH: {diffs[:3]}")
                elif checks % 10 == 0:
                    print(f"  t={time.time()-t0:5.1f}s ok  ({checks} checks, {model.patches} patches, {len(model.chat)} chat items)")
                await asyncio.sleep(max(0.0, 1.0 - 0.55))
        finally:
            pump_task.cancel()
    print(f"\n{checks} checks, {bad} mismatches, {model.patches} patches / {msgs} messages, {len(model.chat)} chat items → {'PASS' if bad == 0 and checks >= 30 else 'FAIL'}")
    return 0 if bad == 0 and checks >= 30 else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--base", default=None, help="已在跑的沙盒；缺省自起临时实例")
    args = ap.parse_args()
    proc = None; data_dir = None
    base = args.base
    if base is None:
        data_dir = Path(tempfile.mkdtemp(prefix="sandbox_ws_")); port = free_port(); base = f"http://127.0.0.1:{port}"
        env = {**os.environ, "SANDBOX_DATA_DIR": str(data_dir), "SELF_SYNC": "0"}
        proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--port", str(port), "--log-level", "warning"],
                                cwd=BACK_END, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_up(f"{base}/world"); print(f"[sandbox] {base}")
    try:
        return asyncio.run(run(base, args.seconds, drive=True))
    finally:
        if proc:
            proc.terminate()
            try: proc.wait(timeout=5)
            except subprocess.TimeoutExpired: proc.kill()
            shutil.rmtree(data_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
