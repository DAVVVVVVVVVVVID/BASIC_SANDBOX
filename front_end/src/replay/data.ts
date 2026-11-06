/**
 * 回放页数据源（E13）：全部是只读导出件 / JSONL 文件，经 Vite 的只读目录中间件取：
 *   /dataset/<town>/<date>/{manifest.json,state.jsonl,episodes.jsonl,events.jsonl}   ← A 的每日导出（schema 0.2/0.3）
 *   /sandboxdata/{actions,chat,state}/<date>.jsonl                                       ← B 的 append-only JSONL（主镇）
 * 地图几何（tiles / objects）是静态的，从 /api/world 取一次。弹幕 / 评论原文不在这些文件里（A 的导出已脱敏）。
 */
import type { Tile, GameObject, Position } from '../types'
import { API_BASE } from '../api/client'

export interface VarsSample { t: number; vars: Record<string, number>; source: 'self-history' | 'self-sample' | 'sandbox' }
export interface Episode { t0: number; t1: number; plan: string; thought: string; action: string; model?: string; cost?: number }
export interface MemEvent { t: number; type: string; description: string; importance?: number }
export interface ActionRow { t: number; entity: string; type: string; payload: Record<string, unknown>; success: boolean; label?: string | null; reason?: string | null }
export interface ChatRow { t: number; kind: string; from?: string; from_name?: string; text?: string; event?: string; room?: string }
export interface PosSample { t: number; pos: Position; player: string }

export interface ReplayData {
  town: string
  date: string
  tiles: Tile[]
  objects: GameObject[]
  vars: VarsSample[]
  episodes: Episode[]
  events: MemEvent[]
  actions: ActionRow[]
  chat: ChatRow[]
  positions: PosSample[]
  whaleIds: Set<string>
  t0: number
  t1: number
  notes: string[]
}

const parseTs = (s: unknown): number => {
  if (typeof s !== 'string' || !s) return NaN
  // 没带时区的 ISO（B 的 ts）按本机时区；带 +08:00 的按原样
  const t = Date.parse(s)
  return Number.isNaN(t) ? NaN : t
}

async function jsonl<T = Record<string, unknown>>(url: string): Promise<T[]> {
  const res = await fetch(url, { cache: 'no-store' })
  if (!res.ok) return []
  const text = await res.text()
  const out: T[] = []
  for (const line of text.split('\n')) {
    const l = line.trim()
    if (!l) continue
    try { out.push(JSON.parse(l) as T) } catch { /* skip bad line */ }
  }
  return out
}

export async function loadReplay(town: string, date: string): Promise<ReplayData> {
  const notes: string[] = []
  const ds = `/dataset/${encodeURIComponent(town)}/${date}`
  const sb = town === 'main' ? '/sandboxdata' : null

  const [world, stateA, episodesA, eventsA, actionsB, chatB, stateB] = await Promise.all([
    fetch(`${API_BASE}/world?fields=tiles,objects`).then(r => r.ok ? r.json() : { tiles: [], objects: [] }).catch(() => ({ tiles: [], objects: [] })),
    jsonl(`${ds}/state.jsonl`),
    jsonl(`${ds}/episodes.jsonl`),
    jsonl(`${ds}/events.jsonl`),
    sb ? jsonl(`${sb}/actions/${date}.jsonl`) : Promise.resolve([]),
    sb ? jsonl(`${sb}/chat/${date}.jsonl`) : Promise.resolve([]),
    sb ? jsonl(`${sb}/state/${date}.jsonl`) : Promise.resolve([]),
  ])

  const vars: VarsSample[] = []
  for (const r of stateA) {
    const t = parseTs(r.ts)
    const v = r.vars as Record<string, number> | undefined
    if (!Number.isNaN(t) && v) vars.push({ t, vars: v, source: r.kind === 'history' ? 'self-history' : 'self-sample' })
  }
  const positions: PosSample[] = []
  const whaleIds = new Set<string>()
  for (const r of stateB) {
    const t = parseTs(r.ts)
    const v = r.vars as Record<string, number> | undefined
    const pid = String(r.player_id ?? '')
    if (r.agent_id === 'whale' || /鲸/.test(pid)) whaleIds.add(pid)
    if (!Number.isNaN(t) && v && (r.agent_id === 'whale' || /鲸/.test(pid))) vars.push({ t, vars: v, source: 'sandbox' })
    if (!Number.isNaN(t) && r.position && typeof (r.position as Position).x === 'number') positions.push({ t, pos: r.position as Position, player: pid })
  }
  vars.sort((a, b) => a.t - b.t)

  const episodes: Episode[] = []
  for (const r of episodesA) {
    const w = (r.window ?? {}) as { from?: string; to?: string }
    const th = (r.think ?? {}) as Record<string, unknown>
    const t0 = parseTs(w.from ?? th.ts), t1 = parseTs(w.to ?? w.from ?? th.ts)
    if (Number.isNaN(t0)) continue
    episodes.push({
      t0, t1: Number.isNaN(t1) ? t0 + 60000 : t1,
      plan: String(r.plan ?? ''),
      thought: String(r.thought ?? r.summary ?? (th.summary as string) ?? ''),
      action: String(r.action ?? (Array.isArray(th.tool_calls) ? (th.tool_calls as string[]).join(', ') : '')),
      model: typeof th.model === 'string' ? th.model.replace(/^us\.anthropic\./, '') : undefined,
      cost: typeof th.cost_usd === 'number' ? th.cost_usd : undefined,
    })
  }
  episodes.sort((a, b) => a.t0 - b.t0)

  const events: MemEvent[] = []
  for (const r of eventsA) {
    const t = parseTs(r.time)
    if (Number.isNaN(t)) continue
    events.push({ t, type: String(r.type ?? 'event'), description: String(r.description ?? ''), importance: typeof r.importance === 'number' ? r.importance : undefined })
  }
  events.sort((a, b) => a.t - b.t)

  const actions: ActionRow[] = []
  for (const r of actionsB) {
    const t = parseTs(r.timestamp)
    if (Number.isNaN(t)) continue
    const entity = String(r.entityId ?? '')
    if (/鲸/.test(entity)) whaleIds.add(entity)
    actions.push({ t, entity, type: String(r.type ?? ''), payload: (r.payload ?? {}) as Record<string, unknown>, success: !!r.success, label: (r.label as string | null) ?? null, reason: (r.reason as string | null) ?? null })
  }
  actions.sort((a, b) => a.t - b.t)

  const chat: ChatRow[] = []
  for (const r of chatB) {
    const t = parseTs(r.ts)
    if (Number.isNaN(t)) continue
    chat.push({ t, kind: String(r.kind ?? ''), from: r.from as string | undefined, from_name: r.from_name as string | undefined, text: r.text as string | undefined, event: r.event as string | undefined, room: r.room_id as string | undefined })
  }
  chat.sort((a, b) => a.t - b.t)

  if (positions.length === 0) notes.push('没有 state 位置样本（后端 W6 前的数据）：位置按行动日志近似推算')
  if (vars.length === 0) notes.push('没有七变量样本')
  if (episodes.length === 0) notes.push('没有 episodes（思考）')

  const all = [...vars.map(v => v.t), ...episodes.map(e => e.t0), ...events.map(e => e.t), ...actions.map(a => a.t), ...chat.map(c => c.t), ...positions.map(p => p.t)]
  const dayStart = Date.parse(`${date}T00:00:00+08:00`)
  const dayEnd = dayStart + 86400000
  const inDay = all.filter(t => t >= dayStart - 3600000 && t <= dayEnd + 3600000)
  const t0 = inDay.length ? Math.min(...inDay) : dayStart
  const t1 = inDay.length ? Math.max(...inDay) : dayEnd

  return { town, date, tiles: world.tiles ?? [], objects: world.objects ?? [], vars, episodes, events, actions, chat, positions, whaleIds, t0, t1: Math.max(t1, t0 + 60000), notes }
}

/** 行动日志推算位置轨迹（没有 state 位置样本时）：move / move_n 按方向位移，move_to_area 到区域质心 */
export function approximateTrack(d: ReplayData, start: Position): PosSample[] {
  if (d.positions.length > 0) return d.positions.filter(p => d.whaleIds.has(p.player))
  const walkable = new Set(d.tiles.filter(t => t.walkable).map(t => `${t.x},${t.y}`))
  const cent = new Map<string, { sx: number; sy: number; n: number; pts: Position[] }>()
  for (const t of d.tiles) {
    if (!t.arena || !t.walkable) continue
    const c = cent.get(t.arena) ?? { sx: 0, sy: 0, n: 0, pts: [] }
    c.sx += t.x; c.sy += t.y; c.n++; c.pts.push({ x: t.x, y: t.y })
    cent.set(t.arena, c)
  }
  const DELTA: Record<string, Position> = { up: { x: 0, y: -1 }, down: { x: 0, y: 1 }, left: { x: -1, y: 0 }, right: { x: 1, y: 0 } }
  let pos = { ...start }
  const out: PosSample[] = []
  for (const a of d.actions) {
    if (!d.whaleIds.has(a.entity) || !a.success) continue
    if (a.type === 'move' || a.type === 'move_n') {
      const dir = String(a.payload.direction ?? '')
      const steps = a.type === 'move_n' ? Number(a.payload.steps ?? 1) : 1
      const dlt = DELTA[dir]
      if (!dlt) continue
      for (let i = 0; i < steps; i++) {
        const nx = { x: pos.x + dlt.x, y: pos.y + dlt.y }
        if (!walkable.has(`${nx.x},${nx.y}`)) break
        pos = nx
      }
      out.push({ t: a.t, pos: { ...pos }, player: a.entity })
    } else if (a.type === 'move_to_area') {
      const c = cent.get(String(a.payload.area_id ?? ''))
      if (c) {
        const cx = c.sx / c.n, cy = c.sy / c.n
        let best = c.pts[0]
        for (const p of c.pts) if (Math.hypot(p.x - cx, p.y - cy) < Math.hypot(best.x - cx, best.y - cy)) best = p
        pos = { ...best }
        out.push({ t: a.t, pos: { ...pos }, player: a.entity })
      }
    }
  }
  return out
}
