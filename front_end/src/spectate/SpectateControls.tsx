import { useEffect, useState } from 'react'
import { useGameStore } from '../store/gameStore'
import { EventBus } from '../game/EventBus'
import Minimap from '../ui/Minimap'
import type { FreeCmd } from '../game/scenes/GameScene'

/**
 * W9 任务 0（主播 11-07 晚）：旁观页的镜头控件——「自由 / 全景」两个按钮、在线角色一键跟随、可点击的小地图（白框 = 当前镜头）。
 * 画布本身：拖动 / WASD 平移、滚轮以鼠标为中心缩放、点人跟随、点建筑进屋（含 2F）、点屋外或 Esc 回小镇。`layout=live` / `hud=0` 下不渲染。
 */
export default function SpectateControls({ initialMode, initialFollow }: { initialMode: 'free' | 'follow' | 'world'; initialFollow: string | null }) {
  const players = useGameStore((s) => s.players)
  const [state, setState] = useState<{ mode: string; follow: string | null; focus: { sector: string; floor: number } | null }>({ mode: initialMode, follow: initialFollow, focus: null })
  const [vp, setVp] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null)
  useEffect(() => {
    const onState = (s: typeof state) => setState(s)
    const onCam = (v: typeof vp) => setVp(v)
    EventBus.on('spectate-state', onState); EventBus.on('spectate-camera', onCam)
    return () => { EventBus.off('spectate-state', onState); EventBus.off('spectate-camera', onCam) }
  }, [])
  const send = (c: FreeCmd) => EventBus.emit('spectate-cmd', c)
  const followId = state.follow ? (players.find(p => p.id === state.follow || p.name === state.follow || p.agent_id === state.follow)?.id ?? null) : null
  return (
    <div style={{ position: 'absolute', right: 16, bottom: 16, display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-end', fontFamily: 'system-ui, "PingFang SC", sans-serif', fontSize: 12, color: '#e2e8f0', userSelect: 'none' }}>
      <Minimap inline viewport={vp} followId={followId} onClickTile={(x, y) => send({ cmd: 'jump', x, y })} />
      <div style={{ background: 'rgba(15,15,30,0.85)', border: '1px solid #4a5568', borderRadius: 8, padding: '8px 10px', minWidth: 200 }}>
        <div style={{ display: 'flex', gap: 6, marginBottom: 6 }}>
          <button onClick={() => send({ cmd: 'free' })} style={{ ...btn, background: state.mode === 'free' ? '#2b6cb0' : '#2a2d3e' }} title="拖动 / WASD 平移，滚轮缩放，点人跟随，点房子进屋，Esc 回小镇">🎥 自由</button>
          <button onClick={() => send({ cmd: 'world' })} style={{ ...btn, background: state.mode === 'world' ? '#2b6cb0' : '#2a2d3e' }}>🗺 全景</button>
          {state.focus && <button onClick={() => send({ cmd: 'exit' })} style={{ ...btn, background: '#744210' }}>🚪 出 {state.focus.sector}{state.focus.floor > 1 ? ` ${state.focus.floor}F` : ''}</button>}
        </div>
        <div style={{ color: '#718096', fontSize: 11, marginBottom: 4 }}>跟随（点名字）</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {players.map(p => (
            <button key={p.id} onClick={() => send({ cmd: 'follow', id: p.id })} style={{ ...btn, background: followId === p.id ? '#2b6cb0' : '#2a2d3e', opacity: p.online === false ? 0.55 : 1 }}>
              {p.online === false ? '○ ' : '● '}{p.name}
            </button>
          ))}
          {players.length === 0 && <span style={{ color: '#718096' }}>镇上没人</span>}
        </div>
      </div>
    </div>
  )
}
const btn: React.CSSProperties = { border: 'none', borderRadius: 6, color: '#fff', padding: '4px 9px', cursor: 'pointer', fontSize: 12 }
