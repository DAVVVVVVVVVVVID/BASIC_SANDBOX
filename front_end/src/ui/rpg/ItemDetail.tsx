import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import type { InventoryItem } from '../../game/items'
import { itemMeta, itemDisplayName } from '../../game/items'
import { noteRows, cdSheetRows, receiptRows } from '../../game/school'
import { C, FONT } from './theme'

/**
 * 上课系统 v1：背包物品详情（课堂笔记全文 / 作业 CD 创作单 / 作业回执）。纯展示 GET /player.inventory[].meta，不发 read_item——跟随别人只读也能看。
 * portal 到 body，桌面居中卡片、手机近全屏；点遮罩 / ✕ / Esc 关。
 */
const OWNER_ZH: Record<string, string> = { whale: '鲸仔', claudine: '小克' }
/** holder = 持有人的 agent_id（笔记 meta.owner 也是 agent_id，不同 = 借来的） */
export default function ItemDetail({ item, holder, onClose }: { item: InventoryItem; holder?: string | null; onClose: () => void }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.stopPropagation(); onClose() } }
    window.addEventListener('keydown', k, true)
    return () => window.removeEventListener('keydown', k, true)
  }, [onClose])
  const m = item.meta ?? {}
  const meta = itemMeta(item.type, item.name)
  let sub = '', body: JSX.Element
  if (item.type === 'class_notes') {
    const rows = noteRows(m)
    const owner = typeof m.owner === 'string' ? m.owner : ''
    sub = [m.title, m.date, owner && holder && owner !== holder ? `借来的 · 原主 ${OWNER_ZH[owner] ?? owner}` : ''].filter(Boolean).join(' · ')
    const heard = rows.filter(r => !r.muted).length
    body = (
      <>
        <div style={{ fontSize: 12, color: C.inkSoft, marginBottom: 6 }}>记下 {heard}/{rows.length} 段</div>
        {rows.map(r => (
          <div key={r.i} style={{ display: 'flex', gap: 8, padding: '5px 0', borderBottom: '1px dashed #E6DCCB' }}>
            <span style={{ color: C.inkSoft, width: 18, flexShrink: 0, textAlign: 'right' }}>{r.i}</span>
            <span style={{ whiteSpace: 'pre-wrap', lineHeight: 1.55, ...(r.muted ? { color: '#A89A88', fontStyle: 'italic' } : {}) }}>{r.text}</span>
          </div>
        ))}
        {rows.length === 0 && <div style={{ color: C.inkSoft }}>这本笔记是空的</div>}
      </>
    )
  } else if (item.type === 'homework_receipt') {
    body = <Table rows={receiptRows(m).map(r => ({ label: r.label, value: r.value, warn: r.warn }))} />
  } else {
    const rows = cdSheetRows(m)
    sub = typeof m.by === 'string' ? `作者 ${m.by}` : ''
    body = rows.length ? (
      <>
        <Table rows={rows.filter(r => !r.long)} />
        {rows.filter(r => r.long).map(r => (
          <div key={r.key} style={{ marginTop: 8 }}>
            <div style={{ fontSize: 12, color: C.inkSoft, marginBottom: 2 }}>{r.label}</div>
            <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6, background: '#fff', border: '1px solid #E6DCCB', borderRadius: 6, padding: '6px 8px' }}>{r.value}</div>
          </div>
        ))}
      </>
    ) : <div style={{ color: C.inkSoft }}>这张 CD 没有创作单</div>
  }
  return createPortal(
    <div onClick={onClose} data-testid="item-detail-mask" style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.35)', zIndex: 400, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div onClick={e => e.stopPropagation()} data-testid="item-detail" className="rpg" style={{ width: 'min(520px, 94vw)', maxHeight: 'min(80vh, 720px)', display: 'flex', flexDirection: 'column', background: C.cream, border: `3px solid ${C.sky}`, borderRadius: 12, boxShadow: `4px 4px 0 ${C.shadow}`, color: C.ink, fontFamily: FONT, fontSize: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px', borderBottom: '1px solid #E6DCCB' }}>
          <span style={{ fontSize: 22 }}>{meta.icon}</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <b style={{ fontSize: 16 }}>{itemDisplayName(item)}</b>
            {sub && <div style={{ fontSize: 12, color: C.inkSoft, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{sub}</div>}
          </div>
          <button className="closex" onClick={onClose} title="关闭" data-testid="item-detail-close">✕</button>
        </div>
        <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '8px 14px 14px', WebkitOverflowScrolling: 'touch' } as React.CSSProperties}>{body}</div>
      </div>
    </div>,
    document.body,
  )
}

function Table({ rows }: { rows: { label: string; value: string; warn?: boolean }[] }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', columnGap: 12, rowGap: 4 }}>
      {rows.map(r => [
        <span key={`${r.label}-l`} style={{ color: C.inkSoft, fontSize: 13 }}>{r.label}</span>,
        <span key={`${r.label}-v`} style={{ color: r.warn ? '#D9534F' : C.ink, wordBreak: 'break-word' }}>{r.value}</span>,
      ])}
    </div>
  )
}
