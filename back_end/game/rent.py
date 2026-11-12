"""
房租（world-v1.1 §3.3，economy.json `rent`）：
- 每月 due_day 日 due_at 自动扣（铺面与住房分两笔，items 按账号）；账户独立于在线（economy.accounts）。
- 钱不够：记欠租 rent_due（不赶人、不部分扣）；欠租期间每日 due_at：在线者心情 overdue_mood_per_day、房东（镇公所 town_hall）QQ 催一条；
  之后任何时刻余额够了就自动补齐并清掉（ws rent cleared）。
- 扣前 notice_days 天：rent 视图 due_in_days ≤ notice_days（C 感知用），每日 due_at 一条 ws rent due_soon。
- rent.enabled=false（bench 短场景）整段关闭。人类玩家不交。
"""
from __future__ import annotations

from datetime import datetime, timedelta

_status: dict[str, dict[str, str]] = {}       # account -> {"YYYY-MM": "paid"|"due"}
_due: dict[str, dict] = {}                    # account -> {amount, period, since}
_daily_done: dict[str, str] = {}              # account -> 已做当日欠租处理的日期
_notice_done: dict[str, str] = {}             # account -> 已发 due_soon 的日期


def cfg() -> dict:
    from game.economy import cfg as _c
    return _c().get("rent", {}) or {}


def enabled() -> bool:
    return bool(cfg().get("enabled", False))


def items_for(account: str) -> list[dict]:
    return [dict(x) for x in (cfg().get("items") or {}).get(account, [])]


def total_for(account: str) -> int:
    return sum(int(x.get("amount", 0)) for x in items_for(account))


def _hm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def _due_dt(year: int, month: int) -> datetime:
    from game.time_state import GAME_TZ
    d = int(cfg().get("due_day", 1)); h, m = (cfg().get("due_at") or "08:00").split(":")
    return datetime(year, month, d, int(h), int(m), tzinfo=GAME_TZ)


def next_due(now: datetime) -> datetime:
    """下一次扣租时刻：本月的若还没过（且本期没处理过）就是本月，否则下月。"""
    this = _due_dt(now.year, now.month)
    if now < this:
        return this
    y, mth = (now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1)
    return _due_dt(y, mth)


def _push(ev: dict) -> None:
    try:
        from routers.ws import hub
        hub.push_event({"type": "rent", **ev})
    except Exception:
        pass


def _charge(account: str, amount: int, period: str, players_by_acc: dict, label: str) -> None:
    from game import economy
    items = items_for(account)
    for it in items:
        economy.credit_account(account, -int(it.get("amount", 0)), "rent", label=label, rent_kind=it.get("kind"), period=period, landlord=cfg().get("landlord", "town_hall"))
    p = players_by_acc.get(account)
    if p is not None:
        from game import world_state
        world_state._pending_messages[p["id"]] = f"交了这个月的房租 {amount} 金币。"
    _push({"event": "paid" if label == "rent" else "cleared", "account": account, "entity": p["id"] if p else None, "amount": amount, "period": period,
           "balance": economy.balance(account)})


def on_tick(gts: float, players: dict) -> None:
    """调用方持 STATE_LOCK。"""
    if not enabled():
        return
    from game import economy, qq
    from game.time_state import _game_dt
    from game.qq import account_of
    from game.buff_tick import add_var
    now = _game_dt(gts); period = now.strftime("%Y-%m"); day = now.strftime("%Y-%m-%d")
    due_at = cfg().get("due_at") or "08:00"
    by_acc = {account_of(p): p for p in players.values() if p.get("controller") == "agent"}
    for acc in (cfg().get("items") or {}):
        opened = economy.opened_at(acc)
        if opened is None:                               # 只对在这个镇开过户的账号
            continue
        total = total_for(acc)
        if total <= 0:
            continue
        st = _status.setdefault(acc, {})
        due_dt = _due_dt(now.year, now.month)
        if period not in st and due_dt.timestamp() < opened:        # 开户前就到期的那个月不收（世界中途启动）
            st[period] = "n/a"
        # ① 到期扣租（本期还没处理）
        if period not in st and now >= due_dt:
            if economy.balance(acc) >= total and acc not in _due:
                st[period] = "paid"
                _charge(acc, total, period, by_acc, "rent")
            else:
                st[period] = "due"
                owed = int(_due.get(acc, {}).get("amount", 0)) + total
                _due[acc] = {"amount": owed, "period": period, "since": _due.get(acc, {}).get("since") or now.isoformat(timespec="seconds")}
                p = by_acc.get(acc)
                if p is not None:
                    from game import world_state
                    world_state._pending_messages[p["id"]] = f"房租 {total} 金币没交上，欠着了。"
                _push({"event": "overdue", "account": acc, "entity": p["id"] if p else None, "amount": owed, "period": period, "balance": economy.balance(acc)})
                from game import external_log
                external_log.log("rent", p["id"] if p else None, account=acc, action="overdue", amount=owed, period=period, balance=economy.balance(acc))
                _daily_done[acc] = day                 # 当天不再另催
        # ② 欠租：余额够了就补齐；否则每日 due_at 心情 −3 + 镇公所 QQ 催
        if acc in _due:
            owed = int(_due[acc]["amount"])
            if economy.balance(acc) >= owed:
                dp = _due.pop(acc)
                economy.credit_account(acc, -owed, "rent", label="rent_cleared", period=dp["period"], landlord=cfg().get("landlord", "town_hall"))
                p = by_acc.get(acc)
                if p is not None:
                    from game import world_state
                    world_state._pending_messages[p["id"]] = f"补上了欠的房租 {owed} 金币。"
                _push({"event": "cleared", "account": acc, "entity": p["id"] if p else None, "amount": owed, "period": dp["period"], "balance": economy.balance(acc)})
            elif _hm(now) >= due_at and _daily_done.get(acc) != day:
                _daily_done[acc] = day
                p = by_acc.get(acc)
                if p is not None:
                    add_var(p, "mood", float(cfg().get("overdue_mood_per_day", -3)))
                qq.system_send(cfg().get("landlord", "town_hall"), acc,
                               f"{qq.display_name(acc)}，你还欠着房租 {owed} 金币（{_due[acc]['period']} 起），余额 {economy.balance(acc)}，请尽快补上。——镇公所")
        # ③ 扣前 notice_days 天：每日一条 due_soon
        nd = next_due(now)
        days_left = (nd - now).total_seconds() / 86400.0
        if acc not in _due and period not in st and 0 < days_left <= int(cfg().get("notice_days", 3)) and _hm(now) >= due_at and _notice_done.get(acc) != day:
            _notice_done[acc] = day
            p = by_acc.get(acc)
            _push({"event": "due_soon", "account": acc, "entity": p["id"] if p else None, "amount": total, "due_at": nd.isoformat(timespec="seconds"),
                   "due_in_days": int(days_left) + (1 if days_left % 1 else 0), "balance": economy.balance(acc)})


def view(account: str, now_gts: float | None = None) -> dict | None:
    """GET /player 的 rent 字段；没有房租项（人类）为 None。"""
    if not enabled() or not items_for(account):
        return None
    from game import economy
    from game.time_state import _game_dt, game_now_ts
    now = _game_dt(game_now_ts() if now_gts is None else now_gts)
    nd = next_due(now)
    due = _due.get(account)
    return {"amount": total_for(account), "items": items_for(account), "landlord": cfg().get("landlord", "town_hall"),
            "due_at": nd.isoformat(timespec="seconds"), "due_in_days": max(0, int((nd - now).total_seconds() // 86400)),
            "overdue": due is not None, "owed": int(due["amount"]) if due else 0, "since": due["since"] if due else None,
            "balance": economy.balance(account)}


def export_state() -> dict:
    return {"status": {k: dict(v) for k, v in _status.items()}, "due": {k: dict(v) for k, v in _due.items()},
            "daily_done": dict(_daily_done), "notice_done": dict(_notice_done)}


def import_state(d: dict) -> None:
    _status.clear(); _due.clear(); _daily_done.clear(); _notice_done.clear()
    _status.update({k: dict(v) for k, v in (d.get("status") or {}).items()}); _due.update({k: dict(v) for k, v in (d.get("due") or {}).items()})
    _daily_done.update(d.get("daily_done") or {}); _notice_done.update(d.get("notice_done") or {})


def _reset_for_tests() -> None:
    _status.clear(); _due.clear(); _daily_done.clear(); _notice_done.clear()
