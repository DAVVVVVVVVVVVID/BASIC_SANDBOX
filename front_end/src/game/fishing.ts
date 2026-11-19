/**
 * 钓鱼 v1（B world-v1.4.8 / §12.31）：ws {type: "fishing", entity, cast} → 头顶提示一句（纯函数；单测 tests/shop.test.ts）。
 * 鱼 / 垃圾冒提示，空竿不冒；稀有 / 传说加强调，破纪录另起头。
 */
export interface FishingCast { result?: string; item_name?: string; fish?: { name?: string; tier?: string; weight?: number } | null; tier_name?: string; big?: boolean; record_break?: boolean }
const TIER: Record<string, string> = { common: '普通', rare: '稀有', legend: '传说', legendary: '传说' }
export function fishingBubbleText(c: FishingCast | null | undefined): string | null {
  if (!c) return null
  if (c.result === 'junk') return `🎣 钓上来一个${c.item_name ?? '垃圾'}……`
  if (c.result !== 'fish' || !c.fish) return null
  const tier = c.fish.tier ?? 'common'
  const w = typeof c.fish.weight === 'number' ? ` ${c.fish.weight.toFixed(1)} kg` : ''
  const tn = c.tier_name ?? TIER[tier] ?? tier
  const head = c.record_break ? '🏆 破纪录！' : tier === 'legend' || tier === 'legendary' ? '🌟 传说！' : tier === 'rare' ? '✨ 稀有！' : '🎣'
  return `${head}钓到${c.fish.name ?? '鱼'}${w}${tier !== 'common' ? `（${tn}）` : c.big ? '（大的）' : ''}`
}

/** 鱼种 id → 中文名 / 品级（B fishing.json，world-v1.4.10）；个人纪录 by_species 按 id 记 */
export const SPECIES: Record<string, { name: string; tier: 'common' | 'rare' | 'legend' }> = {
  crucian: { name: '鲫鱼', tier: 'common' }, bleak: { name: '白条', tier: 'common' }, small_bass: { name: '小鲈鱼', tier: 'common' }, eel: { name: '黄鳝', tier: 'common' },
  golden_carp: { name: '金鳞鲤', tier: 'rare' }, largemouth: { name: '大口鲈', tier: 'rare' }, silver_cod: { name: '银鳕', tier: 'rare' },
  river_sturgeon: { name: '河神鲟', tier: 'legend' }, moon_catfish: { name: '月光鲶', tier: 'legend' }, star_kaluga: { name: '星斑鳇', tier: 'legend' },
}
export interface FishingCastRow { at: string; result: 'fish' | 'junk' | 'empty' | string; text: string; tier?: string; weight?: number; recordBreak: boolean }
export interface FishingView {
  best: { name: string; weight: number; at: string; initial: boolean } | null
  bySpecies: { id: string; name: string; tier: string; weight: number }[]
  today: { casts: number; minutes: number; limit: number | null } | null
  recent: FishingCastRow[]
}
/** GET /player/{id}.fishing = {spot, casts_today, minutes_today, limit_min, last_cast, recent_casts[], record{best, by_species}} → 显示数据（跟随看他的钓鱼纪录） */
export function fishingView(raw: unknown): FishingView | null {
  if (!raw || typeof raw !== 'object') return null
  const f = raw as Record<string, unknown>
  const rec = (f.record && typeof f.record === 'object' ? f.record : {}) as Record<string, unknown>
  const b = rec.best as Record<string, unknown> | null | undefined
  const best = b && typeof b.weight === 'number' ? { name: String(b.name ?? SPECIES[String(b.species)]?.name ?? b.species ?? '鱼'), weight: b.weight, at: String(b.at ?? ''), initial: !!b.initial } : null
  const bs = (rec.by_species && typeof rec.by_species === 'object' ? rec.by_species : {}) as Record<string, unknown>
  const tierRank: Record<string, number> = { legend: 0, rare: 1, common: 2 }
  const bySpecies = Object.entries(bs).filter(([, w]) => typeof w === 'number').map(([id, w]) => ({ id, name: SPECIES[id]?.name ?? id, tier: SPECIES[id]?.tier ?? 'common', weight: w as number }))
    .sort((x, y) => (tierRank[x.tier] ?? 3) - (tierRank[y.tier] ?? 3) || y.weight - x.weight)
  const recentRaw = Array.isArray(f.recent_casts) ? f.recent_casts as Record<string, unknown>[] : []
  const recent: FishingCastRow[] = recentRaw.map(c => {
    const fish = (c.fish && typeof c.fish === 'object' ? c.fish : null) as { name?: string; tier?: string; weight?: number; species?: string } | null
    const result = String(c.result ?? '')
    const text = result === 'fish' && fish ? `${fish.name ?? SPECIES[String(fish.species)]?.name ?? '鱼'}${typeof fish.weight === 'number' ? ` ${fish.weight.toFixed(1)} kg` : ''}` : result === 'junk' ? String(c.item_name ?? '垃圾') : '空竿'
    return { at: String(c.at ?? ''), result, text, tier: fish?.tier, weight: fish?.weight, recordBreak: !!c.record_break }
  }).sort((a, b2) => b2.at.localeCompare(a.at))
  const hasToday = typeof f.casts_today === 'number' || typeof f.minutes_today === 'number'
  const today = hasToday ? { casts: Number(f.casts_today ?? 0), minutes: Math.round(Number(f.minutes_today ?? 0)), limit: typeof f.limit_min === 'number' ? Math.round(f.limit_min) : null } : null
  if (!best && !bySpecies.length && !recent.length && !today) return null
  return { best, bySpecies, today, recent }
}
