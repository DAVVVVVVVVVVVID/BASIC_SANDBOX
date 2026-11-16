import { useMemo, useState } from 'react'
import { useGameStore } from '../../store/gameStore'
import { EventBus } from '../../game/EventBus'
import { setDnd, leavePlayer, setDndOnUnload, timeToggle, timeSpeed, timeReset } from '../../api/world'
import { parseMapV2 } from '../../game/map/mapv2'
import { stairsHop } from '../../game/stairs'
import type { WorldState } from '../../types'
import { C, btn } from './theme'

/** 「设置」（主播定稿）：收纳 楼梯 / 勿扰 / 倍速 / 登出 */
export default function SettingsPanel() {
  const player = useGameStore((s) => s.player)
  const identity = useGameStore((s) => s.identity)
  const ws = useGameStore((s) => s.worldState)
  const setWorldState = useGameStore((s) => s.setWorldState)
  const tiles = useGameStore((s) => s.tiles)
  const mapExtras = useGameStore((s) => s.mapExtras)
  const mapVersion = useGameStore((s) => s.mapVersion)
  const [busy, setBusy] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  // eslint-disable-next-line react-hooks/exhaustive-deps -- 地图只随 mapVersion 变
  const v2 = useMemo(() => parseMapV2({ tiles, ...mapExtras } as unknown as Parameters<typeof parseMapV2>[0]), [mapVersion])
  const hop = useMemo(() => player ? stairsHop(v2, tiles, player.position) : null, [v2, tiles, player?.position.x, player?.position.y]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!player) return null
  const row = (label: string, body: React.ReactNode) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 6px', borderBottom: '1px dashed #E6DCCB' }}>
      <span style={{ width: 56, color: C.inkSoft }}>{label}</span>
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>{body}</div>
    </div>
  )
  const run = async (k: string, f: () => Promise<void>) => { setBusy(k); setMsg(null); try { await f() } catch (e) { setMsg(`✗ ${(e as Error).message}`) } finally { setBusy(null) } }
  const goStairs = () => { if (hop) EventBus.emit('walk-to-tile', { x: hop.target.x, y: hop.target.y, label: `走楼梯去 ${hop.toFloor} 楼` }) }
  const toggleDnd = () => run('dnd', async () => { const r = await setDnd(player.id, !player.dnd); const cur = useGameStore.getState().player; if (cur && cur.id === player.id) useGameStore.getState().setPlayer({ ...cur, dnd: r.dnd, tags: r.tags ?? cur.tags }) })
  const speed = (m: number) => run('speed', async () => { if (!ws) return; const r = await timeSpeed(ws.speed * m); setWorldState({ ...ws, speed: r.speed } as WorldState) })
  const toggleRun = () => run('run', async () => { if (!ws) return; const r = await timeToggle(); setWorldState({ ...ws, ...r } as WorldState) })
  const reset = () => run('reset', async () => { if (!ws) return; const r = await timeReset(); setWorldState({ ...ws, ...r } as WorldState) })
  const logout = () => run('logout', async () => {
    if (identity === 'achan') await setDndOnUnload(player.id, true)   // 主播离开：阿蝉留在镇上、勿扰归位，不删人
    else await leavePlayer(player.id)
    window.location.reload()
  })
  return (
    <div>
      {row('楼梯', hop
        ? <><button className="rb" onClick={goStairs} style={btn('primary')} data-testid="set-stairs">{hop.toFloor < hop.fromFloor ? '⬇ 下楼' : '⬆ 上楼'}去 {hop.toFloor} 楼</button><span style={{ fontSize: 11, color: C.inkSoft }}>或直接点另一层的地板</span></>
        : <span style={{ color: C.inkSoft }}>这栋没有楼梯</span>)}
      {row('勿扰', <>
        <span style={{ color: player.dnd ? '#A3581F' : '#246B5C' }}>{player.dnd ? (player.tags?.includes('working') ? '开 · 工作中' : '开') : '关'}</span>
        <button className="rb" onClick={toggleDnd} disabled={busy === 'dnd'} style={btn(player.dnd ? 'warn' : 'primary')} data-testid="dnd-toggle">{player.dnd ? '关闭勿扰' : '开启勿扰'}</button>
        <span style={{ fontSize: 11, color: C.inkSoft }}>开着别人不会来找你聊；关页自动开</span>
      </>)}
      {ws && row('时间', <>
        <span style={{ fontVariantNumeric: 'tabular-nums' }}>{ws.date} {ws.time}</span>
        <span style={{ color: C.inkSoft }}>· {ws.speed}x</span>
        <button className="rb" onClick={toggleRun} style={btn('neutral')} title={ws.running ? '暂停' : '开始'}>{ws.running ? '⏸' : '▶'}</button>
        <button className="rb" onClick={() => speed(2)} style={btn('neutral')} title="加速 ×2">＋</button>
        <button className="rb" onClick={() => speed(0.5)} style={btn('neutral')} title="减速 ÷2">－</button>
        <button className="rb" onClick={reset} style={btn('neutral')} title="重置时间">⟲</button>
      </>)}
      {row('账号', <>
        <span style={{ color: C.inkSoft, fontSize: 11 }}>{player.id}</span>
        <button className="rb" onClick={logout} disabled={busy === 'logout'} style={btn('secondary')} data-testid="logout">登出</button>
      </>)}
      {msg && <div style={{ color: C.coral, marginTop: 6 }}>{msg}</div>}
    </div>
  )
}
