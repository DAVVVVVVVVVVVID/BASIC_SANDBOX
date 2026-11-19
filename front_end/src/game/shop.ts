/**
 * 点商店物件直接弹商店面板（主播 11-19，fishing-system.md「页面」）——纯函数（单测 tests/shop.test.ts）。
 * 只排版：价格 / 库存 / 收不收 / 开没开门都照后端（objects[].shop / open / opensAt），能不能买卖以 POST /action 回包为准。
 */
import type { GameObject, ShopEntry } from '../types'
import { itemMeta, type InventoryItem } from './items'

export interface MetaChip { label: string; value: string; tone?: 'common' | 'rare' | 'legendary' | 'fresh' | 'stale' | 'spoiled' }
const GRADE: Record<string, { zh: string; tone: MetaChip['tone'] }> = {
  common: { zh: '普通', tone: 'common' }, normal: { zh: '普通', tone: 'common' }, 普通: { zh: '普通', tone: 'common' },
  rare: { zh: '稀有', tone: 'rare' }, 稀有: { zh: '稀有', tone: 'rare' },
  legendary: { zh: '传说', tone: 'legendary' }, legend: { zh: '传说', tone: 'legendary' }, 传说: { zh: '传说', tone: 'legendary' },
}
const FRESH: Record<string, { zh: string; tone: MetaChip['tone'] }> = {
  fresh: { zh: '新鲜', tone: 'fresh' }, 新鲜: { zh: '新鲜', tone: 'fresh' },
  stale: { zh: '不新鲜', tone: 'stale' }, 不新鲜: { zh: '不新鲜', tone: 'stale' },
  spoiled: { zh: '变质', tone: 'spoiled' }, 变质: { zh: '变质', tone: 'spoiled' },
}

/** 物品 meta → 小标签：品种 / 重量 / 品级 / 新鲜度（钓鱼系统逐条鱼）；没有的不显示 */
export function metaChips(meta: Record<string, unknown> | null | undefined): MetaChip[] {
  if (!meta) return []
  const out: MetaChip[] = []
  // B 草案（11-19）：{fish_id, species, name（中文名）, tier, weight, caught_at, caught_by, freshness}——有 name 时标题已显示中文名，不再重复出品种标签（species 多半是英文 id）
  const species = meta.species_name ?? (typeof meta.name === 'string' && meta.name ? null : meta.species ?? meta.kind_name)
  if (typeof species === 'string' && species) out.push({ label: '品种', value: species })
  const w = meta.weight_kg ?? meta.weight
  if (typeof w === 'number' && isFinite(w)) out.push({ label: '重量', value: `${w >= 10 ? w.toFixed(0) : w.toFixed(1)} kg` })
  const g = meta.tier ?? meta.grade ?? meta.rarity
  if (typeof g === 'string' && g) { const m = GRADE[g.toLowerCase()] ?? GRADE[g]; out.push({ label: '品级', value: m?.zh ?? g, tone: m?.tone }) }
  const f = meta.freshness ?? meta.fresh
  if (typeof f === 'string' && f) { const m = FRESH[f.toLowerCase()] ?? FRESH[f]; out.push({ label: '新鲜度', value: m?.zh ?? f, tone: m?.tone }) }
  return out
}

export interface GoodsRow { key: string; item: string; itemId?: string; name: string; icon: string; price: number | null; stock: number | null; chips: MetaChip[] }
/** 这家店在卖的（price 非空）；逐条货（有 id / meta）各占一行 */
export function goodsRows(obj: Pick<GameObject, 'shop' | 'stock' | 'daily_supply'>): GoodsRow[] {
  const rows: GoodsRow[] = []
  ;(obj.shop ?? []).forEach((s: ShopEntry, i) => {
    if (s.price === null || s.price === undefined) return
    const item = String(s.type ?? s.item ?? s.name ?? `item${i}`)
    const m = itemMeta(item, s.name)
    const stock = typeof s.stock === 'number' ? s.stock : (obj.stock && typeof obj.stock[item] === 'number' ? obj.stock[item] : null)
    const itemId = s.item_id ?? s.id
    rows.push({ key: itemId ?? `${item}-${i}`, item, itemId, name: String((s.meta?.name as string | undefined) ?? s.name ?? m.label), icon: m.icon, price: s.price, stock, chips: metaChips(s.meta) })
  })
  return rows
}

export interface SellRow { key: string; item: string; itemId?: string; name: string; icon: string; count: number; sell: number; chips: MetaChip[] }
/** 自己背包里这家店收的（shop[].sell 非空、类型对上） */
export function sellRows(obj: Pick<GameObject, 'shop'>, inv: InventoryItem[]): SellRow[] {
  const buys = new Map<string, number>()
  for (const s of obj.shop ?? []) if (typeof s.sell === 'number') buys.set(String(s.type ?? s.item ?? ''), s.sell)
  return inv.flatMap((it, i) => {
    const sell = buys.get(it.type)
    if (sell === undefined) return []
    const m = itemMeta(it.type, it.name)
    return [{ key: `${it.id ?? it.type}-${i}`, item: it.type, itemId: it.id, name: (typeof it.meta?.name === 'string' && it.meta.name) || it.name || m.label, icon: m.icon, count: it.count, sell, chips: metaChips(it.meta) }]
  })
}

/** 到物件最近一格的曼哈顿距离（只用来提示「走近一点」，能不能买以后端为准） */
export function distanceTo(pos: { x: number; y: number }, obj: Pick<GameObject, 'position' | 'tiles'>): number {
  const ts = obj.tiles && obj.tiles.length ? obj.tiles : [obj.position]
  return Math.min(...ts.map(t => Math.abs(t.x - pos.x) + Math.abs(t.y - pos.y)))
}
export const NEAR_ENOUGH = 1
export const isShop = (o: Pick<GameObject, 'shop'>) => Array.isArray(o.shop) && o.shop.length > 0

/** 买 / 卖失败 reason → 中文（后端带 message 的优先） */
export function shopFailText(reason: string | null | undefined, result: Record<string, unknown> | null | undefined): string {
  const r = result ?? {}
  if (typeof r.message === 'string' && r.message) return r.message
  switch (reason) {
    case 'insufficient_funds': return '钱不够'
    case 'object_too_far': case 'no_object': return '离太远了，走近一点'
    case 'shop_closed': return `已经打烊了${typeof r.opens_at === 'string' ? `，${r.opens_at} 开门` : ''}`
    case 'not_for_sale': return '这家不卖这个'
    case 'not_buying': return '这家不收这个'
    case 'no_item': return '背包里没有了'
    case 'inventory_full': return '背包满了'
    case 'out_of_stock': return '卖完了'
    default: return reason ? `没成（${reason}）` : '没成'
  }
}
