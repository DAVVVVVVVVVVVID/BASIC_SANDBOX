"""
社交 / 娱乐来源（world-v1.1 §4.1，needs.json conversation / qq）：
- 聊天房：active 房间里在场的参与者按在房计时 social +32/h、fun +4/h（on_tick）。
- say 通道：15 分钟窗口内有「2 格内的 say 往来」（说者与听者各算一次）→ 每人每窗口 +8（mark_say）。
- QQ：每条 +1，每人每小时最多计 12 条（qq_credit）。
- 下播：+10（live_session_end）。
"""
from __future__ import annotations

_say_credit: dict[str, int] = {}          # entity -> 已记过的 15 分钟窗口号
_qq_credit: dict[str, tuple[int, int]] = {}   # entity -> (小时号, 本小时已计条数)


def _conv() -> dict:
    from game import needs_cfg as needs
    return needs.conversation()


def on_tick(gts: float, delta_ms: float, players: dict) -> None:
    """聊天房在房计时。调用方持 STATE_LOCK。"""
    if delta_ms <= 0:
        return
    from game import chat_state
    from game.buff_tick import add_var
    c = _conv()
    dt_h = delta_ms / 3_600_000.0
    s_rate = float(c.get("social_per_hour", 0.0)); f_rate = float(c.get("fun_per_hour", 0.0))
    if not (s_rate or f_rate):
        return
    for room in list(chat_state._chat_rooms.values()):
        if room.get("status") != "active":
            continue
        for eid in room.get("participants") or []:
            p = players.get(eid)
            if p is None:
                continue
            if s_rate:
                add_var(p, "social", s_rate * dt_h)
            if f_rate:
                add_var(p, "fun", f_rate * dt_h)


def mark_say(gts: float, speaker: dict, hearers: list[dict]) -> list[str]:
    """一次有人听到的 say：本窗口内还没记过的参与者各 +say_social_per_window。返回记了的 id。"""
    from game.buff_tick import add_var
    c = _conv()
    win_s = max(60.0, float(c.get("say_window_min", 15)) * 60.0)
    win = int(gts // win_s)
    credited = []
    for p in [speaker, *hearers]:
        if _say_credit.get(p["id"]) == win:
            continue
        _say_credit[p["id"]] = win
        add_var(p, "social", float(c.get("say_social_per_window", 0.0)))
        credited.append(p["id"])
    return credited


def qq_credit(gts: float, player: dict, n_messages: int = 1) -> float:
    """QQ 每条 +social_per_message，每人每小时最多 max_messages_per_hour 条。返回实际加的 social。"""
    from game import needs_cfg as needs
    from game.buff_tick import add_var
    q = needs.qq()
    per = float(q.get("social_per_message", 0.0)); cap = int(q.get("max_messages_per_hour", 0))
    if per <= 0 or n_messages <= 0:
        return 0.0
    hour = int(gts // 3600)
    h, used = _qq_credit.get(player["id"], (hour, 0))
    if h != hour:
        used = 0
    allowed = n_messages if cap <= 0 else max(0, min(n_messages, cap - used))
    _qq_credit[player["id"]] = (hour, used + allowed)
    if allowed:
        add_var(player, "social", per * allowed)
    return per * allowed


def live_session_end(player: dict) -> float:
    from game import needs_cfg as needs
    from game.buff_tick import add_var
    v = needs.live_session_social()
    if v:
        add_var(player, "social", v)
    return v


def export_state() -> dict:
    return {"say_credit": dict(_say_credit), "qq_credit": {k: list(v) for k, v in _qq_credit.items()}}


def import_state(d: dict) -> None:
    _say_credit.clear(); _say_credit.update({k: int(v) for k, v in (d.get("say_credit") or {}).items()})
    _qq_credit.clear(); _qq_credit.update({k: (int(v[0]), int(v[1])) for k, v in (d.get("qq_credit") or {}).items()})


def _reset_for_tests() -> None:
    _say_credit.clear(); _qq_credit.clear()
