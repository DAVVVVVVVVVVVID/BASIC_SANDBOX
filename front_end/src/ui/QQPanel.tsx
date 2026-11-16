import { useEffect, useMemo, useRef, useState } from 'react'
import { useGameStore } from '../store/gameStore'
import { godotCharKeyFor } from '../game/godotChars'
import qqNicknames from './qqNicknames.json'
import { EventBus } from '../game/EventBus'
import { fetchContactsWithAccount, fetchInbox, markRead, msgClock, normalizeMessage, sendText, type QQContact, type QQMessage } from '../api/qq'
import { itemMeta } from '../game/items'   // 老消息里的 kind:file 条目仍要能显示

/**
 * W9 任务 2：QQ 面板（`docs/world-bible/08-phone-messaging.md`）。
 *   操控页（阿蝉）：联系人 / 会话 / 未读，发文字。world-v1.1 起歌 / 稿子是实体物品（CD / 稿子），文件传输取消，「发文件」已撤（B：kind:file 回 400 files_not_supported）。
 *   旁观页：只读，看跟随目标（鲸仔）的会话；`layout=live` 收成右上角图标 + 未读角标，点开看最近 5 条。
 * 数据：ws `qq` 事件即时推；每 4 s 轮询 /qq/inbox 兜底；后端还没有 /qq/*（404）时面板显示「后端未开通」而不是报错。
 */
interface Props { playerId: string; readOnly: boolean; compact?: boolean; style?: React.CSSProperties; /** 主播 11-15：手机样式（屏幕居中弹出，联系人 → 会话页），收起回角标 */ phone?: boolean }

const POLL_MS = 4000
const wallClockMs = () => Date.now()   // 节流用（事件 / effect 里调，不在渲染里）

export default function QQPanel({ playerId, readOnly, compact = false, style, phone = false }: Props) {
  const qq = useGameStore((s) => s.qq)
  const players = useGameStore((s) => s.players)
  const { setQQContacts, mergeQQMessages, replaceQQThread, markQQRead } = useGameStore.getState()
  /** 我的 QQ 账号（/qq/contacts 的 account；achan / whale），ws 事件只收与我有关的 */
  const accountRef = useRef<string | null>(null)
  const groupsRef = useRef<Set<string>>(new Set())
  const [peer, setPeer] = useState<string | null>(null)
  const [open, setOpen] = useState(!compact)
  const [text, setText] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const peerRef = useRef<string | null>(null)
  peerRef.current = peer
  const listRef = useRef<HTMLDivElement>(null)
  /** 消息属于 pid 这个会话（1:1 或群）——以 QQ 账号 / direction 判，不用 entity id */
  const belongsTo = (m: QQMessage, pid: string, group: boolean) => group ? m.group === pid : (!m.group && ((m.direction === 'out' || m.from === accountRef.current) ? m.to === pid : m.from === pid))

  // 轮询 + ws：联系人 / 未读数用 /qq/contacts；正文按当前选中的 peer 全量取（peer= + limit=500，不带 since），以后端为准覆盖本地该会话
  useEffect(() => {
    let stop = false
    const tick = async (forPeer: string | null = peerRef.current) => {
      try {
        const [c, m] = await Promise.all([fetchContactsWithAccount(playerId), fetchInbox(playerId, null, { peer: forPeer, limit: 500 })])
        if (stop) return
        if (c) { setQQContacts(c.contacts); if (c.account) accountRef.current = c.account; groupsRef.current = new Set(c.contacts.filter(x => x.group).map(x => x.id)) }
        else setQQContacts(null)
        if (m) {
          if (forPeer) { const g = groupsRef.current.has(forPeer); replaceQQThread(x => belongsTo(x, forPeer, g), m) }
          else mergeQQMessages(m)
        }
      } catch { /* 网络抖动：下次再试 */ }
    }
    tick()
    const id = window.setInterval(() => tick(), POLL_MS)
    const onWs = (msg: unknown) => {
      const ev = (msg as { event?: string }).event
      if (ev === 'read') { tick(); return }               // B：平铺 {type:'qq', event:'message'|'read', …}；read 只刷一次状态
      const m = normalizeMessage(msg); if (!m) return
      // 沙盒把所有 QQ 事件广播给全部 ws 订阅者（主播 11-16：阿蝉的鲸仔会话里混进鲸仔发给小克的）→ 只收与我有关的；账号还没拿到就丢，等轮询
      // B world-v1.3.16：message 事件不再带 text，带 participants[]（发件人 + 收件人账号 / 群成员）→ 按它判相关，再按 peer 拉 inbox 取正文
      const me = accountRef.current
      if (!me) return
      const parts = (msg as { participants?: unknown }).participants
      const mine = Array.isArray(parts) ? parts.map(String).includes(me) : (m.group ? groupsRef.current.has(m.group) : (m.from === me || m.to === me))
      if (!mine) return
      const peerOf = m.group ?? (m.from === me ? m.to ?? null : m.from)
      if (typeof m.text === 'string' && m.text) mergeQQMessages([{ ...m, direction: m.direction ?? (m.from === me ? 'out' : 'in') }])   // 旧后端带正文：先上屏
      if (peerOf) void tick(peerOf)                                                                                                     // 以 /qq/inbox?peer= 为准拉正文 / 覆盖
      else void tick()
    }
    EventBus.on('qq-event', onWs)
    return () => { stop = true; window.clearInterval(id); EventBus.off('qq-event', onWs) }
  }, [playerId, setQQContacts, mergeQQMessages, replaceQQThread])

  /** 是我发的：优先后端 direction；老数据没有就退回按 entity id 比 */
  const isMine = (m: QQMessage) => m.direction ? m.direction === 'out' : (accountRef.current ? m.from === accountRef.current : m.from === playerId)
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
  // 切换联系人：立刻按 peer 全量拉它的会话，以后端为准覆盖
  useEffect(() => {
    if (!peer) return
    let stop = false
    const g = groupsRef.current.has(peer)
    fetchInbox(playerId, null, { peer, limit: 500 }).then(m => { if (!stop && m) replaceQQThread(x => belongsTo(x, peer, g), m) }).catch(() => { /* 下次轮询再试 */ })
    return () => { stop = true }
  }, [peer, playerId, replaceQQThread])

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
  /**
   * /qq/read 节流（总控 11-15：沙盒每次 read 给读者叠 60 s reading busy，今早叠到 4831 s 锁住主播）：
   * 只在 ① 用户点「标记已读」② 首次打开某联系人会话页 时调；同一联系人同一批未读只 read 一次（按最后一条未读 id 去重），
   * 并且每个联系人 90 s 内不重复；4 s 轮询只拉 /qq/inbox，从不调 read。
   */
  const readSent = useRef(new Map<string, { lastId: string; at: number }>())
  const unreadIn = (pid: string) => qq.messages.filter(m => !isMine(m) && !m.readAt && (m.group === pid || (!m.group && m.from === pid)))
  const doRead = async (manual = true) => {
    if (!peer || readOnly) return
    const un = unreadIn(peer)
    const lastId = un.length ? un[un.length - 1].id : ''
    const prev = readSent.current.get(peer)
    const now = wallClockMs()
    if (!manual) {
      if (!lastId) return                                              // 没未读不读
      if (prev && (prev.lastId === lastId || now - prev.at < 90_000)) return   // 同一批已读过 / 90 s 内读过
    } else if (prev && now - prev.at < 10_000) { setErr('刚标记过，稍等几秒'); return }
    readSent.current.set(peer, { lastId, at: now })
    try { await markRead(playerId, peer, !!peerC?.group); markQQRead(peer) } catch (e) { setErr(`标记已读失败：${(e as Error).message}`) }
  }
  // 首次打开某联系人会话页（且有未读）→ 自动 read 一次；轮询到同一联系人的新未读会再读一次（受 90 s 节流）
  const unreadCountForPeer = peer ? unreadIn(peer).length : 0
  useEffect(() => { if (peer && open && !readOnly && unreadCountForPeer > 0) void doRead(false) }, [peer, open, readOnly, unreadCountForPeer]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── 手机样式（操控页，kit 风 · 总控 qq-redo.md 11-16）：角标 → 居中手机；联系人页 → 会话页 ──
  if (phone) {
    if (!open) {
      return (
        <button onClick={() => setOpen(true)} title="QQ" data-testid="qq-badge" className="qqicon" style={{ ...style, position: 'absolute', zIndex: 210, background: 'none' }}>
          {totalUnread > 0 && <span className="badge">{totalUnread}</span>}
        </button>
      )
    }
    const threadOf = (c: QQContact) => qq.messages.filter(m => c.group ? m.group === c.id : (!m.group && ((!isMine(m) && m.from === c.id) || (isMine(m) && m.to === c.id))))
    const lastOf = (c: QQContact) => { const ms = threadOf(c); return ms[ms.length - 1] }
    const now = useGameStore.getState().worldState?.time ?? ''
    const close = () => { setOpen(false) }
    // 排序：有未读在前 → 最后一条时间倒序 → 群固定最后
    const sorted = [...contacts].sort((a, b) => (Number(!!a.group) - Number(!!b.group)) || (Number(b.unread > 0) - Number(a.unread > 0)) || ((lastOf(b)?.ts ?? '').localeCompare(lastOf(a)?.ts ?? '')))
    const INK = '#3b3a44', SUB = '#8a8a96', FAINT = '#b4b4bf'
    return (
      <div className="rpg" onClick={close} onKeyDown={e => { if (e.key === 'Escape') close() }} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.35)', zIndex: 300, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div onClick={e => e.stopPropagation()} data-testid="qq-phone" style={{ width: 374, height: 'min(700px, 92vh)', position: 'relative', display: 'flex', flexDirection: 'column', color: INK }}>
          {/* 壳：kit phone_shell 九宫格；屏幕 cream */}
          <div style={{ position: 'absolute', inset: 0, borderWidth: 28, borderStyle: 'solid', borderColor: 'transparent', borderImage: 'url(assets/ui/kit/phone_shell.png) 60 fill / 28px stretch', imageRendering: 'pixelated', pointerEvents: 'none' }} />
          <div style={{ position: 'absolute', left: 14, right: 14, top: 18, bottom: 22, background: '#FFF8EC', borderRadius: 18, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            {/* 状态栏 */}
            <div style={{ display: 'flex', alignItems: 'center', padding: '8px 16px 2px', fontSize: 12, color: SUB }}>
              <span>{now.slice(0, 5) || '--:--'}</span>
              <span style={{ marginLeft: 'auto', marginRight: 8 }}>{totalUnread > 0 ? `${totalUnread} 未读` : '📶'}</span>
              <button className="closex" onClick={close} title="收起" style={{ width: 22, height: 22 }}>✕</button>
            </div>
            {qq.available === false && <div style={{ padding: 16, color: SUB }}>QQ 还没开通。</div>}
            {qq.available !== false && !peer && (
              <>
                <div style={{ padding: '4px 16px 8px', fontSize: 20, fontWeight: 700 }}>QQ <span style={{ fontSize: 12, color: SUB, fontWeight: 400, marginLeft: 6 }}>{nameOf(playerId)}</span></div>
                <div style={{ flex: 1, overflowY: 'auto', padding: '0 8px 8px', display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {sorted.length === 0 && <div style={{ padding: 18, color: FAINT, textAlign: 'center' }}>没有联系人</div>}
                  {sorted.map(c => { const last = lastOf(c); return (
                    <div key={c.id} onClick={() => setPeer(c.id)} data-testid={`qq-contact-${c.id}`} className="panel9" style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '2px 6px', cursor: 'pointer', minHeight: 44 }}>
                      <QQAvatar c={c} size={48} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'baseline', minWidth: 0 }}><QQName c={c} size={14} /><span style={{ color: SUB, fontSize: 11, flexShrink: 0 }}>{last ? msgClock(last) : ''}</span></div>
                        <div style={{ fontSize: 12, color: last ? '#6b6b78' : FAINT, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', ...(last ? {} : { fontSize: 11 }) }}>{last ? (last.kind === 'file' ? '[文件]' : last.text) : '还没有消息'}</div>
                      </div>
                      {c.unread > 0 && <span style={{ background: '#FF8A73', color: '#fff', borderRadius: 10, padding: '1px 7px', fontSize: 11, border: '1px solid #fff' }}>{c.unread}</span>}
                    </div>
                  ) })}
                </div>
              </>
            )}
            {qq.available !== false && peer && (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '2px 8px 6px', borderBottom: '2px solid #7FB6E8' }}>
                  <button onClick={() => setPeer(null)} data-testid="qq-back" title="返回" style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, lineHeight: 0 }}><img className="mi" src="assets/ui/kit/dir_back.png" alt="‹" style={{ width: 26, height: 26 }} /></button>
                  {peerC && <QQAvatar c={peerC} size={32} />}
                  {peerC ? <QQName c={peerC} size={15} /> : <b style={{ fontSize: 15, color: INK }}>{peer}</b>}
                  {(peerC?.unread ?? 0) > 0 && <span style={{ color: '#FF8A73', fontSize: 11 }}>{peerC!.unread} 未读</span>}
                  {!readOnly && <button className="k" onClick={() => doRead(true)} title="读消息占 1 游戏分钟（打开会话会自动读一次）" style={{ marginLeft: 'auto', fontSize: 12, minHeight: 28, whiteSpace: 'nowrap', flexShrink: 0 }}>标为已读</button>}
                </div>
                <div ref={listRef} style={{ flex: 1, overflowY: 'auto', padding: '10px 10px', display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {thread.length === 0 && peerC && <div style={{ textAlign: 'center', marginTop: 30, color: FAINT, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}><QQAvatar c={peerC} size={80} /><span style={{ fontSize: 12 }}>还没有消息</span></div>}
                  {thread.map(m => { const mine = isMine(m); return (
                    <div key={m.id} style={{ alignSelf: mine ? 'flex-end' : 'flex-start', maxWidth: '82%', display: 'flex', flexDirection: 'column', alignItems: mine ? 'flex-end' : 'flex-start' }}>
                      <div style={{ borderWidth: '12px 18px 16px 18px', borderStyle: 'solid', borderColor: 'transparent', borderImage: `url(assets/ui/kit/${mine ? 'speech_r' : 'speech_l'}.png) 30 50 44 50 fill / 12px 18px 16px 18px stretch`, imageRendering: 'pixelated', padding: '0 2px', fontSize: 13, color: mine ? '#fff' : INK, wordBreak: 'break-word', lineHeight: 1.4, ...(mine ? { filter: 'none' } : {}) }}>
                        <span style={mine ? { background: '#3BB7A8', boxShadow: '0 0 0 6px #3BB7A8', borderRadius: 2 } : undefined}>{m.kind === 'file' ? <span>{itemMeta(m.file?.type, m.file?.name).icon} 文件：{m.file?.name || itemMeta(m.file?.type).label}</span> : m.text}</span>
                      </div>
                      <div style={{ color: SUB, fontSize: 10, marginTop: -6 }}>{mine ? '我' : (m.fromName ?? nameOf(m.from))} · {msgClock(m)}{!mine && !m.readAt ? ' · 未读' : ''}</div>
                    </div>
                  ) })}
                </div>
                {!readOnly && (
                  <div style={{ padding: '6px 10px 10px', display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                      <input value={text} onChange={e => setText(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') doSend() }} placeholder={`发给 ${peerC?.name ?? peer}…`} autoFocus
                        style={{ flex: 1, borderWidth: 10, borderStyle: 'solid', borderColor: 'transparent', borderImage: 'url(assets/ui/kit/input_box.png) 24 fill / 10px stretch', imageRendering: 'pixelated', background: 'none', color: INK, padding: '2px 6px', fontSize: 13, outline: 'none', minHeight: 36 }} />
                      <button onClick={doSend} disabled={!text.trim()} style={{ width: 72, height: 38, border: 'none', background: 'url(assets/ui/kit/send_btn.png) center / 100% 100% no-repeat', color: '#fff', fontSize: 14, fontWeight: 700, cursor: 'pointer', imageRendering: 'pixelated', opacity: text.trim() ? 1 : 0.6 }}>发送</button>
                    </div>
                    {err && <div style={{ color: '#FF8A73', fontSize: 11 }}>{err}</div>}
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
                    <div style={{ color: '#718096', fontSize: 10, textAlign: mine ? 'right' : 'left' }}>{mine ? '我' : (m.fromName ?? nameOf(m.from))} · {msgClock(m)}{!mine && !m.readAt ? ' · 未读' : ''}</div>
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
                  <button onClick={() => doRead(true)} disabled={!peer} title="读消息占 1 游戏分钟" style={btn}>标记已读</button>
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

// ─── QQ 头像（总控 qq-redo.md）：人物用裁好的精灵头像 + 3px 人设色外框 + 1px 白内框；镇公所 / 直播组用 kit04 图标 ───
// 二期（主播 11-16 12:3x）：头像换成「这个人自己会选的 QQ 头像」（run/data/art/ui-redo/qq-avatars → public/assets/ui/qq），网名只在界面显示、真名小字保留；按 QQ 账号 id 映射，不动后端
const QQ_RING: Record<string, string> = { whale: '#7FB6E8', achan: '#C9B6F2', claudine: '#FF8A73', fisher: '#3BB7A8', grocer: '#F2B84B', cook: '#FFB38A', townhall: '#7FB6E8', livegroup: '#7FB6E8' }
const NICK = qqNicknames as Record<string, { nick: string; name: string }>
/** 联系人 → 头像 key（whale / achan / claudine / grocer / cook / fisher / townhall / livegroup） */
export function qqKeyOf(c: QQContact): string {
  if (c.group) return 'livegroup'
  if (/镇公所|town|hall|office/i.test(c.id + c.name)) return 'townhall'
  return godotCharKeyFor(c.name, null, c.id)
}
export function qqNick(c: QQContact): { nick: string; name: string } {
  const n = NICK[qqKeyOf(c)]
  return n ? { nick: n.nick, name: n.name } : { nick: c.name, name: '' }
}
function QQAvatar({ c, size }: { c: QQContact; size: number }) {
  const key = qqKeyOf(c)
  const src = `assets/ui/qq/${key}_${size > 56 ? 112 : 56}.png`
  return <img className="px" src={src} width={size} height={size} alt="" style={{ borderRadius: 10, border: `3px solid ${QQ_RING[key] ?? '#7FB6E8'}`, boxShadow: 'inset 0 0 0 1px #fff', background: '#fff', flexShrink: 0, imageRendering: 'pixelated' }} />
}
/** 网名 + 真名小字 */
function QQName({ c, size = 14 }: { c: QQContact; size?: number }) {
  const n = qqNick(c)
  return <span style={{ minWidth: 0, display: 'inline-flex', alignItems: 'baseline', gap: 6, flex: 1 }}><b style={{ fontSize: size, color: '#3b3a44', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{n.nick}</b>{n.name && n.name !== n.nick && <span style={{ fontSize: Math.max(10, size - 3), color: '#8a8a96', whiteSpace: 'nowrap', flexShrink: 0 }}>{n.name}</span>}</span>
}
