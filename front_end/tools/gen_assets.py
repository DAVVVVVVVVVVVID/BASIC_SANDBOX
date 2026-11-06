#!/usr/bin/env python3
"""
自制像素素材生成器（E6 / E7）。全部由本脚本程序化绘制，无第三方素材，作 CC0 发布。

    python3 tools/gen_assets.py            # 输出到 public/assets/gen/

产物：
  tiles.png / tiles.json     16×16 地砖集（8 列），tiles.json 记录 名字→索引 与「类型/区域 → 地砖」规则
  tile_gids.json             给 B 的 {类型: gid}（firstgid=1，gid = 索引 + 1），附 _tileset 描述本图
  char_<key>.png             角色四向走路：4 行（down/left/right/up）× 4 列（站 / 走A / 站 / 走B），每帧 16×24
  obj_<type>.png             物品，按 footprint 比例（每格 16 px）
"""
from __future__ import annotations
import json, math, os
from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "public" / "assets" / "gen"
OUT.mkdir(parents=True, exist_ok=True)
T = 16

def h2(x: int, y: int, salt: int = 0) -> float:
    h = (x * 374761393 + y * 668265263 + salt * 1442695041) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFFFFFF) / 4294967295

def rgb(hexs: str, a: int = 255):
    hexs = hexs.lstrip('#')
    if len(hexs) == 3: hexs = ''.join(ch * 2 for ch in hexs)
    return (int(hexs[0:2], 16), int(hexs[2:4], 16), int(hexs[4:6], 16), a)

# ───────────────────────────── 地砖 ─────────────────────────────

TILE_NAMES = [
    "grass", "grass_flower", "grass_park", "road", "square", "dock", "floor_wood", "floor_tile",
    "wall_top", "wall_face", "water0", "water1", "water2", "water3", "carpet", "shop_floor",
    "door", "grass_dark",
]
COLS = 8

def tile_grass(d, ox, oy, variant: int, salt: int):
    base = {0: "#5fae5a", 1: "#5fae5a", 2: "#4f9e55", 3: "#4a9450"}[variant]
    dark = {0: "#54a050", 1: "#54a050", 2: "#448f4a", 3: "#3f8544"}[variant]
    d.rectangle([ox, oy, ox + T - 1, oy + T - 1], fill=rgb(base))
    for i in range(14):
        x, y = int(h2(i, salt, 1) * T), int(h2(i, salt, 2) * T)
        d.point((ox + x, oy + y), fill=rgb(dark))
        if h2(i, salt, 3) > 0.6: d.point((ox + x, oy + max(0, y - 1)), fill=rgb("#6dbd66"))
    if variant == 1:  # 小花
        for (fx, fy, c) in [(3, 4, "#ffd166"), (10, 9, "#ff8fab"), (6, 12, "#ffffff")]:
            d.point((ox + fx, oy + fy), fill=rgb(c)); d.point((ox + fx + 1, oy + fy), fill=rgb(c))
            d.point((ox + fx, oy + fy + 1), fill=rgb(c)); d.point((ox + fx + 1, oy + fy + 1), fill=rgb(c))
            d.point((ox + fx, oy + fy + 2), fill=rgb("#3f8544"))
    if variant == 2:  # 公园：更密、更深的草丛
        for i in range(4):
            x, y = int(h2(i, salt, 4) * (T - 2)), int(h2(i, salt, 5) * (T - 3))
            d.line([ox + x, oy + y + 2, ox + x, oy + y], fill=rgb("#3f8544"))
            d.point((ox + x + 1, oy + y + 2), fill=rgb("#3f8544"))

def tile_road(d, ox, oy, salt):
    d.rectangle([ox, oy, ox + T - 1, oy + T - 1], fill=rgb("#b9a98a"))
    for i in range(10):
        x, y = int(h2(i, salt, 6) * T), int(h2(i, salt, 7) * T)
        d.point((ox + x, oy + y), fill=rgb("#a89877"))
    for i in range(4):
        x, y = int(h2(i, salt, 8) * (T - 2)), int(h2(i, salt, 9) * (T - 2))
        d.rectangle([ox + x, oy + y, ox + x + 1, oy + y + 1], fill=rgb("#c9bb9c"))

def tile_square(d, ox, oy):
    d.rectangle([ox, oy, ox + T - 1, oy + T - 1], fill=rgb("#cfc3ad"))
    d.line([ox, oy + 7, ox + T - 1, oy + 7], fill=rgb("#b5a88f"))
    d.line([ox, oy + 15, ox + T - 1, oy + 15], fill=rgb("#b5a88f"))
    d.line([ox + 7, oy, ox + 7, oy + 7], fill=rgb("#b5a88f"))
    d.line([ox + 15, oy, ox + 15, oy + 7], fill=rgb("#b5a88f"))
    d.line([ox + 3, oy + 8, ox + 3, oy + 15], fill=rgb("#b5a88f"))
    d.line([ox + 11, oy + 8, ox + 11, oy + 15], fill=rgb("#b5a88f"))

def tile_planks(d, ox, oy, light, dark, line, vertical=False):
    d.rectangle([ox, oy, ox + T - 1, oy + T - 1], fill=rgb(light))
    for i in range(0, T, 4):
        if vertical: d.line([ox + i, oy, ox + i, oy + T - 1], fill=rgb(line))
        else: d.line([ox, oy + i, ox + T - 1, oy + i], fill=rgb(line))
    for i in range(6):
        x, y = int(h2(i, 0, 11) * T), int(h2(i, 0, 12) * T)
        d.point((ox + x, oy + y), fill=rgb(dark))

def tile_floor_tile(d, ox, oy):
    for y in range(0, T, 8):
        for x in range(0, T, 8):
            c = "#e8e2d2" if ((x + y) // 8) % 2 == 0 else "#d4cdbb"
            d.rectangle([ox + x, oy + y, ox + x + 7, oy + y + 7], fill=rgb(c))
    for i in range(0, T, 8):
        d.line([ox + i, oy, ox + i, oy + T - 1], fill=rgb("#c2b9a6"))
        d.line([ox, oy + i, ox + T - 1, oy + i], fill=rgb("#c2b9a6"))

def tile_wall_top(d, ox, oy):
    d.rectangle([ox, oy, ox + T - 1, oy + T - 1], fill=rgb("#5b4a42"))
    for y in range(0, T, 4):
        off = 0 if (y // 4) % 2 == 0 else 4
        for x in range(-4, T, 8):
            d.rectangle([ox + x + off + 1, oy + y + 1, ox + x + off + 7, oy + y + 3], fill=rgb("#6d5a50"))
    d.line([ox, oy, ox + T - 1, oy], fill=rgb("#7d6a60"))

def tile_wall_face(d, ox, oy):
    d.rectangle([ox, oy, ox + T - 1, oy + T - 1], fill=rgb("#8c7568"))
    for y in range(0, T, 4):
        off = 0 if (y // 4) % 2 == 0 else 4
        for x in range(-4, T, 8):
            d.rectangle([ox + x + off + 1, oy + y + 1, ox + x + off + 7, oy + y + 3], fill=rgb("#a08878"))
    d.rectangle([ox, oy + T - 2, ox + T - 1, oy + T - 1], fill=rgb("#4a3b33"))

def tile_water(d, ox, oy, frame):
    d.rectangle([ox, oy, ox + T - 1, oy + T - 1], fill=rgb("#3d7fc4"))
    for i in range(5):
        y = (i * 3 + frame * 2) % T
        x0 = int(h2(i, frame, 21) * 8)
        d.line([ox + x0, oy + y, ox + x0 + 5, oy + y], fill=rgb("#5a9ad8"))
        d.point((ox + (x0 + 7) % T, oy + y), fill=rgb("#8ec1ea"))
    for i in range(3):
        x, y = int(h2(i, frame, 22) * T), int(h2(i, frame, 23) * T)
        d.point((ox + x, oy + y), fill=rgb("#2f6aa8"))

def tile_carpet(d, ox, oy):
    d.rectangle([ox, oy, ox + T - 1, oy + T - 1], fill=rgb("#a8463f"))
    for i in range(0, T, 4):
        for j in range(0, T, 4):
            if (i + j) % 8 == 0: d.point((ox + i + 1, oy + j + 1), fill=rgb("#c0574f"))
    d.rectangle([ox, oy, ox + T - 1, oy + T - 1], outline=rgb("#8e3a34"))

def tile_shop_floor(d, ox, oy):
    d.rectangle([ox, oy, ox + T - 1, oy + T - 1], fill=rgb("#cdb48f"))
    for y in range(0, T, 8):
        for x in range(0, T, 8):
            if ((x + y) // 8) % 2 == 0: d.rectangle([ox + x, oy + y, ox + x + 7, oy + y + 7], fill=rgb("#bda37e"))

def tile_door(d, ox, oy):
    tile_planks(d, ox, oy, "#b48a5a", "#9a7247", "#8a6540", vertical=True)
    d.rectangle([ox + 2, oy + 6, ox + 13, oy + 9], fill=rgb("#8e6b45"))

def build_tiles():
    rows = math.ceil(len(TILE_NAMES) / COLS)
    img = Image.new("RGBA", (COLS * T, rows * T), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, name in enumerate(TILE_NAMES):
        ox, oy = (i % COLS) * T, (i // COLS) * T
        if name == "grass": tile_grass(d, ox, oy, 0, 1)
        elif name == "grass_flower": tile_grass(d, ox, oy, 1, 2)
        elif name == "grass_park": tile_grass(d, ox, oy, 2, 3)
        elif name == "grass_dark": tile_grass(d, ox, oy, 3, 4)
        elif name == "road": tile_road(d, ox, oy, 5)
        elif name == "square": tile_square(d, ox, oy)
        elif name == "dock": tile_planks(d, ox, oy, "#b48a5a", "#9a7247", "#8a6540")
        elif name == "floor_wood": tile_planks(d, ox, oy, "#d2a86e", "#bf9458", "#b08650")
        elif name == "floor_tile": tile_floor_tile(d, ox, oy)
        elif name == "wall_top": tile_wall_top(d, ox, oy)
        elif name == "wall_face": tile_wall_face(d, ox, oy)
        elif name.startswith("water"): tile_water(d, ox, oy, int(name[-1]))
        elif name == "carpet": tile_carpet(d, ox, oy)
        elif name == "shop_floor": tile_shop_floor(d, ox, oy)
        elif name == "door": tile_door(d, ox, oy)
    img.save(OUT / "tiles.png")
    index = {n: i for i, n in enumerate(TILE_NAMES)}
    meta = {
        "image": "gen/tiles.png", "tile": T, "columns": COLS, "count": len(TILE_NAMES),
        "index": index,
        "rules": {
            "type": {"grass": "grass|grass_flower（按格哈希 12% 开花）", "grass1": "grass_dark", "road": "road", "water": "water0..3 动画 2 fps",
                     "wall": "下方非墙 → wall_face，否则 wall_top", "floor/object": "按 arena：kitchen/bath/rest_kitchen → floor_tile；dining → carpet；grocer_shop → shop_floor；其余 floor_wood"},
            "arena": {"park": "grass_park", "square": "square", "dock": "dock", "road": "road"},
        },
    }
    (OUT / "tiles.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    # 给 B 的 gid 表：B 的 gen_map.py 用 gids.update(json) 覆盖 TILE_GIDS，键是 tile 类型
    gids = {
        "grass": index["grass"] + 1, "grass1": index["grass_dark"] + 1, "wall": index["wall_top"] + 1,
        "floor": index["floor_wood"] + 1, "object": index["floor_wood"] + 1, "water": index["water0"] + 1,
        "_tileset": {"name": "whale_gen_tiles", "firstgid": 1, "tilewidth": T, "tileheight": T, "tilecount": len(TILE_NAMES),
                     "columns": COLS, "imageSource": "gen/tiles.png", "imageWidth": COLS * T, "imageHeight": rows * T, "margin": 0, "spacing": 0},
        "_arena_gids": {"park": index["grass_park"] + 1, "square": index["square"] + 1, "dock": index["dock"] + 1, "road": index["road"] + 1,
                        "kitchen": index["floor_tile"] + 1, "regular_bath": index["floor_tile"] + 1, "cook_kitchen": index["floor_tile"] + 1,
                        "rest_kitchen": index["floor_tile"] + 1, "dining": index["carpet"] + 1, "grocer_shop": index["shop_floor"] + 1},
        "_wall_face": index["wall_face"] + 1, "_water_frames": [index[f"water{i}"] + 1 for i in range(4)],
        "_note": "自制 CC0 地砖（front_end/tools/gen_assets.py）。顶层键是 B 的 TILE_GIDS 覆盖；_ 开头的是给前端/人的说明。",
    }
    (OUT / "tile_gids.json").write_text(json.dumps(gids, ensure_ascii=False, indent=2), encoding="utf-8")
    return index

# ───────────────────────────── 角色 ─────────────────────────────

FW, FH = 16, 24

CHARS = {
    # key: skin, hair, hair2(高光/条纹), shirt, shirt2(前襟/配色), pants, eye, extra
    "whale":    dict(skin="#ffe6d5", hair="#7cc4ff", hair2="#ffffff", shirt="#3b82f6", shirt2="#eaf4ff", pants="#1e3a8a", eye="#1d4ed8", extra="fin"),
    "achan":    dict(skin="#ffe9dc", hair="#f4f4f4", hair2="#dcdcdc", shirt="#4a7fd6", shirt2="#2b3a67", pants="#2f3542", eye="#6b7f99", extra="catears"),
    "cook":     dict(skin="#f5d6b8", hair="#5a3a22", hair2="#7a553a", shirt="#f8f8f8", shirt2="#d94d4d", pants="#3a3a3a", eye="#3a2a1a", extra="chefhat"),
    "grocer":   dict(skin="#f1cfae", hair="#8a5a2b", hair2="#a8743d", shirt="#e0c38c", shirt2="#2f8f5b", pants="#5b4636", eye="#3a2a1a", extra="apron"),
    "fisher":   dict(skin="#e9c2a0", hair="#2b2b2b", hair2="#444", shirt="#f2c14e", shirt2="#e0a800", pants="#2c4a6e", eye="#222", extra="hat"),
    "regular":  dict(skin="#f7dcc4", hair="#c0392b", hair2="#e74c3c", shirt="#b23a48", shirt2="#f0f0f0", pants="#2d3436", eye="#2a1a1a", extra=None),
    "villager": dict(skin="#f3d2b6", hair="#6c5ce7", hair2="#8e7cf0", shirt="#a29bfe", shirt2="#ffffff", pants="#4b4b6b", eye="#2a2a3a", extra=None),
}

def draw_char_frame(img: Image.Image, ox: int, oy: int, c: dict, facing: str, step: int):
    """facing: down/left/right/up；step: 0 站 1 走A 2 走B。右向由左向镜像生成，这里只画 down/left/up。"""
    d = ImageDraw.Draw(img)
    bob = -1 if step else 0
    skin, hair, hair2, shirt, shirt2, pants, eye = (rgb(c[k]) for k in ("skin", "hair", "hair2", "shirt", "shirt2", "pants", "eye"))
    outline = rgb("#2b2230")
    # 腿
    ly = oy + 19 + bob
    if step == 0:
        d.rectangle([ox + 5, ly, ox + 6, ly + 3], fill=pants); d.rectangle([ox + 9, ly, ox + 10, ly + 3], fill=pants)
    elif step == 1:
        d.rectangle([ox + 4, ly, ox + 5, ly + 3], fill=pants); d.rectangle([ox + 9, ly - 1, ox + 10, ly + 2], fill=pants)
    else:
        d.rectangle([ox + 5, ly - 1, ox + 6, ly + 2], fill=pants); d.rectangle([ox + 10, ly, ox + 11, ly + 3], fill=pants)
    # 鞋
    d.point((ox + 5, ly + 3), fill=outline); d.point((ox + 10, ly + 3), fill=outline)
    # 身体
    by = oy + 12 + bob
    d.rectangle([ox + 4, by, ox + 11, by + 6], fill=shirt)
    if facing == "down":
        d.rectangle([ox + 7, by, ox + 8, by + 6], fill=shirt2)   # 前襟
    elif facing == "up":
        d.rectangle([ox + 4, by, ox + 11, by + 6], fill=shirt)
    else:
        d.rectangle([ox + 5, by, ox + 6, by + 6], fill=shirt2)
    # 手臂
    ay = by + 1
    swing = 1 if step == 1 else (-1 if step == 2 else 0)
    d.rectangle([ox + 3, ay + swing, ox + 3, ay + 4 + swing], fill=skin if facing != "up" else shirt)
    d.rectangle([ox + 12, ay - swing, ox + 12, ay + 4 - swing], fill=skin if facing != "up" else shirt)
    # 配饰：围裙 / 领带
    if c.get("extra") == "apron": d.rectangle([ox + 6, by + 2, ox + 9, by + 6], fill=rgb(c["shirt2"]))
    if c.get("extra") == "catears" and facing != "up": d.rectangle([ox + 7, by + 1, ox + 8, by + 4], fill=rgb("#1f2a44"))  # 领带
    if c.get("extra") == "fin" and facing == "up":  # 鲸尾鳍
        d.polygon([(ox + 7, by + 7), (ox + 4, by + 10), (ox + 10, by + 10)], fill=rgb("#7cc4ff"))
        d.polygon([(ox + 7, by + 8), (ox + 5, by + 10), (ox + 9, by + 10)], fill=rgb("#ffffff"))
    # 头
    hy = oy + 4 + bob
    d.rectangle([ox + 4, hy, ox + 11, hy + 7], fill=skin)
    # 头发
    d.rectangle([ox + 4, hy - 1, ox + 11, hy + 2], fill=hair)
    d.rectangle([ox + 3, hy, ox + 3, hy + 4], fill=hair); d.rectangle([ox + 12, hy, ox + 12, hy + 4], fill=hair)
    d.point((ox + 6, hy), fill=hair2); d.point((ox + 9, hy + 1), fill=hair2)
    if facing == "up":
        d.rectangle([ox + 4, hy, ox + 11, hy + 6], fill=hair)
        d.rectangle([ox + 5, hy + 1, ox + 6, hy + 5], fill=hair2)
    elif facing == "left":
        d.rectangle([ox + 8, hy, ox + 11, hy + 5], fill=hair)
    # 鲸仔：发尾白条纹 + 蓝白发卡
    if c["extra"] == "fin":
        d.point((ox + 10, hy + 2), fill=rgb("#ffffff")); d.point((ox + 5, hy + 2), fill=rgb("#ffffff"))
    # 眼睛
    if facing == "down":
        d.point((ox + 6, hy + 4), fill=eye); d.point((ox + 9, hy + 4), fill=eye)
        d.point((ox + 6, hy + 6), fill=rgb("#d98c7a")); d.point((ox + 9, hy + 6), fill=rgb("#d98c7a"))  # 腮红
    elif facing == "left":
        d.point((ox + 5, hy + 4), fill=eye)
        d.point((ox + 5, hy + 6), fill=rgb("#d98c7a"))
    # 头饰
    ex = c.get("extra")
    if ex == "catears":
        for x in (4, 10):
            d.polygon([(ox + x, hy - 1), (ox + x + 1, hy - 4), (ox + x + 2, hy - 1)], fill=rgb("#f4f4f4"))
            d.point((ox + x + 1, hy - 2), fill=rgb("#f9b4c3"))
        d.point((ox + 10, hy), fill=rgb("#3b82f6"))  # 蓝发卡
    elif ex == "chefhat":
        d.rectangle([ox + 4, hy - 4, ox + 11, hy - 1], fill=rgb("#ffffff")); d.rectangle([ox + 5, hy - 5, ox + 10, hy - 4], fill=rgb("#ffffff"))
    elif ex == "hat":
        d.rectangle([ox + 3, hy - 1, ox + 12, hy], fill=rgb("#d4a017")); d.rectangle([ox + 5, hy - 3, ox + 10, hy - 1], fill=rgb("#e6b422"))
    elif ex == "fin" and facing != "up":
        # 鲸鱼娘：头顶小背鳍
        d.polygon([(ox + 7, hy - 1), (ox + 8, hy - 4), (ox + 9, hy - 1)], fill=rgb("#7cc4ff"))
    # 描边（简单：身体与头的外侧一圈暗色点）
    for (x, y) in [(ox + 3, hy - 1), (ox + 12, hy - 1), (ox + 3, hy + 7), (ox + 12, hy + 7)]:
        d.point((x, y), fill=outline)

def build_char(key: str, c: dict):
    sheet = Image.new("RGBA", (FW * 4, FH * 4), (0, 0, 0, 0))
    for row, facing in enumerate(["down", "left", "right", "up"]):
        for col, step in enumerate([0, 1, 0, 2]):
            frame = Image.new("RGBA", (FW, FH), (0, 0, 0, 0))
            src = "left" if facing == "right" else facing
            draw_char_frame(frame, 0, 0, c, src, step)
            if facing == "right": frame = frame.transpose(Image.FLIP_LEFT_RIGHT)
            sheet.paste(frame, (col * FW, row * FH))
    sheet.save(OUT / f"char_{key}.png")

# ───────────────────────────── 物品 ─────────────────────────────

def new_obj(w_tiles, h_tiles):
    img = Image.new("RGBA", (w_tiles * T, h_tiles * T), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)

def box(d, x0, y0, x1, y1, fill, outline="#2b2230"):
    d.rectangle([x0, y0, x1, y1], fill=rgb(fill), outline=rgb(outline))

def obj_bed(vertical=True):
    img, d = new_obj(1, 2) if vertical else new_obj(2, 1)
    W, H = img.size
    box(d, 1, 1, W - 2, H - 2, "#8a5a3c")
    if vertical:
        box(d, 2, 2, W - 3, 6, "#f4f1ea")             # 枕头
        box(d, 2, 7, W - 3, H - 4, "#7fb3e6")         # 被子
        d.line([3, 10, W - 4, 10], fill=rgb("#a9cdf0")); d.line([3, 14, W - 4, 14], fill=rgb("#a9cdf0"))
    else:
        box(d, 2, 2, 6, H - 3, "#f4f1ea")
        box(d, 7, 2, W - 4, H - 3, "#7fb3e6")
        d.line([10, 3, 10, H - 4], fill=rgb("#a9cdf0")); d.line([16, 3, 16, H - 4], fill=rgb("#a9cdf0"))
    return img

def obj_bath():
    img, d = new_obj(1, 2); W, H = img.size
    box(d, 1, 1, W - 2, H - 2, "#eef2f5")
    box(d, 3, 3, W - 4, H - 4, "#9fd3f5", outline="#c9d6df")
    d.line([4, 5, 7, 5], fill=rgb("#dff3ff"))
    box(d, 6, 1, 9, 2, "#9aa5ad")  # 龙头
    return img

def obj_fridge():
    img, d = new_obj(1, 1)
    box(d, 2, 0, 13, 15, "#e9eef2")
    d.line([3, 6, 12, 6], fill=rgb("#b8c2cc"))
    d.rectangle([11, 2, 11, 4], fill=rgb("#8a949c")); d.rectangle([11, 8, 11, 12], fill=rgb("#8a949c"))
    return img

def obj_desk(with_monitor=False, live=False):
    img, d = new_obj(1, 1)
    box(d, 1, 6, 14, 12, "#b07a4a")
    d.rectangle([2, 13, 3, 15], fill=rgb("#8a5a3c")); d.rectangle([12, 13, 13, 15], fill=rgb("#8a5a3c"))
    if with_monitor:
        box(d, 4, 1, 11, 6, "#2b2f3a"); d.rectangle([5, 2, 10, 5], fill=rgb("#4ea8ff"))
        if live:
            d.rectangle([5, 2, 10, 5], fill=rgb("#ff7aa2")); d.point((9, 3), fill=rgb("#ff2d55"))
            d.rectangle([12, 2, 14, 4], fill=rgb("#2b2f3a")); d.point((13, 3), fill=rgb("#ff2d55"))  # 摄像头红灯
    else:
        d.rectangle([3, 4, 7, 6], fill=rgb("#f4f1ea")); d.line([4, 5, 6, 5], fill=rgb("#8a8a8a"))  # 纸
    return img

def obj_desk_long():
    img, d = new_obj(1, 2); W, H = img.size
    box(d, 1, 2, W - 2, H - 3, "#b07a4a")
    d.rectangle([3, 5, 7, 9], fill=rgb("#f4f1ea")); d.rectangle([3, 18, 9, 22], fill=rgb("#4ea8ff"))
    return img

def obj_book():
    img, d = new_obj(1, 1)
    box(d, 1, 0, 14, 15, "#7a4e2d")
    for y in (2, 7, 12):
        d.rectangle([2, y, 13, y + 3], fill=rgb("#5a3a22"))
        for i, c in enumerate(["#e74c3c", "#3498db", "#f1c40f", "#2ecc71", "#9b59b6", "#e67e22"]):
            d.rectangle([2 + i * 2, y, 2 + i * 2, y + 3], fill=rgb(c))
    return img

def obj_phone():
    img, d = new_obj(1, 1)
    box(d, 1, 7, 14, 12, "#b07a4a")
    d.rectangle([2, 13, 3, 15], fill=rgb("#8a5a3c")); d.rectangle([12, 13, 13, 15], fill=rgb("#8a5a3c"))
    box(d, 6, 2, 9, 8, "#2b2f3a"); d.rectangle([7, 3, 8, 6], fill=rgb("#7cc4ff")); d.point((7, 7), fill=rgb("#aaa"))
    return img

def obj_table():
    img, d = new_obj(2, 1); W, H = img.size
    box(d, 1, 4, W - 2, 11, "#c48a52")
    d.rectangle([2, 12, 3, 15], fill=rgb("#8a5a3c")); d.rectangle([W - 4, 12, W - 3, 15], fill=rgb("#8a5a3c"))
    for cx in (7, 23):
        d.ellipse([cx - 3, 5, cx + 3, 10], fill=rgb("#f4f1ea"), outline=rgb("#c9c2b5")); d.point((cx, 7), fill=rgb("#e67e22"))
    return img

def obj_bench():
    img, d = new_obj(2, 1); W, H = img.size
    box(d, 1, 7, W - 2, 11, "#a86f3e")
    box(d, 1, 3, W - 2, 6, "#b57a46")
    for x in (2, W - 3): d.rectangle([x, 12, x, 15], fill=rgb("#5a3a22"))
    return img

def obj_fishing_spot():
    img, d = new_obj(1, 1)
    tile_water(d, 0, 0, 1)
    d.ellipse([3, 6, 12, 11], outline=rgb("#8ec1ea"))
    d.rectangle([7, 7, 8, 8], fill=rgb("#ff2d55")); d.point((7, 6), fill=rgb("#ffffff"))
    box(d, 12, 1, 14, 6, "#b07a4a"); d.point((13, 0), fill=rgb("#ffd166"))  # 小木牌
    return img

def obj_counter():
    img, d = new_obj(1, 1)
    box(d, 0, 6, 15, 13, "#b07a4a"); d.rectangle([1, 14, 14, 15], fill=rgb("#8a5a3c"))
    box(d, 9, 2, 13, 6, "#2b2f3a"); d.rectangle([10, 3, 12, 4], fill=rgb("#7ee787"))  # 收银机
    d.rectangle([2, 3, 6, 6], fill=rgb("#f1c40f")); d.rectangle([3, 2, 5, 2], fill=rgb("#e67e22"))  # 货篓
    return img

def obj_sofa():
    img, d = new_obj(2, 1); W, H = img.size
    box(d, 1, 5, W - 2, 13, "#b23a48"); box(d, 1, 2, W - 2, 6, "#8e2e3a")
    d.line([W // 2, 6, W // 2, 12], fill=rgb("#8e2e3a"))
    return img

def obj_stove():
    img, d = new_obj(1, 1)
    box(d, 1, 3, 14, 15, "#cfd6dc"); d.rectangle([3, 5, 6, 8], fill=rgb("#2b2f3a")); d.rectangle([9, 5, 12, 8], fill=rgb("#2b2f3a"))
    d.point((4, 6), fill=rgb("#ff7a00")); d.point((10, 6), fill=rgb("#ff7a00")); d.rectangle([3, 11, 12, 13], fill=rgb("#8a949c"))
    return img

def obj_sink():
    img, d = new_obj(1, 1)
    box(d, 1, 5, 14, 14, "#eef2f5"); box(d, 3, 7, 12, 11, "#9fd3f5", outline="#c9d6df"); d.rectangle([7, 2, 8, 6], fill=rgb("#9aa5ad"))
    return img

def obj_toilet():
    img, d = new_obj(1, 1)
    box(d, 4, 1, 11, 6, "#eef2f5"); d.ellipse([3, 7, 12, 14], fill=rgb("#eef2f5"), outline=rgb("#2b2230")); d.ellipse([5, 9, 10, 12], fill=rgb("#9fd3f5"))
    return img

def obj_well():
    img, d = new_obj(1, 1)
    d.ellipse([2, 8, 13, 15], fill=rgb("#8a8a8a"), outline=rgb("#2b2230")); d.ellipse([4, 10, 11, 13], fill=rgb("#3d7fc4"))
    d.rectangle([3, 2, 3, 9], fill=rgb("#8a5a3c")); d.rectangle([12, 2, 12, 9], fill=rgb("#8a5a3c")); d.rectangle([2, 1, 13, 2], fill=rgb("#a86f3e"))
    return img

def obj_tree():
    img, d = new_obj(1, 1)
    d.rectangle([7, 10, 8, 15], fill=rgb("#7a4e2d")); d.ellipse([2, 1, 13, 11], fill=rgb("#3f8544"), outline=rgb("#2d6b33")); d.point((5, 4), fill=rgb("#6dbd66"))
    return img

OBJECTS = {
    "bed": lambda: obj_bed(True), "bed_21": lambda: obj_bed(False), "bath": obj_bath, "fridge": obj_fridge,
    "desk": lambda: obj_desk(False), "stream_desk": lambda: obj_desk(True, True), "desk_12": obj_desk_long,
    "book": obj_book, "phone": obj_phone, "restaurant_table": obj_table, "bench": obj_bench,
    "fishing_spot": obj_fishing_spot, "shop_counter": obj_counter, "sofa": obj_sofa, "cook": obj_stove,
    "sink": obj_sink, "toilet": obj_toilet, "well": obj_well, "tree": obj_tree,
}

def main():
    build_tiles()
    for k, c in CHARS.items(): build_char(k, c)
    for k, fn in OBJECTS.items(): fn().save(OUT / f"obj_{k}.png")
    manifest = {"tiles": "tiles.png", "chars": sorted(CHARS), "objects": sorted(OBJECTS), "license": "CC0-1.0（本仓库自制，tools/gen_assets.py 生成）"}
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", len(list(OUT.iterdir())), "files to", OUT)

if __name__ == "__main__":
    main()
