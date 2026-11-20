import type { GameObject } from '../../types'
import { goodsRows, menuRows } from '../../game/shop'
import { itemMeta } from '../../game/items'
import { iconUrl, weightText, type PixelCard } from './shopSkin'

/** 商店物件 → 像素卡片（杂货 / 吧台的 shop[]；鱼摊有 listings 时逐条） */
export function goodsCards(obj: Pick<GameObject, 'shop' | 'stock' | 'daily_supply' | 'listings'>): PixelCard[] {
  if (Array.isArray(obj.listings)) {
    return obj.listings.map(l => ({
      key: `listing-${l.listing_id}`, icon: iconUrl(l.species) ?? iconUrl('fish'), name: l.name ?? '鱼', price: l.price, sub: weightText(l.weight), soldOut: false, tier: l.tier ?? null,
      note: [l.name, weightText(l.weight), l.freshness === 'stale' ? '不新鲜' : l.freshness === 'fresh' ? '新鲜' : ''].filter(Boolean).join(' · '),
    }))
  }
  return goodsRows(obj).map(g => ({ key: g.key, icon: iconUrl(g.item), emoji: itemMeta(g.item).icon, name: g.name, price: g.price, sub: g.stock === null ? null : String(g.stock), soldOut: g.stock === 0 }))
}
/** 餐厅菜单 → 像素卡片（available=false 当售罄显示，原因放 note） */
export function menuCards(menu: unknown): PixelCard[] {
  return menuRows(menu).map(r => ({
    key: `dish-${r.dish}`, icon: iconUrl(r.dish), emoji: '🍲', name: r.name, price: r.price, priceText: r.price !== null && r.priceNote ? `${r.price}起` : undefined,
    sub: null, soldOut: !r.available, note: r.available ? (r.uses ? `用料：${r.uses}` : r.name) : (r.why || '现在点不了'),
  }))
}
