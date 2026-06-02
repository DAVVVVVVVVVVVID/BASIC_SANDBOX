import { useState, useEffect, useRef } from 'react'
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

// 本地倒计时 key：source:key，唯一标识一个 instant buff 实例
function buffKey(b: Buff) { return `${b.source}:${b.key}` }

export default function HUD() {
  const player  = useGameStore((s) => s.player)
  const speed   = useGameStore((s) => s.worldState?.speed ?? 1)
  const running = useGameStore((s) => s.worldState?.running ?? false)
  const tiles   = useGameStore((s) => s.tiles)

  // 本地维护 instant buff 的 remaining（游戏毫秒），用于平滑倒计时显示
  const [localRemaining, setLocalRemaining] = useState<Record<string, number>>({})
  const speedRef = useRef(speed)
  const runningRef = useRef(running)
  speedRef.current = speed
  runningRef.current = running

  // 服务端更新时，用服务端值覆盖本地值
  useEffect(() => {
    if (!player) return
    setLocalRemaining(prev => {
      const next = { ...prev }
      for (const b of player.buffs) {
        if (b.mode === 'timed' && b.remaining !== null) {
          next[buffKey(b)] = b.remaining
        }
      }
      // 清除已消失的 buff
      for (const k of Object.keys(next)) {
        if (!player.buffs.some(b => buffKey(b) === k)) delete next[k]
      }
      return next
    })
  }, [player?.buffs])

  // 本地每 100ms 按游戏速度递减
  useEffect(() => {
    const id = window.setInterval(() => {
      if (!runningRef.current) return
      const gameDelta = 100 * speedRef.current
      setLocalRemaining(prev => {
        const next: Record<string, number> = {}
        for (const [k, v] of Object.entries(prev)) {
          const updated = v - gameDelta
          if (updated > 0) next[k] = updated
        }
        return next
      })
    }, 100)
    return () => window.clearInterval(id)
  }, [])

  if (!player) return null

  const { profile, position, facing, state, stateLabel, hp, energy, usingObjectId, buffs, tags } = player

  const currentTile = tiles.find(t => t.x === position.x && t.y === position.y)
  const zoneParts = [currentTile?.world, currentTile?.sector, currentTile?.arena].filter(Boolean)
  const zoneLabel = zoneParts.length > 0 ? zoneParts.join(' / ') : '—'

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
      <Row label="Age" value={profile?.age ?? '—'} />
      <Row label="ID"   value={<span style={{ color: '#718096', fontSize: 11 }}>{player.id}</span>} />

      <Divider />

      {/* 位置与朝向 */}
      <Row label="Location" value={<span style={{ color: '#a0aec0', fontSize: 11 }}>{zoneLabel}</span>} />
      <Row label="Coords"   value={`(${position.x}, ${position.y})`} />
      <Row label="Facing"   value={{ up: '↑ Up', down: '↓ Down', left: '← Left', right: '→ Right' }[facing]} />

      <Divider />

      {/* 状态 */}
      <Row
        label="State"
        value={
          <span style={{ color: state === 'using' ? '#68d391' : state === 'idle' ? '#a0aec0' : '#fbd38d' }}>
            {stateDisplay}
          </span>
        }
      />
      {usingObjectId && (
        <Row label="Using" value={<span style={{ color: '#68d391', fontSize: 11 }}>{usingObjectId}</span>} />
      )}

      <Divider />

      {/* HP */}
      <div style={{ marginBottom: 6 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
          <span style={{ color: '#a0aec0' }}>HP</span>
          <span>{Math.floor(hp)} / 100</span>
        </div>
        <Bar value={hp} max={100} color="#e53e3e" />
      </div>

      {/* Energy */}
      <div style={{ marginBottom: 4 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
          <span style={{ color: '#a0aec0' }}>Energy</span>
          <span>{Math.floor(energy)} / 100</span>
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
                    {b.key}{b.value ? ` ${b.value > 0 ? '+' : ''}${b.value}` : ''}
                    {b.mode === 'timed'
                      ? ` (${((localRemaining[buffKey(b)] ?? b.remaining ?? 0) / 1000).toFixed(1)}s)`
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
