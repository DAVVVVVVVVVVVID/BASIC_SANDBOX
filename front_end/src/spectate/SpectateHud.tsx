import { useGameStore } from '../store/gameStore'
import { NEED_KEYS } from '../types'
import { NEED_LABELS } from '../game/objects/ActorSprite'
import { resolveFollowTarget } from '../game/systems/TickSystem'

const NEED_CSS: Record<string, string> = {
  fullness: '#f6ad55', energy: '#63b3ed', social: '#b794f4', fun: '#68d391', mood: '#fbd38d',
}

/** 旁观模式的 React 面板（hud=1 时显示）：目标名、在线状态、七变量、连接状态 */
export default function SpectateHud({ follow }: { follow: string | null }) {
  const players = useGameStore((s) => s.players)
  const playerVars = useGameStore((s) => s.playerVars)
  const connection = useGameStore((s) => s.connection)
  const transport = useGameStore((s) => s.transport)
  const target = resolveFollowTarget(players, follow)
  const vars = target ? playerVars[target.id] : undefined

  return (
    <div style={{
      position: 'absolute', top: 16, left: 16,
      background: 'rgba(15, 15, 30, 0.85)', border: '1px solid #4a5568', borderRadius: 8,
      padding: '10px 14px', color: '#e2e8f0', fontSize: 12, minWidth: 200,
      fontFamily: 'system-ui, sans-serif', userSelect: 'none',
    }}>
      <div style={{ fontWeight: 700, color: '#90cdf4', fontSize: 13, marginBottom: 4 }}>
        旁观 {follow ? `· 跟随 ${follow}` : '· 全景'}
      </div>
      <div style={{ color: connection === 'online' ? '#68d391' : '#fc8181' }}>
        {connection === 'online' ? '● 已连接' : connection === 'offline' ? '● 连接中断，重连中…' : '● 连接中'}
        <span style={{ color: '#718096', marginLeft: 6, fontSize: 11 }}>{transport === 'ws' ? 'WebSocket 推送' : transport === 'poll' ? '轮询（ws 不可用）' : ''}</span>
      </div>
      {follow && (
        <div style={{ marginTop: 4, color: target ? (target.online === false ? '#fbd38d' : '#a0aec0') : '#fc8181' }}>
          {target ? (target.online === false ? `${target.name} 离线（身体在 ${target.position.x},${target.position.y}）` : `${target.name} 在线 · (${target.position.x}, ${target.position.y}) · ${target.state}`) : '目标不在场，显示全景'}
        </div>
      )}
      {vars && (
        <div style={{ marginTop: 8, display: 'grid', gridTemplateColumns: 'auto 1fr auto', gap: '3px 8px', alignItems: 'center' }}>
          {NEED_KEYS.map(k => (
            <Row key={k} label={NEED_LABELS[k]} value={vars.vars[k]} color={NEED_CSS[k]} />
          ))}
        </div>
      )}
      {vars && vars.emotion_tags.length > 0 && (
        <div style={{ marginTop: 6, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {vars.emotion_tags.map((t, i) => (
            <span key={i} style={{ background: '#2a2d3e', color: '#fbd38d', borderRadius: 3, padding: '1px 6px', fontSize: 11 }}>{t.key}</span>
          ))}
        </div>
      )}
      <div style={{ marginTop: 8, color: '#718096', fontSize: 11 }}>
        {players.filter(p => p.online !== false).length} 人在线 / 共 {players.length}
      </div>
    </div>
  )
}

function Row({ label, value, color }: { label: string; value: number; color: string }) {
  const pct = Math.max(0, Math.min(100, value))
  return (
    <>
      <span style={{ color: '#a0aec0' }}>{label}</span>
      <div style={{ height: 6, background: '#2d3748', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: pct < 25 ? '#e53e3e' : color, transition: 'width 0.5s' }} />
      </div>
      <span style={{ fontVariantNumeric: 'tabular-nums', minWidth: 24, textAlign: 'right' }}>{Math.round(value)}</span>
    </>
  )
}
