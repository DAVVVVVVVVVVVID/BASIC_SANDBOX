import { useEffect, useMemo, useState } from 'react'
import { useGameStore } from '../store/gameStore'
import { EventBus } from '../game/EventBus'
import { openDoor, respondKnock, knockDoor } from '../api/door'
import type { MapDoor, PendingKnock, WsDoor, WsKnock } from '../types'

/**
 * §3.41 门禁（总控 11-08，B c3808ad / api-spec §11）操控页：
 * - 屋里有人敲门（GET /player.pending_knocks[] + ws knock 的 notified 含我）→ 顶部弹「X 在敲门」：
 *   「隔门回一句」输入 → POST /door/respond {text}；「不开」→ {decline:true}；提示「走到门边开门」。屋内任何人可应，不看 owner。
 * - 站在带 owner 的家门内侧格或其相邻格 → 「开门」→ POST /action open_door {door_id}（不需钥匙，敞开 60 游戏秒）；
 *   not_inside_door 时按 result.inside 提示该站哪格。
 * - 自己敲了别人家的门（player.door_request）→ 显示状态与屋里人的回话。
 * - 主播 11-16：站在别人家门外 ≤ 2 格 → 「🚪 敲 X 的门」→ POST /action knock {door_id}（有钥匙 / 不是家 / 太远按后端 reason 提示）。
 */
export default function KnockPanel() {
  const player = useGameStore((s) => s.player)
  const myId = useGameStore((s) => s.myPlayerId)
  const mapExtras = useGameStore((s) => s.mapExtras)
  const [local, setLocal] = useState<(PendingKnock & { at: number })[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [reply, setReply] = useState<Record<string, string>>({})
  const [opened, setOpened] = useState<Record<string, true>>({})   // door_id → 本地记的「敞开中」（60 s 后或收到 closed 清掉）
  const markOpen = (id: string) => { setOpened((o) => ({ ...o, [id]: true })); window.setTimeout(() => setOpened((o) => { const n = { ...o }; delete n[id]; return n }), 60_000) }

  useEffect(() => {
    const onKnock = (m: WsKnock) => {
      if (!myId || !(m.notified?.includes(myId) || m.owners?.includes(myId))) return
      setLocal((l) => [...l.filter((k) => k.id !== m.request_id), { id: m.request_id, visitor: m.visitor, visitor_name: m.visitor_name, home: m.home, home_name: m.home_name, door: m.door, expires_at: m.expires_at, status: 'pending', at: Date.now() }])
    }
    const onDoor = (m: WsDoor) => {
      if (m.request_id && (m.event === 'declined' || m.event === 'no_answer' || m.event === 'visitor_entered' || m.event === 'closed')) setLocal((l) => l.filter((k) => k.id !== m.request_id))
      const id = m.door_id ?? m.door?.door_id ?? m.door?.id
      if (id && m.event === 'opened') markOpen(id)
      if (id && m.event === 'closed') setOpened((o) => { const n = { ...o }; delete n[id]; return n })
    }
    EventBus.on('knock-event', onKnock); EventBus.on('door-event', onDoor)
    const t = window.setInterval(() => setLocal((l) => l.filter((k) => Date.now() - k.at < 180_000)), 5000)
    return () => { EventBus.off('knock-event', onKnock); EventBus.off('door-event', onDoor); window.clearInterval(t) }
  }, [myId])

  // 家门表（/world.map.doors[]）+ 对应的内侧格（edges 里 a=(x,y) 的那条的 b；找不到取上一格）
  const doors = useMemo(() => {
    const m = (mapExtras.map as { doors?: MapDoor[]; edges?: unknown[] } | undefined)
    const list = Array.isArray(m?.doors) ? m!.doors! : []
    const edges = (Array.isArray(mapExtras.edges) ? mapExtras.edges : Array.isArray(m?.edges) ? m!.edges! : []) as { a?: { x: number; y: number }; b?: { x: number; y: number } }[]
    return list.map((d) => { const e = edges.find((e) => e.a && e.a.x === d.x && e.a.y === d.y); return { ...d, inside: e?.b ?? { x: d.x, y: d.y - 1 } } })
  }, [mapExtras])
  if (!myId || !player) return null
  const me = player.position
  const nearDoor = doors.find((d) => Math.abs(d.inside.x - me.x) + Math.abs(d.inside.y - me.y) <= 1)
  const server = player.pending_knocks ?? []
  const knocks: PendingKnock[] = [...server, ...local.filter((k) => !server.some((s) => s.id === k.id))].filter((k) => !k.status || k.status === 'pending' || k.status === 'answered')
  const mine = player.door_request
  const myKnockOpen = mine && (mine.status === 'pending' || mine.status === 'answered')
  // 门外 ≤ 2 格（按门外侧格 (x,y) 算）且不在门内侧、没有在等的敲门 → 可敲；取最近的一扇
  const knockable = !nearDoor && !myKnockOpen
    ? doors.map((d) => ({ d, dist: Math.abs(d.x - me.x) + Math.abs(d.y - me.y) })).filter((x) => x.dist <= 2).sort((a, b) => a.dist - b.dist)[0]?.d ?? null
    : null
  if (knocks.length === 0 && !nearDoor && !myKnockOpen && !knockable && !msg) return null

  const flash = (t: string) => { setMsg(t); window.setTimeout(() => setMsg(null), 4000) }
  const say = async (k: PendingKnock) => {
    const text = (reply[k.id] ?? '').trim(); if (!text) { flash('✗ 先写一句'); return }
    setBusy(k.id)
    try { const r = await respondKnock(k.id, myId, { text }); if (r.success) { setReply((x) => ({ ...x, [k.id]: '' })); flash(`💬 隔着门说了「${text}」，要开门走到门边`) } else flash(`✗ ${reasonText(r.reason)}`) }
    catch (e) { flash(`✗ ${(e as Error).message}`) } finally { setBusy(null) }
  }
  const decline = async (k: PendingKnock) => {
    setBusy(k.id)
    try { const r = await respondKnock(k.id, myId, { decline: true }); if (r.success) { setLocal((l) => l.filter((x) => x.id !== k.id)); flash(`🙅 没让 ${k.visitor_name ?? '访客'} 进`) } else flash(`✗ ${reasonText(r.reason)}`) }
    catch (e) { flash(`✗ ${(e as Error).message}`) } finally { setBusy(null) }
  }
  const knock = async (doorId: string) => {
    setBusy(doorId)
    try {
      const r = await knockDoor(myId, doorId)
      if (r.success) flash(`🚪 咚咚咚……敲了${r.result?.door?.name ?? '门'}，${(r.result?.notified?.length ?? 0) > 0 ? '屋里有人听见了，等人应门' : '屋里好像没人'}`)
      else flash(`✗ ${reasonText(r.reason)}`)
    } catch (e) { flash(`✗ ${(e as Error).message}`) } finally { setBusy(null) }
  }
  const open = async (doorId: string) => {
    setBusy(doorId)
    try {
      const r = await openDoor(myId, doorId)
      if (r.success) { markOpen(doorId); flash(`🔓 ${r.result?.name ?? '门'}开了，60 游戏秒后自动落锁`) }
      else if (r.reason === 'not_inside_door' && r.result?.inside) flash(`✗ 要站到门内侧 (${r.result.inside.x}, ${r.result.inside.y}) 或旁边一格`)
      else flash(`✗ ${reasonText(r.reason)}`)
    } catch (e) { flash(`✗ ${(e as Error).message}`) } finally { setBusy(null) }
  }

  return (
    <div style={{ position: 'absolute', top: 16, left: '50%', transform: 'translateX(-50%)', width: 360, background: 'rgba(30,20,15,0.92)', border: '1px solid #b7791f', borderRadius: 10, color: '#fff7ed', fontSize: 13, padding: '10px 12px', fontFamily: 'system-ui, "PingFang SC", sans-serif', userSelect: 'none', boxShadow: '0 4px 18px rgba(0,0,0,0.4)' }}>
      {knocks.map((k) => {
        const doorId = k.door?.door_id ?? k.door?.id
        const d = doors.find((x) => x.door_id === doorId) ?? doors.find((x) => k.door && x.x === k.door.x && x.y === k.door.y)
        const canOpen = d && Math.abs(d.inside.x - me.x) + Math.abs(d.inside.y - me.y) <= 1
        return (
          <div key={k.id} style={{ marginBottom: 8, paddingBottom: 8, borderBottom: '1px solid rgba(183,121,31,0.4)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 20 }}>🚪</span>
              <span style={{ flex: 1 }}><b>{k.visitor_name ?? k.visitor ?? '有人'}</b> 在敲{k.door?.name ?? (k.home_name ? `${k.home_name}的门` : '门')}{k.status === 'answered' ? '（已回话）' : ''}</span>
              {canOpen && d ? <button disabled={!!busy} onClick={() => open(d.door_id)} style={{ ...bt, background: '#2f855a' }}>开门</button> : <span style={{ fontSize: 11, color: '#fbd38d' }}>走到门边开门{d ? ` (${d.inside.x}, ${d.inside.y})` : ''}</span>}
            </div>
            <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
              <input value={reply[k.id] ?? ''} onChange={(e) => setReply((x) => ({ ...x, [k.id]: e.target.value }))} onKeyDown={(e) => { if (e.key === 'Enter') say(k) }} placeholder="隔门回一句（谁呀？稍等…）" style={{ flex: 1, background: '#1a1b2e', border: '1px solid #4a5568', borderRadius: 6, color: '#e2e8f0', padding: '4px 8px', fontSize: 12 }} />
              <button disabled={!!busy} onClick={() => say(k)} style={{ ...bt, background: '#2b6cb0' }}>说</button>
              <button disabled={!!busy} onClick={() => decline(k)} style={{ ...bt, background: '#9b2c2c' }}>不开</button>
            </div>
          </div>
        )
      })}
      {knocks.length === 0 && knockable && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 18 }}>🚪</span>
          <span style={{ flex: 1 }}>{knockable.name ?? knockable.door_id}{knockable.owners?.length ? <span style={{ color: '#fbd38d', fontSize: 11 }}>（{knockable.owners.map(ownerName).join('、')}家）</span> : null}</span>
          <button disabled={!!busy} onClick={() => knock(knockable.door_id)} data-testid="knock-door" style={{ ...bt, background: '#b7791f' }}>敲门</button>
        </div>
      )}
      {knocks.length === 0 && nearDoor && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 18 }}>{opened[nearDoor.door_id] ? '🔓' : '🔒'}</span>
          <span style={{ flex: 1 }}>{nearDoor.name ?? nearDoor.door_id}{opened[nearDoor.door_id] ? '（敞开中）' : ''}</span>
          <button disabled={!!busy} onClick={() => open(nearDoor.door_id)} style={{ ...bt, background: '#2f855a' }}>开门</button>
        </div>
      )}
      {myKnockOpen && mine && (
        <div style={{ marginTop: knocks.length || nearDoor ? 8 : 0, fontSize: 12, color: '#fbd38d' }}>
          🚪 你敲了{mine.home_name ?? '别人家'}的门：{mine.status === 'answered' ? '里面有人应了' : '等人应门…'}
          {(mine.answers ?? []).slice(-2).map((a, i) => <div key={i} style={{ color: '#e2e8f0' }}>💬 {a.by_name ?? a.by}：「{a.text}」</div>)}
        </div>
      )}
      {msg && <div style={{ marginTop: 6, color: msg.startsWith('✗') ? '#fc8181' : '#9ae6b4', fontSize: 12 }}>{msg}</div>}
    </div>
  )
}
const OWNER_NAMES: Record<string, string> = { whale: '鲸仔', achan: '阿蝉', claudine: '克劳蒂娜', npc_fisher: '老渔夫', npc_rest_owner: '餐厅老板', npc_grocer: '杂货店老板娘' }
const ownerName = (id: string) => OWNER_NAMES[id] ?? id
function reasonText(r: string | null | undefined) {
  if (!r) return '失败'
  if (r === 'has_key') return '你有这家的钥匙，直接进就行'
  if (r === 'not_a_home') return '这不是住家，不用敲'
  if (r === 'too_far') return '离门太远，走到门口 2 格内'
  if (r === 'already_knocking') return '已经敲过了，等人应门'
  if (r === 'already_inside') return '你已经在屋里了'
  if (r === 'no_door' || r === 'unknown_door') return '这里没有门'
  if (r === 'not_inside') return '你不在这家里面'
  if (r === 'text_required') return '要么说一句，要么不开'
  if (/^not_pending/.test(r)) return '这次敲门已经过了'
  if (r === 'walking') return '还在走，站定再试'
  return r
}
const bt: React.CSSProperties = { border: 'none', borderRadius: 6, color: '#fff', padding: '4px 10px', cursor: 'pointer', fontSize: 12, whiteSpace: 'nowrap' }
