/**
 * 像素商店（town-director-plan §3，主播 11-20 认可 v2 样图：三家同一结构只换材质）——切图映射与数据整理（纯函数；单测 tests/pixelShop.test.ts）。
 * 切图在 public/assets/ui/shop/（总控 gpt-image-2，run/data/art/ui-redo/shop/final/）。
 */
export type ShopKind = 'grocery' | 'restaurant' | 'fish_stall'
export const SHOP_ASSET = (name: string) => `assets/ui/shop/${name}.png`

/** 沙盒 item id / 菜 dish id / 鱼 species → 切图 icon key */
const ICON: Record<string, string> = {
  bread: 'bread', sweets: 'sweets', sweet: 'sweets', candy: 'sweets', ingredients: 'ingredients', ingredient: 'ingredients', gift: 'small_gift', bait: 'bait',
  home_rice: 'meal_homestyle', tomato_noodle: 'noodles_tomato_egg', fish_soup: 'fish_soup', catch_of_day: 'fresh_fish_plate', dessert: 'dessert',
  crucian: 'crucian_carp', bleak: 'white_bait', small_bass: 'small_bass', eel: 'eel', golden_carp: 'golden_carp', largemouth: 'largemouth_bass',
  silver_cod: 'silver_cod', river_sturgeon: 'river_god_sturgeon', moon_catfish: 'moonlight_catfish', star_kaluga: 'star_sturgeon',
  junk_boot: 'old_boot', junk_can: 'soda_can', junk_bag: 'plastic_bag', junk_line: 'broken_line',
  fish_dish: 'fish_dish', spoiled_food: 'spoiled_food', cd: 'cd', script: 'script', radio_script: 'script', class_notes: 'class_notes', homework_receipt: 'homework_receipt', key: 'key',
  fish: 'crucian_carp', home_meal: 'meal_homestyle', meal: 'meal_homestyle',
}
/** 有图就给 url，没有返回 null（调用方退回 emoji） */
export function iconUrl(id: string | null | undefined): string | null {
  const k = id ? ICON[id] : undefined
  return k ? SHOP_ASSET(`icon_${k}`) : null
}

export const KIND_SKIN: Record<ShopKind, { banner: string; bannerH: number; frame: string; card: string; ownerKey: string; ownerName: string }> = {
  grocery: { banner: 'banner_grocery', bannerH: 126, frame: 'frame_wood_shelf', card: 'card_wood', ownerKey: 'grocer', ownerName: '杂货店老板' },
  restaurant: { banner: 'banner_restaurant', bannerH: 150, frame: 'frame_chalkboard', card: 'card_paper', ownerKey: 'cook', ownerName: '餐厅老板' },
  fish_stall: { banner: 'banner_fishstall', bannerH: 136, frame: 'frame_ice_counter', card: 'card_ice', ownerKey: 'fisher', ownerName: '老渔夫' },
}
/** 物件类型 → 哪一家 */
export function kindOfObject(o: { type?: string; id?: string } | null | undefined): ShopKind | null {
  const t = `${o?.type ?? ''} ${o?.id ?? ''}`
  if (/shop_counter|counter/.test(t)) return 'grocery'
  if (/fish_stall/.test(t)) return 'fish_stall'
  if (/\bbar\b|restaurant/.test(t)) return 'restaurant'
  return null
}

export interface PixelCard { key: string; icon: string | null; emoji?: string; name: string; price: number | null; priceText?: string; sub: string | null; soldOut: boolean; tier?: string | null; note?: string }
/** 卡片按 3 列切行（店越多行越多） */
export function rowsOf<T>(cards: T[], cols = 3): T[][] {
  const out: T[][] = []
  for (let i = 0; i < cards.length; i += cols) out.push(cards.slice(i, i + cols))
  return out
}
export const weightText = (w: unknown) => (typeof w === 'number' && isFinite(w) ? `${w >= 10 ? w.toFixed(0) : w.toFixed(1)}kg` : null)
