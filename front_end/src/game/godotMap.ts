/**
 * Godot 呈现层地图管线在 Phaser 侧的纯逻辑（11-14 总控：5173 画面同步成 Godot 的）。
 * 移植自 whale-godot/scripts/MapRenderer.gd + AssetLib.gd：
 *   tiles[] 的 type + arena → 语义名（assets/map_rules.json）→ 图集格（tiles/<preset>.json 的 index / variants，本套没有回落 fallback 套）
 *   自动拼接：8 邻格掩码（Tiled wang 顺序）→ blob 表；base / overlay / object_overlays / 墙立面下半（face_b）
 * 不依赖 Phaser，便于单测。
 */
import type { Tile, GameObject } from '../types'

export interface TilesMeta {
  image: string
  tile: number
  columns: number
  filter?: string
  fallback?: string
  index: Record<string, number>
  variants?: Record<string, string[]>
  base?: Record<string, string>
  autotile?: AutotileRule[]
  overlay?: Record<string, string[]>
  object_overlays?: { object_type: string; size: number; cells: string[][] }[]
}
export interface AutotileRule { name?: string; layer?: 'ground' | 'overlay'; apply_to: string[]; same?: string[]; only_near?: string[]; blob: Record<string, string[]> }
export type MapRules = Record<string, unknown>
export interface Cell { x: number; y: number; src: 'main' | 'fb'; idx: number }
export interface ObjectsMeta { tile_px?: number; items: Record<string, ObjectEntry>; alias?: Record<string, string> }
export interface ObjectEntry { image: string; footprint?: [number, number]; px_per_tile?: number; tile_px?: number; filter?: string; size?: [number, number]; variants?: string[]; key?: string }

type Rec = Record<string, unknown>
const asRec = (v: unknown): Rec | null => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Rec) : null)

/** 同 AssetLib._hash（64 位整数异或后取 abs % 1000003）：变体 / 撒点选择与 Godot 画面一致 */
export function godotHash(x: number, y: number, salt: number): number {
  const xor64 = (a: number, b: number) => {
    const hi = (Math.floor(a / 4294967296) ^ Math.floor(b / 4294967296)) >>> 0
    const lo = ((a >>> 0) ^ (b >>> 0)) >>> 0
    return hi * 4294967296 + lo
  }
  const h = xor64(xor64(x * 73856093, y * 19349663), salt * 83492791)
  return Math.abs(h) % 1000003
}

export const isIndoorTile = (t: Pick<Tile, 'sector'> | null | undefined) => !!t?.sector && t.sector !== 'outside'

const regexCache = new Map<string, RegExp>()
const re = (p: string) => { let r = regexCache.get(p); if (!r) { r = new RegExp(p); regexCache.set(p, r) } return r }

function resolve(rule: unknown, t: Tile, arena: string): string {
  if (typeof rule === 'string') return rule
  const r = asRec(rule)
  if (!r) return 'grass'
  if ('sprinkle' in r) {
    const pct = Number(r.sprinkle_pct ?? 5)
    return godotHash(t.x, t.y, 1) % 100 < pct ? String(r.sprinkle) : String(r.base)
  }
  const byArena = asRec(r.by_arena_regex)
  if (byArena) {
    for (const [pat, v] of Object.entries(byArena)) if (re(pat).test(arena)) return String(v)
    return String(r.default ?? 'grass')
  }
  return String(r.base ?? r.default ?? 'grass')
}

/** 同 MapRenderer.pick：一格的语义名 */
export function pickSemantic(rules: MapRules, t: Tile, below: Tile | undefined): string {
  const type = String(t.type ?? '')
  const arena = t.arena ?? ''
  if ((type === 'object' || type === 'floor_occupied') && arena === '' && !isIndoorTile(t)) return 'grass'
  const ov = asRec(rules.arena_override) ?? {}
  if (type !== 'water' && type !== 'wall' && arena in ov) return resolve(ov[arena], t, arena)
  const by = asRec(rules.by_type) ?? {}
  if (type in by) {
    const r = by[type]
    const rr = asRec(r)
    if (type === 'wall' && rr) {
      const belowType = below ? String(below.type ?? '') : ''
      const base = (!below || belowType !== 'wall') ? String(rr.face ?? 'wall_face') : String(rr.top ?? 'wall_top')
      const styles = asRec(rr.style_by_arena_regex)
      if (styles) {
        let style = String(rr.style_default ?? 'wainscot')
        for (const [pat, v] of Object.entries(styles)) if (re(pat).test(arena)) { style = String(v); break }
        return `${base}_${style}`
      }
      return base
    }
    if (typeof r === 'string' && r in by && r !== type) return resolve(by[r], t, arena)
    return resolve(r, t, arena)
  }
  return resolve(by._default ?? 'grass', t, arena)
}

/** 8 邻格掩码（上、右上、右、右下、下、左下、左、左上），地图外算同类；角位要两侧边都为 1 */
export function mask8(semOf: Map<string, string>, x: number, y: number, same: string[]): string {
  const dirs = [[0, -1], [1, -1], [1, 0], [1, 1], [0, 1], [-1, 1], [-1, 0], [-1, -1]]
  const bits = dirs.map(([dx, dy]) => { const s = semOf.get(`${x + dx},${y + dy}`); return s === undefined || same.includes(s) ? 1 : 0 })
  for (const i of [1, 3, 5, 7]) if (bits[(i + 7) % 8] === 0 || bits[(i + 1) % 8] === 0) bits[i] = 0
  return bits.join('')
}
export function near8(semOf: Map<string, string>, x: number, y: number, what: string[]): boolean {
  for (const dx of [-1, 0, 1]) for (const dy of [-1, 0, 1]) {
    if (dx === 0 && dy === 0) continue
    const s = semOf.get(`${x + dx},${y + dy}`)
    if (s !== undefined && what.includes(s)) return true
  }
  return false
}
/** 掩码 → 候选格名；没有精确项时逐步抹掉角位，再退到全同类格 */
export function blobPick(blob: Record<string, string[]>, mask: string): string[] {
  if (blob[mask]) return blob[mask]
  let m = mask
  for (const i of [1, 3, 5, 7]) {
    if (m[i] === '1') {
      m = m.slice(0, i) + '0' + m.slice(i + 1)
      if (blob[m]) return blob[m]
    }
  }
  return blob['11111111'] ?? []
}

/** 语义名 / 变体组 / 格名 → 图集序号；-1 = 没有 */
export function lookupIndex(meta: TilesMeta, semantic: string, x: number, y: number): number {
  let name = semantic
  const vs = meta.variants?.[semantic]
  if (vs && vs.length) name = vs[godotHash(x, y, 7) % vs.length]
  const i = meta.index[name]
  return typeof i === 'number' ? i : -1
}
export function tileCell(main: TilesMeta, fb: TilesMeta | null, semantic: string, x: number, y: number): Cell | null {
  let i = lookupIndex(main, semantic, x, y)
  if (i >= 0) return { x, y, src: 'main', idx: i }
  if (fb) { i = lookupIndex(fb, semantic, x, y); if (i >= 0) return { x, y, src: 'fb', idx: i } }
  return null
}

export interface EdgeLike { id?: string; kind?: string; type?: string; a?: { x: number; y: number }; b?: { x: number; y: number } }
export interface LayerCells { ground: Cell[]; overlay: Cell[]; structures: Cell[] }
export interface MapPlan {
  ground: Cell[]
  overlay: Cell[]
  structures: Cell[]
  /** focus-only 层（③）：floor ≠ 1 的另置画布 / 有外观贴图的楼——只在取景到该 key 时显示；底层这些格铺草 */
  focusLayers: Map<string, LayerCells>
  /** door_id → 内侧格（开关态换 door / door_open） */
  doors: Map<string, { x: number; y: number }>
  semOf: Map<string, string>
  missing: Record<string, number>
}

/** 同 MapRenderer.rebuild 的瓦片部分（不含屋顶 / focus-only 层 / 细墙；那些由 ③④ 处理）。edges 用后端原始 {kind, a, b} */
export interface PlanOpts {
  /** 格 → 取景 key（"" = 室外）；缺省全部画在底层 */
  keyOf?: (t: Tile | undefined) => string
  /** 该 key 的瓦片是否只在取景时显示（floor ≠ 1 或有外观贴图） */
  hidden?: (key: string) => boolean
}
export function planMap(tiles: Tile[], objects: GameObject[], edges: EdgeLike[], rules: MapRules, main: TilesMeta, fb: TilesMeta | null, opts: PlanOpts = {}): MapPlan {
  const byKey = new Map<string, Tile>()
  for (const t of tiles) byKey.set(`${t.x},${t.y}`, t)
  const semOf = new Map<string, string>()
  for (const t of tiles) semOf.set(`${t.x},${t.y}`, pickSemantic(rules, t, byKey.get(`${t.x},${t.y + 1}`)))
  const baseMap = main.base ?? {}
  const autoRules = main.autotile ?? []
  const overlayMap = main.overlay ?? {}
  const base: LayerCells = { ground: [], overlay: [], structures: [] }
  const focusLayers = new Map<string, LayerCells>()
  const layerFor = (key: string): LayerCells => { let l = focusLayers.get(key); if (!l) { l = { ground: [], overlay: [], structures: [] }; focusLayers.set(key, l) } return l }
  const keyOf = opts.keyOf ?? (() => '')
  const hiddenKey = (k: string) => k !== '' && !!opts.hidden && opts.hidden(k)
  const overlayTaken = new Set<string>()
  const missing: Record<string, number> = {}
  const put = (arr: Cell[], c: Cell | null) => { if (c) arr.push(c) }
  const putOverlay = (c: Cell | null) => { if (c) { base.overlay.push(c); overlayTaken.add(`${c.x},${c.y}`) } }
  const { ground, structures } = base
  for (const t of tiles) {
    const x = t.x, y = t.y
    const sem = semOf.get(`${x},${y}`)!
    const key = keyOf(t)
    const hide = hiddenKey(key)
    const target = hide ? layerFor(key) : base
    if (hide) put(ground, tileCell(main, fb, 'grass', x, y))   // 底下铺草：另置画布全景不留洞；外观图有透明像素也不露底
    let placedGround = false
    for (const r of autoRules) {
      if (!r.apply_to.includes(sem)) continue
      const nearList = r.only_near ?? []
      if (nearList.length && !near8(semOf, x, y, nearList)) continue
      const names = blobPick(r.blob, mask8(semOf, x, y, r.same ?? r.apply_to))
      if (!names.length) continue
      const cell = tileCell(main, fb, names[godotHash(x, y, 7) % names.length], x, y)
      if (!cell) continue
      if ((r.layer ?? 'overlay') === 'overlay') putOverlay(cell)   // 自动拼接覆盖层（路 / 水）只在室外，一律底层
      else { target.ground.push(cell); placedGround = true }
    }
    if (!placedGround) {
      const gsem = String(baseMap[sem] ?? sem)
      let c = tileCell(main, fb, gsem, x, y)
      if (!c && gsem.startsWith('wall_')) c = tileCell(main, fb, gsem.startsWith('wall_face') ? 'wall_face' : 'wall_top', x, y)
      if (!c && gsem.startsWith('floor_')) c = tileCell(main, fb, 'floor_wood', x, y)
      if (!c) { missing[gsem] = (missing[gsem] ?? 0) + 1; c = tileCell(main, fb, 'grass', x, y) }
      put(target.ground, c)
    }
    // 墙立面下半压到下一格（室内地板）的覆盖层；下一格的楼若是 focus-only，就进它的层
    if (sem.startsWith('wall_face_')) {
      const below = byKey.get(`${x},${y + 1}`)
      if (below && isIndoorTile(below) && String(below.type) !== 'wall') {
        const bc = tileCell(main, fb, 'wall_face_b_' + sem.slice('wall_face_'.length), x, y)
        if (bc) { const bk = keyOf(below); if (hiddenKey(bk)) layerFor(bk).overlay.push({ ...bc, x, y: y + 1 }); else putOverlay({ ...bc, x, y: y + 1 }) }
      }
    }
    // 覆盖层点缀（花丛）：自动拼接没占这格才放
    const vs = overlayMap[sem]
    if (vs && vs.length && !overlayTaken.has(`${x},${y}`) && !hide) putOverlay(tileCell(main, fb, vs[godotHash(x, y, 13) % vs.length], x, y))
  }
  // 物品周围拼花（喷泉 4×4 拼花）
  for (const rule of main.object_overlays ?? []) {
    const n = rule.size ?? 4
    for (const o of objects) {
      if (o.type !== rule.object_type) continue
      const ts = o.tiles && o.tiles.length ? o.tiles : [o.position]
      const x0 = Math.min(...ts.map(p => p.x)), x1 = Math.max(...ts.map(p => p.x)), y0 = Math.min(...ts.map(p => p.y)), y1 = Math.max(...ts.map(p => p.y))
      const ox = Math.floor((x0 + x1 + 1) * 0.5 - n * 0.5), oy = Math.floor((y0 + y1 + 1) * 0.5 - n * 0.5)
      for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) {
        const name = rule.cells[j]?.[i]
        if (name) putOverlay(tileCell(main, fb, name, ox + i, oy + j))
      }
    }
  }
  // 门 / 楼梯（a 外侧、b 内侧 → 画在 b）
  const st = asRec(rules.structures) ?? {}
  const doors = new Map<string, { x: number; y: number }>()
  for (const e of edges) {
    const kind = String(e.kind ?? e.type ?? 'door')
    const sem2 = st[kind]
    const b = e.b
    if (sem2 == null || !b || typeof b.x !== 'number') continue
    const ck = keyOf(byKey.get(`${b.x},${b.y}`))
    put(hiddenKey(ck) ? layerFor(ck).structures : structures, tileCell(main, fb, String(sem2), b.x, b.y))
    if (kind === 'door' && e.id) doors.set(String(e.id), { x: b.x, y: b.y })
  }
  return { ground, overlay: base.overlay, structures, focusLayers, doors, semOf, missing }
}

// ── 物品 ──────────────────────────────────────────────────────────────────────
/** 同 AssetLib.object_entry：别名 → 去数字后缀 → 再别名 */
export function objectEntry(meta: ObjectsMeta, type: string): ObjectEntry | null {
  const items = meta.items ?? {}, alias = meta.alias ?? {}
  let t = type
  if (!(t in items) && t in alias) t = alias[t]
  if (!(t in items)) {
    const stripped = t.replace(/[0-9]+$/, '').replace(/_+$/, '')
    if (stripped in items) t = stripped
    else if (stripped in alias) t = alias[stripped]
  }
  if (!(t in items)) return null
  return { ...items[t], key: t }
}
/** 有 variants[] 时按格位哈希挑一张 */
export function objectImage(e: ObjectEntry, x: number, y: number): string {
  const vs = e.variants
  if (vs && vs.length) return vs[godotHash(x, y, 11) % vs.length]
  return e.image
}
export const objectPxPerTile = (meta: ObjectsMeta, e: ObjectEntry) => Number(e.px_per_tile ?? e.tile_px ?? meta.tile_px ?? 96)
/** 预设叠加（manifest.<preset>.json）：items / alias 覆盖同名项 */
export function mergeObjectsMeta(base: ObjectsMeta, over: Partial<ObjectsMeta> | null): ObjectsMeta {
  if (!over) return base
  return { ...base, items: { ...base.items, ...(over.items ?? {}) }, alias: { ...(base.alias ?? {}), ...(over.alias ?? {}) } }
}

// ── 取景 key / 建筑占地 / 外观布局（移植 Focus.gd + BuildingsLayer.gd） ──────────────────────────
/** 室外 arena（校园 / 街道 / 广场 / 公园 / 码头 / 水）即使 sector 不是 outside 也不算室内 */
export const OUTDOOR_ARENAS = ['campus', 'street', 'lane', 'road', 'square', 'park', 'dock', 'water', 'grass']
/** 一个 sector 里多栋楼（大学）按 arena 拆 */
export const SPLIT_BY_ARENA = ['university']
/** 同 Focus.key_of_tile："<sector>|<floor>"（大学 "university:<arena>|<floor>"）；室外 "" */
export function focusKeyOf(t: Tile | undefined, floorOf: (t: Tile) => number): string {
  if (!t || !isIndoorTile(t)) return ''
  if (t.arena && OUTDOOR_ARENAS.includes(t.arena)) return ''
  if (['grass', 'grass1', 'water'].includes(String(t.type))) return ''
  let sector = String(t.sector)
  if (SPLIT_BY_ARENA.includes(sector) && t.arena) sector = `${sector}:${t.arena}`
  return `${sector}|${floorOf(t)}`
}
export const floorOfKey = (key: string) => { const p = key.split('|'); return p.length > 1 ? Number(p[1]) || 1 : 1 }
/** Godot key ↔ 5173 原有 roofedSectors 键（"sector|floor"，大学按 arena："classroom|1"） */
export const phaserKeyOf = (godotKey: string) => godotKey.includes(':') ? godotKey.split(':')[1] : godotKey

export interface BuildingBox { key: string; x0: number; y0: number; x1: number; y1: number; doors: { x: number; y: number }[]; id: string }
/** 同 MapRenderer.rebuild 的 v1.2 分支：map.buildings[] → key → 占地盒（key 取占地内第一块室内格） */
export function buildingBoxes(buildings: { id: string; footprint: { x: number; y: number; w: number; h: number }; doors: { cell: { x: number; y: number } }[] }[], tileAt: (x: number, y: number) => Tile | undefined, keyOf: (t: Tile | undefined) => string): BuildingBox[] {
  const out: BuildingBox[] = []
  for (const b of buildings) {
    const { x, y, w, h } = b.footprint
    let key = ''
    outer: for (let yy = y; yy < y + h; yy++) for (let xx = x; xx < x + w; xx++) { key = keyOf(tileAt(xx, yy)); if (key) break outer }
    if (!key) continue
    out.push({ key, x0: x, y0: y, x1: x + w - 1, y1: y + h - 1, doors: b.doors.map(d => ({ x: d.cell.x, y: d.cell.y })), id: b.id })
  }
  return out
}

export interface BuildingsManifest { buildings: Record<string, { keys: string[]; anchor?: string | string[] }> }
export interface BuildingSpec { image: string; night_image?: string; fit?: 'none' | 'width' | 'stretch'; roof_extra_px?: number; px_per_tile?: number; filter?: string; door_px?: number[]; backing?: string }
/** 同 AssetLib.building_for_names：key / id 任一命中 manifest 的 keys */
export function buildingForNames(m: BuildingsManifest, names: (string | null | undefined)[]): { id: string; keys: string[]; anchors: string[] } | null {
  for (const n of names) {
    if (!n) continue
    for (const [id, e] of Object.entries(m.buildings ?? {})) {
      const keys = e.keys ?? []
      if (keys.includes(n)) { const anc = e.anchor ?? keys[0]; return { id, keys, anchors: Array.isArray(anc) ? anc : [anc] } }
    }
  }
  return null
}
export function hasFacadeAnchor(m: BuildingsManifest, key: string, id = ''): boolean {
  const e = buildingForNames(m, [key, id]); if (!e) return false
  return e.anchors.some(a => a === key || (id !== '' && a === id))
}

export interface FacadeLayout { sx: number; sy: number; w: number; h: number; cx: number; bottom: number; shift: number; clipL: number; clipR: number; W: number; H: number }
/** 同 BuildingsLayer.rebuild 的几何：fit、门对齐（≤ 余量）、相邻列有物品就裁掉那一侧余量 */
export function facadeLayout(spec: BuildingSpec, b: BuildingBox, texW: number, texH: number, T: number, columnHasObject: (x: number, y0: number, y1: number) => boolean): FacadeLayout {
  const W = b.x1 - b.x0 + 1, H = b.y1 - b.y0 + 1
  const fit = spec.fit ?? 'none'
  let sx = 1, sy = 1
  if (fit === 'width' || fit === 'stretch') { sx = W * T / texW; sy = sx; if (fit === 'stretch') sy = (H * T + (spec.roof_extra_px ?? T)) / texH }
  else { sx = T / (spec.px_per_tile ?? T); sy = sx }
  const w = texW * sx, h = texH * sy
  const cx = (b.x0 + W * 0.5) * T, bottom = (b.y1 + 1) * T
  let shift = 0
  const dpx = spec.door_px
  if (dpx && dpx.length && b.doors.length && b.doors[0].y === b.y1) {
    const ours = (b.doors[0].x + 0.5) * T, theirs = cx - w * 0.5 + dpx[0] * sx
    const margin = Math.max(0, (w - W * T) * 0.5)
    shift = Math.max(-margin, Math.min(margin, ours - theirs))
  }
  const marginPx = Math.max(0, (w - W * T) * 0.5)
  let clipL = 0, clipR = 0
  if (marginPx > 0) {
    if (columnHasObject(b.x0 - 1, b.y0, b.y1)) clipL = marginPx
    if (columnHasObject(b.x1 + 1, b.y0, b.y1)) clipR = marginPx
    if (clipL > 0 || clipR > 0) { const m2 = Math.max(0, marginPx - Math.max(clipL, clipR)); shift = Math.max(-m2, Math.min(m2, shift)) }
  }
  return { sx, sy, w, h, cx, bottom, shift, clipL, clipR, W, H }
}

/** 同 State.night_factor：17:30 起淡入、19:30 全亮，05:00 起淡出、06:30 全灭 */
export function nightFactor(time: string | undefined): number {
  if (!time || time.length < 5) return 0
  const h = Number(time.slice(0, 2)) + Number(time.slice(3, 5)) / 60
  if (h >= 19.5 || h < 5) return 1
  if (h >= 17.5) return (h - 17.5) / 2
  if (h < 6.5) return 1 - (h - 5) / 1.5
  return 0
}
