import { useEffect, useMemo, useState } from 'react'
import { useGameStore } from '../store/gameStore'
import { EventBus } from '../game/EventBus'
import { deriveStateLabel } from '../game/stateLabel'
import { zoneLabel } from '../game/map/zones'
import type { DirectorCmd } from '../game/scenes/GameScene'

/**
 * 操控页「导播视角」（主播 11-16：操控阿蝉时能知道的信息太少）——阿蝉的上帝视角，只给主播用，旁观 / 直播布局不动。
 *   镜头三态：跟随阿蝉（默认）/ 自由（拖动 / WASD / 滚轮）/ 跟随任一角色（点名字或点画面上的人）；切走后点地面仍是走路；Esc 或「回阿蝉」一键回来。
 *   六人状态：名字 · 区域 · 在做什么 · 在线 · 金币 · 与我距离；小地图的点照旧。
 */
export default function DirectorPanel() {
  const me = useGameStore((s) => s.player)
  const players = useGameStore((s) => s.players)
  const objects = useGameStore((s) => s.objects)
  const tiles = useGameStore((s) => s.tiles)
  const [state, setState] = useState<{ mode: 'self' | 'free' | 'follow'; follow: string | null }>({ mode: 'self', follow: null })
  const [open, setOpen] = useState(true)
  const [thoughts, setThoughts] = useState(true)
  const toggleThoughts = () => { const on = !thoughts; setThoughts(on); EventBus.emit('director-thoughts', { on }) }
  useEffect(() => {
    const on = (s: typeof state) => setState(s)
    EventBus.on('director-state', on)
    return () => { EventBus.off('director-state', on) }
  }, [])
  const send = (c: DirectorCmd) => EventBus.emit('director-cmd', c)
  const tileAt = useMemo(() => new Map(tiles.map(t => [`${t.x},${t.y}`, t] as const)), [tiles])
  if (!me) return null
  const rows = players.filter(p => p.id !== me.id).map(p => {
    const t = tileAt.get(`${p.position.x},${p.position.y}`)
    const dist = Math.abs(p.position.x - me.position.x) + Math.abs(p.position.y - me.position.y)
    const th = p.last_thought?.text?.trim()
    return { p, zone: zoneLabel(t) || '—', doing: deriveStateLabel(p, objects) ?? (p.state === 'walking' ? '🚶 走路' : '站着'), dist, thought: th ? (th.length > 20 ? th.slice(0, 20) + '…' : th) : '' }
  })
  const modeLabel = state.mode === 'self' ? '跟随阿蝉' : state.mode === 'free' ? '自由镜头' : `跟随 ${players.find(p => p.id === state.follow)?.name ?? state.follow ?? ''}`
  return (
    <div data-testid="director" style={{ position: 'absolute', top: 12, left: '50%', transform: 'translateX(-50%)', width: 620, background: 'rgba(15,15,30,0.9)', border: '1px solid #4a5568', borderRadius: 8, color: '#e2e8f0', fontSize: 12, fontFamily: 'system-ui, "PingFang SC", sans-serif', userSelect: 'none', zIndex: 150 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 10px' }}>
        <b style={{ color: '#90cdf4' }}>🎬 导播</b>
        <span style={{ color: '#718096', fontSize: 11 }}>{modeLabel}</span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
          <button onClick={() => send({ cmd: 'self' })} data-testid="dir-self" style={{ ...btn, background: state.mode === 'self' ? '#2b6cb0' : '#2a2d3e' }} title="镜头回到阿蝉（Esc）">🙋 回阿蝉</button>
          <button onClick={() => send({ cmd: 'free' })} data-testid="dir-free" style={{ ...btn, background: state.mode === 'free' ? '#2b6cb0' : '#2a2d3e' }} title="拖动 / WASD 平移，滚轮缩放；点地面阿蝉照样走过去">🎥 自由</button>
          <button onClick={toggleThoughts} data-testid="dir-thoughts" style={{ ...btn, background: thoughts ? '#553c9a' : '#2a2d3e' }} title="角色头顶显示当前想法（players[].last_thought）">💭 想法</button>
          <button onClick={() => setOpen(o => !o)} style={{ ...btn, background: '#2a2d3e' }}>{open ? '▴' : '▾'}</button>
        </div>
      </div>
      {open && (
        <div style={{ borderTop: '1px solid #2d3748', padding: '4px 6px 6px', display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 10 }}>
          {rows.length === 0 && <div style={{ color: '#718096', padding: 6 }}>镇上没有别人</div>}
          {rows.map(({ p, zone, doing, dist, thought }) => (
            <div key={p.id} onClick={() => send({ cmd: 'follow', id: p.id })} data-testid={`dir-row-${p.id}`} title="点一下：镜头跟随"
              style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '3px 6px', borderRadius: 6, cursor: 'pointer', background: state.follow === p.id && state.mode === 'follow' ? '#2a4365' : 'transparent', opacity: p.online === false ? 0.6 : 1 }}>
              <span style={{ color: p.online === false ? '#718096' : '#68d391', fontSize: 10 }}>●</span>
              <b style={{ width: 72, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.name}</b>
              <span style={{ color: '#a0aec0', width: 84, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={zone}>{zone}</span>
              <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={thought ? `${doing}\n💭 ${p.last_thought?.text}` : doing}>{doing}{thoughts && thought ? <span style={{ color: '#b794f4' }}> 💭 {thought}</span> : null}</span>
              {typeof p.gold === 'number' && <span style={{ color: '#ffe9a8', fontSize: 11 }}>💰{p.gold}</span>}
              <span style={{ color: '#718096', fontSize: 11, width: 40, textAlign: 'right' }}>{dist} 格</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
const btn: React.CSSProperties = { border: 'none', borderRadius: 6, color: '#fff', padding: '3px 8px', cursor: 'pointer', fontSize: 12 }
