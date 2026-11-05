"""
自我层同步（ARCHITECTURE §2.5「沙盒后端 tick … 每 30 游戏秒批量 POST /self/state/delta」）

设计（与 whale-self/whale_self/state.py 的 apply_delta 对齐）：
- 自我层收到 delta 时会先按自己的衰减表把状态从 last_tick_ts 补算到 ts，再加 vars_delta。
  所以沙盒**只上报非衰减变化**（物品 buff、instant_effect、/effects 推送），衰减两边各自算，
  公式同源（buff_tick.DECAY_RATES）。这样数值差只来自离散事件落在批内的时刻差与 3 位小数的四舍五入。
- 只同步 controller == "agent" 的 player；agent_id 取 profile.agent_id（缺省用 name 的 slug，假设）。
- 加入 / 重启时先 GET /self/state 把七变量、closeness、emotion_tags、ocean(→mood_base) 种到本地。
- 每 30 游戏秒出一批：{agent, scene, ts(游戏时刻 ISO), vars_delta, source:"sandbox_tick"}。
  失败：把 vars_delta 合并回 pending，指数退避重试；本地 tick 不受影响。
- 成功：比较自我层返回的 vars 与「发批时的本地快照」，记录 drift；若 max|drift| > SNAP_THRESHOLD
  则把差值作为修正加到本地（自我层是持久化与对外出口，假设以它为准）。
- 发送在独立线程，不阻塞 ticker。SELF_URL / SELF_TOKEN / SELF_SYNC 由环境变量配置。
"""

import logging
import os
import queue
import threading
import time
from datetime import datetime

import httpx

log = logging.getLogger("sandbox.self_sync")

SYNC_INTERVAL_GAME_S = 30.0
SNAP_THRESHOLD = float(os.environ.get("SELF_SYNC_SNAP_THRESHOLD", "0.5"))
HTTP_TIMEOUT = 3.0
MAX_BACKOFF_S = 30.0
VARS = ("fullness", "energy", "social", "fun", "mood")

_cfg = {
    "url":     os.environ.get("SELF_URL", "http://127.0.0.1:8100").rstrip("/"),
    "token":   os.environ.get("SELF_TOKEN", ""),
    "enabled": os.environ.get("SELF_SYNC", "1") not in ("0", "false", "False"),
    "snap":    os.environ.get("SELF_SYNC_SNAP", "1") not in ("0", "false", "False"),
    "transport": None,     # 测试注入 httpx.MockTransport
}

_lock = threading.Lock()
_pending: dict[str, dict[str, float]] = {}        # player_id -> {var: delta}
_last_sync_game_ts: dict[str, float] = {}         # player_id -> 上次出批的游戏时刻
_queue: "queue.Queue[dict]" = queue.Queue()
_worker: threading.Thread | None = None
_stop = threading.Event()
stats: dict = {
    "sent": 0, "failed": 0, "seeded": 0, "resyncs": 0,
    "drift_max": 0.0, "drift_last": {}, "last_error": None, "last_ok_ts": None,
    "self_url": _cfg["url"], "enabled": _cfg["enabled"],
}


# ── 配置 ─────────────────────────────────────────────────────────────────────

def configure(url: str | None = None, token: str | None = None, enabled: bool | None = None,
              snap: bool | None = None, transport=None) -> None:
    if url is not None:
        _cfg["url"] = url.rstrip("/")
    if token is not None:
        _cfg["token"] = token
    if enabled is not None:
        _cfg["enabled"] = enabled
    if snap is not None:
        _cfg["snap"] = snap
    _cfg["transport"] = transport
    stats["self_url"] = _cfg["url"]
    stats["enabled"] = _cfg["enabled"]


def enabled() -> bool:
    return bool(_cfg["enabled"])


def _client() -> httpx.Client:
    headers = {"content-type": "application/json"}
    if _cfg["token"]:
        headers["Authorization"] = f"Bearer {_cfg['token']}"
    return httpx.Client(base_url=_cfg["url"], headers=headers, timeout=HTTP_TIMEOUT,
                        transport=_cfg["transport"])


def _iso(game_ts: float) -> str:
    from game.time_state import GAME_TZ
    return datetime.fromtimestamp(game_ts, GAME_TZ).isoformat(timespec="seconds")


def _parse_iso(s: str) -> float:
    return datetime.fromisoformat(s).timestamp()


# ── 变化追踪（由 buff_tick.ON_VAR_CHANGE 调用） ─────────────────────────────

def track(player_id: str, var: str, applied: float) -> None:
    if not _cfg["enabled"] or not player_id or var not in VARS:
        return
    with _lock:
        if player_id not in _pending:
            return                      # 未登记（非 agent）的 player 不追踪
        _pending[player_id][var] = _pending[player_id].get(var, 0.0) + applied


def register(player_id: str, game_ts: float) -> None:
    with _lock:
        _pending.setdefault(player_id, {})
        _last_sync_game_ts.setdefault(player_id, game_ts)


def unregister(player_id: str) -> None:
    with _lock:
        _pending.pop(player_id, None)
        _last_sync_game_ts.pop(player_id, None)


def is_registered(player_id: str) -> bool:
    with _lock:
        return player_id in _pending


# ── 种子：GET /self/state ─────────────────────────────────────────────────────

def seed_player(player: dict, game_ts: float) -> bool:
    """用自我层状态覆盖本地七变量 / closeness / emotion_tags / mood_base / scene。失败返回 False。"""
    if not _cfg["enabled"]:
        return False
    agent = player.get("agent_id")
    if not agent:
        return False
    try:
        with _client() as c:
            r = c.get("/self/state", params={"agent": agent})
            r.raise_for_status()
            doc = r.json()
    except Exception as e:
        stats["last_error"] = f"seed: {e}"
        log.warning("self-layer seed failed for %s: %s", agent, e)
        return False
    from game.buff_tick import set_var, mood_baseline
    vars_ = doc.get("vars") or {}
    for v in VARS:
        if v in vars_:
            set_var(player, v, float(vars_[v]), track=False)
    if isinstance(doc.get("closeness"), dict):
        player["closeness"] = {k: float(x) for k, x in doc["closeness"].items()}
    ocean = doc.get("ocean") or {}
    if ocean:
        player["mood_base"] = mood_baseline(ocean.get("E", 50), ocean.get("N", 50))
    if doc.get("scene") in ("sandbox", "live"):
        player["scene"] = doc["scene"]
    tags = []
    for t in doc.get("emotion_tags") or []:
        try:
            remaining = (_parse_iso(t["until"]) - game_ts) * 1000.0
        except Exception:
            continue
        if remaining > 0:
            tags.append({"key": t["tag"], "value": 0.0, "mode": "timed", "remaining": remaining, "source": "self"})
    player["emotion_tags"] = tags
    with _lock:
        _pending[player["id"]] = {}
        _last_sync_game_ts[player["id"]] = game_ts
    stats["seeded"] += 1
    return True


# ── 出批（由 ticker 每 tick 调用） ────────────────────────────────────────────

def on_tick(game_ts: float, players: dict[str, dict]) -> int:
    """到 30 游戏秒的 player 出一批进队列。返回出批数。"""
    if not _cfg["enabled"]:
        return 0
    n = 0
    with _lock:
        for pid, last in list(_last_sync_game_ts.items()):
            if game_ts - last < SYNC_INTERVAL_GAME_S:
                continue
            p = players.get(pid)
            if p is None:
                continue
            delta = {k: round(v, 6) for k, v in _pending.get(pid, {}).items() if v != 0.0}
            _pending[pid] = {}
            _last_sync_game_ts[pid] = game_ts
            _queue.put({
                "player_id": pid,
                "agent": p.get("agent_id") or pid,
                "scene": p.get("scene", "sandbox"),
                "ts": _iso(game_ts),
                "vars_delta": delta,
                "snapshot": {v: float(p.get(v, 0.0)) for v in VARS},
            })
            n += 1
    return n


def _requeue(batch: dict) -> None:
    """发送失败：把 delta 合回 pending，下批一起重发。"""
    with _lock:
        pend = _pending.setdefault(batch["player_id"], {})
        for k, v in batch["vars_delta"].items():
            pend[k] = pend.get(k, 0.0) + v


def process_batch(batch: dict, client: httpx.Client | None = None) -> bool:
    """发送一批。成功返回 True 并处理 drift；失败 requeue 并返回 False。"""
    body = {
        "agent": batch["agent"], "scene": batch["scene"], "ts": batch["ts"],
        "vars_delta": batch["vars_delta"], "source": "sandbox_tick",
    }
    try:
        own = client is None
        c = client or _client()
        try:
            r = c.post("/self/state/delta", json=body)
            r.raise_for_status()
            resp = r.json()
        finally:
            if own:
                c.close()
    except Exception as e:
        stats["failed"] += 1
        stats["last_error"] = str(e)
        _requeue(batch)
        return False

    stats["sent"] += 1
    stats["last_ok_ts"] = time.time()
    stats["last_error"] = None
    remote = resp.get("vars") or {}
    drift = {v: float(remote[v]) - batch["snapshot"][v] for v in VARS if v in remote}
    stats["drift_last"] = {k: round(x, 4) for k, x in drift.items()}
    worst = max((abs(x) for x in drift.values()), default=0.0)
    stats["drift_max"] = max(stats["drift_max"], worst)
    if _cfg["snap"] and worst > SNAP_THRESHOLD:
        _apply_correction(batch["player_id"], drift)
    return True


def _apply_correction(player_id: str, drift: dict[str, float]) -> None:
    from game import world_state
    from game.buff_tick import add_var
    with world_state.STATE_LOCK:
        p = world_state._players.get(player_id)
        if p is None:
            return
        for v, d in drift.items():
            if abs(d) > 1e-9:
                add_var(p, v, d, track=False)
    stats["resyncs"] += 1
    log.info("self-sync snap %s: %s", player_id, {k: round(x, 3) for k, x in drift.items()})


def drain(client: httpx.Client | None = None, max_items: int = 1000) -> int:
    """同步处理队列（测试 / 关停用）。返回成功批数。"""
    ok = 0
    own = client is None
    c = client or _client()
    try:
        for _ in range(max_items):
            try:
                batch = _queue.get_nowait()
            except queue.Empty:
                break
            if process_batch(batch, c):
                ok += 1
    finally:
        if own:
            c.close()
    return ok


def _worker_loop() -> None:
    backoff = 1.0
    while not _stop.is_set():
        try:
            batch = _queue.get(timeout=0.5)
        except queue.Empty:
            continue
        if process_batch(batch):
            backoff = 1.0
        else:
            # 失败后清空同轮其余批（它们的 delta 也 requeue），等退避
            while True:
                try:
                    _requeue(_queue.get_nowait())
                except queue.Empty:
                    break
            _stop.wait(backoff)
            backoff = min(MAX_BACKOFF_S, backoff * 2)


def start() -> None:
    global _worker
    if not _cfg["enabled"]:
        return
    if _worker is not None and _worker.is_alive():
        return
    _stop.clear()
    _worker = threading.Thread(target=_worker_loop, name="self-sync", daemon=True)
    _worker.start()


def stop() -> None:
    global _worker
    _stop.set()
    if _worker is not None:
        _worker.join(timeout=2.0)
    _worker = None


def snapshot_stats() -> dict:
    with _lock:
        pending = {pid: dict(d) for pid, d in _pending.items()}
    return {**stats, "pending": pending, "queue": _queue.qsize()}


def _reset_for_tests() -> None:
    stop()
    with _lock:
        _pending.clear()
        _last_sync_game_ts.clear()
    while True:
        try:
            _queue.get_nowait()
        except queue.Empty:
            break
    stats.update({"sent": 0, "failed": 0, "seeded": 0, "resyncs": 0, "drift_max": 0.0,
                  "drift_last": {}, "last_error": None, "last_ok_ts": None})
    _cfg["transport"] = None
    _cfg["enabled"] = os.environ.get("SELF_SYNC", "1") not in ("0", "false", "False")
    _cfg["snap"] = True
    _cfg["url"] = os.environ.get("SELF_URL", "http://127.0.0.1:8100").rstrip("/")


# 挂钩到 buff_tick
from game import buff_tick as _bt  # noqa: E402
_bt.ON_VAR_CHANGE = track
