"""
闭测周 §5.2 interventions.jsonl（A 定格式 v1：whale docs/interventions-format.md）——凡不是 agent 自己决策却改变了世界 / 角色的事，记一行。
沙盒侧自动记：achan_login / achan_logout（主播操控的阿蝉上线 / 离线 / dnd 开关）、achan_chat（阿蝉参与的一段当面对话）、achan_qq（阿蝉发的每条 QQ，只记长度）、
achan_knock（阿蝉敲门 / 应门 / 开门 / 给物）、set_time（夹具拨钟）、fixture（每次 /admin/scenario）、restart（沙盒启动）。
位置：run/data/<town>/interventions/<YYYY-MM-DD>.jsonl（墙钟日期）；SANDBOX_INTERVENTIONS_DIR 可覆盖。红线：不记弹幕原文 / uid / 昵称 / 凭证；阿蝉说的话只记长度。
"""
from __future__ import annotations

import json
import os
import secrets
import threading
from datetime import datetime
from pathlib import Path

SCHEMA_VERSION = 1
_LOCK = threading.Lock()
_MEM: list[dict] = []        # 测试 / 诊断用的最近若干行
_MEM_MAX = 500


def town() -> str:
    return os.environ.get("SANDBOX_TOWN") or "main"


def _dir() -> Path:
    ov = os.environ.get("SANDBOX_INTERVENTIONS_DIR")
    if ov:
        p = Path(ov)
    else:
        from game.paths import data_dir
        base = data_dir().resolve()
        root = next((a for a in [base, *base.parents] if a.name == "data"), None)     # …/run/data/sandbox → …/run/data/<town>/interventions
        p = (root / town() / "interventions") if root is not None else (base / "interventions")
    p.mkdir(parents=True, exist_ok=True)
    return p


def is_streamer(player: dict | None) -> bool:
    """主播本人操控的人类玩家（阿蝉）：human + dnd_auto。"""
    return bool(player) and player.get("controller") == "human" and bool(player.get("dnd_auto"))


def _game_time() -> str | None:
    try:
        from game.time_state import game_now_iso
        return game_now_iso()
    except Exception:
        return None


def log(kind: str, actor: str, targets: list[str], summary: str, *, payload: dict | None = None, ref: dict | None = None,
        source: str = "sandbox", duration_s: float | None = None, reversible: bool | None = None, note: str | None = None) -> dict:
    now = datetime.now().astimezone()
    row = {"id": f"iv-{now.strftime('%Y%m%d')}-{secrets.token_hex(3)}", "ts": now.isoformat(timespec="seconds"), "game_time": _game_time(),
           "town": town(), "kind": kind, "actor": actor, "targets": list(targets) or ["*"], "summary": summary[:120], "source": source,
           "schema_version": SCHEMA_VERSION}
    if ref: row["ref"] = ref
    if payload is not None: row["payload"] = payload
    if duration_s is not None: row["duration_s"] = int(duration_s)
    if reversible is not None: row["reversible"] = reversible
    if note: row["note"] = note
    try:
        with _LOCK:
            with open(_dir() / f"{now.date().isoformat()}.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            _MEM.append(row)
            if len(_MEM) > _MEM_MAX:
                del _MEM[: len(_MEM) - _MEM_MAX]
    except Exception:
        pass
    return row


def _agent_targets(players: list[dict]) -> list[str]:
    return [p.get("agent_id") or p["id"] for p in players if p]


# ── 阿蝉相关的便捷入口 ─────────────────────────────────────────────────────────
def achan_login(player: dict, via: str, **extra) -> None:
    log("achan_login", "streamer", [player.get("agent_id") or player["id"]], f"阿蝉上线接管（{via}）",
        payload={"player_id": player["id"], "via": via, "dnd": bool(player.get("dnd")), **extra})


def achan_logout(player: dict, reason: str, **extra) -> None:
    log("achan_logout", "streamer", [player.get("agent_id") or player["id"]], f"阿蝉离线 / 勿扰（{reason}）",
        payload={"player_id": player["id"], "reason": reason, "dnd": bool(player.get("dnd")), "position": dict(player.get("position") or {}), **extra})


def achan_qq(player: dict, peer: str, chars: int, group: bool) -> None:
    log("achan_qq", "streamer", [peer], f"阿蝉发 QQ 给 {peer}（{chars} 字）", payload={"channel": "qq", "peer": peer, "chars": int(chars), "group": bool(group)})


def achan_knock(player: dict, what: str, targets: list[str], **payload) -> None:
    log("achan_knock", "streamer", targets, f"阿蝉{what}", payload={"channel": "knock", "what": what, **payload})


def achan_chat(player: dict, others: list[dict], turns: int, minutes: float, room_id: str) -> None:
    log("achan_chat", "streamer", _agent_targets(others), f"阿蝉当面与 {'、'.join(_agent_targets(others)) or '?'} 聊了一段（{turns} 轮）",
        payload={"channel": "face", "turns": int(turns), "minutes": round(minutes, 1), "room_id": room_id}, duration_s=minutes * 60)


def recent(n: int = 50) -> list[dict]:
    return list(_MEM[-n:])


def _reset_for_tests() -> None:
    _MEM.clear()
