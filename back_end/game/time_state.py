"""
游戏时间状态模块（B7：真实起点 + 倍率）

状态只存四个量：
    anchor_real  墙钟时间（epoch 秒），锚点
    anchor_game  锚点时刻对应的游戏时间（epoch 秒，按 GAME_TZ 解释）
    speed        倍率（真实 1s = 游戏 speed s），下限 MIN_SPEED
    running      是否推进

    game_now = anchor_game + (now − anchor_real) × speed      （running=True）
    game_now = anchor_game                                      （running=False）

set_speed / set_running 时先把当前游戏时刻折算成新锚点，所以倍率切换、暂停、
重启（配合 persistence 回填锚点）后游戏时间都是连续的。

首次启动：anchor_game = 真实当前时间（与北京时间 1:1，时区取 GAME_TZ），不再写死
START_DATE。之后从检查点恢复。

时段划分：
    06:00–08:00  morning（早晨）
    08:00–20:00  day（白天）
    20:00–22:00  dusk（黄昏）
    22:00–06:00  night（夜晚）

advance_time(real_delta_ms) 保留签名：仍返回 game_delta_ms 供 buff tick 使用，
但它不再"累加"时间——时间由锚点推导。
"""

import os
import time
from datetime import datetime, timezone
from typing import Callable, Literal
from zoneinfo import ZoneInfo

# ── 常量 ──────────────────────────────────────────────────────────────────────

DEFAULT_SPEED   = 1.0    # 真实 1s = 游戏 1s（UI 显示 1x，与现实同步）
MIN_SPEED       = 1.0
DEFAULT_RUNNING = os.environ.get("SANDBOX_TIME_RUNNING", "1") not in ("0", "false", "False")
# 假设：沙盒时间与北京时间 1:1（handoffs/README 第 8 条），时区固定 Asia/Shanghai，可用环境变量覆盖
GAME_TZ = ZoneInfo(os.environ.get("SANDBOX_TZ", "Asia/Shanghai"))

TimePeriod = Literal["morning", "day", "dusk", "night"]

# 可注入的时钟（单测用假时钟）
_clock: Callable[[], float] = time.time


def set_clock(fn: Callable[[], float] | None) -> None:
    """替换墙钟（测试用）。传 None 恢复 time.time。"""
    global _clock
    _clock = fn or time.time


def now_real() -> float:
    return _clock()


# ── 内部状态 ──────────────────────────────────────────────────────────────────

_state: dict = {
    "anchor_real": None,     # float epoch 秒；None = 尚未初始化
    "anchor_game": None,     # float epoch 秒（游戏时刻）
    "speed":       DEFAULT_SPEED,
    "running":     DEFAULT_RUNNING,
    "_last_game_delta": 0.0,
}


def _ensure_init() -> None:
    if _state["anchor_real"] is None:
        now = _clock()
        _state["anchor_real"] = now
        _state["anchor_game"] = now


# ── 内部工具 ──────────────────────────────────────────────────────────────────

def _calc_period(hour_float: float) -> TimePeriod:
    if 6 <= hour_float < 8:
        return "morning"
    if 8 <= hour_float < 20:
        return "day"
    if 20 <= hour_float < 22:
        return "dusk"
    return "night"


def _game_dt(game_ts: float) -> datetime:
    return datetime.fromtimestamp(game_ts, tz=GAME_TZ)


def _reanchor() -> None:
    """把当前游戏时刻折算成新锚点（切换 speed / running 前调用）。"""
    _ensure_init()
    g = game_now_ts()
    _state["anchor_game"] = g
    _state["anchor_real"] = _clock()


# ── 公开接口 ──────────────────────────────────────────────────────────────────

def game_now_ts() -> float:
    """当前游戏时刻（epoch 秒）。"""
    _ensure_init()
    if not _state["running"]:
        return _state["anchor_game"]
    return _state["anchor_game"] + (_clock() - _state["anchor_real"]) * _state["speed"]


def game_now() -> datetime:
    """当前游戏时刻（带 GAME_TZ 的 datetime）。"""
    return _game_dt(game_now_ts())


def game_now_iso() -> str:
    return game_now().isoformat(timespec="seconds")


def advance_time(real_delta_ms: float) -> float:
    """
    供 tick 调用：返回这段真实时间对应的 game_delta_ms（游戏毫秒）。
    - running=False 时返回 0。
    - 签名与旧版相同；时间本身由锚点推导，这里只做换算并记录。
    """
    _ensure_init()
    if not _state["running"]:
        _state["_last_game_delta"] = 0.0
        return 0.0
    game_delta_ms = max(0.0, float(real_delta_ms)) * _state["speed"]
    _state["_last_game_delta"] = game_delta_ms
    return game_delta_ms


def get_last_game_delta() -> float:
    """返回上次 advance_time 计算的 game_delta_ms，不重复推进时间。"""
    return _state["_last_game_delta"]


def reset_time() -> None:
    """重置：游戏时间回到真实当前时间，恢复默认倍率与默认运行状态。"""
    now = _clock()
    _state["anchor_real"] = now
    _state["anchor_game"] = now
    _state["speed"]   = DEFAULT_SPEED
    _state["running"] = DEFAULT_RUNNING
    _state["_last_game_delta"] = 0.0


def set_speed(value: float) -> float:
    """设置时间倍率，下限 MIN_SPEED，返回实际设置值。切换前重锚，游戏时间连续。"""
    _reanchor()
    _state["speed"] = max(MIN_SPEED, float(value))
    return _state["speed"]


def set_running(value: bool) -> None:
    """设置运行状态。切换前重锚，暂停期间游戏时间静止。"""
    _reanchor()
    _state["running"] = bool(value)


def get_time_state() -> dict:
    """返回当前时间状态（供 world_state / router 读取）。形状与旧版一致。"""
    dt = game_now()
    return {
        "date":    dt.strftime("%Y-%m-%d"),
        "time":    dt.strftime("%H:%M:%S"),
        "period":  _calc_period(dt.hour + dt.minute / 60.0 + dt.second / 3600.0),
        "running": _state["running"],
        "speed":   _state["speed"],
    }


# ── 持久化（B2） ──────────────────────────────────────────────────────────────

def export_state() -> dict:
    """导出可序列化的锚点状态。"""
    _ensure_init()
    return {
        "anchor_real": _state["anchor_real"],
        "anchor_game": _state["anchor_game"],
        "speed":       _state["speed"],
        "running":     _state["running"],
    }


def import_state(data: dict) -> None:
    """从检查点回填。running=True 时游戏时间按停机时长自然推进（锚点公式），无需额外处理。"""
    if not data:
        return
    _state["anchor_real"] = float(data["anchor_real"])
    _state["anchor_game"] = float(data["anchor_game"])
    _state["speed"]       = max(MIN_SPEED, float(data.get("speed", DEFAULT_SPEED)))
    _state["running"]     = bool(data.get("running", DEFAULT_RUNNING))
    _state["_last_game_delta"] = 0.0


def _reset_for_tests() -> None:
    """清空到未初始化状态（测试用）。"""
    _state["anchor_real"] = None
    _state["anchor_game"] = None
    _state["speed"]   = DEFAULT_SPEED
    _state["running"] = DEFAULT_RUNNING
    _state["_last_game_delta"] = 0.0
