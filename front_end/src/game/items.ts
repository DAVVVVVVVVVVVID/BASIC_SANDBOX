/**
 * W9：背包物品表（`docs/world-bible/03-objects.md` 3.2）。后端的物品类型名尚未定稿（B W10 任务 4），
 * 这里按中英文都认，认不出的用 📦 + 原名显示。
 */
export interface ItemMeta { icon: string; label: string; kind: 'food' | 'material' | 'gift' | 'file' | 'key' | 'physical' | 'other'; price?: number; spoiled?: boolean }
/** 实体作品（CD / 稿子）：背包里画带底框的图标 */
export const isPhysicalWork = (m: ItemMeta) => m.kind === 'physical'

const META: Record<string, ItemMeta> = {
  bread: { icon: '🍞', label: '面包', kind: 'food', price: 5 },
  sweet: { icon: '🍬', label: '甜食', kind: 'food', price: 6 },
  candy: { icon: '🍬', label: '甜食', kind: 'food', price: 6 },
  bento: { icon: '🍱', label: '便当', kind: 'food' },
  lunchbox: { icon: '🍱', label: '便当', kind: 'food' },
  ingredient: { icon: '🥬', label: '食材', kind: 'material', price: 8 },
  ingredients: { icon: '🥬', label: '食材', kind: 'material', price: 8 },
  fish: { icon: '🐟', label: '鱼', kind: 'food', price: 10 },
  bait: { icon: '🪱', label: '鱼饵', kind: 'material', price: 3 },
  gift: { icon: '🎁', label: '小礼物', kind: 'gift', price: 25 },
  song: { icon: '🎵', label: '歌', kind: 'file' },
  script: { icon: '📄', label: '稿子', kind: 'physical' },   // v1.1 起实体
  radio_script: { icon: '📄', label: '稿子', kind: 'physical' },
  image: { icon: '🖼', label: '图片', kind: 'file' },
  key: { icon: '🔑', label: '钥匙', kind: 'key' },
  // world-v1.1（B 字段表 11-13）：家常菜 / 鱼料理 / 坏食；CD = 歌的实体版、稿子 = 电台稿实体版（替代 song / script 文件类，图标沿用加「实体」底框）
  home_meal: { icon: '🍲', label: '家常菜', kind: 'food' },
  fish_dish: { icon: '🍛', label: '鱼料理', kind: 'food' },
  spoiled_food: { icon: '🤢', label: '坏掉的食物', kind: 'food', spoiled: true },
  meal: { icon: '🍽', label: '餐厅一顿', kind: 'food', price: 20 },
  cd: { icon: '🎵', label: '唱片', kind: 'physical' },   // §3.41：钥匙物品 {type:'key', meta:{door_id, name}}，显示 meta.name（合租房大门钥匙）；送钥匙走「送」带 door_id
}
const CN: Record<string, string> = { 面包: 'bread', 甜食: 'sweet', 便当: 'bento', 食材: 'ingredient', 鱼: 'fish', 鱼饵: 'bait', 小礼物: 'gift', 礼物: 'gift', 歌: 'song', 电台文稿: 'script', 文稿: 'script', 图片: 'image', 钥匙: 'key', 家常菜: 'home_meal', 鱼料理: 'fish_dish', 坏掉的食物: 'spoiled_food', 唱片: 'cd', 稿子: 'script' }

export function itemMeta(type: string | undefined | null, name?: string | null): ItemMeta {
  const k = (type ?? '').toLowerCase().replace(/[-\s]/g, '_')
  if (META[k]) return META[k]
  const byName = name ? CN[name] : undefined
  if (byName) return META[byName]
  const cnKey = CN[type ?? '']
  if (cnKey) return META[cnKey]
  return { icon: '📦', label: name || type || '物品', kind: 'other' }
}

/** 后端 inventory 条目形状未定：接受 {type,name,count} / {item,qty} / 纯字符串 */
export interface InventoryItem { type: string; name?: string; count: number; id?: string; kind?: string; meta?: Record<string, unknown> }
export function normalizeInventory(raw: unknown): InventoryItem[] {
  if (!Array.isArray(raw)) return []
  const out: InventoryItem[] = []
  for (const r of raw) {
    if (typeof r === 'string') { out.push({ type: r, count: 1 }); continue }
    if (!r || typeof r !== 'object') continue
    const o = r as Record<string, unknown>
    const type = String(o.type ?? o.item ?? o.item_type ?? o.kind ?? o.name ?? 'item')
    const count = Number(o.count ?? o.qty ?? o.quantity ?? o.n ?? 1) || 1
    out.push({ type, name: typeof o.name === 'string' ? o.name : undefined, count, id: typeof o.id === 'string' ? o.id : undefined, kind: typeof (o.kind ?? o.class) === 'string' ? String(o.kind ?? o.class) : undefined, meta: o.meta && typeof o.meta === 'object' ? (o.meta as Record<string, unknown>) : undefined })
  }
  return out
}
export const isFileItem = (it: InventoryItem) => it.kind === 'file' || itemMeta(it.type, it.name).kind === 'file'
/** 条目显示名：钥匙等带 meta.name 的用 meta.name（「合租房大门钥匙」） */
export const itemDisplayName = (it: InventoryItem) => (typeof it.meta?.name === 'string' && it.meta.name) || it.name || itemMeta(it.type, it.name).label
