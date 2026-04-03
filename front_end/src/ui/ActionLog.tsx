import { useRef, useEffect } from 'react'
import { useGameStore } from '../store/gameStore'

export default function ActionLog() {
  const log = useGameStore((s) => s.actionLog)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [log])

  return (
    <div style={{
      position: 'absolute',
      bottom: 16,
      left: 16,
      width: 300,
      maxHeight: 220,
      background: 'rgba(15, 15, 30, 0.85)',
      border: '1px solid #4a5568',
      borderRadius: 8,
      padding: '8px 10px',
      color: '#e2e8f0',
      fontSize: 11,
      userSelect: 'none',
      display: 'flex',
      flexDirection: 'column',
    }}>
      <div style={{ marginBottom: 6, fontSize: 12, color: '#a0aec0', borderBottom: '1px solid #4a5568', paddingBottom: 4 }}>
        行为日志（最近 {log.length} 条）
      </div>
      <div style={{ overflowY: 'auto', flex: 1 }}>
        {log.map((entry, i) => {
          const time = entry.timestamp.slice(11, 19)
          const color = entry.success ? '#68d391' : '#fc8181'
          const display = entry.label ?? entry.type
          return (
            <div key={i} style={{ marginBottom: 4, lineHeight: 1.4 }}>
              <span style={{ color: '#a0aec0' }}>{time} </span>
              <span style={{ color: '#90cdf4' }}>[{entry.entityId}] </span>
              <span style={{ color }}>{display}</span>
              {!entry.success && entry.reason && (
                <span style={{ color: '#a0aec0' }}> — {entry.reason}</span>
              )}
            </div>
          )
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
