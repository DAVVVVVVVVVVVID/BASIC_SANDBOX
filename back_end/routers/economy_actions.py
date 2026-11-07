"""
W10 ④ 金币与背包动作：buy / sell / eat / give（挂进 routers/actions._HANDLERS）。
payload 字段按 E 的假设：item | item_id、object_id | objectId（缺省 = 面前的物品）、target（player id / agent_id / 名字）、qty。
失败 reason：insufficient_funds / no_shop / shop_closed / not_for_sale / not_buying / unknown_item / no_item /
            inventory_full / not_edible / target_not_found / target_too_far / no_object / use_disabled。
数值全读 game/items.json 与 game/economy.json。每笔金币变动写 data/economy/<date>.jsonl（kinds=economy 导出）。
"""
from models.action import ActionResponse
from game import inventory, economy
from game.world_state import (
    STATE_LOCK, _players, get_object_at, get_object_by_id, open_state, mark_input,
)
from game.buff_tick import add_var, add_closeness

_DIR = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}


def _item(payload: dict) -> str | None:
    return payload.get("item") or payload.get("item_id") or payload.get("type")


def _qty(payload: dict) -> int:
    try:
        return max(1, int(payload.get("qty") or payload.get("count") or 1))
    except (TypeError, ValueError):
        return 1


def _adjacent(player: dict, obj: dict) -> bool:
    px, py = player["position"]["x"], player["position"]["y"]
    return any(abs(t["x"] - px) <= 1 and abs(t["y"] - py) <= 1 for t in obj["tiles"])


def _shop_object(player: dict, payload: dict) -> tuple[dict | None, str | None]:
    oid = payload.get("object_id") or payload.get("objectId")
    if oid:
        obj = get_object_by_id(oid)
        if obj is None:
            return None, "no_object"
        if not _adjacent(player, obj):
            return None, "object_too_far"
    else:
        dx, dy = _DIR[player["facing"]]
        obj = get_object_at(player["position"]["x"] + dx, player["position"]["y"] + dy)
        if obj is None:
            return None, "no_object"
    if economy.shop_for(obj["type"]) is None:
        return None, "no_shop"
    is_open, opens_at = open_state(obj)
    if not is_open:
        return obj, "shop_closed"
    return obj, None


def _owner_player(obj_type: str) -> dict | None:
    from game.qq import account_of
    s = economy.shop_for(obj_type) or {}
    owner = s.get("owner")
    for p in _players.values():
        if owner and account_of(p) == owner:
            return p
    return None


def _item_fields(item: str, qty: int, price: int | None = None) -> dict:
    d = inventory.item_def(item) or {}
    out = {"item": item, "item_name": d.get("name", item), "qty": qty}
    if price is not None:
        out["price"] = price
    return out


def handle_buy(entity_id: str, payload: dict) -> ActionResponse:
    with STATE_LOCK:
        p = _players.get(entity_id)
        if p is None:
            return ActionResponse(success=False, type="buy", reason="player_not_found")
        if not p.get("canUse", True):
            return ActionResponse(success=False, type="buy", reason="use_disabled")
        obj, err = _shop_object(p, payload)
        if err:
            res = {"objectId": obj["id"]} if obj else None
            if err == "shop_closed":
                res["opens_at"] = open_state(obj)[1]; res["openHours"] = obj.get("openHours")
            return ActionResponse(success=False, type="buy", reason=err, result=res)
        item, qty = _item(payload), _qty(payload)
        d = inventory.item_def(item or "")
        if d is None:
            return ActionResponse(success=False, type="buy", reason="unknown_item", result={"objectId": obj["id"], "item": item})
        shop = economy.shop_for(obj["type"])
        if item not in shop.get("sells", []) or d.get("price") is None:
            return ActionResponse(success=False, type="buy", reason="not_for_sale", result={"objectId": obj["id"], **_item_fields(item, qty)})
        total = int(d["price"]) * qty
        if int(p.get("gold", 0)) < total:
            return ActionResponse(success=False, type="buy", reason="insufficient_funds",
                                  result={"objectId": obj["id"], **_item_fields(item, qty, total), "gold": int(p.get("gold", 0)),
                                          "message": f"钱不够：{d['name']} 要 {total} 金币，身上只有 {int(p.get('gold', 0))}。"})
        ierr = inventory.add(p, item, qty)
        if ierr:
            return ActionResponse(success=False, type="buy", reason=ierr, result={"objectId": obj["id"], **_item_fields(item, qty, total)})
        economy.ledger("buy", p, -total, item=item, qty=qty, price=int(d["price"]), shop=obj["id"], shop_type=obj["type"])
        owner = _owner_player(obj["type"])
        if owner is not None and owner["id"] != p["id"]:
            economy.ledger("income", owner, total, source="shop_sale", item=item, qty=qty, shop=obj["id"], peer=p["id"])
        mark_input(entity_id)
        return ActionResponse(success=True, type="buy", result={
            "message": f"买了 {qty} 个{d['name']}，花了 {total} 金币。", "objectId": obj["id"], **_item_fields(item, qty, total),
            "gold_delta": -total, "gold": p["gold"], "inventory": inventory.view(p)})


def handle_sell(entity_id: str, payload: dict) -> ActionResponse:
    with STATE_LOCK:
        p = _players.get(entity_id)
        if p is None:
            return ActionResponse(success=False, type="sell", reason="player_not_found")
        if not p.get("canUse", True):
            return ActionResponse(success=False, type="sell", reason="use_disabled")
        obj, err = _shop_object(p, payload)
        if err:
            res = {"objectId": obj["id"]} if obj else None
            if err == "shop_closed":
                res["opens_at"] = open_state(obj)[1]; res["openHours"] = obj.get("openHours")
            return ActionResponse(success=False, type="sell", reason=err, result=res)
        item, qty = _item(payload), _qty(payload)
        d = inventory.item_def(item or "")
        if d is None:
            return ActionResponse(success=False, type="sell", reason="unknown_item", result={"objectId": obj["id"], "item": item})
        shop = economy.shop_for(obj["type"])
        if item not in shop.get("buys", []) or d.get("sell") is None:
            return ActionResponse(success=False, type="sell", reason="not_buying", result={"objectId": obj["id"], **_item_fields(item, qty)})
        if inventory.count(p, item) < qty:
            return ActionResponse(success=False, type="sell", reason="no_item", result={"objectId": obj["id"], **_item_fields(item, qty), "have": inventory.count(p, item)})
        total = int(d["sell"]) * qty
        inventory.remove(p, item, qty)
        economy.ledger("sell", p, total, item=item, qty=qty, price=int(d["sell"]), shop=obj["id"], shop_type=obj["type"])
        owner = _owner_player(obj["type"])
        if owner is not None and owner["id"] != p["id"]:
            economy.ledger("expense", owner, -total, source="shop_purchase", item=item, qty=qty, shop=obj["id"], peer=p["id"])
        mark_input(entity_id)
        return ActionResponse(success=True, type="sell", result={
            "message": f"卖了 {qty} 个{d['name']}，得 {total} 金币。", "objectId": obj["id"], **_item_fields(item, qty, total),
            "gold_delta": total, "gold": p["gold"], "inventory": inventory.view(p)})


def handle_eat(entity_id: str, payload: dict) -> ActionResponse:
    with STATE_LOCK:
        p = _players.get(entity_id)
        if p is None:
            return ActionResponse(success=False, type="eat", reason="player_not_found")
        if not p.get("canUse", True):
            return ActionResponse(success=False, type="eat", reason="use_disabled")
        item = _item(payload)
        d = inventory.item_def(item or "")
        if d is None:
            return ActionResponse(success=False, type="eat", reason="unknown_item", result={"item": item})
        if d.get("class") != "food" or not d.get("eat"):
            return ActionResponse(success=False, type="eat", reason="not_edible", result=_item_fields(item, 1))
        if inventory.count(p, item) < 1:
            return ActionResponse(success=False, type="eat", reason="no_item", result=_item_fields(item, 1))
        inventory.remove(p, item, 1)
        applied = {}
        for var, delta in d["eat"].items():
            add_var(p, var, float(delta)); applied[var] = round(float(p.get(var, 0.0)), 3)      # 吃后的值
        mark_input(entity_id)
        return ActionResponse(success=True, type="eat", result={
            "message": f"吃了{d['name']}。", **_item_fields(item, 1), "effects": d["eat"], "vars": applied, "inventory": inventory.view(p)})


def _find_target(player: dict, ref: str | None) -> tuple[dict | None, str | None]:
    if not ref:
        return None, "target_not_found"
    from game.qq import account_of
    t = _players.get(ref)
    if t is None:
        for q in _players.values():
            if account_of(q) == ref or q.get("name") == ref or q.get("agent_id") == ref:
                t = q; break
    if t is None or t["id"] == player["id"]:
        return None, "target_not_found"
    px, py = player["position"]["x"], player["position"]["y"]
    tx, ty = t["position"]["x"], t["position"]["y"]
    if max(abs(px - tx), abs(py - ty)) > 2:                       # 当面给：2 格内（假设）
        return t, "target_too_far"
    return t, None


def handle_give(entity_id: str, payload: dict) -> ActionResponse:
    with STATE_LOCK:
        p = _players.get(entity_id)
        if p is None:
            return ActionResponse(success=False, type="give", reason="player_not_found")
        if not p.get("canUse", True):
            return ActionResponse(success=False, type="give", reason="use_disabled")
        item, qty = _item(payload), _qty(payload)
        d = inventory.item_def(item or "")
        if d is None:
            return ActionResponse(success=False, type="give", reason="unknown_item", result={"item": item})
        t, err = _find_target(p, payload.get("target") or payload.get("target_id") or payload.get("to"))
        if err:
            return ActionResponse(success=False, type="give", reason=err, result={"target": payload.get("target"), **_item_fields(item, qty)})
        if inventory.count(p, item) < qty:
            return ActionResponse(success=False, type="give", reason="no_item", result={**_item_fields(item, qty), "have": inventory.count(p, item)})
        ierr = inventory.add(t, item, qty)
        if ierr:
            return ActionResponse(success=False, type="give", reason=ierr, result={**_item_fields(item, qty), "target": t["id"], "target_name": t.get("name")})
        inventory.remove(p, item, qty)
        effects = {}
        if d.get("give"):                                          # 小礼物：对方亲密度 +8、心情 +5（items.json）
            for k, v in d["give"].items():
                if k == "closeness":
                    add_closeness(t, entity_id, float(v) * qty); effects["closeness"] = round(float(t["closeness"].get(entity_id, 0.0)), 3)
                else:
                    add_var(t, k, float(v) * qty); effects[k] = round(float(t.get(k, 0.0)), 3)
        mark_input(entity_id)
        return ActionResponse(success=True, type="give", result={
            "message": f"把 {qty} 个{d['name']}给了{t.get('name')}。", **_item_fields(item, qty), "target": t["id"],
            "target_name": t.get("name"), "target_effects": effects, "inventory": inventory.view(p)})
