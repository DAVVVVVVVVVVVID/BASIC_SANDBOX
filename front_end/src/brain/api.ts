/**
 * 「她的脑子」页数据源：总控的只读观察服务（8002，经 Vite 代理 /observe）。接口形状以 whale/scripts/observe_server.py 顶部注释为准。
 * 这里只读、只展示摘要与她自己的话 / 工具调用；观察服务本身不含弹幕原文。
 */
import { OBSERVE_BASE } from '../api/observe'

export interface TraceRow {
  ts: string
  tier: 'think' | 'plan' | 'shadow' | string
  phase?: string
  model?: string
  plan_id?: string | null
  plan?: string | null
  thought?: string
  tool_calls?: string
  loop_step?: number | null
  cost_usd?: number | null
  latency_ms?: number | null
  cache_hit?: boolean | null
  call_id?: string | null
}
export interface Latest {
  ts: string | null; plan?: string | null; thought?: string; action?: string | null; needs_lines?: string[]
  model?: string; cost_usd?: number | null; loop_step?: number | null; call_id?: string | null
}
export interface PromptDetail {
  call_id: string; ts: string; tier?: string; model?: string; prompt_text: string; response?: string | null
  tool_calls?: unknown; usage?: Record<string, number> | null; cost_usd?: number | null
}
export interface PlanBatch { plan_id: string; plan: string | null; first_ts: string; last_ts: string; think_calls: number; cost_usd: number; thoughts: { ts: string; text: string }[] }
export interface MemoryRow { ts?: string; type?: string; description?: string; keywords?: string[]; path?: string | null }
export interface TodayView {
  date: string; schedule_md: string | null; plans_md: string | null; plan_batches: PlanBatch[]; memories: MemoryRow[]
  dream: unknown; day_summary_md: string | null
  stats: { calls: number; think: number; plan_calls: number; cost_usd: number; memories: number; plan_batches: number }
}

async function getJson<T>(path: string, timeoutMs = 8000): Promise<T> {
  const ctrl = new AbortController()
  const timer = window.setTimeout(() => ctrl.abort(), timeoutMs)
  try {
    const res = await fetch(`${OBSERVE_BASE}${path}`, { signal: ctrl.signal, cache: 'no-store' })
    if (!res.ok) throw new Error(`${path} ${res.status}`)
    return (await res.json()) as T
  } finally { window.clearTimeout(timer) }
}

export const fetchLatest = () => getJson<Latest>('/latest')
export const fetchTraces = (date?: string, since?: string, n = 300) =>
  getJson<{ date: string; count: number; items: TraceRow[] }>(`/traces?${date ? `date=${date}&` : ''}${since ? `since=${encodeURIComponent(since)}&` : ''}n=${n}`)
export const fetchPrompt = (callId: string) => getJson<PromptDetail>(`/prompt/${encodeURIComponent(callId)}`, 15000)
export const fetchToday = (date?: string) => getJson<TodayView>(`/today${date ? `?date=${date}` : ''}`, 15000)
export const streamUrl = (date?: string) => `${OBSERVE_BASE}/stream${date ? `?date=${date}` : ''}`

/** 从 tool_calls 字串里把她 finish(reply=…) 的话抠出来；没有就返回 null */
export function replyFromToolCalls(tc?: string | null): string | null {
  if (!tc) return null
  const m = /'reply':\s*'((?:[^'\\]|\\.)*)'/.exec(tc) || /"reply":\s*"((?:[^"\\]|\\.)*)"/.exec(tc)
  return m ? m[1].replace(/\\n/g, '\n').replace(/\\'/g, "'") : null
}
/** 工具名列表 */
export function toolNames(tc?: string | null): string[] {
  if (!tc) return []
  return [...tc.matchAll(/'name':\s*'([a-z_]+)'/g)].map(m => m[1])
}
/** 记忆全文：观察服务的 memories[] 没有 path 时，用 A 的当日导出（/dataset）按描述对上 path，再从 /selfmem 读 .md */
const indexCache = new Map<string, { desc: string; time: string; file: string }[]>()
/** 读 memory/<kind>/<YYYY-MM>/MEMORY.md 索引：`- [id](events/x.md) — 描述 | 时间 | imp=5` */
async function loadMonthIndex(kind: 'events' | 'recognitions', ym: string) {
  const key = `${kind}/${ym}`
  if (indexCache.has(key)) return indexCache.get(key)!
  const out: { desc: string; time: string; file: string }[] = []
  try {
    const res = await fetch(`/selfmem/${kind}/${ym}/MEMORY.md`, { cache: 'no-store' })
    if (res.ok) {
      for (const line of (await res.text()).split('\n')) {
        const mm = /^- \[[^\]]+\]\(([^)]+)\)\s+—\s+(.*?)\s+\|\s+(\S+)\s+\|/.exec(line)
        if (mm) out.push({ file: mm[1], desc: mm[2].trim(), time: mm[3] })   // 链接相对 memory 根：events/event_000105.md（月目录里只有索引）
      }
    }
  } catch { /* ignore */ }
  indexCache.set(key, out)
  return out
}

export async function fetchMemoryText(town: string, date: string, m: MemoryRow): Promise<{ path: string | null; text: string | null }> {
  let path = m.path ?? null
  // 1) 她记忆目录自带的月索引（最新最全）：描述相同且时间相差 ≤ 2 分钟
  if (!path && m.description) {
    const kind = m.type === 'recognition' ? 'recognitions' : 'events'
    const idx = await loadMonthIndex(kind, (m.ts ?? date).slice(0, 7))
    const mt = m.ts ? Date.parse(m.ts) : NaN
    const cands = idx.filter(e => e.desc === m.description!.trim())
    const best = cands.find(e => Number.isNaN(mt) || Math.abs(Date.parse(e.time) - mt) <= 120000) ?? cands[0]
    if (best) path = best.file
  }
  // 2) A 的当日导出（有 path 字段）
  if (!path) {
    try {
      const res = await fetch(`/dataset/${encodeURIComponent(town)}/${date}/${m.type === 'recognition' ? 'recognitions' : 'events'}.jsonl`, { cache: 'no-store' })
      if (res.ok) {
        for (const line of (await res.text()).split('\n')) {
          if (!line.trim()) continue
          try {
            const r = JSON.parse(line) as { description?: string; path?: string; time?: string }
            if (r.description && m.description && r.description.trim() === m.description.trim()) { path = r.path ?? null; break }
          } catch { /* skip */ }
        }
      }
    } catch { /* ignore */ }
  }
  if (!path) return { path: null, text: null }
  try {
    const res = await fetch(`/selfmem/${path.split('/').map(encodeURIComponent).join('/')}`, { cache: 'no-store' })
    return { path, text: res.ok ? await res.text() : null }
  } catch { return { path, text: null } }
}
