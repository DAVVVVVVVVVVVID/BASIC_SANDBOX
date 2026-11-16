import { useMemo, useState, type RefObject } from 'react'
import type { QQContact, QQMessage } from '../../api/qq'
import { msgClock } from '../../api/qq'
import { itemMeta } from '../../game/items'

/**
 * QQ 三期（主播 11-16 13:xx，总控 qq-redo.md「三期」）：仿 QQ NT 桌面版三栏「图标栏 | 消息列表 | 聊天区」。
 * 纯展示层：状态与拉取 / 读节流 / 方向过滤仍在 QQPanel（props 传入）。窗内系统无衬线字、QQ 配色；窗外不动。
 */
export interface QQDesktopProps {
  myKey: string                                  // 自己的头像 key（阿蝉）
  contacts: QQContact[]                           // 已排序
  peer: string | null
  setPeer: (id: string | null) => void
  threadOf: (c: QQContact) => QQMessage[]
  isMine: (m: QQMessage) => boolean
  nameOf: (id: string) => string
  keyOf: (c: QQContact) => string
  nickOf: (c: QQContact) => { nick: string; name: string }
  totalUnread: number
  text: string
  setText: (t: string) => void
  doSend: () => void
  doRead: () => void
  err: string | null
  readOnly: boolean
  listRef: RefObject<HTMLDivElement>
  gameDate: string | undefined                    // worldState.date "YYYY-MM-DD"
  available: boolean | null
  onClose: () => void
}

const BLUE = '#0099ff'
const avatar = (key: string, size: number) => <img src={`assets/ui/qq/${key}_${size > 56 ? 112 : 56}.png`} width={size} height={size} alt="" style={{ borderRadius: '50%', flexShrink: 0, objectFit: 'cover', background: '#eee' }} />

/** 消息时间（照 QQ）：今天 HH:MM / 昨天 / 周几 / MM-DD；以游戏日期为「今天」 */
function qqTime(m: QQMessage, gameDate: string | undefined): string {
  const t = m.gameTime || m.ts || ''
  const d = t.slice(0, 10), hm = msgClock(m)
  if (!gameDate || !/^\d{4}-\d{2}-\d{2}$/.test(d)) return hm
  if (d === gameDate) return hm
  const day = (s: string) => Math.floor(Date.parse(s + 'T00:00:00Z') / 86400000)
  const diff = day(gameDate) - day(d)
  if (diff === 1) return '昨天'
  if (diff > 1 && diff < 7) return ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][new Date(d + 'T00:00:00Z').getUTCDay()]
  return d.slice(5)
}
const minutesOf = (m: QQMessage) => { const t = m.gameTime || m.ts || ''; return Date.parse(t.length <= 19 ? t + 'Z' : t) / 60000 }

/* 内联 SVG 线框图标（1.5px，灰 #666，选中 #0099ff） */
const I = {
  msg: <path d="M4 5h16v11H9l-5 4V5z" />,
  people: <><circle cx="9" cy="8" r="3.2" /><path d="M3.5 19c0-3 2.5-5 5.5-5s5.5 2 5.5 5" /><circle cx="17" cy="9" r="2.5" /><path d="M15.5 14.5c2.8 0 5 1.8 5 4.5" /></>,
  star: <path d="M12 3.5l2.6 5.4 5.9.8-4.3 4.1 1.1 5.9L12 16.9l-5.3 2.8 1.1-5.9-4.3-4.1 5.9-.8z" />,
  hash: <path d="M9 4L7 20M17 4l-2 16M4 9h16M3 15h16" />,
  dots: <><circle cx="6" cy="12" r="1.3" /><circle cx="12" cy="12" r="1.3" /><circle cx="18" cy="12" r="1.3" /></>,
  gear: <><circle cx="12" cy="12" r="3" /><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1" /></>,
  search: <><circle cx="11" cy="11" r="6" /><path d="M20 20l-4.2-4.2" /></>,
  smile: <><circle cx="12" cy="12" r="8.5" /><path d="M8.5 14c1 1.5 2.2 2.2 3.5 2.2s2.5-.7 3.5-2.2M9.5 10h.01M14.5 10h.01" /></>,
  image: <><rect x="3.5" y="5" width="17" height="14" rx="2" /><path d="M3.5 16l5-5 4 4 3-3 5 5" /><circle cx="16" cy="9" r="1.3" /></>,
  scissors: <><circle cx="7" cy="7" r="2.5" /><circle cx="7" cy="17" r="2.5" /><path d="M9 8.5L20 17M9 15.5L20 7" /></>,
}
function Icon({ d, color = '#666', size = 22 }: { d: React.ReactNode; color?: string; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">{d}</svg>
}

export default function QQDesktop(p: QQDesktopProps) {
  const [tab, setTab] = useState<'msg' | 'contacts'>('msg')
  const [q, setQ] = useState('')
  const [hover, setHover] = useState<string | null>(null)
  const peerC = p.contacts.find(c => c.id === p.peer) ?? null
  const thread = useMemo(() => (peerC ? p.threadOf(peerC) : []), [peerC, p])
  const filtered = p.contacts.filter(c => !q.trim() || (p.nickOf(c).nick + p.nickOf(c).name + c.name).includes(q.trim()))
  const groups = useMemo(() => {
    const g: Record<'人物' | '机构' | '群', QQContact[]> = { 人物: [], 机构: [], 群: [] }
    for (const c of p.contacts) { const k = p.keyOf(c); (c.group || k === 'livegroup' ? g.群 : k === 'townhall' ? g.机构 : g.人物).push(c) }
    return g
  }, [p])
  const F = { fontFamily: '-apple-system, "PingFang SC", "Microsoft YaHei", "Segoe UI", system-ui, sans-serif' } as const
  const rail = (key: string, d: React.ReactNode, title: string, active: boolean, onClick?: () => void, badge?: number) => (
    <button key={key} onClick={onClick} title={onClick ? title : `${title}（还没开通）`} style={{ position: 'relative', width: 40, height: 40, border: 'none', background: active ? '#e8e8e8' : 'transparent', borderRadius: 8, cursor: onClick ? 'pointer' : 'default', display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: onClick ? 1 : 0.55 }}>
      <Icon d={d} color={active ? BLUE : '#666'} />
      {badge ? <span style={{ position: 'absolute', right: 2, top: 2, minWidth: 16, height: 16, lineHeight: '16px', borderRadius: 8, background: '#ff4d4f', color: '#fff', fontSize: 10, textAlign: 'center', padding: '0 4px' }}>{badge > 99 ? '99+' : badge}</span> : null}
    </button>
  )
  const row = (c: QQContact) => {
    const n = p.nickOf(c), ms = p.threadOf(c), last = ms[ms.length - 1], sel = c.id === p.peer
    const preview = last ? `${c.group && !p.isMine(last) ? `${last.fromName ?? p.nameOf(last.from)}: ` : ''}${last.kind === 'file' ? '[文件]' : last.text ?? ''}` : ''
    return (
      <div key={c.id} data-testid={`qq-contact-${c.id}`} onClick={() => { p.setPeer(c.id); setTab('msg') }} onMouseEnter={() => setHover(c.id)} onMouseLeave={() => setHover(null)}
        style={{ display: 'flex', alignItems: 'center', gap: 10, height: 64, padding: '0 12px', cursor: 'pointer', background: sel ? '#ececec' : hover === c.id ? '#f5f5f5' : 'transparent' }}>
        <div style={{ position: 'relative', flexShrink: 0 }}>
          {avatar(p.keyOf(c), 44)}
          {c.unread > 0 && <span style={{ position: 'absolute', right: -4, top: -4, minWidth: 18, height: 18, lineHeight: '18px', borderRadius: 9, background: '#ff4d4f', color: '#fff', fontSize: 11, textAlign: 'center', padding: '0 5px', border: '2px solid #fff' }}>{c.unread > 99 ? '99+' : c.unread}</span>}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, minWidth: 0 }}>
            <span style={{ fontSize: 14, fontWeight: 600, color: '#000', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{n.nick}</span>
            {n.name && n.name !== n.nick && <span style={{ fontSize: 12, color: '#999', whiteSpace: 'nowrap', flexShrink: 0 }}>{n.name}</span>}
            <span style={{ marginLeft: 'auto', fontSize: 12, color: '#999', whiteSpace: 'nowrap', flexShrink: 0 }}>{last ? qqTime(last, p.gameDate) : ''}</span>
          </div>
          <div style={{ fontSize: 12, color: '#999', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', marginTop: 3, minHeight: 16 }}>{preview}</div>
        </div>
      </div>
    )
  }
  return (
    <div onClick={p.onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.35)', zIndex: 300, display: 'flex', alignItems: 'center', justifyContent: 'center', ...F }}>
      <div data-testid="qq-phone" onClick={e => e.stopPropagation()} style={{ width: 840, height: 560, background: '#fff', borderRadius: 12, boxShadow: '0 12px 40px rgba(0,0,0,0.25)', display: 'flex', overflow: 'hidden', color: '#000', fontSize: 13, userSelect: 'none', position: 'relative' }}>
        <button onClick={p.onClose} title="关闭" data-testid="qq-close" onMouseEnter={e => (e.currentTarget.style.color = '#ff4d4f')} onMouseLeave={e => (e.currentTarget.style.color = '#999')} style={{ position: 'absolute', right: 10, top: 8, background: 'none', border: 'none', color: '#999', fontSize: 18, cursor: 'pointer', zIndex: 2, lineHeight: 1 }}>✕</button>
        {/* 左图标栏 */}
        <div style={{ width: 56, background: '#f7f7f7', display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '14px 0 10px', gap: 6 }}>
          <div style={{ position: 'relative', marginBottom: 10 }}>{avatar(p.myKey, 36)}<span style={{ position: 'absolute', right: -1, bottom: -1, width: 10, height: 10, borderRadius: 5, background: '#52c41a', border: '2px solid #f7f7f7' }} /></div>
          {rail('msg', I.msg, '消息', tab === 'msg', () => setTab('msg'), p.totalUnread)}
          {rail('contacts', I.people, '联系人', tab === 'contacts', () => setTab('contacts'))}
          {rail('star', I.star, '收藏', false)}
          {rail('hash', I.hash, '频道', false)}
          {rail('dots', I.dots, '小程序', false)}
          <div style={{ flex: 1 }} />
          {rail('gear', I.gear, '设置', false)}
        </div>
        {/* 中栏：消息列表 / 联系人 */}
        <div style={{ width: 280, borderRight: '1px solid #eee', display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          <div style={{ padding: '12px 12px 8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: '#f2f2f2', borderRadius: 6, padding: '5px 10px' }}>
              <Icon d={I.search} color="#999" size={16} />
              <input value={q} onChange={e => setQ(e.target.value)} placeholder="搜索" style={{ flex: 1, border: 'none', background: 'transparent', outline: 'none', fontSize: 13, color: '#333', ...F }} />
            </div>
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
            {p.available === false && <div style={{ padding: 16, color: '#999' }}>QQ 还没开通</div>}
            {tab === 'msg' && filtered.map(row)}
            {tab === 'msg' && filtered.length === 0 && p.available !== false && <div style={{ padding: 16, color: '#999', textAlign: 'center' }}>没有会话</div>}
            {tab === 'contacts' && (['人物', '机构', '群'] as const).map(g => groups[g].length ? (
              <div key={g}>
                <div style={{ padding: '8px 12px 2px', fontSize: 12, color: '#999' }}>{g} · {groups[g].length}</div>
                {groups[g].filter(c => filtered.includes(c)).map(row)}
              </div>
            ) : null)}
          </div>
        </div>
        {/* 右：聊天区 */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          {!peerC && <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#bbb', fontSize: 14 }}>选择一个会话</div>}
          {peerC && (
            <>
              <div style={{ height: 56, display: 'flex', alignItems: 'center', gap: 8, padding: '0 16px', borderBottom: '1px solid #eee' }}>
                <span style={{ fontSize: 15, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.nickOf(peerC).nick}</span>
                {p.nickOf(peerC).name && <span style={{ fontSize: 12, color: '#999', whiteSpace: 'nowrap' }}>{p.nickOf(peerC).name}</span>}
                {peerC.unread > 0 && <span style={{ fontSize: 12, color: '#ff4d4f' }}>{peerC.unread} 条未读</span>}
                {!p.readOnly && <button onClick={p.doRead} title="读消息占 1 游戏分钟（打开会话会自动读一次）" style={{ marginLeft: 'auto', marginRight: 28, background: 'none', border: 'none', color: BLUE, fontSize: 12, cursor: 'pointer' }}>标为已读</button>}
              </div>
              <div ref={p.listRef} style={{ flex: 1, overflowY: 'auto', padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
                {thread.length === 0 && <div style={{ color: '#bbb', textAlign: 'center', marginTop: 40 }}>还没有消息</div>}
                {thread.map((m, i) => {
                  const mine = p.isMine(m)
                  const prev = thread[i - 1]
                  const sep = !prev || Math.abs(minutesOf(m) - minutesOf(prev)) > 5
                  const who = mine ? p.myKey : p.keyOf(peerC)
                  return (
                    <div key={m.id} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                      {sep && <div style={{ textAlign: 'center', fontSize: 11, color: '#bbb' }}>{qqTime(m, p.gameDate) === msgClock(m) ? msgClock(m) : `${qqTime(m, p.gameDate)} ${msgClock(m)}`}</div>}
                      <div style={{ display: 'flex', gap: 8, flexDirection: mine ? 'row-reverse' : 'row', alignItems: 'flex-start' }}>
                        {avatar(who, 36)}
                        <div style={{ maxWidth: '70%', display: 'flex', flexDirection: 'column', alignItems: mine ? 'flex-end' : 'flex-start', gap: 4 }}>
                          {!mine && <span style={{ fontSize: 12, color: '#999' }}>{m.fromName ?? p.nameOf(m.from)}</span>}
                          <div style={{ background: mine ? BLUE : '#f0f0f0', color: mine ? '#fff' : '#111', borderRadius: 8, padding: '8px 12px', fontSize: 14, lineHeight: 1.5, wordBreak: 'break-word', whiteSpace: 'pre-wrap' }}>
                            {m.kind === 'file' ? `${itemMeta(m.file?.type, m.file?.name).icon} 文件：${m.file?.name || itemMeta(m.file?.type).label}` : m.text}
                          </div>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
              {!p.readOnly && (
                <div style={{ borderTop: '1px solid #eee', padding: '6px 12px 10px', display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <div style={{ display: 'flex', gap: 10, padding: '2px 2px 4px' }}><Icon d={I.smile} color="#888" size={20} /><Icon d={I.image} color="#888" size={20} /><Icon d={I.scissors} color="#888" size={20} /></div>
                  {p.err && <div style={{ color: '#ff4d4f', fontSize: 12 }}>{p.err}</div>}
                  <textarea value={p.text} onChange={e => p.setText(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); p.doSend() } }} rows={3} autoFocus
                    style={{ border: 'none', outline: 'none', resize: 'none', fontSize: 14, lineHeight: 1.5, color: '#111', background: 'transparent', ...F }} />
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ fontSize: 11, color: '#bbb' }}>Enter 发送 · Shift+Enter 换行</span>
                    <button onClick={p.doSend} disabled={!p.text.trim()} style={{ marginLeft: 'auto', background: p.text.trim() ? BLUE : '#ccc', color: '#fff', border: 'none', borderRadius: 4, padding: '6px 22px', fontSize: 14, cursor: p.text.trim() ? 'pointer' : 'default' }}>发送</button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
