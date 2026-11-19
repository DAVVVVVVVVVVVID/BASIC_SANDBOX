"""
商店第三期 · 路人顾客（world-v1.4.14；whale shops-system.md §5 + 主播 11-19 修改；命名 / 形象 api-spec §12.32）。

脚本角色（controller "script"、role "passerby"）：不跑大模型、不接自我层、不开经济账户 / QQ / 亲密度，不进 roster。
按时段从南门（gate）进镇 → 走到店 → 做一笔交易（杂货 / 鱼 / 吃饭）→ 走回南门消失。失败（没开门 / 没货 / 太贵 /
没位子 / 等太久 / 店主不在 / 没料 / 后厨没人）说一句、账本记 lost。到店说一句模板话。
自动出现只在 SANDBOX_TOWN=main 或 env SANDBOX_PASSERSBY=1；scenario op spawn_passerby 手动放。
状态（今天的日程、在场路人、序号）进检查点；路人本身不进检查点的角色表（重启时清掉，记一笔）。
"""
import hashlib
import os
import random

from game import shops

_sched: dict = {"day": None, "items": []}       # 今天的到达日程 [{at_gts, purpose, slot}]
_active: dict[str, dict] = {}                   # pid → {purpose, phase, target, budget, patience_until, sprite, seq, ...}
_seq: dict[str, int] = {}                        # day → 当天已用序号
_last_seen_sprite: dict[str, float] = {}         # sprite → 最近一次离场 gts


def pcfg() -> dict:
    return shops.cfg()["passersby"]


def enabled() -> bool:
    v = (os.environ.get("SANDBOX_PASSERSBY") or "").strip().lower()
    if v in ("0", "false", "off"):
        return False
    if v in ("1", "true", "on"):
        return True
    return (os.environ.get("SANDBOX_TOWN") or "") == "main"                    # 主镇进程显式带 SANDBOX_TOWN=main；测试 / 未设一律关


def _seed() -> str:
    from game.world_state import SANDBOX_SEED
    return str(SANDBOX_SEED if SANDBOX_SEED is not None else (os.environ.get("SANDBOX_TOWN") or "main"))


def _h(*parts) -> int:
    return int.from_bytes(hashlib.sha256("|".join(str(p) for p in (_seed(), *parts)).encode()).digest()[:8], "big")


def _rng(*parts) -> random.Random:
    return random.Random(_h(*parts))


def _day(gts: float) -> str:
    return shops._day_key(gts)


def _hm_to_gts(day_gts: float, hm: str) -> float:
    from datetime import timedelta
    dt = shops._dt(day_gts)
    base = (dt - timedelta(hours=4)).replace(hour=0, minute=0, second=0, microsecond=0)
    h, m = map(int, hm.split(":"))
    return (base + timedelta(hours=h, minutes=m)).timestamp()


def _plan_day(gts: float) -> None:
    day = _day(gts)
    if _sched["day"] == day:
        return
    items = []
    for si, s in enumerate(pcfg()["slots"]):
        r = _rng("slot", day, si)
        n = r.randint(int(s["n"][0]), int(s["n"][1]))
        a, b = _hm_to_gts(gts, s["from"]), _hm_to_gts(gts, s["to"])
        for k in range(n):
            items.append({"at_gts": a + (b - a) * (k + r.random()) / max(1, n), "purpose": r.choice(s["purposes"]), "slot": si, "done": False})
    items.sort(key=lambda x: x["at_gts"])
    _sched["day"] = day; _sched["items"] = items


# ── 生成 / 删除 ──────────────────────────────────────────────────────────────
def _pick_sprite(day: str, seq: int, shop_mates: set[str]) -> str:
    from game import world_state
    sprites = list(pcfg()["sprites"])
    used = {p.get("sprite") for p in world_state._players.values() if p.get("role") == "passerby"}
    free = [s for s in sprites if s not in used]
    if free:
        return free[_h("sprite", day, seq) % len(free)]
    pool = [s for s in sprites if s not in shop_mates] or sprites                # 6 套都在用：同店不重复，取最久没出现的
    return min(pool, key=lambda s: (_last_seen_sprite.get(s, 0.0), _h("sprite", day, seq, s)))


def _name(day: str, seq: int) -> str:
    from game import world_state
    names = list(pcfg()["names"]); taken = {p.get("name") for p in world_state._players.values() if p.get("role") == "passerby"}
    taken |= {a.get("name") for a in _active.values()}
    start = _h("name", day, seq) % len(names)
    for i in range(len(names)):
        n = names[(start + i) % len(names)]
        if n not in taken:
            return n
    return names[start] + str(seq)


def spawn(purpose: str, gts: float, at: tuple[int, int] | None = None) -> dict | None:
    """放一个路人（调用方持 STATE_LOCK）。返回 player。"""
    from game import world_state
    if purpose not in ("grocery", "fish_stall", "restaurant"):
        raise ValueError(purpose)
    if len(_active) >= int(pcfg()["max_concurrent"]):
        return None
    day = _day(gts); seq = _seq.get(day, 0) + 1; _seq[day] = seq
    pid = f"passerby_{day.replace('-', '')}_{seq:02d}"
    if pid in world_state._players:
        return None
    mates = {a["sprite"] for a in _active.values() if a["purpose"] == purpose}
    sprite = _pick_sprite(day, seq, mates)
    g = pcfg()["gate"]; x, y = at or (g["x"], g["y"])
    p = world_state._make_player(pid, _name(day, seq), "human", None)
    p.update({"controller": "script", "role": "passerby", "agent_id": pid, "sprite": sprite, "dnd": False, "dnd_auto": False,
              "position": {"x": x, "y": y}, "facing": "up", "inventory": [], "online": True, "away": False})
    r = _rng("budget", day, seq)
    lo, hi = pcfg()["budget"][purpose]
    p["gold"] = r.randint(int(lo), int(hi))
    world_state._players[pid] = p
    world_state._pending_messages[pid] = None
    world_state._use_start_times[pid] = None
    _active[pid] = {"purpose": purpose, "phase": "to_shop", "budget": p["gold"], "sprite": sprite, "seq": seq, "spawned_gts": gts,
                    "patience_until": gts + float(pcfg()["patience_min"][purpose]) * 60 + 3600, "said": False}
    _go_to_shop(p, purpose, gts)
    _log(pid, "spawn", purpose=purpose, sprite=sprite, name=p["name"], budget=p["gold"])
    return p


def _despawn(pid: str, gts: float, reason: str) -> None:
    from game import world_state
    a = _active.pop(pid, None)
    if a:
        _last_seen_sprite[a["sprite"]] = gts
    if pid in world_state._players:
        world_state.remove_player(pid)
    _log(pid, "leave", reason=reason)


# ── 走路 ─────────────────────────────────────────────────────────────────────
def _neighbors(x: int, y: int):
    return {(x + 1, y): "left", (x - 1, y): "right", (x, y + 1): "up", (x, y - 1): "down"}


def _stand_tiles(obj: dict) -> dict[tuple[int, int], str]:
    """站在物件旁边、面朝它的格子 → 朝向。"""
    from game import world_state
    out = {}
    occ = {(t["x"], t["y"]) for o in world_state._OBJECTS for t in (o.get("tiles") or [o["position"]])}
    for t in obj.get("tiles") or [obj["position"]]:
        for (nx, ny), facing in _neighbors(t["x"], t["y"]).items():
            if (world_state._TILE_LOOKUP.get((nx, ny)) or {}).get("walkable") and (nx, ny) not in occ:
                out[(nx, ny)] = facing
    return out


def _shop_object(purpose: str):
    from game import world_state
    if purpose == "grocery":
        return world_state.get_object_by_id(shops.cfg()["ledgers"]["grocery"]["objects"][0])
    if purpose == "fish_stall":
        return world_state.get_object_by_id("fish_stall")
    tables = [o for o in world_state._OBJECTS if o.get("type") == "restaurant_table"]
    free = [o for o in tables if int(o.get("currentUsers", 0)) < int(o.get("maxUsers") or 1)]
    return free[0] if free else (tables[0] if tables else None)


def _go_to_shop(p: dict, purpose: str, gts: float) -> None:
    from game import world_state
    obj = _shop_object(purpose)
    a = _active[p["id"]]
    if obj is None:
        a["phase"] = "leaving"; _go_gate(p); return
    stands = _stand_tiles(obj)
    path = world_state.bfs_path((p["position"]["x"], p["position"]["y"]), set(stands), p)
    if path is None:
        a["phase"] = "leaving"; _fail(p, "closed", purpose, gts, note="走不到店"); return
    a["target_obj"] = obj["id"]; a["stands"] = {f"{k[0]},{k[1]}": v for k, v in stands.items()}
    world_state.start_walk(p["id"], path, "passerby", {"object": obj["id"]})


def _go_gate(p: dict) -> None:
    from game import world_state
    g = pcfg()["gate"]
    path = world_state.bfs_path((p["position"]["x"], p["position"]["y"]), {(g["x"], g["y"])}, p)
    if path:
        world_state.start_walk(p["id"], path, "passerby", {"gate": True})


def _walking(pid: str) -> bool:
    from game import world_state
    return pid in world_state._walks


# ── 交易 ─────────────────────────────────────────────────────────────────────
def _say(p: dict, text: str) -> None:
    try:
        from game import speech
        speech.say(p["id"], text)
    except Exception:
        pass


def _line(kind: str, purpose: str, pid: str) -> str:
    opts = pcfg()["say"][kind][purpose]
    return opts[_h("say", kind, pid) % len(opts)]


def _fail(p: dict, why: str, purpose: str, gts: float, note: str | None = None) -> None:
    _say(p, pcfg()["say"]["fail"].get(why, "算了。"))
    shops.record(purpose, "lost", who=p, amount=0, note=note or why, ref={"reason": why})
    _log(p["id"], "lost", purpose=purpose, reason=why)
    a = _active.get(p["id"])
    if a:
        a["phase"] = "leaving"; a["result"] = why
    _go_gate(p)


def _done(p: dict, purpose: str) -> None:
    _say(p, _line("done", purpose, p["id"]))
    a = _active.get(p["id"])
    if a:
        a["phase"] = "leaving"; a["result"] = "ok"
    _go_gate(p)


def _pay_owner(p: dict, shop: str, price: int, item: str, qty: int, note: str | None = None, ref: dict | None = None) -> None:
    from game import economy
    owner = shops.cfg()["ledgers"][shop]["owner"]
    p["gold"] = int(p.get("gold", 0)) - int(price)
    economy.credit_account(owner, int(price), "income", peer=p["id"], source="passerby", item=item, qty=qty)
    shops.record(shop, "sale", who=p, item=item, qty=qty, unit_price=round(price / max(1, qty), 2), amount=int(price), note=note or "路人", ref=ref)


def _owner_present(shop: str, arena: str) -> bool:
    from game import world_state
    from game.qq import account_of
    o = next((x for x in world_state._players.values() if account_of(x) == shops.cfg()["ledgers"][shop]["owner"]), None)
    if o is None or not o.get("online", True):
        return False
    return world_state.get_zone_at(o["position"]["x"], o["position"]["y"]).get("arena") == arena


def _trade_grocery(p: dict, obj: dict, gts: float) -> None:
    from game import world_state, inventory
    if not world_state.open_state(obj, gts)[0]:
        return _fail(p, "closed", "grocery", gts)
    if not _owner_present("grocery", "grocery_shop") and _rng("unattended", p["id"]).random() < float(pcfg()["unattended_fail_p"]):
        return _fail(p, "unattended", "grocery", gts)
    r = _rng("want", p["id"])
    wants = list(pcfg()["grocery_wants"]); r.shuffle(wants)
    st = obj.get("stock") or {}
    for item in wants:
        price = int((inventory.item_def(item) or {}).get("price") or 0)
        if int(st.get(item, 0)) <= 0 or price <= 0:
            continue
        if price > int(p["gold"]):
            return _fail(p, "too_expensive", "grocery", gts, note=f"{(inventory.item_def(item) or {}).get('name', item)} {price} 金币超预算")
        qty = 1 if price * 2 > int(p["gold"]) or int(st[item]) < 2 else (1 + (r.random() < 0.4))
        st[item] = int(st[item]) - qty
        world_state.refresh_shop_views()
        _pay_owner(p, "grocery", price * qty, item, qty)
        return _done(p, "grocery")
    return _fail(p, "out_of_stock", "grocery", gts)


def _trade_fish(p: dict, obj: dict, gts: float) -> None:
    from game import world_state, fishing
    if not world_state.open_state(obj, gts)[0]:
        return _fail(p, "closed", "fish_stall", gts)
    lst = [m for m in (obj.get("listings") or []) if m.get("freshness") != "spoiled"]
    if not lst:
        return _fail(p, "out_of_stock", "fish_stall", gts)
    afford = [m for m in lst if (fishing.price_of(m) or 10 ** 9) <= int(p["gold"])]
    if not afford:
        return _fail(p, "too_expensive", "fish_stall", gts)
    m = max(afford, key=lambda x: (fishing.price_of(x) or 0))                      # 预算内挑最好的
    price = int(fishing.price_of(m) or 0)
    obj["listings"] = [x for x in obj["listings"] if x is not m]
    world_state.refresh_shop_views()
    _pay_owner(p, "fish_stall", price, "fish", 1, note=f"路人买 {m['name']} {m['weight']:.2f} kg", ref={"fish_id": m["fish_id"]})
    return _done(p, "fish_stall")


def _trade_restaurant(p: dict, obj: dict, gts: float) -> None:
    from game import world_state
    a = _active[p["id"]]
    if int(obj.get("currentUsers", 0)) >= int(obj.get("maxUsers") or 1):
        return _fail(p, "table_full", "restaurant", gts)
    world_state.enter_object(obj["id"], p["id"])
    menu = [m for m in shops.menu_view(world_state._players, world_state._OBJECTS, gts)]
    if not menu or all(m.get("reason") == "shop_closed" for m in menu):
        world_state.leave_object(p["id"], "passerby"); return _fail(p, "closed", "restaurant", gts)
    if all(m.get("reason") == "owner_not_in_kitchen" for m in menu):
        world_state.leave_object(p["id"], "passerby"); return _fail(p, "owner_not_in_kitchen", "restaurant", gts)
    ok = [m for m in menu if m["available"] and m["price"] is not None]
    if not ok:
        world_state.leave_object(p["id"], "passerby"); return _fail(p, "no_ingredients", "restaurant", gts)
    afford = [m for m in ok if int(m["price"]) <= int(p["gold"])]
    if not afford:
        world_state.leave_object(p["id"], "passerby"); return _fail(p, "too_expensive", "restaurant", gts)
    m = afford[_h("dish", p["id"]) % len(afford)]
    res, why, extra = shops.order(p, m["dish"], gts)
    if why:
        world_state.leave_object(p["id"], "passerby"); return _fail(p, why if why in pcfg()["say"]["fail"] else "no_ingredients", "restaurant", gts, note=why)
    a["phase"] = "eating"; a["order_id"] = res["order_id"]


# ── tick ─────────────────────────────────────────────────────────────────────
def on_tick(gts: float) -> None:
    """调用方持 STATE_LOCK。"""
    from game import world_state, food
    if enabled():
        _plan_day(gts)
        for it in _sched["items"]:
            if not it["done"] and gts >= it["at_gts"]:
                it["done"] = True
                if gts - it["at_gts"] < 1800:                                       # 停机补算时不补放半小时前的
                    spawn(it["purpose"], gts)
    for pid, a in list(_active.items()):
        p = world_state._players.get(pid)
        if p is None:
            _active.pop(pid, None); continue
        if _walking(pid):
            continue
        if a["phase"] == "to_shop":
            obj = world_state.get_object_by_id(a.get("target_obj") or "")
            key = f"{p['position']['x']},{p['position']['y']}"
            if obj is None or key not in (a.get("stands") or {}):
                if gts > a["patience_until"]:
                    _fail(p, "too_long", a["purpose"], gts)
                else:
                    _go_to_shop(p, a["purpose"], gts)
                continue
            p["facing"] = a["stands"][key]
            if not a["said"]:
                _say(p, _line("arrive", a["purpose"], pid)); a["said"] = True
            a["phase"] = "trading"
            {"grocery": _trade_grocery, "fish_stall": _trade_fish, "restaurant": _trade_restaurant}[a["purpose"]](p, obj, gts)
        elif a["phase"] == "eating":
            if pid in shops._waiting or food.is_busy(pid):
                continue
            if p.get("usingObjectId"):
                world_state.leave_object(pid, "passerby")
            _done(p, "restaurant")
        elif a["phase"] == "leaving":
            g = pcfg()["gate"]
            if (p["position"]["x"], p["position"]["y"]) == (g["x"], g["y"]):
                _despawn(pid, gts, a.get("result") or "left")
            else:
                _go_gate(p)
                if not _walking(pid):                                               # 回不去门口：直接消失
                    _despawn(pid, gts, "no_path_home")


def _log(pid: str, action: str, **kw) -> None:
    try:
        from game import external_log
        external_log.log("passerby", pid, action=action, **kw)
    except Exception:
        pass


def view() -> dict:
    return {"enabled": enabled(), "day": _sched["day"], "scheduled": [{"at": shops._iso(i["at_gts"]), "purpose": i["purpose"], "done": i["done"]} for i in _sched["items"]],
            "active": {pid: {k: v for k, v in a.items() if k != "stands"} for pid, a in _active.items()}}


# ── 检查点：路人不进角色表；重启时把在场的清掉 ─────────────────────────────
def export_state() -> dict:
    return {"sched": {"day": _sched["day"], "items": [dict(i) for i in _sched["items"]]}, "seq": dict(_seq), "last_seen_sprite": dict(_last_seen_sprite)}


def import_state(d: dict | None) -> None:
    _active.clear(); _seq.clear(); _last_seen_sprite.clear(); _sched["day"] = None; _sched["items"] = []
    if not d:
        return
    s = d.get("sched") or {}
    _sched["day"] = s.get("day"); _sched["items"] = [dict(i) for i in s.get("items") or []]
    _seq.update(d.get("seq") or {}); _last_seen_sprite.update(d.get("last_seen_sprite") or {})


def purge_on_load(players: dict) -> int:
    gone = [pid for pid, p in players.items() if p.get("role") == "passerby"]
    for pid in gone:
        players.pop(pid, None)
    if gone:
        _log(None, "purge_on_restart", players=gone)
    return len(gone)


def _reset_for_tests() -> None:
    import_state(None)
