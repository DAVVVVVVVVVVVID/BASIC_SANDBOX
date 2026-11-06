"""
需求状态快照 JSONL（W6 任务 1，数据集 schema v0.2 的沙盒侧 state 来源）。

data/state/YYYY-MM-DD.jsonl：每个 player 每 30 游戏秒一行
  {"kind":"sample","ts","game_time","town","map_version","seed","player_id","agent_id","controller","scene",
   "vars":{fullness,energy,social,fun,mood},"emotion_tags":[tag],"closeness":{},"online","position":{x,y},"using"}
由 ticker 驱动（与 self_sync 的 30 游戏秒批同节拍）。GET /admin/export?date= 一并给出。
"""

import json
import threading
from datetime import datetime
from pathlib import Path

from game.paths import data_dir

SAMPLE_INTERVAL_GAME_S = 30.0
_LOCK = threading.Lock()
_last_sample_game_ts: dict[str, float] = {}


def _dir() -> Path:
    p = data_dir() / "state"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _row(player: dict, game_iso: str) -> dict:
    from game.world_state import MAP_VERSION, SANDBOX_SEED, TOWN
    return {
        "kind": "sample", "ts": datetime.now().isoformat(timespec="milliseconds"), "game_time": game_iso,
        "town": TOWN, "map_version": MAP_VERSION, "seed": SANDBOX_SEED,
        "player_id": player["id"], "agent_id": player.get("agent_id"), "controller": player.get("controller", "human"),
        "scene": player.get("scene", "sandbox"),
        "vars": {k: round(float(player.get(k, 0.0)), 3) for k in ("fullness", "energy", "social", "fun", "mood")},
        "emotion_tags": [t["key"] for t in player.get("emotion_tags", [])],
        "closeness": {k: round(float(v), 3) for k, v in (player.get("closeness") or {}).items()},
        "online": player.get("online", True),
        "position": dict(player["position"]), "using": player.get("usingObjectId"),
    }


def on_tick(game_ts: float, game_iso: str, players: dict[str, dict]) -> int:
    """到 30 游戏秒的 player 各写一行。返回写入数。"""
    rows = []
    for pid, p in players.items():
        last = _last_sample_game_ts.get(pid)
        if last is None:
            _last_sample_game_ts[pid] = game_ts
            rows.append(_row(p, game_iso))
        elif game_ts - last >= SAMPLE_INTERVAL_GAME_S:
            _last_sample_game_ts[pid] = game_ts
            rows.append(_row(p, game_iso))
    for pid in [k for k in _last_sample_game_ts if k not in players]:
        _last_sample_game_ts.pop(pid, None)
    if rows:
        with _LOCK:
            with open(_dir() / f"{datetime.now().date().isoformat()}.jsonl", "a", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)


def read_log(date: str | None = None, player: str | None = None, limit: int | None = None) -> list[dict]:
    files = sorted(_dir().glob("*.jsonl"))
    if date:
        files = [f for f in files if f.stem == date]
    out = []
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
                if player is not None and rec.get("player_id") != player:
                    continue
                out.append(rec)
    if limit is not None and limit >= 0:
        out = out[-limit:] if limit else []
    return out


def _reset_for_tests() -> None:
    _last_sample_game_ts.clear()
