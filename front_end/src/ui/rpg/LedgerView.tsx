import { useEffect, useState } from 'react'
import { useGameStore } from '../../store/gameStore'
import { apiGetOrNull } from '../../api/client'
import { normalizeLedger, summarize, entriesIn, demoLedger, KIND_ZH, type Ledger, type LedgerKind } from '../../game/ledger'
import { isShop } from '../../game/shop'
import { C } from './theme'

/**
 * 商店账本（商店系统第一期，shops-system.md §4）：导播视角（操控页）能看三家店；顶部切店、今天 / 近 7 天。
 * 数据：GET /shops/{id}/ledger?days=（**接口名待 B 的 read_ledger 草案**，404 = 还没开通）；`?shopdemo=1` 用样例看版式。只读。
 */
export const SHOP_DEMO = typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('shopdemo') === '1'
const FILTERS: (LedgerKind | 'all')[] = ['all', 'sale', 'purchase', 'recycle', 'lost', 'price']

export default function LedgerView({ shopId: initial }: { shopId: string }) {
  const objects = useGameStore((s) => s.objects)
  const today = useGameStore((s) => s.worldState?.date) ?? new Date().toISOString().slice(0, 10)
  const shops = objects.filter(isShop)
  const [shopId, setShopId] = useState(initial)
  const [range, setRange] = useState<'today' | 'week'>('today')
  const [kind, setKind] = useState<LedgerKind | 'all'>('all')
  const [ledger, setLedger] = useState<Ledger | null>(null)
  const [state, setState] = useState<'loading' | 'ok' | 'missing'>('loading')
  useEffect(() => {
    if (SHOP_DEMO) { setLedger(demoLedger(shopId, today)); setState('ok'); return }
    let stop = false
    setState('loading')
    const load = () => apiGetOrNull<unknown>(`/shops/${encodeURIComponent(shopId)}/ledger?days=7&view=admin`).then(r => {
      if (stop) return
      const l = r ? normalizeLedger(r, shopId) : null
      setLedger(l); setState(l ? 'ok' : 'missing')
    }).catch(() => { if (!stop) setState('missing') })
    load()
    const t = window.setInterval(load, 15_000)
    return () => { stop = true; window.clearInterval(t) }
  }, [shopId, today])
  const sum = ledger ? summarize(ledger, range) : null
  const rows = ledger ? entriesIn(ledger, range, kind) : []
  const tab = (on: boolean) => ({ fontSize: 12, padding: '2px 10px', borderRadius: 10, border: `1px solid ${on ? C.teal : '#E6DCCB'}`, background: on ? '#DDF3EE' : '#fff', color: on ? '#1F7A6F' : C.inkSoft, cursor: 'pointer' }) as const
  const money = (n: number) => `${n < 0 ? '−' : ''}¥${Math.abs(Math.round(n))}`
  return (
    <div data-testid="ledger" style={{ display: 'flex', flexDirection: 'column', gap: 8, color: C.ink, fontSize: 13 }}>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
        {shops.map(s => <button key={s.id} data-testid={`ledger-shop-${s.id}`} onClick={() => setShopId(s.id)} style={tab(s.id === shopId)}>{s.name}</button>)}
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
          <button onClick={() => setRange('today')} style={tab(range === 'today')} data-testid="ledger-today">今天</button>
          <button onClick={() => setRange('week')} style={tab(range === 'week')} data-testid="ledger-week">近 7 天</button>
        </span>
      </div>
      {SHOP_DEMO && <div style={{ fontSize: 11, color: '#8A6116' }}>样例数据（?shopdemo=1），等 B 的账本接口</div>}
      {state === 'loading' && <div style={{ color: C.inkSoft }}>读取中…</div>}
      {state === 'missing' && <div data-testid="ledger-missing" style={{ color: C.inkSoft, padding: 8 }}>账本接口还没开通（等沙盒的 read_ledger）</div>}
      {state === 'ok' && sum && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 6 }}>
            {([['收入', sum.revenue, '#1F7A6F'], ['成本', sum.cost, '#8A6116'], ['毛利', sum.gross, sum.gross >= 0 ? '#1F7A6F' : '#B23B2E'], ['流失', sum.lost, '#B23B2E']] as [string, number, string][]).map(([k, v, col]) => (
              <div key={k} style={{ background: 'rgba(255,255,255,0.7)', border: '1px solid #E6DCCB', borderRadius: 8, padding: '6px 8px', textAlign: 'center' }}>
                <div style={{ fontSize: 11, color: C.inkSoft }}>{k}</div>
                <div style={{ fontSize: 17, fontWeight: 700, color: col }}>{k === '流失' ? `${v} 位` : money(v)}</div>
              </div>
            ))}
          </div>
          {range === 'week' && sum.days.length > 1 && (
            <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr 1fr 1fr', columnGap: 10, rowGap: 2, fontSize: 12, background: 'rgba(255,255,255,0.5)', borderRadius: 8, padding: '6px 8px' }}>
              {['日期', '收入', '成本', '毛利'].map(h => <b key={h} style={{ color: C.inkSoft }}>{h}</b>)}
              {sum.days.map(d => [<span key={`${d.date}-d`}>{d.date.slice(5)}</span>, <span key={`${d.date}-r`}>{money(d.revenue)}</span>, <span key={`${d.date}-c`}>{money(d.cost)}</span>, <span key={`${d.date}-g`} style={{ color: d.gross >= 0 ? '#1F7A6F' : '#B23B2E' }}>{money(d.gross)}</span>])}
            </div>
          )}
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {FILTERS.map(f => <button key={f} onClick={() => setKind(f)} style={tab(kind === f)}>{f === 'all' ? '全部' : KIND_ZH[f].label}</button>)}
          </div>
          <div data-testid="ledger-rows" style={{ display: 'flex', flexDirection: 'column', gap: 3, maxHeight: 260, overflowY: 'auto' }}>
            {rows.length === 0 && <div style={{ color: C.inkSoft }}>这段时间没有记录</div>}
            {rows.map((e, i) => (
              <div key={i} style={{ display: 'flex', gap: 6, alignItems: 'baseline', padding: '3px 6px', borderBottom: '1px dashed #EEE4D4' }}>
                <span style={{ fontSize: 11, color: C.inkSoft, width: range === 'week' ? 72 : 38, flexShrink: 0 }}>{range === 'week' ? `${e.ts.slice(5, 10)} ${e.ts.slice(11, 16)}` : e.ts.slice(11, 16)}</span>
                <span style={{ flexShrink: 0 }}>{KIND_ZH[e.kind].icon}</span>
                <span style={{ flex: 1, minWidth: 0 }}>
                  <b>{KIND_ZH[e.kind].label}</b> {e.item}{e.qty > 1 ? ` ×${e.qty}` : ''}{e.unit !== null && e.kind !== 'price' ? ` @${e.unit}` : ''}
                  {e.who && <span style={{ color: C.inkSoft }}> · {e.who}</span>}
                  {e.note && <span style={{ color: e.kind === 'lost' ? '#B23B2E' : C.inkSoft }}> · {e.note}</span>}
                </span>
                {e.amount !== 0 && <span style={{ fontWeight: 700, color: e.amount > 0 ? '#1F7A6F' : '#8A6116', whiteSpace: 'nowrap' }}>{e.amount > 0 ? '+' : ''}{money(e.amount)}</span>}
              </div>
            ))}
          </div>
          {Object.keys(sum.stock).length > 0 && (
            <div style={{ fontSize: 12, color: C.inkSoft }}>日终库存：{Object.entries(sum.stock).map(([k, v]) => `${k} ${v}`).join(' · ')}</div>
          )}
        </>
      )}
    </div>
  )
}
