"""
后台 ticker（B8）

独立 asyncio 任务，每 TICK_INTERVAL（200 ms）：
    real_delta → time_state.advance_time → game_delta
    game_delta > 0 时 world_state._run_buff_tick_all(game_delta)
    world_state._cleanup_stale_players()
    每 CHECKPOINT_INTERVAL（5 s）persistence.save_checkpoint()

GET /world 不再推进任何状态。tick_once() 可被测试直接调用（配合 time_state.set_clock 假时钟）。
"""

import asyncio
import logging
import time

from game import time_state, world_state, persistence

log = logging.getLogger("sandbox.ticker")

TICK_INTERVAL = 0.2   # 秒

_last_real: float | None = None
_last_checkpoint: float = 0.0
_task: asyncio.Task | None = None
_tick_count = 0
# 指标：最近 N 次 tick 的耗时与间隔（毫秒），供 GET /admin/metrics
_METRICS_N = 600
_durations_ms: list[float] = []
_gaps_ms: list[float] = []
_last_tick_wall: float | None = None


def tick_once(now_real: float | None = None, *, checkpoint: bool = True) -> float:
    """执行一次 tick，返回本次 game_delta_ms。可注入 now_real（测试）。"""
    global _last_real, _last_checkpoint, _tick_count
    global _last_tick_wall
    t_start = time.perf_counter()
    wall = time.time()
    if _last_tick_wall is not None:
        _gaps_ms.append((wall - _last_tick_wall) * 1000.0)
        if len(_gaps_ms) > _METRICS_N:
            del _gaps_ms[: len(_gaps_ms) - _METRICS_N]
    _last_tick_wall = wall
    now = now_real if now_real is not None else time_state.now_real()
    if _last_real is None:
        _last_real = now
    real_delta_ms = max(0.0, (now - _last_real) * 1000.0)
    _last_real = now

    game_delta_ms = time_state.advance_time(real_delta_ms)
    if game_delta_ms > 0:
        world_state._run_buff_tick_all(game_delta_ms)
    world_state._cleanup_stale_players()
    with world_state.STATE_LOCK:
        world_state._update_away()         # W8 Q0e：按墙钟，每 tick 都算（不依赖 game_delta）
    from game import chat_state
    chat_state.tick()                      # B9：邀请超时、walking_over 建房
    _tick_count += 1

    if checkpoint and now - _last_checkpoint >= persistence.CHECKPOINT_INTERVAL:
        try:
            persistence.save_checkpoint()
        except Exception:        # 检查点失败不能把 tick 拖死
            log.exception("checkpoint failed")
        _last_checkpoint = now
    _durations_ms.append((time.perf_counter() - t_start) * 1000.0)
    if len(_durations_ms) > _METRICS_N:
        del _durations_ms[: len(_durations_ms) - _METRICS_N]
    return game_delta_ms


def _pct(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    return s[min(len(s) - 1, int(round(q * (len(s) - 1))))]


def metrics() -> dict:
    """tick 耗时 / 间隔统计（最近 600 次 ≈ 2 分钟）。"""
    return {
        "tick_count": _tick_count,
        "interval_target_ms": TICK_INTERVAL * 1000.0,
        "tick_duration_ms": {"p50": round(_pct(_durations_ms, 0.5), 3), "p95": round(_pct(_durations_ms, 0.95), 3),
                             "max": round(max(_durations_ms), 3) if _durations_ms else 0.0},
        "tick_gap_ms": {"p50": round(_pct(_gaps_ms, 0.5), 1), "p95": round(_pct(_gaps_ms, 0.95), 1),
                        "max": round(max(_gaps_ms), 1) if _gaps_ms else 0.0},
        "running": is_running(),
    }


async def _loop() -> None:
    while True:
        try:
            tick_once()
        except Exception:
            log.exception("tick failed")
        await asyncio.sleep(TICK_INTERVAL)


def start() -> asyncio.Task:
    """在当前事件循环里启动后台 tick 任务（幂等）。"""
    global _task, _last_real, _last_checkpoint
    if _task is not None and not _task.done():
        return _task
    _last_real = None
    _last_checkpoint = time.time()
    _task = asyncio.get_running_loop().create_task(_loop(), name="sandbox-ticker")
    return _task


async def stop() -> None:
    global _task
    if _task is None:
        return
    _task.cancel()
    try:
        await _task
    except (asyncio.CancelledError, Exception):
        pass
    _task = None


def is_running() -> bool:
    return _task is not None and not _task.done()


def _reset_for_tests() -> None:
    global _last_real, _last_checkpoint, _tick_count, _last_tick_wall
    _last_real = None
    _last_checkpoint = 0.0
    _tick_count = 0
    _last_tick_wall = None
    _durations_ms.clear(); _gaps_ms.clear()
