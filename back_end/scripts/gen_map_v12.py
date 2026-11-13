#!/usr/bin/env python3
"""
world-v1.2 紧凑地图（主播 2026-11-14 定：每栋楼占地缩小、外观整栋贴图、室内瓦片拼；楼名 / sector / arena / 门 id / 物品 id 与 v1 完全一致）。
草案与校验见 scripts/draft_map_v12.py 与 docs/map-v1.2-draft.md。50×37，格式 v2。

  cd back_end && uv run python scripts/gen_map_v12.py [--out game/maps/v1.2] [--print]

布局（x 右 y 下）：
  y0–7   鲸鱼大学 campus x2–30（教学楼 / 图书馆 / 音乐楼 三栋 7×5 并排，过道 y6，校门 (20,7)(21,7) 接南北街）；老渔夫家 x33–41,y1–6；码头 x42–45,y1–9 贴河（河 x46–49）
  y8–9   东西主街；x20–21 南北街（y8–26）；y18 北巷（各家 / 餐厅门前）；y26 南巷
  y10–17 合租房 1F x2–11 | 公园 x13–19 | 广场 x22–31 | 餐厅 x33–42
  y20–25 小千家 x13–20 | 杂货店 x22–29（门朝南开到短巷 y25）| 店主们的家 x31–41
  2F 阿蝉房画在 x2–7,y29–33，楼梯边 (10,16)↔(3,30)
"""
import argparse
import json
import string
from pathlib import Path

W, H = 50, 37
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
buildings: list[dict] = []          # E 的整栋贴图：{id, sector, floor, footprint{x,y,w,h}（外墙含）, doors[{door_id, cell}]（室内侧格）}
SIZES = {"dining_table": (2, 1), "bed": (1, 2), "bed_21": (2, 1), "bath": (1, 2), "fridge": (1, 1), "desk": (1, 1), "desk_12": (1, 2), "book": (1, 1),
         "phone": (1, 1), "stream_desk": (1, 1), "restaurant_table": (2, 1), "bench": (2, 1), "fishing_spot": (1, 1),
         "shop_counter": (1, 1), "game_console": (1, 1), "pc": (1, 1), "pc_desk": (1, 1), "stove": (1, 1), "sofa_tv": (2, 1),
         "bar": (2, 1), "fish_stall": (1, 1), "notice_board": (1, 1), "pc_music": (1, 1), "reading_desk": (1, 1),
         "classroom_desk": (1, 1), "tree": (1, 1), "tree_big": (2, 2), "lamp": (1, 1), "shelf": (1, 1), "boat": (2, 1), "fountain": (2, 2), "piano": (1, 1)}


def fill(x0, y0, x1, y1, ch=None, sec=None, ar=None):
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if ch: tiles[y][x] = ch
            if sec: sector[y][x] = S(sec)
            if ar: arena[y][x] = R(ar)


def house(x0, y0, x1, y1, sec, rooms, doors=(), building=None, floor=1):
    """外墙归第一间房；rooms=[(x0,y0,x1,y1,arena)]；doors=[(x,y)] 墙上开口变地板。building：记进 buildings[]（id 缺省 = sector；None = 不记，如校园围墙）。"""
    if building is not None:
        buildings.append({"id": building or sec, "sector": sec, "floor": floor, "footprint": {"x": x0, "y": y0, "w": x1 - x0 + 1, "h": y1 - y0 + 1}, "doors": []})
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


def edge(eid, kind, a, b, name=None, open_hours=None, allow=None, owner=None, keys=None):
    e = {"id": eid, "kind": kind, "name": name or eid,
         "a": {"arena": ARENAS[arena[a[1]][a[0]]], "x": a[0], "y": a[1]},
         "b": {"arena": ARENAS[arena[b[1]][b[0]]], "x": b[0], "y": b[1]}}
    if open_hours: e["open_hours"] = open_hours
    if allow: e["allow"] = allow
    if owner: e["owner"] = owner
    if owner: e["keys"] = keys if keys is not None else len(owner)      # §3.41：钥匙总数（缺省 = 每个 owner 一把）
    edges.append(e)


# ── 河与码头（右上，贴河）─────────────────────────────────────────────────────
fill(46, 0, 49, H - 1, "b", "outside", "water")
fill(42, 1, 45, 9, "F", "outside", "dock")
obj("fish_stall", "fish_stall", 42, 1); obj("fishing_spot_1", "fishing_spot", 45, 2); obj("fishing_spot_2", "fishing_spot", 45, 6); obj("boat", "boat", 43, 9)

# ── 街道 ─────────────────────────────────────────────────────────────────────
fill(0, 8, 45, 9, "F", "outside", "street")             # 东西主街
fill(20, 0, 21, 26, "F", "outside", "street")           # 南北街（穿校园，校门口 y7 由 house 开口）
fill(2, 18, 45, 18, "F", "outside", "lane")             # 北巷：合租房 / 餐厅门前
fill(12, 26, 41, 26, "F", "outside", "lane")            # 南巷：小千家 / 店主家门前
fill(36, 7, 36, 7, "F", "outside", "lane")              # 渔夫家门前一格（门 (36,6)）
fill(22, 25, 29, 25, "F", "outside", "lane")            # 杂货店门前短巷 y25：西接南北街 (21,25)、南接南巷 y26
obj("notice_board_street", "notice_board", 19, 10); obj("lamp_1", "lamp", 22, 10); obj("lamp_2", "lamp", 12, 19)

# ── 鲸鱼大学（校园外墙 x2–30,y0–7；校门 (20,7)(21,7)）────────────────────────
house(2, 0, 30, 7, "university", rooms=[(3, 1, 29, 6, "campus")], doors=[(20, 7), (21, 7)])                  # 围墙不记 buildings（E 按瓦片）
fill(3, 1, 29, 6, "F", "university", "campus")
house(3, 1, 9, 5, "university", rooms=[(4, 2, 8, 4, "classroom")], doors=[(5, 5)], building="classroom")     # v1.2.1：门格跟外观图（E 量表）
obj("classroom_desk_1", "classroom_desk", 4, 2); obj("classroom_desk_2", "classroom_desk", 6, 2); obj("pc_lab", "pc_desk", 8, 2)
house(11, 1, 17, 5, "university", rooms=[(12, 2, 16, 4, "library")], doors=[(14, 5)], building="library")
obj("reading_desk_1", "reading_desk", 12, 2); obj("reading_desk_2", "reading_desk", 14, 2); obj("shelf_lib_1", "shelf", 16, 2); obj("shelf_lib_2", "shelf", 16, 4)
house(23, 1, 29, 5, "university", rooms=[(24, 2, 28, 4, "music_room")], doors=[(24, 5)], building="music_room")
obj("pc_music", "pc_music", 24, 2); obj("piano", "piano", 28, 2)
edge("school_gate_w", "gate", (20, 8), (20, 7), "校门", open_hours=[["06:00", "23:00"]])
edge("school_gate_e", "gate", (21, 8), (21, 7), "校门", open_hours=[["06:00", "23:00"]])
edge("door_classroom", "door", (5, 6), (5, 5), "教学楼门", open_hours=[["08:00", "20:00"]])
edge("door_library", "door", (14, 6), (14, 5), "图书馆门", open_hours=[["09:00", "21:00"]])
edge("door_music", "door", (24, 6), (24, 5), "音乐楼门", open_hours=[["08:00", "22:00"]])

# ── 老渔夫家（x33–41,y1–6；门 (37,6) → (37,7) 小巷 → 主街）─────────────────────
house(33, 1, 41, 6, "fisher_house", rooms=[(34, 2, 36, 5, "fisher_bedroom"), (38, 2, 40, 5, "fisher_kitchen")], doors=[(36, 6)], building="")
wall(37, 2, 37, 4, ar="fisher_bedroom"); arena[5][37] = R("fisher_bedroom")   # (37,5) 卧室↔厨房内门；大门 (36,6) 开在卧室底墙
obj("bed_fisher", "bed", 34, 2); obj("stove_fisher", "stove", 38, 2); obj("fridge_fisher", "fridge", 40, 2); obj("table_fisher", "dining_table", 38, 4)
edge("door_fisher", "door", (36, 7), (36, 6), "渔夫家门", owner=["npc_fisher"])
access["fisher_bedroom"] = {"owner": ["npc_fisher"]}
access["fisher_kitchen"] = {"owner": ["npc_fisher"]}

# ── 合租房 1F（x2–11,y10–17；门 (9,17) → 北巷 (9,18)）与 2F（x2–7,y29–33）────────
house(2, 10, 11, 17, "home", rooms=[(3, 11, 5, 13, "whale_room"), (7, 11, 10, 16, "living_room"), (3, 15, 5, 16, "kitchen")], doors=[(9, 17)], building="")
arena[17][9] = R("living_room")                          # 门格归客厅
wall(6, 11, 6, 16, door=(6, 12), ar="whale_room"); tiles[16][6] = "f"; arena[16][6] = R("kitchen")   # 鲸仔房↔客厅 (6,12)；厨房↔客厅 (6,16)
wall(3, 14, 5, 14, ar="whale_room")                      # 鲸仔房 ↔ 厨房 之间的墙
obj("bed_whale", "bed", 3, 11); obj("pc_whale", "pc", 5, 11); obj("shelf_whale", "book", 5, 13)
obj("table_home", "dining_table", 7, 11); obj("sofa_tv", "sofa_tv", 7, 15)
obj("fridge_home", "fridge", 5, 15); obj("stove", "stove", 3, 15)
edge("door_home", "door", (9, 18), (9, 17), "合租房大门", owner=["whale", "achan"], keys=3)
access["whale_room"] = {"owner": ["whale"]}
access["living_room"] = {"owner": ["whale", "achan"]}
access["kitchen"] = {"owner": ["whale", "achan"]}
house(2, 29, 7, 33, "home", rooms=[(3, 30, 6, 32, "achan_room")], building="home_2f", floor=2)     # 2F：画布另一处，无门
obj("bed_achan", "bed_21", 3, 32); obj("pc_achan", "pc_desk", 6, 30); obj("shelf_achan", "book", 6, 32)
edge("stairs_home", "stairs", (10, 16), (3, 30), "合租房楼梯")
access["achan_room"] = {"owner": ["achan"], "locked": [["09:00", "18:30"]], "allow_when_locked": []}

# ── 公园（x13–19,y10–17，十字小路）与广场（x22–31,y10–17）─────────────────────
fill(13, 10, 19, 17, "#", "outside", "park")
fill(13, 13, 19, 13, "F", "outside", "park"); fill(16, 10, 16, 17, "F", "outside", "park")
obj("tree_1", "tree_big", 13, 10); obj("tree_2", "tree_big", 17, 16); obj("tree_3", "tree", 14, 16); obj("tree_4", "tree", 15, 11)   # v1.2.2：树冠别盖告示牌——tree_4 离开 (18,11)（画在 (19,10) 之后会盖住），tree_2 左挪一格离广场告示牌 (22,17)
obj("bench_park_1", "bench", 14, 12); obj("bench_park_2", "bench", 17, 14)
fill(22, 10, 31, 17, "F", "outside", "square")
obj("fountain", "fountain", 26, 12)
obj("bench_square_1", "bench", 23, 11); obj("bench_square_2", "bench", 29, 11); obj("bench_square_3", "bench", 26, 16)
obj("notice_board_square", "notice_board", 22, 17); obj("lamp_3", "lamp", 31, 10)

# ── 餐厅（x33–42,y10–17；门 (35,17) → 北巷 (35,18)）──────────────────────────
house(33, 10, 42, 17, "restaurant", rooms=[(34, 11, 38, 16, "dining"), (40, 11, 41, 16, "rest_kitchen")], doors=[(35, 17)], building="")
wall(39, 11, 39, 16, door=(39, 13), ar="dining")
obj("table_rest_1", "restaurant_table", 34, 11); obj("table_rest_2", "restaurant_table", 34, 14); obj("bar", "bar", 37, 11)
obj("fridge_rest", "fridge", 41, 11); obj("stove_rest", "stove", 40, 15)
edge("door_restaurant", "door", (35, 18), (35, 17), "餐厅门", open_hours=[["11:00", "14:00"], ["17:00", "21:00"]], owner=["npc_rest_owner"])

# ── 杂货店（x22–29,y20–24；v1.2.1 门跟外观图：南墙最西 (23,24) → 短巷 (23,25) → 南北街 / 南巷）──
house(22, 20, 29, 24, "grocery", rooms=[(23, 21, 28, 23, "grocery_shop")], doors=[(23, 24)], building="")
obj("counter", "shop_counter", 28, 22); obj("shelf_1", "shelf", 23, 21); obj("shelf_2", "shelf", 24, 23); obj("shelf_3", "shelf", 28, 21)   # shelf_2 让出门内格 (23,23)
edge("door_grocery", "door", (23, 25), (23, 24), "杂货店门", open_hours=[["09:00", "22:00"]], owner=["npc_grocer"])

# ── 小千家（x13–20,y20–25；门 (16,25) → 南巷 (16,26)）与店主们的家（x31–41,y20–25；门 (36,25) → (36,26)）──
house(13, 20, 20, 25, "xiaoqian_house", rooms=[(14, 21, 16, 24, "xiaoqian_room"), (18, 21, 19, 24, "xiaoqian_kitchen")], doors=[(15, 25)], building="")
wall(17, 21, 17, 24, door=(17, 23), ar="xiaoqian_room")
obj("bed_xiaoqian", "bed", 14, 21); obj("table_xiaoqian", "dining_table", 14, 23); obj("stove_xiaoqian", "stove", 18, 21); obj("fridge_xiaoqian", "fridge", 19, 21)
edge("door_xiaoqian", "door", (15, 26), (15, 25), "小千家门", owner=["npc_xiaoqian"])
access["xiaoqian_room"] = {"owner": ["npc_xiaoqian"]}
access["xiaoqian_kitchen"] = {"owner": ["npc_xiaoqian"]}
house(31, 20, 41, 25, "owners_house", rooms=[(32, 21, 33, 24, "owner_rest_room"), (35, 21, 37, 24, "owners_kitchen"), (39, 21, 40, 24, "owner_grocer_room")], doors=[(34, 25)], building="")
arena[25][34] = R("owners_kitchen")                      # 门格归厨房；门 (34,25) 正对内墙 x34 → 底排 (34,24) 开成过道（左老板房 / 右厨房）
wall(34, 21, 34, 24, door=(34, 23), ar="owner_rest_room"); tiles[24][34] = "f"; arena[24][34] = R("owners_kitchen"); wall(38, 21, 38, 24, door=(38, 22), ar="owners_kitchen")
obj("bed_owner_rest", "bed_21", 32, 21); obj("stove_owners", "stove", 35, 21); obj("fridge_owners", "fridge", 37, 21); obj("table_owners", "dining_table", 36, 23)
obj("bed_owner_grocer", "bed_21", 39, 21)
edge("door_owners", "door", (34, 26), (34, 25), "店主家门", owner=["npc_rest_owner", "npc_grocer"])
for a_ in ("owner_rest_room", "owners_kitchen", "owner_grocer_room"):
    access[a_] = {"owner": ["npc_rest_owner", "npc_grocer"]}

# ── 装饰层 decor[]：v1.2 去掉草坪装饰树 / 池塘 / 晾衣绳 / 花坛（主播定），只留空表（E 的外观走整栋贴图）──
decor: list[dict] = []

# ── 码头栈道边（主街 ↔ 小巷无门，不设边）──
PLAYER_START = {"x": 4, "y": 13, "facing": "down"}       # 鲸仔房间
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


def _buildings_with_doors() -> list[dict]:
    """给每栋楼挂上室内侧门格（edges 的 b 落在占地内即属它；楼梯边归 2F 房）。"""
    out = []
    for b in buildings:
        fp = b["footprint"]
        inside = lambda c: fp["x"] <= c["x"] < fp["x"] + fp["w"] and fp["y"] <= c["y"] < fp["y"] + fp["h"]
        ds = [{"door_id": e["id"], "cell": {"x": e["b"]["x"], "y": e["b"]["y"]}, "kind": e["kind"]} for e in edges if inside(e["b"])]
        out.append({**b, "doors": ds})
    return out


def build(out_dir: Path) -> dict:
    return {
        "format": 2,
        "meta": {"name": "鲸鱼大学城·v1.2 紧凑版", "width": W, "height": H, "player_start": PLAYER_START, "bible": "docs/world-bible/02-map.md v0.1 + docs/map-v1.2-draft.md"},
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
        "buildings": _buildings_with_doors(),
        "tiled": build_tiled(out_dir),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "game" / "maps" / "v1.2"))
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
