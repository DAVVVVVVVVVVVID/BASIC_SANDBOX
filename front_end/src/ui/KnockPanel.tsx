import { useEffect, useState } from 'react'
import { useGameStore } from '../store/gameStore'
import { EventBus } from '../game/EventBus'
import { respondKnock } from '../api/door'
import type { PendingKnock, WsDoor, WsKnock } from '../types'

/**
 * §3.40 敲门（总控 11-08，api-spec §11）：操控页弹「X 在敲门」接受 / 拒绝 → POST /door/respond。
 * 数据：GET /player 的 pending_knocks[]（主人视角，随轮询刷新）+ ws knock 即时加（notified / owners 含我）；ws door / 回应成功 / 2 分钟后移除。
 * 人类玩家算主人（阿蝉）；不是主人时后端回 not_owner，面板原样显示。
 */
export default function KnockPanel() {
  const player = useGameStore((s) => s.player)
  const myId = useGameStore((s) => s.myPlayerId)
  const [local, setLocal] = useState<(PendingKnock & { at: number })[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  useEffect(() => {
    const onKnock = (m: WsKnock) => {
      if (!myId || !(m.notified?.includes(myId) || m.owners?.includes(myId))) return
      setLocal((l) => [...l.filter((k) => k.id !== m.request_id), { id: m.request_id, visitor: m.visitor, visitor_name: m.visitor_name, home: m.home, home_name: m.home_name, door: m.door, expires_at: m.expires_at, at: Date.now() }])
    }
    const onDoor = (m: WsDoor) => { if (m.request_id) setLocal((l) => l.filter((k) => k.id !== m.request_id)) }
    EventBus.on('knock-event', onKnock); EventBus.on('door-event', onDoor)
    const t = window.setInterval(() => setLocal((l) => l.filter((k) => Date.now() - k.at < 120_000)), 5000)
    return () => { EventBus.off('knock-event', onKnock); EventBus.off('door-event', onDoor); window.clearInterval(t) }
  }, [myId])
  if (!myId) return null
  const server = player?.pending_knocks ?? []
  const list: PendingKnock[] = [...server, ...local.filter((k) => !server.some((s) => s.id === k.id))]
  if (list.length === 0 && !msg) return null

  const act = async (k: PendingKnock, accept: boolean) => {
    setBusy(k.id); setMsg(null)
    try {
      const r = await respondKnock(k.id, myId, accept)
      if (r.success) { setLocal((l) => l.filter((x) => x.id !== k.id)); setMsg(accept ? `🔓 给 ${k.visitor_name ?? '访客'} 开了门` : `🙅 没让 ${k.visitor_name ?? '访客'} 进`) }
      else setMsg(`✗ ${r.reason === 'not_owner' ? '你不是这家的主人' : r.reason === 'not_pending' || /^not_pending/.test(r.reason ?? '') ? '这次敲门已经过了' : (r.reason ?? '失败')}`)
    } catch (e) { setMsg(`✗ ${(e as Error).message}`) }
    finally { setBusy(null); window.setTimeout(() => setMsg(null), 4000) }
  }
  return (
    <div style={{ position: 'absolute', top: 16, left: '50%', transform: 'translateX(-50%)', width: 320, background: 'rgba(30,20,15,0.92)', border: '1px solid #b7791f', borderRadius: 10, color: '#fff7ed', fontSize: 13, padding: '10px 12px', fontFamily: 'system-ui, "PingFang SC", sans-serif', userSelect: 'none', boxShadow: '0 4px 18px rgba(0,0,0,0.4)' }}>
      {list.map((k) => (
        <div key={k.id} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
          <span style={{ fontSize: 20 }}>🚪</span>
          <span style={{ flex: 1 }}><b>{k.visitor_name ?? k.visitor ?? '有人'}</b> 在敲{k.home_name ? `${k.home_name}的` : ''}门</span>
          <button disabled={!!busy} onClick={() => act(k, true)} style={{ ...bt, background: '#2f855a' }}>开门</button>
          <button disabled={!!busy} onClick={() => act(k, false)} style={{ ...bt, background: '#9b2c2c' }}>不开</button>
        </div>
      ))}
      {msg && <div style={{ color: msg.startsWith('✗') ? '#fc8181' : '#9ae6b4', fontSize: 12 }}>{msg}</div>}
    </div>
  )
}
const bt: React.CSSProperties = { border: 'none', borderRadius: 6, color: '#fff', padding: '4px 10px', cursor: 'pointer', fontSize: 12 }
