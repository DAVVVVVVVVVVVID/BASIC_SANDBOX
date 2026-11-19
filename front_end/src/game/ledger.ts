/**
 * 商店账本 / 库房（商店系统第一期，whale docs/systems/shops-system.md §1 §4，主播 11-19 开工）——纯函数（单测 tests/ledger.test.ts）。
 * B 的 read_ledger 形状还没定：这里宽容解析（字段名几种写法都认），接口到了对一下即可；没有接口时页面显示「还没开通」，`?shopdemo=1` 才用样例。
 */
export type LedgerKind = 'sale' | 'purchase' | 'freight' | 'refund' | 'recycle' | 'list' | 'spoiled' | 'lost' | 'other'
export interface LedgerEntry { ts: string; kind: LedgerKind; who: string; item: string; qty: number; unit: number | null; amount: number; note: string }
export interface LedgerDay { date: string; revenue: number; cost: number; gross: number; stock: Record<string, number> }
export interface Ledger { shop: string; days: LedgerDay[]; entries: LedgerEntry[] }
export interface Incoming { item: string; qty: number; eta: string }
export interface Warehouse { stock: Record<string, number>; cap: number | null; incoming: Incoming[] }

const KIND_ALIAS: Record<string, LedgerKind> = {
  sale: 'sale', sell: 'sale', sold: 'sale', 卖出: 'sale',
  purchase: 'purchase', restock: 'purchase', order: 'purchase', 进货: 'purchase',
  freight: 'freight', shipping: 'freight', 运费: 'freight',
  refund: 'refund', 退款: 'refund',
  recycle: 'recycle', exchange: 'recycle', trade_in: 'recycle', 回收: 'recycle', 换鱼饵: 'recycle',
  list: 'list', listing: 'list', 上货: 'list',
  spoiled: 'spoiled', spoil: 'spoiled', 变质: 'spoiled',
  lost: 'lost', lost_customer: 'lost', fail: 'lost', 流失: 'lost',
}
export const KIND_ZH: Record<LedgerKind, { label: string; icon: string }> = {
  sale: { label: '卖出', icon: '💰' }, purchase: { label: '进货', icon: '📦' }, freight: { label: '运费', icon: '🚚' },
  refund: { label: '退款', icon: '↩️' }, recycle: { label: '换鱼饵', icon: '♻️' }, list: { label: '上货', icon: '🐟' }, spoiled: { label: '变质下架', icon: '🗑' },
  lost: { label: '流失', icon: '🚶' }, other: { label: '其他', icon: '·' },
}
const num = (x: unknown, d = 0) => (typeof x === 'number' && isFinite(x) ? x : typeof x === 'string' && x.trim() && isFinite(Number(x)) ? Number(x) : d)
const str = (x: unknown) => (typeof x === 'string' ? x : x === null || x === undefined ? '' : String(x))
const obj = (x: unknown): Record<string, unknown> => (x && typeof x === 'object' && !Array.isArray(x) ? x as Record<string, unknown> : {})

export function normalizeLedger(raw: unknown, shop = ''): Ledger | null {
  const r = obj(raw)
  const rawEntries = Array.isArray(r.entries) ? r.entries : Array.isArray(r.rows) ? r.rows : Array.isArray(raw) ? raw : null
  const rawDays = Array.isArray(r.days) ? r.days : Array.isArray(r.summary) ? r.summary : null
  if (!rawEntries && !rawDays) return null
  const entries: LedgerEntry[] = (rawEntries ?? []).map(e => {
    const o = obj(e)
    const kind = KIND_ALIAS[str(o.kind ?? o.type ?? o.action)] ?? 'other'
    const qty = num(o.qty ?? o.count, 1), unit = o.unit_price ?? o.price ?? o.unit
    const amount = num(o.amount ?? o.total ?? (typeof unit === 'number' ? unit * qty : 0))
    return { ts: str(o.ts ?? o.game_time ?? o.time), kind, who: str(o.who_name ?? o.buyer_name ?? o.who ?? o.buyer ?? o.customer ?? ''), item: str(o.item_name ?? o.item ?? ''), qty, unit: typeof unit === 'number' ? unit : null, amount, note: str(o.note ?? o.reason ?? o.message ?? '') }
  }).sort((a, b) => b.ts.localeCompare(a.ts))
  const days: LedgerDay[] = (rawDays ?? []).map(d => {
    const o = obj(d)
    const revenue = num(o.revenue ?? o.income), cost = num(o.cost ?? o.expense)
    const stockRaw = obj(o.stock ?? o.inventory)
    return { date: str(o.date ?? o.day), revenue, cost, gross: num(o.gross ?? o.profit, revenue - cost), stock: Object.fromEntries(Object.entries(stockRaw).map(([k, v]) => [k, num(v)])) }
  }).sort((a, b) => b.date.localeCompare(a.date))
  return { shop: str(r.shop ?? shop), days, entries }
}

/** 范围汇总：today = 最新一天；week = 近 7 天合计（库存取最新一天） */
export function summarize(l: Ledger, range: 'today' | 'week'): { revenue: number; cost: number; gross: number; stock: Record<string, number>; lost: number; days: LedgerDay[] } {
  const days = range === 'today' ? l.days.slice(0, 1) : l.days.slice(0, 7)
  const dates = new Set(days.map(d => d.date))
  const inRange = (e: LedgerEntry) => !dates.size || dates.has(e.ts.slice(0, 10))
  return {
    revenue: days.reduce((a, d) => a + d.revenue, 0),
    cost: days.reduce((a, d) => a + d.cost, 0),
    gross: days.reduce((a, d) => a + d.gross, 0),
    stock: days[0]?.stock ?? {},
    lost: l.entries.filter(e => e.kind === 'lost' && inRange(e)).length,
    days,
  }
}
export function entriesIn(l: Ledger, range: 'today' | 'week', kind: LedgerKind | 'all'): LedgerEntry[] {
  const days = range === 'today' ? l.days.slice(0, 1) : l.days.slice(0, 7)
  const dates = new Set(days.map(d => d.date))
  return l.entries.filter(e => (kind === 'all' || e.kind === kind) && (!dates.size || dates.has(e.ts.slice(0, 10))))
}

/** 商店物件上的库房 / 待送达订单（字段名待 B 定：warehouse / storeroom，incoming / orders / pending_orders） */
export function normalizeWarehouse(o: Record<string, unknown> | null | undefined): Warehouse | null {
  const r = obj(o)
  const w = obj(r.warehouse ?? r.storeroom ?? r.backstock)
  const stockRaw = obj(w.stock ?? w.items ?? (Object.keys(w).length && !('stock' in w) && !('incoming' in w) ? w : {}))
  const inc = Array.isArray(w.incoming) ? w.incoming : Array.isArray(r.incoming) ? r.incoming : Array.isArray(r.pending_orders) ? r.pending_orders : Array.isArray(r.orders) ? r.orders : []
  const stock = Object.fromEntries(Object.entries(stockRaw).filter(([, v]) => typeof v === 'number' || (typeof v === 'string' && isFinite(Number(v)))).map(([k, v]) => [k, num(v)]))
  const incoming: Incoming[] = inc.flatMap(x => {
    const o2 = obj(x)
    const eta = str(o2.eta ?? o2.arrive_at ?? o2.deliver_at ?? '')
    const lines = Array.isArray(o2.items) ? o2.items.map(obj) : [o2]
    return lines.filter(l => l.item || l.name).map(l => ({ item: str(l.item ?? l.name), qty: num(l.qty ?? l.count, 1), eta }))
  })
  if (!Object.keys(stock).length && !incoming.length) return null
  return { stock, cap: typeof w.cap === 'number' ? w.cap : typeof w.capacity === 'number' ? w.capacity : null, incoming }
}

/** "2026-11-20T07:30:00+08:00" → "明早 07:30"（相对游戏今天） */
export function etaText(eta: string, today: string | undefined): string {
  if (!eta) return ''
  const d = eta.slice(0, 10), hm = eta.slice(11, 16) || eta
  if (!today || !/^\d{4}-\d{2}-\d{2}$/.test(d)) return hm
  const diff = Math.round((Date.parse(d + 'T00:00:00Z') - Date.parse(today + 'T00:00:00Z')) / 86400000)
  const when = diff === 0 ? '今天' : diff === 1 ? (Number(hm.slice(0, 2)) < 12 ? '明早' : '明天') : diff === 2 ? '后天' : d.slice(5)
  return `${when} ${hm}`
}

/** 样例（只在 ?shopdemo=1 用，给主播看版式） */
export function demoLedger(shop: string, today: string): Ledger {
  const day = (k: number) => new Date(Date.parse(today + 'T00:00:00Z') - k * 86400000).toISOString().slice(0, 10)
  const days: LedgerDay[] = Array.from({ length: 7 }, (_, k) => ({ date: day(k), revenue: 140 - k * 9 + (k % 2) * 15, cost: 70 - k * 3, gross: 0, stock: (k === 0 ? { 面包: 6, 食材: 9, 甜食: 2, 鱼饵: 14, 小礼物: 3 } : {}) as Record<string, number> })).map(d => ({ ...d, gross: d.revenue - d.cost }))
  const t = (hm: string) => `${today}T${hm}:00`
  const entries: LedgerEntry[] = [
    { ts: t('19:42'), kind: 'sale', who: '路人 · 老王', item: '面包', qty: 2, unit: 5, amount: 10, note: '' },
    { ts: t('16:05'), kind: 'sale', who: '鲸仔', item: '甜食', qty: 1, unit: 6, amount: 6, note: '' },
    { ts: t('14:30'), kind: 'recycle', who: '老渔夫', item: '变质的鱼 → 鱼饵', qty: 2, unit: 1, amount: 2, note: '' },
    { ts: t('07:31'), kind: 'refund', who: '镇外批发 · 周叔', item: '鱼饵', qty: 2, unit: 1, amount: 2, note: '库房满 40，退款' },
    { ts: t('09:20'), kind: 'sale', who: '克劳蒂娜', item: '食材', qty: 3, unit: 8, amount: 24, note: '' },
    { ts: t('07:30'), kind: 'purchase', who: '镇外批发 · 周叔', item: '面包', qty: 10, unit: 3, amount: -30, note: '到货' },
    { ts: t('07:30'), kind: 'freight', who: '镇外批发 · 周叔', item: '运费', qty: 1, unit: 10, amount: -10, note: '' },
  ]
  return { shop, days, entries: entries.sort((a, b) => b.ts.localeCompare(a.ts)) }
}
export function demoWarehouse(today: string): Warehouse {
  const tomorrow = new Date(Date.parse(today + 'T00:00:00Z') + 86400000).toISOString().slice(0, 10)
  return { stock: { 面包: 22, 食材: 9, 甜食: 4, 鱼饵: 30, 小礼物: 6 }, cap: 40, incoming: [{ item: '面包', qty: 10, eta: `${tomorrow}T07:30:00` }, { item: '食材', qty: 12, eta: `${tomorrow}T07:30:00` }] }
}
