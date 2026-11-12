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
import hashlib
import os
_DEFAULT_PATH = Path(__file__).with_name("economy.json")
ECONOMY_PATH = Path(os.environ.get("SANDBOX_ECONOMY_PATH") or _DEFAULT_PATH)      # X5：按镇覆盖（towns.yaml sandbox_env 指路径）
_CFG: dict = {}
_INFO: dict = {}


def reload(path: Path | str | None = None) -> dict:
    """（重新）加载 economy.json；返回 {path, sha256}。X5：每镇可指独立文件，manifest 记 sha。"""
    global ECONOMY_PATH
    if path is not None:
        ECONOMY_PATH = Path(path)
    raw = ECONOMY_PATH.read_bytes()
    _CFG.clear(); _CFG.update(json.loads(raw.decode("utf-8")))
    _INFO.clear(); _INFO.update({"path": str(ECONOMY_PATH), "sha256": hashlib.sha256(raw).hexdigest(), "default": ECONOMY_PATH == _DEFAULT_PATH})
    return dict(_INFO)


def info() -> dict:
    return dict(_INFO)


reload()
_paid: dict[str, str] = {}            # "account:daily:YYYY-MM-DD" / "account:hourly:YYYY-MM-DDTHH" -> ts（防重复结算）


def cfg() -> dict:
    return _CFG


def initial_gold(agent_id: str | None) -> int:
    ig = _CFG.get("initial_gold", {})
    return int(ig.get(agent_id or "", ig.get("default", 0)))


def shop_for(obj_type: str) -> dict | None:
    return _CFG.get("shops", {}).get(obj_type)


def shop_listing(obj_type: str, stock: dict | None = None) -> list[dict] | None:
    """object 的 shop[]：[{item, name, price, sell, stock}]（price 买价 / sell 收购价，null = 不卖 / 不收；stock null = 不限量）。"""
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
                     "sell": d.get("sell") if item in s.get("buys", []) else None,
                     "stock": (stock or {}).get(item) if stock is not None else None})
    return rows


def initial_stock(obj_type: str) -> dict | None:
    """商店按 shops[].daily_supply（缺省 stock）；冰箱给空表（内容由 food.init_contents 按物品 id 填，stock 是派生计数）；其余 None。"""
    s = shop_for(obj_type)
    if s is not None:
        return {k: int(v) for k, v in (s.get("daily_supply") or s.get("stock") or {}).items()}
    if obj_type == "fridge":
        return {}
    return None


def daily_supply(obj_type: str) -> dict | None:
    s = shop_for(obj_type)
    if s is None:
        return None
    return {k: int(v) for k, v in (s.get("daily_supply") or s.get("stock") or {}).items()}


_restocked: dict[str, str] = {}      # "<obj_id>:<day>" -> hm


def restock_tick(gts: float, objects: list[dict]) -> int:
    """每日 restock_at：商店 restock_mode=reset（v1.1 默认）→ stock := daily_supply（固定上新、卖完即止）；legacy → 补到水位只补不减。
    冰箱只在 fridge.restock_enabled 时 +restock_qty 不超过 max（v1.1 默认关）。返回补货物品数。调用方持 STATE_LOCK。"""
    from game.time_state import _game_dt
    dt = _game_dt(gts); day = dt.strftime("%Y-%m-%d"); hm = dt.strftime("%H:%M")
    n = 0
    for o in objects:
        if o.get("stock") is None:
            continue
        s = shop_for(o["type"])
        if s is not None:
            at = s.get("restock_at", "08:00"); target = s.get("daily_supply") or s.get("stock") or {}
        elif o["type"] == "fridge":
            f = _CFG.get("fridge", {})
            if not f.get("restock_enabled", False):
                continue
            at = f.get("restock_at", "08:00"); target = None
        else:
            continue
        key = f"{o['id']}:{day}"
        if hm < at or key in _restocked:
            continue
        _restocked[key] = hm
        before = dict(o["stock"])
        if target is not None:
            if (s.get("restock_mode") or "reset") == "reset":
                o["stock"] = {item: int(lvl) for item, lvl in target.items()}
            else:
                for item, lvl in target.items():
                    o["stock"][item] = max(int(o["stock"].get(item, 0)), int(lvl))
        else:
            from game import food, inventory
            f = _CFG.get("fridge", {}); item = f.get("consumes", "ingredients")
            cur = int(o["stock"].get(item, 0)); add = max(0, min(int(f.get("restock_qty", 2)), int(f.get("max", 4)) - cur))
            if add:
                food.store(o, item, add, inventory.expires_at_for(item, gts))
        if o["stock"] != before:                       # 按配置定时补货是确定性的，不记 external
            n += 1
    return n


def stream_income_amount(viewers_avg: float | None, gifts: float | None) -> int:
    li = _CFG.get("live_income", {})
    return int(round(float(viewers_avg or 0) * float(li.get("per_viewer", 0.5)) + float(gifts or 0) * float(li.get("gift_rate", 1.0))))


def synthetic_stream_income(player: dict, obj_id: str) -> dict | None:
    """W11 ②：直播机未接前，下播按 synthetic_range 随机入账并标 synthetic:true（live_income.synthetic=false 则不做）。"""
    li = _CFG.get("live_income", {})
    if not li.get("synthetic", False):
        return None
    import random
    from game.world_state import SANDBOX_SEED
    from game.time_state import game_now_iso
    lo, hi = li.get("synthetic_range", [20, 60])
    r = random.Random(f"{SANDBOX_SEED}:stream:{player['id']}:{game_now_iso()}") if SANDBOX_SEED is not None else random.Random()
    amt = r.randint(int(lo), int(hi))
    return ledger("income", player, amt, source="stream", synthetic=True, shop=obj_id, viewers_avg=None, gifts=None)


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
    return {"paid": dict(_paid), "restocked": dict(_restocked)}


def import_state(data: dict) -> None:
    _paid.clear(); _paid.update(data.get("paid") or {})
    _restocked.clear(); _restocked.update(data.get("restocked") or {})


def _reset_for_tests() -> None:
    _paid.clear(); _restocked.clear()
