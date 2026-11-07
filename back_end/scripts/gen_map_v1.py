#!/usr/bin/env python3
"""
世界设定 v1.0 地图草图（W9）：按 docs/world-bible/02-map.md 生成 64×48，地图格式 v2（edges / floors / access / homes）。

  cd back_end && uv run python scripts/gen_map_v1.py [--out game/maps/v1] [--print]

布局（x 右 y 下）：
  y 0–8   鲸鱼大学（校园 campus：教学楼 classroom / 图书馆 library / 音乐楼 music_room），校门在 (30,8)(31,8) 接南北街
  y 1–7   右上 老渔夫家（fisher_bedroom / fisher_kitchen），小巷 x52–53 接街
  y 10–16 码头 dock（钓位×2、渔船、卖鱼摊）贴河；河 x58–63 全高
  y 18–20 东西主街；x30–31 南北街贯通；y31 / y34–35 两条小巷
  x2–15 y21–33 合租房 1F（鲸仔房 whale_room / 客厅 living_room / 厨房 kitchen）；2F 阿蝉房 achan_room 画在 x2–9 y36–41，楼梯边连客厅
  x17–29 y23–33 公园 park；x32–45 y22–30 广场 square；x46–56 y22–30 餐厅（dining / rest_kitchen）；x46–56 y32–38 杂货店 grocery
  x12–20 y36–41 小千家；x22–29 y36–46 店主们的家（餐厅老板 / 杂货店老板 + 共用厨房）
物品按 03-objects.md 3.1 的位置摆，类型沿用旧表或占位类型（数值不改）。
"""
import argparse
import json
import string
from pathlib import Path

W, H = 64, 48
TILE_CHARS = {"#": "grass", ".": "wall", "f": "floor", "F": "grass1", "a": "object", "b": "water"}   # grass1 = 铺地（街道 / 广场 / 码头）
tiles  = [["#"] * W for _ in range(H)]
sector = [["A"] * W for _ in range(H)]
arena  = [["A"] * W for _ in range(H)]

# ── 区域登记：id -> (sector_id, 名字, floor) ──
SECTORS: dict[str, str] = {}       # char -> sector id
ARENAS: dict[str, str] = {}        # char -> arena id
SECTOR_NAMES = {"outside": "小镇", "university": "鲸鱼大学", "fisher_house": "老渔夫家", "home": "合租房", "restaurant": "餐厅",
                "grocery": "杂货店", "xiaoqian_house": "小千家", "owners_house": "店主们的家"}
ARENA_NAMES = {"grass": "草地", "street": "街道", "lane": "小巷", "campus": "校园", "classroom": "教学楼", "library": "图书馆",
               "music_room": "音乐楼·琴房", "fisher_bedroom": "渔夫的卧室", "fisher_kitchen": "渔夫的厨房", "dock": "码头", "water": "河",
               "whale_room": "鲸仔房间", "living_room": "客厅", "kitchen": "厨房", "achan_room": "阿蝉房间（2F）",
               "park": "公园", "square": "广场", "dining": "餐厅大堂", "rest_kitchen": "餐厅后厨", "grocery_shop": "杂货店",
               "xiaoqian_room": "小千的房间", "xiaoqian_kitchen": "小千的厨房",
               "owner_rest_room": "餐厅老板的房间", "owner_grocer_room": "杂货店老板的房间", "owners_kitchen": "店主们的厨房"}
FLOORS = {"achan_room": 2}
_sec_chars = iter(string.ascii_uppercase); _ar_chars = iter(string.ascii_letters + string.digits)
sec_char = {}; ar_char = {}
def S(sid):
    if sid not in sec_char:
        c = next(_sec_chars); sec_char[sid] = c; SECTORS[c] = sid
    return sec_char[sid]
def R(aid):
    if aid not in ar_char:
        c = next(_ar_chars); ar_char[aid] = c; ARENAS[c] = aid
    return ar_char[aid]
S("outside"); R("grass")

objects: list[dict] = []
edges: list[dict] = []
access: dict[str, dict] = {}
SIZES = {"bed": (1, 2), "bed_21": (2, 1), "bath": (1, 2), "fridge": (1, 1), "desk": (1, 1), "desk_12": (1, 2), "book": (1, 1),
         "phone": (1, 1), "stream_desk": (1, 1), "restaurant_table": (2, 1), "bench": (2, 1), "fishing_spot": (1, 1),
         "shop_counter": (1, 1), "game_console": (1, 1), "pc": (1, 1), "pc_desk": (1, 1), "stove": (1, 1), "sofa_tv": (2, 1),
         "bar": (2, 1), "fish_stall": (1, 1), "notice_board": (1, 1), "pc_music": (1, 1), "reading_desk": (1, 1),
         "classroom_desk": (1, 1), "tree": (1, 1), "shelf": (1, 1), "boat": (2, 1), "fountain": (2, 2), "piano": (1, 1)}


def fill(x0, y0, x1, y1, ch=None, sec=None, ar=None):
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if ch: tiles[y][x] = ch
            if sec: sector[y][x] = S(sec)
            if ar: arena[y][x] = R(ar)


def house(x0, y0, x1, y1, sec, rooms, doors=()):
    """外墙归第一间房；rooms=[(x0,y0,x1,y1,arena)]；doors=[(x,y)] 墙上开口变地板。"""
    fill(x0, y0, x1, y1, ".", sec, rooms[0][4])
    fill(x0 + 1, y0 + 1, x1 - 1, y1 - 1, "f", sec, None)
    for rx0, ry0, rx1, ry1, ar in rooms:
        fill(rx0, ry0, rx1, ry1, None, sec, ar)
    for x, y in doors:
        tiles[y][x] = "f"


def wall(x0, y0, x1, y1, door=None, ar=None):
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            tiles[y][x] = "."
            if ar: arena[y][x] = R(ar)
    if door:
        tiles[door[1]][door[0]] = "f"


def obj(oid, typ, x, y):
    w, h = SIZES[typ]
    for dy in range(h):
        for dx in range(w):
            tiles[y + dy][x + dx] = "a"
    objects.append({"id": oid, "type": typ, "position": {"x": x, "y": y}})


def edge(eid, kind, a, b, name=None, open_hours=None, allow=None, owner=None):
    e = {"id": eid, "kind": kind, "name": name or eid,
         "a": {"arena": ARENAS[arena[a[1]][a[0]]], "x": a[0], "y": a[1]},
         "b": {"arena": ARENAS[arena[b[1]][b[0]]], "x": b[0], "y": b[1]}}
    if open_hours: e["open_hours"] = open_hours
    if allow: e["allow"] = allow
    if owner: e["owner"] = owner
    edges.append(e)


# ── 河与码头 ─────────────────────────────────────────────────────────────────
fill(58, 0, 63, H - 1, "b", "outside", "water")
fill(52, 10, 57, 16, "F", "outside", "dock")
obj("fishing_spot_1", "fishing_spot", 57, 11); obj("fishing_spot_2", "fishing_spot", 57, 15)
obj("boat", "boat", 54, 16); obj("fish_stall", "fish_stall", 52, 10)

# ── 街道 ─────────────────────────────────────────────────────────────────────
fill(0, 18, 57, 20, "F", "outside", "street")           # 东西主街
fill(30, 0, 31, H - 1, "F", "outside", "street")        # 南北街（贯通，含校门口）
fill(32, 31, 57, 31, "F", "outside", "lane")            # 餐厅 / 杂货店之间的小巷
fill(0, 34, 57, 35, "F", "outside", "lane")             # 南侧小巷（各家门前）
fill(52, 8, 53, 17, "F", "outside", "lane")             # 渔夫家 / 码头 ↔ 主街
arena[17][28] = R("street"); obj("notice_board_street", "notice_board", 28, 17)      # 街边公告栏（归 street）

# ── 鲸鱼大学（校园外墙 x2–45,y0–8；校门 (30,8)(31,8)）────────────────────────
house(2, 0, 45, 8, "university", rooms=[(3, 1, 44, 7, "campus")], doors=[(30, 8), (31, 8)])
fill(3, 1, 44, 7, "F", "university", "campus")
house(4, 1, 13, 6, "university", rooms=[(5, 2, 12, 5, "classroom")], doors=[(9, 6)])
obj("classroom_desk_1", "classroom_desk", 5, 2); obj("classroom_desk_2", "classroom_desk", 8, 2); obj("pc_lab", "pc_desk", 12, 2)
house(17, 1, 28, 6, "university", rooms=[(18, 2, 27, 5, "library")], doors=[(22, 6)])
obj("reading_desk_1", "reading_desk", 18, 2); obj("reading_desk_2", "reading_desk", 21, 2); obj("shelf_lib_1", "shelf", 27, 2); obj("shelf_lib_2", "shelf", 27, 4)
house(33, 1, 42, 6, "university", rooms=[(34, 2, 41, 5, "music_room")], doors=[(37, 6)])
obj("pc_music", "pc_music", 34, 2); obj("piano", "piano", 41, 2)
edge("school_gate_w", "gate", (30, 9), (30, 8), "校门", open_hours=[["06:00", "23:00"]])
edge("school_gate_e", "gate", (31, 9), (31, 8), "校门", open_hours=[["06:00", "23:00"]])
edge("door_classroom", "door", (9, 7), (9, 6), "教学楼门", open_hours=[["08:00", "20:00"]])
edge("door_library", "door", (22, 7), (22, 6), "图书馆门", open_hours=[["09:00", "21:00"]])
edge("door_music", "door", (37, 7), (37, 6), "音乐楼门", open_hours=[["08:00", "22:00"]])

# ── 老渔夫家（右上）────────────────────────────────────────────────────────────
house(47, 1, 57, 7, "fisher_house", rooms=[(48, 2, 51, 6, "fisher_bedroom"), (53, 2, 56, 6, "fisher_kitchen")], doors=[(52, 7)])
wall(52, 2, 52, 5, door=(52, 4), ar="fisher_bedroom")   # (52,6) 留作门内过道
obj("bed_fisher", "bed", 48, 2); obj("fridge_fisher", "fridge", 56, 2)
edge("door_fisher", "door", (52, 8), (52, 7), "渔夫家门", allow=["owner"], owner=["npc_fisher"])
access["fisher_bedroom"] = {"owner": ["npc_fisher"], "locked": "always"}
access["fisher_kitchen"] = {"owner": ["npc_fisher"], "locked": "always"}

# ── 合租房 1F（x2–15,y21–33）与 2F（x2–9,y36–41）──────────────────────────────
house(2, 21, 15, 33, "home", rooms=[(3, 22, 8, 27, "whale_room"), (10, 22, 14, 32, "living_room"), (3, 29, 8, 32, "kitchen")], doors=[(12, 33)])   # 南门（W10：所有建筑南面进门）
arena[33][12] = R("living_room")                          # 门格归它所邻的客厅
wall(9, 22, 9, 32, door=(9, 24), ar="whale_room")       # 鲸仔房 ↔ 客厅
tiles[30][9] = "f"                                       # 厨房 ↔ 客厅
wall(3, 28, 8, 28, ar="whale_room")                      # 鲸仔房 ↔ 厨房 之间的墙
obj("bed_whale", "bed", 3, 22); obj("pc_whale", "pc", 8, 22); obj("shelf_whale", "book", 8, 27)
obj("table_home", "restaurant_table", 11, 23); obj("sofa_tv", "sofa_tv", 11, 27)
obj("fridge_home", "fridge", 3, 29); obj("stove", "stove", 8, 29)
edge("door_home", "door", (12, 34), (12, 33), "合租房大门")
house(2, 36, 9, 41, "home", rooms=[(3, 37, 8, 40, "achan_room")])     # 2F：画布另一处，无门
obj("bed_achan", "bed_21", 3, 40); obj("pc_achan", "pc_desk", 8, 37); obj("shelf_achan", "book", 8, 40)
edge("stairs_home", "stairs", (14, 32), (3, 37), "合租房楼梯")
access["achan_room"] = {"owner": ["achan"], "locked": [["09:00", "18:30"]], "allow_when_locked": []}

# ── 公园与广场 ────────────────────────────────────────────────────────────────
fill(17, 23, 29, 33, "#", "outside", "park")
fill(17, 28, 29, 28, "F", "outside", "park"); fill(23, 23, 23, 33, "F", "outside", "park")   # 小路
for i, (x, y) in enumerate([(18, 24), (27, 24), (19, 32), (28, 31), (21, 26), (26, 30)]):
    obj(f"tree_{i+1}", "tree", x, y)
obj("bench_park_1", "bench", 24, 26); obj("bench_park_2", "bench", 24, 30)
fill(32, 22, 45, 30, "F", "outside", "square")
obj("fountain", "fountain", 38, 25)
obj("bench_square_1", "bench", 33, 23); obj("bench_square_2", "bench", 42, 23); obj("bench_square_3", "bench", 37, 29)
obj("notice_board_square", "notice_board", 33, 29)

# ── 餐厅（x46–56,y22–30）门朝广场 (46,25) ──────────────────────────────────────
house(46, 22, 56, 30, "restaurant", rooms=[(47, 23, 52, 29, "dining"), (54, 23, 55, 29, "rest_kitchen")], doors=[(51, 30)])   # 南门
wall(53, 23, 53, 29, door=(53, 26), ar="dining")
obj("table_rest_1", "restaurant_table", 48, 23); obj("table_rest_2", "restaurant_table", 48, 28); obj("bar", "bar", 51, 25); obj("fridge_rest", "fridge", 55, 23)
edge("door_restaurant", "door", (51, 31), (51, 30), "餐厅门", open_hours=[["11:00", "14:00"], ["17:00", "21:00"]])

# ── 杂货店（x46–56,y32–38）门朝小巷 (50,32) ────────────────────────────────────
house(46, 32, 56, 38, "grocery", rooms=[(47, 33, 55, 37, "grocery_shop")], doors=[(51, 38)])   # 南门
obj("counter", "shop_counter", 55, 35); obj("shelf_1", "shelf", 47, 33); obj("shelf_2", "shelf", 47, 37); obj("shelf_3", "shelf", 55, 33)
fill(46, 39, 57, 39, "F", "outside", "lane")             # 杂货店门前小巷
edge("door_grocery", "door", (51, 39), (51, 38), "杂货店门", open_hours=[["09:00", "20:00"]])

# ── 小千家（x12–20,y36–41）与店主们的家（x22–29,y36–46）────────────────────────
house(12, 36, 20, 41, "xiaoqian_house", rooms=[(13, 37, 16, 40, "xiaoqian_room"), (18, 37, 19, 40, "xiaoqian_kitchen")], doors=[(16, 41)])   # 南门
wall(17, 37, 17, 40, door=(17, 39), ar="xiaoqian_room")
obj("bed_xiaoqian", "bed", 13, 37); obj("fridge_xiaoqian", "fridge", 19, 37)
fill(12, 42, 29, 42, "F", "outside", "lane"); fill(22, 47, 29, 47, "F", "outside", "lane")   # 小千家 / 店主家门前小巷
edge("door_xiaoqian", "door", (16, 42), (16, 41), "小千家门", allow=["owner"], owner=["npc_xiaoqian"])
access["xiaoqian_room"] = {"owner": ["npc_xiaoqian"], "locked": "always"}
access["xiaoqian_kitchen"] = {"owner": ["npc_xiaoqian"], "locked": "always"}
house(22, 36, 29, 46, "owners_house", rooms=[(23, 37, 28, 39, "owner_rest_room"), (23, 41, 28, 42, "owners_kitchen"), (23, 44, 28, 45, "owner_grocer_room")], doors=[(26, 46)])   # 南门
arena[46][26] = R("owner_grocer_room")                    # 门格归它所邻的杂货店主房
wall(23, 40, 28, 40, door=(25, 40), ar="owner_rest_room"); wall(23, 43, 28, 43, door=(25, 43), ar="owners_kitchen")
obj("bed_owner_rest", "bed_21", 27, 37); obj("fridge_owners", "fridge", 23, 41); obj("bed_owner_grocer", "bed_21", 27, 45)
edge("door_owners", "door", (26, 47), (26, 46), "店主家门", allow=["owner"], owner=["npc_rest_owner", "npc_grocer"])
for a_ in ("owner_rest_room", "owners_kitchen", "owner_grocer_room"):
    access[a_] = {"owner": ["npc_rest_owner", "npc_grocer"], "locked": "always"}

# ── 装饰层 decor[]（W10，E 的外观底图参考；不可交互。path / pond 同时改 tile，其余只记位置）──
decor: list[dict] = []
def path_tiles(pts, arena_id="grass"):
    for x, y in pts:
        if tiles[y][x] == "#":
            tiles[y][x] = "F"
    decor.append({"id": f"path_{len(decor)+1}", "kind": "path", "tiles": [{"x": x, "y": y} for x, y in pts]})
def pond(x0, y0, x1, y1):
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            tiles[y][x] = "b"
    decor.append({"id": f"pond_{len(decor)+1}", "kind": "pond", "tiles": [{"x": x, "y": y} for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]})
# 西草坪 x0–29 y9–17：小径从街道斜到合租房前，小池塘，晾衣绳（合租房门口附近），几棵树
path_tiles([(29, 12), (28, 12), (27, 13), (26, 13), (25, 14), (24, 14), (23, 15), (22, 15), (21, 16), (20, 16), (19, 17), (18, 17)])
pond(8, 11, 10, 13)
decor.append({"id": "clothesline_home", "kind": "clothesline", "tiles": [{"x": 4, "y": 16}, {"x": 5, "y": 16}, {"x": 6, "y": 16}]})
for i, (x, y) in enumerate([(3, 10), (14, 10), (16, 15), (12, 16), (25, 10)]):
    obj(f"tree_w{i+1}", "tree", x, y)
# 东草坪 x32–51 y9–17：小径从校门斜到码头巷，小池塘，花坛（只记位置），几棵树
path_tiles([(33, 10), (34, 10), (35, 11), (36, 11), (37, 12), (38, 12), (39, 13), (40, 13), (41, 14), (42, 14), (43, 15), (44, 15), (45, 16), (46, 16), (47, 17), (48, 17), (49, 17), (50, 17), (51, 17)])
pond(40, 9, 42, 10)
decor.append({"id": "flowerbed_e", "kind": "flowerbed", "tiles": [{"x": 36, "y": 15}, {"x": 37, "y": 15}, {"x": 36, "y": 16}, {"x": 37, "y": 16}]})
for i, (x, y) in enumerate([(34, 14), (46, 11), (50, 13), (43, 9)]):
    obj(f"tree_e{i+1}", "tree", x, y)

# ── 码头栈道边（主街 ↔ 小巷无门，不设边）──
PLAYER_START = {"x": 5, "y": 25, "facing": "down"}       # 鲸仔房间
HOMES = {"whale": "whale_room", "achan": "achan_room", "npc_fisher": "fisher_bedroom", "npc_xiaoqian": "xiaoqian_room",
         "npc_rest_owner": "owner_rest_room", "npc_grocer": "owner_grocer_room"}


def build_tiled(out_dir: Path):
    gids = {"grass": 1, "grass1": 18, "wall": 9, "floor": 7, "object": 7, "water": 11}
    tileset = {"name": "whale_gen_tiles", "firstgid": 1, "tilewidth": 16, "tileheight": 16, "tilecount": 18, "columns": 8,
               "imageSource": "gen/tiles.png", "imageWidth": 128, "imageHeight": 48, "margin": 0, "spacing": 0}
    ov_path = out_dir / "tile_gids.json"
    if ov_path.exists():
        ov = json.loads(ov_path.read_text(encoding="utf-8"))
        gids.update({k: v for k, v in ov.items() if not k.startswith("_") and isinstance(v, int)})
        if isinstance(ov.get("_tileset"), dict):
            tileset.update(ov["_tileset"])
    ground = [gids.get(TILE_CHARS[ch], gids["grass"]) for row in tiles for ch in row]
    deco = [gids["wall"] if TILE_CHARS[ch] == "wall" else (gids["water"] if TILE_CHARS[ch] == "water" else 0) for row in tiles for ch in row]
    return {"tilesets": [tileset], "layers": [{"id": 1, "name": "ground", "width": W, "height": H, "data": ground},
                                              {"id": 2, "name": "structures", "width": W, "height": H, "data": deco}]}


def build(out_dir: Path) -> dict:
    return {
        "format": 2,
        "meta": {"name": "鲸鱼大学城·v1.0 草图", "width": W, "height": H, "player_start": PLAYER_START, "bible": "docs/world-bible/02-map.md v0.1"},
        "tile_chars": TILE_CHARS,
        "tiles": ["".join(r) for r in tiles],
        "zone_chars": {"world": {"A": "town"}, "sector": SECTORS, "arena": ARENAS},
        "zone_names": {"world": {"town": "鲸鱼大学城"}, "sector": SECTOR_NAMES, "arena": ARENA_NAMES},
        "world_map": ["A" * W for _ in range(H)],
        "sector_map": ["".join(r) for r in sector],
        "arena_map": ["".join(r) for r in arena],
        "events": [],
        "edges": edges,
        "floors": FLOORS,
        "access": access,
        "homes": HOMES,
        "decor": decor,
        "tiled": build_tiled(out_dir),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "game" / "maps" / "v1"))
    ap.add_argument("--print", action="store_true")
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    src = Path(__file__).resolve().parent.parent / "game" / "maps"
    for f in ("tile_types.json", "tile_gids.json"):
        if (src / f).exists() and not (out / f).exists():
            (out / f).write_text((src / f).read_text(encoding="utf-8"), encoding="utf-8")
    data = build(out)
    (out / "map.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "objects.json").write_text(json.dumps(objects, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.print:
        print("\n".join(data["tiles"]))
    print(f"wrote {out} ({W}x{H}, format 2), {len(objects)} objects, {len(edges)} edges, {len(access)} access rules, floors={FLOORS}, decor={len(decor)}")


if __name__ == "__main__":
    main()
