import { useGameStore } from '../store/gameStore'

const BAR_WIDTH = 160

function Bar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = Math.max(0, Math.min(1, value / max))
  return (
    <div style={{ width: BAR_WIDTH, height: 10, background: '#2d3748', borderRadius: 4, overflow: 'hidden' }}>
      <div style={{ width: `${pct * 100}%`, height: '100%', background: color, transition: 'width 0.2s' }} />
    </div>
  )
}

export default function HUD() {
  const player = useGameStore((s) => s.player)
  if (!player) return null

  return (
    <div style={{
      position: 'absolute',
      top: 16,
      left: 16,
      background: 'rgba(15, 15, 30, 0.85)',
      border: '1px solid #4a5568',
      borderRadius: 8,
      padding: '10px 14px',
      color: '#e2e8f0',
      fontSize: 13,
      userSelect: 'none',
      minWidth: 180,
    }}>
      <div style={{ marginBottom: 6 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
          <span>HP</span><span>{player.hp} / 100</span>
        </div>
        <Bar value={player.hp} max={100} color="#e53e3e" />
      </div>
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
          <span>Energy</span><span>{player.energy} / 100</span>
        </div>
        <Bar value={player.energy} max={100} color="#3182ce" />
      </div>
    </div>
  )
}
