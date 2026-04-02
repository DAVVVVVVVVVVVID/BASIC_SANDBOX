import { useState, useEffect } from 'react'
import { EventBus } from '../game/EventBus'

export default function InteractionPanel() {
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    const handler = ({ message }: { message: string }) => setMessage(message)
    EventBus.on('show-interaction', handler)
    return () => { EventBus.off('show-interaction', handler) }
  }, [])

  useEffect(() => {
    if (!message) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setMessage(null) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [message])

  if (!message) return null

  return (
    <div
      onClick={() => setMessage(null)}
      style={{
        position: 'absolute',
        bottom: '24px',
        left: '50%',
        transform: 'translateX(-50%)',
        backgroundColor: 'rgba(15, 15, 30, 0.92)',
        color: '#e2e8f0',
        padding: '16px 28px',
        borderRadius: '8px',
        border: '1px solid #4a5568',
        maxWidth: '360px',
        width: 'max-content',
        textAlign: 'center',
        fontSize: '14px',
        lineHeight: '1.6',
        zIndex: 100,
        cursor: 'pointer',
        userSelect: 'none',
      }}
    >
      <p style={{ margin: 0 }}>{message}</p>
      <small style={{ color: '#718096', marginTop: '8px', display: 'block' }}>
        点击或按 Esc 关闭
      </small>
    </div>
  )
}
