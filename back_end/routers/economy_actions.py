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
    STATE_LOCK, _players, get_object_at, get_object_by_id, open_state, mark_input, refresh_shop_views,
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


def _credit_account(account: str | None, payer: dict, delta: int, **fields) -> None:
    """v1.1 M-5：销售 / 餐费 / 配钥匙的钱进店主账户，不看在线（自己买自己的不算）。"""
    from game.qq import account_of
    if not account or account_of(payer) == account:
        return
    economy.credit_account(account, int(delta), "income" if delta >= 0 else "expense", peer=payer["id"], **fields)


def _credit_owner(obj_type: str, payer: dict, delta: int, **fields) -> None:
    _credit_account((economy.shop_for(obj_type) or {}).get("owner"), payer, delta, **fields)


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
        stock = obj.get("stock")
        if stock is not None and int(stock.get(item, 0)) < qty:                      # W11 ④：库存
            return ActionResponse(success=False, type="buy", reason="out_of_stock",
                                  result={"objectId": obj["id"], **_item_fields(item, qty, total), "stock": int(stock.get(item, 0)),
                                          "message": f"{d['name']}卖完了，明早补货。"})
        if int(p.get("gold", 0)) < total:
            return ActionResponse(success=False, type="buy", reason="insufficient_funds",
                                  result={"objectId": obj["id"], **_item_fields(item, qty, total), "gold": int(p.get("gold", 0)),
                                          "message": f"钱不够：{d['name']} 要 {total} 金币，身上只有 {int(p.get('gold', 0))}。"})
        ierr = inventory.add(p, item, qty)
        if ierr:
            return ActionResponse(success=False, type="buy", reason=ierr, result={"objectId": obj["id"], **_item_fields(item, qty, total)})
        if stock is not None:
            stock[item] = int(stock.get(item, 0)) - qty
            refresh_shop_views()
        economy.ledger("buy", p, -total, item=item, qty=qty, price=int(d["price"]), shop=obj["id"], shop_type=obj["type"])
        _credit_owner(obj["type"], p, total, source="shop_sale", item=item, qty=qty, shop=obj["id"])
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
        if obj.get("stock") is not None:
            obj["stock"][item] = int(obj["stock"].get(item, 0)) + qty
            refresh_shop_views()
        economy.ledger("sell", p, total, item=item, qty=qty, price=int(d["sell"]), shop=obj["id"], shop_type=obj["type"])
        _credit_owner(obj["type"], p, -total, source="shop_purchase", item=item, qty=qty, shop=obj["id"])
        mark_input(entity_id)
        return ActionResponse(success=True, type="sell", result={
            "message": f"卖了 {qty} 个{d['name']}，得 {total} 金币。", "objectId": obj["id"], **_item_fields(item, qty, total),
            "gold_delta": total, "gold": p["gold"], "inventory": inventory.view(p)})


def handle_eat(entity_id: str, payload: dict) -> ActionResponse:
    """world-v1.1 §1：进食 = 餐桌类物品上的持续动作。
    须正坐在 object_types 带 `dining` 的物品上（否则 not_at_table）；`dining.allow` 非空时只许清单内物品（not_allowed_here）；
    直播中 streaming；吃着不能再吃 already_eating。开吃即扣物品（或餐厅扣钱），饱腹 / 心情按 minutes 线性涨，吃完涨完；中途 leave 按比例。
    餐厅：eat {item:"meal"} 在 `dining.meal` 的桌上，按 economy.meal 扣 price 给厨师。"""
    from game import food
    from game.time_state import game_now_ts
    with STATE_LOCK:
        p = _players.get(entity_id)
        if p is None:
            return ActionResponse(success=False, type="eat", reason="player_not_found")
        item = _item(payload)
        if not item:
            return ActionResponse(success=False, type="eat", reason="unknown_item", result={"item": item})
        if food.is_streaming(p):
            return ActionResponse(success=False, type="eat", reason="streaming", result={"message": "直播中不能吃东西，下播再说。", **(_item_fields(item, 1) if item != food.MEAL_ITEM else {"item": item})})
        obj = get_object_by_id(p.get("usingObjectId") or "") if p.get("usingObjectId") else None
        rule = food.dining_rule(obj)
        if rule is None:
            return ActionResponse(success=False, type="eat", reason="not_at_table",
                                  result={"message": "得先在餐桌边坐下（use 餐桌 / 长椅 / 吧台）才能吃。", "item": item, "usingObjectId": p.get("usingObjectId")})
        if food.is_busy(entity_id):
            return ActionResponse(success=False, type="eat", reason="already_eating", result={"busy": food.busy_view(entity_id), "item": item})
        gts = game_now_ts()
        if item == food.MEAL_ITEM:                                       # 餐厅一顿
            if not rule.get("meal"):
                return ActionResponse(success=False, type="eat", reason="not_allowed_here", result={"message": "这里不是餐厅，点不了菜。", "item": item, "objectId": obj["id"]})
            mc = food.meal_cfg(); price = int(mc.get("price", 20))
            if int(p.get("gold", 0)) < price:
                return ActionResponse(success=False, type="eat", reason="insufficient_funds",
                                      result={"message": f"一顿要 {price} 金币，身上只有 {int(p.get('gold', 0))}。", "item": item, "price": price, "gold": int(p.get("gold", 0)), "objectId": obj["id"]})
            economy.ledger("buy", p, -price, item="meal", qty=1, price=price, shop=obj["id"], shop_type=obj["type"])
            _credit_account(mc.get("owner") or "npc_rest_owner", p, price, source="restaurant_meal", shop=obj["id"])
            gain = {k: float(v) for k, v in (mc.get("gain") or {}).items()}; minutes = float(mc.get("minutes", 30))
            name = "一顿饭"; fields = {"item": item, "item_name": name, "qty": 1, "price": price, "gold_delta": -price, "gold": p["gold"]}
        else:
            d = inventory.item_def(item)
            if d is None:
                return ActionResponse(success=False, type="eat", reason="unknown_item", result={"item": item})
            if not d.get("eat"):
                return ActionResponse(success=False, type="eat", reason="not_edible", result=_item_fields(item, 1))
            allow = rule.get("allow")
            if allow is not None and item not in allow:
                return ActionResponse(success=False, type="eat", reason="not_allowed_here",
                                      result={"message": f"{obj['name']}这儿只能吃简餐（{'、'.join((inventory.item_def(a) or {}).get('name', a) for a in allow)}）。", "allowed": list(allow), **_item_fields(item, 1), "objectId": obj["id"]})
            if inventory.count(p, item) < 1:
                return ActionResponse(success=False, type="eat", reason="no_item", result=_item_fields(item, 1))
            inventory.remove(p, item, 1)
            gain = {k: float(v) for k, v in d["eat"].items() if k != "minutes"}; minutes = float(d["eat"].get("minutes", 5))
            name = d["name"]; fields = _item_fields(item, 1)
        busy = food.start_eating(p, obj, item, gain, minutes, gts)
        mark_input(entity_id)
        return ActionResponse(success=True, type="eat", result={
            "message": f"开始吃{name}，{minutes:.0f} 分钟吃完。", **fields, "duration_s": int(minutes * 60), "ends_at": busy["ends_at"],
            "gain": gain, "busy": busy, "objectId": obj["id"], "inventory": inventory.view(p)})


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
        if item == "key":                                            # §3.41：钥匙按 door_id 实物转交
            from game import doors
            door_id = payload.get("door_id") or payload.get("door")
            if not door_id:
                mine = doors.keys_of(p)
                if len(mine) != 1:
                    return ActionResponse(success=False, type="give", reason="door_id_required", result={"keys": mine})
                door_id = mine[0]["door_id"]
            kerr = doors.transfer_key(p, t, door_id)
            if kerr:
                return ActionResponse(success=False, type="give", reason=kerr, result={"item": "key", "door_id": door_id, "target": t["id"]})
            mark_input(entity_id)
            return ActionResponse(success=True, type="give", result={"message": f"把{door_id}的钥匙给了{t.get('name')}。", "item": "key", "item_name": "钥匙",
                                                                    "door_id": door_id, "qty": 1, "target": t["id"], "target_name": t.get("name"), "inventory": inventory.view(p)})
        if inventory.count(p, item) < qty:
            return ActionResponse(success=False, type="give", reason="no_item", result={**_item_fields(item, qty), "have": inventory.count(p, item)})
        ierr = inventory.add(t, item, qty)
        if ierr:
            return ActionResponse(success=False, type="give", reason=ierr, result={**_item_fields(item, qty), "target": t["id"], "target_name": t.get("name")})
        inventory.remove(p, item, qty)
        effects = {}
        commission = None
        if item in (economy.cfg().get("commissions", {}).get("deliver_items") or ["cd", "song"]):   # W11 ① / v1.1 Q-5：给委托人 CD（旧 song）= 交付委托
            from game import commissions
            meta = {"commission_id": payload["commission_id"]} if payload.get("commission_id") else _song_meta(payload, p, t, item)
            commission = commissions.deliver(p, t, meta)
        if d.get("give"):                                          # 小礼物：对方亲密度 +8、心情 +5（items.json）
            for k, v in d["give"].items():
                if k == "closeness":
                    add_closeness(t, entity_id, float(v) * qty); effects["closeness"] = round(float(t["closeness"].get(entity_id, 0.0)), 3)
                else:
                    add_var(t, k, float(v) * qty); effects[k] = round(float(t.get(k, 0.0)), 3)
        mark_input(entity_id)
        res = {"message": f"把 {qty} 个{d['name']}给了{t.get('name')}。", **_item_fields(item, qty), "target": t["id"],
               "target_name": t.get("name"), "target_effects": effects, "inventory": inventory.view(p)}
        if commission:
            res["commission"] = commission; res["gold_delta"] = commission["fee"]; res["gold"] = p["gold"]
            res["message"] += f" 完成委托《{commission['title']}》，收到 {commission['fee']} 金币。"
        return ActionResponse(success=True, type="give", result=res)


def _song_meta(payload: dict, giver: dict, target: dict, item: str = "cd") -> dict:
    """give cd / song 没指明 commission_id 时：用刚转出去的那张的 meta（取 target 背包里最新的该类条目）。"""
    songs = [e for e in inventory.ensure(target) if e.get("type") == item]
    return dict((songs[-1].get("meta") or {})) if songs else {}


def handle_copy_key(entity_id: str, payload: dict) -> ActionResponse:
    """world-v1.1 I-7：配钥匙 {door_id}。面向杂货店柜台（营业中）、只有门主能配自己门的钥匙、15 金币给店主；配出的是普通 key 物品可 give。"""
    from game import doors
    with STATE_LOCK:
        p = _players.get(entity_id)
        if p is None:
            return ActionResponse(success=False, type="copy_key", reason="player_not_found")
        if not p.get("canUse", True):
            return ActionResponse(success=False, type="copy_key", reason="use_disabled")
        svc = economy.cfg().get("services", {}).get("copy_key", {"price": 15, "shop": "shop_counter"})
        obj, err = _shop_object(p, payload)
        if err and err != "no_shop":
            res = {"objectId": obj["id"]} if obj else None
            if err == "shop_closed":
                res["opens_at"] = open_state(obj)[1]
            return ActionResponse(success=False, type="copy_key", reason=err, result=res)
        if obj is None or obj.get("type") != svc.get("shop", "shop_counter"):
            return ActionResponse(success=False, type="copy_key", reason="not_at_counter", result={"objectId": obj["id"] if obj else None, "need": svc.get("shop", "shop_counter")})
        door_id = payload.get("door_id") or payload.get("door")
        edge = doors.door(door_id or "")
        if edge is None or not doors.is_keyed(edge):
            return ActionResponse(success=False, type="copy_key", reason="unknown_door", result={"door_id": door_id})
        from game.world_state import _mover_ids
        if not (set(edge.get("owner") or []) & set(_mover_ids(p))):
            return ActionResponse(success=False, type="copy_key", reason="not_owner", result={"door_id": door_id, "owners": list(edge.get("owner") or [])})
        price = int(svc.get("price", 15))
        if int(p.get("gold", 0)) < price:
            return ActionResponse(success=False, type="copy_key", reason="insufficient_funds", result={"door_id": door_id, "price": price, "gold": int(p.get("gold", 0))})
        meta = {"door_id": door_id, "name": doors.key_name(edge), "copy": True}
        ierr = inventory.add(p, "key", 1, meta=meta, expires_at=None)
        if ierr:
            return ActionResponse(success=False, type="copy_key", reason=ierr, result={"door_id": door_id})
        economy.ledger("buy", p, -price, item="key_copy", qty=1, price=price, shop=obj["id"], shop_type=obj["type"], door_id=door_id)
        _credit_owner(obj["type"], p, price, source="shop_service", item="key_copy", qty=1, shop=obj["id"])
        doors._log(entity_id, "copy_key", {"door_id": door_id, "price": price})
        mark_input(entity_id)
        return ActionResponse(success=True, type="copy_key", result={"message": f"配了一把{meta['name']}，花了 {price} 金币。", "item": "key", "item_name": "钥匙", "door_id": door_id,
                                                                     "qty": 1, "price": price, "gold_delta": -price, "gold": p["gold"], "objectId": obj["id"], "inventory": inventory.view(p)})


def handle_burn_cd(entity_id: str, payload: dict) -> ActionResponse:
    """world-v1.1 Q-5：再刻一张 {title?}。须正在用琴房电脑且背包里有同名 CD；10 分钟后 +1 张（busy kind burning）；不耗钱。"""
    from game import production
    res, reason, extra = production.start_burn(entity_id, payload)
    if reason:
        return ActionResponse(success=False, type="burn_cd", reason=reason, result=extra)
    return ActionResponse(success=True, type="burn_cd", result=res)


def _storage_target(p: dict, payload: dict, typ: str) -> tuple[dict | None, ActionResponse | None]:
    oid = payload.get("object_id") or payload.get("objectId")
    if oid:
        obj = get_object_by_id(oid)
        if obj is None:
            return None, ActionResponse(success=False, type=typ, reason="no_object")
        if not _adjacent(p, obj):
            return None, ActionResponse(success=False, type=typ, reason="object_too_far")
    else:
        dx, dy = _DIR[p["facing"]]
        obj = get_object_at(p["position"]["x"] + dx, p["position"]["y"] + dy)
        if obj is None:
            return None, ActionResponse(success=False, type=typ, reason="no_object")
    if obj.get("contents") is None:
        return None, ActionResponse(success=False, type=typ, reason="not_storage", result={"objectId": obj["id"]})
    return obj, None


def handle_store(entity_id: str, payload: dict) -> ActionResponse:
    """world-v1.1：把背包里的食物 / 食材放进冰箱（相邻或 object_id；按叠带保质期；容量 economy.fridge.capacity）。payload {item, qty?=1, object_id?}。"""
    from game import food
    with STATE_LOCK:
        p = _players.get(entity_id)
        if p is None:
            return ActionResponse(success=False, type="store", reason="player_not_found")
        if not p.get("canUse", True):
            return ActionResponse(success=False, type="store", reason="use_disabled")
        obj, err = _storage_target(p, payload, "store")
        if err:
            return err
        item = _item(payload) or "ingredients"; qty = _qty(payload)
        d = inventory.item_def(item)
        if d is None:
            return ActionResponse(success=False, type="store", reason="unknown_item", result={"objectId": obj["id"], "item": item})
        if d.get("class") not in ("food", "material"):
            return ActionResponse(success=False, type="store", reason="not_storable", result={"objectId": obj["id"], **_item_fields(item, qty)})
        if inventory.count(p, item) < qty:
            return ActionResponse(success=False, type="store", reason="no_item", result={"objectId": obj["id"], **_item_fields(item, qty), "have": inventory.count(p, item)})
        room = food.capacity(obj) - food.used(obj)
        if room <= 0:
            return ActionResponse(success=False, type="store", reason="storage_full", result={"objectId": obj["id"], "capacity": food.capacity(obj), "used": food.used(obj)})
        qty = min(qty, room)
        # 按叠搬：先搬最早到期的，保质期跟着走
        moved = 0
        for e in sorted([e for e in inventory.ensure(p) if e.get("type") == item], key=lambda e: (e.get("expires_at") is None, e.get("expires_at") or 0.0)):
            if moved >= qty:
                break
            n = min(qty - moved, int(e.get("count", 0)))
            food.store(obj, item, n, e.get("expires_at"))
            inventory.remove_entry(p, e, n); moved += n
        mark_input(entity_id)
        from game.time_state import game_now_ts
        return ActionResponse(success=True, type="store", result={"message": f"把 {moved} 份{d['name']}放进了{obj['name']}。",
                                                                  "objectId": obj["id"], **_item_fields(item, moved), "stock": dict(obj["stock"]),
                                                                  "contents": food.contents_view(obj, game_now_ts()), "storage": {"capacity": food.capacity(obj), "used": food.used(obj)},
                                                                  "inventory": inventory.view(p)})


def handle_take(entity_id: str, payload: dict) -> ActionResponse:
    """world-v1.1：从冰箱拿出 {item, qty?=1, object_id?}（先拿最早到期的，保质期跟着走）。失败 not_storage / not_in_storage / inventory_full / stack_full。"""
    from game import food
    with STATE_LOCK:
        p = _players.get(entity_id)
        if p is None:
            return ActionResponse(success=False, type="take", reason="player_not_found")
        if not p.get("canUse", True):
            return ActionResponse(success=False, type="take", reason="use_disabled")
        obj, err = _storage_target(p, payload, "take")
        if err:
            return err
        item = _item(payload); qty = _qty(payload)
        if not item or inventory.item_def(item) is None:
            return ActionResponse(success=False, type="take", reason="unknown_item", result={"objectId": obj["id"], "item": item})
        have = int((obj.get("stock") or {}).get(item, 0))
        if have < 1:
            return ActionResponse(success=False, type="take", reason="not_in_storage", result={"objectId": obj["id"], **_item_fields(item, qty), "stock": dict(obj["stock"])})
        qty = min(qty, have)
        # 先探背包放得下多少（种数 / 每种 20）
        room_kind = item in inventory.kinds(p) or len(inventory.kinds(p)) < inventory.MAX_KINDS or not inventory.counts_toward_kinds(item)
        if not room_kind:
            return ActionResponse(success=False, type="take", reason="inventory_full", result={"objectId": obj["id"], **_item_fields(item, qty)})
        cap_left = inventory.MAX_PER_KIND - inventory.count(p, item)
        if cap_left <= 0:
            return ActionResponse(success=False, type="take", reason="stack_full", result={"objectId": obj["id"], **_item_fields(item, qty), "max_per_kind": inventory.MAX_PER_KIND})
        qty = min(qty, cap_left)
        taken = 0
        for n, exp in food.take(obj, item, qty):
            inventory.add(p, item, n, expires_at=exp); taken += n
        mark_input(entity_id)
        from game.time_state import game_now_ts
        d = inventory.item_def(item)
        msg = f"从{obj['name']}拿出 {taken} 份{d['name']}。"
        if item == "spoiled_food":
            msg += "已经坏了，丢掉吧（discard）。"
        return ActionResponse(success=True, type="take", result={"message": msg, "objectId": obj["id"], **_item_fields(item, taken), "stock": dict(obj["stock"]),
                                                                 "contents": food.contents_view(obj, game_now_ts()), "storage": {"capacity": food.capacity(obj), "used": food.used(obj)},
                                                                 "inventory": inventory.view(p)})


def handle_discard(entity_id: str, payload: dict) -> ActionResponse:
    """world-v1.1：丢掉背包里的东西 {item, qty?=1}（任何物品；钥匙回池走 give / 删角色，这里不许丢）。"""
    with STATE_LOCK:
        p = _players.get(entity_id)
        if p is None:
            return ActionResponse(success=False, type="discard", reason="player_not_found")
        item = _item(payload); qty = _qty(payload)
        d = inventory.item_def(item or "")
        if d is None:
            return ActionResponse(success=False, type="discard", reason="unknown_item", result={"item": item})
        if d.get("class") == "key":
            return ActionResponse(success=False, type="discard", reason="not_discardable", result=_item_fields(item, qty))
        have = inventory.count(p, item)
        if have < 1:
            return ActionResponse(success=False, type="discard", reason="no_item", result={**_item_fields(item, qty), "have": have})
        qty = min(qty, have)
        inventory.remove(p, item, qty)
        mark_input(entity_id)
        return ActionResponse(success=True, type="discard", result={"message": f"丢掉了 {qty} 个{d['name']}。", **_item_fields(item, qty), "inventory": inventory.view(p)})


def handle_compose(entity_id: str, payload: dict) -> ActionResponse:
    return _craft("compose", entity_id, payload)


def handle_make_video(entity_id: str, payload: dict) -> ActionResponse:
    return _craft("make_video", entity_id, payload)


def _craft(kind: str, entity_id: str, payload: dict) -> ActionResponse:
    from game import production
    res, reason, extra = production.craft(entity_id, kind, payload)
    if reason:
        return ActionResponse(success=False, type=kind, reason=reason, result=extra)
    return ActionResponse(success=True, type=kind, result=res)
