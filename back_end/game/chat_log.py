"""
聊天 append-only JSONL（W5 任务 1，README 第 10 条「数据集优先」）。

data/chat/YYYY-MM-DD.jsonl（按真实日期分文件），每行一条：
  消息  {"kind":"message","ts","game_time","room_id","seq","from","from_name","to":[...],"text","controller"}
  事件  {"kind":"event","event":"room_open"|"room_close"|"player_exit"|"room_limit"|"request_expired"|"request_rejected",
         "ts","game_time","room_id"|null,"request_id"|null,"participants":[...],"reason"?}
与 /ws/world 的 chat 推送同源（同一处写入），GET /history/chat?since=&room= 只读回放。
"""

import json
import threading
from datetime import datetime, date
from pathlib import Path

from game.paths import data_dir

_LOCK = threading.Lock()
_MEM_MAX = 200
_MEM: list[dict] = []


def _dir() -> Path:
    p = data_dir() / "chat"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _game_time() -> str | None:
    try:
        from game.time_state import game_now_iso
        return game_now_iso()
    except Exception:
        return None


def _dataset_fields() -> dict:
    try:
        from game.world_state import TOWN, MAP_VERSION, SANDBOX_SEED
        return {"town": TOWN, "map_version": MAP_VERSION, "seed": SANDBOX_SEED}
    except Exception:
        return {"town": None, "map_version": None, "seed": None}


def _write(entry: dict) -> dict:
    now = datetime.now()
    entry = {"ts": now.isoformat(timespec="milliseconds"), "game_time": _game_time(), **_dataset_fields(), **entry}
    line = json.dumps(entry, ensure_ascii=False)
    with _LOCK:
        with open(_dir() / f"{now.date().isoformat()}.jsonl", "a", encoding="utf-8") as f:
            f.write(line + "\n")
        _MEM.append(entry)
        if len(_MEM) > _MEM_MAX:
            del _MEM[: len(_MEM) - _MEM_MAX]
    return entry


def log_message(room_id: str, seq: int, from_id: str, from_name: str, to: list[str], text: str, controller: str) -> dict:
    return _write({"kind": "message", "room_id": room_id, "seq": seq, "from": from_id, "from_name": from_name,
                   "to": list(to), "text": text, "controller": controller})


def log_event(event: str, room_id: str | None, participants: list[str], request_id: str | None = None, **extra) -> dict:
    return _write({"kind": "event", "event": event, "room_id": room_id, "request_id": request_id,
                   "participants": list(participants), **extra})


def recent() -> list[dict]:
    with _LOCK:
        return list(_MEM)


def read_log(since: str | None = None, room: str | None = None, kind: str | None = None, limit: int | None = None) -> list[dict]:
    since_dt = None
    if since:
        since_dt = datetime.fromisoformat(since)
        if since_dt.tzinfo is not None:
            since_dt = since_dt.astimezone().replace(tzinfo=None)
    files = sorted(_dir().glob("*.jsonl"))
    if since_dt is not None:
        files = [f for f in files if f.stem >= since_dt.date().isoformat()]
    out: list[dict] = []
    for fp in files:
        with open(fp, encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if room is not None and rec.get("room_id") != room:
                    continue
                if kind is not None and rec.get("kind") != kind:
                    continue
                if since_dt is not None and datetime.fromisoformat(rec["ts"]) < since_dt:
                    continue
                out.append(rec)
    if limit is not None and limit >= 0:
        out = out[-limit:] if limit else []
    return out


def _reset_for_tests() -> None:
    with _LOCK:
        _MEM.clear()
