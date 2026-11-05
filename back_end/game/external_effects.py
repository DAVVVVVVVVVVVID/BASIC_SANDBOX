"""
外部效果（B10 / B11）：object effect `{"type": "external", "key": "feed" | "live"}` 触发对自我层的调用。

  feed        GET  {SELF_URL}/self/feed?for=<agent_id>&n=8     → 信息流摘要（只有 digest 文字，原文不进沙盒）
  live.start  POST {SELF_URL}/self/live/start {"agent", "ts"}  → 开播（失败 → use 失败 reason=live_unavailable）
  live.stop   POST {SELF_URL}/self/live/stop  {"agent", "ts"}  → 下播（不可失败，只记日志；后台线程发送）

复用 self_sync 的 SELF_URL / SELF_TOKEN / transport 配置。超时 3 s。
"""

import logging
import threading

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
    """返回 {"ok": bool, "error"?: str, "resp"?: dict}。没有 agent_id（人类玩家）只做本地切换。"""
    agent = _agent_for(player)
    if not agent or not self_sync.enabled():
        return {"ok": True, "local_only": True}
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


def external_keys(obj: dict) -> set[str]:
    return {e.get("key") for e in obj.get("effects", []) if e.get("type") == "external"}
