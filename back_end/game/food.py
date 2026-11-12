"""
食物（world-v1.1 §1，主播 11-12 夜重设计）：
- 冰箱 = 存储：obj["contents"] = [{item, count, expires_at}]，容量 economy.fridge.capacity；store / take；不自动补货（restock_enabled）。
  obj["stock"]（{item: n}）保留为按种计数的派生视图（旧字段只加不删）。
- 保鲜：items.json spoil_days；背包与冰箱里到期的那叠整叠变 spoiled_food（ws `spoiled`）。
- 进食 = 餐桌类物品上的持续动作：eat {item} 开吃即扣物品，饱腹 / 心情按时长线性涨（timed buff，source "eat"），吃完涨完、
  中途 leave 按已过时间比例（buff 随 leave 摘掉即为比例）；期间 tags 含 eating，player.busy 给进度；结束 ws `eat_done`。
  只能在 object_types 带 `dining` 的物品上吃；`dining.allow` 非空时只许清单内物品（长椅 = 简餐处）；直播中（scene live / tag streaming）一律 `streaming`。
  餐厅：eat {item: "meal"}（不在背包）在 `dining.meal` 的桌上，开吃扣 economy.meal.price 给厨师，minutes / gain 按 economy.meal。
"""
from __future__ import annotations

_busy: dict[str, dict] = {}        # entity -> {kind, item, started_gts, ends_gts, gain{var: total}, object}
EAT_SOURCE = "eat"
MEAL_ITEM = "meal"


def _iso(ts: float) -> str:
    from datetime import datetime
    from game.time_state import GAME_TZ
    return datetime.fromtimestamp(ts, GAME_TZ).isoformat(timespec="seconds")


def _push(ev: dict) -> None:
    try:
        from routers.ws import hub
        hub.push_event(ev)
    except Exception:
        pass


# ── 冰箱 / 存储 ────────────────────────────────────────────────────────────────
def fridge_cfg() -> dict:
    from game.economy import cfg
    return cfg().get("fridge", {})


def is_storage(obj: dict) -> bool:
    return obj.get("type") == "fridge"


def capacity(obj: dict) -> int:
    return int(fridge_cfg().get("capacity", 20))


def used(obj: dict) -> int:
    return sum(int(c.get("count", 0)) for c in (obj.get("contents") or []))


def refresh_stock(obj: dict) -> None:
    """contents → stock（按种计数，旧字段）。"""
    st: dict[str, int] = {}
    for c in obj.get("contents") or []:
        st[c["item"]] = st.get(c["item"], 0) + int(c.get("count", 0))
    obj["stock"] = st


def init_contents(obj: dict, now_gts: float) -> None:
    """按 economy.fridge.initial[obj id] / default 填初始内容（只在建对象 / reset 时调）。"""
    from game import inventory
    fc = fridge_cfg()
    init = (fc.get("initial") or {})
    spec = init.get(obj["id"], init.get("default", {})) or {}
    obj["contents"] = [{"item": it, "count": int(n), "expires_at": inventory.expires_at_for(it, now_gts)} for it, n in spec.items() if int(n) > 0]
    refresh_stock(obj)


def store(obj: dict, item: str, qty: int, expires_at: float | None) -> int:
    """放 qty 份进去（同到期日合叠）；返回实际放入数（受容量限制）。"""
    from game.inventory import _same_day
    room = capacity(obj) - used(obj)
    n = max(0, min(qty, room))
    if n <= 0:
        return 0
    contents = obj.setdefault("contents", [])
    for c in contents:
        if c["item"] == item and _same_day(c.get("expires_at"), expires_at):
            c["count"] += n
            if expires_at is not None and c.get("expires_at") is not None:
                c["expires_at"] = min(float(c["expires_at"]), float(expires_at))
            break
    else:
        contents.append({"item": item, "count": n, "expires_at": expires_at})
    refresh_stock(obj)
    return n


def take(obj: dict, item: str, qty: int) -> list[tuple[int, float | None]]:
    """拿 qty 份出来，先拿最早到期的；返回 [(count, expires_at)]（不够就拿到多少算多少）。"""
    contents = obj.get("contents") or []
    out: list[tuple[int, float | None]] = []
    left = qty
    for c in sorted([c for c in contents if c["item"] == item], key=lambda c: (c.get("expires_at") is None, c.get("expires_at") or 0.0)):
        if left <= 0:
            break
        n = min(left, int(c["count"]))
        c["count"] -= n; left -= n
        out.append((n, c.get("expires_at")))
        if c["count"] <= 0:
            contents.remove(c)
    refresh_stock(obj)
    return out


def contents_view(obj: dict, now_gts: float) -> list[dict]:
    from game.inventory import item_def, days_left
    rows = []
    for c in obj.get("contents") or []:
        d = item_def(c["item"]) or {}
        row = {"item": c["item"], "name": d.get("name", c["item"]), "count": int(c["count"]), "spoiled": c["item"] == "spoiled_food",
               "expires_at": _iso(float(c["expires_at"])) if c.get("expires_at") is not None else None,
               "expires_in_days": days_left(c.get("expires_at"), now_gts)}
        rows.append(row)
    return rows


# ── 保鲜 ───────────────────────────────────────────────────────────────────────
def spoil_tick(gts: float, players: dict, objects: list[dict]) -> int:
    """到期的叠变 spoiled_food。调用方持 STATE_LOCK。返回变坏的叠数。"""
    from game import inventory, external_log
    n = 0
    for p in players.values():
        inv = inventory.ensure(p)
        for e in list(inv):
            exp = e.get("expires_at")
            if exp is None or float(exp) > gts or e["type"] == "spoiled_food":
                continue
            qty = int(e.get("count", 0)); item = e["type"]
            inv.remove(e)
            inventory.add(p, "spoiled_food", qty, expires_at=None)
            n += 1
            external_log.log("spoiled", p["id"], item=item, qty=qty, where="inventory")
            _push({"type": "spoiled", "entity": p["id"], "item": item, "qty": qty})
            from game import world_state
            world_state._pending_messages[p["id"]] = f"背包里的{(inventory.item_def(item) or {}).get('name', item)}坏了。"
    for o in objects:
        if not is_storage(o) or not o.get("contents"):
            continue
        changed = False
        for c in list(o["contents"]):
            exp = c.get("expires_at")
            if exp is None or float(exp) > gts or c["item"] == "spoiled_food":
                continue
            qty = int(c["count"]); item = c["item"]
            o["contents"].remove(c)
            for s in o["contents"]:
                if s["item"] == "spoiled_food":
                    s["count"] += qty; break
            else:
                o["contents"].append({"item": "spoiled_food", "count": qty, "expires_at": None})
            changed = True; n += 1
            external_log.log("spoiled", None, object=o["id"], item=item, qty=qty, where="fridge")
            _push({"type": "spoiled", "object": o["id"], "object_type": o["type"], "position": dict(o["position"]), "item": item, "qty": qty})
        if changed:
            refresh_stock(o)
    return n


# ── 进食 ───────────────────────────────────────────────────────────────────────
def dining_rule(obj: dict | None) -> dict | None:
    """物品类型的 dining 规则 {allow: None|[...], meal?: bool}；非餐桌类 None。"""
    if obj is None:
        return None
    from game.world_state import OBJECT_TYPES
    return OBJECT_TYPES.get(obj.get("type"), {}).get("dining")


def meal_cfg() -> dict:
    from game.economy import cfg
    return cfg().get("meal", {"price": cfg().get("meal_price", 20), "minutes": 30, "gain": {"fullness": 45, "mood": 5}})


def is_streaming(player: dict) -> bool:
    return player.get("scene") == "live" or "streaming" in (player.get("tags") or [])


def start_eating(player: dict, obj: dict, item: str, gain: dict, minutes: float, gts: float) -> dict:
    """登记 busy + eating tag。增量在 on_tick 里按已过时间精确记（不用 timed buff：单个 tick 跨过结束时刻会丢最后一段）。"""
    dur_s = max(1.0, float(minutes) * 60.0)
    if "eating" not in player["tags"]:
        player["tags"].append("eating")
    _busy[player["id"]] = {"kind": "eating", "item": item, "started_gts": gts, "ends_gts": gts + dur_s, "last_gts": gts,
                           "gain": {k: float(v) for k, v in gain.items()}, "applied": {k: 0.0 for k in gain}, "object": obj["id"]}
    return busy_view(player["id"], gts)


def _apply_progress(player: dict, b: dict, upto_gts: float) -> None:
    """把 last_gts → min(upto, ends) 这段的线性增量落到 player（吃完涨完、中断按比例）。"""
    from game.buff_tick import add_var
    end = min(float(upto_gts), b["ends_gts"])
    dur = max(1e-6, b["ends_gts"] - b["started_gts"])
    if end <= b["last_gts"]:
        return
    frac = (end - b["last_gts"]) / dur
    for var, total in b["gain"].items():
        d = total * frac
        if d:
            add_var(player, var, d)
            b["applied"][var] = b["applied"].get(var, 0.0) + d
    b["last_gts"] = end


def cancel(player: dict, reason: str = "left", gts: float | None = None) -> dict | None:
    """中途离开 / 被请出：结算到此刻（按比例），清 busy。"""
    b = _busy.pop(player["id"], None)
    if "eating" in player.get("tags", []):
        player["tags"].remove("eating")
    if b:
        if gts is None:
            from game.time_state import game_now_ts
            gts = game_now_ts()
        _apply_progress(player, b, gts)
        from game import external_log
        external_log.log("eat", player["id"], action="cancelled", item=b["item"], reason=reason, progress=round(min(1.0, (b["last_gts"] - b["started_gts"]) / max(1e-6, b["ends_gts"] - b["started_gts"])), 3))
        _push({"type": "eat_cancelled", "entity": player["id"], "item": b["item"], "reason": reason, "applied": b["applied"]})
    return b


def on_tick(gts: float, players: dict) -> None:
    """按已过时间记增量；到点吃完：摘 tag、清 busy、ws eat_done。调用方持 STATE_LOCK。"""
    from game import inventory, world_state
    for pid, b in list(_busy.items()):
        p = players.get(pid)
        if p is None:
            _busy.pop(pid, None); continue
        _apply_progress(p, b, gts)
        if gts >= b["ends_gts"]:
            _busy.pop(pid, None)
            if "eating" in p.get("tags", []):
                p["tags"].remove("eating")
            name = "一顿饭" if b["item"] == MEAL_ITEM else (inventory.item_def(b["item"]) or {}).get("name", b["item"])
            world_state._pending_messages[pid] = f"吃完了{name}。"
            _push({"type": "eat_done", "entity": pid, "item": b["item"], "gain": b["gain"], "object": b["object"]})


def busy_view(pid: str, gts: float | None = None) -> dict | None:
    b = _busy.get(pid)
    if b is None:
        return None
    if gts is None:
        from game.time_state import game_now_ts
        gts = game_now_ts()
    dur = max(1e-6, b["ends_gts"] - b["started_gts"])
    return {"kind": b["kind"], "item": b["item"], "object": b.get("object"), "started_at": _iso(b["started_gts"]), "ends_at": _iso(b["ends_gts"]),
            "remaining_s": max(0, round(b["ends_gts"] - gts)), "progress": round(min(1.0, max(0.0, (gts - b["started_gts"]) / dur)), 3), "gain": b["gain"]}


def is_busy(pid: str) -> bool:
    return pid in _busy


def export_state() -> dict:
    """进食 busy + 各冰箱内容（object_runtime 表只有 stock 计数；按叠的保质期走检查点 meta）。"""
    from game import world_state
    return {"busy": {k: dict(v) for k, v in _busy.items()},
            "fridge_contents": {o["id"]: [dict(c) for c in o["contents"]] for o in world_state._OBJECTS if o.get("contents") is not None}}


def import_state(d: dict) -> None:
    from game import world_state
    _busy.clear(); _busy.update({k: dict(v) for k, v in (d.get("busy") or {}).items()})
    fc = d.get("fridge_contents") or {}
    for o in world_state._OBJECTS:
        if o.get("contents") is not None and o["id"] in fc:
            o["contents"] = [dict(c) for c in fc[o["id"]]]
            refresh_stock(o)


def _reset_for_tests() -> None:
    _busy.clear()
