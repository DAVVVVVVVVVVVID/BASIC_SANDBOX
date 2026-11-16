import { useEffect, useState } from 'react'
import { useGameStore } from '../../store/gameStore'
import { EventBus } from '../../game/EventBus'
import { fetchThoughts } from '../../api/world'
import type { DirectorCmd } from '../../game/scenes/GameScene'
import { C, panel, kit } from './theme'

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
  const key = (label: string, icon: string, active: boolean, onClick: () => void, title: string, testid: string) => (
    <button className={`sq${active ? ' active' : ''}`} onClick={onClick} title={title} data-testid={testid} style={{ width: 84, height: 76, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 2, fontSize: 13 }}>
      <img className="mi" src={kit(icon)} alt="" style={{ width: 30, height: 30 }} /><span>{label}</span>
    </button>
  )
  const wIcon = ws?.weather === 'rain' ? 'mi_rain' : ws?.weather === 'cloudy' ? 'mi_cloud' : (ws?.period === 'night' ? 'mi_moon' : 'mi_sun')
  return (
    <div style={{ position: 'absolute', top: 12, right: 12, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 8, pointerEvents: 'auto' }}>
      <div className="panel9" style={panel({ display: 'flex', alignItems: 'center', gap: 12, padding: '2px 10px', fontSize: 18, minHeight: 24 })}>
        <img className="mi" src={kit('mi_clock')} alt="" /><span style={{ fontVariantNumeric: 'tabular-nums' }}>{time}</span>
        <img className="mi" src={kit(wIcon)} alt="" title={WEATHER_ICON[ws?.weather ?? ''] ?? ''} /><span style={{ color: C.inkSoft, fontSize: 14 }}>{PERIOD[ws?.period ?? ''] ?? ''}</span>
        <img className="mi" src={kit('mi_coin')} alt="" /><b>{gold}</b>
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        {key('回阿蝉', 'dir_back', dir.mode === 'self', () => send({ cmd: 'self' }), '镜头回到阿蝉（Esc）', 'dir-self')}
        {key('自由', 'dir_camera', dir.mode === 'free', () => send({ cmd: 'free' }), '自由镜头：拖动 / WASD / 滚轮；点地面阿蝉照样走', 'dir-free')}
        {key('想法', 'dir_thought', thoughts, toggleThoughts, '角色头顶显示当前想法', 'dir-thoughts')}
      </div>
      {dir.mode === 'follow' && <div style={{ fontSize: 11, color: C.inkSoft, background: C.creamA, padding: '1px 8px', borderRadius: 8 }}>跟随中 · 点「回阿蝉」或 Esc 回来</div>}
    </div>
  )
}
