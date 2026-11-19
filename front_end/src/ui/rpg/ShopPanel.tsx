import { useMemo, useState } from 'react'
import { useGameStore } from '../../store/gameStore'
import { EventBus } from '../../game/EventBus'
import { sendAction } from '../../api/world'
import { normalizeInventory } from '../../game/items'
import { goodsRows, sellRows, distanceTo, NEAR_ENOUGH, shopFailText, type MetaChip } from '../../game/shop'
import { C } from './theme'
import { Chip } from './MetaChips'
import LedgerView, { SHOP_DEMO } from './LedgerView'
import { GroceryExtras, RestaurantMenu } from './ShopExtras'
import { useObjectRefresh, refreshObjects } from '../../game/objectRefresh'
import { normalizeWarehouse, demoWarehouse, etaText } from '../../game/ledger'
import { itemMeta } from '../../game/items'

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
  const [tabSel, setTab] = useState<'menu' | 'goods' | 'ledger' | null>(null)
  const today = useGameStore((s) => s.worldState?.date)
  const inv = useMemo(() => normalizeInventory(player?.inventory), [player?.inventory])
  useObjectRefresh(4000)   // 库存 / 挂单 / 菜单 / 后厨 ws 不推，面板开着时补拉
  if (!obj || !player) return <div style={{ color: C.inkSoft, padding: 12 }}>找不到这家店</div>
  const goods = goodsRows(obj), selling = sellRows(obj, inv)
  const dist = distanceTo(player.position, obj)
  const far = dist > NEAR_ENOUGH
  const gold = typeof player.gold === 'number' ? player.gold : null
  const hours = (obj.openHours ?? []).map(h => h.join('–')).join('、')
  const closed = obj.open === false
  // 商店第二期：吧台（带 menu）多「菜单」页，打开默认就是菜单
  const isBar = Array.isArray((obj as unknown as { menu?: unknown }).menu)   // 只有后端真带了 menu 才出菜单页：② 上线前吧台照旧开货架
  const tabs = (isBar ? ['menu', 'goods', 'ledger'] : ['goods', 'ledger']) as ('menu' | 'goods' | 'ledger')[]
  const tab = tabSel && tabs.includes(tabSel) ? tabSel : tabs[0]

  const act = async (key: string, label: string, type: string, payload: Record<string, unknown>) => {
    setBusy(key); setMsg(null)
    try {
      const r = await sendAction(player.id, type, { ...payload, object_id: obj.id, objectId: obj.id, qty: 1 }, { logLabel: label }) as unknown as { success?: boolean; reason?: string; result?: Record<string, unknown> }
      const res = r.result ?? {}
      if (r.success) setMsg({ ok: true, text: `${label}${typeof res.gold === 'number' ? ` · 余额 ${res.gold}` : ''}${typeof res.message === 'string' && res.message ? ` · ${res.message}` : ''}` })
      else setMsg({ ok: false, text: `${label}没成 · ${shopFailText(r.reason, res)}` })
    } catch (e) { setMsg({ ok: false, text: `${label}没成 · ${(e as Error).message}` }) }
    finally { setBusy(null); void refreshObjects() }   // 买完立刻拉一次库存
  }
  // 商店第一期：库房库存 + 明早到货（字段待 B 定；?shopdemo=1 用样例）
  const wh = normalizeWarehouse(obj as unknown as Record<string, unknown>) ?? (SHOP_DEMO && obj.type === 'shop_counter' ? demoWarehouse(today ?? new Date().toISOString().slice(0, 10)) : null)
  const label = (k: string) => itemMeta(k, k).label
  const walk = () => { const t = (obj.tiles && obj.tiles.length ? obj.tiles : [obj.position])[0]; EventBus.emit('walk-to', { x: t.x, y: t.y }) }

  return (
    <div data-testid="shop-panel" style={{ display: 'flex', flexDirection: 'column', gap: 10, color: C.ink, fontSize: 14 }}>
      <div style={{ display: 'flex', gap: 6 }}>
        {tabs.map(t => <button key={t} data-testid={`shop-tab-${t}`} className={`k${tab === t ? ' teal' : ''}`} onClick={() => setTab(t)} style={{ minHeight: 32, fontSize: 13 }}>{t === 'menu' ? '🍲 菜单' : t === 'goods' ? '🛒 货架' : '📒 账本'}</button>)}
      </div>
      {tab === 'ledger' && <LedgerView shopId={obj.id} />}
      {tab === 'menu' && <>
        <RestaurantMenu obj={obj} busy={busy} act={act} />
        {msg && <div data-testid="shop-msg" style={{ fontSize: 13, color: msg.ok ? '#1F7A6F' : '#B23B2E' }}>{msg.ok ? '✓ ' : '✗ '}{msg.text}</div>}
      </>}
      {tab === 'goods' && <>
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
        {goods.length === 0 && <div style={{ color: C.inkSoft, fontSize: 13 }}>{Array.isArray(obj.listings) ? '摊上还没有鱼（老渔夫上货后才有）' : '这家现在不卖东西'}</div>}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {goods.map(g => {
            const soldOut = g.stock === 0
            return (
              <div key={g.key} data-testid={`shop-goods-${g.item}`} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px', borderRadius: 8, background: 'rgba(255,255,255,0.6)', border: '1px solid #E6DCCB', opacity: soldOut ? 0.6 : 1 }}>
                <span style={{ fontSize: 20 }}>{g.icon}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'baseline', flexWrap: 'wrap' }}><b>{g.name}</b>{g.chips.map(chip)}</div>
                  <div style={{ fontSize: 12, color: C.inkSoft }}>{g.stock === null ? '' : soldOut ? (obj.type === 'shop_counter' ? '卖完了，等进货' : '卖完了') : `余 ${g.stock}`}</div>
                </div>
                <span style={{ fontWeight: 700, color: '#8A6116', whiteSpace: 'nowrap' }}>{g.price} 金币</span>
                <button className="k teal" data-testid={`shop-buy-${g.item}`} disabled={!!busy || soldOut} onClick={() => act(g.key, `买 ${g.name}`, 'buy', { item: g.item, ...(g.listingId ? { listing_id: g.listingId } : {}), ...(g.itemId ? { item_id: g.itemId } : {}) })} style={{ minWidth: 56, minHeight: 36 }}>{busy === g.key ? '…' : '买'}</button>
              </div>
            )
          })}
        </div>
      </section>
      {wh && (
        <section data-testid="shop-warehouse" style={{ background: 'rgba(255,255,255,0.5)', border: '1px dashed #E6DCCB', borderRadius: 8, padding: '6px 10px' }}>
          <div style={{ fontWeight: 700, marginBottom: 4 }}>库房{wh.cap ? <span style={{ fontWeight: 400, fontSize: 12, color: C.inkSoft }}> · 每种上限 {wh.cap}</span> : null}</div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', fontSize: 13 }}>
            {Object.entries(wh.stock).map(([k, v]) => <span key={k}>{itemMeta(k, k).icon} {label(k)} <b>{v}</b>{wh.cap ? <span style={{ color: C.inkSoft }}>/{wh.cap}</span> : null}</span>)}
          </div>
          {wh.incoming.length > 0 && (
            <div data-testid="shop-incoming" style={{ marginTop: 6, fontSize: 13 }}>
              <span style={{ color: C.inkSoft }}>🚚 待到货：</span>
              {wh.incoming.map((i, n) => <span key={n} style={{ marginRight: 10 }}>{label(i.item)} ×{i.qty}<span style={{ color: C.inkSoft }}>（{etaText(i.eta, today) || '待送达'}）</span></span>)}
            </div>
          )}
        </section>
      )}
      {obj.type === 'shop_counter' && <GroceryExtras busy={busy} act={act} />}
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
              <span style={{ fontWeight: 700, color: '#1F7A6F', whiteSpace: 'nowrap', fontSize: s.sell === null ? 12 : undefined }}>{s.sell === null ? '按挂单价收' : `收 ${s.sell}`}</span>
              <button className="k" data-testid={`shop-sell-${s.item}`} disabled={!!busy} onClick={() => act(s.key, `卖 ${s.name}`, 'sell', { item: s.item, ...(s.fishId ? { fish_id: s.fishId } : {}), ...(s.itemId ? { item_id: s.itemId } : {}) })} style={{ minWidth: 56, minHeight: 36 }}>{busy === s.key ? '…' : '卖'}</button>
            </div>
          ))}
        </div>
      </section>
      {msg && <div data-testid="shop-msg" style={{ fontSize: 13, color: msg.ok ? '#1F7A6F' : '#B23B2E' }}>{msg.ok ? '✓ ' : '✗ '}{msg.text}</div>}
      </>}
    </div>
  )
}
