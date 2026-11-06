import type { Tile, Position, WorldData } from '../../types'

/**
 * 世界 v1.0 地图格式 v2（B W9：`edges` / `floors` / `access`）的宽容解析。
 * B 的字段名尚未冻结（11-07），这里按 02-map.md 的语义接几种可能的写法；拿不到的字段一律当作「没有」，不影响旧地图。
 *   edges[]  : { type: door|stairs|road, from, to, position|pos|x,y|tiles, open_hours: "09:00-18:30"|[start,end]|{start,end}, allow: [...] }
 *   floors   : tiles[].floor / tiles[].level，或 world.floors = { <arena>: 2 } / [{ arena, floor }]
 *   access   : world.access = { <arena>: { owner, locked: "09:00-18:30"|{start,end}, allow } } 或 arenas[].access
 */
export type EdgeType = 'door' | 'stairs' | 'road' | string
export interface Hours { start: string; end: string }   // "HH:MM"
export interface MapEdge {
  type: EdgeType
  from: string | null
  to: string | null
  tiles: Position[]
  openHours: Hours | null      // 开放时段（门）；null = 常开
  allow: string[] | null
  floors: [number, number] | null  // 楼梯两端楼层
}
export interface ArenaAccess { owner: string | null; lockHours: Hours | null; allow: string[] | null }
export interface MapV2 {
  edges: MapEdge[]
  floorOf: (t: Pick<Tile, 'x' | 'y' | 'arena'> | null | undefined) => number
  maxFloor: number
  access: Map<string, ArenaAccess>
  hasV2: boolean
}

type AnyRec = Record<string, unknown>
const asRec = (v: unknown): AnyRec | null => (v && typeof v === 'object' && !Array.isArray(v) ? (v as AnyRec) : null)

function parseHours(v: unknown): Hours | null {
  if (!v) return null
  if (typeof v === 'string') {
    const m = /(\d{1,2}:\d{2})\s*[-–~]\s*(\d{1,2}:\d{2})/.exec(v)
    return m ? { start: m[1].padStart(5, '0'), end: m[2].padStart(5, '0') } : null
  }
  if (Array.isArray(v) && v.length >= 2 && typeof v[0] === 'string') return { start: String(v[0]).padStart(5, '0'), end: String(v[1]).padStart(5, '0') }
  const r = asRec(v)
  if (r) {
    const s = (r.start ?? r.open ?? r.from) as string | undefined, e = (r.end ?? r.close ?? r.to) as string | undefined
    if (s && e) return { start: String(s).padStart(5, '0'), end: String(e).padStart(5, '0') }
  }
  return null
}

function parsePositions(r: AnyRec): Position[] {
  const out: Position[] = []
  const push = (p: unknown) => { const q = asRec(p); if (q && typeof q.x === 'number' && typeof q.y === 'number') out.push({ x: q.x as number, y: q.y as number }) }
  if (Array.isArray(r.tiles)) r.tiles.forEach(push)
  if (Array.isArray(r.positions)) r.positions.forEach(push)
  push(r.position); push(r.pos)
  if (typeof r.x === 'number' && typeof r.y === 'number') out.push({ x: r.x as number, y: r.y as number })
  // 楼梯两端各一格：{ a: {x,y}, b: {x,y} } / { from_pos, to_pos }
  push(r.a); push(r.b); push(r.from_pos); push(r.to_pos); push(r.from_position); push(r.to_position)
  return out
}

export function parseMapV2(world: Pick<WorldData, 'tiles'> & AnyRec): MapV2 {
  const raw = world as AnyRec
  // ── floors ──
  const arenaFloor = new Map<string, number>()
  const fl = raw.floors
  if (Array.isArray(fl)) for (const f of fl) { const r = asRec(f); if (r && typeof r.floor === 'number') for (const a of ([] as unknown[]).concat(r.arena ?? r.arenas ?? r.id ?? [])) arenaFloor.set(String(a), r.floor as number) }
  else if (asRec(fl)) for (const [k, v] of Object.entries(fl as AnyRec)) { if (typeof v === 'number') arenaFloor.set(k, v); else if (Array.isArray(v)) for (const a of v) arenaFloor.set(String(a), Number(k) || 1) }
  const tileFloor = new Map<string, number>()
  let maxFloor = 1
  for (const t of world.tiles) {
    const tr = t as unknown as AnyRec
    const f: number = typeof tr.floor === 'number' ? (tr.floor as number) : typeof tr.level === 'number' ? (tr.level as number) : ((t.arena ? arenaFloor.get(t.arena) : undefined) ?? 1)
    if (f !== 1) tileFloor.set(`${t.x},${t.y}`, f)
    if (f > maxFloor) maxFloor = f
  }
  const floorOf: MapV2['floorOf'] = (t) => (t ? (tileFloor.get(`${t.x},${t.y}`) ?? (t.arena ? arenaFloor.get(t.arena) : undefined) ?? 1) : 1)

  // ── edges ──
  const edges: MapEdge[] = []
  const rawEdges = Array.isArray(raw.edges) ? raw.edges : Array.isArray((asRec(raw.map) ?? {}).edges) ? (asRec(raw.map)!.edges as unknown[]) : []
  for (const e of rawEdges) {
    const r = asRec(e); if (!r) continue
    const tiles = parsePositions(r)
    const type = String(r.type ?? r.kind ?? 'door').toLowerCase()
    const fromA = asRec(r.from), toA = asRec(r.to)
    edges.push({
      type,
      from: typeof r.from === 'string' ? r.from : (fromA?.arena as string | undefined) ?? (r.from_arena as string | undefined) ?? null,
      to: typeof r.to === 'string' ? r.to : (toA?.arena as string | undefined) ?? (r.to_arena as string | undefined) ?? null,
      tiles,
      openHours: parseHours(r.open_hours ?? r.hours ?? r.open),
      allow: Array.isArray(r.allow) ? (r.allow as unknown[]).map(String) : null,
      floors: type === 'stairs' ? [Number((fromA?.floor as number | undefined) ?? r.from_floor ?? 1), Number((toA?.floor as number | undefined) ?? r.to_floor ?? 2)] : null,
    })
  }

  // ── access ──
  const access = new Map<string, ArenaAccess>()
  const acc = raw.access ?? raw.arena_access
  if (asRec(acc)) for (const [k, v] of Object.entries(acc as AnyRec)) {
    const r = asRec(v); if (!r) continue
    access.set(k, { owner: (r.owner as string | undefined) ?? null, lockHours: parseHours(r.locked ?? r.lock_hours ?? r.locked_hours ?? r.lock), allow: Array.isArray(r.allow) ? (r.allow as unknown[]).map(String) : null })
  }
  if (Array.isArray(raw.arenas)) for (const a of raw.arenas) {
    const r = asRec(a); const ac = r && asRec(r.access); if (!r || !ac) continue
    access.set(String(r.id ?? r.arena ?? r.name), { owner: (ac.owner as string | undefined) ?? null, lockHours: parseHours(ac.locked ?? ac.lock_hours ?? ac.lock), allow: Array.isArray(ac.allow) ? (ac.allow as unknown[]).map(String) : null })
  }

  return { edges, floorOf, maxFloor, access, hasV2: edges.length > 0 || maxFloor > 1 || access.size > 0 }
}

/** 当前游戏时刻（"HH:MM:SS"）是否在时段内；跨午夜也算 */
export function inHours(h: Hours | null, time: string | undefined): boolean {
  if (!h || !time) return true
  const t = time.slice(0, 5)
  return h.start <= h.end ? (t >= h.start && t < h.end) : (t >= h.start || t < h.end)
}
/** 门此刻是否锁着：有 open_hours 且不在时段内 */
export const edgeLockedNow = (e: MapEdge, time?: string) => e.type === 'door' && !!e.openHours && !inHours(e.openHours, time)
/** 场所此刻是否锁着（access.locked 是「锁定时段」） */
export const arenaLockedNow = (a: ArenaAccess | undefined, time?: string) => !!a?.lockHours && inHours(a.lockHours, time)

/** 场所包围盒（格） */
export function arenaBBox(tiles: Tile[], sector: string | null, arena?: string | null) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity, n = 0
  for (const t of tiles) {
    if (sector && t.sector !== sector) continue
    if (arena && t.arena !== arena) continue
    if (t.x < x0) x0 = t.x; if (t.y < y0) y0 = t.y; if (t.x > x1) x1 = t.x; if (t.y > y1) y1 = t.y; n++
  }
  return n ? { x0, y0, x1, y1, n } : null
}
export const isIndoor = (t: Pick<Tile, 'sector'> | null | undefined) => !!t?.sector && t.sector !== 'outside'
