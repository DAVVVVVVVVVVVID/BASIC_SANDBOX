
/** C 的只读观察面板（W4 第 0 项）：GET /observe/latest → { plan, thought, action, needs_lines, ts } */
export interface ObserveLatest {
  plan?: string | null
  thought?: string | null
  action?: string | null
  needs_lines?: string[] | string | null
  ts?: string | number | null
}

export const OBSERVE_BASE: string = (import.meta.env.VITE_OBSERVE_BASE ?? '/observe').replace(/\/$/, '')

/**
 * 只取摘要字段。弹幕 / 评论原文永不上屏（§4.3）：这里显式只挑 thought / needs_lines / ts，
 * 其余字段（将来若有 raw、danmaku、comments 等）一律丢弃。
 */
export async function fetchObserveLatest(): Promise<{ thought: string; needs: string[]; ts: string } | null> {
  const ctrl = new AbortController()
  const timer = window.setTimeout(() => ctrl.abort(), 3000)
  let raw: ObserveLatest
  try {
    const res = await fetch(`${OBSERVE_BASE}/latest`, { signal: ctrl.signal, cache: 'no-store' })
    if (!res.ok) return null
    raw = (await res.json()) as ObserveLatest
  } finally { window.clearTimeout(timer) }
  if (!raw || typeof raw !== 'object') return null
  const thought = typeof raw.thought === 'string' ? raw.thought.trim() : ''
  const needsRaw = raw.needs_lines
  const needs = Array.isArray(needsRaw) ? needsRaw.filter((x): x is string => typeof x === 'string')
    : typeof needsRaw === 'string' && needsRaw ? [needsRaw] : []
  return { thought, needs, ts: String(raw.ts ?? '') }
}
