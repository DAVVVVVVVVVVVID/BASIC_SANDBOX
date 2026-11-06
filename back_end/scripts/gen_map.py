#!/usr/bin/env python3
"""
B16：生成「阿蝉家 + 小镇」地图（MAP_EDITOR 不在本机，按其导出格式直接生成 map.json / objects.json）。

  cd back_end && uv run python scripts/gen_map.py [--out game/maps] [--print]

布局（60 × 40，左上原点）：
  阿蝉家（sector achan_house）：小仓库（鲸仔住，bed/desk/book/phone/stream_desk）、阿蝉房间（bed_21/book）、厨房（fridge/desk_12）
  四个 NPC 家：厨子家（bed/fridge）、杂货商家（店面 desk + 卧室 bed）、渔夫小屋（bed_21/book）、常客家（bed/desk/bath）
  小镇（sector outside）：街道、广场、公园、码头、河
  NPC 名单来自 whale-self personas/：achan（与鲸仔同住）、npc_cook、npc_grocer、npc_fisher、npc_regular
tile 字符沿用现有 tile_chars：# grass  . wall  f floor  F grass1  a object  b water
"""
import argparse
import json
from pathlib import Path

W, H = 60, 40
TILE_CHARS = {"#": "grass", ".": "wall", "f": "floor", "F": "grass1", "a": "object", "b": "water"}

tiles  = [["#"] * W for _ in range(H)]
world  = [["A"] * W for _ in range(H)]
sector = [["A"] * W for _ in range(H)]
arena  = [["A"] * W for _ in range(H)]

SECTORS = {"A": "outside", "B": "achan_house", "C": "cook_house", "D": "grocer_house", "E": "fisher_house", "F": "regular_house",
           "G": "restaurant"}
ARENAS = {
    "A": "grass", "K": "road", "S": "square", "P": "park", "L": "water", "M": "dock",
    "a": "storage", "b": "achan_room", "c": "kitchen",
    "d": "cook_bedroom", "e": "cook_kitchen",
    "g": "grocer_shop", "h": "grocer_bedroom",
    "i": "fisher_hut",
    "j": "regular_bedroom", "k": "regular_bath",
    "r": "dining", "s": "rest_kitchen",
}
ZONE_NAMES = {
    "world": {"town": "鲸仔小镇"},
    "sector": {"outside": "小镇", "achan_house": "阿蝉家", "cook_house": "厨子家", "grocer_house": "杂货商家",
               "fisher_house": "渔夫小屋", "regular_house": "常客家", "restaurant": "餐馆"},
    "arena": {"grass": "草地", "road": "街道", "square": "广场", "park": "公园", "water": "河", "dock": "码头",
              "storage": "小仓库", "achan_room": "阿蝉房间", "kitchen": "厨房",
              "cook_bedroom": "厨子的卧室", "cook_kitchen": "厨子的厨房",
              "grocer_shop": "杂货店", "grocer_bedroom": "杂货商的卧室",
              "fisher_hut": "渔夫的小屋", "regular_bedroom": "常客的卧室", "regular_bath": "常客的浴室",
              "dining": "餐馆大堂", "rest_kitchen": "餐馆后厨"},
}
objects: list[dict] = []
SIZES = {"bed": (1, 2), "bed_21": (2, 1), "bath": (1, 2), "fridge": (1, 1), "desk": (1, 1), "desk_12": (1, 2),
         "book": (1, 1), "phone": (1, 1), "stream_desk": (1, 1),
         "restaurant_table": (2, 1), "bench": (2, 1), "fishing_spot": (1, 1), "shop_counter": (1, 1)}


def fill(x0, y0, x1, y1, ch=None, sec=None, ar=None):
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if ch: tiles[y][x] = ch
            if sec: sector[y][x] = sec
            if ar: arena[y][x] = ar


def house(x0, y0, x1, y1, sec, rooms, doors):
    """外墙 + 内部地板；rooms = [(rx0, ry0, rx1, ry1, arena_char)] 内部分区；doors = [(x, y)] 墙上开口（变地板）。"""
    fill(x0, y0, x1, y1, ".", sec, rooms[0][4])          # 外墙归第一间房的 arena，不落到 grass
    fill(x0 + 1, y0 + 1, x1 - 1, y1 - 1, "f", sec, None)
    for rx0, ry0, rx1, ry1, ar in rooms:
        fill(rx0, ry0, rx1, ry1, None, sec, ar)
    for x, y in doors:
        tiles[y][x] = "f"


def wall_line(x0, y0, x1, y1, door_at=None):
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            tiles[y][x] = "."
            if arena[y][x] == "A":                         # 内墙归相邻房间
                arena[y][x] = arena[y][x - 1] if x > 0 and arena[y][x - 1] != "A" else arena[y - 1][x]
    if door_at:
        tiles[door_at[1]][door_at[0]] = "f"


def obj(oid, typ, x, y):
    w, h = SIZES[typ]
    for dy in range(h):
        for dx in range(w):
            tiles[y + dy][x + dx] = "a"
    objects.append({"id": oid, "type": typ, "position": {"x": x, "y": y}})


# ── 小镇：河与码头（右侧）、街道、广场、公园 ───────────────────────────────────
fill(54, 0, 59, 39, "b", "A", "L")                       # 河
fill(50, 16, 53, 19, "f", "A", "M")                      # 码头（木板用 floor）
fill(0, 19, 53, 20, "F", "A", "K")                       # 东西向主街
fill(28, 0, 29, 39, "F", "A", "K")                       # 南北向主街
fill(30, 21, 41, 30, "F", "A", "S")                      # 广场
fill(2, 23, 14, 36, "#", "A", "P")                       # 公园
# 给走廊 / 街道留下 arena：没标的草地保持 A

# ── 阿蝉家（左上，sector B）：外框 (2,2)-(25,15) ───────────────────────────────
# 内部：小仓库 x3..10 | 墙 x11 | 阿蝉房间 x12..17 | 墙 x18 | 厨房 x19..24 ；y3..14
house(2, 2, 25, 15, "B",
      rooms=[(3, 3, 10, 14, "a"), (12, 3, 17, 14, "b"), (19, 3, 24, 14, "c")],
      doors=[(6, 15), (22, 15)])                         # 小仓库南门、厨房南门通街
wall_line(11, 3, 11, 14, door_at=(11, 9))                # 小仓库 ↔ 阿蝉房间
wall_line(18, 3, 18, 14, door_at=(18, 9))                # 阿蝉房间 ↔ 厨房
# 小仓库（鲸仔）
obj("bed_whale",         "bed",         3, 3)            # 站 (4,3)/(4,4) 朝 left，或 (3,5) 朝 up
obj("desk_whale",        "desk",        10, 3)           # 站 (9,3) 朝 right
obj("book_whale",        "book",        10, 5)
obj("phone_whale",       "phone",       10, 7)
obj("stream_desk_whale", "stream_desk", 3, 13)           # 站 (4,13) 朝 left
# 阿蝉房间
obj("bed_achan",  "bed_21", 13, 3)                       # 站 (13,4)/(14,4) 朝 up
obj("book_achan", "book",   17, 13)
# 厨房
obj("fridge_kitchen", "fridge",  24, 3)                  # 站 (23,3) 朝 right
obj("desk_kitchen",   "desk_12", 19, 12)                 # 餐桌：站 (20,12) 朝 left

# ── 厨子家（sector C，街北、中间）(32,6)-(43,15) ──────────────────────────────
house(32, 6, 43, 15, "C", rooms=[(33, 7, 37, 14, "d"), (39, 7, 42, 14, "e")], doors=[(35, 15)])
wall_line(38, 7, 38, 14, door_at=(38, 11))
obj("bed_cook",    "bed",    33, 7)
obj("fridge_cook", "fridge", 42, 7)
obj("desk_cook",   "desk",   42, 14)

# ── 杂货商家（sector D，街南、西侧）(16,23)-(27,33) ────────────────────────────
house(16, 23, 27, 33, "D", rooms=[(17, 24, 26, 27, "g"), (17, 29, 26, 32, "h")], doors=[(21, 23)])
wall_line(17, 28, 26, 28, door_at=(21, 28))
obj("counter_grocer", "shop_counter", 26, 24)          # 柜台（instant：买零食）
obj("fridge_grocer",  "fridge",       17, 24)
obj("bed_grocer",  "bed",    17, 30)
obj("book_grocer", "book",   26, 32)

# ── 渔夫小屋（sector E，码头边）(44, 22)-(52, 28) ──────────────────────────────
house(44, 22, 52, 28, "E", rooms=[(45, 23, 51, 27, "i")], doors=[(48, 22)])
obj("bed_fisher",    "bed_21", 45, 23)
obj("book_fisher",   "book",   51, 27)
obj("fridge_fisher", "fridge", 51, 23)

# ── 常客家（sector F，街南、东侧）(30, 32)-(43, 39) ────────────────────────────
house(30, 32, 43, 38, "F", rooms=[(31, 33, 37, 37, "j"), (39, 33, 42, 37, "k")], doors=[(34, 32)])
wall_line(38, 33, 38, 37, door_at=(38, 35))
obj("bed_regular",    "bed",    31, 33)
obj("desk_regular",   "desk",   37, 37)
obj("bath_regular",   "bath",   42, 33)
obj("fridge_regular", "fridge", 31, 37)

# ── 餐馆（sector G，码头南）(44, 30)-(53, 38)：大堂两张四人桌 + 后厨 ───────────
house(44, 30, 53, 38, "G", rooms=[(45, 31, 52, 35, "r"), (45, 37, 52, 37, "s")], doors=[(48, 30)])
wall_line(45, 36, 52, 36, door_at=(48, 36))
obj("table_rest_1", "restaurant_table", 46, 32)          # 站 (46,33)/(47,33) 朝 up 或 (46,31)/(47,31) 朝 down
obj("table_rest_2", "restaurant_table", 50, 32)
obj("fridge_rest",  "fridge", 52, 37)

# ── 广场长椅、码头钓位 ─────────────────────────────────────────────────────────
obj("bench_square_1", "bench", 32, 25)
obj("bench_square_2", "bench", 38, 25)
obj("fishing_spot_1", "fishing_spot", 53, 17)            # 站 (52,17) 朝 right
obj("fishing_spot_2", "fishing_spot", 53, 19)

PLAYER_START = {"x": 6, "y": 9, "facing": "down"}        # 小仓库中央


def build():
    return {
        "meta": {"name": "阿蝉家与小镇", "width": W, "height": H, "player_start": PLAYER_START},
        "tile_chars": TILE_CHARS,
        "tiles": ["".join(r) for r in tiles],
        "zone_chars": {"world": {"A": "town"}, "sector": SECTORS, "arena": ARENAS},
        "zone_names": ZONE_NAMES,
        "world_map": ["".join(r) for r in world],
        "sector_map": ["".join(r) for r in sector],
        "arena_map": ["".join(r) for r in arena],
        "events": [],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "game" / "maps"))
    ap.add_argument("--print", action="store_true")
    args = ap.parse_args()
    out = Path(args.out)
    data = build()
    (out / "map.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "objects.json").write_text(json.dumps(objects, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.print:
        print("\n".join(data["tiles"]))
        print()
        print("\n".join(data["arena_map"]))
    print(f"wrote {out/'map.json'} ({W}x{H}), {len(objects)} objects")


if __name__ == "__main__":
    main()
