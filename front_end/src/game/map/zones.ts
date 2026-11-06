import type { Tile } from '../../types'

/**
 * 区域中文名。来源：B 的 back_end/scripts/gen_map.py 的 ZONE_NAMES（map.json 里有，但 GET /world 没暴露）——这里是一份复制，
 * **假设** 名字不常变；已在报告里请 B 把 zone_names 放进 /world。未知 id 直接显示 id。
 */
export const ZONE_NAMES: { world: Record<string, string>; sector: Record<string, string>; arena: Record<string, string> } = {
  world: { town: '鲸仔小镇' },
  sector: { outside: '小镇', achan_house: '阿蝉家', cook_house: '厨子家', grocer_house: '杂货商家', fisher_house: '渔夫小屋', regular_house: '常客家', restaurant: '餐馆' },
  arena: {
    grass: '草地', road: '街道', square: '广场', park: '公园', water: '河', dock: '码头',
    storage: '小仓库', achan_room: '阿蝉房间', kitchen: '厨房',
    cook_bedroom: '厨子的卧室', cook_kitchen: '厨子的厨房',
    grocer_shop: '杂货店', grocer_bedroom: '杂货商的卧室',
    fisher_hut: '渔夫的小屋', regular_bedroom: '常客的卧室', regular_bath: '常客的浴室',
    dining: '餐馆大堂', rest_kitchen: '餐馆后厨',
  },
}

export const sectorName = (id: string | null | undefined) => (id ? ZONE_NAMES.sector[id] ?? id : '')
export const arenaName = (id: string | null | undefined) => (id ? ZONE_NAMES.arena[id] ?? id : '')

/** 「阿蝉家 · 厨房」这样的显示名；室外只显示 arena */
export function zoneLabel(t: Pick<Tile, 'sector' | 'arena'> | null | undefined): string {
  if (!t) return ''
  if (!t.sector || t.sector === 'outside') return arenaName(t.arena)
  const s = sectorName(t.sector), a = arenaName(t.arena)
  return a && a !== s ? `${s} · ${a}` : s
}

/** 按 (x,y) 查 tile 的索引 */
export function buildTileIndex(tiles: Tile[]): Map<string, Tile> {
  const m = new Map<string, Tile>()
  for (const t of tiles) m.set(`${t.x},${t.y}`, t)
  return m
}
