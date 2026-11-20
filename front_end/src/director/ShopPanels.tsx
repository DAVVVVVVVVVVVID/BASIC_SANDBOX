import { useEffect, useState } from 'react'
import { useGameStore } from '../store/gameStore'
import { apiGetOrNull } from '../api/client'
import PixelShop from '../ui/shop/PixelShop'
import { goodsCards, menuCards } from '../ui/shop/cards'
import { iconUrl, kindOfObject, weightText, type PixelCard } from '../ui/shop/shopSkin'
import { useObjectRefresh } from '../game/objectRefresh'
import { isShop } from '../game/shop'
import { distanceTo } from '../game/shop'
import { godotCharKeyFor } from '../game/godotChars'
import type { GameObject, OtherPlayer } from '../types'
import type { TownEvent } from './events'

/**
 * 导播情境面板 · 二期（town-director-plan §2 / §3）：买卖 → 这家店的像素货架（只读，和操控页同一组件）；钓鱼 → 今日渔获冰卡 + 纪录。
 * 买卖：高亮她最近买的那件、刚成交盖章；数据走 store objects（导播开着买卖面板时补拉）。
 */
export function TradePanel({ target, events, now }: { target: OtherPlayer; events: TownEvent[]; now: number }) {
  const objects = useGameStore((s) => s.objects)
  useObjectRefresh(5000)
  const shops = objects.filter(o => isShop(o) || Array.isArray((o as unknown as { menu?: unknown }).menu))
  const last = [...events].reverse().find(e => e.who === target.id && e.category === 'trade' && now - e.at < 30_000) ?? null
  const shop: GameObject | undefined = (last?.place ? shops.find(o => o.id === last.place) : undefined)
    ?? shops.map(o => ({ o, d: distanceTo(target.position, o) })).sort((a, b) => a.d - b.d).find(x => x.d <= 4)?.o
  if (!shop) return <div style={{ fontSize: 22 }}>🛒 在买东西</div>
  const kind = kindOfObject(shop) ?? 'grocery'
  const menu = (shop as unknown as { menu?: unknown }).menu
  const cards: PixelCard[] = kind === 'restaurant' && Array.isArray(menu) ? menuCards(menu) : goodsCards(shop)
  const hit = last ? cards.find(c => (last.itemName && c.name === last.itemName) || (last.item && (c.key === last.item || c.key.startsWith(`${last.item}-`) || c.key === `dish-${last.item}`))) : undefined
  const footer = <span data-testid="director-trade-receipt" style={{ fontSize: 18, color: kind === 'restaurant' ? '#F3EAD8' : '#3B2F2F', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{last ? `${last.icon} ${last.text}` : `${target.name.replace(/_[0-9a-f]{6}$/i, '')} 在看货……`}</span>
  return <PixelShop kind={kind} title={shop.name} cards={cards} selectedKey={hit?.key ?? null} stampKey={hit && last && now - last.at < 2500 ? hit.key : null} footer={footer} gold={typeof target.gold === 'number' ? target.gold : null} scale={0.95} />
}

interface Cast { at?: string; result?: string; fish?: { species?: string; name?: string; weight?: number; tier?: string } | null; item_name?: string; record_break?: boolean }
interface Fishing { casts_today?: number; minutes_today?: number; recent_casts?: Cast[]; record?: { best?: { name?: string; weight?: number } | null } }

export function FishingPanel({ target }: { target: OtherPlayer }) {
  const [f, setF] = useState<Fishing | null>(null)
  useEffect(() => {
    let stop = false
    const load = () => apiGetOrNull<{ fishing?: Fishing }>(`/player/${encodeURIComponent(target.id)}`).then(r => { if (!stop) setF(r?.fishing ?? null) }).catch(() => {})
    load(); const t = window.setInterval(load, 5000)
    return () => { stop = true; window.clearInterval(t) }
  }, [target.id])
  const catches = (f?.recent_casts ?? []).filter(c => c.result === 'fish' && c.fish).slice(-6).reverse()
  const cards: PixelCard[] = catches.map((c, i) => ({ key: `c${i}`, icon: iconUrl(c.fish!.species) ?? iconUrl('fish'), name: c.fish!.name ?? '鱼', price: null, priceText: c.fish!.tier === 'legend' ? '传说' : c.fish!.tier === 'rare' ? '稀有' : '普通', sub: weightText(c.fish!.weight), soldOut: false, tier: c.fish!.tier ?? null }))
  const best = f?.record?.best
  const footer = (
    <div style={{ fontSize: 17, color: '#3B2F2F', lineHeight: 1.4 }}>
      <div>今天 {f?.casts_today ?? 0} 竿 · 坐了 {Math.round(f?.minutes_today ?? 0)} 分钟</div>
      {best && <div>🏆 最好：{best.name} {typeof best.weight === 'number' ? best.weight.toFixed(2) : ''} kg</div>}
    </div>
  )
  return <PixelShop kind="fish_stall" title={`${target.name.replace(/_[0-9a-f]{6}$/i, '')} 的渔获`} cards={cards} footer={footer} scale={0.95} ownerKey={godotCharKeyFor(target.name, target.controller, target.agent_id, target.sprite)} emptyText="今天还没钓到" />
}
