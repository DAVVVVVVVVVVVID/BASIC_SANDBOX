import { useEffect, useState } from 'react'
import { useGameStore } from '../../store/gameStore'
import { apiGetOrNull } from '../../api/client'
import { exchangeRows, orderRows, menuRows, waitingText, type OrderRow } from '../../game/shop'
import { gameNowMs, parseGameTime } from '../../game/v11'
import { etaText } from '../../game/ledger'
import { normalizeInventory } from '../../game/items'
import type { GameObject } from '../../types'
import { Chip } from './MetaChips'
import { C } from './theme'
import PixelShop from '../shop/PixelShop'
import { menuCards } from '../shop/cards'
import { SHOP_ASSET } from '../shop/shopSkin'

/**
 * 商店面板里两家店特有的部分（主播 11-19：钓鱼 / 杂货店 / 餐厅今天上主镇）。
 * 杂货店柜台：进货单（GET /shop/orders?shop=grocery）+ 换鱼饵（exchange pay / donate）。
 * 餐厅吧台：菜单（objects[bar].menu）+ 点单（order {dish}，先坐餐桌）+ 等菜（players[].busy waiting_order）+ 后厨在做（objects[bar].orders）。
 * 能不能换 / 点都以后端为准，失败 message 原样显示（父组件的 act）。
 */
type Act = (key: string, label: string, type: string, payload: Record<string, unknown>) => void
const TONE: Record<OrderRow['tone'], { bg: string; fg: string }> = { wait: { bg: '#FBEBC9', fg: '#8A6116' }, ok: { bg: '#DDEBFF', fg: '#2F5E8A' }, done: { bg: '#DDF3EE', fg: '#1F7A6F' }, bad: { bg: '#FBDAD6', fg: '#B23B2E' } }
const DEMO = typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('shopdemo') === '1'

export function GroceryExtras({ busy, act }: { busy: string | null; act: Act }) {
  const player = useGameStore((s) => s.player)
  const today = useGameStore((s) => s.worldState?.date)
  const [orders, setOrders] = useState<OrderRow[] | null>(null)
  useEffect(() => {
    let stop = false
    const load = () => (DEMO
      ? Promise.resolve({ orders: [{ order_id: 'po-demo', status: 'confirmed', items: [{ item: 'bread', name: '面包', qty: 10 }, { item: 'ingredients', name: '食材', qty: 12 }], total: 118, ordered_by: '克劳蒂娜', deliver_at: `${today ?? '2026-11-20'}T07:30:00+08:00` }, { order_id: 'po-demo0', status: 'quoted', items: [{ item: 'sweets', name: '甜食', qty: 6 }], total: 28, ordered_by: '杂货店老板', expires_at: `${today ?? '2026-11-20'}T21:30:00+08:00` }] })
      : apiGetOrNull<unknown>('/shop/orders?shop=grocery')).then(r => { if (!stop) setOrders(r ? orderRows(r) : null) }).catch(() => { if (!stop) setOrders(null) })
    load(); const t = window.setInterval(load, 15_000)
    return () => { stop = true; window.clearInterval(t) }
  }, [today])
  const rows = exchangeRows(normalizeInventory(player?.inventory))
  return (
    <>
      {orders && (
        <section data-testid="shop-orders" style={{ background: 'rgba(255,255,255,0.5)', border: '1px dashed #E6DCCB', borderRadius: 8, padding: '6px 10px' }}>
          <div style={{ fontWeight: 700, marginBottom: 4 }}>进货单 <span style={{ fontWeight: 400, fontSize: 12, color: C.inkSoft }}>· 向「镇外批发 · 周叔」QQ 下单，22:00 截单、07:30 送到</span></div>
          {orders.length === 0 && <div style={{ fontSize: 13, color: C.inkSoft }}>最近没有进货单</div>}
          {orders.slice(0, 5).map(o => (
            <div key={o.id} style={{ display: 'flex', alignItems: 'baseline', gap: 6, fontSize: 13, padding: '2px 0', flexWrap: 'wrap' }}>
              <span style={{ fontSize: 11, padding: '1px 7px', borderRadius: 9, background: TONE[o.tone].bg, color: TONE[o.tone].fg, whiteSpace: 'nowrap' }}>{o.statusZh}</span>
              <span style={{ flex: 1, minWidth: 0 }}>{o.items || '—'}{o.total !== null ? <b> · ¥{o.total}</b> : null}{o.by ? <span style={{ color: C.inkSoft }}> · {o.by}</span> : null}</span>
              {o.when && <span style={{ fontSize: 12, color: C.inkSoft, whiteSpace: 'nowrap' }}>{o.status === 'confirmed' ? `${etaText(o.when, today)} 到` : o.status === 'quoted' ? `${etaText(o.when, today)} 前确认` : etaText(o.when, today)}</span>}
            </div>
          ))}
        </section>
      )}
      <section data-testid="shop-exchange">
        <div style={{ fontWeight: 700, marginBottom: 4 }}>换鱼饵 <span style={{ fontWeight: 400, fontSize: 12, color: C.inkSoft }}>· 变质的鱼 / 变质食物 / 垃圾，每件换 1 个鱼饵（永久不坏）</span></div>
        {rows.length === 0 && <div style={{ color: C.inkSoft, fontSize: 13 }}>背包里没有能换的（放坏太久的东西约 2 天后会自动扔掉）</div>}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {rows.map(r => (
            <div key={r.key} data-testid={`shop-exchange-row-${r.item}`} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px', borderRadius: 8, background: 'rgba(255,255,255,0.6)', border: '1px solid #E6DCCB', flexWrap: 'wrap' }}>
              <span style={{ fontSize: 20 }}>{r.icon}</span>
              <div style={{ flex: 1, minWidth: 0, display: 'flex', gap: 6, alignItems: 'baseline', flexWrap: 'wrap' }}><b>{r.name}</b>{r.count > 1 ? <span>×{r.count}</span> : null}{r.chips.map((c, i) => <Chip key={i} c={c} />)}</div>
              <button className="k teal" data-testid={`shop-exchange-pay-${r.item}`} disabled={!!busy} onClick={() => act(`${r.key}-pay`, `换鱼饵（${r.name}，付 1 金币）`, 'exchange', { item: r.item, mode: 'pay', ...(r.fishId ? { fish_id: r.fishId } : {}) })} style={{ minHeight: 36 }}>付 1 金币换</button>
              <button className="k" data-testid={`shop-exchange-donate-${r.item}`} disabled={!!busy} onClick={() => act(`${r.key}-donate`, `换鱼饵（${r.name}，送给店主）`, 'exchange', { item: r.item, mode: 'donate', ...(r.fishId ? { fish_id: r.fishId } : {}) })} style={{ minHeight: 36 }}>送给店主</button>
            </div>
          ))}
        </div>
      </section>
    </>
  )
}

export function RestaurantMenu({ obj, busy, act }: { obj: GameObject; busy: string | null; act: Act }) {
  const player = useGameStore((s) => s.player)
  const ws = useGameStore((s) => s.worldState)
  const players = useGameStore((s) => s.players)
  const [, tick] = useState(0)
  const [selKey, setSelKey] = useState<string | null>(null)
  useEffect(() => { const t = window.setInterval(() => tick(x => x + 1), 1000); return () => window.clearInterval(t) }, [])
  const rows = menuRows((obj as unknown as { menu?: unknown }).menu)
  const nowMs = gameNowMs(ws)
  const wait = waitingText(player?.busy as { kind?: string; name?: string; ends_at?: string } | null, nowMs, parseGameTime)
  const kitchen = Array.isArray((obj as unknown as { orders?: unknown }).orders) ? (obj as unknown as { orders: { order_id: string; by?: string; by_name?: string; name?: string; dish?: string; ready_at?: string }[] }).orders : []
  if (!rows.length) return <div data-testid="shop-menu-missing" style={{ color: C.inkSoft, fontSize: 13 }}>菜单还没开通（等沙盒的餐厅点单）</div>
  return (
    <div data-testid="shop-menu" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ fontSize: 12, color: C.inkSoft }}>先坐到餐厅的餐桌上（点餐桌或面朝它按 E），再点菜；现点现做，约 1 分钟上菜，上菜后自动开吃。</div>
      {player?.busy?.kind === 'eating' && <div style={{ background: '#DDF3EE', border: '1px solid #8FD3C7', borderRadius: 8, padding: '6px 10px' }}>🍽 正在吃{(player.busy as { name?: string; item?: string }).name ?? ''}</div>}
      {/* 像素黑板菜单（主播 11-20 v2，与直播导播页共用） */}
      {(() => {
        const sel = rows.find(r => `dish-${r.dish}` === selKey) ?? null
        const prog = typeof (player?.busy as { progress?: number } | null)?.progress === 'number' ? (player!.busy as { progress: number }).progress : null
        const footer = wait
          ? <div data-testid="shop-waiting" style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%', color: '#F3EAD8' }}>
              <span style={{ width: 48, height: 48, flexShrink: 0, backgroundImage: `url(${SHOP_ASSET('pot_cooking_strip')})`, backgroundSize: '192px 48px', imageRendering: 'pixelated', animation: 'potCook 0.8s steps(4) infinite' }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 700 }}>{wait}</div>
                <div style={{ height: 8, background: 'rgba(255,255,255,0.25)', borderRadius: 4, overflow: 'hidden', marginTop: 4 }}><div style={{ width: `${Math.round((prog ?? 0.3) * 100)}%`, height: '100%', background: '#F2A14B' }} /></div>
              </div>
              <style>{'@keyframes potCook { from { background-position: 0 0 } to { background-position: -192px 0 } }'}</style>
            </div>
          : sel
            ? <div style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%', flexWrap: 'wrap', color: '#F3EAD8' }}>
                <span style={{ fontSize: 14 }}>点：<b>{sel.name}</b>{sel.price !== null ? ` · ${sel.price}${sel.priceNote ? ' 起' : ''} 金币` : ''}</span>
                <button className="k teal" data-testid={`shop-order-${sel.dish}`} disabled={!!busy || !sel.available} onClick={() => act(`order-${sel.dish}`, `点 ${sel.name}`, 'order', { dish: sel.dish })} style={{ minWidth: 64, minHeight: 36 }}>{busy === `order-${sel.dish}` ? '…' : '点'}</button>
              </div>
            : <span style={{ fontSize: 13, color: '#F3EAD8' }}>点一道菜选中，再按「点」</span>
        return <PixelShop kind="restaurant" title={obj.name} cards={menuCards((obj as unknown as { menu?: unknown }).menu)} selectedKey={selKey} gold={typeof player?.gold === 'number' ? player.gold : null} scale={0.7}
          onPick={c => setSelKey(k => (k === c.key ? null : c.key))} footer={footer} />
      })()}
      {kitchen.length > 0 && (
        <div data-testid="shop-kitchen" style={{ fontSize: 12, color: C.inkSoft }}>
          后厨在做：{kitchen.map(k => { const end = parseGameTime(k.ready_at); const left = end !== null && nowMs !== null ? Math.max(0, Math.round((end - nowMs) / 1000)) : null; return `${k.by_name ?? players.find(p => p.id === k.by)?.name ?? k.by ?? ''} · ${k.name ?? k.dish}${left !== null ? `（${left} 秒）` : ''}` }).join('；')}
        </div>
      )}
    </div>
  )
}
