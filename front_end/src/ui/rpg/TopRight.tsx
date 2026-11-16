import { useEffect, useState } from 'react'
import { useGameStore } from '../../store/gameStore'
import { EventBus } from '../../game/EventBus'
import { fetchThoughts } from '../../api/world'
import type { DirectorCmd } from '../../game/scenes/GameScene'
import { C, btn, panel } from './theme'

const WEATHER_ICON: Record<string, string> = { sunny: '☀', cloudy: '☁', rain: '🌧' }
const PERIOD: Record<string, string> = { morning: '早晨', day: '白天', dusk: '黄昏', night: '夜晚' }

/** 右上（mockC1）：「10:30 ☀ 💰 2,345」一条药丸，其下三小方键 [回阿蝉] [自由] [💭]（导播三态 + 想法开关） */
export default function TopRight() {
  const ws = useGameStore((s) => s.worldState)
  const player = useGameStore((s) => s.player)
  const [dir, setDir] = useState<{ mode: 'self' | 'free' | 'follow'; follow: string | null }>({ mode: 'self', follow: null })
  const [thoughts, setThoughts] = useState(true)
  useEffect(() => {
    const on = (s: typeof dir) => setDir(s)
    EventBus.on('director-state', on)
    return () => { EventBus.off('director-state', on) }
  }, [])
  // 💭 想法慢轮询（8 s）：ws snapshot / patch 不带 last_thought，只有 /world?view=admin 带；ws thought 事件即时补
  useEffect(() => {
    if (!thoughts) return
    let stop = false
    const tick = async () => {
      try { const r = await fetchThoughts(); if (stop) return; const set = useGameStore.getState().setPlayerThought; for (const p of r.players ?? []) if (p.id) set(p.id, p.last_thought ?? null) } catch { /* 下次再试 */ }
    }
    tick(); const id = window.setInterval(tick, 8000)
    return () => { stop = true; window.clearInterval(id) }
  }, [thoughts])
  const send = (c: DirectorCmd) => EventBus.emit('director-cmd', c)
  const toggleThoughts = () => { const on = !thoughts; setThoughts(on); EventBus.emit('director-thoughts', { on }) }
  const time = (ws?.time ?? '--:--').slice(0, 5)
  const gold = typeof player?.gold === 'number' ? player.gold.toLocaleString('en-US') : '—'
  const key = (label: string, active: boolean, onClick: () => void, title: string, testid: string, kind: 'neutral' | 'thought' = 'neutral') => (
    <button className={`rb${active ? ' active' : ''}`} onClick={onClick} title={title} data-testid={testid} style={btn(kind, { width: 64, height: 44, padding: 0, fontSize: 13, background: active && kind === 'neutral' ? '#E3F0FB' : undefined })}>{label}</button>
  )
  return (
    <div style={{ position: 'absolute', top: 12, right: 12, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 8, pointerEvents: 'auto' }}>
      <div style={panel({ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 14px', fontSize: 16, borderRadius: 18 })}>
        <span style={{ fontVariantNumeric: 'tabular-nums' }}>{time}</span>
        <span title={ws?.weather ?? ''}>{WEATHER_ICON[ws?.weather ?? ''] ?? '☀'}</span>
        <span style={{ color: C.inkSoft, fontSize: 13 }}>{PERIOD[ws?.period ?? ''] ?? ''}</span>
        <span>💰 <b>{gold}</b></span>
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        {key('回阿蝉', dir.mode === 'self', () => send({ cmd: 'self' }), '镜头回到阿蝉（Esc）', 'dir-self')}
        {key('自由', dir.mode === 'free', () => send({ cmd: 'free' }), '自由镜头：拖动 / WASD / 滚轮；点地面阿蝉照样走', 'dir-free')}
        {key('💭', thoughts, toggleThoughts, '角色头顶显示当前想法', 'dir-thoughts', 'thought')}
      </div>
      {dir.mode === 'follow' && <div style={{ fontSize: 11, color: C.inkSoft, background: C.creamA, padding: '1px 8px', borderRadius: 8 }}>跟随中 · 点「回阿蝉」或 Esc 回来</div>}
    </div>
  )
}
