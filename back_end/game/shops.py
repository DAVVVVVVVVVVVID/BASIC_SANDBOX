"""
商店系统（world-v1.4.11 起；whale docs/systems/shops-system.md「主播 11-19 修改」；草案 docs/shops-phase1-sandbox.md）。

第一期：
- 进货：系统 QQ 账号「镇外批发 · 周叔」（supplier_zhou）。杂货店老板 / 小克发 QQ 下单 → 规则读单 → 周叔回确认单（meta.order）
  → 下单人回「确认」→ 扣店主账户 → 22:00 截单 → deliver_at（次日 / 后天 07:30）进 counter 库房（每种上限 storeroom_cap，超出退款）。
- 账本：三本（grocery / restaurant / fish_stall），按店主账户归属；read_ledger 动作（viewers）与 GET /shops/{shop_id}/ledger（导播）。
- 库房视图：counter 物件带 warehouse {stock, capacity, incoming}。
状态进检查点：orders / ledger / seq。
"""
import json
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path

DAY_S = 86400.0
_CFG_PATH = Path(__file__).parent / "shops.json"
_cfg: dict = {}
_orders: dict[str, dict] = {}
_ledger: dict[str, list[dict]] = {}     # shop → entries（按时间）
_seq = {"n": 0}

_CN_NUM = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def cfg() -> dict:
    if not _cfg:
        _cfg.update(json.loads(_CFG_PATH.read_text(encoding="utf-8")))
    return _cfg


def sup() -> dict:
    return cfg()["supplier"]


def _gts() -> float:
    from game.time_state import game_now_ts
    return game_now_ts()


def _iso(gts: float) -> str:
    from game.food import _iso as f
    return f(gts)


def _dt(gts: float) -> datetime:
    from game.time_state import _game_dt
    return _game_dt(gts)


def _item_name(item: str) -> str:
    from game.inventory import item_def
    return (item_def(item) or {}).get("name", item)


# ── 账本 ─────────────────────────────────────────────────────────────────────
def shop_of_account(account: str | None) -> str | None:
    for k, v in cfg()["ledgers"].items():
        if v.get("owner") == account:
            return k
    return None


def shop_of_object(obj_id: str | None) -> str | None:
    for k, v in cfg()["ledgers"].items():
        if obj_id in (v.get("objects") or []):
            return k
    return None


def record(shop: str | None, kind: str, *, who: dict | str | None = None, item: str | None = None, qty: int | None = None,
           unit_price: float | None = None, amount: int = 0, note: str | None = None, ref: dict | None = None, gts: float | None = None) -> dict | None:
    """记一笔账（amount 对店主：收入正、支出负）。"""
    if shop not in cfg()["ledgers"]:
        return None
    gts = _gts() if gts is None else gts
    if isinstance(who, dict):
        who_id, who_name = who.get("id"), who.get("name")
    else:
        from game.qq import display_name
        who_id, who_name = who, (display_name(who) if who else None)
    _seq["n"] += 1
    e = {"seq": _seq["n"], "ts": datetime.now().isoformat(timespec="seconds"), "game_time": _iso(gts), "day": _day_key(gts), "kind": kind,
         "who": who_id, "who_name": who_name, "item": item, "item_name": _item_name(item) if item else None, "qty": qty,
         "unit_price": unit_price, "amount": int(amount)}
    if note:
        e["note"] = note
    if ref:
        e["ref"] = ref
    _ledger.setdefault(shop, []).append(e)
    _trim(shop, gts)
    try:
        from game import external_log
        external_log.log("ledger", who_id, shop=shop, **{k: v for k, v in e.items() if k not in ("ts", "who")})
    except Exception:
        pass
    return e


def _day_key(gts: float) -> str:
    return (_dt(gts) - timedelta(hours=4)).strftime("%Y-%m-%d")


def _trim(shop: str, gts: float) -> None:
    keep = int(cfg().get("ledger_keep_days", 14))
    cut = (_dt(gts) - timedelta(hours=4) - timedelta(days=keep)).strftime("%Y-%m-%d")
    rows = _ledger.get(shop) or []
    if rows and rows[0]["day"] < cut:
        _ledger[shop] = [r for r in rows if r["day"] >= cut]


def on_credit(account: str | None, payer: dict, delta: int, fields: dict) -> None:
    """economy_actions._credit_account 的钩子：钱进 / 出店主账户 = 一笔卖出 / 收购。"""
    shop = shop_of_account(account)
    if shop is None or not delta:
        return
    qty = fields.get("qty")
    unit = (fields.get("price") if fields.get("price") is not None else (round(abs(delta) / qty, 2) if qty else None))
    record(shop, "sale" if delta > 0 else "purchase", who=payer, item=fields.get("item"), qty=qty, unit_price=unit, amount=int(delta),
           note=fields.get("source"), ref={k: fields[k] for k in ("shop", "fish", "fish_id", "order_id", "dish") if fields.get(k) is not None} or None)


def _stock_of(shop: str) -> dict:
    from game import world_state
    out: dict = {}
    for oid in cfg()["ledgers"][shop].get("objects") or []:
        o = world_state.get_object_by_id(oid)
        if o is None:
            continue
        if o.get("type") == "fish_stall":
            for m in o.get("listings") or []:
                out[m["species"]] = out.get(m["species"], 0) + 1
        else:
            for k, v in (o.get("stock") or {}).items():
                out[k] = out.get(k, 0) + int(v)
    return out


def ledger_view(shop: str, days: int = 1) -> dict:
    gts = _gts()
    days = max(1, min(int(days or 1), int(cfg().get("ledger_keep_days", 14))))
    today = _dt(gts) - timedelta(hours=4)
    keys = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)][::-1]
    rows = [r for r in (_ledger.get(shop) or []) if r["day"] in keys]
    summ = []
    for k in keys:
        rr = [r for r in rows if r["day"] == k]
        rev = sum(r["amount"] for r in rr if r["amount"] > 0)
        cost = -sum(r["amount"] for r in rr if r["amount"] < 0)
        summ.append({"date": k, "revenue": rev, "cost": cost, "gross": rev - cost, "stock": _stock_of(shop) if k == keys[-1] else None})
    return {"shop": shop, "name": cfg()["ledgers"][shop]["name"], "days": summ, "entries": [{k: v for k, v in r.items() if k != "day"} for r in rows]}


def can_read(player: dict, shop: str) -> bool:
    from game.qq import account_of
    return account_of(player) in (cfg()["ledgers"].get(shop, {}).get("viewers") or [])


# ── 进货：读单 ───────────────────────────────────────────────────────────────
def _num(tok: str) -> int | None:
    if tok.isdigit():
        return int(tok)
    if all(c in _CN_NUM for c in tok):
        if tok == "十":
            return 10
        if tok.startswith("十"):
            return 10 + _CN_NUM[tok[1]]
        if len(tok) == 2 and tok[1] == "十":
            return _CN_NUM[tok[0]] * 10
        if len(tok) == 3 and tok[1] == "十":
            return _CN_NUM[tok[0]] * 10 + _CN_NUM[tok[2]]
        if len(tok) == 1:
            return _CN_NUM[tok]
    return None


def parse_order(text: str) -> list[dict]:
    """规则读单：「面包 10、食材×12」「10 个面包」「面包十份」。返回 [{item, qty}]（同货合并）。"""
    aliases = sorted(sup()["aliases"].items(), key=lambda kv: -len(kv[0]))
    num = r"(\d+|[零一二两三四五六七八九十]{1,3})"
    unit = r"(?:个|份|袋|只|包|盒|斤|件|条|箱)?"
    got: dict[str, int] = {}
    t = text
    for alias, item in aliases:
        for m in list(re.finditer(re.escape(alias) + r"\s*[×xX*]?\s*" + num + unit, t)) + list(re.finditer(num + r"\s*" + unit + r"\s*" + re.escape(alias), t)):
            n = _num(m.group(1))
            if n and n > 0:
                got[item] = got.get(item, 0) + n
                t = t[:m.start()] + " " * (m.end() - m.start()) + t[m.end():]
    return [{"item": k, "qty": v} for k, v in got.items() if k in sup()["costs"]]


def _is_confirm(text: str) -> bool:
    s = re.sub(r"[\s。！!，,.~～]+", "", text or "")
    return s in sup()["confirm_words"] or s.lower() in [w.lower() for w in sup()["confirm_words"]]


def _deliver_gts(confirm_gts: float) -> float:
    dt = _dt(confirm_gts)
    hh, mm = map(int, sup()["cutoff"].split(":"))
    dh, dm = map(int, sup()["deliver_at"].split(":"))
    days = 1 if (dt.hour, dt.minute) < (hh, mm) else 2
    if dt.hour < 4:                                                # 凌晨下的单属于前一天（04:00 换日）
        days -= 1
    d = (dt + timedelta(days=days)).replace(hour=dh, minute=dm, second=0, microsecond=0)
    return d.timestamp()


def _order_public(o: dict) -> dict:
    return {k: v for k, v in o.items() if not k.endswith("_gts")}


def _reply(to_acc: str, text: str, order: dict | None) -> None:
    from game import qq
    qq.system_send(sup()["account"], to_acc, text, meta={"order": _order_public(order)} if order else None)


def on_supplier_message(player: dict, msg: dict) -> None:
    """qq.send 发给周叔之后调用（调用方持 STATE_LOCK）。"""
    from game.qq import account_of
    me = account_of(player)
    text = msg.get("text") or ""
    if me not in sup()["allowed"]:
        _reply(me, "我只跟杂货店做生意。", None); return
    gts = _gts()
    _expire(gts)
    if _is_confirm(text):
        q = sorted([o for o in _orders.values() if o["ordered_by"] == me and o["status"] == "quoted"], key=lambda o: o["quoted_at_gts"])
        if not q:
            _reply(me, "没有等你确认的单子。要什么直接写，比如「面包 10、食材 12」。", None); return
        confirm(q[-1], player, gts); return
    items = parse_order(text)
    if not items:
        _reply(me, "没看懂要什么，按「面包 10、食材 12」这样写一下？", None); return
    costs = sup()["costs"]
    lines = [{"item": i["item"], "name": _item_name(i["item"]), "qty": int(i["qty"]), "unit_cost": costs[i["item"]]} for i in items]
    goods = sum(l["qty"] * l["unit_cost"] for l in lines); freight = int(sup()["freight"])
    oid = f"po-{_dt(gts).strftime('%Y%m%d')}-{uuid.uuid4().hex[:4]}"
    o = {"order_id": oid, "status": "quoted", "shop": sup()["shop"], "items": lines, "goods": goods, "freight": freight, "total": goods + freight,
         "ordered_by": me, "payer": sup()["payer"], "quoted_at": _iso(gts), "quoted_at_gts": gts,
         "expires_at": _iso(gts + float(sup()["quote_ttl_min"]) * 60), "expires_at_gts": gts + float(sup()["quote_ttl_min"]) * 60,
         "deliver_at": _iso(_deliver_gts(gts)), "deliver_at_gts": _deliver_gts(gts)}
    _orders[oid] = o
    when = "明早" if _dt(o["deliver_at_gts"]).date() == (_dt(gts) - timedelta(hours=4)).date() + timedelta(days=1) else "后天早上"
    body = "、".join(f"{l['name']} ×{l['qty']}" for l in lines)
    _reply(me, f"收到：{body}，货款 ¥{goods} + 运费 ¥{freight} = ¥{o['total']}，{when} {sup()['deliver_at']} 前送到。回复「确认」就下单（30 分钟内有效）。", o)
    _log_order(o, "quoted")


def confirm(o: dict, player: dict, gts: float) -> None:
    from game import economy
    from game.qq import account_of
    payer_acc = o["payer"]
    bal = economy.balance(payer_acc)
    if bal < o["total"]:
        o["status"] = "failed"; o["failed_reason"] = "insufficient_funds"
        _reply(o["ordered_by"], f"店里账上钱不够，这单 ¥{o['total']}，还差 ¥{o['total'] - bal}。", o); _log_order(o, "failed"); return
    o["deliver_at_gts"] = _deliver_gts(gts); o["deliver_at"] = _iso(o["deliver_at_gts"])
    economy.credit_account(payer_acc, -int(o["goods"]), "expense", peer=sup()["account"], source="supplier_goods", order_id=o["order_id"])
    economy.credit_account(payer_acc, -int(o["freight"]), "expense", peer=sup()["account"], source="supplier_freight", order_id=o["order_id"])
    o["status"] = "confirmed"; o["confirmed_at"] = _iso(gts); o["confirmed_by"] = account_of(player)
    shop = o["shop"]
    for l in o["items"]:
        record(shop, "purchase", who=player, item=l["item"], qty=l["qty"], unit_price=l["unit_cost"], amount=-l["qty"] * l["unit_cost"], ref={"order_id": o["order_id"]}, gts=gts)
    record(shop, "freight", who=player, amount=-int(o["freight"]), note="运费", ref={"order_id": o["order_id"]}, gts=gts)
    when = "明早" if _dt(o["deliver_at_gts"]).date() == (_dt(gts) - timedelta(hours=4)).date() + timedelta(days=1) else "后天早上"
    _reply(o["ordered_by"], f"好的，{when} {sup()['deliver_at']} 送到。", o)
    _log_order(o, "confirmed")


def _expire(gts: float) -> None:
    for o in _orders.values():
        if o["status"] == "quoted" and gts >= o["expires_at_gts"]:
            o["status"] = "expired"; _log_order(o, "expired")


def on_tick(gts: float, players: dict, objects: list[dict]) -> None:
    """调用方持 STATE_LOCK：报价过期、到点送货。"""
    _expire(gts)
    for o in list(_orders.values()):
        if o["status"] == "confirmed" and gts >= o["deliver_at_gts"]:
            _deliver(o, gts, objects)


def _deliver(o: dict, gts: float, objects: list[dict]) -> None:
    from game import economy
    counter = next((x for x in objects if x.get("type") == sup()["object_type"]), None)
    if counter is None:
        return
    cap = int(sup()["storeroom_cap"])
    st = counter.setdefault("stock", {})
    got, refund = [], 0
    for l in o["items"]:
        cur = int(st.get(l["item"], 0)); room = max(0, cap - cur); n = min(room, int(l["qty"]))
        st[l["item"]] = cur + n
        got.append({"item": l["item"], "name": l["name"], "qty": n})
        if n < l["qty"]:
            r = (int(l["qty"]) - n) * int(l["unit_cost"]); refund += r
            record(o["shop"], "refund", who=sup()["account"], item=l["item"], qty=int(l["qty"]) - n, unit_price=l["unit_cost"], amount=r,
                   note=f"库房每种上限 {cap}，多的退回", ref={"order_id": o["order_id"]}, gts=gts)
    if refund:
        economy.credit_account(o["payer"], refund, "income", peer=sup()["account"], source="supplier_refund", order_id=o["order_id"])
    from game.world_state import refresh_shop_views
    refresh_shop_views()
    o["status"] = "delivered"; o["delivered_at"] = _iso(gts); o["delivered"] = got
    body = "、".join(f"{g['name']} ×{g['qty']}" for g in got if g["qty"]) or "（库房满了，全退了）"
    msg = f"货到了：{body}，放进库房了。" + (f"库房放不下的退了 ¥{refund}。" if refund else "")
    for acc in {o["ordered_by"], o["payer"]}:
        _reply(acc, msg, o)
    _log_order(o, "delivered")


def _log_order(o: dict, event: str) -> None:
    try:
        from game import external_log
        external_log.log("supplier", None, action=event, **_order_public(o))
        from routers.ws import hub
        hub.push_event({"type": "supplier_order", "event": event, "order": _order_public(o)})
    except Exception:
        pass


def orders_view(shop: str | None = None, status: str | None = None) -> list[dict]:
    rows = [o for o in _orders.values() if (not shop or o["shop"] == shop) and (not status or o["status"] == status)]
    return [_order_public(o) for o in sorted(rows, key=lambda o: o["quoted_at_gts"])]


def pending_for(player: dict) -> list[dict] | None:
    from game.qq import account_of
    if account_of(player) not in sup()["allowed"]:
        return None
    return [_order_public(o) for o in sorted(_orders.values(), key=lambda o: o["quoted_at_gts"]) if o["status"] in ("quoted", "confirmed")]


def warehouse_view(obj: dict) -> dict | None:
    if obj.get("type") != sup()["object_type"]:
        return None
    inc = [{"order_id": o["order_id"], "items": [{"item": l["item"], "qty": l["qty"]} for l in o["items"]], "eta": o["deliver_at"]}
           for o in sorted(_orders.values(), key=lambda o: o["deliver_at_gts"]) if o["status"] == "confirmed"]
    return {"stock": {k: int(v) for k, v in (obj.get("stock") or {}).items()}, "capacity": int(sup()["storeroom_cap"]), "incoming": inc}


# ── 检查点 ───────────────────────────────────────────────────────────────────
def export_state() -> dict:
    return {"orders": json.loads(json.dumps(_orders)), "ledger": json.loads(json.dumps(_ledger)), "seq": _seq["n"]}


def import_state(d: dict | None) -> None:
    _orders.clear(); _ledger.clear(); _seq["n"] = 0
    if not d:
        return
    _orders.update(d.get("orders") or {}); _ledger.update(d.get("ledger") or {}); _seq["n"] = int(d.get("seq") or 0)


def post_load(objects: list[dict]) -> None:
    """旧检查点：鱼摊里 v1.4.8 以前的计数库存（没有鱼种 / 重量，买不了）清掉。"""
    for o in objects:
        if o.get("type") == "fish_stall" and (o.get("stock") or {}).get("fish"):
            o["stock"].pop("fish", None)


def _reset_for_tests() -> None:
    import_state(None); _cfg.clear()
