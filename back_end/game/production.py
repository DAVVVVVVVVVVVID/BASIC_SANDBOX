"""
产出链（W11 ①，03-objects 3.1 假设值，全在 economy.json `production`）。

- 钓位：使用中每 interval_min 游戏分钟掷一次（p；有鱼饵 p_bait，每次掷消耗 1 鱼饵），中了「鱼」进背包。
- 灶台：use 时消耗食材（不够 → use 失败 no_ingredients），满 minutes 游戏分钟产便当 ×2；提前 leave 不产（食材已耗）。
- compose / make_video：POST /action，须正在使用配置里的物品类型且已用满 min_minutes；产「歌」/「电台文稿」（文件类，带 meta）。
随机数用 SANDBOX_SEED 定种（seed 为空时真随机，记 external nondeterministic）；每次产出记 external `produce` 一行 + ws `produce` 事件。
"""
import math
import random

_fish: dict[str, dict] = {}        # entity -> {"last_roll_gts", "rolls"}
_stove: dict[str, dict] = {}       # entity -> {"start_gts", "done"}


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
    world_state._pending_messages[player["id"]] = {"fishing": f"钓到一条{name}！", "stove": f"做好了 {qty} 份{name}。"}.get(kind, f"得到{name}×{qty}")


# ── 钓位 ──
def on_enter(player: dict, obj: dict, gts: float) -> str | None:
    """use 成功前调用：灶台检查并消耗食材；返回失败 reason 或 None。"""
    from game import inventory
    pc = cfg()
    if obj["type"] == "fishing_spot":
        _fish[player["id"]] = {"last_roll_gts": gts, "rolls": 0, "object": obj["id"]}
    elif obj["type"] == "stove":
        need = pc.get("stove", {}).get("consumes", {})
        for item, n in need.items():
            if inventory.count(player, item) < n:
                return "no_ingredients"
        for item, n in need.items():
            inventory.remove(player, item, n)
        _stove[player["id"]] = {"start_gts": gts, "done": False, "object": obj["id"]}
    return None


def on_leave(player: dict) -> None:
    _fish.pop(player["id"], None)
    _stove.pop(player["id"], None)


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
    sc = pc.get("stove", {})
    for pid, st in list(_stove.items()):
        p = players.get(pid)
        if p is None or p.get("usingObjectId") != st["object"]:
            _stove.pop(pid, None); continue
        if not st["done"] and gts - st["start_gts"] >= float(sc.get("minutes", 30)) * 60.0:
            st["done"] = True
            for item, n in sc.get("produces", {}).items():
                if inventory.add(p, item, n) is None:
                    _notify(p, "stove", item, n, object=st["object"])


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
        err = inventory.add(p, item, 1, meta=meta)
        if err:
            return None, err, {"objectId": oid}
        _notify(p, kind, item, 1, object=oid, title=title, commission_id=meta.get("commission_id"))
        world_state.record_object_use(entity_id, oid)
        return {"message": f"完成了《{title}》。", "objectId": oid, "item": item, "item_name": (inventory.item_def(item) or {}).get("name", item),
                "qty": 1, "meta": meta, "inventory": inventory.view(p)}, None, None


def export_state() -> dict:
    return {"fish": dict(_fish), "stove": dict(_stove)}


def import_state(d: dict) -> None:
    _fish.clear(); _stove.clear()
    _fish.update(d.get("fish") or {}); _stove.update(d.get("stove") or {})


def _reset_for_tests() -> None:
    _fish.clear(); _stove.clear()
