#!/usr/bin/env python3
"""
美术管线 v1.0（W8）：用 OpenAI gpt-image-2 的 images.edit 重绘底图 / 物品 / 角色。密钥 ~/.env 的 OPENAI_API_KEY（仅此用途）。

  tools/.venv/bin/python tools/gen_assets_ai.py backdrops --regions home_1f_interior,home_1f_exterior [--quality high] [--attempts 2] [--dry-run]
  tools/.venv/bin/python tools/gen_assets_ai.py objects   --items bed,fridge [--quality high]
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
REF_STYLE = ROOT / "ref/jingzai_action_sheet_q.png"
REF_ROOM = ROOT / "ref/gpt-image-probe/house.png"
MODEL = "gpt-image-2"
TILE_OUT = 32            # 输出 px/格（前端 ×3 nearest = 96）
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
    "home_2f_interior": "the second floor of the shared house: a single bedroom belonging to a quiet programmer (cat-eared boy), wooden floor, stone walls, a stairway landing tile at the left",
    "classroom_1f_interior": "a university classroom building interior: one long room with a wooden floor, stone walls, a door on the bottom wall",
    "classroom_1f_exterior": "a small university classroom building seen from outside: blue tiled roof, pale stone outer walls, entrance door on the bottom side, campus pavement around it",
    "library_1f_interior": "a university library interior: one long reading hall with wooden floor and stone walls, a door on the bottom wall",
    "library_1f_exterior": "a small university library building seen from outside: blue tiled roof with a skylight, pale stone outer walls, entrance door on the bottom side, campus pavement around it",
    "music_room_1f_interior": "a university music building interior: one practice hall with wooden floor and stone walls, a door on the bottom wall",
    "music_room_1f_exterior": "a small university music building seen from outside: blue tiled roof, pale stone outer walls, a round window, entrance door on the bottom side, campus pavement around it",
}

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
    "tree": (1, 1, "a round leafy green tree with a brown trunk"),
    "fountain": (1, 1, "a small round stone fountain with blue water"),
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
        prompt = (f"The first image is a flat-colored top-down layout of {desc}. Repaint it as finished 2D top-down game art, "
                  f"keeping every wall, door{'' if view == 'exterior' else ', doorway'} and room boundary exactly at the same position and size, "
                  f"and keeping the surrounding ground (grass / pavement) where it is. "
                  + ("Draw the building exterior in the classic Pokemon-style 3/4 top-down RPG view: the blue-gray area of the layout is a pitched tiled roof (ridge line, eaves, a chimney) "
                     "and the lighter band along the bottom edge of the building is the FRONT WALL seen from the front, with windows, flower boxes and a wooden door; "
                     "the small brown square in the layout marks where the entrance tile is. Keep the building footprint exactly the same; do not show the interior. "
                     if view == "exterior" else "Do not add furniture; leave the floors empty so objects can be placed later. ")
                  + "The room layout must follow the first image exactly; do not copy or add rooms from any other image. "
                  + STYLE + " " + CAMERA_BACKDROP)
        size = pick_size(flat.width, flat.height)
        canvas, box = letterbox(flat, size)
        tmp = RAW / f"{name}_input.png"; canvas.save(tmp)
        best = None
        for attempt in range(1, args.attempts + 1):
            row = {"kind": "backdrop", "name": name, "model": MODEL, "size": size, "quality": args.quality, "attempt": attempt, "prompt": prompt,
                   "inputs": [str(tmp.relative_to(ROOT)), "ref/jingzai_action_sheet_q.png"], "seed": None, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
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
            q = quantize(best[1]); q.save(OUT / "backdrops" / f"{name}.png")
            (OUT / "backdrops" / f"{name}.json").write_text(json.dumps({**meta, "tile_px": TILE_OUT, "qa_score": round(best[0], 3)}, ensure_ascii=False, indent=2))

def finish_object(img: Image.Image, key: str, w: int, h: int):
    """品红抠像 → 裁 alpha 包围盒 → 缩到 footprint（w×h 格 × 32 px，保持比例、居中、底对齐）→ 量化 → 存 objects/<key>.png"""
    img = chroma_key(img.convert("RGBA"))
    bbox = img.getbbox()
    if bbox: img = img.crop(bbox)
    tw, th = w * TILE_OUT, h * TILE_OUT
    s = min(tw / img.width, th / img.height)
    small = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.LANCZOS)
    canvas = Image.new("RGBA", (tw, th), (0, 0, 0, 0)); canvas.paste(small, ((tw - small.width) // 2, th - small.height), small)
    quantize(canvas).save(OUT / "objects" / f"{key}.png")
    return bbox

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
        size = "1024x1024" if w == h else ("1536x1024" if w > h else "1024x1536")
        row = {"kind": "object", "name": key, "model": MODEL, "size": size, "quality": args.quality, "attempt": 1, "prompt": prompt,
               "inputs": ["ref/jingzai_action_sheet_q.png", "ref/gpt-image-probe/house.png"], "seed": None, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
        if args.dry_run: print(json.dumps(row, ensure_ascii=False)[:300]); continue
        try:
            img, info = call_edit(cli, [REF_STYLE, REF_ROOM], prompt, size, args.quality)   # gpt-image-2 不支持 transparent，用品红抠像
        except Exception as e:
            row.update(error=str(e)[:400]); log(row); print("ERROR", key, e); continue
        row.update(info); row["cost_usd_est"] = PRICE.get(args.quality, 0.25)
        img = img.convert("RGBA"); img.save(RAW / f"obj_{key}_raw.png")
        bbox = finish_object(img, key, w, h)
        row["alpha_bbox"] = bbox; row["out_px"] = [w * TILE_OUT, h * TILE_OUT]
        log(row); print(f"{key}: ok ({info['latency_s']}s)")

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
    m = {"tile_px": TILE_OUT, "backdrops": {}, "objects": sorted(p.stem for p in (OUT / "objects").glob("*.png"))}
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
    if LOG.exists(): (OUT / "gen.jsonl").write_text(LOG.read_text(encoding="utf-8"), encoding="utf-8")
    print("manifest:", len(m["backdrops"]), "backdrops,", len(m["objects"]), "objects")

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("backdrops"); a.add_argument("--regions"); a.add_argument("--quality", default="high"); a.add_argument("--attempts", type=int, default=2); a.add_argument("--qa", type=float, default=0.9); a.add_argument("--dry-run", action="store_true")
    b = sub.add_parser("objects"); b.add_argument("--items"); b.add_argument("--quality", default="high"); b.add_argument("--dry-run", action="store_true")
    sub.add_parser("manifest"); sub.add_parser("qa"); sub.add_parser("rekey")
    args = ap.parse_args()
    {"backdrops": do_backdrops, "objects": do_objects, "manifest": do_manifest, "qa": do_qa, "rekey": do_rekey}[args.cmd](args)
    if args.cmd != "manifest": do_manifest(args)

if __name__ == "__main__":
    main()
