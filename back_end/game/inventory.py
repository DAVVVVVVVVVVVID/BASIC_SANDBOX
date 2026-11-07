"""
背包（W10 ④ 数据层；③ QQ 文件转交先用）。

player["inventory"] = [{"type": <items.json 键>, "count": int, "meta": {...}?}]（E 的字段名；视图另给 name / class），最多 MAX_KINDS 种。
文件类物品（class=file）走 QQ 时是「复制」（发送者保留），实物只能当面 give。
"""
import json
from pathlib import Path

MAX_KINDS = 10
_ITEMS: dict = {k: v for k, v in json.load(open(Path(__file__).with_name("items.json"), encoding="utf-8")).items() if not k.startswith("_")}


def catalog() -> dict:
    return _ITEMS


def item_def(item: str) -> dict | None:
    return _ITEMS.get(item)


def is_file_item(item: str) -> bool:
    d = _ITEMS.get(item)
    return bool(d and d.get("class") == "file")


def ensure(player: dict) -> list[dict]:
    inv = player.get("inventory")
    if inv is None:
        inv = player["inventory"] = []
    return inv


def count(player: dict, item: str) -> int:
    return sum(int(e.get("count", 0)) for e in ensure(player) if e.get("type") == item)


def add(player: dict, item: str, qty: int = 1, meta: dict | None = None) -> str | None:
    """加物品；返回失败原因（unknown_item / inventory_full）或 None。"""
    if item not in _ITEMS:
        return "unknown_item"
    inv = ensure(player)
    for e in inv:
        if e.get("type") == item and (meta is None or e.get("meta") == meta):
            e["count"] = int(e.get("count", 0)) + qty
            return None
    if len({e["type"] for e in inv}) >= MAX_KINDS and item not in {e["type"] for e in inv}:
        return "inventory_full"
    entry = {"type": item, "count": qty}
    if meta:
        entry["meta"] = meta
    inv.append(entry)
    return None


def remove(player: dict, item: str, qty: int = 1) -> str | None:
    """扣物品；不够返回 no_item。"""
    if count(player, item) < qty:
        return "no_item"
    inv = ensure(player)
    left = qty
    for e in list(inv):
        if e.get("type") != item or left <= 0:
            continue
        take = min(left, int(e.get("count", 0)))
        e["count"] -= take; left -= take
        if e["count"] <= 0:
            inv.remove(e)
    return None


def view(player: dict) -> list[dict]:
    out = []
    for e in ensure(player):
        d = _ITEMS.get(e["type"], {})
        row = {"type": e["type"], "name": d.get("name", e["type"]), "class": d.get("class"), "count": int(e.get("count", 0))}
        if e.get("meta"):
            row["meta"] = e["meta"]
        out.append(row)
    return out
