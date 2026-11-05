"""
行动日志（B1）

- append-only JSONL：data/actions/YYYY-MM-DD.jsonl（按真实日期分文件），每行一条，
  在旧字段之上追加 game_time（游戏时刻 ISO）与 controller（human | agent）。
- 内存只保留最近 _MAX_LOG_SIZE 条给 GET /history（字段只加不减，形状不变）。
- read_log(since, entity, limit) 从文件读回，供评测与自我层拉取。
"""

import json
import threading
from datetime import datetime, date, timedelta
from pathlib import Path

from game.paths import data_dir

_MAX_LOG_SIZE = 20
_LOG: list[dict] = []
_LOCK = threading.Lock()


def _actions_dir() -> Path:
    p = data_dir() / "actions"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _file_for(day: date) -> Path:
    return _actions_dir() / f"{day.isoformat()}.jsonl"


def _game_time_and_controller(entity_id: str) -> tuple[str | None, str]:
    game_time = None
    controller = "human"
    try:
        from game.time_state import game_now_iso
        game_time = game_now_iso()
    except Exception:
        pass
    try:
        from game.world_state import _players
        p = _players.get(entity_id)
        if p:
            controller = p.get("controller", "human")
    except Exception:
        pass
    return game_time, controller


def append_log(
    entity_id: str,
    action_type: str,
    payload: dict,
    success: bool,
    reason: str | None,
    label: str | None = None,
) -> dict:
    now = datetime.now()
    game_time, controller = _game_time_and_controller(entity_id)
    entry = {
        "timestamp":  now.isoformat(timespec="milliseconds"),
        "entityId":   entity_id,
        "type":       action_type,
        "payload":    payload,
        "success":    success,
        "reason":     reason,
        "label":      label,
        "game_time":  game_time,
        "controller": controller,
    }
    line = json.dumps(entry, ensure_ascii=False)
    with _LOCK:
        with open(_file_for(now.date()), "a", encoding="utf-8") as f:
            f.write(line + "\n")
        _LOG.append(entry)
        if len(_LOG) > _MAX_LOG_SIZE:
            _LOG.pop(0)
    return entry


def get_log() -> list[dict]:
    with _LOCK:
        return list(_LOG)


def read_log(
    since: str | None = None,
    entity: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """
    从 JSONL 文件读取行动日志（按时间升序）。
    since：ISO 时间字符串（含日期即可），只返回 timestamp >= since 的记录；None = 全部。
    entity：只返回该 entityId 的记录。
    limit：最多返回条数（取最新的 limit 条）。
    """
    since_dt: datetime | None = None
    if since:
        since_dt = datetime.fromisoformat(since)
        if since_dt.tzinfo is not None:
            since_dt = since_dt.astimezone().replace(tzinfo=None)
    files = sorted(_actions_dir().glob("*.jsonl"))
    if since_dt is not None:
        first_day = since_dt.date().isoformat()
        files = [f for f in files if f.stem >= first_day]
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
                    continue  # 被 kill -9 截断的半行，跳过
                if entity is not None and rec.get("entityId") != entity:
                    continue
                if since_dt is not None and datetime.fromisoformat(rec["timestamp"]) < since_dt:
                    continue
                out.append(rec)
    if limit is not None and limit >= 0:
        out = out[-limit:] if limit else []
    return out


def _reset_for_tests() -> None:
    with _LOCK:
        _LOG.clear()
