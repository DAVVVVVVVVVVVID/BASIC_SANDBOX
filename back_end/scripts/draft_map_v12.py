#!/usr/bin/env python3
"""
world-v1.2 紧凑地图 **草案**（主播 11-14 定：每栋楼占地缩小、外观整栋贴图、室内仍瓦片拼；楼名 / sector / arena / 门 id 全部不改）。
只打印 ASCII 平面图 + 校验（每件物品的站位格可走、从出生点 BFS 全部物品可达、家 ↔ 餐厅等步数），**不写任何地图文件**。
主播点头后把这里的布局搬进 gen_map_v12.py。

  cd back_end && uv run python scripts/draft_map_v12.py
"""
from collections import deque

W, H = 50, 37
tiles = [["#"] * W for _ in range(H)]
label = [[" "] * W for _ in range(H)]        # ASCII 里标楼 / 区域的字母
objects: list[dict] = []
edges: list[tuple] = []
SIZES = {"dining_table": (2, 1), "bed": (1, 2), "bed_21": (2, 1), "fridge": (1, 1), "book": (1, 1), "pc": (1, 1), "pc_desk": (1, 1),
         "stove": (1, 1), "sofa_tv": (2, 1), "restaurant_table": (2, 1), "bar": (2, 1), "bench": (2, 1), "fishing_spot": (1, 1),
         "shop_counter": (1, 1), "fish_stall": (1, 1), "notice_board": (1, 1), "pc_music": (1, 1), "reading_desk": (1, 1),
         "classroom_desk": (1, 1), "tree": (1, 1), "tree_big": (2, 2), "shelf": (1, 1), "boat": (2, 1), "fountain": (2, 2), "piano": (1, 1), "lamp": (1, 1)}
USE_POS = {"bed": [(0, 0)], "bed_21": [(0, 0)], "pc": [(0, 1)], "pc_desk": [(0, 1)], "stove": [(0, 1)], "pc_music": [(0, 1)], "classroom_desk": [(0, 1)],
           "reading_desk": [(0, 1), (1, 0)], "bar": [(0, 1), (1, 1)], "dining_table": [(0, 1), (1, 1), (0, -1), (1, -1)],
           "restaurant_table": [(0, 1), (1, 1), (0, -1), (1, -1)], "bench": [(0, 0), (1, 0)], "sofa_tv": [(0, 0), (1, 0)]}


def fill(x0, y0, x1, y1, ch, lab=None):
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            tiles[y][x] = ch
            if lab:
                label[y][x] = lab


def house(x0, y0, x1, y1, lab, doors=()):
    fill(x0, y0, x1, y1, ".", lab); fill(x0 + 1, y0 + 1, x1 - 1, y1 - 1, "f", lab)
    for x, y in doors:
        tiles[y][x] = "f"


def wall(x0, y0, x1, y1, door=None):
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            tiles[y][x] = "."
    if door:
        tiles[door[1]][door[0]] = "f"


def obj(oid, typ, x, y):
    w, h = SIZES[typ]
    for dy in range(h):
        for dx in range(w):
            tiles[y + dy][x + dx] = "a"
    objects.append({"id": oid, "type": typ, "x": x, "y": y, "w": w, "h": h})


def edge(eid, a, b):
    edges.append((eid, a, b))


# ── 河 / 码头（右上）──
fill(46, 0, 49, H - 1, "b", "~")
fill(42, 1, 45, 9, "F", "d")                                   # dock x42–45,y1–9（贴河）
obj("fish_stall", "fish_stall", 42, 1); obj("fishing_spot_1", "fishing_spot", 45, 2); obj("fishing_spot_2", "fishing_spot", 45, 6); obj("boat", "boat", 43, 9)
# ── 街道：主街 y8–9（x0–45）；南北街 x20–21（y8–26）；北巷 y18（x2–45，各家门前）；南巷 y26（x12–33）──
fill(0, 8, 45, 9, "F", "=")
fill(20, 0, 21, 26, "F", "|")
fill(2, 18, 45, 18, "F", "-"); fill(12, 26, 41, 26, "F", "-")
obj("notice_board_street", "notice_board", 19, 10); obj("lamp_1", "lamp", 22, 10); obj("lamp_2", "lamp", 12, 19)
# ── 鲸鱼大学 campus x2–30,y0–7（外墙；校门 (20,7)(21,7) 接南北街）──
house(2, 0, 30, 7, "U", doors=[(20, 7), (21, 7)]); fill(3, 1, 29, 6, "F", "u")
house(3, 1, 9, 5, "C", doors=[(6, 5)])                           # 教学楼 7×5：interior x4–8,y2–4；门 (6,5) 开到校园过道 y6
obj("classroom_desk_1", "classroom_desk", 4, 2); obj("classroom_desk_2", "classroom_desk", 6, 2); obj("pc_lab", "pc_desk", 8, 2)
house(11, 1, 17, 5, "L", doors=[(14, 5)])                        # 图书馆 7×5：interior x12–16,y2–4
obj("reading_desk_1", "reading_desk", 12, 2); obj("reading_desk_2", "reading_desk", 14, 2); obj("shelf_lib_1", "shelf", 16, 2); obj("shelf_lib_2", "shelf", 16, 4)
house(23, 1, 29, 5, "M", doors=[(26, 5)])                        # 音乐楼 7×5：interior x24–28,y2–4
obj("pc_music", "pc_music", 24, 2); obj("piano", "piano", 28, 2)
edge("school_gate_w", (20, 8), (20, 7)); edge("school_gate_e", (21, 8), (21, 7))
edge("door_classroom", (6, 6), (6, 5)); edge("door_library", (14, 6), (14, 5)); edge("door_music", (26, 6), (26, 5))
# ── 老渔夫家 x33–41,y1–6（9×6，门 (37,6) 接小巷 x37,y7 → 主街）──
house(33, 1, 41, 6, "F", doors=[(37, 6)]); fill(37, 7, 37, 7, "F", "-")
wall(37, 2, 37, 4)                                                # 卧室 x34–36,y2–5 | 厨房 x38–40,y2–5；(37,5) 门内过道兼内门
obj("bed_fisher", "bed", 34, 2); obj("stove_fisher", "stove", 38, 2); obj("fridge_fisher", "fridge", 40, 2); obj("table_fisher", "dining_table", 38, 4)
edge("door_fisher", (37, 7), (37, 6))
# ── 合租房 1F x2–11,y11–18 → 门 (9,18) 直接开在北巷 y18？不行：改 x2–11,y10–17，门 (9,17) 接北巷 y18 ──
house(2, 10, 11, 17, "H", doors=[(9, 17)])
wall(6, 11, 6, 16, door=(6, 12)); tiles[16][6] = "f"             # 鲸仔房 x3–5,y11–13 | 客厅 x7–10,y11–16；厨房 x3–5,y15–16
wall(3, 14, 5, 14)
obj("bed_whale", "bed", 3, 11); obj("pc_whale", "pc", 5, 11); obj("shelf_whale", "book", 5, 13)
obj("table_home", "dining_table", 7, 11); obj("sofa_tv", "sofa_tv", 7, 15)
obj("fridge_home", "fridge", 5, 15); obj("stove", "stove", 3, 15)
edge("door_home", (9, 18), (9, 17))
# 2F 阿蝉房（画布另一处 x2–7,y29–33，楼梯边 (10,16) ↔ (3,30)）
house(2, 29, 7, 33, "A"); obj("bed_achan", "bed_21", 3, 32); obj("pc_achan", "pc_desk", 6, 30); obj("shelf_achan", "book", 6, 32)
edge("stairs_home", (10, 16), (3, 30))
# ── 公园 x13–19,y10–17 ──
fill(13, 10, 19, 17, "#", "p"); fill(13, 13, 19, 13, "F", "p"); fill(16, 10, 16, 17, "F", "p")
obj("tree_1", "tree_big", 13, 10); obj("tree_2", "tree_big", 18, 16); obj("tree_3", "tree", 14, 16); obj("tree_4", "tree", 18, 11)
obj("bench_park_1", "bench", 14, 12); obj("bench_park_2", "bench", 17, 14)
# ── 广场 x22–31,y10–17 ──
fill(22, 10, 31, 17, "F", "q")
obj("fountain", "fountain", 26, 12); obj("bench_square_1", "bench", 23, 11); obj("bench_square_2", "bench", 29, 11); obj("bench_square_3", "bench", 26, 16)
obj("notice_board_square", "notice_board", 22, 17); obj("lamp_3", "lamp", 31, 10)
# ── 餐厅 x33–42,y10–17（10×8；门 (36,17) 接北巷 y18）──
house(33, 10, 42, 17, "R", doors=[(36, 17)])
wall(39, 11, 39, 16, door=(39, 13))                               # 大堂 x34–38,y11–16 | 后厨 x40–41
obj("table_rest_1", "restaurant_table", 34, 11); obj("table_rest_2", "restaurant_table", 34, 14); obj("bar", "bar", 37, 11)
obj("fridge_rest", "fridge", 41, 11); obj("stove_rest", "stove", 40, 15)       # 后厨门 (39,13) 对着 (40,13) 要留空
edge("door_restaurant", (36, 18), (36, 17))
# ── 杂货店 x22–29,y20–24（8×5；主播定：门朝西 (22,22) 直接开到南北街 (21,22)）──
house(22, 20, 29, 24, "G", doors=[(22, 22)])
obj("counter", "shop_counter", 28, 22); obj("shelf_1", "shelf", 23, 21); obj("shelf_2", "shelf", 23, 23); obj("shelf_3", "shelf", 28, 21)
edge("door_grocery", (21, 22), (22, 22))
# ── 小千家 x13–20,y20–25（8×6；门 (16,25) 接南巷 y26）──
house(13, 20, 20, 25, "X", doors=[(16, 25)])
wall(17, 21, 17, 24, door=(17, 23))                               # 房间 x14–16 | 厨房 x18–19
obj("bed_xiaoqian", "bed", 14, 21); obj("table_xiaoqian", "dining_table", 14, 23); obj("stove_xiaoqian", "stove", 18, 21); obj("fridge_xiaoqian", "fridge", 19, 21)
edge("door_xiaoqian", (16, 26), (16, 25))
# ── 店主们的家 x31–41,y20–25（11×6；门 (36,25) 接南巷 y26）──
house(31, 20, 41, 25, "O", doors=[(36, 25)])
wall(34, 21, 34, 24, door=(34, 23)); wall(38, 21, 38, 24, door=(38, 22))   # 餐厅老板房 x32–33 | 厨房 x35–37 | 店主房 x39–40（(38,23) 对着餐桌，门开 (38,22)）
obj("bed_owner_rest", "bed_21", 32, 21); obj("stove_owners", "stove", 35, 21); obj("fridge_owners", "fridge", 37, 21); obj("table_owners", "dining_table", 36, 23)
obj("bed_owner_grocer", "bed_21", 39, 21)
edge("door_owners", (36, 26), (36, 25))
PLAYER_START = (4, 13)

# ── 校验 ──
walk = {(x, y) for y in range(H) for x in range(W) if tiles[y][x] in ("f", "F", "#")}
problems = []
for o in objects:
    own = {(o["x"] + dx, o["y"] + dy) for dx in range(o["w"]) for dy in range(o["h"])}
    seats = [(o["x"] + dx, o["y"] + dy) for dx, dy in USE_POS.get(o["type"], []) if (o["x"] + dx, o["y"] + dy) not in own]
    if seats:
        ok = [s for s in seats if s in walk]
        need = 2 if o["type"] in ("dining_table", "restaurant_table", "bar") else 1
        if len(ok) < need:
            problems.append(f"{o['id']} 可走站位 {len(ok)} < {need}（{seats}）")
    if o["type"] not in USE_POS:
        adj = {(o["x"] + dx, o["y"] + dy) for dx in range(-1, o["w"] + 1) for dy in range(-1, o["h"] + 1)} - {(o["x"] + dx, o["y"] + dy) for dx in range(o["w"]) for dy in range(o["h"])}
        if not (adj & walk):
            problems.append(f"{o['id']} 没有相邻可走格")
stairs = {(10, 16): (3, 30), (3, 30): (10, 16)}


def bfs(start):
    seen = {start}; q = deque([start])
    while q:
        cx, cy = q.popleft()
        nbrs = [(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)] + ([stairs[(cx, cy)]] if (cx, cy) in stairs else [])
        for n in nbrs:
            if n in walk and n not in seen:
                seen.add(n); q.append(n)
    return seen


reach = bfs(PLAYER_START)
for o in objects:
    adj = {(o["x"] + dx, o["y"] + dy) for dx in range(-1, o["w"] + 1) for dy in range(-1, o["h"] + 1)}
    if not (adj & reach):
        problems.append(f"{o['id']} 从出生点不可达")


def dist(a, b):
    seen = {a: 0}; q = deque([a])
    while q:
        c = q.popleft()
        if c == b:
            return seen[c]
        nbrs = [(c[0] + 1, c[1]), (c[0] - 1, c[1]), (c[0], c[1] + 1), (c[0], c[1] - 1)] + ([stairs[c]] if c in stairs else [])
        for n in nbrs:
            if n in walk and n not in seen:
                seen[n] = seen[c] + 1; q.append(n)
    return None


if __name__ == "__main__":
    print("world-v1.2 草案 %dx%d（v1 为 64x48）" % (W, H))
    print("    " + "".join(str(x // 10) if x % 10 == 0 else " " for x in range(W)))
    print("    " + "".join(str(x % 10) for x in range(W)))
    for y in range(H):
        row = ""
        for x in range(W):
            t = tiles[y][x]
            row += {"b": "~", ".": "#", "a": "o", "F": label[y][x] if label[y][x] in "=|-dqu" else "·", "f": label[y][x].lower() if label[y][x].strip() else ".", "#": " "}[t]
        print(f"{y:3d} {row}")
    print("\n图例：# 墙  o 物品  · 铺地(街/广场/码头)  小写字母 室内地板（c 教学楼 l 图书馆 m 音乐楼 f 渔夫家 h 合租房 a 阿蝉房(2F) r 餐厅 g 杂货店 x 小千家 o 店主家）  ~ 河  空白 草地")
    print("\n物品 %d 件；边 %d 条；校验：%s" % (len(objects), len(edges), "全部通过" if not problems else problems))
    home_door, rest_door, groc_door, gate, dock, music = (9, 18), (36, 18), (21, 22), (20, 8), (43, 8), (26, 6)
    for name, a, b in [("家门→餐厅门", home_door, rest_door), ("家门→杂货店门", home_door, groc_door), ("家门→校门", home_door, gate), ("家门→码头", home_door, dock),
                       ("家门→琴房门", home_door, music), ("餐厅门→杂货店门", rest_door, groc_door), ("鲸仔床边→餐厅门", PLAYER_START, rest_door)]:
        print(f"  {name}: {dist(a, b)} 步（×1 速 = 秒）")
