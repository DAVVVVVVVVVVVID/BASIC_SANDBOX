#!/usr/bin/env python3
"""
W9 0c（总控 11-07 晚，主播「先快修」）：AI 底图的墙 / 门与引擎格子错位 → 量偏差 + 不花钱的确定性校正。

  tools/.venv/bin/python tools/rectify_backdrops.py measure [--names a,b] [--src DIR] [--out data/assets/rectify_report.json] [--overlays]
  tools/.venv/bin/python tools/rectify_backdrops.py fix     [--names a,b]        # 原图第一次备份到 data/assets/gen-ai-raw/prefix_<name>.png，之后永远从备份出发，可重复跑
  tools/.venv/bin/python tools/rectify_backdrops.py restore [--names a,b]        # 从备份还原

室内做法：墙的位置不再信模型——每个引擎 wall 格用「从同一张图量到的墙带」合成一块整格墙砖（墙带放在格子靠房间一侧，其余用墙顶面补满），
优先用该格自己位置上的墙带像素（外圈大多对得准，细节保留），该处不是干净的墙（门 / 窗 / 偏掉了）就用整段里最干净的一段；
模型画出引擎格以外的墙（偏进地板里的那部分 + 墙下阴影）用该房间的干净地板补回；室内门（墙上开口）铲平成地板；
对外的门：先贴墙砖再把模型画的门剪下来贴到引擎门格（没量到就用 objects/door_closed.png）；多画的门 / 窗随墙重画消失；最后沿墙补一条软阴影。
室外（exterior）只校正正面墙上的门：剪下来平移到引擎门格，原位用旁边的墙面补。
量法：墙带 = 沿引擎墙段逐行（列）统计「墙色占比」（平滑 1/4 格）> 0.42 的连续带，取与引擎格重叠最多的；偏差 = 带中心 − 格中心；
开口 = 墙带里非墙色的窗口，配到 2 格内最近的引擎开口；配不上的是「多余开口」。
"""
from __future__ import annotations
import argparse, json, shutil
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
FLATS = ROOT / "data/assets/flats"
OUT = ROOT / "public/assets/gen-ai/backdrops"
RAW = ROOT / "data/assets/gen-ai-raw"
REPORT = ROOT / "data/assets/rectify_report.json"
OVERLAYS = ROOT / "data/assets/rectify"
T = 96      # AI 底图 px/格
F = 32      # 版式 px/格

# FlatApp 的 COLORS（版式图里各类格子的平涂色）
C = {"grass": (127, 184, 122), "grass1": (110, 163, 109), "wall": (122, 106, 99), "floor": (217, 185, 140), "water": (106, 162, 214),
     "road": (185, 169, 138), "square": (207, 195, 173), "park": (115, 173, 114), "dock": (180, 138, 90), "carpet": (184, 106, 98),
     "tile": (232, 226, 210), "door": (154, 106, 62), "stairs": (201, 166, 115), "roof": (91, 111, 181), "roof_edge": (63, 79, 138), "outer_wall": (138, 122, 114)}
FLOOR_KINDS = {"floor", "carpet", "tile"}
OUTDOOR = {"square", "park", "dock"}

def classify(rgb) -> str:
    best, bd = "other", 1e9
    for k, c in C.items():
        d = sum(abs(int(a) - b) for a, b in zip(rgb, c))
        if d < bd: best, bd = k, d
    return best if bd < 24 else "other"

def smooth(vals, k):
    v = np.asarray(vals, float); k = max(1, int(k)); ker = np.ones(k) / k
    return np.convolve(np.pad(v, (k // 2, k - 1 - k // 2), mode="edge"), ker, mode="valid")

def runs_of(flags):
    out, cur = [], None
    for i, f in enumerate(flags):
        if f:
            if cur is None: cur = [i, i]
            else: cur[1] = i
        elif cur is not None: out.append(tuple(cur)); cur = None
    if cur is not None: out.append(tuple(cur))
    return out

def palette(pixels: np.ndarray, k: int = 5):
    if len(pixels) == 0: return []
    im = Image.fromarray(pixels.reshape(1, -1, 3).astype(np.uint8), "RGB").quantize(colors=k, method=Image.MEDIANCUT, dither=Image.NONE)
    pal = np.array(im.getpalette()[: k * 3]).reshape(-1, 3); counts = np.bincount(np.asarray(im).ravel(), minlength=k)
    order = np.argsort(-counts)
    return [(pal[i], counts[i] / counts.sum()) for i in order if counts[i] > 0]

def closeness(a: np.ndarray, cols, thr: float) -> np.ndarray:
    m = np.zeros(a.shape[:2], bool)
    for c in cols: m |= np.abs(a[:, :, :3].astype(int) - np.asarray(c).astype(int)).sum(axis=2) < thr
    return m

# ──────────────────────────────────────────────────────────────────────────────
class Scene:
    """一张底图 + 它的引擎版式"""
    def __init__(self, name: str, src: Path):
        self.name = name
        self.meta = json.loads((FLATS / f"{name}.json").read_text())
        self.flat = Image.open(FLATS / f"{name}.png").convert("RGB")
        self.img = Image.open(src / f"{name}.png").convert("RGBA")
        self.H, self.W = self.meta["h"], self.meta["w"]
        assert self.img.size == (self.W * T, self.H * T), f"{name}: backdrop {self.img.size} != {self.W*T}x{self.H*T}"
        self.a = np.asarray(self.img).copy()
        H, W = self.H, self.W
        cls = [[None] * W for _ in range(H)]; base = [[None] * W for _ in range(H)]
        for ty in range(H):
            for tx in range(W):
                c = classify(self.flat.getpixel((tx * F + F // 2, ty * F + F // 2)))
                b = classify(self.flat.getpixel((tx * F + 2, ty * F + 2)))   # 门 / 楼梯方块只占中间 70%，角上是底下的格子
                cls[ty][tx] = c; base[ty][tx] = b if c in ("door", "stairs") else c
        # 地图边界 / 别的建筑的 wall 不算本建筑的墙：墙必须 8 邻域里有室内地板
        for ty in range(H):
            for tx in range(W):
                if cls[ty][tx] == "wall" and not any(base[y][x] in FLOOR_KINDS for y in range(max(0, ty-1), min(H, ty+2)) for x in range(max(0, tx-1), min(W, tx+2))):
                    cls[ty][tx] = "other"; base[ty][tx] = "other"
        self.cls, self.base = cls, base
        self.view = self.meta["view"]
        self.outdoor = name.split("_")[0] in OUTDOOR
        self.doors = [(tx, ty) for ty in range(H) for tx in range(W) if cls[ty][tx] == "door"]
        self.stairs = [(tx, ty) for ty in range(H) for tx in range(W) if cls[ty][tx] == "stairs"]
        self.segs = []

    def wall(self, ty, tx): return 0 <= ty < self.H and 0 <= tx < self.W and self.cls[ty][tx] == "wall"
    def indoor(self, ty, tx): return 0 <= ty < self.H and 0 <= tx < self.W and (self.base[ty][tx] in FLOOR_KINDS or self.cls[ty][tx] == "wall")
    def floor(self, ty, tx): return 0 <= ty < self.H and 0 <= tx < self.W and self.base[ty][tx] in FLOOR_KINDS and self.cls[ty][tx] != "wall"
    def is_gap(self, ty, tx):
        """墙线上的开口格（室内门 / 对外门）"""
        return self.floor(ty, tx) and ((self.wall(ty, tx-1) and self.wall(ty, tx+1)) or (self.wall(ty-1, tx) and self.wall(ty+1, tx)))

    # ── 墙段 ──
    def segments(self):
        """横 / 竖墙段（含开口）：[(orient, fixed, a0, b0, gaps)]"""
        segs = []
        for orient in ("h", "v"):
            n_fixed, n_along = (self.H, self.W) if orient == "h" else (self.W, self.H)
            isw = (lambda f, p: self.wall(f, p)) if orient == "h" else (lambda f, p: self.wall(p, f))
            gap = (lambda f, p: self.is_gap(f, p)) if orient == "h" else (lambda f, p: self.is_gap(p, f))
            for f in range(n_fixed):
                p = 0
                while p < n_along:
                    if not isw(f, p): p += 1; continue
                    a0 = p
                    while p < n_along and (isw(f, p) or (p + 1 < n_along and isw(f, p + 1) and gap(f, p))): p += 1
                    b0 = p - 1
                    if b0 - a0 >= 2: segs.append((orient, f, a0, b0, [q for q in range(a0, b0 + 1) if not isw(f, q)]))
        return segs

    # ── 墙色 ──
    def wall_palette(self):
        H, W = self.H, self.W; a = self.a
        def corner(ty, tx): return (self.wall(ty, tx-1) or self.wall(ty, tx+1)) and (self.wall(ty-1, tx) or self.wall(ty+1, tx))
        def outer(ty, tx): return any(not self.indoor(y, x) for y, x in ((ty-1, tx), (ty+1, tx), (ty, tx-1), (ty, tx+1)))
        ring = [(ty, tx) for ty in range(H) for tx in range(W) if self.wall(ty, tx) and outer(ty, tx) and not corner(ty, tx)]
        if not ring: ring = [(ty, tx) for ty in range(H) for tx in range(W) if self.wall(ty, tx)]
        wall_px = np.concatenate([a[ty*T+12:ty*T+84, tx*T+12:tx*T+84, :3].reshape(-1, 3) for ty, tx in ring])
        far = [(ty, tx) for ty in range(H) for tx in range(W) if self.floor(ty, tx) and not any(self.wall(y, x) for y in range(ty-1, ty+2) for x in range(tx-1, tx+2))]
        floor_px = np.concatenate([a[ty*T+8:ty*T+88, tx*T+8:tx*T+88, :3].reshape(-1, 3) for ty, tx in far]) if far else np.zeros((0, 3))
        outside = [(ty, tx) for ty in range(H) for tx in range(W) if not self.indoor(ty, tx)]
        out_px = np.concatenate([a[ty*T+8:ty*T+88, tx*T+8:tx*T+88, :3].reshape(-1, 3) for ty, tx in outside]) if outside else np.zeros((0, 3))
        wp = palette(wall_px, 8); fp = palette(floor_px, 6) if len(floor_px) else []; op = palette(out_px, 6) if len(out_px) else []
        far_from = lambda c, pal, thr: all(np.abs(c.astype(int) - f.astype(int)).sum() > thr for f, _ in pal)
        greenish = lambda c: int(c[1]) > int(c[0]) + 12 and int(c[1]) > int(c[2]) + 12   # 草 / 树：墙从不是绿的
        cols = [c for c, sh in wp if sh >= 0.06 and far_from(c, fp, 50) and far_from(c, op, 30) and not greenish(c)]
        return cols or [c for c, _ in wp[:3] if not greenish(c)] or [c for c, _ in wp[:3]]

    # ── 分析 ──
    def analyze(self):
        """量每段墙的墙带 / 开口；self.segs = [{orient,fixed,a0,b0,gaps,band,windows,openings,extra}]"""
        self.wcols = self.wall_palette()
        self.wmask = closeness(self.a, self.wcols, 48)
        segs = []
        for orient, fixed, a0, b0, gaps in self.segments():
            seg = {"orient": orient, "fixed": fixed, "a0": a0, "b0": b0, "gaps": gaps, "band": None, "windows": [], "openings": {}, "extra": []}
            band = self.find_band(orient, fixed, a0, b0, gaps)
            if band is not None:
                seg["band"] = band
                wins = self.windows(orient, fixed, a0, b0, band)
                seg["windows"] = wins
                used = set()
                for g in gaps:
                    cand = [w for w in wins if abs((w[0] + w[1]) / 2 - (g + 0.5)) <= 2.0 and w not in used]
                    if cand:
                        w = min(cand, key=lambda w: abs((w[0] + w[1]) / 2 - (g + 0.5))); used.add(w); seg["openings"][g] = w
                seg["extra"] = [w for w in wins if w not in used]
            segs.append(seg)
        self.segs = segs
        return segs

    def find_band(self, orient, fixed, a0, b0, gaps, span=1.5, thr=0.42):
        """沿法向逐行（列）墙色占比 → 与引擎格 [0,T) 重叠最多的连续带 (lo, hi) px，相对 fixed*T"""
        m = self.wmask
        xs = [x for x in range(a0, b0 + 1) if x not in gaps]
        lo, hi = int((fixed - span) * T), int((fixed + 1 + span) * T)
        n = m.shape[0] if orient == "h" else m.shape[1]
        ps = list(range(max(0, lo), min(n, hi)))
        prof = []
        for p in ps:
            vals = np.concatenate([m[p, x*T:(x+1)*T] for x in xs]) if orient == "h" else np.concatenate([m[x*T:(x+1)*T, p] for x in xs])
            prof.append(vals.mean())
        sm = smooth(prof, T // 4)
        rr = [(ps[s] - fixed * T, ps[e] + 1 - fixed * T) for s, e in runs_of(sm > thr) if e - s + 1 >= T * 0.25]
        if not rr: return None
        def overlap(r): return max(0, min(r[1], T) - max(r[0], 0))
        best = max(rr, key=lambda r: (overlap(r), -abs((r[0] + r[1]) / 2 - T / 2)))
        if overlap(best) == 0 and abs((best[0] + best[1]) / 2 - T / 2) > T * 1.2: return None
        return best

    def windows(self, orient, fixed, a0, b0, band):
        """墙带里沿墙方向的非墙窗口 → [(start_tile, end_tile)]"""
        m = self.wmask
        t0, t1 = int(fixed * T + band[0] + 4), int(fixed * T + band[1] - 4)
        if t1 <= t0 + 4: return []
        cols = []
        for q in range(a0 * T, (b0 + 1) * T):
            v = m[t0:t1, q] if orient == "h" else m[q, t0:t1]
            cols.append(v.mean())
        sm = smooth(cols, T // 6)
        out = []
        for s, e in runs_of(sm < 0.3):
            if e - s + 1 >= T * 0.4 and s > 3 and e < len(cols) - 4: out.append((a0 + s / T, a0 + (e + 1) / T))
        return out

    def seg_of(self, orient, fixed, pos):
        for s in self.segs:
            if s["orient"] == orient and s["fixed"] == fixed and s["a0"] <= pos <= s["b0"]: return s
        return None

    # ── 室外正面墙的门 ──
    def facade(self):
        H, W = self.H, self.W
        fac = [(tx, ty) for ty in range(H) for tx in range(W) if self.cls[ty][tx] == "outer_wall" or (self.cls[ty][tx] == "door" and self.base[ty][tx] in ("outer_wall", "roof", "roof_edge"))]
        if not fac: return None
        ty = max(set(t for _, t in fac), key=lambda t: sum(1 for _, tt in fac if tt == t))
        xs = sorted(tx for tx, t in fac if t == ty)
        return ty, xs

    def facade_doors(self):
        """正面墙附近（引擎 facade 行 −0.5 格 … +1.5 格）里门大小的深棕木色连通块 → [(start_tile, end_tile, y_top_px, y_bot_px)]"""
        f = self.facade()
        if not f: return []
        ty, xs = f
        y_a, y_b = max(0, int((ty - 0.5) * T)), min(self.H * T, int((ty + 1.6) * T))
        x_a, x_b = xs[0] * T, (xs[-1] + 1) * T
        band = self.a[y_a:y_b, x_a:x_b, :3].astype(int)
        r_, g_, b_ = band[:, :, 0], band[:, :, 1], band[:, :, 2]
        brown = (r_ > g_) & (g_ >= b_ - 6) & (r_ - b_ >= 30) & (r_ <= 190) & (g_ <= 150)
        # 连通块（4 邻域，简单扫描）
        lab = np.zeros(brown.shape, int); n = 0; comps = []
        Hh, Ww = brown.shape
        for y in range(Hh):
            for x in range(Ww):
                if brown[y, x] and lab[y, x] == 0:
                    n += 1; stack = [(y, x)]; lab[y, x] = n; ys = []; xs_ = []
                    while stack:
                        cy, cx = stack.pop(); ys.append(cy); xs_.append(cx)
                        for ny, nx in ((cy+1, cx), (cy-1, cx), (cy, cx+1), (cy, cx-1)):
                            if 0 <= ny < Hh and 0 <= nx < Ww and brown[ny, nx] and lab[ny, nx] == 0: lab[ny, nx] = n; stack.append((ny, nx))
                    if len(ys) >= T * T * 0.12:
                        y0_, y1_, x0_, x1_ = min(ys), max(ys) + 1, min(xs_), max(xs_) + 1
                        w, h = (x1_ - x0_) / T, (y1_ - y0_) / T
                        if 0.4 <= w <= 1.3 and 0.5 <= h <= 1.4 and len(ys) >= 0.35 * (x1_ - x0_) * (y1_ - y0_):
                            comps.append(((x_a + x0_) / T, (x_a + x1_) / T, y_a + y0_, y_a + y1_))
        return comps

# ──────────────────────────────────────────────────────────────────────────────
def pick_facade_door(sc: Scene, dx, cands):
    """只在没有歧义时认门：整面墙只有一个门大小的深棕块（6 格内都认，home 的门被画到正中、离引擎门 4.8 格），
    或 1.5 格内恰好只有一个；窗框 / 菜箱也是棕色，多个候选时不猜（报人工核对）"""
    cen = dx + 0.5
    if len(cands) == 1 and abs((cands[0][0] + cands[0][1]) / 2 - cen) <= 6: return cands[0]
    near = [c for c in cands if abs((c[0] + c[1]) / 2 - cen) <= 1.5]
    return near[0] if len(near) == 1 else None

def measure_one(name, src: Path):
    sc = Scene(name, src); x0, y0 = sc.meta["x0"], sc.meta["y0"]; rows = []
    if sc.outdoor: return {"name": name, "view": sc.view, "rows": rows, "note": "室外地面，无墙"}
    if sc.view == "exterior":
        f = sc.facade()
        if not f: return {"name": name, "view": sc.view, "rows": rows, "note": "no facade"}
        ty, xs = f; cands = sc.facade_doors()
        for dx, dy in sc.doors:
            if dy != ty: continue
            c = pick_facade_door(sc, dx, cands)
            if c:
                rows.append({"kind": "door", "engine": [x0 + dx, y0 + dy], "drawn": [round(x0 + (c[0] + c[1]) / 2, 2), y0 + ty + 0.5], "offset_tiles": round((c[0] + c[1]) / 2 - (dx + 0.5), 2), "width_tiles": round(c[1] - c[0], 2)})
            else:
                rows.append({"kind": "door", "engine": [x0 + dx, y0 + dy], "drawn": None, "offset_tiles": None, "note": "正面墙上没找到门", "cands": [(round(c[0], 2), round(c[1], 2)) for c in cands]})
        return {"name": name, "view": sc.view, "rows": rows}

    sc.analyze()
    extra = []
    for s in sc.segs:
        orient, fixed, a0, b0 = s["orient"], s["fixed"], s["a0"], s["b0"]
        seg_name = f"{'横' if orient == 'h' else '竖'}墙 {'y' if orient == 'h' else 'x'}={(y0 if orient == 'h' else x0) + fixed} {'x' if orient == 'h' else 'y'}∈[{(x0 if orient == 'h' else y0) + a0},{(x0 if orient == 'h' else y0) + b0}]"
        if s["band"] is None:
            rows.append({"kind": "wall", "seg": seg_name, "offset_tiles": None, "note": "没找到墙带"}); continue
        b = s["band"]; off = ((b[0] + b[1]) / 2 - T / 2) / T
        rows.append({"kind": "wall", "seg": seg_name, "offset_tiles": round(off, 2), "thickness_tiles": round((b[1] - b[0]) / T, 2)})
        for g in s["gaps"]:
            pos = [x0 + g, y0 + fixed] if orient == "h" else [x0 + fixed, y0 + g]
            w = s["openings"].get(g)
            if w: rows.append({"kind": "opening", "engine": pos, "offset_along": round((w[0] + w[1]) / 2 - (g + 0.5), 2), "offset_across": round(off, 2), "width_tiles": round(w[1] - w[0], 2)})
            else: rows.append({"kind": "opening", "engine": pos, "offset_along": None, "offset_across": round(off, 2), "note": "墙带里没画开口（墙连着）"})
        for w in s["extra"]:
            pos = [round(x0 + (w[0] + w[1]) / 2, 2), round(y0 + fixed + off + 0.5, 2)] if orient == "h" else [round(x0 + fixed + off + 0.5, 2), round(y0 + (w[0] + w[1]) / 2, 2)]
            extra.append({"kind": "extra_opening", "drawn": pos, "width_tiles": round(w[1] - w[0], 2), "seg": seg_name})
    rows.extend(extra)
    return {"name": name, "view": sc.view, "rows": rows, "wall_palette": [c.tolist() for c in sc.wcols]}

def overlay_image(name, src: Path, dst: Path):
    sc = Scene(name, src); H, W = sc.H, sc.W
    ov = Image.new("RGBA", sc.img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    for ty in range(H):
        for tx in range(W):
            c = sc.cls[ty][tx]; r = [tx*T, ty*T, (tx+1)*T-1, (ty+1)*T-1]
            if c == "wall": d.rectangle(r, fill=(255, 40, 40, 70), outline=(255, 40, 40, 160))
            elif c == "outer_wall": d.rectangle(r, outline=(255, 120, 40, 160))
            elif c == "door": d.rectangle(r, fill=(255, 210, 60, 90), outline=(255, 210, 60, 230), width=3)
            elif c == "stairs": d.rectangle(r, fill=(60, 220, 255, 90), outline=(60, 220, 255, 230), width=3)
            elif sc.is_gap(ty, tx): d.rectangle(r, fill=(60, 255, 120, 80), outline=(60, 255, 120, 230), width=3)
    for x in range(0, W*T+1, T): d.line([(x, 0), (x, H*T)], fill=(255, 255, 255, 60))
    for y in range(0, H*T+1, T): d.line([(0, y), (W*T, y)], fill=(255, 255, 255, 60))
    out = Image.alpha_composite(sc.img, ov); out.thumbnail((1024, 1024)); out.save(dst)

# ──────────────────────────────────────────────────────────────────────────────
def clean_floor_tile(sc: Scene, orig: np.ndarray, ty, tx):
    """同房间（不穿墙 4 连通）、同地板种类、离墙最远的地板格像素块"""
    H, W = sc.H, sc.W; kind = sc.base[ty][tx]
    seen, q, comp = {(tx, ty)}, [(tx, ty)], []
    while q:
        x, y = q.pop(); comp.append((x, y))
        for nx, ny in ((x+1, y), (x-1, y), (x, y+1), (x, y-1)):
            if sc.floor(ny, nx) and sc.base[ny][nx] == kind and (nx, ny) not in seen and not sc.is_gap(ny, nx): seen.add((nx, ny)); q.append((nx, ny))
    blockers = [(xx, yy) for yy in range(H) for xx in range(W) if sc.wall(yy, xx) or sc.cls[yy][xx] in ("door", "stairs") or not sc.indoor(yy, xx)]
    def d2w(x, y): return min(max(abs(xx-x), abs(yy-y)) for xx, yy in blockers) if blockers else 99
    best = max(comp, key=lambda p: (d2w(*p), -abs(p[0]-tx) - abs(p[1]-ty)))
    return orig[best[1]*T:(best[1]+1)*T, best[0]*T:(best[0]+1)*T]

def textured_fill(strip: np.ndarray, n: int, axis: int) -> np.ndarray:
    """沿 axis 方向补 n 行（列）：取墙带靠外侧 1/4 的均色，叠上墙带去均值后的细节（×0.5），避免平铺窄条产生条纹"""
    edge = strip[: max(8, strip.shape[0] // 4)] if axis == 0 else strip[:, : max(8, strip.shape[1] // 4)]
    mean = edge[:, :, :3].reshape(-1, 3).mean(axis=0)
    detail = (strip[:, :, :3].astype(float) - strip[:, :, :3].reshape(-1, 3).mean(axis=0)) * 0.5
    out = np.zeros(((n, strip.shape[1], 4) if axis == 0 else (strip.shape[0], n, 4)), np.uint8); out[:, :, 3] = 255
    for i in range(n):
        src = detail[i % detail.shape[0]] if axis == 0 else detail[:, i % detail.shape[1]]
        vals = np.clip(mean + src, 0, 255).astype(np.uint8)
        if axis == 0: out[i, :, :3] = vals
        else: out[:, i, :3] = vals
    return out

def wall_tile(sc: Scene, orig: np.ndarray, orient: str, fixed: int, pos: int, band, clean_strip):
    """合成一块整格墙砖：墙带（厚 h<T）贴在格子的「房间一侧」（横墙：下沿；竖墙：居中），其余用墙顶面补满。
    优先用该格自己位置上的墙带像素（干净时），否则用 clean_strip"""
    lo, hi = int(round(band[0])), int(round(band[1])); h = max(T // 3, min(T, hi - lo))
    tile = np.zeros((T, T, 4), np.uint8); tile[:, :, 3] = 255
    if orient == "h":
        y0 = max(0, fixed * T + lo); strip = orig[y0:y0 + h, pos*T:(pos+1)*T]
        ok = strip.shape[0] == h and sc.wmask[y0:y0 + h, pos*T:(pos+1)*T].mean() > 0.7
        if not ok: strip = clean_strip
        h = min(h, strip.shape[0]); strip = strip[:h]
        fill_h = T - h
        if fill_h > 0: tile[:fill_h] = textured_fill(strip, fill_h, 0)
        tile[fill_h:] = strip
    else:
        x0 = max(0, fixed * T + lo); strip = orig[pos*T:(pos+1)*T, x0:x0 + h]
        ok = strip.shape[1] == h and sc.wmask[pos*T:(pos+1)*T, x0:x0 + h].mean() > 0.7
        if not ok: strip = clean_strip
        h = min(h, strip.shape[1]); strip = strip[:, :h]
        left = (T - h) // 2; right = T - h - left
        if left > 0: tile[:, :left] = textured_fill(strip, left, 1)
        tile[:, left:left + h] = strip
        if right > 0: tile[:, left + h:] = textured_fill(strip, right, 1)
    return tile

def clean_strip_for(sc: Scene, orig: np.ndarray, orient: str):
    """整图里最干净的一段墙带（长 1 格、厚 = 墙带厚）→ (score, strip, band)"""
    best = None
    for s in sc.segs:
        if s["orient"] != orient or s["band"] is None: continue
        lo, hi = int(round(s["band"][0])), int(round(s["band"][1])); h = max(T // 3, min(T, hi - lo))
        for p in range(s["a0"], s["b0"] + 1):
            if p in s["gaps"]: continue
            if orient == "h":
                y0 = s["fixed"] * T + lo
                if y0 < 0 or y0 + h > sc.H * T: continue
                score = sc.wmask[y0:y0+h, p*T:(p+1)*T].mean(); strip = orig[y0:y0+h, p*T:(p+1)*T]
            else:
                x0 = s["fixed"] * T + lo
                if x0 < 0 or x0 + h > sc.W * T: continue
                score = sc.wmask[p*T:(p+1)*T, x0:x0+h].mean(); strip = orig[p*T:(p+1)*T, x0:x0+h]
            if best is None or score > best[0]: best = (score, strip.copy(), s["band"])
    return best

def door_sprite_from(orig, sx, sy):
    """从原图 (sx,sy) 处剪 T×T，按与中心色的接近度抠出门本体 → RGBA"""
    crop = orig[sy:sy+T, sx:sx+T].copy()
    cc = crop[T//2-8:T//2+8, T//2-8:T//2+8, :3].reshape(-1, 3).mean(axis=0)
    dist = np.abs(crop[:, :, :3].astype(int) - cc.astype(int)).sum(axis=2)
    al = np.clip((110 - dist) / 60, 0, 1)
    ys, xs_ = np.where(al > 0.5)
    if len(ys) < 200: return None
    m = np.zeros((T, T), bool); m[ys.min():ys.max()+1, xs_.min():xs_.max()+1] = True
    return np.dstack([crop[:, :, :3], (al * m * 255).astype(np.uint8)])

def blend(dst, sprite):
    al = sprite[:, :, 3:4].astype(float) / 255
    dst[:, :, :3] = (sprite[:, :, :3] * al + dst[:, :, :3] * (1 - al)).astype(np.uint8)

def fix_one(name, src: Path):
    sc = Scene(name, src); H, W = sc.H, sc.W
    if sc.outdoor: return {"name": name, "skipped": "outdoor"}
    a = sc.a; orig = a.copy()
    if sc.view == "exterior":
        f = sc.facade()
        if not f: return {"name": name, "skipped": "no facade"}
        ty, xs = f; cands = sc.facade_doors(); moved = []
        for dx, dy in sc.doors:
            if dy != ty: continue
            c = pick_facade_door(sc, dx, cands)
            if not c: continue
            off = (c[0] + c[1]) / 2 - (dx + 0.5)
            if abs(off) < 0.3: continue
            dw = int(max(T, (c[1] - c[0]) * T + T // 2)); sx0 = int((c[0] + c[1]) / 2 * T - dw / 2)   # 连门框 / 拱一起剪
            by0, by1 = max(0, int(c[2]) - T // 4), min(H * T, int(c[3]) + T // 3)        # 门 + 门框 + 门前台阶
            door = orig[by0:by1, sx0:sx0 + dw].copy()
            fill = orig[by0:by1, sx0 - dw:sx0] if sx0 - dw >= xs[0] * T else orig[by0:by1, sx0 + dw:sx0 + 2 * dw]
            if fill.shape == door.shape: a[by0:by1, sx0:sx0 + dw] = fill
            nx0 = int((dx + 0.5) * T - dw / 2); nx0 = max(0, min(W * T - dw, nx0))
            a[by0:by1, nx0:nx0 + dw] = door
            moved.append({"engine": [sc.meta["x0"] + dx, sc.meta["y0"] + dy], "from_offset": round(off, 2)})
        Image.fromarray(a, "RGBA").save(OUT / f"{name}.png")
        return {"name": name, "moved_doors": moved}

    sc.analyze()
    cs_h = clean_strip_for(sc, orig, "h"); cs_v = clean_strip_for(sc, orig, "v")
    if cs_h is None and cs_v is None: return {"name": name, "error": "没有任何墙带可采样"}
    if cs_h is None: cs_h = (0, np.rot90(cs_v[1]).copy(), cs_v[2])
    if cs_v is None: cs_v = (0, np.rot90(cs_h[1], -1).copy(), cs_h[2])
    floor_cache = {}
    def clean_floor(ty, tx):
        k = (ty, tx)
        if k not in floor_cache: floor_cache[k] = clean_floor_tile(sc, orig, ty, tx)
        return floor_cache[k]

    # 1) 模型画到引擎墙格以外的墙 + 墙下阴影 → 地板
    for s in sc.segs:
        if s["band"] is None: continue
        lo, hi = s["band"]; orient, fixed = s["orient"], s["fixed"]
        ranges = []                                      # 法向上要清的 px 区间（相对 fixed*T）
        if lo < 0: ranges.append((lo - 6, 0))
        if hi > T - T // 4: ranges.append((T, hi + T // 4 + 6))   # 带越界的部分 + 下方阴影
        for r0, r1 in ranges:
            for p in range(s["a0"], s["b0"] + 1):
                for q in range(int(np.floor(r0 / T)), int(np.ceil(r1 / T)) + 1):
                    ty, tx = (fixed + q, p) if orient == "h" else (p, fixed + q)
                    if not sc.floor(ty, tx) or (tx, ty) in sc.stairs: continue
                    cf = clean_floor(ty, tx); blk = a[ty*T:(ty+1)*T, tx*T:(tx+1)*T]
                    if orient == "h":
                        y_lo = max(0, int(fixed * T + r0) - ty * T); y_hi = min(T, int(fixed * T + r1) - ty * T)
                        if y_hi > y_lo: blk[y_lo:y_hi] = cf[y_lo:y_hi]
                    else:
                        x_lo = max(0, int(fixed * T + r0) - tx * T); x_hi = min(T, int(fixed * T + r1) - tx * T)
                        if x_hi > x_lo: blk[:, x_lo:x_hi] = cf[:, x_lo:x_hi]
    # 2) 开口格整格铲成地板
    for ty in range(H):
        for tx in range(W):
            if sc.is_gap(ty, tx): a[ty*T:(ty+1)*T, tx*T:(tx+1)*T] = clean_floor(ty, tx)
    # 3) 墙砖
    def tile_for(ty, tx):
        horiz = sc.wall(ty, tx-1) or sc.wall(ty, tx+1) or (sc.wall(ty-1, tx) is False and sc.wall(ty+1, tx) is False)
        if horiz:
            s = sc.seg_of("h", ty, tx); band = s["band"] if s and s["band"] is not None else cs_h[2]
            return wall_tile(sc, orig, "h", ty, tx, band, cs_h[1])
        s = sc.seg_of("v", tx, ty); band = s["band"] if s and s["band"] is not None else cs_v[2]
        return wall_tile(sc, orig, "v", tx, ty, band, cs_v[1])
    for ty in range(H):
        for tx in range(W):
            if sc.wall(ty, tx): a[ty*T:(ty+1)*T, tx*T:(tx+1)*T] = tile_for(ty, tx)
    # 4) 对外的门：开口格贴墙砖 + 门
    fallback = None
    p = ROOT / "public/assets/gen-ai/objects/door_closed.png"
    if p.exists():
        d = Image.open(p).convert("RGBA"); d.thumbnail((T - 8, T - 8)); cv = Image.new("RGBA", (T, T), (0, 0, 0, 0)); cv.paste(d, ((T - d.width) // 2, T - d.height - 2), d); fallback = np.asarray(cv)
    for dx, dy in sc.doors:
        if not sc.is_gap(dy, dx): continue
        horiz = sc.wall(dy, dx-1) and sc.wall(dy, dx+1)
        s = sc.seg_of("h", dy, dx) if horiz else sc.seg_of("v", dx, dy)
        cs = cs_h if horiz else cs_v
        band = s["band"] if s and s["band"] is not None else cs[2]
        a[dy*T:(dy+1)*T, dx*T:(dx+1)*T] = wall_tile(sc, orig, "h" if horiz else "v", dy if horiz else dx, dx if horiz else dy, band, cs[1])
        sprite = None
        w = s["openings"].get(dx if horiz else dy) if s else None
        if w and s["band"] is not None:
            cen = (w[0] + w[1]) / 2 * T; mid = s["fixed"] * T + (s["band"][0] + s["band"][1]) / 2
            sx, sy = (int(cen - T / 2), int(mid - T / 2)) if horiz else (int(mid - T / 2), int(cen - T / 2))
            sprite = door_sprite_from(orig, max(0, min(W*T - T, sx)), max(0, min(H*T - T, sy)))
        if sprite is None: sprite = fallback
        if sprite is not None: blend(a[dy*T:(dy+1)*T, dx*T:(dx+1)*T], sprite)
    # 5) 软阴影：横墙下方（房间侧）、竖墙右侧
    sh = Image.new("RGBA", sc.img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(sh)
    for ty in range(H):
        for tx in range(W):
            if not sc.wall(ty, tx): continue
            if sc.floor(ty+1, tx):
                for i in range(20): d.line([(tx*T, (ty+1)*T + i), ((tx+1)*T - 1, (ty+1)*T + i)], fill=(25, 15, 35, int(60 * (1 - i / 20))))
            if sc.floor(ty, tx+1):
                for i in range(12): d.line([((tx+1)*T + i, ty*T), ((tx+1)*T + i, (ty+1)*T - 1)], fill=(25, 15, 35, int(34 * (1 - i / 12))))
    out = Image.alpha_composite(Image.fromarray(a, "RGBA"), sh)
    out.save(OUT / f"{name}.png")
    return {"name": name, "walls": sum(1 for ty in range(H) for tx in range(W) if sc.wall(ty, tx)), "doors": len(sc.doors),
            "bands": {f"{s['orient']}{s['fixed']}": (round(((s['band'][0] + s['band'][1]) / 2 - T / 2) / T, 2) if s['band'] else None) for s in sc.segs}}

def all_names(): return sorted(p.stem for p in FLATS.glob("*.png"))

def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure"); m.add_argument("--names"); m.add_argument("--src", default=str(OUT)); m.add_argument("--out", default=str(REPORT)); m.add_argument("--overlays", action="store_true")
    f = sub.add_parser("fix"); f.add_argument("--names")
    r = sub.add_parser("restore"); r.add_argument("--names")
    args = ap.parse_args()
    names = args.names.split(",") if args.names else all_names()
    if args.cmd == "measure":
        OVERLAYS.mkdir(parents=True, exist_ok=True); res = {}
        for n in names:
            try: rr = measure_one(n, Path(args.src))
            except Exception as e:
                import traceback; traceback.print_exc(); rr = {"name": n, "error": str(e)}
            res[n] = rr
            if args.overlays:
                try: overlay_image(n, Path(args.src), OVERLAYS / f"{n}.png")
                except Exception as e: print("overlay fail", n, e)
            print(json.dumps(rr, ensure_ascii=False))
        Path(args.out).write_text(json.dumps(res, ensure_ascii=False, indent=1))
    elif args.cmd == "restore":
        for n in names:
            bak = RAW / f"prefix_{n}.png"
            if bak.exists(): shutil.copy(bak, OUT / f"{n}.png"); print("restored", n)
    else:
        RAW.mkdir(parents=True, exist_ok=True); tmpdir = RAW / "prefix_src"; tmpdir.mkdir(exist_ok=True)
        for n in names:
            bak = RAW / f"prefix_{n}.png"
            if not bak.exists(): shutil.copy(OUT / f"{n}.png", bak)   # 只备份第一次（校正前的原图）
            shutil.copy(bak, tmpdir / f"{n}.png")
            try: rr = fix_one(n, tmpdir)
            except Exception as e:
                import traceback; traceback.print_exc(); rr = {"name": n, "error": str(e)}
            print(json.dumps(rr, ensure_ascii=False))

if __name__ == "__main__":
    main()
