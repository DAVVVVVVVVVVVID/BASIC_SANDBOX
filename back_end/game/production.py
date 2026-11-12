"""
产出链（W11 ①，03-objects 3.1 假设值，全在 economy.json `production`）。

- 钓位：使用中每 interval_min 游戏分钟掷一次（p；有鱼饵 p_bait，每次掷消耗 1 鱼饵），中了「鱼」进背包。
- 灶台（world-v1.1 按份）：use {item?="ingredients"|"fish", qty?=1} 立即扣 n 份食材（不够 → no_ingredients），minutes_first + minutes_extra×(n−1)
  游戏分钟后产 n 份 recipes[item]（家常菜 / 鱼料理，带保鲜期）；提前 leave 白费（ws cook_cancelled）。free_for_owner 的灶台由店主用时不扣食材。
- compose / make_video：POST /action，须正在使用配置里的物品类型且已用满 min_minutes；产「歌」/「电台文稿」（文件类，带 meta）。
随机数用 SANDBOX_SEED 定种（seed 为空时真随机，记 external nondeterministic）；每次产出记 external `produce` 一行 + ws `produce` 事件。
"""
import math
import random

_fish: dict[str, dict] = {}        # entity -> {"last_roll_gts", "rolls"}
_stove: dict[str, dict] = {}       # entity -> {"start_gts", "done"}
_burn: dict[str, dict] = {}        # entity -> {"start_gts", "ready_gts", "object", "meta"}（world-v1.1 Q-5：再刻一张 CD）


def cfg() -> dict:
    from game.economy import cfg as _c
    return _c().get("production", {})


def _rng(*parts) -> random.Random:
    from game.world_state import SANDBOX_SEED
    if SANDBOX_SEED is None:
        return random.Random()
    return random.Random(":".join(str(p) for p in (SANDBOX_SEED, *parts)))


def _notify(player: dict, kind: str, item: str, qty: int, **fields) -> None:
    from game import external_log, world_state
    from game.inventory import item_def
    name = (item_def(item) or {}).get("name", item)
    external_log.log("produce", player["id"], via=kind, item=item, qty=qty, seeded=world_state.SANDBOX_SEED is not None, **fields)
    try:
        from routers.ws import hub
        hub.push_event({"type": "produce", "entity": player["id"], "via": kind, "item": item, "item_name": name, "qty": qty, **fields})
    except Exception:
        pass
    world_state._pending_messages[player["id"]] = {"fishing": f"钓到一条{name}！", "stove": f"做好了 {qty} 份{name}。", "burn_cd": f"又刻好一张《{fields.get('title') or ''}》。"}.get(kind, f"得到{name}×{qty}")


# ── 钓位 ──
def stove_plan(player: dict, obj: dict, payload: dict | None) -> tuple[dict | None, str | None, dict | None]:
    """算这次下厨：返回 (plan, reason, extra)。plan = {item, qty, product, minutes, free}。"""
    from game import inventory
    sc = cfg().get("stove", {})
    recipes = sc.get("recipes") or {"ingredients": "home_meal"}
    item = (payload or {}).get("item") or "ingredients"
    try:
        qty = max(1, int((payload or {}).get("qty", 1)))
    except (TypeError, ValueError):
        qty = 1
    qty = min(qty, int(sc.get("max_portions", 6)))
    if item not in recipes:
        return None, "not_cookable", {"item": item, "cookable": sorted(recipes)}
    free_owner = (sc.get("free_for_owner") or {}).get(obj["id"])
    free = bool(free_owner) and (player.get("agent_id") == free_owner)
    have = inventory.count(player, item)
    if not free and have < qty:
        return None, "no_ingredients", {"item": item, "have": have, "need": qty}
    minutes = float(sc.get("minutes_first", 20)) + float(sc.get("minutes_extra", 10)) * (qty - 1)
    return {"item": item, "qty": qty, "product": recipes[item], "minutes": minutes, "free": free}, None, None


def on_enter(player: dict, obj: dict, gts: float, payload: dict | None = None) -> str | None:
    """use 成功前调用：灶台按份扣食材并开计时；钓位开始计时。返回失败 reason 或 None。失败细节在 player['_use_err']。"""
    from game import inventory
    player.pop("_use_err", None)
    if obj["type"] == "fishing_spot":
        _fish[player["id"]] = {"last_roll_gts": gts, "rolls": 0, "object": obj["id"]}
    elif obj["type"] == "stove":
        plan, reason, extra = stove_plan(player, obj, payload)
        if reason:
            player["_use_err"] = extra or {}
            return reason
        if not plan["free"]:
            inventory.remove(player, plan["item"], plan["qty"])
        _stove[player["id"]] = {"start_gts": gts, "done": False, "object": obj["id"], "item": plan["item"], "qty": plan["qty"],
                                "product": plan["product"], "minutes": plan["minutes"], "ready_gts": gts + plan["minutes"] * 60.0}
    return None


def cooking_view(obj_id: str, gts: float) -> dict | None:
    """物品的 cooking 字段：{by, item, portions, product, started_at, ready_at, ready_in_min}。"""
    for pid, st in _stove.items():
        if st.get("object") == obj_id and not st.get("done"):
            from game.food import _iso
            return {"by": pid, "item": st.get("item"), "portions": st.get("qty"), "product": st.get("product"),
                    "started_at": _iso(st["start_gts"]), "ready_at": _iso(st["ready_gts"]), "ready_in_min": max(0, round((st["ready_gts"] - gts) / 60.0, 1))}
    return None


def start_burn(entity_id: str, payload: dict) -> tuple[dict | None, str | None, dict | None]:
    """再刻一张：返回 (result, reason, extra)。"""
    from game import world_state, inventory
    from game.food import _iso
    bc = cfg().get("burn_cd", {"objects": ["pc_music"], "minutes": 10})
    with world_state.STATE_LOCK:
        p = world_state._players.get(entity_id)
        if p is None:
            return None, "player_not_found", None
        oid = p.get("usingObjectId")
        obj = world_state.get_object_by_id(oid) if oid else None
        if obj is None or obj["type"] not in bc.get("objects", ["pc_music"]):
            return None, "need_object", {"objects": bc.get("objects", ["pc_music"])}
        if entity_id in _burn:
            return None, "already_burning", {"busy": busy_view(entity_id)}
        title = (payload or {}).get("title")
        cds = [e for e in inventory.ensure(p) if e.get("type") == "cd" and (not title or (e.get("meta") or {}).get("title") == title)]
        if not cds:
            return None, "no_item", {"item": "cd", "title": title}
        if not title and len({(e.get("meta") or {}).get("title") for e in cds}) > 1:
            return None, "title_required", {"titles": sorted({(e.get("meta") or {}).get("title") for e in cds if e.get("meta")})}
        src = cds[-1]
        gts = world_state.game_now_ts()
        minutes = float(bc.get("minutes", 10))
        _burn[entity_id] = {"start_gts": gts, "ready_gts": gts + minutes * 60.0, "object": oid, "meta": dict(src.get("meta") or {})}
        if "burning" not in p["tags"]:
            p["tags"].append("burning")
        return {"message": f"开始刻《{_burn[entity_id]['meta'].get('title', '')}》，{minutes:.0f} 分钟后多一张。", "objectId": oid, "item": "cd",
                "title": _burn[entity_id]["meta"].get("title"), "duration_s": int(minutes * 60), "ends_at": _iso(gts + minutes * 60.0), "busy": busy_view(entity_id, gts)}, None, None


def busy_view(pid: str, gts: float | None = None) -> dict | None:
    b = _burn.get(pid)
    if b is None:
        return None
    from game.food import _iso
    if gts is None:
        from game.world_state import game_now_ts
        gts = game_now_ts()
    dur = max(1e-6, b["ready_gts"] - b["start_gts"])
    return {"kind": "burning", "item": "cd", "object": b["object"], "started_at": _iso(b["start_gts"]), "ends_at": _iso(b["ready_gts"]),
            "remaining_s": max(0, round(b["ready_gts"] - gts)), "progress": round(min(1.0, max(0.0, (gts - b["start_gts"]) / dur)), 3), "title": b["meta"].get("title")}


def on_leave(player: dict) -> None:
    _fish.pop(player["id"], None)
    if _burn.pop(player["id"], None) is not None and "burning" in player.get("tags", []):
        player["tags"].remove("burning")              # 中途走：这张没刻成
    st = _stove.pop(player["id"], None)
    if st and not st.get("done"):                                  # 中途走：已扣的食材白费
        from game import external_log, world_state
        external_log.log("produce", player["id"], via="stove", action="cancelled", item=st.get("item"), qty=st.get("qty"), object=st.get("object"))
        try:
            from routers.ws import hub
            hub.push_event({"type": "cook_cancelled", "entity": player["id"], "object": st.get("object"), "item": st.get("item"), "qty": st.get("qty")})
        except Exception:
            pass
        world_state._pending_messages[player["id"]] = "饭没做完就走了，食材白费了。"


def on_tick(gts: float, players: dict) -> None:
    """调用方持 STATE_LOCK。"""
    from game import inventory
    pc = cfg()
    fc = pc.get("fishing", {})
    for pid, st in list(_fish.items()):
        p = players.get(pid)
        if p is None or p.get("usingObjectId") != st["object"]:
            _fish.pop(pid, None); continue
        interval = float(fc.get("interval_min", 40)) * 60.0
        while gts - st["last_roll_gts"] >= interval:
            st["last_roll_gts"] += interval; st["rolls"] += 1
            bait = fc.get("bait"); has_bait = bool(bait) and inventory.count(p, bait) > 0
            if has_bait:
                inventory.remove(p, bait, 1)
            prob = float(fc.get("p_bait", 0.8) if has_bait else fc.get("p", 0.5))
            hit = _rng("fish", pid, st["object"], st["rolls"]).random() < prob
            if hit and inventory.add(p, fc.get("item", "fish"), 1) is None:
                _notify(p, "fishing", fc.get("item", "fish"), 1, object=st["object"], roll=st["rolls"], bait=has_bait, p=prob)
    for pid, b in list(_burn.items()):                                   # 刻盘
        p = players.get(pid)
        if p is None or p.get("usingObjectId") != b["object"]:
            _burn.pop(pid, None); continue
        if gts >= b["ready_gts"]:
            _burn.pop(pid, None)
            if "burning" in p.get("tags", []):
                p["tags"].remove("burning")
            err = inventory.add(p, "cd", 1, meta=dict(b["meta"]), expires_at=None)
            if err is None:
                _notify(p, "burn_cd", "cd", 1, object=b["object"], title=b["meta"].get("title"))
            else:
                from game import world_state
                world_state._pending_messages[pid] = f"刻好了，可是背包放不下（{err}）。"
    for pid, st in list(_stove.items()):
        p = players.get(pid)
        if p is None or p.get("usingObjectId") != st["object"]:
            _stove.pop(pid, None); continue
        if not st["done"] and gts >= st.get("ready_gts", st["start_gts"] + st.get("minutes", 20) * 60.0):
            st["done"] = True
            item, n = st.get("product", "home_meal"), int(st.get("qty", 1))
            err = inventory.add(p, item, n, now_gts=gts)
            if err is None:
                _notify(p, "stove", item, n, object=st["object"], portions=n)
            else:
                from game import world_state
                world_state._pending_messages[pid] = f"做好了 {n} 份，可是背包放不下（{err}）。"
                _notify(p, "stove", item, 0, object=st["object"], portions=n, error=err)


# ── compose / make_video ──
def craft(entity_id: str, kind: str, payload: dict) -> tuple[dict | None, str | None, dict | None]:
    """返回 (result, reason, extra)。kind: compose | make_video。"""
    from game import world_state, inventory
    from game.time_state import game_now_iso
    pc = cfg().get(kind)
    if not pc:
        return None, "unknown_action", None
    with world_state.STATE_LOCK:
        p = world_state._players.get(entity_id)
        if p is None:
            return None, "player_not_found", None
        oid = p.get("usingObjectId")
        obj = world_state.get_object_by_id(oid) if oid else None
        if obj is None or obj["type"] not in pc.get("objects", []):
            return None, "need_object", {"objects": pc.get("objects", [])}
        elapsed_min = world_state.use_elapsed_game_s(entity_id) / 60.0
        need = float(pc.get("min_minutes", 0))
        if elapsed_min < need:
            return None, "not_ready", {"objectId": oid, "ready_in_min": math.ceil(need - elapsed_min), "min_minutes": need}
        item = pc["item"]
        meta = {k: v for k, v in (payload.get("meta") or {}).items()}
        title = payload.get("title") or meta.get("title") or f"{(inventory.item_def(item) or {}).get('name', item)} {game_now_iso()[:16]}"
        meta["title"] = title
        for k in ("commission_id", "text", "summary", "ref"):
            if payload.get(k) is not None:
                meta[k] = payload[k]
        meta["created_at"] = game_now_iso(); meta["by"] = p.get("agent_id") or p["id"]
        err = inventory.add(p, item, 1, meta=meta, expires_at=None)
        if err:
            return None, err, {"objectId": oid}
        _notify(p, kind, item, 1, object=oid, title=title, commission_id=meta.get("commission_id"))
        world_state.record_object_use(entity_id, oid)
        return {"message": f"完成了《{title}》。", "objectId": oid, "item": item, "item_name": (inventory.item_def(item) or {}).get("name", item),
                "qty": 1, "meta": meta, "inventory": inventory.view(p)}, None, None


def export_state() -> dict:
    return {"fish": dict(_fish), "stove": dict(_stove), "burn": dict(_burn)}


def import_state(d: dict) -> None:
    _fish.clear(); _stove.clear(); _burn.clear()
    _fish.update(d.get("fish") or {}); _stove.update(d.get("stove") or {}); _burn.update(d.get("burn") or {})


def _reset_for_tests() -> None:
    _fish.clear(); _stove.clear(); _burn.clear()
