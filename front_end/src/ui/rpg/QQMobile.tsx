import { useMemo, useState, type ReactNode } from 'react'
import type { QQContact, QQMessage } from '../../api/qq'
import { msgClock } from '../../api/qq'
import { itemMeta } from '../../game/items'
import type { QQDesktopProps } from './QQDesktop'

/**
 * QQ 三期修正（主播 11-16 13:xx，qq-redo.md「三期修正」）：手机壳（kit phone_shell）里放照手机 QQ 的界面。
 * 消息页（顶栏 + 搜索 + 白底无框行 + 底部 Tab）/ 聊天页（滑入；‹ 网名 ≡；#F5F6F7 底；白 / #12B7F5 气泡；输入栏）/ 联系人页（分组折叠）。
 * 纯展示层，状态与逻辑在 QQPanel（props 与桌面版同一套）。
 */
const BLUE = '#12B7F5', RED = '#FF4D4F'
const F = { fontFamily: '-apple-system, "PingFang SC", "Microsoft YaHei", "Segoe UI", system-ui, sans-serif' } as const
const avatar = (key: string, size: number, dot = false) => (
  <span style={{ position: 'relative', display: 'inline-block', width: size, height: size, flexShrink: 0 }}>
    <img src={`assets/ui/qq/${key}_${size > 56 ? 112 : 56}.png`} width={size} height={size} alt="" style={{ borderRadius: '50%', objectFit: 'cover', background: '#eee', display: 'block' }} />
    {dot && <span style={{ position: 'absolute', right: -1, bottom: -1, width: 9, height: 9, borderRadius: 5, background: '#52c41a', border: '2px solid #fff' }} />}
  </span>
)
function qqTime(m: QQMessage, gameDate: string | undefined): string {
  const t = m.gameTime || m.ts || ''; const d = t.slice(0, 10), hm = msgClock(m)
  if (!gameDate || !/^\d{4}-\d{2}-\d{2}$/.test(d) || d === gameDate) return hm
  const day = (s: string) => Math.floor(Date.parse(s + 'T00:00:00Z') / 86400000); const diff = day(gameDate) - day(d)
  if (diff === 1) return '昨天'
  if (diff > 1 && diff < 7) return ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][new Date(d + 'T00:00:00Z').getUTCDay()]
  return d.slice(5)
}
const minutesOf = (m: QQMessage) => { const t = m.gameTime || m.ts || ''; return Date.parse(t.length <= 19 ? t + 'Z' : t) / 60000 }
const I = {
  msg: <path d="M4 5h16v11H9l-5 4V5z" />,
  people: <><circle cx="9" cy="8" r="3.2" /><path d="M3.5 19c0-3 2.5-5 5.5-5s5.5 2 5.5 5" /><circle cx="17" cy="9" r="2.5" /><path d="M15.5 14.5c2.8 0 5 1.8 5 4.5" /></>,
  feed: <><circle cx="12" cy="12" r="8.5" /><path d="M12 7v5l3.5 2" /></>,
  search: <><circle cx="11" cy="11" r="6" /><path d="M20 20l-4.2-4.2" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  back: <path d="M15 5l-7 7 7 7" />,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  mic: <><rect x="9" y="3.5" width="6" height="11" rx="3" /><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3M9 21h6" /></>,
  smile: <><circle cx="12" cy="12" r="8.5" /><path d="M8.5 14c1 1.5 2.2 2.2 3.5 2.2s2.5-.7 3.5-2.2M9.5 10h.01M14.5 10h.01" /></>,
  chevron: <path d="M9 6l6 6-6 6" />,
}
const Icon = ({ d, color = '#333', size = 22 }: { d: ReactNode; color?: string; size?: number }) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">{d}</svg>

export default function QQMobile(p: QQDesktopProps & { fullscreen?: boolean; kb?: number }) {
  const [tab, setTab] = useState<'msg' | 'contacts'>('msg')
  const [menu, setMenu] = useState(false)
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})
  const peerC = p.contacts.find(c => c.id === p.peer) ?? null
  const thread = useMemo(() => (peerC ? p.threadOf(peerC) : []), [peerC, p])
  const groups = useMemo(() => {
    const g: Record<'人物' | '机构' | '群', QQContact[]> = { 人物: [], 机构: [], 群: [] }
    for (const c of p.contacts) { const k = p.keyOf(c); (c.group || k === 'livegroup' ? g.群 : k === 'townhall' ? g.机构 : g.人物).push(c) }
    return g
  }, [p])
  const row = (c: QQContact, withPreview: boolean) => {
    const n = p.nickOf(c), ms = p.threadOf(c), last = ms[ms.length - 1]
    const preview = last ? `${c.group && !p.isMine(last) ? `${last.fromName ?? p.nameOf(last.from)}: ` : ''}${last.kind === 'file' ? '[文件]' : last.text ?? ''}` : ''
    return (
      <div key={c.id} data-testid={`qq-contact-${c.id}`} onClick={() => p.setPeer(c.id)} style={{ display: 'flex', alignItems: 'center', gap: 12, height: withPreview ? 68 : 56, padding: '0 14px', cursor: 'pointer', background: '#fff' }}>
        <span style={{ position: 'relative', flexShrink: 0 }}>
          {avatar(p.keyOf(c), 48)}
          {c.unread > 0 && <span style={{ position: 'absolute', right: -5, top: -4, minWidth: 18, height: 18, lineHeight: '18px', borderRadius: 9, background: RED, color: '#fff', fontSize: 11, textAlign: 'center', padding: '0 5px', border: '2px solid #fff' }}>{c.unread > 99 ? '99+' : c.unread}</span>}
        </span>
        <div style={{ flex: 1, minWidth: 0, height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center', borderBottom: '1px solid #EEE' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, minWidth: 0 }}>
            <span style={{ fontSize: 16, color: '#000', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{n.nick}</span>
            {n.name && n.name !== n.nick && <span style={{ fontSize: 12, color: '#999', whiteSpace: 'nowrap', flexShrink: 0 }}>{n.name}</span>}
            {withPreview && <span style={{ marginLeft: 'auto', fontSize: 12, color: '#999', whiteSpace: 'nowrap', flexShrink: 0 }}>{last ? qqTime(last, p.gameDate) : ''}</span>}
          </div>
          {withPreview && <div style={{ fontSize: 13, color: '#999', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', marginTop: 4, minHeight: 17 }}>{preview}</div>}
        </div>
      </div>
    )
  }
  const tabBtn = (key: 'msg' | 'contacts' | 'feed', d: ReactNode, label: string, badge?: number) => {
    const active = tab === key, on = key !== 'feed'
    return (
      <button key={key} onClick={on ? () => { setTab(key as 'msg' | 'contacts'); p.setPeer(null) } : undefined} title={on ? label : `${label}（还没开通）`} style={{ flex: 1, border: 'none', background: 'none', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, cursor: on ? 'pointer' : 'default', position: 'relative', opacity: on ? 1 : 0.5, padding: 0 }}>
        <Icon d={d} color={active ? BLUE : '#666'} size={24} />
        <span style={{ fontSize: 11, color: active ? BLUE : '#666' }}>{label}</span>
        {badge ? <span style={{ position: 'absolute', left: 'calc(50% + 6px)', top: -2, minWidth: 16, height: 16, lineHeight: '16px', borderRadius: 8, background: RED, color: '#fff', fontSize: 10, padding: '0 4px', textAlign: 'center' }}>{badge > 99 ? '99+' : badge}</span> : null}
      </button>
    )
  }
  return (
    <div onClick={p.fullscreen ? undefined : p.onClose} onKeyDown={e => { if (e.key === 'Escape') p.onClose() }} style={{ position: 'fixed', inset: 0, background: p.fullscreen ? '#F5F6F7' : 'rgba(0,0,0,0.35)', zIndex: 300, display: 'flex', alignItems: 'center', justifyContent: 'center', ...F }}>
      <div onClick={e => e.stopPropagation()} data-testid="qq-phone" style={p.fullscreen ? { position: 'absolute', inset: 0, color: '#000', fontSize: 15, userSelect: 'none' } : { width: 374, height: 'min(720px, 92vh)', position: 'relative', color: '#000', fontSize: 14, userSelect: 'none' }}>
        {!p.fullscreen && <div style={{ position: 'absolute', inset: 0, borderWidth: 28, borderStyle: 'solid', borderColor: 'transparent', borderImage: 'url(assets/ui/kit/phone_shell.png) 60 fill / 28px stretch', imageRendering: 'pixelated', pointerEvents: 'none' }} />}
        <div style={p.fullscreen ? { position: 'absolute', inset: 0, paddingTop: 'env(safe-area-inset-top, 0px)', paddingBottom: `calc(env(safe-area-inset-bottom, 0px) + ${p.kb ?? 0}px)`, background: '#F5F6F7', overflow: 'hidden', display: 'flex', flexDirection: 'column' } : { position: 'absolute', left: 14, right: 14, top: 18, bottom: 22, background: '#F5F6F7', borderRadius: 18, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          {p.available === false && <div style={{ padding: 16, color: '#999' }}>QQ 还没开通</div>}
          {/* ── 消息 / 联系人 页 ── */}
          {!peerC && (
            <>
              <div style={{ background: '#fff', display: 'flex', alignItems: 'center', padding: '10px 14px 8px', gap: 10 }}>
                {p.fullscreen && <button onClick={p.onClose} data-testid="qq-exit" title="返回" style={{ background: 'none', border: 'none', padding: 2, cursor: 'pointer', lineHeight: 0 }}><Icon d={I.back} size={24} /></button>}
                {avatar(p.myKey, 32, true)}
                <b style={{ flex: 1, textAlign: 'center', fontSize: 17 }}>{tab === 'msg' ? '消息' : '联系人'}</b>
                <button title="还没开通" style={{ background: 'none', border: 'none', padding: 0, cursor: 'default', lineHeight: 0 }}><Icon d={I.plus} size={22} /></button>
              </div>
              <div style={{ background: '#fff', padding: '0 14px 8px' }}>
                <div style={{ background: '#F2F3F5', borderRadius: 18, height: 34, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, color: '#999', fontSize: 14 }}><Icon d={I.search} color="#999" size={16} />搜索</div>
              </div>
              <div style={{ flex: 1, overflowY: 'auto', background: '#fff' }}>
                {tab === 'msg' && p.contacts.map(c => row(c, true))}
                {tab === 'msg' && p.contacts.length === 0 && <div style={{ padding: 24, color: '#999', textAlign: 'center' }}>没有会话</div>}
                {tab === 'contacts' && (['人物', '机构', '群'] as const).map(g => groups[g].length ? (
                  <div key={g}>
                    <div onClick={() => setCollapsed(s => ({ ...s, [g]: !s[g] }))} style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '10px 14px 6px', fontSize: 13, color: '#666', cursor: 'pointer', background: '#F5F6F7' }}>
                      <span style={{ display: 'inline-block', transform: collapsed[g] ? 'rotate(0)' : 'rotate(90deg)', transition: 'transform 120ms' }}><Icon d={I.chevron} color="#999" size={14} /></span>{g}<span style={{ color: '#aaa', marginLeft: 'auto' }}>{groups[g].length}</span>
                    </div>
                    {!collapsed[g] && groups[g].map(c => row(c, false))}
                  </div>
                ) : null)}
              </div>
              <div style={{ height: 56, background: '#fff', borderTop: '1px solid #EEE', display: 'flex', alignItems: 'center' }}>
                {tabBtn('msg', I.msg, '消息', p.totalUnread)}
                {tabBtn('contacts', I.people, '联系人')}
                {tabBtn('feed', I.feed, '动态')}
              </div>
            </>
          )}
          {/* ── 聊天页 ── */}
          {peerC && (
            <>
              <div style={{ background: '#fff', display: 'flex', alignItems: 'center', padding: '8px 10px', gap: 6, borderBottom: '1px solid #EEE', position: 'relative' }}>
                <button onClick={() => { p.setPeer(null); setMenu(false) }} data-testid="qq-back" title="返回" style={{ background: 'none', border: 'none', padding: 2, cursor: 'pointer', lineHeight: 0 }}><Icon d={I.back} size={24} /></button>
                <div style={{ flex: 1, minWidth: 0, textAlign: 'center' }}>
                  <div style={{ fontSize: 17, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.nickOf(peerC).nick}</div>
                  <div style={{ fontSize: 12, color: '#999' }}>{p.nickOf(peerC).name}{peerC.unread > 0 ? ` · ${peerC.unread} 条未读` : ''}</div>
                </div>
                <button onClick={() => setMenu(m => !m)} title="菜单" data-testid="qq-menu" style={{ background: 'none', border: 'none', padding: 2, cursor: 'pointer', lineHeight: 0 }}><Icon d={I.menu} size={24} /></button>
                {menu && (
                  <div style={{ position: 'absolute', right: 8, top: 44, background: '#fff', borderRadius: 8, boxShadow: '0 4px 16px rgba(0,0,0,0.18)', padding: 4, zIndex: 2, minWidth: 120 }}>
                    {!p.readOnly && <div onClick={() => { p.doRead(); setMenu(false) }} style={{ padding: '8px 12px', fontSize: 14, cursor: 'pointer' }}>标为已读</div>}
                    <div onClick={() => setMenu(false)} style={{ padding: '8px 12px', fontSize: 14, color: '#999', cursor: 'pointer' }}>取消</div>
                  </div>
                )}
              </div>
              <div ref={p.listRef} style={{ flex: 1, overflowY: 'auto', padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 10, background: '#F5F6F7' }}>
                {thread.length === 0 && <div style={{ color: '#bbb', textAlign: 'center', marginTop: 40 }}>还没有消息</div>}
                {thread.map((m, i) => {
                  const mine = p.isMine(m), prev = thread[i - 1]
                  const sep = !prev || Math.abs(minutesOf(m) - minutesOf(prev)) > 5
                  return (
                    <div key={m.id} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                      {sep && <div style={{ textAlign: 'center', fontSize: 11, color: '#bbb' }}>{qqTime(m, p.gameDate) === msgClock(m) ? msgClock(m) : `${qqTime(m, p.gameDate)} ${msgClock(m)}`}</div>}
                      <div style={{ display: 'flex', gap: 8, flexDirection: mine ? 'row-reverse' : 'row', alignItems: 'flex-start' }}>
                        {avatar(mine ? p.myKey : p.keyOf(peerC), 40)}
                        <div style={{ maxWidth: '72%', position: 'relative', background: mine ? BLUE : '#fff', color: mine ? '#fff' : '#111', borderRadius: 8, padding: '8px 12px', fontSize: 15, lineHeight: 1.45, wordBreak: 'break-word', whiteSpace: 'pre-wrap', marginTop: 6 }}>
                          <span style={{ position: 'absolute', top: 10, [mine ? 'right' : 'left']: -5, width: 0, height: 0, borderTop: '5px solid transparent', borderBottom: '5px solid transparent', [mine ? 'borderLeft' : 'borderRight']: `6px solid ${mine ? BLUE : '#fff'}` }} />
                          {m.kind === 'file' ? `${itemMeta(m.file?.type, m.file?.name).icon} 文件：${m.file?.name || itemMeta(m.file?.type).label}` : m.text}
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
              {!p.readOnly && (
                <div style={{ background: '#fff', borderTop: '1px solid #EEE', padding: '6px 10px 10px' }}>
                  {p.err && <div style={{ color: RED, fontSize: 12, marginBottom: 4 }}>{p.err}</div>}
                  <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8 }}>
                    <Icon d={I.mic} color="#333" size={24} />
                    <textarea value={p.text} onChange={e => p.setText(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); p.doSend() } }} rows={Math.min(3, Math.max(1, p.text.split('\n').length))} autoFocus
                      style={{ flex: 1, border: 'none', outline: 'none', resize: 'none', background: '#F2F3F5', borderRadius: 20, padding: '8px 14px', fontSize: 15, lineHeight: 1.4, color: '#111', ...F }} />
                    <Icon d={I.smile} color="#333" size={24} />
                    {p.text.trim()
                      ? <button onClick={p.doSend} style={{ background: BLUE, color: '#fff', border: 'none', borderRadius: 6, padding: '7px 12px', fontSize: 14, cursor: 'pointer' }}>发送</button>
                      : <Icon d={I.plus} color="#333" size={24} />}
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
