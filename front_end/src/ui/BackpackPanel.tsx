import { useMemo, useState } from 'react'
import { useGameStore } from '../store/gameStore'
import { sendAction } from '../api/world'
import { itemMeta, normalizeInventory, type InventoryItem } from '../game/items'
import type { GameObject } from '../types'

/**
 * W9 任务 3：操控页的金币与背包（`06-economy.md`）。≤ 10 格；物品可「吃 / 用」「送」（给相邻的人）「卖」（在卖鱼摊 / 柜台旁）；
 * 站在商店物品（柜台 / 卖鱼摊，带 `shop[]`）旁时列出可买的东西。动作全部 `POST /action {type: buy|eat|give|sell}`，
 * payload 字段名（item / object_id / target）是**假设**，B 的 api-spec 落地后对齐；成败以后端回包为准。
 */
export default function BackpackPanel() {
  const player = useGameStore((s) => s.player)
  const objects = useGameStore((s) => s.objects)
  const players = useGameStore((s) => s.players)
  const [busy, setBusy] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const inv = useMemo(() => normalizeInventory(player?.inventory), [player?.inventory])
  if (!player) return null
  const gold = typeof player.gold === 'number' ? player.gold : null
  const near = (o: { position: { x: number; y: number }; tiles?: { x: number; y: number }[] }) => (o.tiles?.length ? o.tiles : [o.position]).some(t => Math.abs(t.x - player.position.x) + Math.abs(t.y - player.position.y) <= 1)
  const shop: GameObject | undefined = objects.find(o => Array.isArray(o.shop) && o.shop.length > 0 && near(o))
  const neighbours = players.filter(p => p.id !== player.id && p.online !== false && near(p))

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
    <div style={{ position: 'absolute', left: 330, bottom: 16, width: 300, background: 'rgba(15,15,30,0.9)', border: '1px solid #4a5568', borderRadius: 8, color: '#e2e8f0', fontSize: 12, padding: '10px 12px', fontFamily: 'system-ui, "PingFang SC", sans-serif', userSelect: 'none' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <b style={{ color: '#90cdf4' }}>🎒 背包</b>
        <span style={{ marginLeft: 'auto', color: '#ffe9a8', fontWeight: 700 }}>💰 {gold === null ? '—' : gold}</span>
      </div>
      {gold === null && <div style={{ color: '#718096', fontSize: 10, marginTop: 2 }}>后端还没给 gold / inventory（B W10 任务 4）</div>}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 6, marginTop: 8 }}>
        {slots.map((it, i) => {
          const m = it ? itemMeta(it.type, it.name) : null
          return (
            <div key={i} title={it ? `${m!.label} ×${it.count}` : '空'} style={{ height: 46, background: '#1a1b2e', border: '1px solid #2d3748', borderRadius: 6, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
              {it && <><span style={{ fontSize: 18 }}>{m!.icon}</span><span style={{ fontSize: 10, color: '#a0aec0' }}>{(it.name ?? m!.label).slice(0, 4)}</span>{it.count > 1 && <span style={{ position: 'absolute', right: 3, top: 1, fontSize: 10, color: '#ffe9a8' }}>×{it.count}</span>}</>}
            </div>
          )
        })}
      </div>
      {inv.length > 0 && (
        <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 120, overflowY: 'auto' }}>
          {inv.map(it => {
            const m = itemMeta(it.type, it.name); const key = it.id ?? it.type
            return (
              <div key={key} style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                <span style={{ flex: 1 }}>{m.icon} {it.name ?? m.label} ×{it.count}</span>
                {(m.kind === 'food') && <button disabled={!!busy} onClick={() => act(`吃 ${m.label}`, 'eat', { item: it.type, item_id: it.id })} style={sb}>吃</button>}
                {neighbours.map(n => <button key={n.id} disabled={!!busy} onClick={() => act(`送 ${m.label} 给 ${n.name}`, 'give', { item: it.type, item_id: it.id, target: n.id, target_id: n.id, ...(typeof it.meta?.commission_id === 'string' ? { commission_id: it.meta.commission_id } : {}) })} style={sb}>送{n.name.slice(0, 2)}</button>)}
                {shop && <button disabled={!!busy} onClick={() => act(`卖 ${m.label}`, 'sell', { item: it.type, item_id: it.id, object_id: shop.id })} style={sb}>卖</button>}
              </div>
            )
          })}
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
                  {typeof s.stock === 'number' && <span style={{ color: s.stock > 0 ? '#718096' : '#fc8181', fontSize: 11 }}>{s.stock > 0 ? `余 ${s.stock}` : '卖完'}</span>}
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
