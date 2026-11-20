/**
 * 小镇导播 · 事件提示（town-director-plan §4）：统一格式「图标 谁 做了什么 对象 ×数量 金额」，按类型上色，同人同类 10 s 内合并。
 * 来源优先 B 的公开事件（public_event）；它上线前从现有 ws 的 action / produce / fishing 事件拼（纯函数；单测 tests/director.test.ts）。
 */
export type EventCategory = 'trade' | 'produce' | 'fishing' | 'school' | 'social' | 'live'
export interface TownEvent { key: string; who: string; whoName: string; category: EventCategory; icon: string; text: string; gold: number | null; at: number; count: number; item?: string | null; itemName?: string | null; place?: string | null }

export const CATEGORY_COLOR: Record<EventCategory, { bg: string; fg: string }> = {
  trade: { bg: '#FFF1CF', fg: '#8A6116' }, produce: { bg: '#EFE7FF', fg: '#5B4A8A' }, fishing: { bg: '#DDEFFB', fg: '#2F5E8A' },
  school: { bg: '#E6F6F3', fg: '#1F7A6F' }, social: { bg: '#FDE3EC', fg: '#A3405F' }, live: { bg: '#FBDAD6', fg: '#B23B2E' },
}
const VERB_ICON: Record<string, string> = {
  buy: '🛒', sell: '💰', order_meal: '🍲', serve_meal: '🍽', fish_caught: '🐟', record_broken: '🏆', produce: '💿', submit_homework: '📝',
  gift: '🎁', live_start: '📺', live_stop: '📺', closeness_tier_up: '💗', exchange: '♻️', stall_list: '🐟', class_answer: '✏️', class_called: '🙋',
}
const VERB_CAT: Record<string, EventCategory> = {
  buy: 'trade', sell: 'trade', order_meal: 'trade', serve_meal: 'trade', exchange: 'trade', stall_list: 'trade',
  fish_caught: 'fishing', record_broken: 'fishing', produce: 'produce', submit_homework: 'school', class_answer: 'school', class_called: 'school',
  gift: 'social', closeness_tier_up: 'social', live_start: 'live', live_stop: 'live',
}
const money = (g: number | null | undefined) => (typeof g === 'number' && g !== 0 ? ` ${g > 0 ? '+' : '−'}${Math.abs(Math.round(g))}` : '')

/** B 的公开事件 → TownEvent（text 后端已给，可直接显示；前面补图标） */
export function fromPublicEvent(e: Record<string, unknown>, at: number): TownEvent | null {
  const who = (e.who ?? {}) as { id?: string; name?: string }
  if (!who.id) return null
  const verb = String(e.verb ?? '')
  const category = (VERB_CAT[verb] ?? (e.category as EventCategory) ?? 'social') as EventCategory
  const gold = typeof e.gold_delta === 'number' ? e.gold_delta : null
  const obj = (e.object ?? {}) as { id?: string; item?: string; item_name?: string }
  return { key: `pe-${e.seq ?? at}`, who: who.id, whoName: who.name ?? who.id, category, icon: VERB_ICON[verb] ?? '✨', text: String(e.text ?? ''), gold, at, count: 1, item: obj.item ?? null, itemName: obj.item_name ?? null, place: obj.id ?? null }
}

/** 现有 ws 事件 → TownEvent（公开事件上线前的兜底） */
export function fromLegacy(type: 'action' | 'produce' | 'fishing', m: Record<string, unknown>, nameOf: (id: string) => string, at: number): TownEvent | null {
  const who = String(m.entity ?? '')
  if (!who) return null
  const name = nameOf(who)
  if (type === 'action') {
    if (!m.success) return null
    const act = String(m.action ?? ''), item = String(m.item_name ?? m.item ?? '')
    const extra = { item: typeof m.item === 'string' ? m.item : null, itemName: typeof m.item_name === 'string' ? m.item_name : null, place: typeof m.object === 'string' ? m.object : null }
    const gold = typeof m.gold_delta === 'number' ? m.gold_delta : null
    if (act === 'buy') return { key: `a-${at}-${who}`, who, whoName: name, category: 'trade', icon: '🛒', text: `${name} 买了 ${item}${money(gold)}`, gold, at, count: 1, ...extra }
    if (act === 'sell') return { key: `a-${at}-${who}`, who, whoName: name, category: 'trade', icon: '💰', text: `${name} 卖出 ${item}${money(gold)}`, gold, at, count: 1, ...extra }
    if (act === 'give') return { key: `a-${at}-${who}`, who, whoName: name, category: 'social', icon: '🎁', text: `${name} 把 ${item} 送给了 ${String(m.target_name ?? '')}`, gold: null, at, count: 1 }
    if (act === 'answer') return { key: `a-${at}-${who}`, who, whoName: name, category: 'school', icon: '✏️', text: `${name} 回答了课上的提问`, gold: null, at, count: 1 }
    if (act === 'order') return { key: `a-${at}-${who}`, who, whoName: name, category: 'trade', icon: '🍲', text: `${name} 点了 ${item || '菜'}${money(gold)}`, gold, at, count: 1, ...extra }
    return null
  }
  if (type === 'produce') {
    const via = String(m.via ?? ''), item = String(m.item_name ?? m.item ?? '')
    if (via === 'fishing') return null   // 钓鱼走 fishing 事件
    const icon = via === 'compose' ? '💿' : via === 'make_video' ? '📄' : via === 'stove' ? '🍳' : '✨'
    const text = via === 'compose' ? `${name} 写完了一首新歌` : via === 'make_video' ? `${name} 做完了一份稿子` : `${name} 做好了 ${item}`
    return { key: `p-${at}-${who}`, who, whoName: name, category: 'produce', icon, text, gold: null, at, count: 1 }
  }
  const cast = (m.cast ?? {}) as { result?: string; fish?: { name?: string; weight?: number; tier?: string }; record_break?: boolean }
  if (cast.result !== 'fish' || !cast.fish) return null
  const w = typeof cast.fish.weight === 'number' ? ` ${cast.fish.weight.toFixed(1)} kg` : ''
  return { key: `f-${at}-${who}`, who, whoName: name, category: 'fishing', icon: cast.record_break ? '🏆' : '🐟', text: `${name} 钓到 ${cast.fish.name ?? '鱼'}${w}${cast.record_break ? '，破纪录！' : ''}`, gold: null, at, count: 1 }
}

/** 同人同类 10 s 内合并：返回新列表（最新在后） */
export function mergeEvent(list: TownEvent[], e: TownEvent, windowMs = 10_000, max = 40): TownEvent[] {
  const i = list.findIndex(x => x.who === e.who && x.category === e.category && e.at - x.at <= windowMs)
  if (i >= 0) {
    const prev = list[i]
    const merged: TownEvent = { ...e, key: prev.key, count: prev.count + 1, gold: prev.gold !== null || e.gold !== null ? (prev.gold ?? 0) + (e.gold ?? 0) : null, text: e.text + (prev.count + 1 > 1 ? `（×${prev.count + 1}）` : '') }
    return [...list.slice(0, i), ...list.slice(i + 1), merged].slice(-max)
  }
  return [...list, e].slice(-max)
}
