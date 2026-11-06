"""
外部效果 / 不确定性日志（W7 B19，可复现回放的第三个输入）。

data/external/YYYY-MM-DD.jsonl，每行一条，`kind`：
  self_seed        join / 重启时从自我层种入的七变量（replay 以此为起点之一）
  self_snap        self-sync 对账纠偏加回本地的差值
  effects_push     POST /player/{id}/effects 的完整载荷（含 source / event / scene）
  adjudication     freeform 的裁决结果（effects / narration / reason）
  feed             手机拉到的 digest 状态（ok / no_signal，条数）
  live             直播台 start / stop 结果
  game             游戏机 start / end 结果
  nondeterministic 让重放不确定的操作：time_speed / time_toggle / time_reset / weather（seed 为空时）等
每行都带 ts、game_time、town、map_version、seed、entity。GET /admin/export?kinds=external 一并给出。
"""

import json
import threading
from datetime import datetime
from pathlib import Path

from game.paths import data_dir

_LOCK = threading.Lock()
_MEM: list[dict] = []
_MEM_MAX = 200


def _dir() -> Path:
    p = data_dir() / "external"
    p.mkdir(parents=True, exist_ok=True)
    return p


def log(kind: str, entity: str | None, **fields) -> dict:
    try:
        from game.world_state import TOWN, MAP_VERSION, SANDBOX_SEED
        from game.time_state import game_now_iso
        base = {"town": TOWN, "map_version": MAP_VERSION, "seed": SANDBOX_SEED, "game_time": game_now_iso()}
    except Exception:
        base = {"town": None, "map_version": None, "seed": None, "game_time": None}
    now = datetime.now()
    entry = {"kind": kind, "ts": now.isoformat(timespec="milliseconds"), **base, "entity": entity, **fields}
    line = json.dumps(entry, ensure_ascii=False, default=str)
    with _LOCK:
        with open(_dir() / f"{now.date().isoformat()}.jsonl", "a", encoding="utf-8") as f:
            f.write(line + "\n")
        _MEM.append(entry)
        if len(_MEM) > _MEM_MAX:
            del _MEM[: len(_MEM) - _MEM_MAX]
    return entry


def read_log(date: str | None = None, kind: str | None = None, entity: str | None = None) -> list[dict]:
    files = sorted(_dir().glob("*.jsonl"))
    if date:
        files = [f for f in files if f.stem == date]
    out = []
    for fp in files:
        for raw in fp.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if kind is not None and rec.get("kind") != kind:
                continue
            if entity is not None and rec.get("entity") != entity:
                continue
            out.append(rec)
    return out


def _reset_for_tests() -> None:
    with _LOCK:
        _MEM.clear()
