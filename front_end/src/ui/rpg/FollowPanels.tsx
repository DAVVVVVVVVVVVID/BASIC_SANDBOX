import { useEffect, useMemo, useRef, useState } from 'react'
import { useGameStore } from '../../store/gameStore'
import { EventBus } from '../../game/EventBus'
import { fetchPlayer } from '../../api/world'
import { getChatHistory, type ChatHistoryRow } from '../../api/chat'
import { normalizeInventory, itemMeta, itemDisplayName, isFreeSlot, type InventoryItem } from '../../game/items'
import { hasItemDetail } from '../../game/school'
import { groupFollowRooms } from '../../game/followChat'
import ItemDetail from './ItemDetail'
import MetaChips from './MetaChips'
import { rentText } from '../../game/v11'
import type { Player, WsChatEvent } from '../../types'
import { C, avatarUrl } from './theme'

/**
 * 导播「跟随角色」时 HUD 切到该角色（总控 director-follow.md 11-16）：数据只走 GET /player/{id} 与 GET /history/chat + /ws/world chat 推送；只读；后端零改动。
 */

/** 跟随中每 2 s 轮询 GET /player/{id}（任何玩家可读） */
export function useFollowedPlayer(id: string | null): Player | null {
  const [p, setP] = useState<Player | null>(null)
  useEffect(() => {
    if (!id) { setP(null); return }
    let stop = false
    const tick = async () => { try { const r = await fetchPlayer(id); if (!stop) setP(r) } catch { /* 下次再试 */ } }
    tick(); const t = window.setInterval(tick, 2000)
    return () => { stop = true; window.clearInterval(t) }
  }, [id])
  return p
}

/** lavender 提示条：「正在看 X 的 …」 */
export function FollowBanner({ name, what }: { name: string; what: string }) {
  return <div style={{ background: '#E6DDF8', color: '#5B4A8A', borderRadius: 6, padding: '4px 10px', fontSize: 12, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>🔒 正在看 <b>{name}</b> 的{what}<span style={{ marginLeft: 'auto', color: '#8A7FB0' }}>只读 · 点左上卡或「回阿蝉」退出</span></div>
}

/** 他的背包：inventory + 金币 + 房租，没有任何操作键 */
export function FollowBag({ player, name }: { player: Player | null; name: string }) {
  const inv = useMemo(() => normalizeInventory(player?.inventory), [player?.inventory])
  const [detail, setDetail] = useState<InventoryItem | null>(null)
  if (!player) return <div style={{ color: C.inkSoft }}>读取中…</div>
  const gold = typeof player.gold === 'number' ? player.gold : null
  const rent = rentText(player.rent)
  const slots = [...inv.slice(0, 10)]; while (slots.length < 10) slots.push(null as unknown as typeof inv[number])
  return (
    <div>
      <FollowBanner name={name} what="背包" />
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 6 }}>
        <b>🎒 {name} 的背包</b><span style={{ color: C.inkSoft, fontSize: 11 }}>{inv.filter(i => !isFreeSlot(i)).length}/10 种</span>
        <span style={{ marginLeft: 'auto', color: '#8A6116', fontWeight: 700 }}>💰 {gold ?? '—'}</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 6 }}>
        {slots.map((it, i) => { const m = it ? itemMeta(it.type, it.name) : null; return (
          <div key={i} title={it ? `${m!.label} ×${it.count}` : '空'} onClick={it && hasItemDetail(it) ? () => setDetail(it) : undefined} style={{ cursor: it && hasItemDetail(it) ? 'pointer' : 'default', height: 50, background: '#fff', border: `1px solid ${C.sky}`, borderRadius: 6, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
            {it && <><span style={{ fontSize: 20 }}>{m!.icon}</span><span style={{ fontSize: 10, color: C.inkSoft }}>{itemDisplayName(it).slice(0, 5)}</span>{it.count > 1 && <span style={{ position: 'absolute', right: 3, top: 1, fontSize: 10, color: '#8A6116' }}>×{it.count}</span>}</>}
          </div>
        ) })}
      </div>
      {inv.length > 0 && <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 3 }}>{inv.map((it, i) => <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap', minWidth: 0 }}>{itemMeta(it.type, it.name).icon} {itemDisplayName(it)}{it.count > 1 ? ` ×${it.count}` : ''}<MetaChips meta={it.meta} /></span>{hasItemDetail(it) && <button className="k" data-testid={`follow-bag-view-${it.type}`} onClick={() => setDetail(it)} style={{ fontSize: 12, padding: '1px 10px' }}>看</button>}</div>)}</div>}
      {rent && <div style={{ marginTop: 8, color: rent.overdue ? '#D9534F' : C.inkSoft, fontSize: 12 }}>🏠 {rent.text.replace(/^🏠 /, '')}</div>}
      {player.usingObjectId && <div style={{ marginTop: 4, color: C.inkSoft, fontSize: 12 }}>正在用：{player.usingObjectId}</div>}
      {detail && <ItemDetail item={detail} holder={player.agent_id} onClose={() => setDetail(null)} />}
    </div>
  )
}

/** 他今日的对话（只读）：GET /history/chat 当日 + ws chat 行实时追加；按 room 分组，进行中置顶 */
export function FollowChat({ id, name, avatarKey, player }: { id: string; name: string; avatarKey: string; player: Player | null }) {
  const players = useGameStore((s) => s.players)
  const [rows, setRows] = useState<ChatHistoryRow[]>([])
  const seen = useRef(new Set<string>())
  const mine = (r: { from?: string; to?: string[]; participants?: string[]; entity?: string }) => r.from === id || (r.to ?? []).includes(id) || (r.participants ?? []).includes(id) || r.entity === id
  useEffect(() => {
    let stop = false
    seen.current.clear(); setRows([])
    const since = new Date(); since.setHours(0, 0, 0, 0)
    const sinceIso = since.toISOString().slice(0, 19)
    const load = async () => {
      try {
        const all = await getChatHistory(sinceIso, 800); if (stop) return
        const got = all.filter(mine)
        setRows(prev => { const byKey = new Map(prev.map(r => [`${r.room_id}:${r.kind}:${r.seq ?? r.ts}`, r])); for (const r of got) byKey.set(`${r.room_id}:${r.kind}:${r.seq ?? r.ts}`, r); return [...byKey.values()].sort((a, b) => a.ts.localeCompare(b.ts)) })
      } catch { /* 下次再试 */ }
    }
    load(); const t = window.setInterval(load, 10000)
    const onRow = (c: WsChatEvent) => {
      const r: ChatHistoryRow = { kind: c.kind, ts: new Date().toISOString().slice(0, 23), room_id: c.chat_room_id, seq: c.seq, from: c.from_entity_id, from_name: c.from_name, text: (c as { content?: string }).content, event: (c as { event?: string }).event, participants: c.participants }
      if (!mine(r)) return
      setRows(prev => [...prev, r])
    }
    EventBus.on('chat-row', onRow)
    return () => { stop = true; window.clearInterval(t); EventBus.off('chat-row', onRow) }
  }, [id]) // eslint-disable-line react-hooks/exhaustive-deps
  const activeRoom = (player as { chat_room_id?: string | null } | null)?.chat_room_id ?? null
  // room_id 为 null 的邀请事件（过期 / 被拒）单列，不进房间分组（总控 11-18 黑屏根因）
  const { rooms, invites } = useMemo(() => groupFollowRooms(rows, activeRoom), [rows, activeRoom])
  const nameOf = (eid?: string, fallback?: string) => fallback ?? players.find(p => p.id === eid)?.name ?? eid ?? ''
  return (
    <div>
      <FollowBanner name={name} what="对话 · 今天" />
      {rooms.length === 0 && invites.length === 0 && <div style={{ color: C.inkSoft, textAlign: 'center', padding: 16 }}>今天还没有对话</div>}
      {rooms.map(({ room, rs, active }) => (
        <div key={room} style={{ marginBottom: 10, border: `1px solid ${active ? '#C9B6F2' : '#E6DCCB'}`, borderRadius: 8, padding: '6px 8px', background: active ? '#F6F1FF' : 'rgba(255,255,255,0.5)' }}>
          <div style={{ fontSize: 11, color: C.inkSoft, marginBottom: 4, display: 'flex', gap: 6 }}>{active && <span style={{ color: '#5B4A8A', fontWeight: 700 }}>● 进行中</span>}<span>房间 {String(room ?? '').slice(0, 8)}</span><span>· {String(rs[0]?.ts ?? '').slice(11, 16)}</span><span style={{ marginLeft: 'auto' }}>{[...new Set(rs.flatMap(r => r.participants ?? (r.from ? [r.from] : [])))].map(e => nameOf(e)).join('、')}</span></div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 220, overflowY: 'auto' }}>
            {rs.map((r, i) => r.kind === 'event'
              ? <div key={i} style={{ textAlign: 'center', fontSize: 11, color: C.inkSoft }}>— {r.event === 'room_open' ? '开始对话' : r.event === 'room_close' ? '对话结束' : r.event === 'player_exit' ? `${nameOf(r.entity)} 离开` : r.event === 'player_join' ? `${nameOf(r.entity)} 加入了聊天` : r.event} —</div>
              : (() => { const self = r.from === id; return (
                <div key={i} style={{ display: 'flex', gap: 6, flexDirection: self ? 'row-reverse' : 'row', alignItems: 'flex-start' }}>
                  {self && <img className="px" src={avatarUrl(avatarKey, 80)} width={24} height={24} alt="" style={{ borderRadius: 6 }} />}
                  <div style={{ maxWidth: '78%' }}>
                    <div style={{ fontSize: 10, color: C.inkSoft, textAlign: self ? 'right' : 'left' }}>{nameOf(r.from, r.from_name)} · {String(r.ts ?? '').slice(11, 16)}</div>
                    <div style={{ background: self ? '#C9B6F2' : '#fff', color: C.ink, border: `1px solid ${self ? '#B39DE6' : '#E6DCCB'}`, borderRadius: 8, padding: '4px 8px', fontSize: 13, wordBreak: 'break-word' }}>{r.text}</div>
                  </div>
                </div>
              ) })()
            )}
          </div>
        </div>
      ))}
      {invites.length > 0 && (
        <div data-testid="follow-chat-invites" style={{ border: '1px dashed #E6DCCB', borderRadius: 8, padding: '6px 8px', fontSize: 12, color: C.inkSoft }}>
          <div style={{ marginBottom: 2 }}>邀请未成</div>
          {invites.map((v, i) => (
            <div key={i}>{v.ts.slice(11, 16)} · {v.participants.map(e => nameOf(e)).join(' → ') || '—'} · {v.label}</div>
          ))}
        </div>
      )}
    </div>
  )
}
