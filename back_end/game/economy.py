"""
金币与流水（W10 ④）。数值全读 economy.json / items.json。

- 玩家 gold 在 player["gold"]；每笔变动 ledger(...) 追加 data/economy/<date>.jsonl：
  {kind: buy|sell|eat|give|income|wage|adjust, ts, game_time, town, map_version, seed, account, entity, delta, balance, item?, qty?, price?, shop?, peer?, source?, label?}
- 日薪 / 时薪由 ticker 调 on_tick(gts, players) 按 wages 日程结算；写歌酬金 / 直播收入由外部 POST /admin/income。
- 商店：object_types 里 shop_counter / fish_stall / bar 的 shop[] 来自 shops（营业时间沿用物品 open_hours）。
"""
import json
import threading
from datetime import datetime
from pathlib import Path

from game.paths import data_dir

_LOCK = threading.Lock()
_CFG: dict = json.load(open(Path(__file__).with_name("economy.json"), encoding="utf-8"))
_paid: dict[str, str] = {}            # "account:daily:YYYY-MM-DD" / "account:hourly:YYYY-MM-DDTHH" -> ts（防重复结算）


def cfg() -> dict:
    return _CFG


def initial_gold(agent_id: str | None) -> int:
    ig = _CFG.get("initial_gold", {})
    return int(ig.get(agent_id or "", ig.get("default", 0)))


def shop_for(obj_type: str) -> dict | None:
    return _CFG.get("shops", {}).get(obj_type)


def shop_listing(obj_type: str) -> list[dict] | None:
    """object 的 shop[]：[{item, name, price, sell}]（price 买价 / sell 收购价，null = 不卖 / 不收）。"""
    s = shop_for(obj_type)
    if s is None:
        return None
    from game.inventory import catalog
    cat = catalog()
    rows = []
    for item in sorted(set(s.get("sells", [])) | set(s.get("buys", []))):
        d = cat.get(item, {})
        rows.append({"item": item, "name": d.get("name", item),
                     "price": d.get("price") if item in s.get("sells", []) else None,
                     "sell": d.get("sell") if item in s.get("buys", []) else None})
    return rows


def _dir() -> Path:
    p = data_dir() / "economy"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _base() -> dict:
    try:
        from game.world_state import TOWN, MAP_VERSION, SANDBOX_SEED
        from game.time_state import game_now_iso
        return {"town": TOWN, "map_version": MAP_VERSION, "seed": SANDBOX_SEED, "game_time": game_now_iso()}
    except Exception:
        return {"town": None, "map_version": None, "seed": None, "game_time": None}


def ledger(kind: str, player: dict, delta: int, **fields) -> dict:
    """改余额并记一行流水。调用方须持 STATE_LOCK。"""
    from game.qq import account_of
    player["gold"] = int(player.get("gold", 0)) + int(delta)
    now = datetime.now()
    row = {"kind": kind, "ts": now.isoformat(timespec="milliseconds"), **_base(), "account": account_of(player),
           "entity": player["id"], "delta": int(delta), "balance": player["gold"], **fields}
    with _LOCK:
        with open(_dir() / f"{now.date().isoformat()}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    try:
        from routers.ws import hub
        hub.push_event({"type": "economy", **row})
    except Exception:
        pass
    return row


def on_tick(gts: float, players: dict) -> None:
    """按 wages 日程结算（调用方持 STATE_LOCK）。daily：游戏时刻过 pay_at 且当日未付；hourly：hours 区间内每个整点付一次。"""
    from game.time_state import _game_dt
    from game.qq import account_of
    dt = _game_dt(gts)
    day = dt.strftime("%Y-%m-%d"); hm = dt.strftime("%H:%M")
    for p in players.values():
        acc = account_of(p)
        w = _CFG.get("wages", {}).get(acc)
        if not w:
            continue
        if w["kind"] == "daily":
            key = f"{acc}:daily:{day}"
            if hm >= w["pay_at"] and key not in _paid:
                _paid[key] = day
                ledger("wage", p, int(w["amount"]), label=w.get("label"), schedule=w["pay_at"])
        elif w["kind"] == "hourly":
            start, end = w["hours"]
            h0, h1 = int(start[:2]), int(end[:2])
            for h in range(h0 + 1, h1 + 1):                        # 每满 1 游戏小时结一次：整点 h0+1 … h1
                if hm >= f"{h:02d}:00":
                    key = f"{acc}:hourly:{day}T{h:02d}"
                    if key not in _paid:
                        _paid[key] = day
                        ledger("wage", p, int(w["amount"]), label=w.get("label"), schedule=f"{start}-{end}", hour=h)

def export_state() -> dict:
    return {"paid": dict(_paid)}


def import_state(data: dict) -> None:
    _paid.clear(); _paid.update(data.get("paid") or {})


def _reset_for_tests() -> None:
    _paid.clear()
