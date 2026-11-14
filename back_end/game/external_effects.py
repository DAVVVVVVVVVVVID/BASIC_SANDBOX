"""
外部效果（B10 / B11）：object effect `{"type": "external", "key": "feed" | "live"}` 触发对自我层的调用。

  feed        GET  {SELF_URL}/self/feed?for=<agent_id>&n=8     → 信息流摘要（只有 digest 文字，原文不进沙盒）
  live.start  POST {SELF_URL}/self/live/start {"agent", "ts"}  → 开播（失败 → use 失败 reason=live_unavailable）
  live.stop   POST {SELF_URL}/self/live/stop  {"agent", "ts"}  → 下播（不可失败，只记日志；后台线程发送）

复用 self_sync 的 SELF_URL / SELF_TOKEN / transport 配置。超时 3 s。
"""

import logging
import threading
import time

import httpx

from game import self_sync

log = logging.getLogger("sandbox.external")

FEED_N = 8
FEED_ITEM_FIELDS = ("ts", "topic", "sentiment", "is_question", "is_song_request", "summary", "injection")
SYNC_STOP = False   # 测试：True 时 live.stop 同步发送

# ── 闭测 §2（world-v1.3.9）：直播机 → whale-live webhook。LIVE_URL 非空才发；start 同步 3 s 超时、失败只记日志不阻塞 use；stop 后台线程。
# payload（与 G 对定）：event / agent / player / object / object_type / town / ts / game_time / session_id / reason（仅 stop）；Authorization: Bearer $LIVE_TOKEN。
import os as _os
import uuid as _uuid
from datetime import datetime as _dt
_LIVE = {"url": (_os.environ.get("LIVE_URL") or "").rstrip("/"), "token": _os.environ.get("LIVE_TOKEN") or "", "transport": None, "timeout": 3.0}
_live_sessions: dict[str, str] = {}      # agent -> session_id（start/stop 同一个）
live_stats = {"start_sent": 0, "stop_sent": 0, "failed": 0, "last_error": None, "last_status": None}


def configure_live(url: str | None = None, token: str | None = None, transport=None) -> None:
    if url is not None: _LIVE["url"] = url.rstrip("/")
    if token is not None: _LIVE["token"] = token
    _LIVE["transport"] = transport


def live_webhook_enabled() -> bool:
    return bool(_LIVE["url"])


def _live_client() -> httpx.Client:
    headers = {"Authorization": f"Bearer {_LIVE['token']}"} if _LIVE["token"] else {}
    return httpx.Client(base_url=_LIVE["url"], headers=headers, timeout=_LIVE["timeout"], transport=_LIVE["transport"])


def _live_payload(event: str, player: dict, obj: dict | None, game_iso: str, session_id: str, reason: str | None) -> dict:
    p = {"event": event, "agent": player.get("agent_id"), "player": player["id"], "object": (obj or {}).get("id"), "object_type": (obj or {}).get("type"),
         "town": _os.environ.get("SANDBOX_TOWN") or "main", "ts": _dt.now().astimezone().isoformat(timespec="seconds"), "game_time": game_iso, "session_id": session_id}
    if event == "stop":
        p["reason"] = reason or "leave"
    return p


def _live_post(path: str, payload: dict) -> None:
    try:
        with _live_client() as c:
            r = c.post(path, json=payload)
            live_stats["last_status"] = r.status_code
            r.raise_for_status()
            live_stats["start_sent" if payload["event"] == "start" else "stop_sent"] += 1
    except Exception as e:
        live_stats["failed"] += 1; live_stats["last_error"] = str(e)[:200]
        log.warning("live webhook %s failed for %s: %s", path, payload.get("agent"), e)


def _ws_live(payload: dict) -> None:
    try:
        from routers.ws import hub
        hub.push_event({"type": "live", **payload})
    except Exception:
        pass


def live_webhook_start(player: dict, obj: dict | None, game_iso: str) -> str | None:
    """开播通知（同步，失败不阻塞）。返回 session_id。"""
    agent = _agent_for(player) or player["id"]
    sid = _uuid.uuid4().hex[:12]
    _live_sessions[agent] = sid
    payload = _live_payload("start", player, obj, game_iso, sid, None)
    if live_webhook_enabled():
        _live_post("/live/start", payload)
    _ws_live(payload)
    return sid


def live_webhook_stop(player: dict, obj: dict | None, game_iso: str, reason: str) -> None:
    agent = _agent_for(player) or player["id"]
    sid = _live_sessions.pop(agent, None) or _uuid.uuid4().hex[:12]
    payload = _live_payload("stop", player, obj, game_iso, sid, reason)
    if live_webhook_enabled():
        if SYNC_STOP:
            _live_post("/live/stop", payload)
        else:
            threading.Thread(target=_live_post, args=("/live/stop", payload), name="live-webhook-stop", daemon=True).start()
    _ws_live(payload)


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


def live_start(player: dict, game_iso: str, obj: dict | None = None) -> dict:
    """返回 {"ok": bool, "error"?: str, "resp"?: dict, "session_id"?: str}。
    没有 agent_id（人类玩家）→ 失败（§3.11 B4：阿蝉不能替她开播）；SELF_SYNC 关闭 → 失败。成功后再发 whale-live webhook（失败不影响结果）。"""
    agent = _agent_for(player)
    if not agent:
        return {"ok": False, "error": "no_agent_id: only agent players can stream"}
    if not self_sync.enabled():
        return {"ok": False, "error": "self_sync_disabled"}
    try:
        with self_sync._client() as c:
            r = c.post("/self/live/start", json={"agent": agent, "ts": game_iso})
            r.raise_for_status()
            resp = r.json()
    except Exception as e:
        log.warning("live.start failed for %s: %s", agent, e)
        return {"ok": False, "error": str(e)}
    sid = live_webhook_start(player, obj, game_iso)
    return {"ok": True, "resp": resp, "session_id": sid}


def _live_stop_send(agent: str, game_iso: str) -> None:
    try:
        with self_sync._client() as c:
            r = c.post("/self/live/stop", json={"agent": agent, "ts": game_iso})
            r.raise_for_status()
    except Exception as e:
        log.warning("live.stop failed for %s: %s", agent, e)


def live_stop(player: dict, game_iso: str, obj: dict | None = None, reason: str = "leave") -> None:
    """下播：不可失败，后台线程发送（SYNC_STOP=True 时同步，测试用）。自我层 + whale-live webhook（带 reason）。"""
    agent = _agent_for(player)
    if not agent or not self_sync.enabled():
        return
    if SYNC_STOP:
        _live_stop_send(agent, game_iso)
    else:
        threading.Thread(target=_live_stop_send, args=(agent, game_iso), name="live-stop", daemon=True).start()
    live_webhook_stop(player, obj, game_iso, reason)


# ── B18 / W10-4b 游戏机：D 的 brain 正式接口（report-D.md 5b / 6；地址 GAME_URL，默认 http://127.0.0.1:8110） ──
# use   → GET /game/state；alive=false 或 run_id 空 → POST /game/start {"by":"sandbox"}，每 GAME_POLL_S 轮询 /game/state
#         直到 alive=true（GAME_START_TIMEOUT_S 超时 → use 失败 reason game_unavailable）
# 局中  → GET /game/state（perceive / GET /player/{id}/state 时刷新，3 s 超时；失败保留旧值）
# leave → POST /game/stop {"by":"sandbox","shutdown":false}（存档、不关服；后台发送，不可失败）
# 局的开始 / 结束由 D 的 runner 自己写自我层（/self/game/session），沙盒不发；/healthz /event /metrics 仍可用但不再依赖。
import os as _os
GAME_URL = _os.environ.get("GAME_URL", "http://127.0.0.1:8110").rstrip("/")
GAME_TIMEOUT = 3.0
GAME_TRANSPORT = None          # 测试注入 httpx.MockTransport（假 D）
GAME_POLL_S = float(_os.environ.get("GAME_POLL_S", "5"))
GAME_START_TIMEOUT_S = float(_os.environ.get("GAME_START_TIMEOUT_S", "120"))
GAME_FIELDS = ("run_id", "alive", "deaths", "day", "phase", "time_in_phase", "health", "hunger", "sanity",
               "is_in_light", "goal", "latest_png", "usd_today", "server", "tick_age_s")
GAME_ENERGY_MIN = 25.0         # use 前置：energy ≥ 中（低于 needs 的 low 阈值就不坐下）


def _game_client() -> httpx.Client:
    return httpx.Client(base_url=GAME_URL, timeout=GAME_TIMEOUT, transport=GAME_TRANSPORT)


def _game_state(c: httpx.Client) -> dict | None:
    """GET /game/state → 只留 GAME_FIELDS；不可达 / 非 2xx → None。"""
    try:
        r = c.get("/game/state")
        r.raise_for_status()
        m = r.json()
        return {k: m.get(k) for k in GAME_FIELDS if k in m}
    except Exception:
        return None


def game_text(g: dict | None) -> str | None:
    """给感知的一句话：「饥荒第 {day} 天{phase}，HP {health}，正在{goal}」。"""
    if not g or g.get("status") not in ("playing",):
        return None
    phase = {"day": "白天", "dusk": "黄昏", "night": "夜里"}.get(str(g.get("phase") or ""), str(g.get("phase") or ""))
    parts = [f"饥荒第 {g.get('day')} 天{phase}" if g.get("day") is not None else "饥荒新一局"]
    if g.get("health") is not None:
        parts.append(f"HP {g['health']}")
    if g.get("goal"):
        parts.append(f"正在{g['goal']}")
    if g.get("alive") is False:
        parts.append("角色已死亡")
    return "，".join(parts)


def game_start(player: dict, game_iso: str) -> dict:
    """返回 {"ok": bool, "game": {...}, "error"?}。alive 的局直接接着玩；否则开新局并轮询到 alive。"""
    try:
        with _game_client() as c:
            st = _game_state(c)
            if st is None:
                return {"ok": False, "error": "brain_unreachable"}
            how = "joined"
            if not st.get("alive") or not st.get("run_id"):
                r = c.post("/game/start", json={"by": "sandbox"})
                r.raise_for_status()
                how = (r.json() or {}).get("how") or "started"
                deadline = time.time() + GAME_START_TIMEOUT_S
                st = _game_state(c)
                while not (st and st.get("alive") and st.get("run_id")):
                    if time.time() >= deadline:
                        return {"ok": False, "error": "start_timeout"}
                    time.sleep(GAME_POLL_S)
                    st = _game_state(c)
            game = {"status": "playing", "started_at": game_iso, "how": how, "brain_run_id": st.get("run_id"), **st}
            game["text"] = game_text(game)
            return {"ok": True, "game": game}
    except Exception as e:
        log.warning("game.start failed: %s", e)
        return {"ok": False, "error": str(e)}


def _game_stop_send(body: dict) -> None:
    try:
        with _game_client() as c:
            c.post("/game/stop", json=body).raise_for_status()
    except Exception as e:
        log.warning("game.stop failed: %s", e)


def game_end(player: dict, game_iso: str) -> None:
    """结束一局：POST /game/stop {"by":"sandbox","shutdown":false}；不可失败，后台发送（SYNC_STOP=True 同步，测试用）。"""
    body = {"by": "sandbox", "shutdown": False}
    if SYNC_STOP:
        _game_stop_send(body)
    else:
        threading.Thread(target=_game_stop_send, args=(body,), name="game-stop", daemon=True).start()


def game_refresh(player: dict) -> dict | None:
    """局中刷新 D 的 /game/state（perceive 时调用，3 s 超时；失败保留旧值）。"""
    g = player.get("game")
    if not g or g.get("status") != "playing":
        return g
    try:
        with _game_client() as c:
            st = _game_state(c)
            if st:
                g.update(st)
                g["text"] = game_text(g)
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
