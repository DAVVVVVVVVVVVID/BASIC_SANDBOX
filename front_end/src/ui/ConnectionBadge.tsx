import { useGameStore } from '../store/gameStore'

/** 操控模式：后端连不上时顶部提示（轮询会自动恢复） */
export default function ConnectionBadge() {
  const connection = useGameStore((s) => s.connection)
  if (connection !== 'offline') return null
  return (
    <div style={{
      position: 'fixed', top: 12, left: '50%', transform: 'translateX(-50%)',
      background: 'rgba(120,20,20,0.85)', color: '#fed7d7', border: '1px solid #c53030',
      padding: '5px 14px', borderRadius: 6, fontSize: 13, zIndex: 500, pointerEvents: 'none',
      fontFamily: 'system-ui, sans-serif',
    }}>
      后端连接中断，自动重连中…
    </div>
  )
}
