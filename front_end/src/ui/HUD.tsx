import { useGameStore } from '../store/gameStore'
import type { Buff } from '../types'

const BAR_WIDTH = 160

function Bar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = Math.max(0, Math.min(1, value / max))
  return (
    <div style={{ width: BAR_WIDTH, height: 8, background: '#2d3748', borderRadius: 4, overflow: 'hidden' }}>
      <div style={{ width: `${pct * 100}%`, height: '100%', background: color, transition: 'width 0.2s' }} />
    </div>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 2 }}>
      <span style={{ color: '#a0aec0', flexShrink: 0 }}>{label}</span>
      <span style={{ color: '#e2e8f0', textAlign: 'right' }}>{value}</span>
    </div>
  )
}

function Divider() {
  return <div style={{ borderTop: '1px solid #2d3748', margin: '6px 0' }} />
}

export default function HUD() {
  const player = useGameStore((s) => s.player)
  if (!player) return null

  const { profile, position, facing, state, stateLabel, hp, energy, usingObjectId, buffs, tags } = player

  const stateDisplay = stateLabel ?? state

  return (
    <div style={{
      position: 'absolute',
      top: 16,
      left: 16,
      background: 'rgba(15, 15, 30, 0.9)',
      border: '1px solid #4a5568',
      borderRadius: 8,
      padding: '10px 14px',
      color: '#e2e8f0',
      fontSize: 12,
      userSelect: 'none',
      minWidth: 200,
    }}>
      {/* 档案 */}
      <div style={{ fontWeight: 'bold', marginBottom: 6, color: '#90cdf4', fontSize: 13 }}>
        {profile?.name ?? player.id}
      </div>
      <Row label="年龄" value={profile?.age ?? '—'} />
      <Row label="ID"   value={<span style={{ color: '#718096', fontSize: 11 }}>{player.id}</span>} />

      <Divider />

      {/* 位置与朝向 */}
      <Row label="坐标"   value={`(${position.x}, ${position.y})`} />
      <Row label="朝向"   value={{ up: '↑ 上', down: '↓ 下', left: '← 左', right: '→ 右' }[facing]} />

      <Divider />

      {/* 状态 */}
      <Row
        label="状态"
        value={
          <span style={{ color: state === 'using' ? '#68d391' : state === 'idle' ? '#a0aec0' : '#fbd38d' }}>
            {stateDisplay}
          </span>
        }
      />
      {usingObjectId && (
        <Row label="使用中" value={<span style={{ color: '#68d391', fontSize: 11 }}>{usingObjectId}</span>} />
      )}

      <Divider />

      {/* HP */}
      <div style={{ marginBottom: 6 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
          <span style={{ color: '#a0aec0' }}>HP</span>
          <span>{hp} / 100</span>
        </div>
        <Bar value={hp} max={100} color="#e53e3e" />
      </div>

      {/* Energy */}
      <div style={{ marginBottom: 4 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
          <span style={{ color: '#a0aec0' }}>Energy</span>
          <span>{energy} / 100</span>
        </div>
        <Bar value={energy} max={100} color="#3182ce" />
      </div>

      {/* Buffs & Tags */}
      {(buffs.length > 0 || tags.length > 0) && (
        <>
          <Divider />
          {buffs.length > 0 && (
            <div style={{ marginBottom: 4 }}>
              <div style={{ color: '#a0aec0', marginBottom: 3 }}>Buffs</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {buffs.map((b: Buff, i) => (
                  <span key={i} style={{
                    background: '#2d5016', color: '#68d391',
                    borderRadius: 3, padding: '1px 6px', fontSize: 11,
                  }}>
                    {b.key}{b.value ? ` +${b.value}` : ''}
                    {b.mode === 'instant' && b.remaining !== null
                      ? ` (${(b.remaining / 1000).toFixed(1)}s)`
                      : ''}
                  </span>
                ))}
              </div>
            </div>
          )}
          {tags.length > 0 && (
            <div>
              <div style={{ color: '#a0aec0', marginBottom: 3 }}>Tags</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {tags.map((tag, i) => (
                  <span key={i} style={{
                    background: '#2a2d3e', color: '#90cdf4',
                    borderRadius: 3, padding: '1px 6px', fontSize: 11,
                  }}>
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
