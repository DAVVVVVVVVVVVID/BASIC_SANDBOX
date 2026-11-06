"""
外部效果（B10 / B11）：object effect `{"type": "external", "key": "feed" | "live"}` 触发对自我层的调用。

  feed        GET  {SELF_URL}/self/feed?for=<agent_id>&n=8     → 信息流摘要（只有 digest 文字，原文不进沙盒）
  live.start  POST {SELF_URL}/self/live/start {"agent", "ts"}  → 开播（失败 → use 失败 reason=live_unavailable）
  live.stop   POST {SELF_URL}/self/live/stop  {"agent", "ts"}  → 下播（不可失败，只记日志；后台线程发送）

复用 self_sync 的 SELF_URL / SELF_TOKEN / transport 配置。超时 3 s。
"""

import logging
import threading

import httpx

from game import self_sync

log = logging.getLogger("sandbox.external")

FEED_N = 8
FEED_ITEM_FIELDS = ("ts", "topic", "sentiment", "is_question", "is_song_request", "summary", "injection")
SYNC_STOP = False   # 测试：True 时 live.stop 同步发送


def _agent_for(player: dict) -> str | None:
    return player.get("agent_id")


def _sanitize_items(items: list) -> list[dict]:
    """只保留 digest 字段，丢掉任何 id / source / author / 原文。"""
    out = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        out.append({k: it.get(k) for k in FEED_ITEM_FIELDS if k in it})
    return out


def feed_text(digest: dict) -> str:
    if digest.get("status") != "ok":
        return "手机没信号，刷不出来。"
    items = digest.get("items") or []
    if not items:
        return "手机上没有新消息。"
    parts = []
    for it in items[:FEED_N]:
        s = (it.get("summary") or it.get("topic") or "").strip()
        if not s:
            continue
        tag = "（有人点歌）" if it.get("is_song_request") else ("（有人提问）" if it.get("is_question") else "")
        parts.append(s + tag)
    return f"手机上有 {len(items)} 条新动态：" + "；".join(parts) if parts else "手机上有新动态，但看不清说什么。"


def fetch_feed(player: dict, game_iso: str) -> dict:
    """返回 digest：{"status": "ok"|"no_signal", "items": [...], "digest_ts", "fetched_at", "error"?}。"""
    agent = _agent_for(player) or player.get("id")
    base = {"items": [], "digest_ts": None, "fetched_at": game_iso, "for": agent}
    if not self_sync.enabled():
        return {**base, "status": "no_signal", "error": "self_sync_disabled"}
    try:
        with self_sync._client() as c:
            r = c.get("/self/feed", params={"for": agent, "n": FEED_N})
            r.raise_for_status()
            doc = r.json()
    except Exception as e:
        log.warning("feed fetch failed for %s: %s", agent, e)
        return {**base, "status": "no_signal", "error": str(e)}
    return {**base, "status": "ok", "items": _sanitize_items(doc.get("items")), "digest_ts": doc.get("digest_ts")}


def live_start(player: dict, game_iso: str) -> dict:
    """返回 {"ok": bool, "error"?: str, "resp"?: dict}。
    没有 agent_id（人类玩家）→ 失败（§3.11 B4：阿蝉不能替她开播）；SELF_SYNC 关闭 → 失败。"""
    agent = _agent_for(player)
    if not agent:
        return {"ok": False, "error": "no_agent_id: only agent players can stream"}
    if not self_sync.enabled():
        return {"ok": False, "error": "self_sync_disabled"}
    try:
        with self_sync._client() as c:
            r = c.post("/self/live/start", json={"agent": agent, "ts": game_iso})
            r.raise_for_status()
            return {"ok": True, "resp": r.json()}
    except Exception as e:
        log.warning("live.start failed for %s: %s", agent, e)
        return {"ok": False, "error": str(e)}


def _live_stop_send(agent: str, game_iso: str) -> None:
    try:
        with self_sync._client() as c:
            r = c.post("/self/live/stop", json={"agent": agent, "ts": game_iso})
            r.raise_for_status()
    except Exception as e:
        log.warning("live.stop failed for %s: %s", agent, e)


def live_stop(player: dict, game_iso: str) -> None:
    """下播：不可失败，后台线程发送（SYNC_STOP=True 时同步，测试用）。"""
    agent = _agent_for(player)
    if not agent or not self_sync.enabled():
        return
    if SYNC_STOP:
        _live_stop_send(agent, game_iso)
    else:
        threading.Thread(target=_live_stop_send, args=(agent, game_iso), name="live-stop", daemon=True).start()


# ── B18 游戏机：D 的 brain API（假设契约，D12 未出；地址 GAME_URL，默认 http://127.0.0.1:8110） ─────────
# use  → GET {GAME_URL}/healthz 必须 ok，再 POST {GAME_URL}/event {type:"sandbox_session_start", agent, player_id, ts}
# leave → POST {GAME_URL}/event {type:"sandbox_session_end", ...}（后台发送，不可失败）
# 局内状态：GET {GAME_URL}/metrics 的 run_id / day / phase / health / hunger / sanity 进 player["game"]（perceive 的 game 字段）
# 结果由 D 自己 POST /self/game/session 写自我层，沙盒不转发。
import os as _os
GAME_URL = _os.environ.get("GAME_URL", "http://127.0.0.1:8110").rstrip("/")
GAME_TIMEOUT = 3.0
GAME_TRANSPORT = None          # 测试注入 httpx.MockTransport（假 D）
GAME_FIELDS = ("run_id", "ticks", "day", "phase", "health", "hunger", "sanity", "deaths")


def _game_client() -> httpx.Client:
    return httpx.Client(base_url=GAME_URL, timeout=GAME_TIMEOUT, transport=GAME_TRANSPORT)


def _game_metrics(c: httpx.Client) -> dict:
    try:
        r = c.get("/metrics")
        r.raise_for_status()
        m = r.json()
        return {k: m.get(k) for k in GAME_FIELDS if k in m}
    except Exception:
        return {}


def game_start(player: dict, game_iso: str) -> dict:
    """返回 {"ok": bool, "game": {...}, "error"?}。"""
    try:
        with _game_client() as c:
            h = c.get("/healthz")
            h.raise_for_status()
            hj = h.json()
            if not hj.get("ok", True):
                return {"ok": False, "error": "brain_not_ok"}
            ev = {"type": "sandbox_session_start", "agent": player.get("agent_id") or player.get("name"),
                  "player_id": player["id"], "ts": game_iso, "tick": hj.get("ticks", 0)}
            r = c.post("/event", json=ev)
            r.raise_for_status()
            game = {"status": "playing", "started_at": game_iso, "brain_run_id": hj.get("run_id"), **_game_metrics(c)}
            return {"ok": True, "game": game}
    except Exception as e:
        log.warning("game.start failed: %s", e)
        return {"ok": False, "error": str(e)}


def _game_end_send(ev: dict) -> None:
    try:
        with _game_client() as c:
            c.post("/event", json=ev).raise_for_status()
    except Exception as e:
        log.warning("game.end failed: %s", e)


def game_end(player: dict, game_iso: str) -> None:
    """结束一局：不可失败，后台发送（SYNC_STOP=True 同步，测试用）。"""
    ev = {"type": "sandbox_session_end", "agent": player.get("agent_id") or player.get("name"),
          "player_id": player["id"], "ts": game_iso, "started_at": (player.get("game") or {}).get("started_at")}
    if SYNC_STOP:
        _game_end_send(ev)
    else:
        threading.Thread(target=_game_end_send, args=(ev,), name="game-end", daemon=True).start()


def game_refresh(player: dict) -> dict | None:
    """局中刷新 D 的 metrics（perceive 时调用，3 s 超时；失败保留旧值）。"""
    g = player.get("game")
    if not g or g.get("status") != "playing":
        return g
    try:
        with _game_client() as c:
            g.update(_game_metrics(c))
    except Exception:
        pass
    return g


# ── B12 freeform：自我层裁决 ──────────────────────────────────────────────────

ADJUDICATE_TIMEOUT = 15.0     # 模型调用，比 feed/live 的 3 s 长


def adjudicate(player: dict, text: str, target: str | None, context: str | None) -> dict:
    """
    POST {SELF_URL}/self/adjudicate {agent, text, target?, context?}
    → 原样返回自我层的 {success, narration, effects[], feasible?, skipped?, injection?, reason?}
    不可达 / 非 2xx → {"success": False, "reason": "adjudication_unavailable" | 自我层给的 reason, ...}
    """
    agent = _agent_for(player) or player.get("name", player.get("id"))
    if not self_sync.enabled():
        return {"success": False, "narration": "", "effects": [], "reason": "adjudication_unavailable", "error": "self_sync_disabled"}
    body = {"agent": agent, "text": text}
    if target:
        body["target"] = target
    if context:
        body["context"] = context[:1000]
    try:
        headers = {"content-type": "application/json"}
        if self_sync._cfg["token"]:
            headers["Authorization"] = f"Bearer {self_sync._cfg['token']}"
        with httpx.Client(base_url=self_sync._cfg["url"], headers=headers, timeout=ADJUDICATE_TIMEOUT,
                          transport=self_sync._cfg["transport"]) as c:
            r = c.post("/self/adjudicate", json=body)
        if r.status_code == 429:
            detail = (r.json() or {}).get("detail") if r.headers.get("content-type", "").startswith("application/json") else None
            inner = detail.get("detail") if isinstance(detail, dict) else {}
            return {"success": False, "narration": "", "effects": [], "reason": "rate_limited",
                    "retry_after": (inner or {}).get("retry_after")}
        if r.status_code == 404:
            return {"success": False, "narration": "", "effects": [], "reason": "adjudication_unavailable", "error": "persona_not_found"}
        r.raise_for_status()
        res = r.json()
        if not isinstance(res, dict):
            raise ValueError("bad response")
        return res
    except Exception as e:
        log.warning("adjudicate failed for %s: %s", agent, e)
        return {"success": False, "narration": "", "effects": [], "reason": "adjudication_unavailable", "error": str(e)}


def external_keys(obj: dict) -> set[str]:
    return {e.get("key") for e in obj.get("effects", []) if e.get("type") == "external"}
