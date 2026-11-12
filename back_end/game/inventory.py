"""
背包（W10 ④ 数据层；world-v1.1 加保鲜与上限）。

player["inventory"] = [{"type": <items.json 键>, "count": int, "meta": {...}?, "expires_at": <游戏时刻 epoch 秒>?}]
- 同种物品按（meta, expires_at 所在日）分叠；视图另给 name / class / expires_in_days。
- 上限：MAX_KINDS 种 × 每种 MAX_PER_KIND 个（I-3）；钥匙（class key）不占种数、不限个数。
- 保鲜（§1.4）：items.json `spoil_days` 非空的物品获得时记 expires_at = 获得时刻 + N×24 游戏小时；到期由 food.spoil_tick 整叠变 spoiled_food。
文件类物品（class=file）已作废（Q-5），只为旧检查点保留定义。
"""
import json
from pathlib import Path

MAX_KINDS = 10
MAX_PER_KIND = 20
_ITEMS: dict = {k: v for k, v in json.load(open(Path(__file__).with_name("items.json"), encoding="utf-8")).items() if not k.startswith("_")}
DAY_S = 86400.0


def catalog() -> dict:
    return _ITEMS


def item_def(item: str) -> dict | None:
    return _ITEMS.get(item)


def is_file_item(item: str) -> bool:
    d = _ITEMS.get(item)
    return bool(d and d.get("class") == "file")


def counts_toward_kinds(item: str) -> bool:
    d = _ITEMS.get(item) or {}
    return d.get("class") != "key"


def spoil_days(item: str) -> float | None:
    d = _ITEMS.get(item) or {}
    v = d.get("spoil_days")
    return float(v) if v else None


def expires_at_for(item: str, now_gts: float) -> float | None:
    sd = spoil_days(item)
    return (now_gts + sd * DAY_S) if sd else None


def ensure(player: dict) -> list[dict]:
    inv = player.get("inventory")
    if inv is None:
        inv = player["inventory"] = []
    return inv


def count(player: dict, item: str) -> int:
    return sum(int(e.get("count", 0)) for e in ensure(player) if e.get("type") == item)


def kinds(player: dict) -> set[str]:
    return {e["type"] for e in ensure(player) if counts_toward_kinds(e["type"])}


def _same_day(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return int(a // DAY_S) == int(b // DAY_S)


def add(player: dict, item: str, qty: int = 1, meta: dict | None = None, *, expires_at: float | None = None, now_gts: float | None = None) -> str | None:
    """加物品；返回失败原因（unknown_item / inventory_full / stack_full）或 None。
    expires_at 缺省按 items.json spoil_days 从 now_gts（缺省当前游戏时刻）起算；None 表示不坏。"""
    if item not in _ITEMS:
        return "unknown_item"
    inv = ensure(player)
    if expires_at is None and spoil_days(item):
        if now_gts is None:
            from game.time_state import game_now_ts
            now_gts = game_now_ts()
        expires_at = expires_at_for(item, now_gts)
    if counts_toward_kinds(item):
        if item not in kinds(player) and len(kinds(player)) >= MAX_KINDS:
            return "inventory_full"
        if count(player, item) + qty > MAX_PER_KIND:
            return "stack_full"
    for e in inv:
        if e.get("type") == item and (meta is None or e.get("meta") == meta) and (meta is not None or not e.get("meta")) and _same_day(e.get("expires_at"), expires_at):
            e["count"] = int(e.get("count", 0)) + qty
            if expires_at is not None and e.get("expires_at") is not None:
                e["expires_at"] = min(float(e["expires_at"]), float(expires_at))
            return None
    entry: dict = {"type": item, "count": qty}
    if meta:
        entry["meta"] = meta
    if expires_at is not None:
        entry["expires_at"] = float(expires_at)
    inv.append(entry)
    return None


def remove(player: dict, item: str, qty: int = 1) -> str | None:
    """扣物品；不够返回 no_item。先扣最早到期的那叠。"""
    if count(player, item) < qty:
        return "no_item"
    inv = ensure(player)
    left = qty
    for e in sorted([e for e in inv if e.get("type") == item], key=lambda e: (e.get("expires_at") is None, e.get("expires_at") or 0.0)):
        if left <= 0:
            break
        take = min(left, int(e.get("count", 0)))
        e["count"] -= take; left -= take
        if e["count"] <= 0:
            inv.remove(e)
    return None


def find(player: dict, item: str, **meta) -> dict | None:
    """找第一条 type 匹配且 meta 含给定键值的条目。"""
    for e in ensure(player):
        if e.get("type") == item and all((e.get("meta") or {}).get(k) == v for k, v in meta.items()):
            return e
    return None


def remove_entry(player: dict, entry: dict, qty: int = 1) -> None:
    inv = ensure(player)
    entry["count"] = int(entry.get("count", 0)) - qty
    if entry["count"] <= 0 and entry in inv:
        inv.remove(entry)


def days_left(expires_at: float | None, now_gts: float) -> int | None:
    if expires_at is None:
        return None
    return max(0, int((float(expires_at) - now_gts) // DAY_S))


def _iso(ts: float) -> str:
    from datetime import datetime
    from game.time_state import GAME_TZ
    return datetime.fromtimestamp(ts, GAME_TZ).isoformat(timespec="seconds")


def view(player: dict, now_gts: float | None = None) -> list[dict]:
    """[{type, name, class, count, meta?, expires_at?, expires_in_days?, spoils_in_days?}]：同种合并计数；spoils_in_days = 该种最早到期天数。"""
    if now_gts is None:
        from game.time_state import game_now_ts
        now_gts = game_now_ts()
    out: list[dict] = []
    for e in ensure(player):
        d = _ITEMS.get(e["type"], {})
        exp = e.get("expires_at")
        row = {"type": e["type"], "name": d.get("name", e["type"]), "class": d.get("class"), "count": int(e.get("count", 0))}
        if e.get("meta"):
            row["meta"] = e["meta"]
        if exp is not None:
            row["expires_at"] = _iso(float(exp)); row["expires_in_days"] = days_left(exp, now_gts)
        prev = next((r for r in out if r["type"] == e["type"] and r.get("meta") == row.get("meta") and (exp is None) == (r.get("expires_at") is None)), None)
        if prev is not None and not e.get("meta"):
            prev["count"] += row["count"]
            if exp is not None and (prev.get("expires_in_days") is None or row["expires_in_days"] < prev["expires_in_days"]):
                prev["expires_at"], prev["expires_in_days"] = row["expires_at"], row["expires_in_days"]
            prev["stacks"] = prev.get("stacks", 1) + 1
        else:
            out.append(row)
    for r in out:
        if r.get("expires_in_days") is not None:
            r["spoils_in_days"] = r["expires_in_days"]
    return out
