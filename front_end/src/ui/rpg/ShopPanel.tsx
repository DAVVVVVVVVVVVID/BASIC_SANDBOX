import { useMemo, useState } from 'react'
import { useGameStore } from '../../store/gameStore'
import { EventBus } from '../../game/EventBus'
import { sendAction } from '../../api/world'
import { normalizeInventory } from '../../game/items'
import { goodsRows, sellRows, distanceTo, NEAR_ENOUGH, shopFailText, type MetaChip } from '../../game/shop'
import { C } from './theme'
import { Chip } from './MetaChips'

/**
 * 商店面板（主播 11-19：点一下鱼摊 / 杂货店柜台 / 餐厅吧台直接弹出，不用先走过去再开背包）。
 * 上：这家在卖的（名称 / 价格 / 库存；逐条鱼显示品种 / 重量 / 品级 / 新鲜度）+「买」；下：我背包里这家收的 +「卖」。
 * 离太远只提示「走近一点」+「走过去」；打烊照后端 open / opensAt 显示营业时间。动作走 POST /action buy / sell，成败以回包为准。
 */
const chip = (c: MetaChip, i: number) => <Chip key={i} c={c} />

export default function ShopPanel({ objectId }: { objectId: string }) {
  const obj = useGameStore((s) => s.objects.find(o => o.id === objectId))
  const player = useGameStore((s) => s.player)
  const [busy, setBusy] = useState<string | null>(null)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const inv = useMemo(() => normalizeInventory(player?.inventory), [player?.inventory])
  if (!obj || !player) return <div style={{ color: C.inkSoft, padding: 12 }}>找不到这家店</div>
  const goods = goodsRows(obj), selling = sellRows(obj, inv)
  const dist = distanceTo(player.position, obj)
  const far = dist > NEAR_ENOUGH
  const gold = typeof player.gold === 'number' ? player.gold : null
  const hours = (obj.openHours ?? []).map(h => h.join('–')).join('、')
  const closed = obj.open === false

  const act = async (key: string, label: string, type: 'buy' | 'sell', payload: Record<string, unknown>) => {
    setBusy(key); setMsg(null)
    try {
      const r = await sendAction(player.id, type, { ...payload, object_id: obj.id, objectId: obj.id, qty: 1 }, { logLabel: label }) as unknown as { success?: boolean; reason?: string; result?: Record<string, unknown> }
      const res = r.result ?? {}
      if (r.success) setMsg({ ok: true, text: `${label}${typeof res.gold === 'number' ? ` · 余额 ${res.gold}` : ''}${typeof res.message === 'string' && res.message ? ` · ${res.message}` : ''}` })
      else setMsg({ ok: false, text: `${label}没成 · ${shopFailText(r.reason, res)}` })
    } catch (e) { setMsg({ ok: false, text: `${label}没成 · ${(e as Error).message}` }) }
    finally { setBusy(null) }
  }
  const walk = () => { const t = (obj.tiles && obj.tiles.length ? obj.tiles : [obj.position])[0]; EventBus.emit('walk-to', { x: t.x, y: t.y }) }

  return (
    <div data-testid="shop-panel" style={{ display: 'flex', flexDirection: 'column', gap: 10, color: C.ink, fontSize: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 12, color: closed ? '#B23B2E' : C.inkSoft }} data-testid="shop-hours">
          {closed ? `已打烊${obj.opensAt ? ` · ${obj.opensAt} 开门` : ''}` : '营业中'}{hours ? ` · 营业时间 ${hours}` : ''}
        </span>
        <span style={{ marginLeft: 'auto', fontWeight: 700, color: '#8A6116' }}>💰 {gold ?? '—'}</span>
      </div>
      {far && (
        <div data-testid="shop-far" style={{ display: 'flex', alignItems: 'center', gap: 8, background: '#FBEBC9', border: '1px solid #F2B84B', borderRadius: 8, padding: '6px 10px', fontSize: 13 }}>
          <span style={{ flex: 1 }}>离太远了，走近一点（还差 {dist - NEAR_ENOUGH} 格）</span>
          <button className="k" onClick={walk} data-testid="shop-walk" style={{ minHeight: 34 }}>走过去</button>
        </div>
      )}
      <section>
        <div style={{ fontWeight: 700, marginBottom: 4 }}>在卖的</div>
        {goods.length === 0 && <div style={{ color: C.inkSoft, fontSize: 13 }}>这家现在不卖东西</div>}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {goods.map(g => {
            const soldOut = g.stock === 0
            return (
              <div key={g.key} data-testid={`shop-goods-${g.item}`} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px', borderRadius: 8, background: 'rgba(255,255,255,0.6)', border: '1px solid #E6DCCB', opacity: soldOut ? 0.6 : 1 }}>
                <span style={{ fontSize: 20 }}>{g.icon}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'baseline', flexWrap: 'wrap' }}><b>{g.name}</b>{g.chips.map(chip)}</div>
                  <div style={{ fontSize: 12, color: C.inkSoft }}>{g.stock === null ? '' : soldOut ? '卖完了' : `余 ${g.stock}`}</div>
                </div>
                <span style={{ fontWeight: 700, color: '#8A6116', whiteSpace: 'nowrap' }}>{g.price} 金币</span>
                <button className="k teal" data-testid={`shop-buy-${g.item}`} disabled={!!busy || soldOut} onClick={() => act(g.key, `买 ${g.name}`, 'buy', { item: g.item, ...(g.itemId ? { item_id: g.itemId } : {}) })} style={{ minWidth: 56, minHeight: 36 }}>{busy === g.key ? '…' : '买'}</button>
              </div>
            )
          })}
        </div>
      </section>
      <section>
        <div style={{ fontWeight: 700, marginBottom: 4 }}>我能卖给这家的</div>
        {selling.length === 0 && <div style={{ color: C.inkSoft, fontSize: 13 }}>{(obj.shop ?? []).some(s => typeof s.sell === 'number') ? '背包里没有这家收的东西' : '这家不收东西'}</div>}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {selling.map(s => (
            <div key={s.key} data-testid={`shop-sell-row-${s.item}`} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px', borderRadius: 8, background: 'rgba(255,255,255,0.6)', border: '1px solid #E6DCCB' }}>
              <span style={{ fontSize: 20 }}>{s.icon}</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', gap: 6, alignItems: 'baseline', flexWrap: 'wrap' }}><b>{s.name}</b>{s.chips.map(chip)}</div>
                <div style={{ fontSize: 12, color: C.inkSoft }}>背包里 {s.count}</div>
              </div>
              <span style={{ fontWeight: 700, color: '#1F7A6F', whiteSpace: 'nowrap' }}>收 {s.sell}</span>
              <button className="k" data-testid={`shop-sell-${s.item}`} disabled={!!busy} onClick={() => act(s.key, `卖 ${s.name}`, 'sell', { item: s.item, ...(s.itemId ? { item_id: s.itemId } : {}) })} style={{ minWidth: 56, minHeight: 36 }}>{busy === s.key ? '…' : '卖'}</button>
            </div>
          ))}
        </div>
      </section>
      {msg && <div data-testid="shop-msg" style={{ fontSize: 13, color: msg.ok ? '#1F7A6F' : '#B23B2E' }}>{msg.ok ? '✓ ' : '✗ '}{msg.text}</div>}
    </div>
  )
}
