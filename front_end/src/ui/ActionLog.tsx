import { useRef, useEffect } from 'react'
import { useGameStore } from '../store/gameStore'

/** §3.40 敲门事件（后端日志 type：knock / door_respond / door_pass_granted / door_pass_expired）→ 事件流文案 */
function knockLabel(e: { type: string; payload: Record<string, unknown>; success: boolean; reason: string | null }): string | null {
  const p = e.payload ?? {}
  const str = (k: string) => (typeof p[k] === 'string' ? (p[k] as string) : undefined)
  if (e.type === 'knock') return `🚪 敲了${str('home_name') ?? str('home') ?? ''}的门`
  if (e.type === 'door_respond') { const o = str('outcome'); return o === 'accepted' ? `🔓 给${str('visitor_name') ?? str('visitor') ?? '访客'}开了门` : o === 'declined' ? `🙅 没让${str('visitor_name') ?? str('visitor') ?? '访客'}进` : o === 'no_answer' ? '😶 敲门没人应' : `🚪 回应敲门：${o ?? ''}` }
  if (e.type === 'door_pass_granted') return `🔓 获准进入${str('home_name') ?? str('home') ?? ''}`
  if (e.type === 'door_pass_expired') return `🔒 通行证失效（${str('reason') === 'left' ? '离开了' : '到期'}）`
  return null
}

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
          const display = entry.label ?? knockLabel(entry) ?? entry.type
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
