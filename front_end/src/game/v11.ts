/**
 * world-v1.1（B 11-13 字段表）显示用纯函数：进食 / 下厨进度插值、冰箱内容、柜台今日供应、每日上限、房租。无 Phaser 依赖，单测 `tests/v11.test.ts`。
 * 游戏时间字段都是带日期的 ISO（+08:00），用 worldState.date + time 拼出「现在」做插值。
 */
import type { BusyState, DailyUse, GameObject, RentInfo, WorldState } from '../types'
import { itemMeta } from './items'

/** 游戏「现在」的毫秒数（按 +08:00 拼 date + time）；缺字段返回 null */
export function gameNowMs(ws: Pick<WorldState, 'date' | 'time'> | null | undefined): number | null {
  if (!ws?.date || !ws?.time) return null
  const t = ws.time.length === 5 ? `${ws.time}:00` : ws.time
  const ms = Date.parse(`${ws.date}T${t}+08:00`)
  return Number.isFinite(ms) ? ms : null
}
export const parseGameTime = (iso: string | null | undefined): number | null => { if (!iso) return null; const ms = Date.parse(iso); return Number.isFinite(ms) ? ms : null }

export interface Progress { progress: number; remainingS: number; totalS: number }
/** 按 started_at / ends_at 对「现在」插值；没有时间字段就用快照里的 progress / remaining_s */
export function busyProgress(b: BusyState | null | undefined, nowMs: number | null): Progress | null {
  if (!b) return null
  const s = parseGameTime(b.started_at), e = parseGameTime(b.ends_at)
  if (s !== null && e !== null && e > s && nowMs !== null) {
    const total = (e - s) / 1000, done = Math.min(total, Math.max(0, (nowMs - s) / 1000))
    return { progress: done / total, remainingS: total - done, totalS: total }
  }
  const p = typeof b.progress === 'number' ? Math.max(0, Math.min(1, b.progress)) : 0
  const rem = typeof b.remaining_s === 'number' ? b.remaining_s : 0
  const total = p < 1 && rem > 0 ? rem / (1 - p) : rem
  return { progress: p, remainingS: rem, totalS: total }
}
export const fmtMin = (s: number) => { const m = Math.ceil(s / 60); return m >= 60 ? `${Math.floor(m / 60)} 小时${m % 60 ? ` ${m % 60} 分` : ''}` : `${m} 分钟` }
export const gainText = (gain: Record<string, number> | null | undefined) => {
  if (!gain) return ''
  const names: Record<string, string> = { fullness: '饱腹', energy: '精力', social: '社交', fun: '乐趣', mood: '心情' }
  return Object.entries(gain).filter(([, v]) => typeof v === 'number' && v !== 0).map(([k, v]) => `${names[k] ?? k} ${v > 0 ? '+' : ''}${v}`).join(' ')
}
/** 「🍴 家常菜 · 剩 9 分钟 · 饱腹 +40」 */
export function busyText(b: BusyState | null | undefined, nowMs: number | null): string | null {
  if (!b) return null
  const pr = busyProgress(b, nowMs)
  const m = itemMeta(b.item ?? undefined)
  const verb = b.kind === 'eating' ? `🍴 吃${m.label}` : b.kind === 'cooking' ? `🍳 做${m.label}` : b.kind === 'burning' ? '🔥 烧着' : `⏳ ${b.kind}`
  const rem = pr && pr.remainingS > 0 ? ` · 剩 ${fmtMin(pr.remainingS)}` : ''
  const g = gainText(b.gain)
  return `${verb}${rem}${g ? ` · ${g}` : ''}`
}

/** 冰箱一行：「🍲 家常菜 ×4 · 剩 2 天」/ 坏了 */
export interface FridgeRow { item: string; name: string; count: number; days: number | null; spoiled: boolean; icon: string }
export function fridgeRows(o: Pick<GameObject, 'contents'> | null | undefined, nowMs: number | null): FridgeRow[] {
  const list = o?.contents ?? []
  return list.map(c => {
    const m = itemMeta(c.item, (c as { name?: string }).name)
    let days: number | null = typeof c.expires_in_days === 'number' ? c.expires_in_days : null
    const ex = parseGameTime(c.expires_at)
    if (ex !== null && nowMs !== null) days = Math.max(0, Math.ceil((ex - nowMs) / 86_400_000 * 10) / 10)
    return { item: c.item, name: (c as { name?: string }).name ?? m.label, count: c.count, days, spoiled: !!c.spoiled || m.spoiled === true, icon: m.icon }
  })
}
export const fridgeTitle = (o: Pick<GameObject, 'name' | 'storage'>) => `🧊 ${o.name}${o.storage ? ` ${o.storage.used}/${o.storage.capacity}` : ''}`

/** 柜台 / 鱼摊：「今日 12 · 剩 7」（stock = 今日剩余；没 daily_supply 就只给剩余） */
export function supplyText(o: Pick<GameObject, 'daily_supply' | 'stock' | 'restock_at'>, item: string): string | null {
  const sup = o.daily_supply?.[item], left = o.stock?.[item]
  if (typeof sup !== 'number' && typeof left !== 'number') return null
  if (typeof sup === 'number' && typeof left === 'number') return left <= 0 ? `今日 ${sup} · 卖完${o.restock_at ? `（${o.restock_at} 上新）` : ''}` : `今日 ${sup} · 剩 ${left}`
  return typeof left === 'number' ? (left <= 0 ? '卖完' : `剩 ${left}`) : `今日 ${sup}`
}

/** 每日上限：「🖥 电脑 3.5/6 h」… 只列有用过或已到上限的 */
export const WORK_NAMES: Record<string, string> = { pc: '电脑', pc_desk: '电脑', pc_music: '琴房电脑', stream_desk: '直播台', fishing_spot: '钓位', phone: '手机', game_console: '游戏机', tv: '电视', sofa_tv: '电视', piano: '钢琴', stove: '灶台' }
const WORK_ICON: Record<string, string> = { pc: '🖥', pc_desk: '🖥', pc_music: '🎹', stream_desk: '📺', fishing_spot: '🎣', phone: '📱', game_console: '🎮', tv: '📺', sofa_tv: '📺', piano: '🎹', stove: '🍳' }
const hrs = (min: number) => { const h = min / 60; return Number.isInteger(h) ? `${h}` : h.toFixed(1).replace(/\.0$/, '') }
export function dailyUseLines(du: DailyUse | null | undefined, all = false): { key: string; text: string; full: boolean }[] {
  if (!du) return []
  return Object.entries(du).filter(([, v]) => v && (all || v.used_min > 0 || v.used_min >= v.limit_min)).map(([k, v]) => ({ key: k, full: v.used_min >= v.limit_min, text: `${WORK_ICON[k] ?? '🔧'} ${WORK_NAMES[k] ?? k} ${hrs(v.used_min)}/${hrs(v.limit_min)} h${v.used_min >= v.limit_min ? ' · 今天用够了' : ''}` }))
}

/** 房租一行：「🏠 房租 300 · 12-01 到期（3 天）」/ 欠租标红 */
export function rentText(r: RentInfo | null | undefined): { text: string; overdue: boolean } | null {
  if (!r || typeof r.amount !== 'number') return null
  const due = r.due_at ? r.due_at.slice(5, 10).replace('-', '-') : ''
  const days = typeof r.due_in_days === 'number' ? `（${r.due_in_days <= 0 ? '今天' : `${r.due_in_days} 天后`}）` : ''
  const parts = r.items && r.items.length > 1 ? ` = ${r.items.map(i => `${i.kind === 'shop' ? '铺面' : '住房'} ${i.amount}`).join(' + ')}` : ''
  if (r.overdue) return { text: `🏠 欠租 ${r.amount}${parts} · 房东催缴中`, overdue: true }
  return { text: `🏠 房租 ${r.amount}${parts}${due ? ` · ${due} 到期` : ''}${days}`, overdue: false }
}

/** 餐桌类是否允许吃某物品（dining_allow null = 都行） */
export const canEatHere = (o: Pick<GameObject, 'dining' | 'dining_allow'> | null | undefined, item: string) => !!o?.dining && (!o.dining_allow || o.dining_allow.includes(item))
