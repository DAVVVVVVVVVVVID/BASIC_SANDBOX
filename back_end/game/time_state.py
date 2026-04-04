"""
游戏时间状态模块

- 起始时间：2026-12-30 00:00:00
- 默认速度：60（真实 1s = 游戏 1min）
- 时段划分：
    06:00–08:00  morning（早晨）
    08:00–20:00  day（白天）
    20:00–22:00  dusk（黄昏）
    22:00–06:00  night（夜晚）
"""

from typing import Literal

# ── 常量 ──────────────────────────────────────────────────────────────────────

START_DATE = "2026-12-30"
START_TIME = "00:00:00"
DEFAULT_SPEED = 1.0    # 真实 1s = 游戏 1s（UI 显示 1x，与现实同步）
MIN_SPEED = 1.0

TimePeriod = Literal["morning", "day", "dusk", "night"]

# ── 内部状态 ──────────────────────────────────────────────────────────────────

# 游戏时间以"距当日 00:00:00 的游戏秒数"存储，方便计算
_state: dict = {
    "date":    START_DATE,      # YYYY-MM-DD
    "_seconds": 0,              # 当日已过游戏秒数（0–86399）
    "period":  "night",         # 初始 00:00 属于夜晚
    "running": False,
    "speed":   DEFAULT_SPEED,
    "_last_game_delta": 0.0,    # 上次 advance_time 返回的 game_delta（供其他系统使用）
}


# ── 内部工具 ──────────────────────────────────────────────────────────────────

def _seconds_to_hms(total_seconds: int) -> str:
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def _calc_period(total_seconds: int) -> TimePeriod:
    h = total_seconds / 3600  # 浮点小时，方便边界比较
    if 6 <= h < 8:
        return "morning"
    if 8 <= h < 20:
        return "day"
    if 20 <= h < 22:
        return "dusk"
    return "night"


def _advance_date(date_str: str) -> str:
    """将 YYYY-MM-DD 日期推进一天（手动实现，避免引入 datetime）。"""
    y, m, d = map(int, date_str.split("-"))
    days_in_month = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    # 闰年判断
    if (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0):
        days_in_month[2] = 29
    d += 1
    if d > days_in_month[m]:
        d = 1
        m += 1
        if m > 12:
            m = 1
            y += 1
    return f"{y:04d}-{m:02d}-{d:02d}"


# ── 公开接口 ──────────────────────────────────────────────────────────────────

def advance_time(real_delta_ms: float) -> float:
    """
    推进游戏时间。
    - 仅 running=True 时推进。
    - 返回 game_delta_ms（游戏毫秒），供 buff_tick 等系统使用。
    - running=False 时返回 0。
    """
    if not _state["running"]:
        return 0.0

    game_delta_ms = real_delta_ms * _state["speed"]
    game_delta_s = game_delta_ms / 1000.0

    new_seconds = _state["_seconds"] + game_delta_s

    # 跨日处理
    while new_seconds >= 86400:
        new_seconds -= 86400
        _state["date"] = _advance_date(_state["date"])

    _state["_seconds"] = new_seconds
    _state["period"] = _calc_period(int(new_seconds))
    _state["_last_game_delta"] = game_delta_ms

    return game_delta_ms


def get_last_game_delta() -> float:
    """返回上次 advance_time 计算的 game_delta_ms，不重复推进时间。"""
    return _state["_last_game_delta"]


def reset_time() -> None:
    """重置至起始时间，停止运行，恢复默认速度。"""
    _state["date"] = START_DATE
    _state["_seconds"] = 0
    _state["period"] = "night"
    _state["running"] = False
    _state["speed"] = DEFAULT_SPEED


def set_speed(value: float) -> float:
    """设置时间倍率，下限 MIN_SPEED，返回实际设置值。"""
    _state["speed"] = max(MIN_SPEED, float(value))
    return _state["speed"]


def set_running(value: bool) -> None:
    """设置运行状态。"""
    _state["running"] = bool(value)


def get_time_state() -> dict:
    """返回当前时间状态（供 world_state / router 读取）。"""
    secs = int(_state["_seconds"])
    return {
        "date":    _state["date"],
        "time":    _seconds_to_hms(secs),
        "period":  _state["period"],
        "running": _state["running"],
        "speed":   _state["speed"],
    }
