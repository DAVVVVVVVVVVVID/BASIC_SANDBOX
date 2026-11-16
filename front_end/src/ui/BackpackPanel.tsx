import { useMemo, useState } from 'react'
import { useGameStore } from '../store/gameStore'
import { sendAction } from '../api/world'
import { itemMeta, normalizeInventory, itemDisplayName, isPhysicalWork, type InventoryItem } from '../game/items'
import { gameNowMs, fridgeRows, fridgeTitle, supplyText, canEatHere, busyText, fmtMin, parseGameTime } from '../game/v11'
import type { GameObject } from '../types'

/**
 * W9 任务 3：操控页的金币与背包（`06-economy.md`）。≤ 10 格；物品可「吃 / 用」「送」（给相邻的人）「卖」（在卖鱼摊 / 柜台旁）；
 * 站在商店物品（柜台 / 卖鱼摊，带 `shop[]`）旁时列出可买的东西。动作全部 `POST /action {type: buy|eat|give|sell}`，
 * payload 字段名（item / object_id / target）是**假设**，B 的 api-spec 落地后对齐；成败以后端回包为准。
 */
export default function BackpackPanel({ embedded = false }: { embedded?: boolean } = {}) {
  const player = useGameStore((s) => s.player)
  const objects = useGameStore((s) => s.objects)
  const players = useGameStore((s) => s.players)
  const [busy, setBusy] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const inv = useMemo(() => normalizeInventory(player?.inventory), [player?.inventory])
  const worldState = useGameStore((s) => s.worldState)
  if (!player) return null
  const gold = typeof player.gold === 'number' ? player.gold : null
  const near = (o: { position: { x: number; y: number }; tiles?: { x: number; y: number }[] }) => (o.tiles?.length ? o.tiles : [o.position]).some(t => Math.abs(t.x - player.position.x) + Math.abs(t.y - player.position.y) <= 1)
  const shop: GameObject | undefined = objects.find(o => Array.isArray(o.shop) && o.shop.length > 0 && near(o))
  const neighbours = players.filter(p => p.id !== player.id && p.online !== false && near(p))
  // world-v1.1：旁边的冰箱 / 灶台 / 餐桌
  const nowMs = gameNowMs(worldState)
  const fridge = objects.find(o => o.type === 'fridge' && near(o))
  const stove = objects.find(o => o.type === 'stove' && near(o))
  const table = objects.find(o => o.dining && near(o))
  const KINDS_MAX = 10, PER_MAX = 20

  const act = async (label: string, type: string, payload: Record<string, unknown>) => {
    setBusy(label); setMsg(null)
    try {
      const r = await sendAction(player.id, type, payload, { logLabel: label }) as unknown as { success?: boolean; message?: string; result?: { message?: string; reason?: string } }
      const text = r.message ?? r.result?.message ?? r.result?.reason ?? ''
      setMsg(`${r.success ? '✓' : '✗'} ${label}${text ? ` · ${text}` : ''}${!r.success && /insufficient_funds/i.test(JSON.stringify(r)) ? ' · 💸 钱不够' : ''}`)
    } catch (e) { setMsg(`✗ ${label} · ${(e as Error).message}`) }
    finally { setBusy(null) }
  }
  const slots: (InventoryItem | null)[] = [...inv.slice(0, 10)]
  while (slots.length < 10) slots.push(null)

  return (
    <div style={{ position: 'absolute', left: 330, bottom: 16, width: 300, background: 'rgba(15,15,30,0.9)', border: '1px solid #4a5568', borderRadius: 8, color: '#e2e8f0', fontSize: 12, padding: '10px 12px', fontFamily: 'system-ui, "PingFang SC", sans-serif', userSelect: 'none', ...(embedded ? { position: 'static', top: 'auto', left: 'auto', right: 'auto', bottom: 'auto', width: 'auto', minWidth: 0, maxHeight: 'none', background: 'transparent', border: 'none', boxShadow: 'none', padding: 0 } : {}), }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <b style={{ color: '#90cdf4' }}>🎒 背包</b><span style={{ color: inv.filter(i => itemMeta(i.type, i.name).kind !== 'key').length >= KINDS_MAX ? '#fc8181' : '#718096', fontSize: 10 }}>{inv.filter(i => itemMeta(i.type, i.name).kind !== 'key').length}/{KINDS_MAX} 种 · 每种 ≤{PER_MAX}</span>
        <span style={{ marginLeft: 'auto', color: '#ffe9a8', fontWeight: 700 }}>💰 {gold === null ? '—' : gold}</span>
      </div>
      {gold === null && <div style={{ color: '#718096', fontSize: 10, marginTop: 2 }}>后端还没给 gold / inventory（B W10 任务 4）</div>}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 6, marginTop: 8 }}>
        {slots.map((it, i) => {
          const m = it ? itemMeta(it.type, it.name) : null
          return (
            <div key={i} title={it ? `${m!.label} ×${it.count}` : '空'} style={{ height: 46, background: '#1a1b2e', border: '1px solid #2d3748', borderRadius: 6, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
              {it && <><span style={{ fontSize: 18, ...(isPhysicalWork(m!) ? { background: '#2d3748', border: '1px solid #90cdf4', borderRadius: 4, padding: '0 3px', lineHeight: 1.1 } : {}), ...(m!.spoiled ? { filter: 'grayscale(1)', opacity: 0.6 } : {}) }}>{m!.icon}</span><span style={{ fontSize: 10, color: '#a0aec0' }}>{itemDisplayName(it).replace(/钥匙$/, '🔑').slice(0, 5)}</span>{it.count > 1 && <span style={{ position: 'absolute', right: 3, top: 1, fontSize: 10, color: it.count >= PER_MAX ? '#fc8181' : '#ffe9a8' }}>×{it.count}</span>}</>}
            </div>
          )
        })}
      </div>
      {inv.length > 0 && (
        <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 140, overflowY: 'auto' }}>
          {inv.map(it => {
            const m = itemMeta(it.type, it.name); const key = it.id ?? it.type
            return (
              <div key={key} style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                <span style={{ flex: 1 }}>{m.icon} {itemDisplayName(it)} ×{it.count}</span>
                {(m.kind === 'food' || /^(ingredients?|fish)$/.test(it.type)) && (table && canEatHere(table, it.type) ? <button disabled={!!busy} onClick={() => act(`吃 ${m.label}`, 'eat', { item: it.type, item_id: it.id, object_id: table.id })} style={sb}>吃</button> : <span title={table ? '这儿只能吃简餐' : 'world-v1.1：只能在餐桌 / 长椅旁吃'} style={{ fontSize: 10, color: '#718096' }}>{table ? '这儿不能吃' : '到餐桌吃'}</span>)}
                {fridge && (m.kind === 'food' || m.kind === 'material') && <button disabled={!!busy} onClick={() => act(`放 ${m.label}`, 'store', { item: it.type, qty: 1, object_id: fridge.id })} style={sb}>放冰箱</button>}
                {stove && !stove.cooking && (it.type === 'ingredients' || it.type === 'ingredient' || it.type === 'fish') && <button disabled={!!busy} onClick={() => act(`做 ${m.label}`, 'use', { objectId: stove.id, item: it.type, qty: 1 })} style={sb}>下厨</button>}
                {neighbours.map(n => <button key={n.id} disabled={!!busy} onClick={() => act(`送 ${itemDisplayName(it)} 给 ${n.name}`, 'give', { item: it.type, item_id: it.id, target: n.id, target_id: n.id, ...(typeof it.meta?.commission_id === 'string' ? { commission_id: it.meta.commission_id } : {}), ...(typeof it.meta?.door_id === 'string' ? { door_id: it.meta.door_id } : {}) })} style={sb}>送{n.name.slice(0, 2)}</button>)}
                {shop && <button disabled={!!busy} onClick={() => act(`卖 ${m.label}`, 'sell', { item: it.type, item_id: it.id, object_id: shop.id })} style={sb}>卖</button>}
              </div>
            )
          })}
        </div>
      )}
      {player.busy && <div style={{ marginTop: 6, color: '#9ae6b4', fontSize: 11 }}>{busyText(player.busy, nowMs)}</div>}
      {fridge && (
        <div style={{ marginTop: 8, borderTop: '1px solid #2d3748', paddingTop: 6 }}>
          <div style={{ color: '#90cdf4', marginBottom: 4 }}>{fridgeTitle(fridge)}</div>
          {fridgeRows(fridge, nowMs).length === 0 && <div style={{ color: '#718096', fontSize: 11 }}>空的（不会自动补货）</div>}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3, maxHeight: 110, overflowY: 'auto' }}>
            {fridgeRows(fridge, nowMs).map((r, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, color: r.spoiled ? '#718096' : '#e2e8f0' }}>
                <span style={{ flex: 1, ...(r.spoiled ? { filter: 'grayscale(1)' } : {}) }}>{r.icon} {r.name} ×{r.count}</span>
                <span style={{ fontSize: 11, color: r.spoiled ? '#fc8181' : r.days !== null && r.days <= 1 ? '#f6ad55' : '#718096' }}>{r.spoiled ? '坏了' : r.days !== null ? `剩 ${r.days} 天` : ''}</span>
                <button disabled={!!busy} onClick={() => act(`取 ${r.name}`, 'take', { item: r.item, qty: 1, object_id: fridge.id })} style={sb}>取</button>
              </div>
            ))}
          </div>
        </div>
      )}
      {stove && (
        <div style={{ marginTop: 8, borderTop: '1px solid #2d3748', paddingTop: 6, fontSize: 11 }}>
          <div style={{ color: '#90cdf4', marginBottom: 2 }}>🍳 {stove.name}</div>
          {stove.cooking ? (() => { const c = stove.cooking!; const ready = parseGameTime(c.ready_at); const rem = ready !== null && nowMs !== null ? Math.max(0, (ready - nowMs) / 1000) : (typeof c.ready_in_min === 'number' ? c.ready_in_min * 60 : null); return <div style={{ color: '#9ae6b4' }}>在做 {itemMeta(c.product).icon}{itemMeta(c.product).label} ×{c.portions}{rem !== null ? ` · 还要 ${fmtMin(rem)}` : ''}（{c.by === player.id ? '你' : players.find(p => p.id === c.by)?.name ?? c.by} · 中途离开食材白费）</div> })() : <div style={{ color: '#718096' }}>空着 · 背包里的食材 / 鱼点「下厨」（1 份 20 分钟，每多 1 份 +10）</div>}
        </div>
      )}
      {shop && (
        <div style={{ marginTop: 8, borderTop: '1px solid #2d3748', paddingTop: 6 }}>
          <div style={{ color: '#90cdf4', marginBottom: 4 }}>🛒 {shop.name}</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            {shop.shop!.filter(s => s.price !== null && s.price !== undefined || s.sell == null).map((s, i) => {
              const t = s.type ?? s.item ?? s.name ?? `item${i}`; const m = itemMeta(t, s.name)
              return (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ flex: 1 }}>{m.icon} {s.name ?? m.label}</span>
                  <span style={{ color: '#ffe9a8' }}>{s.price ?? m.price ?? '?'} 金币</span>
                  {(() => { const sup = supplyText(shop, t); return sup ? <span style={{ color: /卖完/.test(sup) ? '#fc8181' : '#718096', fontSize: 11 }}>{sup}</span> : typeof s.stock === 'number' ? <span style={{ color: s.stock > 0 ? '#718096' : '#fc8181', fontSize: 11 }}>{s.stock > 0 ? `余 ${s.stock}` : '卖完'}</span> : null })()}
                  <button disabled={!!busy || (gold !== null && (s.price ?? m.price ?? 0) > gold) || s.stock === 0} onClick={() => act(`买 ${s.name ?? m.label}`, 'buy', { item: t, object_id: shop.id, qty: 1 })} style={sb}>买</button>
                </div>
              )
            })}
          </div>
        </div>
      )}
      {msg && <div style={{ marginTop: 6, color: msg.startsWith('✓') ? '#68d391' : '#fc8181', fontSize: 11 }}>{msg}</div>}
    </div>
  )
}
const sb: React.CSSProperties = { background: '#2b6cb0', border: 'none', borderRadius: 4, color: '#fff', padding: '2px 7px', cursor: 'pointer', fontSize: 11 }
