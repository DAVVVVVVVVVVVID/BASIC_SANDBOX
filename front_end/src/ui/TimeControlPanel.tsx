import { useGameStore } from '../store/gameStore'
import { timeToggle, timeSpeed, timeReset } from '../api/world'
import type { WorldState } from '../types'

const PERIOD_LABEL: Record<string, string> = {
  morning: '早晨',
  day:     '白天',
  dusk:    '黄昏',
  night:   '夜晚',
}

export default function TimeControlPanel() {
  const worldState = useGameStore((s) => s.worldState)
  const setWorldState = useGameStore((s) => s.setWorldState)
  if (!worldState) return null

  const { running, speed, date, time, period } = worldState

  async function handleToggle() {
    const updated = await timeToggle()
    setWorldState({ ...worldState, ...updated } as WorldState)
  }

  async function handleSpeed(multiplier: number) {
    const newSpeed = speed * multiplier
    const result = await timeSpeed(newSpeed)
    setWorldState({ ...worldState, speed: result.speed } as WorldState)
  }

  async function handleReset() {
    const updated = await timeReset()
    setWorldState({ ...worldState, ...updated } as WorldState)
  }

  return (
    <div style={{
      position: 'absolute',
      bottom: 16,
      right: 16,
      background: 'rgba(15, 15, 30, 0.90)',
      border: '1px solid #4a5568',
      borderRadius: 8,
      padding: '10px 14px',
      color: '#e2e8f0',
      fontSize: 13,
      userSelect: 'none',
      minWidth: 180,
    }}>
      <div style={{ marginBottom: 6, fontWeight: 'bold', color: '#90cdf4' }}>
        {date} {time}
      </div>
      <div style={{ marginBottom: 8, color: '#fbd38d' }}>
        {PERIOD_LABEL[period] ?? period} &nbsp;·&nbsp; {speed}x
      </div>
      <div style={{ display: 'flex', gap: 6 }}>
        <button onClick={handleToggle} title={running ? '暂停' : '开始'} style={btnStyle}>
          {running ? '⏸' : '▶'}
        </button>
        <button onClick={() => handleSpeed(2)} title="加速 ×2" style={btnStyle}>＋</button>
        <button onClick={() => handleSpeed(0.5)} title="减速 ÷2" style={btnStyle}>－</button>
        <button onClick={handleReset} title="重置" style={btnStyle}>🔄</button>
      </div>
    </div>
  )
}

const btnStyle: React.CSSProperties = {
  background: 'rgba(255,255,255,0.08)',
  border: '1px solid #4a5568',
  borderRadius: 4,
  color: '#e2e8f0',
  cursor: 'pointer',
  padding: '3px 8px',
  fontSize: 14,
}
