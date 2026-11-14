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
export interface MapPlan {
  ground: Cell[]
  overlay: Cell[]
  structures: Cell[]
  /** door_id → 内侧格（开关态换 door / door_open） */
  doors: Map<string, { x: number; y: number }>
  semOf: Map<string, string>
  missing: Record<string, number>
}

/** 同 MapRenderer.rebuild 的瓦片部分（不含屋顶 / focus-only 层 / 细墙；那些由 ③④ 处理）。edges 用后端原始 {kind, a, b} */
export function planMap(tiles: Tile[], objects: GameObject[], edges: EdgeLike[], rules: MapRules, main: TilesMeta, fb: TilesMeta | null): MapPlan {
  const byKey = new Map<string, Tile>()
  for (const t of tiles) byKey.set(`${t.x},${t.y}`, t)
  const semOf = new Map<string, string>()
  for (const t of tiles) semOf.set(`${t.x},${t.y}`, pickSemantic(rules, t, byKey.get(`${t.x},${t.y + 1}`)))
  const baseMap = main.base ?? {}
  const autoRules = main.autotile ?? []
  const overlayMap = main.overlay ?? {}
  const ground: Cell[] = [], overlay: Cell[] = [], structures: Cell[] = []
  const overlayTaken = new Set<string>()
  const missing: Record<string, number> = {}
  const put = (arr: Cell[], c: Cell | null) => { if (c) arr.push(c) }
  const putOverlay = (c: Cell | null) => { if (c) { overlay.push(c); overlayTaken.add(`${c.x},${c.y}`) } }
  for (const t of tiles) {
    const x = t.x, y = t.y
    const sem = semOf.get(`${x},${y}`)!
    let placedGround = false
    for (const r of autoRules) {
      if (!r.apply_to.includes(sem)) continue
      const nearList = r.only_near ?? []
      if (nearList.length && !near8(semOf, x, y, nearList)) continue
      const names = blobPick(r.blob, mask8(semOf, x, y, r.same ?? r.apply_to))
      if (!names.length) continue
      const cell = tileCell(main, fb, names[godotHash(x, y, 7) % names.length], x, y)
      if (!cell) continue
      if ((r.layer ?? 'overlay') === 'overlay') putOverlay(cell)
      else { ground.push(cell); placedGround = true }
    }
    if (!placedGround) {
      const gsem = String(baseMap[sem] ?? sem)
      let c = tileCell(main, fb, gsem, x, y)
      if (!c && gsem.startsWith('wall_')) c = tileCell(main, fb, gsem.startsWith('wall_face') ? 'wall_face' : 'wall_top', x, y)
      if (!c && gsem.startsWith('floor_')) c = tileCell(main, fb, 'floor_wood', x, y)
      if (!c) { missing[gsem] = (missing[gsem] ?? 0) + 1; c = tileCell(main, fb, 'grass', x, y) }
      put(ground, c)
    }
    // 墙立面下半压到下一格（室内地板）的覆盖层
    if (sem.startsWith('wall_face_')) {
      const below = byKey.get(`${x},${y + 1}`)
      if (below && isIndoorTile(below) && String(below.type) !== 'wall') {
        const bc = tileCell(main, fb, 'wall_face_b_' + sem.slice('wall_face_'.length), x, y)
        if (bc) putOverlay({ ...bc, x, y: y + 1 })
      }
    }
    // 覆盖层点缀（花丛）：自动拼接没占这格才放
    const vs = overlayMap[sem]
    if (vs && vs.length && !overlayTaken.has(`${x},${y}`)) putOverlay(tileCell(main, fb, vs[godotHash(x, y, 13) % vs.length], x, y))
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
    put(structures, tileCell(main, fb, String(sem2), b.x, b.y))
    if (kind === 'door' && e.id) doors.set(String(e.id), { x: b.x, y: b.y })
  }
  return { ground, overlay, structures, doors, semOf, missing }
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
