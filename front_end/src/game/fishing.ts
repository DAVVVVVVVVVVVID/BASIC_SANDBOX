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
