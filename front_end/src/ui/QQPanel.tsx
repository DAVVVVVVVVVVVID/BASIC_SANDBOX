import { useEffect, useMemo, useRef, useState } from 'react'
import { useGameStore } from '../store/gameStore'
import { EventBus } from '../game/EventBus'
import { fetchContacts, fetchInbox, markRead, normalizeMessage, sendText, type QQContact, type QQMessage } from '../api/qq'
import { itemMeta } from '../game/items'   // 老消息里的 kind:file 条目仍要能显示

/**
 * W9 任务 2：QQ 面板（`docs/world-bible/08-phone-messaging.md`）。
 *   操控页（阿蝉）：联系人 / 会话 / 未读，发文字。world-v1.1 起歌 / 稿子是实体物品（CD / 稿子），文件传输取消，「发文件」已撤（B：kind:file 回 400 files_not_supported）。
 *   旁观页：只读，看跟随目标（鲸仔）的会话；`layout=live` 收成右上角图标 + 未读角标，点开看最近 5 条。
 * 数据：ws `qq` 事件即时推；每 4 s 轮询 /qq/inbox 兜底；后端还没有 /qq/*（404）时面板显示「后端未开通」而不是报错。
 */
interface Props { playerId: string; readOnly: boolean; compact?: boolean; style?: React.CSSProperties; /** 主播 11-15：手机样式（屏幕居中弹出，联系人 → 会话页），收起回角标 */ phone?: boolean }

const POLL_MS = 4000

export default function QQPanel({ playerId, readOnly, compact = false, style, phone = false }: Props) {
  const qq = useGameStore((s) => s.qq)
  const players = useGameStore((s) => s.players)
  const { setQQContacts, mergeQQMessages, markQQRead } = useGameStore.getState()
  const [peer, setPeer] = useState<string | null>(null)
  const [open, setOpen] = useState(!compact)
  const [text, setText] = useState('')
  const [err, setErr] = useState<string | null>(null)
  /** 每个联系人各自的增量游标（按 peer 取，历史多也不会被 limit 截掉） */
  const sinceByPeer = useRef(new Map<string, string>())
  const peerRef = useRef<string | null>(null)
  peerRef.current = peer
  const listRef = useRef<HTMLDivElement>(null)

  // 轮询 + ws：联系人 / 未读数用 /qq/contacts；正文按当前选中的 peer 取（peer= + limit=500 + 各自 since）
  useEffect(() => {
    let stop = false
    const tick = async (forPeer: string | null = peerRef.current) => {
      try {
        const since = forPeer ? sinceByPeer.current.get(forPeer) ?? null : null
        const [c, m] = await Promise.all([fetchContacts(playerId), fetchInbox(playerId, since, { peer: forPeer, limit: 500 })])
        if (stop) return
        setQQContacts(c)
        if (m) { mergeQQMessages(m); if (m.length && forPeer) { const last = m[m.length - 1].ts; if (last) sinceByPeer.current.set(forPeer, last) } }
        else if (c === null) setQQContacts(null)
      } catch { /* 网络抖动：下次再试 */ }
    }
    tick()
    const id = window.setInterval(() => tick(), POLL_MS)
    const onWs = (msg: unknown) => {
      const ev = (msg as { event?: string }).event
      if (ev === 'read') { tick(); return }               // B：平铺 {type:'qq', event:'message'|'read', …}；read 只刷一次状态
      const m = normalizeMessage(msg); if (m) mergeQQMessages([m])
    }
    EventBus.on('qq-event', onWs)
    return () => { stop = true; window.clearInterval(id); EventBus.off('qq-event', onWs) }
  }, [playerId, setQQContacts, mergeQQMessages])

  /** 是我发的：优先后端 direction；老数据没有就退回按 entity id 比 */
  const isMine = (m: QQMessage) => m.direction ? m.direction === 'out' : m.from === playerId
  const nameOf = (id: string) => qq.contacts.find(c => c.id === id)?.name ?? players.find(p => p.id === id)?.name ?? id
  const contacts: QQContact[] = useMemo(() => {
    // 联系人表为空时从消息里推出来
    if (qq.contacts.length) return qq.contacts
    const ids = new Map<string, QQContact>()
    for (const m of qq.messages) {
      const k = m.group ?? (isMine(m) ? (m.to ?? '') : m.from)
      if (!k) continue
      const c = ids.get(k) ?? { id: k, name: nameOf(k), group: !!m.group, unread: 0 }
      if (!isMine(m) && !m.readAt) c.unread++
      ids.set(k, c)
    }
    return [...ids.values()]
  }, [qq.contacts, qq.messages, playerId]) // eslint-disable-line react-hooks/exhaustive-deps
  const totalUnread = contacts.reduce((a, c) => a + c.unread, 0) + (qq.contacts.length ? 0 : 0)
  const thread = useMemo(() => {
    if (!peer) return [] as QQMessage[]
    const c = contacts.find(x => x.id === peer)
    // from / to 是 QQ 账号（achan / whale）而不是 entity id（阿蝉_97b6d8）——按 direction 判「我发的 / 发给我的」（11-15 主播：5 条未读点开看不到就是这里按 playerId 比错了）
    return qq.messages.filter(m => c?.group ? m.group === peer : (!m.group && ((!isMine(m) && m.from === peer) || (isMine(m) && m.to === peer))))
  }, [qq.messages, peer, contacts, playerId]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { listRef.current?.scrollTo({ top: 1e9 }) }, [thread.length, open])
  useEffect(() => { if (!phone && !peer && contacts.length) setPeer(contacts[0].id) }, [contacts, peer, phone])
  // 切换联系人：立刻按 peer 拉它的会话（首次不带 since，取最近 500 条）
  useEffect(() => {
    if (!peer) return
    let stop = false
    fetchInbox(playerId, sinceByPeer.current.get(peer) ?? null, { peer, limit: 500 }).then(m => {
      if (stop || !m) return
      mergeQQMessages(m)
      if (m.length) { const last = m[m.length - 1].ts; if (last) sinceByPeer.current.set(peer, last) }
    }).catch(() => { /* 下次轮询再试 */ })
    return () => { stop = true }
  }, [peer, playerId, mergeQQMessages])

  const peerC = contacts.find(c => c.id === peer)

  const doSend = async () => {
    if (!peer || readOnly) return
    setErr(null)
    try {
      if (text.trim()) {
        await sendText(playerId, peer, text.trim(), !!peerC?.group)
        setText('')
      }
    } catch (e) { setErr(`发送失败：${(e as Error).message}`) }
  }
  const doRead = async () => {
    if (!peer || readOnly) return
    try { await markRead(playerId, peer, !!peerC?.group); markQQRead(peer) } catch (e) { setErr(`标记已读失败：${(e as Error).message}`) }
  }

  // ── 手机样式（操控页）：角标 → 居中手机；联系人页 → 会话页 ──────────────────────────────
  if (phone) {
    if (!open) {
      return (
        <button onClick={() => setOpen(true)} title="QQ" data-testid="qq-badge" style={{ ...style, position: 'absolute', background: 'rgba(15,15,30,0.85)', border: '1px solid #4a5568', borderRadius: 8, color: '#e2e8f0', padding: '6px 10px', cursor: 'pointer', fontSize: 14, zIndex: 210 }}>
          📱{totalUnread > 0 && <span style={{ marginLeft: 6, background: '#e53e3e', color: '#fff', borderRadius: 10, padding: '0 6px', fontSize: 11 }}>{totalUnread}</span>}
        </button>
      )
    }
    const lastOf = (c: QQContact) => { const ms = qq.messages.filter(m => c.group ? m.group === c.id : (!m.group && ((!isMine(m) && m.from === c.id) || (isMine(m) && m.to === c.id)))); return ms[ms.length - 1] }
    const now = useGameStore.getState().worldState?.time ?? ''
    const close = () => { setOpen(false) }
    return (
      <div onClick={close} onKeyDown={e => { if (e.key === 'Escape') close() }} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 300, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div onClick={e => e.stopPropagation()} data-testid="qq-phone" style={{ width: 360, height: 'min(680px, 92vh)', background: '#111', borderRadius: 40, padding: 12, boxShadow: '0 20px 60px rgba(0,0,0,0.6)', display: 'flex', flexDirection: 'column', fontFamily: 'system-ui, "PingFang SC", sans-serif', color: '#e2e8f0', userSelect: 'none' }}>
          <div style={{ flex: 1, minHeight: 0, background: '#15172a', borderRadius: 30, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            {/* 状态栏 */}
            <div style={{ display: 'flex', alignItems: 'center', padding: '10px 18px 4px', fontSize: 12, color: '#a0aec0' }}>
              <span>{now.slice(0, 5) || '--:--'}</span>
              <span style={{ marginLeft: 'auto' }}>{totalUnread > 0 ? `🔴 ${totalUnread} 未读` : '📶'}</span>
              <button onClick={close} title="收起" style={{ marginLeft: 10, background: 'none', border: 'none', color: '#a0aec0', cursor: 'pointer', fontSize: 16, lineHeight: 1 }}>✕</button>
            </div>
            {qq.available === false && <div style={{ padding: 16, color: '#a0aec0' }}>后端还没开通 QQ 接口（/qq/* 404）。</div>}
            {qq.available !== false && !peer && (
              <>
                <div style={{ padding: '6px 18px 10px', fontSize: 20, fontWeight: 700 }}>QQ <span style={{ fontSize: 12, color: '#718096', fontWeight: 400, marginLeft: 6 }}>{nameOf(playerId)}</span></div>
                <div style={{ flex: 1, overflowY: 'auto' }}>
                  {contacts.length === 0 && <div style={{ padding: 18, color: '#718096' }}>没有联系人</div>}
                  {contacts.map(c => { const last = lastOf(c); return (
                    <div key={c.id} onClick={() => setPeer(c.id)} data-testid={`qq-contact-${c.id}`} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 18px', cursor: 'pointer', borderBottom: '1px solid #232640' }}>
                      <div style={{ width: 44, height: 44, borderRadius: 12, background: c.group ? '#553c9a' : '#2b6cb0', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20 }}>{c.group ? '👥' : c.name.slice(0, 1)}</div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}><b style={{ fontSize: 14 }}>{c.name}</b><span style={{ color: '#718096', fontSize: 11 }}>{last?.ts.slice(11, 16) ?? ''}</span></div>
                        <div style={{ color: '#a0aec0', fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{last ? (last.kind === 'file' ? '[文件]' : last.text) : '（还没有消息）'}</div>
                      </div>
                      {c.unread > 0 && <span style={{ background: '#e53e3e', color: '#fff', borderRadius: 10, padding: '1px 7px', fontSize: 11 }}>{c.unread}</span>}
                    </div>
                  ) })}
                </div>
              </>
            )}
            {qq.available !== false && peer && (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 10px 8px', borderBottom: '1px solid #232640' }}>
                  <button onClick={() => setPeer(null)} data-testid="qq-back" style={{ background: 'none', border: 'none', color: '#90cdf4', cursor: 'pointer', fontSize: 18, lineHeight: 1 }}>‹</button>
                  <b style={{ fontSize: 15 }}>{peerC?.group ? '👥 ' : ''}{peerC?.name ?? peer}</b>
                  {(peerC?.unread ?? 0) > 0 && <span style={{ color: '#fc8181', fontSize: 11 }}>{peerC!.unread} 未读</span>}
                  {!readOnly && <button onClick={doRead} title="读消息占 1 游戏分钟" style={{ marginLeft: 'auto', ...btn, padding: '3px 8px', fontSize: 11, background: '#2d3748' }}>标记已读</button>}
                </div>
                <div ref={listRef} style={{ flex: 1, overflowY: 'auto', padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {thread.length === 0 && <div style={{ color: '#718096', textAlign: 'center', marginTop: 20 }}>还没有消息</div>}
                  {thread.map(m => { const mine = isMine(m); return (
                    <div key={m.id} style={{ alignSelf: mine ? 'flex-end' : 'flex-start', maxWidth: '80%' }}>
                      <div style={{ color: '#718096', fontSize: 10, textAlign: mine ? 'right' : 'left' }}>{mine ? '我' : (m.fromName ?? nameOf(m.from))} · {m.ts.slice(11, 16) || m.ts}{!mine && !m.readAt ? ' · 未读' : ''}</div>
                      <div style={{ background: mine ? '#2b6cb0' : '#2a2d3e', borderRadius: 14, padding: '7px 11px', fontSize: 13, wordBreak: 'break-word' }}>
                        {m.kind === 'file' ? <span>{itemMeta(m.file?.type, m.file?.name).icon} 文件：{m.file?.name || itemMeta(m.file?.type).label}</span> : m.text}
                      </div>
                    </div>
                  ) })}
                </div>
                {!readOnly && (
                  <div style={{ borderTop: '1px solid #232640', padding: 10, display: 'flex', flexDirection: 'column', gap: 6, background: '#121426' }}>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <input value={text} onChange={e => setText(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') doSend() }} placeholder={`发给 ${peerC?.name ?? peer}…`} autoFocus
                        style={{ flex: 1, background: '#1a1b2e', border: '1px solid #4a5568', borderRadius: 18, color: '#e2e8f0', padding: '7px 12px', fontSize: 13 }} />
                      <button onClick={doSend} disabled={!text.trim()} style={{ ...btn, borderRadius: 18 }}>发送</button>
                    </div>
                    {err && <div style={{ color: '#fc8181', fontSize: 11 }}>{err}</div>}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    )
  }

  if (compact && !open) {
    return (
      <button onClick={() => setOpen(true)} title="QQ" style={{ ...style, position: 'absolute', background: 'rgba(15,15,30,0.85)', border: '1px solid #4a5568', borderRadius: 8, color: '#e2e8f0', padding: '6px 10px', cursor: 'pointer', fontSize: 14 }}>
        📱{totalUnread > 0 && <span style={{ marginLeft: 6, background: '#e53e3e', color: '#fff', borderRadius: 10, padding: '0 6px', fontSize: 11 }}>{totalUnread}</span>}
      </button>
    )
  }

  const recent = compact ? thread.slice(-5) : thread
  return (
    <div style={{ ...style, position: 'absolute', width: compact ? 300 : 360, background: 'rgba(15,15,30,0.9)', border: '1px solid #4a5568', borderRadius: 8, color: '#e2e8f0', fontSize: 12, fontFamily: 'system-ui, "PingFang SC", sans-serif', display: 'flex', flexDirection: 'column', maxHeight: compact ? 320 : 460, userSelect: 'none' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px', borderBottom: '1px solid #2d3748' }}>
        <b style={{ color: '#90cdf4' }}>📱 QQ</b>
        <span style={{ color: '#718096', fontSize: 11 }}>{readOnly ? `${nameOf(playerId)} 的手机 · 只读` : nameOf(playerId)}</span>
        {totalUnread > 0 && <span style={{ background: '#e53e3e', color: '#fff', borderRadius: 10, padding: '0 6px', fontSize: 11 }}>{totalUnread} 未读</span>}
        {compact && <button onClick={() => setOpen(false)} style={{ marginLeft: 'auto', background: 'none', border: 'none', color: '#a0aec0', cursor: 'pointer' }}>收起</button>}
      </div>
      {qq.available === false && <div style={{ padding: 10, color: '#a0aec0' }}>后端还没开通 QQ 接口（/qq/* 404）。B 的 W10 任务 3 落地后这里自动出现联系人。</div>}
      {qq.available !== false && (
        <div style={{ display: 'flex', minHeight: 0, flex: 1 }}>
          <div style={{ width: compact ? 96 : 120, borderRight: '1px solid #2d3748', overflowY: 'auto' }}>
            {contacts.length === 0 && <div style={{ padding: 8, color: '#718096' }}>没有联系人</div>}
            {contacts.map(c => (
              <div key={c.id} onClick={() => setPeer(c.id)} style={{ padding: '6px 8px', cursor: 'pointer', background: c.id === peer ? '#2a2d3e' : 'transparent', display: 'flex', justifyContent: 'space-between', gap: 4 }}>
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.group ? '👥 ' : ''}{c.name}</span>
                {c.unread > 0 && <span style={{ background: '#e53e3e', color: '#fff', borderRadius: 8, padding: '0 5px', fontSize: 10, alignSelf: 'center' }}>{c.unread}</span>}
              </div>
            ))}
          </div>
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
            <div ref={listRef} style={{ flex: 1, overflowY: 'auto', padding: 8, display: 'flex', flexDirection: 'column', gap: 6, minHeight: compact ? 120 : 220 }}>
              {recent.length === 0 && <div style={{ color: '#718096' }}>{peer ? '还没有消息' : '选一个联系人'}</div>}
              {recent.map(m => {
                const mine = isMine(m)
                return (
                  <div key={m.id} style={{ alignSelf: mine ? 'flex-end' : 'flex-start', maxWidth: '85%' }}>
                    <div style={{ color: '#718096', fontSize: 10, textAlign: mine ? 'right' : 'left' }}>{mine ? '我' : (m.fromName ?? nameOf(m.from))} · {m.ts.slice(11, 16) || m.ts}{!mine && !m.readAt ? ' · 未读' : ''}</div>
                    <div style={{ background: mine ? '#2b6cb0' : '#2a2d3e', borderRadius: 8, padding: '5px 8px', wordBreak: 'break-word' }}>
                      {m.kind === 'file' ? <span>{itemMeta(m.file?.type, m.file?.name).icon} 文件：{m.file?.name || itemMeta(m.file?.type).label}</span> : m.text}
                    </div>
                  </div>
                )
              })}
            </div>
            {!readOnly && (
              <div style={{ borderTop: '1px solid #2d3748', padding: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
                <div style={{ display: 'flex', gap: 6 }}>
                  <input value={text} onChange={e => setText(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') doSend() }} placeholder={peer ? `发给 ${peerC?.name ?? peer}…` : '先选联系人'} disabled={!peer}
                    style={{ flex: 1, background: '#1a1b2e', border: '1px solid #4a5568', borderRadius: 6, color: '#e2e8f0', padding: '5px 8px', fontSize: 12 }} />
                  <button onClick={doSend} disabled={!peer || !text.trim()} style={btn}>发送</button>
                </div>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center', justifyContent: 'flex-end' }}>
                  <button onClick={doRead} disabled={!peer} title="读消息占 1 游戏分钟" style={btn}>标记已读</button>
                </div>
                {err && <div style={{ color: '#fc8181', fontSize: 11 }}>{err}</div>}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
const btn: React.CSSProperties = { background: '#2b6cb0', border: 'none', borderRadius: 6, color: '#fff', padding: '5px 10px', cursor: 'pointer', fontSize: 12 }
