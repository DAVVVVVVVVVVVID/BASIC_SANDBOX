import { useState, useEffect, useRef } from 'react'
import { useGameStore } from '../store/gameStore'
import * as chatApi from '../api/chat'
import type { ChatMessage, ChatRoomEvent, NearbyPlayer, PendingRequest } from '../api/chat'

// ─── Style helpers ────────────────────────────────────────────────────────────

const PANEL: React.CSSProperties = {
  position: 'fixed',
  top: 'calc(50% + 90px)',
  right: 8,
  width: 320,
  background: 'rgba(15, 15, 30, 0.95)',
  border: '1px solid #4a5568',
  borderRadius: 8,
  color: '#e2e8f0',
  fontFamily: 'system-ui, sans-serif',
  fontSize: 13,
  zIndex: 200,
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
}

const ROOM_PANEL: React.CSSProperties = {
  position: 'fixed',
  top: '50%',
  left: '50%',
  transform: 'translate(-50%, -50%)',
  width: 480,
  height: 400,
  background: 'rgba(15, 15, 30, 0.97)',
  border: '1px solid #4a5568',
  borderRadius: 8,
  color: '#e2e8f0',
  fontFamily: 'system-ui, sans-serif',
  fontSize: 13,
  zIndex: 200,
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
}

const PANEL_HEADER: React.CSSProperties = {
  padding: '8px 12px',
  background: 'rgba(30, 30, 60, 0.9)',
  borderBottom: '1px solid #2d3748',
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  flexShrink: 0,
}

const INPUT: React.CSSProperties = {
  width: '100%',
  background: '#1a202c',
  border: '1px solid #4a5568',
  borderRadius: 4,
  color: '#e2e8f0',
  padding: '6px 8px',
  fontSize: 13,
  outline: 'none',
  boxSizing: 'border-box',
}

function btn(bg: string): React.CSSProperties {
  return {
    padding: '5px 14px',
    background: bg,
    border: 'none',
    borderRadius: 4,
    color: '#e2e8f0',
    fontSize: 12,
    fontWeight: 600,
    cursor: 'pointer',
    flexShrink: 0,
  }
}

// ─── Main component ───────────────────────────────────────────────────────────

type Mode = 'idle' | 'selecting' | 'waiting' | 'in_room'

export default function ChatPanel() {
  const myPlayerId = useGameStore((s) => s.myPlayerId)
  const myPlayer   = useGameStore((s) => s.player)

  const [mode, setMode]             = useState<Mode>('idle')
  const [nearby, setNearby]         = useState<NearbyPlayer[]>([])
  const [selected, setSelected]     = useState<Set<string>>(new Set())
  const [greeting, setGreeting]     = useState('')
  const [pendingReq, setPendingReq] = useState<PendingRequest | null>(null)
  const [replyText, setReplyText]   = useState('')
  const [waitingId, setWaitingId]   = useState<string | null>(null)
  const [roomId, setRoomId]         = useState<string | null>(null)
  const [messages, setMessages]     = useState<ChatMessage[]>([])
  const [roomEvents, setRoomEvents] = useState<ChatRoomEvent[]>([])
  const [toast, setToast]           = useState<string | null>(null)
  const [sending, setSending]       = useState(false)
  const [roomHidden, setRoomHidden] = useState(false)

  const sinceRef  = useRef(0)
  const roomIdRef = useRef<string | null>(null)
  roomIdRef.current = roomId

  const myId   = myPlayerId ?? ''
  const myName = myPlayer?.profile?.name ?? myId

  // ── Toast auto-clear ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 3000)
    return () => clearTimeout(t)
  }, [toast])

  // ── Poll: pending requests（始终，2s）─────────────────────────────────────
  useEffect(() => {
    if (!myId) return
    const id = setInterval(async () => {
      if (pendingReq) return
      try {
        const d = await chatApi.getPending(myId)
        if (d.requests.length > 0) {
          setPendingReq(d.requests[0])
          setReplyText('')
        }
      } catch { /* ignore */ }
    }, 2000)
    return () => clearInterval(id)
  }, [myId, pendingReq])

  // ── Poll: nearby players（idle/selecting，3s）──────────────────────────────
  useEffect(() => {
    if (!myId || mode === 'waiting' || mode === 'in_room') return
    const fetch = async () => {
      try {
        const d = await chatApi.getNearby(myId)
        setNearby(d.players)
      } catch { /* ignore */ }
    }
    fetch()
    const id = setInterval(fetch, 3000)
    return () => clearInterval(id)
  }, [myId, mode])

  // ── Poll: request status（waiting，1.5s）──────────────────────────────────
  useEffect(() => {
    if (mode !== 'waiting' || !waitingId) return
    const id = setInterval(async () => {
      try {
        const d = await chatApi.getRequestStatus(waitingId)
        if (d.status === 'active' && d.chat_room_id) {
          clearInterval(id)
          enterRoom(d.chat_room_id)
        } else if (d.status === 'rejected') {
          clearInterval(id)
          setMode('idle')
          setWaitingId(null)
          setToast('对方拒绝了邀请')
        }
      } catch { /* ignore */ }
    }, 1500)
    return () => clearInterval(id)
  }, [mode, waitingId])

  // ── Poll: chat room（in_room，2s）─────────────────────────────────────────
  useEffect(() => {
    if (mode !== 'in_room' || !roomId) return
    const id = setInterval(async () => {
      try {
        const d = await chatApi.getRoom(roomIdRef.current!, myId, sinceRef.current)
        if (d.status === 'closed') {
          setRoomEvents(prev => [
            ...prev,
            { seq: 0, type: 'room_closed', entity_id: '', name: '' },
          ])
          setMode('idle')
          setRoomId(null)
          return
        }
        if (d.messages.length > 0) {
          setMessages(prev => [...prev, ...d.messages])
        }
        if (d.events.length > 0) {
          setRoomEvents(prev => [...prev, ...d.events])
        }
        const allSeqs = [
          ...d.messages.map(m => m.seq),
          ...d.events.map(e => e.seq),
        ]
        if (allSeqs.length > 0) {
          sinceRef.current = Math.max(sinceRef.current, ...allSeqs)
        }
      } catch { /* ignore */ }
    }, 2000)
    return () => clearInterval(id)
  }, [mode, roomId, myId])

  // ─── Helpers ──────────────────────────────────────────────────────────────

  function enterRoom(id: string) {
    sinceRef.current = 0
    setRoomId(id)
    setMessages([])
    setRoomEvents([])
    setMode('in_room')
    setRoomHidden(false)
    setWaitingId(null)
    setSelected(new Set())
    setGreeting('')
  }

  async function handleSendRequest() {
    if (selected.size === 0 || !greeting.trim()) return
    setSending(true)
    try {
      const d = await chatApi.sendRequest(myId, [...selected], greeting.trim())
      setWaitingId(d.request_id)
      setMode('waiting')
      setSelected(new Set())
      setGreeting('')
    } catch {
      setToast('发起请求失败')
    } finally {
      setSending(false)
    }
  }

  async function handleRespond(accept: boolean) {
    if (!pendingReq || !replyText.trim()) return
    setSending(true)
    const reqId = pendingReq.request_id
    try {
      const d = await chatApi.respond(myId, reqId, accept, replyText.trim())
      setPendingReq(null)
      setReplyText('')
      if (accept) {
        if (d.chat_room_id) {
          enterRoom(d.chat_room_id)
        } else {
          // multi-invite: wait for room to be created
          setWaitingId(reqId)
          setMode('waiting')
          setToast('已接受，等待其他人回应')
        }
      }
    } catch {
      setToast('操作失败')
    } finally {
      setSending(false)
    }
  }

  async function handleExit() {
    if (!roomId) return
    try { await chatApi.exitRoom(myId, roomId) } catch { /* ignore */ }
    setMode('idle')
    setRoomId(null)
    setMessages([])
    setRoomEvents([])
  }

  async function handleSend(content: string) {
    if (!roomId || !content.trim()) return
    try {
      await chatApi.sendMessage(myId, roomId, content.trim())
    } catch {
      setToast('发送失败')
    }
  }

  // ─── Render ───────────────────────────────────────────────────────────────

  if (!myId) return null

  return (
    <>
      {/* Toast */}
      {toast && (
        <div style={{
          position: 'fixed', top: 68, left: '50%', transform: 'translateX(-50%)',
          background: 'rgba(30, 30, 60, 0.95)', border: '1px solid #4a5568',
          padding: '6px 18px', borderRadius: 6, color: '#fbd38d',
          fontSize: 13, zIndex: 400, pointerEvents: 'none',
        }}>
          {toast}
        </div>
      )}

      {/* Incoming request notification */}
      {pendingReq && (
        <div style={{
          position: 'fixed', top: 16, left: '50%', transform: 'translateX(-50%)',
          width: 360, background: 'rgba(15, 15, 30, 0.97)',
          border: '1px solid #4a5568', borderRadius: 8, padding: '14px 18px',
          color: '#e2e8f0', fontFamily: 'system-ui, sans-serif', fontSize: 13,
          zIndex: 300, display: 'flex', flexDirection: 'column', gap: 10,
        }}>
          <div style={{ fontWeight: 600, color: '#90cdf4' }}>💬 收到对话邀请</div>
          <div style={{ color: '#a0aec0', lineHeight: 1.5 }}>
            <span style={{ color: '#e2e8f0', fontWeight: 600 }}>{pendingReq.from_name}</span>
            {' 说：'}
            <span style={{
              display: 'inline-block', marginTop: 4, padding: '3px 10px',
              background: '#2d3748', borderRadius: 4, color: '#e2e8f0',
            }}>
              「{pendingReq.greeting}」
            </span>
          </div>
          <textarea
            value={replyText}
            onChange={e => setReplyText(e.target.value)}
            placeholder="填写回应（接受）或拒绝理由…"
            rows={2}
            style={{ ...INPUT, resize: 'none' }}
          />
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={() => handleRespond(true)}
              disabled={!replyText.trim() || sending}
              style={btn('#276749')}
            >接受</button>
            <button
              onClick={() => handleRespond(false)}
              disabled={!replyText.trim() || sending}
              style={btn('#742a2a')}
            >拒绝</button>
            <button
              onClick={() => { setPendingReq(null); setReplyText('') }}
              style={{ ...btn('#2d3748'), marginLeft: 'auto' }}
            >忽略</button>
          </div>
        </div>
      )}

      {/* 小地图区域按钮：idle+附近有人 或 in_room+已隐藏 */}
      {((mode === 'idle' && nearby.length > 0) || (mode === 'in_room' && roomHidden)) && (
        <button
          onClick={() => mode === 'in_room' ? setRoomHidden(false) : setMode('selecting')}
          style={{
            position: 'fixed', top: 'calc(50% + 90px)', right: 8,
            padding: '8px 16px',
            background: 'rgba(15, 15, 30, 0.95)',
            border: '1px solid #4a5568', borderRadius: 8,
            color: '#90cdf4', fontSize: 13, fontWeight: 600,
            cursor: 'pointer', zIndex: 200,
          }}
        >
          {mode === 'in_room' ? '💬 打开聊天室' : `💬 发起对话 (${nearby.length})`}
        </button>
      )}

      {/* 选人 / 等待面板（右侧，小地图下方） */}
      {(mode === 'selecting' || mode === 'waiting') && (
        <div style={PANEL}>
          <div style={PANEL_HEADER}>
            <span style={{ flex: 1, fontWeight: 600, color: '#90cdf4' }}>
              {mode === 'waiting' ? '💬 等待响应…' : '💬 发起对话'}
            </span>
            <button
              onClick={() => { setMode('idle'); setWaitingId(null); setSelected(new Set()) }}
              style={btn('#2d3748')}
            >取消</button>
          </div>
          <div style={{ padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 8 }}>
            {mode === 'selecting' && (
              <>
                {nearby.length === 0 ? (
                  <div style={{ color: '#718096', textAlign: 'center', padding: '8px 0' }}>
                    附近没有其他玩家
                  </div>
                ) : (
                  nearby.map(p => (
                    <label key={p.entity_id} style={{
                      display: 'flex', alignItems: 'center', gap: 10,
                      padding: '5px 0', borderBottom: '1px solid #2d3748', cursor: 'pointer',
                    }}>
                      <input
                        type="checkbox"
                        checked={selected.has(p.entity_id)}
                        onChange={e => setSelected(prev => {
                          const next = new Set(prev)
                          e.target.checked ? next.add(p.entity_id) : next.delete(p.entity_id)
                          return next
                        })}
                        style={{ accentColor: '#4299e1', width: 14, height: 14, flexShrink: 0 }}
                      />
                      <span style={{ flex: 1 }}>{p.name}</span>
                      <span style={{ color: '#718096', fontSize: 11 }}>{p.entity_id}</span>
                    </label>
                  ))
                )}
                {selected.size > 0 && (
                  <>
                    <input
                      value={greeting}
                      onChange={e => setGreeting(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && handleSendRequest()}
                      placeholder="开场白（如：你好！有空聊聊吗）"
                      style={INPUT}
                    />
                    <div style={{ fontSize: 11, color: '#718096' }}>
                      提示：开场白仅用于敲门，请勿包含具体信息诉求
                    </div>
                    <button
                      onClick={handleSendRequest}
                      disabled={!greeting.trim() || sending}
                      style={btn('#2b6cb0')}
                    >发送邀请</button>
                  </>
                )}
              </>
            )}
            {mode === 'waiting' && (
              <div style={{ color: '#a0aec0', textAlign: 'center', padding: '12px 0' }}>
                <div style={{ marginBottom: 8 }}>⏳ 等待对方接受邀请…</div>
                <div style={{ fontSize: 11, color: '#718096' }}>对方接受后将自动进入聊天室</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 聊天室面板（居中固定窗口） */}
      {mode === 'in_room' && !roomHidden && (
        <div style={ROOM_PANEL}>
          <div style={PANEL_HEADER}>
            <span style={{ flex: 1, fontWeight: 600, color: '#90cdf4' }}>💬 聊天室</span>
            {roomId && (
              <span style={{ fontSize: 11, color: '#718096', marginRight: 4 }}>
                {roomId.slice(0, 8)}…
              </span>
            )}
            <button onClick={() => setRoomHidden(true)} style={btn('#2d3748')}>隐藏</button>
            <button onClick={handleExit} style={btn('#742a2a')}>退出</button>
          </div>
          <div style={{ flex: 1, padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 8, overflow: 'hidden' }}>
            <RoomView
              messages={messages}
              events={roomEvents}
              myId={myId}
              myName={myName}
              onSend={handleSend}
            />
          </div>
        </div>
      )}
    </>
  )
}

// ─── Chat room view ───────────────────────────────────────────────────────────

function RoomView({
  messages, events, myId, myName, onSend,
}: {
  messages: ChatMessage[]
  events: ChatRoomEvent[]
  myId: string
  myName: string
  onSend: (content: string) => void
}) {
  const [text, setText] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  // merge messages + events by seq, sorted
  const items = [
    ...messages.map(m => ({ seq: m.seq, kind: 'msg' as const, data: m })),
    ...events.map(e => ({ seq: e.seq, kind: 'evt' as const, data: e })),
  ].sort((a, b) => a.seq - b.seq)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, events])

  function send() {
    const content = text.trim()
    if (!content) return
    onSend(content)
    setText('')
  }

  return (
    <>
      {/* Message list */}
      <div style={{
        flex: 1, overflowY: 'auto',
        display: 'flex', flexDirection: 'column', gap: 6,
        paddingRight: 2,
      }}>
        {items.length === 0 && (
          <div style={{ color: '#718096', fontSize: 12, textAlign: 'center', padding: '8px 0' }}>
            对话开始，开始聊天吧
          </div>
        )}
        {items.map((item, i) => {
          if (item.kind === 'evt') {
            const label =
              item.data.type === 'player_exit' ? `${item.data.name || item.data.entity_id} 退出了对话` :
              item.data.type === 'room_closed'  ? '聊天室已关闭' :
              item.data.type
            return (
              <div key={i} style={{
                textAlign: 'center', color: '#718096',
                fontSize: 11, fontStyle: 'italic',
              }}>
                — {label} —
              </div>
            )
          }
          const m = item.data
          const isSelf = m.from_entity_id === myId
          const name = isSelf ? myName : (m.from_name || m.from_entity_id)
          return (
            <div key={i} style={{ textAlign: isSelf ? 'right' : 'left' }}>
              <div style={{ fontSize: 11, color: '#718096', marginBottom: 2 }}>{name}</div>
              <span style={{
                display: 'inline-block',
                background: isSelf ? '#2b4c7e' : '#2d3748',
                color: isSelf ? '#90cdf4' : '#e2e8f0',
                borderRadius: 6,
                padding: '5px 10px',
                maxWidth: '85%',
                wordBreak: 'break-word',
                textAlign: 'left',
                lineHeight: 1.5,
              }}>
                {m.content}
              </span>
            </div>
          )
        })}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{ display: 'flex', gap: 6 }}>
        <input
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && send()}
          placeholder="输入消息…"
          style={{ ...INPUT, flex: 1 }}
          autoFocus
        />
        <button onClick={send} disabled={!text.trim()} style={btn('#2b6cb0')}>
          发送
        </button>
      </div>
    </>
  )
}
