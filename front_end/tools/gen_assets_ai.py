#!/usr/bin/env python3
"""
美术管线 v1.0（W8）：用 OpenAI gpt-image-2 的 images.edit 重绘底图 / 物品 / 角色。密钥 ~/.env 的 OPENAI_API_KEY（仅此用途）。

  tools/.venv/bin/python tools/gen_assets_ai.py backdrops --regions home_1f_interior,home_1f_exterior [--quality high] [--attempts 2] [--dry-run]
  tools/.venv/bin/python tools/gen_assets_ai.py objects   --items bed,fridge [--quality high]
  tools/.venv/bin/python tools/gen_assets_ai.py chars     --keys whale,achan [--attempts 2] [--reslice]   # 角色四向表（4 列 × 5 行，32×48/帧）
  tools/.venv/bin/python tools/gen_assets_ai.py manifest

输入：data/assets/flats/<region>.png(+.json)（tools/flat_export.mjs 导出），风格参考 ref/jingzai_action_sheet_q.png + ref/gpt-image-probe/house.png。
输出：public/assets/gen-ai/{backdrops,objects}/*.png（32 px/格，≤ 64 色），data/assets/gen-ai-raw/ 保存原始 1024 级输出与 QA 叠图，
      data/assets/gen.jsonl 每张一行（提示词、模型、尺寸、质量、attempt、usage、估算费用、QA 分数）。gpt-image 接口没有 seed 参数，记 attempt 与 response.created。
"""
from __future__ import annotations
import argparse, base64, io, json, os, re, sys, time
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
FLATS = ROOT / "data/assets/flats"
RAW = ROOT / "data/assets/gen-ai-raw"
OUT = ROOT / "public/assets/gen-ai"
LOG = ROOT / "data/assets/gen.jsonl"
REF_STYLE = ROOT / "ref/jingzai_design_sheet_v2.png"   # 11-07 起用新人设图定画风（配色同一套）
REF_ROOM = ROOT / "ref/gpt-image-probe/house.png"
MODEL = "gpt-image-2"
TILE_OUT = 96            # 输出 px/格 = 显示尺寸（主播 11-07：房子 / 物品也不必像素风 → 高清原画、不量化、线性过滤）
TILE_SHEET = 48          # 地砖表 px/格（地面不需要太细，省显存；前端 ×2 线性）
MAX_COLORS = 64
# 估算单价（美元 / 张，按 W8 交接「high 约 0.2–0.3」取中值；若响应带 usage 则另记 token）——**假设**
PRICE = {"low": 0.03, "medium": 0.08, "high": 0.25, "xhigh": 0.4, "max": 0.6, "auto": 0.25}

STYLE = ("Art style must match the attached character reference sheet: soft pastel colors, clean cel-shaded anime chibi game look, "
         "gentle outlines, consistent light from the top-left with soft shadows, no text, no watermark, no characters.")
CAMERA = "Camera: straight top-down 3/4 view exactly like the attached finished room example (the third image), same projection and shadow direction."
CAMERA_BACKDROP = "Camera: straight top-down 3/4 view (walls show a thin front face toward the bottom), light from the top-left."

REGIONS: dict[str, str] = {
    "home_1f_interior": "the ground floor of a shared house: a whale-girl streamer's bedroom (left top), a living room (right, tall), and a kitchen with a tiled floor (left bottom); wooden plank floors, stone walls, inner doorways, a stairway tile at the living room's bottom-right, a front door at the top",
    "home_1f_exterior": "a two-story shared house seen from outside in town view: a blue-gray tiled roof covering the whole footprint, chimney, eaves and outer stone walls, a front door on the top side, grass and a street around it",
    "home_2f_exterior": "a small single-story annex house (it stands for the second floor of the shared house, drawn separately) seen from outside: the same cornflower-blue tiled roof and cream walls as the main house, a dormer window, a wooden door centered on the front wall, grass around it",
    "home_2f_interior": "the second floor of the shared house: a single bedroom belonging to a quiet programmer (cat-eared boy), wooden floor, stone walls, a stairway landing tile at the left",
    "classroom_1f_interior": "a university classroom building interior: one long room with a wooden floor, stone walls, a door on the bottom wall",
    "classroom_1f_exterior": "a small university classroom building seen from outside: blue tiled roof, pale stone outer walls, entrance door on the bottom side, campus pavement around it",
    "library_1f_interior": "a university library interior: one long reading hall with wooden floor and stone walls, a door on the bottom wall",
    "library_1f_exterior": "a small university library building seen from outside: blue tiled roof with a skylight, pale stone outer walls, entrance door on the bottom side, campus pavement around it",
    "music_room_1f_interior": "a university music building interior: one practice hall with wooden floor and stone walls, a door on the bottom wall",
    "music_room_1f_exterior": "a small university music building seen from outside: blue tiled roof, pale stone outer walls, a round window, entrance door on the bottom side, campus pavement around it",
    # W8 任务 4：其余区域（门的朝向按 8091 的 edges：渔夫屋南门，其余北 / 西门——外观一律把门画在正面墙，入口错位已报 B）
    "fisher_house_1f_interior": "an old fisherman's cottage interior: one bedroom (left, larger) and a small kitchen with a tiled floor (right), wooden plank floor, stone walls, a door on the bottom wall",
    "fisher_house_1f_exterior": "an old fisherman's small cottage by the river seen from outside: weathered blue-gray tiled roof, pale stone outer walls, a wooden front door and a hanging lantern on the bottom side, a lane and grass around it",
    "restaurant_1f_interior": "a small-town restaurant interior: a dining hall with a red carpet floor (left, large) and a narrow kitchen with a tiled floor (right), stone walls, an entrance door on the left wall",
    "restaurant_1f_exterior": "a small-town restaurant seen from outside: blue-gray tiled roof, warm cream outer walls, a striped awning and a wooden door on the bottom side, a blank signboard, a stone plaza to the left and grass around",
    "grocery_1f_interior": "a grocery store interior: one open shop floor with wooden planks, stone walls, a door on the top wall",
    "grocery_1f_exterior": "a small grocery store seen from outside: blue-gray tiled roof, cream outer walls, a striped awning, a wooden door and a crate of vegetables on the bottom side, a lane and grass around",
    "xiaoqian_house_1f_interior": "a university girl's small house: a bedroom (left) and a tiny kitchen with a tiled floor (right), wooden floor, stone walls, a door on the top wall",
    "xiaoqian_house_1f_exterior": "a small cozy cottage seen from outside: blue-gray tiled roof, cream outer walls, a wooden door and flower boxes on the bottom side, a lane and grass around",
    "owners_house_1f_interior": "a house shared by two shopkeepers: the restaurant owner's bedroom (top, large), a kitchen with a tiled floor (middle) and the grocer's small bedroom (bottom), wooden floors, stone walls, a door on the top wall",
    "owners_house_1f_exterior": "a two-family town house seen from outside: blue-gray tiled roof, cream outer walls, a wooden door and windows on the bottom side, a lane and grass around",
    "square_1f_interior": "a town square: light stone paving with a subtle flagstone pattern and a grass border; keep it empty (benches and the fountain are placed later as separate sprites)",
    "park_1f_interior": "a small town park: lush grass with flower patches and a few worn dirt paths; keep it empty (trees and benches are placed later as separate sprites)",
    "dock_1f_interior": "a wooden pier on a river bank: weathered planks and mooring posts, the river water on the right side; keep it empty (the boat and the fish stall are placed later as separate sprites)",
}
OUTDOOR = {"square", "park", "dock"}   # 室外地面底图：没有屋顶 / 室内之分，常显，物品另叠
# 外观屋顶 / 墙配色（11-07 主播：全镇一色不好看）。版式里屋顶一律画蓝灰，提示词里指定实际颜色
ROOF_COLORS = {
    "home": "cornflower-blue glazed tiles, warm cream plaster walls with white window frames",
    "classroom": "slate-gray tiles, pale sandstone walls with arched windows",
    "library": "slate-gray tiles with a glass skylight, pale sandstone walls",
    "music_room": "slate-gray tiles, pale sandstone walls with a round rose window",
    "fisher_house": "weathered moss-green wooden shingles, dark timber and whitewashed plank walls",
    "restaurant": "terracotta-red clay tiles, warm ochre walls with a red-and-white striped awning",
    "grocery": "forest-green metal roof, cream walls with a green-and-white striped awning and a vegetable crate by the door",
    "xiaoqian_house": "salmon-pink tiles, white walls with pastel flower boxes",
    "owners_house": "brown wooden shingles, beige stucco walls with two front windows",
}

# 角色：key → (显示名, 形象描述, 参考图列表)。NPC 没有立绘，用两张主角动作表定画风（2 头身 Q 版、柔和配色）
REF_WHALE = [ROOT / "ref/jingzai_design_sheet_v2.png"]   # 11-07 新人设：不再是鲸鱼娘（旧 action_sheet / fullbody 不再喂模型，会把鱼鳍耳带进去）
REF_ACHAN = [ROOT / "ref/achan_design_sheet_v2.png"]     # 11-07 新人设：没有猫耳 / 猫尾
REF_NPC = [ROOT / "ref/jingzai_design_sheet_v2.png", ROOT / "ref/achan_design_sheet_v2.png"]
CHARS: dict[str, tuple[str, str, list]] = {
    "whale": ("鲸仔", "Jingzai, a 21-year-old university music student (a normal human girl, NO animal ears, NO fins, NO tail): very long wavy hair with a navy-to-light-blue gradient, a fluffy antenna strand on top, a blue ribbon bow on the left side of her head and two small white X hair clips on the right, big blue eyes, a white hooded cardigan with a tiny blue whale print on the white T-shirt underneath, a navy pleated skirt with a belt, blue headphones hanging around her neck, white slouch socks and blue-and-white sneakers; use the Q-version chibi on the reference sheet as the model", REF_WHALE),
    "achan": ("阿蝉", "Achan, a calm young man who works as a stream director (a normal human, NO cat ears, NO tail): fluffy short white hair with two small dark hair clips on the right, gray-blue eyes, a white shirt with a black tie under an open denim-blue short-sleeve shirt, a black lanyard with a white badge, a black wristband, black trousers, blue-and-white sneakers; use the chibi on the reference sheet as the model", REF_ACHAN),
    "cook": ("餐厅老板", "a cheerful middle-aged male chef: short brown hair, warm brown eyes, white chef jacket with a red neckerchief, dark trousers, a white chef hat", REF_NPC),
    "grocer": ("杂货店老板（女）", "a warm, friendly middle-aged woman who runs the grocery store: chestnut-brown hair tied in a low bun with a cream headscarf, gentle brown eyes, a beige blouse with rolled sleeves under a green apron with a front pocket, a long brown skirt, flat shoes", REF_NPC),   # 主播 11-07：杂货铺老板是女的
    "fisher": ("老渔夫", "an old fisherman: short gray hair, a weathered kind face, a yellow raincoat, blue trousers, a yellow bucket hat, a small pipe", REF_NPC),
    "regular": ("千小满（小千）", "Xiaoqian, a lively university girl and Jingzai's best friend: shoulder-length auburn hair with a side braid, warm brown eyes, a red-brown cardigan over a white blouse, a dark pleated skirt, loafers", REF_NPC),
    "villager": ("村民", "a generic young townsperson: short purple hair, a lavender hoodie with white drawstrings, dark pants, sneakers", REF_NPC),
}
TALL_OBJECTS = {"tree", "fridge", "shelf", "lamp"}   # 1×1 footprint 但要向上长出格子的，用竖画布
CHAR_COLS, CHAR_ROWS = 4, 5
CHAR_FRAME_OUT = (96, 144)  # 输出帧 = 显示尺寸（主播 11-07：角色不必像素风，直接用原图 → 高清帧、不量化、线性过滤）
CHAR_TEMPLATE = (1024, 1536)
PIX_DIR = ROOT / "public/assets/gen"

OBJECTS: dict[str, tuple[int, int, str]] = {   # type: (w_tiles, h_tiles, description)
    "bed": (1, 2, "a single bed with a light blue quilt and a white pillow, head at the top"),
    "pc": (1, 1, "a small wooden desk with a desktop computer and monitor showing a soft blue screen, a streaming microphone beside it"),
    "fridge": (1, 1, "a white two-door refrigerator with a few cute magnets"),
    "stove": (1, 1, "a compact kitchen stove with two burners and an oven door"),
    "restaurant_table": (2, 1, "a wooden dining table for two with two plates and chairs"),
    "sofa_tv": (2, 1, "a red two-seat sofa facing a small TV on a low stand"),
    "pc_music": (1, 1, "a desk with a music-production computer, MIDI keyboard and headphones"),
    "piano": (1, 1, "an upright piano with its lid open"),
    "reading_desk": (1, 1, "a library reading desk with a green lamp and a stack of books"),
    "classroom_desk": (1, 1, "a school desk with a chair and a notebook"),
    "bar": (2, 1, "a restaurant bar counter with stools and a few bottles"),
    "shop_counter": (1, 1, "a grocery shop counter with a cash register and a basket of apples"),
    "fishing_spot": (1, 1, "a fishing spot marker: a wooden post with a fishing rod leaning on it and a small bucket, on water",),
    "fish_stall": (1, 1, "a small fish market stall with a red-and-white awning and fish on ice"),
    "bench": (2, 1, "a wooden park bench"),
    "notice_board": (1, 1, "a wooden community notice board with pinned papers"),
    "door_closed": (1, 1, "a closed wooden house door with a small brass handle, seen from above"),
    "stairs": (1, 1, "a short wooden staircase going up, seen from above"),
    "tree": (1, 1, "a leafy green tree, clearly taller than wide: a big round canopy above a short brown trunk whose base covers one floor tile"),
    "fountain": (2, 2, "a round stone fountain with a two-tier basin and blue water, footprint 2 by 2 tiles"),
    "lamp": (1, 1, "an old-fashioned black iron street lamp post with a warm glowing glass lantern on top, clearly taller than wide, the whole lamp fully inside the picture with empty margin above the lantern"),
    "desk_long": (1, 2, "a long wooden desk seen from above with a laptop, a desk lamp and a stack of books, a chair tucked in at the bottom end; footprint 1 tile wide by 2 tiles tall"),
    "shelf": (1, 1, "a wooden bookshelf full of colorful books"),
}

def env_key() -> str:
    k = os.environ.get("OPENAI_API_KEY")
    if not k:
        for line in (Path.home() / ".env").read_text().splitlines():
            if line.startswith("OPENAI_API_KEY="): k = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not k: sys.exit("OPENAI_API_KEY not found")
    return k

def client():
    from openai import OpenAI
    return OpenAI(api_key=env_key())

def log(row: dict):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f: f.write(json.dumps(row, ensure_ascii=False) + "\n")

def pick_size(w: int, h: int) -> str:
    r = w / h
    return "1536x1024" if r > 1.25 else "1024x1536" if r < 0.8 else "1024x1024"

def letterbox(img: Image.Image, size: str, fill=(127, 184, 122, 255)) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """把版式图按比例放进目标画布，四周补草地色；返回 (画布, 版式在画布里的 box)"""
    W, H = map(int, size.split("x"))
    s = min(W / img.width, H / img.height)
    nw, nh = int(img.width * s), int(img.height * s)
    canvas = Image.new("RGBA", (W, H), fill)
    im = img.convert("RGBA").resize((nw, nh), Image.NEAREST)
    ox, oy = (W - nw) // 2, (H - nh) // 2
    canvas.paste(im, (ox, oy))
    return canvas, (ox, oy, ox + nw, oy + nh)

def edges_mask(img: Image.Image) -> np.ndarray:
    g = np.asarray(img.convert("L"), dtype=np.float32)
    gx = np.abs(np.diff(g, axis=1, prepend=g[:, :1])); gy = np.abs(np.diff(g, axis=0, prepend=g[:1, :]))
    return (gx + gy) > 24

WALL_COLORS = [(0x7a, 0x6a, 0x63), (0x8a, 0x7a, 0x72), (0x9a, 0x6a, 0x3e)]   # 墙 / 外墙 / 门（FlatApp 的 COLORS；楼梯口颜色接近地板网格线，不计）

def wall_mask(flat: Image.Image) -> np.ndarray:
    a = np.asarray(flat.convert("RGB"), dtype=np.int16)
    m = np.zeros(a.shape[:2], dtype=bool)
    for c in WALL_COLORS:
        m |= (np.abs(a - np.array(c, dtype=np.int16)).sum(axis=2) < 10)
    return m

def wall_band(flat: Image.Image, meta: dict) -> np.ndarray:
    """版式图里「墙 / 门 / 楼梯口」区块的轮廓带（膨胀 ~1/4 格），作为「必须保住的线」；不含地板网格线与草地边界"""
    m = wall_mask(flat)
    e = m ^ np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(3))).astype(bool)   # 轮廓 = mask − erode(mask)
    k = max(1, meta["px"] // 4)
    return np.asarray(Image.fromarray((e * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(2 * k + 1))) > 0

def align_qa(flat: Image.Image, gen: Image.Image, meta: dict) -> tuple[float, Image.Image]:
    """对齐 QA：墙 / 门轮廓带（±1/4 格）里有生成图边缘（±1/3 格内）的比例（≥ 0.9 收）。返回 (score, 叠图：红 = 丢失的轮廓，绿 = 命中)"""
    gen_s = gen.convert("RGB").resize(flat.size, Image.BILINEAR)
    band = wall_band(flat, meta)
    ge = edges_mask(gen_s)
    k = max(1, meta["px"] // 3)   # 容忍 ±1/3 格：模型常把墙画厚一点，物品按格摆放不受影响
    ge_d = np.asarray(Image.fromarray((ge * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(2 * k + 1))) > 0
    hit = (band & ge_d).sum(); tot = band.sum()
    score = float(hit / tot) if tot else 1.0
    ov = gen_s.convert("RGBA"); arr = np.asarray(ov).copy()
    arr[band & ~ge_d] = [255, 60, 60, 255]; arr[band & ge_d] = [80, 220, 120, 255]
    return score, Image.fromarray(arr)

def chroma_key(img: Image.Image, key=(255, 0, 255), tol=90, soft=40) -> Image.Image:
    """品红抠像：到 key 色距离 < tol 透明，tol..tol+soft 之间渐变；再把残留的品红边缘去饱和一点"""
    a = np.asarray(img.convert("RGBA")).astype(np.int32)   # int16 会在平方和上溢出
    d = np.sqrt(((a[:, :, :3] - np.array(key, dtype=np.int32)) ** 2).sum(axis=2))
    alpha = np.clip((d - tol) / soft, 0, 1)
    out = a.copy(); out[:, :, 3] = (alpha * 255).astype(np.int32)
    # 边缘去品红：半透明像素的红蓝通道向绿通道靠一点
    fr = (alpha > 0) & (alpha < 1)
    out[fr, 0] = (out[fr, 0] * 0.6 + out[fr, 1] * 0.4).astype(np.int32); out[fr, 2] = (out[fr, 2] * 0.6 + out[fr, 1] * 0.4).astype(np.int32)
    return Image.fromarray(out.clip(0, 255).astype(np.uint8), "RGBA")

def quantize(img: Image.Image, colors=MAX_COLORS) -> Image.Image:
    if img.mode == "RGBA":
        q = img.quantize(colors=colors, method=Image.FASTOCTREE, dither=Image.NONE)
        return q.convert("RGBA")
    return img.convert("RGB").quantize(colors=colors, method=Image.MEDIANCUT, dither=Image.NONE).convert("RGB")

def call_edit(cli, images: list[Path], prompt: str, size: str, quality: str, transparent=False):
    files = [open(p, "rb") for p in images]
    try:
        kw = dict(model=MODEL, image=files, prompt=prompt, size=size, quality=quality, n=1, output_format="png")
        if transparent: kw["background"] = "transparent"
        t0 = time.time()
        res = cli.images.edit(**kw)
        dt = time.time() - t0
    finally:
        for f in files: f.close()
    d = res.data[0]
    img = Image.open(io.BytesIO(base64.b64decode(d.b64_json))) if getattr(d, "b64_json", None) else None
    if img is None and getattr(d, "url", None):
        import urllib.request
        img = Image.open(io.BytesIO(urllib.request.urlopen(d.url).read()))
    usage = getattr(res, "usage", None)
    usage = usage.model_dump() if usage is not None and hasattr(usage, "model_dump") else (dict(usage) if usage else None)
    return img, {"created": getattr(res, "created", None), "usage": usage, "latency_s": round(dt, 1)}

def do_backdrops(args):
    cli = None if args.dry_run else client()
    regions = args.regions.split(",") if args.regions else list(REGIONS)
    (OUT / "backdrops").mkdir(parents=True, exist_ok=True); RAW.mkdir(parents=True, exist_ok=True)
    for name in regions:
        name = name.strip()
        flat_p, meta_p = FLATS / f"{name}.png", FLATS / f"{name}.json"
        if not flat_p.exists(): print("skip (no flat):", name); continue
        meta = json.loads(meta_p.read_text()); flat = Image.open(flat_p).convert("RGBA")
        desc = REGIONS.get(name, name.replace("_", " "))
        view = "exterior" if name.endswith("exterior") else "interior"
        if name.split("_")[0] in OUTDOOR:
            prompt = (f"The first image is a flat-colored top-down layout of {desc}. Repaint it as finished 2D top-down game ground art, "
                      f"keeping every boundary between ground types (paving / grass / wood / water) exactly at the same position. "
                      f"Do not add any objects, furniture, trees, benches, boats or people; only ground textures and small details like flowers, pebbles, planks. "
                      + STYLE + " " + CAMERA_BACKDROP)
        else:
          prompt = (f"The first image is a flat-colored top-down layout of {desc}. Repaint it as finished 2D top-down game art, "
                  f"keeping every wall, door{'' if view == 'exterior' else ', doorway'} and room boundary exactly at the same position and size, "
                  f"and keeping the surrounding ground (grass / pavement) where it is. "
                  + (f"Draw the building exterior in the classic Pokemon-style 3/4 top-down RPG view: the blue-gray area of the layout is a pitched roof (ridge line, eaves, a chimney) — paint it as {ROOF_COLORS.get(name.rsplit('_1f', 1)[0], 'blue-gray tiles, cream walls')} — "
                     "and the lighter band along the bottom edge of the building is the FRONT WALL seen from the front, with windows and a wooden door centered on it; a soft shadow on the ground along the bottom and right edges of the building; "
                     "if the layout shows a small brown square it marks where the entrance tile is. Keep the building footprint exactly the same; do not show the interior. "
                     if view == "exterior" else "Do not add furniture; leave the floors empty so objects can be placed later. ")
                  + "The room layout must follow the first image exactly; do not copy or add rooms from any other image. "
                  + STYLE + " " + CAMERA_BACKDROP)
        size = pick_size(flat.width, flat.height)
        canvas, box = letterbox(flat, size)
        tmp = RAW / f"{name}_input.png"; canvas.save(tmp)
        best = None
        for attempt in range(1, args.attempts + 1):
            row = {"kind": "backdrop", "name": name, "model": MODEL, "size": size, "quality": args.quality, "attempt": attempt, "prompt": prompt,
                   "inputs": [str(tmp.relative_to(ROOT)), str(REF_STYLE.relative_to(ROOT))], "seed": None, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
            if args.dry_run: print(json.dumps(row, ensure_ascii=False)[:300]); break
            try:
                img, info = call_edit(cli, [tmp, REF_STYLE], prompt, size, args.quality)   # 不再附房间参考图：小房间会被模型照着参考图画成三间（home_2f 第一轮踩过）
            except Exception as e:
                row.update(error=str(e)[:400]); log(row); print("ERROR", name, e); break
            row.update(info); row["cost_usd_est"] = PRICE.get(args.quality, 0.25)
            img.save(RAW / f"{name}_raw_{attempt}.png")
            # 裁回版式区域，按 32 px/格重采样 + 量化
            crop = img.crop(box).convert("RGBA")
            target = (meta["w"] * TILE_OUT, meta["h"] * TILE_OUT)
            small = crop.resize(target, Image.LANCZOS)
            score, overlay = align_qa(flat, crop, meta)
            overlay.save(RAW / f"{name}_qa_{attempt}.png")
            row["qa_score"] = round(score, 3); row["qa_pass"] = score >= args.qa
            log(row); print(f"{name} attempt {attempt}: qa={score:.3f} {'PASS' if row['qa_pass'] else 'retry'} ({info['latency_s']}s)")
            if best is None or score > best[0]: best = (score, small)
            if row["qa_pass"]: break
        if best is not None:
            best[1].save(OUT / "backdrops" / f"{name}.png")   # 高清：不量化
            (OUT / "backdrops" / f"{name}.json").write_text(json.dumps({**meta, "tile_px": TILE_OUT, "qa_score": round(best[0], 3)}, ensure_ascii=False, indent=2))

def finish_object(img: Image.Image, key: str, w: int, h: int):
    """品红抠像 → 裁 alpha 包围盒 → **盖住** footprint（w×h 格 × 32 px）：按较大的比例缩放，宽最多溢出 25%、高最多到 2 倍（高物件向上长出格子，宝可梦式），
    画布 = max(footprint, 实际) 底边居中对齐 → 量化 → objects/<key>.png（前端按纹理实际尺寸 ×3 画、底边贴 footprint 底边）"""
    img = chroma_key(img.convert("RGBA"))
    bbox = img.getbbox()
    if bbox: img = img.crop(bbox)
    tw, th = w * TILE_OUT, h * TILE_OUT
    s = max(tw / img.width, th / img.height)
    s = min(s, tw * 1.25 / img.width, th * 2.0 / img.height)
    s = max(s, min(tw / img.width, th / img.height))   # 至少装进去
    nw, nh = max(1, round(img.width * s)), max(1, round(img.height * s))
    small = img.resize((nw, nh), Image.LANCZOS)
    cw, ch = max(tw, nw), max(th, nh)
    canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0)); canvas.paste(small, ((cw - nw) // 2, ch - nh), small)
    canvas.save(OUT / "objects" / f"{key}.png")   # 高清：不量化
    return {"bbox": bbox, "out": [cw, ch], "footprint": [tw, th]}

def do_rekey(_args):
    """对已有 raw 重新抠像 / 缩放 / 量化（不花钱）"""
    for raw in sorted(RAW.glob("obj_*_raw.png")):
        key = raw.stem[4:-4]
        if key not in OBJECTS: continue
        w, h, _ = OBJECTS[key]
        print(key, finish_object(Image.open(raw), key, w, h))

def do_objects(args):
    cli = None if args.dry_run else client()
    items = args.items.split(",") if args.items else list(OBJECTS)
    (OUT / "objects").mkdir(parents=True, exist_ok=True); RAW.mkdir(parents=True, exist_ok=True)
    for key in items:
        key = key.strip()
        if key not in OBJECTS: print("unknown object", key); continue
        w, h, desc = OBJECTS[key]
        prompt = (f"Draw {desc} as a single 2D game object sprite centered on a flat solid magenta (#FF00FF) background with no gradient, no floor and no shadow outside the object. "
                  f"Camera: top-down 3/4 view, the same projection as the furniture in the attached finished room image (second image): the top surface is visible and the front face is slightly visible below it, soft shadow under the object. "
                  f"The object should fill the canvas and have a footprint about {w} by {h} floor tiles ({'wider than tall' if w > h else 'taller than wide' if h > w else 'square'}). "
                  f"Art style must match the attached character reference sheet (first image): soft pastel colors, clean cel-shaded chibi game look, gentle outlines. No text, no watermark, no characters, nothing else in the image.")
        size = "1024x1536" if key in TALL_OBJECTS else "1024x1024" if w == h else ("1536x1024" if w > h else "1024x1536")
        row = {"kind": "object", "name": key, "model": MODEL, "size": size, "quality": args.quality, "attempt": 1, "prompt": prompt,
               "inputs": [str(REF_STYLE.relative_to(ROOT)), "ref/gpt-image-probe/house.png"], "seed": None, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
        if args.dry_run: print(json.dumps(row, ensure_ascii=False)[:300]); continue
        try:
            img, info = call_edit(cli, [REF_STYLE, REF_ROOM], prompt, size, args.quality)   # gpt-image-2 不支持 transparent，用品红抠像
        except Exception as e:
            row.update(error=str(e)[:400]); log(row); print("ERROR", key, e); continue
        row.update(info); row["cost_usd_est"] = PRICE.get(args.quality, 0.25)
        img = img.convert("RGBA"); img.save(RAW / f"obj_{key}_raw.png")
        bbox = finish_object(img, key, w, h)
        if key == "lamp": (OUT / "deco").mkdir(exist_ok=True); import shutil; shutil.copy(OUT / "objects" / "lamp.png", OUT / "deco" / "lamp.png")   # 路灯：4×4 装饰表里被格线截了头，单独出一张
        row["alpha_bbox"] = bbox; row["out_px"] = [w * TILE_OUT, h * TILE_OUT]
        log(row); print(f"{key}: ok ({info['latency_s']}s)")

# ── 角色四向表 ────────────────────────────────────────────────────────────────

def pixel_sheet_for(key: str) -> Image.Image:
    """姿态版式来源：现有像素表（鲸仔 / 阿蝉用 v1 文字版）"""
    p = PIX_DIR / f"char_{key}_v1.png"
    if not p.exists(): p = PIX_DIR / f"char_{key}.png"
    return Image.open(p).convert("RGBA")

def make_char_template(key: str) -> Image.Image:
    """1024×1536 品红画布，4 列 × 5 行格子（256×307），每格放大 ×9 的像素帧居中、脚底对齐；睡觉格用左向站姿转 90°（不画床）"""
    W, H = CHAR_TEMPLATE; cw, ch = W // CHAR_COLS, H // CHAR_ROWS
    sheet = pixel_sheet_for(key); fw, fh = sheet.width // CHAR_COLS, sheet.height // CHAR_ROWS
    canvas = Image.new("RGBA", (W, H), (255, 0, 255, 255))
    from PIL import ImageDraw
    d = ImageDraw.Draw(canvas)
    for i in range(1, CHAR_COLS): d.line([(i * cw, 0), (i * cw, H)], fill=(240, 0, 240, 255), width=3)
    for j in range(1, CHAR_ROWS): d.line([(0, j * ch), (W, j * ch)], fill=(240, 0, 240, 255), width=3)
    S = 9
    for r in range(CHAR_ROWS):
        for c in range(CHAR_COLS):
            fr = sheet.crop((c * fw, r * fh, (c + 1) * fw, (r + 1) * fh))
            if r == 4 and c == 1:   # 睡觉：左向站姿躺平
                fr = sheet.crop((0, 1 * fh, fw, 2 * fh)).rotate(90, expand=True)
            big = fr.resize((fr.width * S, fr.height * S), Image.NEAREST)
            x = c * cw + (cw - big.width) // 2
            y = r * ch + (ch - big.height) // 2 if (r == 4 and c == 1) else (r + 1) * ch - 36 - big.height
            canvas.alpha_composite(big, (x, y))
    return canvas

def char_prompt(key: str) -> str:
    _, desc, _ = CHARS[key]
    return (f"The first image is a sprite-sheet layout grid on a flat magenta background: 4 columns by 5 rows, each cell holds a rough pixel sketch that only defines the POSE, FACING and FEET POSITION. "
            f"Rows 1-4 are the character facing DOWN (toward the viewer), LEFT, RIGHT and UP (back view); within these rows the 4 columns are a walk cycle: standing, left step, standing, right step. "
            f"Row 5 is: sitting facing down, lying asleep on the side (no bed, no blanket), sitting facing left, sitting facing right. "
            f"Redraw every cell with the SAME character: {desc}. The other attached image is the character design sheet (ignore its text, layout and background; take only the character design and color palette, and follow it exactly), "
            f"as a 2-head-tall chibi game sprite, clean cel-shaded anime look with soft pastel colors and gentle outlines, seen from the game camera (top-down 3/4 view, the character slightly from above, light from the top-left). "
            f"Keep each figure fully inside its cell, same size in every cell, feet on the same baseline as the sketch, standing frames identical except for the legs. "
            f"Background must stay flat solid magenta (#FF00FF) everywhere outside the figures: no grid lines, no shadows, no text, no labels, no props.")

def _bands(mask_1d: np.ndarray, min_gap: int, min_len: int) -> list[tuple[int, int]]:
    """一维投影 → 非空区段列表；小于 min_gap 的空隙并进去，短于 min_len 的区段丢掉（闪光 / 碎屑）"""
    on = mask_1d > 0
    runs: list[list[int]] = []
    i = 0
    while i < len(on):
        if on[i]:
            j = i
            while j < len(on) and on[j]: j += 1
            if runs and i - runs[-1][1] < min_gap: runs[-1][1] = j
            else: runs.append([i, j])
            i = j
        else: i += 1
    return [(a, b) for a, b in runs if b - a >= min_len]

def segment_cells(keyed: Image.Image) -> list[list[Image.Image]] | None:
    """按 alpha 投影切 5 行 × 4 列：模型不一定严格落在版式格子里（脚常画到格线以下），用空隙切比固定网格稳；
    返回 rows[r][c] 的裁好图；行数 / 列数不对 → None（退回固定网格）"""
    a = np.asarray(keyed)[:, :, 3] > 32
    rows = _bands(a.sum(axis=1), min_gap=12, min_len=40)
    if len(rows) != CHAR_ROWS: return None
    out: list[list[Image.Image]] = []
    for (y0, y1) in rows:
        cols = _bands(a[y0:y1].sum(axis=0), min_gap=18, min_len=24)
        if len(cols) != CHAR_COLS: return None
        out.append([keyed.crop((x0, y0, x1, y1)).crop(keyed.crop((x0, y0, x1, y1)).getbbox()) for (x0, x1) in cols])
    return out

def finish_char(raw: Image.Image, key: str) -> dict:
    """品红抠像 → 按空隙切 5 行 × 4 列（退回固定网格）→ 统一比例（站姿帧最高者 44 px）→ 32×48/帧、脚底对齐；右向 = 左向镜像；量化 ≤ 64 色 → chars/<key>.png"""
    W, H = CHAR_TEMPLATE; cw, ch = W // CHAR_COLS, H // CHAR_ROWS
    raw = raw.convert("RGBA").resize((W, H), Image.LANCZOS) if raw.size != (W, H) else raw.convert("RGBA")
    keyed = chroma_key(raw, tol=90, soft=40)
    seg = segment_cells(keyed)
    cells: dict[tuple[int, int], Image.Image | None] = {}
    if seg is not None:
        for r in range(CHAR_ROWS):
            for c in range(CHAR_COLS): cells[(r, c)] = seg[r][c]
        mode, clipped = "bands", 0
    else:
        mode, clipped = "grid", 0
        for r in range(CHAR_ROWS):
            for c in range(CHAR_COLS):
                cell = keyed.crop((c * cw + 4, r * ch + 4, (c + 1) * cw - 4, (r + 1) * ch - 4))
                bb = cell.getbbox()
                if bb and (bb[0] <= 1 or bb[1] <= 1 or bb[2] >= cell.width - 1 or bb[3] >= cell.height - 1): clipped += 1
                cells[(r, c)] = cell.crop(bb) if bb else None
    stand = [im for (r, c), im in cells.items() if r < 4 and im is not None]
    fw, fh = CHAR_FRAME_OUT
    if not stand: return {"cells_ok": 0, "clipped": clipped, "mode": mode}
    s = min((fh - 12) / max(im.height for im in stand), (fw - 6) / max(im.width for im in stand))
    sheet = Image.new("RGBA", (fw * CHAR_COLS, fh * CHAR_ROWS), (0, 0, 0, 0))
    def put(im: Image.Image, r: int, c: int, scale: float, center_v=False):
        sm = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.LANCZOS)
        x = c * fw + (fw - sm.width) // 2
        y = r * fh + ((fh - sm.height) // 2 if center_v else fh - 2 - sm.height)
        sheet.alpha_composite(sm, (x, y))
    for (r, c), im in cells.items():
        if im is None: continue
        if r == 2: continue                       # 右向整行用左向镜像（左右一致，省一半不确定性）
        if r == 4 and c == 3: continue             # 坐右 = 坐左镜像
        if r == 4 and c == 1:                      # 睡觉：模型画的是横躺（头在左）→ 顺时针转 90° 竖躺（头在上）存表，竖床直接用、横床游戏里再转 -90°
            im = im.rotate(-90, expand=True)
            put(im, r, c, min((fw - 2) / im.width, (fh - 2) / im.height), center_v=True); continue
        put(im, r, c, s)
    left = sheet.crop((0, 1 * fh, fw * CHAR_COLS, 2 * fh)).transpose(Image.FLIP_LEFT_RIGHT)
    # 镜像后列顺序反了（站 走A 站 走B → 走B 站 走A 站），按列重排
    for c in range(CHAR_COLS):
        src = left.crop(((CHAR_COLS - 1 - c) * fw, 0, (CHAR_COLS - c) * fw, fh)); sheet.alpha_composite(src, (c * fw, 2 * fh))
    sheet.alpha_composite(sheet.crop((2 * fw, 4 * fh, 3 * fw, 5 * fh)).transpose(Image.FLIP_LEFT_RIGHT), (3 * fw, 4 * fh))
    (OUT / "chars").mkdir(parents=True, exist_ok=True)
    sheet.save(OUT / "chars" / f"{key}.png")   # 角色表不量化（高清原画）
    # 评审预览：放在绿底上
    prev = sheet.copy()
    bg = Image.new("RGBA", prev.size, (90, 140, 90, 255)); bg.alpha_composite(prev); bg.save(RAW / f"char_{key}_sheet.png")
    ok = sum(1 for (r, c), im in cells.items() if im is not None and r != 2 and not (r == 4 and c == 3))
    return {"cells_ok": ok, "cells_needed": 15, "clipped": clipped, "mode": mode, "scale": round(s, 4)}

def do_chars(args):
    cli = None if (args.dry_run or args.reslice) else client()
    keys = args.keys.split(",") if args.keys else list(CHARS)
    RAW.mkdir(parents=True, exist_ok=True)
    for key in keys:
        key = key.strip()
        if key not in CHARS: print("unknown char", key); continue
        tmpl = make_char_template(key); tmp = RAW / f"char_{key}_input.png"; tmpl.save(tmp)
        if args.reslice:
            raws = sorted(RAW.glob(f"char_{key}_raw_*.png"))
            if not raws: print("no raw for", key); continue
            print(key, "reslice", raws[-1].name, finish_char(Image.open(raws[-1]), key)); continue
        prompt = char_prompt(key); refs = CHARS[key][2]
        for attempt in range(1, args.attempts + 1):
            row = {"kind": "char", "name": key, "model": MODEL, "size": f"{CHAR_TEMPLATE[0]}x{CHAR_TEMPLATE[1]}", "quality": args.quality, "attempt": attempt, "prompt": prompt,
                   "inputs": [str(tmp.relative_to(ROOT))] + [str(p.relative_to(ROOT)) for p in refs], "seed": None, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
            if args.dry_run: print(json.dumps(row, ensure_ascii=False)[:400]); break
            try:
                img, info = call_edit(cli, [tmp] + refs, prompt, row["size"], args.quality)
            except Exception as e:
                row.update(error=str(e)[:400]); log(row); print("ERROR", key, e); break
            row.update(info); row["cost_usd_est"] = PRICE.get(args.quality, 0.25)
            img = img.convert("RGBA"); img.save(RAW / f"char_{key}_raw_{attempt}.png")
            res = finish_char(img, key); row.update(res)
            row["qa_pass"] = res.get("cells_ok", 0) >= 15 and res.get("mode") == "bands"
            log(row); print(f"{key} attempt {attempt}: {res} {'PASS' if row['qa_pass'] else 'retry'} ({info['latency_s']}s)")
            if row["qa_pass"]: break


# ── 地砖表 / 装饰物（11-07 主播：小镇整体不好看——地面是平涂像素、建筑都一个色、没有花草）──────────────

TILE_CELLS = [   # 4 × 4，和 TILE_INDEX 名字对齐；前端按格哈希在同类变体里挑
    ("grass_a", "short green lawn grass"), ("grass_b", "lawn grass, slightly different shade"), ("grass_flower", "lawn grass with a few tiny white and yellow wildflowers"), ("grass_dark", "darker, lusher grass"),
    ("road_a", "packed light-brown dirt road"), ("road_b", "dirt road with a few small pebbles and faint wheel ruts"), ("square", "light warm-gray stone plaza paving"), ("campus", "pale flagstone campus pavement"),
    ("water_a", "clear river water with soft light ripples"), ("water_b", "river water, ripples shifted (second animation frame)"), ("dock", "weathered wooden pier planks"), ("grass_park", "park grass with clover and a few daisies"),
    ("floor_wood", "warm wooden plank floor"), ("floor_tile", "cream ceramic kitchen tiles"), ("carpet", "deep red carpet with a subtle woven pattern"), ("grass_tall", "lawn grass with a few tufts of taller grass"),
]
DECO_CELLS = [   # 4 × 4，每格一个 1 格宽的小装饰（品红底），前端按规则撒在室外草地上
    ("bush", "a round green bush"), ("bush_flower", "a round bush with small pink flowers"), ("flowers_pink", "a low cluster of pink and white wildflowers"), ("flowers_yellow", "a low cluster of yellow wildflowers"),
    ("rock", "a small gray rock"), ("rock_moss", "a mossy gray rock"), ("lamp", "an old-fashioned iron street lamp post, tall"), ("fence", "a short wooden picket fence segment, horizontal"),
    ("signpost", "a wooden signpost with a blank board"), ("flowerbed", "a small square flowerbed with a stone border and mixed flowers"), ("stump", "a tree stump"), ("mailbox", "a small blue mailbox on a post"),
    ("barrel", "a wooden barrel"), ("crate", "a wooden crate"), ("pot_plant", "a potted plant in a terracotta pot"), ("pine", "a small young pine tree"),
]

def grid_prompt(kind: str) -> str:
    cells = TILE_CELLS if kind == "tiles" else DECO_CELLS
    items = "; ".join(f"{i + 1}: {d}" for i, (_, d) in enumerate(cells))
    if kind == "tiles":
        return ("Create a 4 by 4 grid of 16 seamless top-down 2D game ground tiles, thin magenta (#FF00FF) lines separating the cells. Each cell is ONE material filling the whole cell, "
                "with a flat uniform base color and only a few small sparse details so that the tile can repeat without visible seams; no objects, no text. "
                f"Cells left to right, top to bottom — {items}. "
                "Art style must match the attached reference: soft pastel colors, clean cel-shaded anime game look, light from the top-left. Camera: straight top-down.")
    return ("Create a 4 by 4 grid of 16 small 2D game decoration sprites on a flat solid magenta (#FF00FF) background, one object centered in each cell, each about one floor tile wide, "
            f"nothing else in the cells, no text, no shadows outside the objects. Cells left to right, top to bottom — {items}. "
            "Camera: top-down 3/4 view like the furniture in the attached finished room image (top surface visible, front face slightly visible below). "
            "Art style must match the attached character reference: soft pastel colors, clean cel-shaded anime chibi game look, gentle outlines.")

def finish_tiles(raw: Image.Image) -> dict:
    """1024² 4×4 → 每格去掉 14 px 边（品红格线）→ 32×32 LANCZOS → 一张 128×128 表（4 列）+ tiles.json 名字 → 索引"""
    raw = raw.convert("RGB").resize((1024, 1024), Image.LANCZOS)
    cs = 256; T = TILE_SHEET; sheet = Image.new("RGB", (T * 4, T * 4))
    cells: dict[str, Image.Image] = {}
    for i, (name, _) in enumerate(TILE_CELLS):
        r, c = divmod(i, 4)
        cells[name] = raw.crop((c * cs + 14, r * cs + 14, (c + 1) * cs - 14, (r + 1) * cs - 14)).resize((T, T), Image.LANCZOS)
    # 同类变体把平均色对齐到基准格（只留纹理差异），否则按格哈希混用会出现棋盘格；深草 / 公园草只比基准深 6%
    def match_mean(im: Image.Image, ref: Image.Image, scale=1.0) -> Image.Image:
        a = np.asarray(im, dtype=np.float32); b = np.asarray(ref, dtype=np.float32)
        out = a - a.mean(axis=(0, 1)) + b.mean(axis=(0, 1)) * scale
        return Image.fromarray(out.clip(0, 255).astype(np.uint8))
    for n in ("grass_b", "grass_tall", "grass_flower"): cells[n] = match_mean(cells[n], cells["grass_a"])
    for n in ("grass_dark", "grass_park"): cells[n] = match_mean(cells[n], cells["grass_a"], 0.94)
    cells["road_b"] = match_mean(cells["road_b"], cells["road_a"])
    cells["water_b"] = match_mean(cells["water_b"], cells["water_a"])
    for i, (name, _) in enumerate(TILE_CELLS):
        r, c = divmod(i, 4); sheet.paste(cells[name], (c * T, r * T))
    q = sheet.convert("RGBA")
    q.save(OUT / "tiles.png")
    meta = {"image": "tiles.png", "tile": T, "columns": 4, "index": {n: i for i, (n, _) in enumerate(TILE_CELLS)},
            "variants": {"grass": ["grass_a", "grass_b", "grass_a", "grass_tall"], "grass_flower": ["grass_flower"], "grass_dark": ["grass_dark"], "road": ["road_a", "road_b", "road_a"],
                         "square": ["square"], "campus": ["campus"], "dock": ["dock"], "grass_park": ["grass_park", "grass_dark"], "water": ["water_a", "water_b"],
                         "floor_wood": ["floor_wood"], "floor_tile": ["floor_tile"], "carpet": ["carpet"]}}
    (OUT / "tiles.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    # 评审：×4 放大的表
    big = q.resize((q.width * 2, q.height * 2), Image.LANCZOS); big.save(RAW / "tiles_sheet.png")
    return {"tiles": len(TILE_CELLS)}

def largest_component(im: Image.Image, thr=40) -> Image.Image:
    """只保留 alpha 最大的连通块（去掉格子里串进来的邻格碎屑 / 杂点）；4 邻域 BFS，按 1/4 分辨率做再放大"""
    a = np.asarray(im)[:, :, 3]
    small = (a[::4, ::4] > thr)
    h, w = small.shape
    seen = np.zeros_like(small, dtype=bool); best: list[tuple[int, int]] = []
    for sy in range(h):
        for sx in range(w):
            if not small[sy, sx] or seen[sy, sx]: continue
            comp = []; stack = [(sy, sx)]; seen[sy, sx] = True
            while stack:
                y, x = stack.pop(); comp.append((y, x))
                for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                    if 0 <= ny < h and 0 <= nx < w and small[ny, nx] and not seen[ny, nx]: seen[ny, nx] = True; stack.append((ny, nx))
            if len(comp) > len(best): best = comp
    if not best: return im
    keep = np.zeros_like(small);
    for y, x in best: keep[y, x] = True
    keep = np.asarray(Image.fromarray((keep * 255).astype(np.uint8)).resize((im.width, im.height), Image.NEAREST).filter(ImageFilter.MaxFilter(9))) > 0
    out = np.asarray(im).copy(); out[~keep, 3] = 0
    return Image.fromarray(out, "RGBA")

def finish_deco(raw: Image.Image) -> dict:
    """1024² 4×4 品红底 → 抠像 → 每格裁包围盒 → 宽装进 32、高 ≤ 48（灯柱 / 小松树可到 64）底边对齐 → deco/<name>.png"""
    raw = raw.convert("RGBA").resize((1024, 1024), Image.LANCZOS)
    keyed = chroma_key(raw); cs = 256; (OUT / "deco").mkdir(parents=True, exist_ok=True)
    ok = 0
    for i, (name, _) in enumerate(DECO_CELLS):
        r, c = divmod(i, 4)
        cell = largest_component(keyed.crop((c * cs + 12, r * cs + 12, (c + 1) * cs - 12, (r + 1) * cs - 12)))
        bb = cell.getbbox()
        if not bb: continue
        im = cell.crop(bb)
        maxh = TILE_OUT * 2 if name in ("lamp", "pine", "signpost") else TILE_OUT * 1.5
        sc = min(TILE_OUT / im.width, maxh / im.height)
        if name in ("fence",): sc = TILE_OUT / im.width
        sm = im.resize((max(1, round(im.width * sc)), max(1, round(im.height * sc))), Image.LANCZOS)
        canvas = Image.new("RGBA", (TILE_OUT, max(TILE_OUT, sm.height)), (0, 0, 0, 0)); canvas.paste(sm, ((TILE_OUT - sm.width) // 2, canvas.height - sm.height), sm)
        canvas.save(OUT / "deco" / f"{name}.png"); ok += 1
    return {"deco_ok": ok, "deco_needed": len(DECO_CELLS)}

def do_grid(args):
    """tiles / deco 两种 4×4 表，各一张 1024²；--reslice 从最新 raw 重切"""
    kind = args.cmd
    RAW.mkdir(parents=True, exist_ok=True)
    finish = finish_tiles if kind == "tiles" else finish_deco
    if args.reslice:
        raws = sorted(RAW.glob(f"{kind}_raw_*.png"))
        if raws: print(kind, "reslice", raws[-1].name, finish(Image.open(raws[-1])))
        return
    cli = None if args.dry_run else client()
    prompt = grid_prompt(kind)
    refs = [REF_STYLE] if kind == "tiles" else [REF_STYLE, REF_ROOM]
    for attempt in range(1, args.attempts + 1):
        row = {"kind": kind, "name": kind, "model": MODEL, "size": "1024x1024", "quality": args.quality, "attempt": attempt, "prompt": prompt,
               "inputs": [str(p.relative_to(ROOT)) for p in refs], "seed": None, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
        if args.dry_run: print(json.dumps(row, ensure_ascii=False)[:400]); return
        try:
            img, info = call_edit(cli, refs, prompt, "1024x1024", args.quality)
        except Exception as e:
            row.update(error=str(e)[:400]); log(row); print("ERROR", kind, e); return
        row.update(info); row["cost_usd_est"] = PRICE.get(args.quality, 0.25)
        img.save(RAW / f"{kind}_raw_{attempt}.png")
        res = finish(img); row.update(res)
        row["qa_pass"] = res.get("deco_ok", 16) >= 14
        log(row); print(f"{kind} attempt {attempt}: {res} ({info['latency_s']}s)")
        if row["qa_pass"]: break


def do_refinish(_args):
    """底图从 raw 重新裁切导出（不花钱）：每个区域把所有 raw 都按当前 QA 指标重算，取分最高的一张，按当前 TILE_OUT 重采样"""
    names = sorted({re.sub(r"_raw_\d+$", "", r.stem) for r in RAW.glob("*_raw_*.png") if not r.stem.startswith(("char_", "tiles_", "deco_", "obj_", "old_"))})
    for name in names:
        flat_p, meta_p = FLATS / f"{name}.png", FLATS / f"{name}.json"
        if not flat_p.exists(): print("skip (no flat)", name); continue
        meta = json.loads(meta_p.read_text()); flat = Image.open(flat_p).convert("RGBA")
        size = pick_size(flat.width, flat.height); _, box = letterbox(flat, size)
        best = None
        for raw in sorted(RAW.glob(f"{name}_raw_*.png")):
            crop = Image.open(raw).crop(box).convert("RGBA")
            score, _ = align_qa(flat, crop, meta)
            if best is None or score > best[0]: best = (score, raw.name, crop)
        if best is None: continue
        out = best[2].resize((meta["w"] * TILE_OUT, meta["h"] * TILE_OUT), Image.LANCZOS)
        out.save(OUT / "backdrops" / f"{name}.png")
        (OUT / "backdrops" / f"{name}.json").write_text(json.dumps({**meta, "tile_px": TILE_OUT, "qa_score": round(best[0], 3)}, ensure_ascii=False, indent=2))
        print(f"{name}: {best[1]} qa={best[0]:.3f} → {out.width}×{out.height}")

def do_qa(args):
    """对 data/assets/gen-ai-raw 里已有的 raw 重算对齐 QA（不花钱），刷新 backdrops/*.json 的 qa_score"""
    for raw in sorted(RAW.glob("*_raw_*.png")):
        name = re.sub(r"_raw_\d+$", "", raw.stem)
        flat_p, meta_p = FLATS / f"{name}.png", FLATS / f"{name}.json"
        if not flat_p.exists(): continue
        meta = json.loads(meta_p.read_text()); flat = Image.open(flat_p).convert("RGBA")
        size = pick_size(flat.width, flat.height); _, box = letterbox(flat, size)
        crop = Image.open(raw).crop(box)
        score, overlay = align_qa(flat, crop, meta)
        overlay.save(RAW / raw.name.replace("_raw_", "_qa_"))
        print(f"{raw.name}: qa={score:.3f}")
        jp = OUT / "backdrops" / f"{name}.json"
        if jp.exists():
            j = json.loads(jp.read_text()); j["qa_score"] = round(score, 3); jp.write_text(json.dumps(j, ensure_ascii=False, indent=2))

def do_manifest(_args):
    m = {"tile_px": TILE_OUT, "backdrops": {}, "objects": sorted(p.stem for p in (OUT / "objects").glob("*.png")),
         "chars": sorted(p.stem for p in (OUT / "chars").glob("*.png")), "char_frame": list(CHAR_FRAME_OUT),
         "deco": sorted(p.stem for p in (OUT / "deco").glob("*.png")) if (OUT / "deco").exists() else [],
         "tiles": json.loads((OUT / "tiles.json").read_text()) if (OUT / "tiles.json").exists() else None}
    for j in (OUT / "backdrops").glob("*.json"):
        m["backdrops"][j.stem] = json.loads(j.read_text())
    (OUT / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2))
    # 评审页材料：版式 / 最新 raw / 最新 QA 叠图（缩到 <= 512 px）+ gen.jsonl 拷贝
    rv = OUT / "review"; rv.mkdir(exist_ok=True)
    def thumb(src: Path, dst: Path, mx=512):
        im = Image.open(src); im.thumbnail((mx, mx)); im.save(dst, optimize=True)
    for name in m["backdrops"]:
        inp = RAW / f"{name}_input.png"
        if inp.exists(): thumb(inp, rv / f"{name}_input.png")
        raws = sorted(RAW.glob(f"{name}_raw_*.png")); qas = sorted(RAW.glob(f"{name}_qa_*.png"))
        if raws: thumb(raws[-1], rv / f"{name}_raw.png")
        if qas: thumb(qas[-1], rv / f"{name}_qa.png")
    for key in m["objects"]:
        r = RAW / f"obj_{key}_raw.png"
        if r.exists(): thumb(r, rv / f"obj_{key}_raw.png", 256)
    for key in m["chars"]:
        inp = RAW / f"char_{key}_input.png"
        if inp.exists(): thumb(inp, rv / f"char_{key}_input.png", 384)
        raws = sorted(RAW.glob(f"char_{key}_raw_*.png"))
        if raws: thumb(raws[-1], rv / f"char_{key}_raw.png", 384)
        sh = RAW / f"char_{key}_sheet.png"
        if sh.exists(): thumb(sh, rv / f"char_{key}_sheet.png", 720)
    for kind in ("tiles", "deco"):
        raws = sorted(RAW.glob(f"{kind}_raw_*.png"))
        if raws: thumb(raws[-1], rv / f"{kind}_raw.png", 512)
    if (RAW / "tiles_sheet.png").exists(): thumb(RAW / "tiles_sheet.png", rv / "tiles_sheet.png", 512)
    if LOG.exists(): (OUT / "gen.jsonl").write_text(LOG.read_text(encoding="utf-8"), encoding="utf-8")
    print("manifest:", len(m["backdrops"]), "backdrops,", len(m["objects"]), "objects,", len(m["chars"]), "chars")

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("backdrops"); a.add_argument("--regions"); a.add_argument("--quality", default="high"); a.add_argument("--attempts", type=int, default=2); a.add_argument("--qa", type=float, default=0.9); a.add_argument("--dry-run", action="store_true")
    b = sub.add_parser("objects"); b.add_argument("--items"); b.add_argument("--quality", default="high"); b.add_argument("--dry-run", action="store_true")
    c = sub.add_parser("chars"); c.add_argument("--keys"); c.add_argument("--quality", default="high"); c.add_argument("--attempts", type=int, default=2); c.add_argument("--reslice", action="store_true"); c.add_argument("--dry-run", action="store_true")
    for k in ("tiles", "deco"):
        g = sub.add_parser(k); g.add_argument("--quality", default="high"); g.add_argument("--attempts", type=int, default=2); g.add_argument("--reslice", action="store_true"); g.add_argument("--dry-run", action="store_true")
    sub.add_parser("manifest"); sub.add_parser("qa"); sub.add_parser("rekey"); sub.add_parser("refinish")
    args = ap.parse_args()
    {"backdrops": do_backdrops, "objects": do_objects, "chars": do_chars, "tiles": do_grid, "deco": do_grid, "manifest": do_manifest, "qa": do_qa, "rekey": do_rekey, "refinish": do_refinish}[args.cmd](args)
    if args.cmd != "manifest": do_manifest(args)

if __name__ == "__main__":
    main()
