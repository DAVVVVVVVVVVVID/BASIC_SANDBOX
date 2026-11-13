"""
写歌委托（W11 ①，economy.json `commissions`）。
{id, kind: "song", client: 账号, client_name, fee, title, status: open|delivered, created_at, delivered_at?, deliverer?}
- 来源：POST /admin/commission（C / A / 直播侧手动下单）+ 每日 refresh_at 以 daily_p 概率自动出一单（公告栏「委托」）。
- 交付：give 一首 song 给委托人（meta.commission_id 对上，或该委托人最早的 open 单）→ 酬金入账（ledger income / song_fee）、委托人对交付者亲密度 +closeness_bonus。
- 读：GET /commissions?player=、use 公告栏的 result.commissions。
"""
import uuid

_items: dict[str, dict] = {}
_refreshed: dict[str, str] = {}      # day -> id|"none"


def cfg() -> dict:
    from game.economy import cfg as _c
    return _c().get("commissions", {})


def _rng(*parts):
    import random
    from game.world_state import SANDBOX_SEED
    return random.Random(":".join(str(p) for p in (SANDBOX_SEED, *parts))) if SANDBOX_SEED is not None else random.Random()


def create(client: str, kind: str = "song", fee: int | None = None, title: str | None = None, source: str = "admin") -> dict:
    from game.qq import display_name, resolve_account
    from game.time_state import game_now_iso
    c = cfg()
    acc = resolve_account(client) or client
    if fee is None:
        lo, hi = c.get("song_fee", [150, 300])
        fee = _rng("fee", acc, len(_items)).randint(int(lo), int(hi))
    from game.time_state import game_now_ts
    from game.food import _iso
    exp_days = float(c.get("expire_days", 0) or 0)
    cm = {"id": f"c{len(_items)+1:03d}_{uuid.uuid4().hex[:4]}", "kind": kind, "client": acc, "client_name": display_name(acc),
          "fee": int(fee), "title": title or f"{display_name(acc)}想要一首歌", "status": "open", "created_at": game_now_iso(), "source": source,
          "expires_at": _iso(game_now_ts() + exp_days * 86400.0) if exp_days else None}      # v1.1 M-6：3 天过期
    _items[cm["id"]] = cm
    from game import external_log
    external_log.log("commission", None, action="open", commission_kind=cm["kind"], **{k: cm[k] for k in ("id", "client", "fee", "title", "source")})
    try:
        from routers.ws import hub
        hub.push_event({"type": "commission", "event": "open", **cm})
    except Exception:
        pass
    return cm


def open_items(client: str | None = None) -> list[dict]:
    return [dict(c) for c in _items.values() if c["status"] == "open" and (client is None or c["client"] == client)]


def all_items() -> list[dict]:
    return [dict(c) for c in _items.values()]


def deliver(giver: dict, target: dict | str, meta: dict | None, via: str = "give") -> dict | None:
    """give cd 时调用（调用方持 STATE_LOCK）。target 可以是在场的委托人 player，或（solo 门口 / 柜台交付）委托人账号字符串。
    对上委托 → 酬金入账 + 委托人亲密度（委托人在线才记）；返回委托或 None。"""
    from game.qq import account_of
    from game.buff_tick import add_closeness
    from game import economy, external_log
    from game.time_state import game_now_iso
    acc = target if isinstance(target, str) else account_of(target)
    target_p = None if isinstance(target, str) else target
    if target_p is None:
        from game.world_state import _players
        target_p = next((q for q in _players.values() if account_of(q) == acc), None)
    cm = None
    cid = (meta or {}).get("commission_id")
    if cid and cid in _items and _items[cid]["status"] == "open" and _items[cid]["client"] == acc:
        cm = _items[cid]
    else:
        opens = [c for c in _items.values() if c["status"] == "open" and c["client"] == acc]
        cm = min(opens, key=lambda c: c["created_at"]) if opens else None
    if cm is None:
        return None
    cm["status"] = "delivered"; cm["delivered_at"] = game_now_iso(); cm["deliverer"] = account_of(giver); cm["via"] = via
    economy.ledger("income", giver, int(cm["fee"]), source="song_fee", commission=cm["id"], peer=target_p["id"] if target_p else acc, label=cm["title"], via=via)
    bonus = float(cfg().get("closeness_bonus", 15))
    if target_p is not None:
        add_closeness(target_p, giver["id"], bonus)
    external_log.log("commission", giver["id"], action="deliver", id=cm["id"], client=cm["client"], fee=cm["fee"], via=via)
    try:
        from routers.ws import hub
        hub.push_event({"type": "commission", "event": "deliver", **cm})
    except Exception:
        pass
    return dict(cm)


def on_tick(gts: float) -> None:
    from game.time_state import _game_dt, game_now_iso
    from datetime import datetime
    c = cfg()
    for cm in _items.values():                                       # v1.1 M-6：过期
        if cm["status"] == "open" and cm.get("expires_at") and datetime.fromisoformat(cm["expires_at"]).timestamp() <= gts:
            cm["status"] = "expired"; cm["expired_at"] = game_now_iso()
            from game import external_log
            external_log.log("commission", None, action="expire", id=cm["id"], client=cm["client"], fee=cm["fee"])
            try:
                from routers.ws import hub
                hub.push_event({"type": "commission", "event": "expire", **cm})
            except Exception:
                pass
    dt = _game_dt(gts); day = dt.strftime("%Y-%m-%d"); hm = dt.strftime("%H:%M")
    if day in _refreshed or hm < c.get("refresh_at", "08:00"):
        return
    _refreshed[day] = "none"
    if len(open_items()) >= int(c.get("max_open", 3)):
        return
    r = _rng("commission", day)
    if r.random() < float(c.get("daily_p", 0.3)):
        clients = c.get("clients") or []
        if clients:
            cm = create(r.choice(clients), source="daily")
            _refreshed[day] = cm["id"]


def export_state() -> dict:
    return {"items": {k: dict(v) for k, v in _items.items()}, "refreshed": dict(_refreshed)}


def import_state(d: dict) -> None:
    _items.clear(); _refreshed.clear()
    _items.update(d.get("items") or {}); _refreshed.update(d.get("refreshed") or {})


def _reset_for_tests() -> None:
    _items.clear(); _refreshed.clear()
