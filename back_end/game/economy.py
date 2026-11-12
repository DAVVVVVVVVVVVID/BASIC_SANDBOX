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
_balances: dict[str, int] = {}        # world-v1.1 §3 M-3 / M-5：按账号（agent_id）记余额，独立于在线；在线时 player.gold 是同一份数（ledger 同步）
_debts: dict[str, int] = {}           # 欠薪：payer 账号 -> 累计欠小千的工资
_opened: dict[str, float] = {}        # 账号 -> 开户游戏时刻（第一次 join / spawn）；日薪 / 房租只对开过户的账号


# ── 账户 ──────────────────────────────────────────────────────────────────────
def _online(account: str) -> dict | None:
    from game.world_state import _players
    from game.qq import account_of
    return next((p for p in _players.values() if account_of(p) == account), None)


def balance(account: str) -> int:
    p = _online(account)
    if p is not None:
        return int(p.get("gold", 0))
    if account not in _balances:
        _balances[account] = initial_gold(account)
    return int(_balances[account])


def on_join(player: dict) -> int:
    """join / spawn：已有账户的接着用（离线期间的入账都在），没有的按 initial_gold 开户。返回 gold。"""
    from game.qq import account_of
    from game.time_state import game_now_ts
    acc = account_of(player)
    if acc in _balances:
        player["gold"] = int(_balances[acc])
    else:
        _balances[acc] = int(player.get("gold", initial_gold(player.get("agent_id"))))
        player["gold"] = _balances[acc]
    if acc not in _opened and player.get("controller") == "agent":
        _opened[acc] = game_now_ts()
    return player["gold"]


def opened_at(account: str) -> float | None:
    return _opened.get(account)


def on_leave(player: dict) -> None:
    from game.qq import account_of
    _balances[account_of(player)] = int(player.get("gold", 0))


def credit_account(account: str, delta: int, kind: str | None = None, **fields) -> dict:
    """给账号加 / 扣钱：在线走 ledger(player)；离线直接记账户 + 流水（entity null）。"""
    p = _online(account)
    k = kind or ("income" if delta >= 0 else "expense")
    if p is not None:
        return ledger(k, p, delta, **fields)
    _balances[account] = balance(account) + int(delta)
    now = datetime.now()
    row = {"kind": k, "ts": now.isoformat(timespec="milliseconds"), **_base(), "account": account, "entity": None, "delta": int(delta), "balance": _balances[account], "offline": True, **fields}
    with _LOCK:
        with open(_dir() / f"{now.date().isoformat()}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    try:
        from routers.ws import hub
        hub.push_event({"type": "economy", **row})
    except Exception:
        pass
    return row


def accounts_view() -> dict:
    """/admin/metrics：所有已知账号余额（在线取 player.gold）。"""
    accs = set(_balances) | {k for k in _CFG.get("initial_gold", {}) if k != "default"} | set(_CFG.get("wages", {})) | set((_CFG.get("rent") or {}).get("items") or {})
    return {a: balance(a) for a in sorted(accs)}


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


def stream_income_amount(viewers_total: float | None, gifts_rmb: float | None) -> int:
    """v1.1 M-2：0.005 × 当场累计观看人次 + 礼物 1:1（旧 viewers_avg / gifts 走同一公式）。"""
    li = _CFG.get("live_income", {})
    return int(round(float(viewers_total or 0) * float(li.get("per_viewer", 0.005)) + float(gifts_rmb or 0) * float(li.get("gift_rate", 1.0))))


def synthetic_stream_income(player: dict, obj_id: str) -> dict | None:
    """W11 ②：直播机未接前，下播按 synthetic_range 随机入账并标 synthetic:true（live_income.synthetic=false 则不做）。"""
    li = _CFG.get("live_income", {})
    if not li.get("synthetic", False):
        return None
    import random
    from game.world_state import SANDBOX_SEED
    from game.time_state import game_now_iso
    r = random.Random(f"{SANDBOX_SEED}:stream:{player['id']}:{game_now_iso()}") if SANDBOX_SEED is not None else random.Random()
    vlo, vhi = li.get("synthetic_viewers", [1000, 3000]); glo, ghi = li.get("synthetic_gifts", [0, 20])
    viewers = r.randint(int(vlo), int(vhi)); gifts = r.randint(int(glo), int(ghi))
    amt = stream_income_amount(viewers, gifts)
    return ledger("income", player, amt, source="stream", synthetic=True, shop=obj_id, viewers_total=viewers, gifts_rmb=gifts)


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
    _balances[account_of(player)] = player["gold"]                 # v1.1：账户与在线 gold 同步
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
    """按 wages 日程结算（调用方持 STATE_LOCK）。v1.1：按账号结、不要求在线。daily：过 pay_at 且当日未付；
    hourly：weekdays 内、hours 区间每个整点付一次，payer 给则从 payer 账户扣（不够 → 照付、payer 记 wage_debt）。"""
    from game.time_state import _game_dt
    dt = _game_dt(gts)
    day = dt.strftime("%Y-%m-%d"); hm = dt.strftime("%H:%M")
    for acc, w in _CFG.get("wages", {}).items():
        if acc not in _opened:                                     # 只结「在这个镇开过户」的账号（join / spawn 过一次）；没来过的人不发钱
            continue
        if w["kind"] == "daily":
            key = f"{acc}:daily:{day}"
            if hm >= w["pay_at"] and key not in _paid:
                _paid[key] = day
                credit_account(acc, int(w["amount"]), "wage", label=w.get("label"), schedule=w["pay_at"])
        elif w["kind"] == "hourly":
            wd = w.get("weekdays")
            if wd and dt.isoweekday() not in wd:
                continue
            start, end = w["hours"]
            h0, h1 = int(start[:2]), int(end[:2])
            for h in range(h0 + 1, h1 + 1):                        # 每满 1 游戏小时结一次：整点 h0+1 … h1
                if hm >= f"{h:02d}:00":
                    key = f"{acc}:hourly:{day}T{h:02d}"
                    if key not in _paid:
                        _paid[key] = day
                        amt = int(w["amount"]); payer = w.get("payer")
                        if payer:
                            if balance(payer) >= amt:
                                credit_account(payer, -amt, "wage_paid", label=f"付{w.get('label')}", to=acc, hour=h)
                            else:
                                _debts[payer] = _debts.get(payer, 0) + amt
                                credit_account(payer, 0, "wage_debt", label=f"欠{w.get('label')}", to=acc, hour=h, owed=amt, owed_total=_debts[payer])
                        credit_account(acc, amt, "wage", label=w.get("label"), schedule=f"{start}-{end}", hour=h, payer=payer)
    from game import rent
    rent.on_tick(gts, players)

def export_state() -> dict:
    return {"paid": dict(_paid), "restocked": dict(_restocked), "balances": dict(_balances), "debts": dict(_debts), "opened": dict(_opened)}


def import_state(data: dict) -> None:
    _paid.clear(); _paid.update(data.get("paid") or {})
    _restocked.clear(); _restocked.update(data.get("restocked") or {})
    _balances.clear(); _balances.update({k: int(v) for k, v in (data.get("balances") or {}).items()})
    _debts.clear(); _debts.update({k: int(v) for k, v in (data.get("debts") or {}).items()})
    _opened.clear(); _opened.update({k: float(v) for k, v in (data.get("opened") or {}).items()})


def _reset_for_tests() -> None:
    _paid.clear(); _restocked.clear(); _balances.clear(); _debts.clear(); _opened.clear()
    from game import rent
    rent._reset_for_tests()
