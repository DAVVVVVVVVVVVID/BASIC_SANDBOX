"""
钓鱼 + 鱼摊 v1（world-v1.4.8；whale docs/systems/fishing-system.md「主播 11-19 修改」「鱼摊与新鲜度」「初始个人纪录」）。

- 每竿（interval_min，默认 20 游戏分钟）：按人掷 空竿 / 垃圾 / 鱼（老渔夫另一套；鱼饵从空竿里扣 bait_bonus）；鱼再掷品级 → 该品级等概率挑鱼种；
  重量统一截断正态 N(mean, sd) ∈ [min, max]，与品级无关。
- 鱼 = 逐条物品 {type: fish, count: 1, meta: {fish_id, species, name, tier, weight, caught_at, caught_by, freshness, age_days, in_fridge, age_s, age_at}}。
- 新鲜度：age_s 累计（冰箱里 fridge_rate 倍速），fresh < stale_days ≤ stale < spoiled_days ≤ spoiled；每游戏小时刷一遍背包 / 冰箱 / 摊位。
- 奖励、老渔夫（空竿 −1 心情、钓鱼时社交 +1/h、每日上限 10 h）、个人纪录（初始按表；破纪录事件 + 心情 + 兴奋）。
- 鱼摊：obj["listings"] = 鱼 meta 列表（逐条定价 = 底价 × 重量 × 新鲜度系数）；变质自动下架退回老渔夫背包。
状态进检查点：records / casts / seq。
"""
import json
import math
import random
import uuid
from collections import deque
from pathlib import Path

DAY_S = 86400.0
_CFG_PATH = Path(__file__).parent / "fishing.json"
_cfg: dict = {}
_records: dict[str, dict] = {}          # agent_id（无则 player id）→ {best: {species, name, weight, at} | None, by_species: {species: weight}}
_casts: dict[str, deque] = {}           # player id → 最近 10 竿
_seq = {"n": 0}
_last_refresh = {"hour": None}


def cfg() -> dict:
    if not _cfg:
        _cfg.update(json.loads(_CFG_PATH.read_text(encoding="utf-8")))
    return _cfg


def _rng(*parts) -> random.Random:
    from game.world_state import SANDBOX_SEED
    return random.Random() if SANDBOX_SEED is None else random.Random(":".join(str(p) for p in (SANDBOX_SEED, "fishing", *parts)))


def _iso(gts: float) -> str:
    from game.food import _iso as f
    return f(gts)


def _key(player: dict) -> str:
    return player.get("agent_id") or player["id"]


def is_fisher(player: dict) -> bool:
    return player.get("agent_id") == cfg()["fisher"]["agent"]


def species_def(sp: str) -> dict:
    return cfg()["species"][sp]


# ── 纪录 ─────────────────────────────────────────────────────────────────────
def _initial_record(k: str) -> dict:
    ini = (cfg().get("records_initial") or {}).get(k)
    if not ini:
        return {"best": None, "by_species": {}}
    sp = ini["species"]
    return {"best": {"species": sp, "name": species_def(sp)["name"], "weight": float(ini["weight"]), "at": ini.get("at"), "initial": True},
            "by_species": {sp: float(ini["weight"])}}


def record_of(player: dict) -> dict:
    k = _key(player)
    if k not in _records:
        _records[k] = _initial_record(k)
    return _records[k]


def reset_records_to_table() -> None:
    _records.clear()


# ── 新鲜度 ───────────────────────────────────────────────────────────────────
def _settle(meta: dict, now: float) -> None:
    rate = float(cfg()["freshness"]["fridge_rate"]) if meta.get("in_fridge") else 1.0
    at = float(meta.get("age_at", now))
    meta["age_s"] = float(meta.get("age_s", 0.0)) + max(0.0, now - at) * rate
    meta["age_at"] = now
    days = meta["age_s"] / DAY_S
    fc = cfg()["freshness"]
    meta["age_days"] = round(days, 2)
    meta["freshness"] = "fresh" if days < fc["stale_days"] else ("stale" if days < fc["spoiled_days"] else "spoiled")


def set_in_fridge(meta: dict, on: bool, now: float) -> None:
    _settle(meta, now)
    meta["in_fridge"] = bool(on)


def fresh_factor(freshness: str) -> float | None:
    return {"fresh": 1.0, "stale": float(cfg()["freshness"]["stale_sell"])}.get(freshness)


def price_of(meta: dict) -> int | None:
    f = fresh_factor(meta.get("freshness", "fresh"))
    if f is None:
        return None
    return max(1, int(round(float(species_def(meta["species"])["price_per_kg"]) * float(meta["weight"]) * f)))


# ── 一竿 ─────────────────────────────────────────────────────────────────────
def _weight(r: random.Random) -> float:
    w = cfg()["weight"]
    for _ in range(64):
        x = r.gauss(float(w["mean"]), float(w["sd"]))
        if float(w["min"]) <= x <= float(w["max"]):
            return round(x, 2)
    return round(float(w["mean"]), 2)


def _pick(r: random.Random, probs: dict) -> str:
    x = r.random(); acc = 0.0
    items = [(k, float(v)) for k, v in probs.items() if k != "bait_bonus"]
    for k, v in items:
        acc += v
        if x < acc:
            return k
    return items[-1][0]


def new_fish(species: str, weight: float, caught_by: str, now: float) -> dict:
    sd = species_def(species)
    m = {"fish_id": "f" + uuid.uuid4().hex[:10], "species": species, "name": sd["name"], "tier": sd["tier"], "weight": float(weight),
         "caught_at": _iso(now), "caught_by": caught_by, "in_fridge": False, "age_s": 0.0, "age_at": now}
    _settle(m, now)
    return m


def cast(player: dict, spot_id: str, roll_no: int, now: float) -> dict:
    """掷一竿（调用方持 STATE_LOCK）。返回 cast 记录。"""
    from game import inventory, world_state
    from game.buff_tick import add_var
    c = cfg(); fisher = is_fisher(player)
    who = "npc_fisher" if fisher else "default"
    r = _rng(player["id"], spot_id, roll_no, int(now))
    bait = c.get("bait"); has_bait = bool(bait) and inventory.count(player, bait) > 0
    if has_bait:
        inventory.remove(player, bait, 1)
    probs = dict(c["outcome"][who])
    if has_bait:
        bonus = min(float(probs.get("bait_bonus", 0)), float(probs["empty"]))
        probs["empty"] = float(probs["empty"]) - bonus; probs["fish"] = float(probs["fish"]) + bonus
    result = _pick(r, {k: probs[k] for k in ("empty", "junk", "fish")})
    _seq["n"] += 1
    rec: dict = {"cast_no": _seq["n"], "at": _iso(now), "result": result, "spot": spot_id, "bait": has_bait, "big": False,
                 "record_break": False, "species_record": False, "effects": {}}
    eff: dict[str, float] = {}
    emotions: list[tuple[str, float]] = []
    rw = c["rewards"]
    msg = None
    if result == "empty":
        if fisher:
            eff.update(rw["empty_fisher"])
    elif result == "junk":
        item = r.choice(c["junk"])
        err = inventory.add(player, item, 1)
        rec["item"] = item; rec["item_name"] = (inventory.item_def(item) or {}).get("name", item)
        if err:
            rec["error"] = err
        eff.update(rw["junk"])
        msg = f"钓上来一个{rec['item_name']}……"
    else:
        tier = _pick(r, c["tier_p"][who])
        sps = sorted(k for k, v in c["species"].items() if v["tier"] == tier)
        sp = r.choice(sps); w = _weight(r)
        meta = new_fish(sp, w, _key(player), now)
        err = inventory.add(player, "fish", 1, meta=meta)
        rec["fish"] = {k: meta[k] for k in ("fish_id", "species", "name", "tier", "weight")}
        if err:
            rec["error"] = err
        tr = rw[tier]
        for k, v in tr.items():
            if k in ("emotion", "emotion_h"):
                continue
            eff[k] = eff.get(k, 0) + float(v)
        if tr.get("emotion"):
            emotions.append((tr["emotion"], float(tr.get("emotion_h", 2))))
        if w > float(c["weight"]["p90"]):
            rec["big"] = True
            for k, v in rw["big_extra"].items():
                eff[k] = eff.get(k, 0) + float(v)
        R = record_of(player)
        if w > float(R["by_species"].get(sp, 0.0)):
            rec["species_record"] = True
            R["by_species"][sp] = w
        best = R.get("best")
        if best is None or w > float(best["weight"]):
            rec["record_break"] = True
            rec["record"] = {"old": ({k: best[k] for k in ("species", "name", "weight")} if best else None),
                             "new": {"species": sp, "name": meta["name"], "weight": w}}
            R["best"] = {"species": sp, "name": meta["name"], "weight": w, "at": _iso(now)}
            for k, v in rw["record"].items():
                if k in ("emotion", "emotion_h"):
                    continue
                eff[k] = eff.get(k, 0) + float(v)
            emotions.append((rw["record"].get("emotion", "excited"), float(rw["record"].get("emotion_h", 4))))
        tname = c["tier_names"][tier]
        msg = f"钓到一条 {w:.2f} kg 的{meta['name']}！" + ("（稀有）" if tier == "rare" else ("（传说！）" if tier == "legend" else "")) + ("这条真大！" if rec["big"] else "")
        if rec["record_break"]:
            old = rec["record"]["old"]
            msg += f" 破纪录了！之前最重的是 {old['weight']:.2f} kg 的{old['name']}。" if old else " 这是你钓到的第一条鱼，记下来！"
        rec["tier_name"] = tname
    for k, v in eff.items():
        add_var(player, k, float(v))
    if emotions:
        world_state.apply_effects(player, [{"type": "emotion_tag", "key": "emotion_tag", "tag": t, "duration": h * 3600 * 1000.0} for t, h in emotions], source="fishing")
    if fisher:                                                          # 老渔夫钓鱼时社交 +social_per_h（按竿摊）
        add_var(player, "social", float(c["fisher"]["social_per_h"]) * float(c["interval_min"]) / 60.0)
    rec["effects"] = {k: round(v, 3) for k, v in eff.items()}
    q = _casts.setdefault(player["id"], deque(maxlen=10)); q.append(rec)
    world_state.daily_count_add(player["id"], "fishing_casts", 1, now)
    if msg:
        prev = world_state._pending_messages.get(player["id"])
        world_state._pending_messages[player["id"]] = (prev + "\n" + msg) if isinstance(prev, str) and prev else msg
    try:
        from game import external_log
        flat = {"outcome": result, "species": (rec.get("fish") or {}).get("species"), "tier": (rec.get("fish") or {}).get("tier"),
                "weight": (rec.get("fish") or {}).get("weight"), "record_broken": rec["record_break"],
                "prev_record": (rec.get("record") or {}).get("old")}                         # A 的 fishing_metrics.py 平铺字段（11-19）
        external_log.log("fishing", player["id"], action="cast", **{k: v for k, v in rec.items() if k not in ("effects",)}, effects=rec["effects"], **flat)
        if rec["record_break"]:
            external_log.log("fishing", player["id"], action="record", **rec["record"])
    except Exception:
        pass
    try:
        from routers.ws import hub
        hub.push_event({"type": "fishing", "entity": player["id"], "cast": rec})
    except Exception:
        pass
    return rec


def view(player: dict, now: float) -> dict:
    from game import world_state
    oid = player.get("usingObjectId")
    obj = world_state.get_object_by_id(oid) if oid else None
    q = list(_casts.get(player["id"]) or [])
    lim = world_state.daily_limit_s("fishing_spot", player["id"])
    return {"spot": oid if obj is not None and obj["type"] == "fishing_spot" else None,
            "casts_today": world_state.daily_count(player["id"], "fishing_casts", now),
            "minutes_today": round(world_state.daily_used_s(player["id"], "fishing_spot", now) / 60.0, 1),
            "limit_min": round(lim / 60.0, 1) if lim else None,
            "last_cast": q[-1] if q else None, "recent_casts": q, "record": record_of(player)}


def daily_limit_min_for(player_id: str | None) -> float | None:
    if not player_id:
        return None
    from game.world_state import _players
    p = _players.get(player_id)
    return float(cfg()["fisher"]["daily_limit_min"]) if p is not None and is_fisher(p) else None


# ── 吃 / 料理 ────────────────────────────────────────────────────────────────
def _scale(meta: dict) -> float:
    return float(meta.get("weight", 1.2)) / float(cfg()["weight"]["scale_ref"])


def pick_fish(entries: list[dict], fish_id: str | None, *, allow_spoiled: bool = False, prefer: str = "oldest") -> dict | None:
    cands = [e for e in entries if e.get("type") == "fish" and e.get("meta")]
    if fish_id:
        return next((e for e in cands if e["meta"].get("fish_id") == fish_id), None)
    if not allow_spoiled:
        cands = [e for e in cands if e["meta"].get("freshness") != "spoiled"]
    if not cands:
        return None
    key = (lambda e: -float(e["meta"].get("age_s", 0))) if prefer == "oldest" else (lambda e: float(e["meta"].get("age_s", 0)))
    return sorted(cands, key=key)[0]


def raw_plan(player: dict, entry: dict, now: float) -> tuple[dict | None, str | None, dict]:
    """生吃：返回 (plan{gain, minutes, name, sick}, reason, extra)。"""
    m = entry["meta"]; _settle(m, now)
    sd = species_def(m["species"])
    if m["freshness"] == "spoiled":
        return None, "spoiled", {"message": f"这条{m['name']}已经变质了，不能吃。", "fish_id": m["fish_id"]}
    if not sd.get("raw"):
        return None, "cannot_eat_raw", {"message": f"{m['name']}不能生吃（会坏肚子），用灶台做成{sd['dish']['name']}再吃。", "fish_id": m["fish_id"]}
    k = _scale(m)
    gain = {v: round(float(x) * k, 2) for v, x in sd["raw"].items()}
    sick = False
    if m["freshness"] == "stale":
        fc = cfg()["freshness"]
        sick = _rng(player["id"], m["fish_id"], "raw").random() < float(fc["stale_raw_sick_p"])
    return {"gain": gain, "minutes": float(cfg()["eat_minutes"]["raw"]), "name": f"生{m['name']}（{_fresh_cn(m['freshness'])}）", "sick": sick,
            "fish": {k2: m[k2] for k2 in ("fish_id", "species", "name", "weight", "freshness")}}, None, {}


def _fresh_cn(f: str) -> str:
    return {"fresh": "新鲜", "stale": "不新鲜", "spoiled": "变质"}.get(f, f)


def dish_meta(fish_meta: dict, now: float) -> dict:
    _settle(fish_meta, now)
    sd = species_def(fish_meta["species"])
    f = fish_meta["freshness"]
    return {"dish": sd["dish"]["name"], "name": f"{sd['dish']['name']}（{_fresh_cn(f)}）", "species": fish_meta["species"], "weight": fish_meta["weight"],
            "freshness": f, "made_at": _iso(now), "from_fish": fish_meta.get("fish_id"), "dish_id": "d" + uuid.uuid4().hex[:10]}


def dish_plan(entry: dict) -> dict:
    m = entry["meta"]; sd = species_def(m["species"])
    k = _scale(m) * (float(cfg()["freshness"]["stale_dish"]) if m.get("freshness") == "stale" else 1.0)
    return {"gain": {v: round(float(x) * k, 2) for v, x in sd["dish"]["gain"].items()}, "minutes": float(cfg()["eat_minutes"]["dish"]), "name": m["name"], "sick": False,
            "dish": {k2: m.get(k2) for k2 in ("dish_id", "dish", "name", "species", "weight", "freshness")}}


# ── 鱼摊 ─────────────────────────────────────────────────────────────────────
def listing_view(meta: dict) -> dict:
    return {"listing_id": meta["fish_id"], "fish_id": meta["fish_id"], "species": meta["species"], "name": meta["name"], "tier": meta["tier"],
            "weight": meta["weight"], "freshness": meta.get("freshness"), "age_days": meta.get("age_days"), "price": price_of(meta)}


def stall_listings(obj: dict) -> list[dict]:
    return [listing_view(m) for m in obj.get("listings") or []]


# ── 每游戏小时：刷新新鲜度、摊位变质下架 ─────────────────────────────────────
def refresh(now: float, players: dict, objects: list[dict], force: bool = False) -> int:
    hour = int(now // 3600)
    if not force and _last_refresh["hour"] == hour:
        return 0
    _last_refresh["hour"] = hour
    n = 0
    from game import shops as _shops
    gone_age = (float(cfg()["freshness"]["spoiled_days"]) + float(_shops.cfg().get("spoiled_vanish_days", 2))) * DAY_S   # v1.4.11：变质后 ~2 日自动消失
    for p in players.values():
        for e in list(p.get("inventory") or []):
            if e.get("type") == "fish" and e.get("meta"):
                _settle(e["meta"], now); n += 1
                if e["meta"].get("age_s", 0) >= gone_age:
                    p["inventory"].remove(e)
                    _vanish_note(p, e["meta"], "inventory")
    owner = next((p for p in players.values() if is_fisher(p)), None)
    for o in objects:
        for c in list(o.get("contents") or []):
            if c.get("item") == "fish" and c.get("meta"):
                _settle(c["meta"], now); n += 1
                if c["meta"].get("age_s", 0) >= gone_age:
                    o["contents"].remove(c)
                    _vanish_note(None, c["meta"], "fridge", o["id"])
                    from game.food import refresh_stock
                    refresh_stock(o)
        if o.get("type") == cfg()["stall"]["type"] and o.get("listings"):
            keep = []
            for m in o["listings"]:
                _settle(m, now); n += 1
                if m["freshness"] == "spoiled":
                    _delist_spoiled(o, m, owner)
                else:
                    keep.append(m)
            o["listings"] = keep
    return n


def _vanish_note(player: dict | None, meta: dict, where: str, obj_id: str | None = None) -> None:
    from game import world_state
    if player is not None:
        msg = f"那条变质的{meta['name']}放太久，扔掉了。"
        prev = world_state._pending_messages.get(player["id"])
        world_state._pending_messages[player["id"]] = (prev + "\n" + msg) if isinstance(prev, str) and prev else msg
    try:
        from game import external_log
        external_log.log("spoil", player["id"] if player else None, action="discard_auto", item="fish", fish_id=meta.get("fish_id"), species=meta.get("species"), where=where, object=obj_id)
    except Exception:
        pass


def _delist_spoiled(obj: dict, meta: dict, owner: dict | None) -> None:
    from game import inventory, world_state
    if owner is not None:
        inventory.add(owner, "fish", 1, meta=meta)
        msg = f"摊上那条 {meta['weight']:.2f} kg 的{meta['name']}变质了，退回你背包（可以丢掉，或拿去杂货店换鱼饵）。"
        prev = world_state._pending_messages.get(owner["id"])
        world_state._pending_messages[owner["id"]] = (prev + "\n" + msg) if isinstance(prev, str) and prev else msg
    try:
        from game import external_log
        external_log.log("fishing", owner["id"] if owner else None, action="stall_spoiled", object=obj["id"], fish_id=meta["fish_id"], species=meta["species"], weight=meta["weight"])
        from game import shops as _shops
        _shops.record("fish_stall", "spoiled", who=owner, item="fish", qty=1, amount=0, note=f"{meta['name']} {meta['weight']:.2f} kg 变质下架，退回老渔夫", ref={"fish_id": meta["fish_id"]})
        from routers.ws import hub
        hub.push_event({"type": "stall_spoiled", "entity": owner["id"] if owner else None, "object": obj["id"], "fish": listing_view(meta)})
    except Exception:
        pass


# ── 检查点 ───────────────────────────────────────────────────────────────────
def export_state() -> dict:
    from game import world_state
    return {"records": json.loads(json.dumps(_records)), "casts": {k: list(v) for k, v in _casts.items()}, "seq": _seq["n"],
            "listings": {o["id"]: [dict(m) for m in o.get("listings") or []] for o in world_state._OBJECTS if o.get("type") == cfg()["stall"]["type"]}}


def import_state(d: dict | None) -> None:
    _records.clear(); _casts.clear(); _seq["n"] = 0; _last_refresh["hour"] = None
    if not d:
        return
    _records.update(d.get("records") or {})
    for k, v in (d.get("casts") or {}).items():
        _casts[k] = deque(v, maxlen=10)
    _seq["n"] = int(d.get("seq") or 0)
    ls = d.get("listings") or {}
    from game import world_state
    for o in world_state._OBJECTS:
        if o.get("type") == cfg()["stall"]["type"]:
            o["listings"] = [dict(m) for m in ls.get(o["id"]) or []]


def _reset_for_tests() -> None:
    import_state(None); _cfg.clear()
