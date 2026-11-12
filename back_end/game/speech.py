"""
靴近即可说（Q6，实验 X4 变体；总控 whale-68 11-07）：POST /action say {text}。
曼哈顿 ≤ SAY_RANGE 格、同一 sector（室内外不隔墙喊）的其他在场玩家在下一次 perceive 的 nearby_speech[] 里看到 {from, from_name, text, ts}；
不开房间、不走邀请。每句进聊天 JSONL（kind: say）与 ws {type:"say"}。听者队列最多 SAY_QUEUE_MAX 条，perceive 读过即清。
"""
SAY_RANGE = 2
SAY_MAX_TEXT = 200
SAY_QUEUE_MAX = 20

_inbox: dict[str, list[dict]] = {}       # listener id -> [{from, from_name, text, ts, game_time}]


def say(entity_id: str, text: str) -> tuple[dict | None, str | None]:
    from game import world_state as ws, chat_log
    from game.time_state import game_now_iso
    p = ws._players.get(entity_id)
    if p is None:
        return None, "player_not_found"
    text = (text or "").strip()
    if not text:
        return None, "empty_text"
    if len(text) > SAY_MAX_TEXT:
        return None, "text_too_long"
    px, py = p["position"]["x"], p["position"]["y"]
    my_sector = ws.get_zone_at(px, py).get("sector")
    heard = []
    msg = {"from": entity_id, "from_name": p.get("name"), "text": text, "ts": game_now_iso(), "position": {"x": px, "y": py}}
    for q in ws._players.values():
        if q["id"] == entity_id or not ws.is_present(q):
            continue
        qx, qy = q["position"]["x"], q["position"]["y"]
        if abs(qx - px) + abs(qy - py) <= SAY_RANGE and ws.get_zone_at(qx, qy).get("sector") == my_sector:
            box = _inbox.setdefault(q["id"], [])
            box.append(dict(msg))
            if len(box) > SAY_QUEUE_MAX:
                del box[: len(box) - SAY_QUEUE_MAX]
            heard.append(q["id"])
    ws.mark_input(entity_id)
    if heard:                                                       # world-v1.1 §4.1：线下 say 往来按 15 分钟窗口 +8
        from game import social
        from game.time_state import game_now_ts
        social.mark_say(game_now_ts(), p, [ws._players[h] for h in heard if h in ws._players])
    chat_log.log_say(entity_id, p.get("name"), heard, text, p.get("controller", "human"), msg["position"])
    try:
        from routers.ws import hub
        hub.push_event({"type": "say", "from": entity_id, "from_name": p.get("name"), "text": text, "position": msg["position"], "heard_by": heard})
    except Exception:
        pass
    return {"message": text, "heard_by": heard, "heard_count": len(heard), "range": SAY_RANGE, "position": msg["position"]}, None


def take(entity_id: str) -> list[dict]:
    """perceive 用：取出并清空该听者的队列。"""
    return _inbox.pop(entity_id, [])


def _reset_for_tests() -> None:
    _inbox.clear()
