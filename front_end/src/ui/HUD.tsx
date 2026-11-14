import { useState, useEffect, useRef, useMemo } from 'react'
import { useGameStore } from '../store/gameStore'
import { setDnd } from '../api/world'
import { gameNowMs, busyText, dailyUseLines, rentText } from '../game/v11'
import type { Buff } from '../types'
import { NEED_KEYS } from '../types'
import { NEED_LABELS } from '../game/objects/ActorSprite'
import { zoneLabel as zoneName } from '../game/map/zones'
import { parseMapV2 } from '../game/map/mapv2'
import { stairsHop } from '../game/stairs'
import { EventBus } from '../game/EventBus'

const NEED_CSS: Record<string, string> = {
  fullness: '#f6ad55', energy: '#63b3ed', social: '#b794f4', fun: '#68d391', mood: '#fbd38d',
}
const NEED_FULL: Record<string, string> = {
  fullness: '饱腹', energy: '精力', social: '社交', fun: '乐趣', mood: '心情',
}

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

/** 楼梯换层（主播问「怎么去 1 楼」）：所在楼有楼梯就给一个按钮，目标格 = 楼梯另一端，交后端寻路（见 InputSystem.walkToTile） */
function StairsRow({ position }: { position: { x: number; y: number } }) {
  const tiles = useGameStore((s) => s.tiles)
  const mapExtras = useGameStore((s) => s.mapExtras)
  const mapVersion = useGameStore((s) => s.mapVersion)
  // eslint-disable-next-line react-hooks/exhaustive-deps -- 地图只随 mapVersion 变
  const v2 = useMemo(() => parseMapV2({ tiles, ...mapExtras } as unknown as Parameters<typeof parseMapV2>[0]), [mapVersion])
  const hop = useMemo(() => stairsHop(v2, tiles, position), [v2, tiles, position.x, position.y])   // eslint-disable-line react-hooks/exhaustive-deps
  if (!hop) return null
  const go = () => EventBus.emit('walk-to-tile', { x: hop.target.x, y: hop.target.y, label: `走楼梯去 ${hop.toFloor} 楼` })
  return (
    <Row label="楼梯" value={
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
        <button onClick={go} data-testid="stairs-go" style={{ fontSize: 11, padding: '1px 8px', borderRadius: 4, border: '1px solid #4a5568', background: '#2c5282', color: '#fff', cursor: 'pointer' }}>
          {hop.toFloor < hop.fromFloor ? '⬇ 下楼' : '⬆ 上楼'}去 {hop.toFloor} 楼
        </button>
        <span style={{ color: '#718096', fontSize: 10 }}>或直接点另一层的地板</span>
      </span>
    } />
  )
}

/** world-v1.3：勿扰开关（主播操控阿蝉）——POST /admin/player/{id}/dnd，回包更新本地 player */
function DndRow({ playerId, dnd, tags }: { playerId: string; dnd: boolean; tags: string[] }) {
  const [busy, setBusy] = useState(false)
  const toggle = async () => {
    if (busy) return
    setBusy(true)
    try {
      const r = await setDnd(playerId, !dnd)
      const cur = useGameStore.getState().player
      if (cur && cur.id === playerId) useGameStore.getState().setPlayer({ ...cur, dnd: r.dnd, tags: r.tags ?? cur.tags })
    } catch { /* 保持原状 */ } finally { setBusy(false) }
  }
  const working = tags.includes('working')
  return (
    <Row label="勿扰" value={
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
        <span style={{ color: dnd ? '#f6ad55' : '#68d391', fontSize: 11 }}>{dnd ? (working ? '开 · 工作中' : '开') : '关'}</span>
        <button onClick={toggle} disabled={busy} data-testid="dnd-toggle" style={{ fontSize: 11, padding: '1px 8px', borderRadius: 4, border: '1px solid #4a5568', background: dnd ? '#744210' : '#22543d', color: '#fff', cursor: 'pointer' }}>
          {busy ? '…' : (dnd ? '关闭勿扰' : '开启勿扰')}
        </button>
      </span>
    } />
  )
}

export default function HUD() {
  const player  = useGameStore((s) => s.player)
  const identity = useGameStore((s) => s.identity)
  const speed   = useGameStore((s) => s.worldState?.speed ?? 1)
  const running = useGameStore((s) => s.worldState?.running ?? false)
  const tiles   = useGameStore((s) => s.tiles)
  const players = useGameStore((s) => s.players)
  const playerVars = useGameStore((s) => s.playerVars)

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
  // eslint-disable-next-line react-hooks/exhaustive-deps -- 只关心 buffs 变化
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

  const worldStateForHud = useGameStore((s) => s.worldState)
  if (!player) return null

  const { profile, position, facing, state, stateLabel, usingObjectId, buffs, tags } = player
  const emotionTags = player.emotion_tags ?? []

  const currentTile = tiles.find(t => t.x === position.x && t.y === position.y)
  const zoneLabel = zoneName(currentTile) || '—'

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
      {typeof player.gold === 'number' && <Row label="金币" value={<span style={{ color: '#ffe9a8', fontWeight: 700 }}>💰 {player.gold}</span>} />}
      {(identity === 'achan' || player.agent_id === 'achan' || typeof player.dnd === 'boolean') && <DndRow playerId={player.id} dnd={!!player.dnd} tags={player.tags ?? []} />}
      <StairsRow position={position} />
      {(() => { const r = rentText(player.rent); return r ? <Row label="房租" value={<span style={{ color: r.overdue ? '#fc8181' : '#a0aec0', fontSize: 11, fontWeight: r.overdue ? 700 : 400 }}>{r.text.replace(/^🏠 /, '')}</span>} /> : null })()}
      {player.busy && <Row label="正在" value={<span style={{ color: '#9ae6b4', fontSize: 11 }}>{busyText(player.busy, gameNowMs(worldStateForHud))}</span>} />}
      {dailyUseLines(player.daily_use).map(l => <Row key={l.key} label="今日" value={<span style={{ color: l.full ? '#fc8181' : '#a0aec0', fontSize: 11 }}>{l.text}</span>} />)}

      <Divider />

      {/* 位置与朝向 */}
      <Row label="位置"   value={<span style={{ color: '#a0aec0', fontSize: 11 }}>{zoneLabel}</span>} />
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

      {/* 七变量（ARCHITECTURE §2.5）；hp 是 fullness 别名，不再单列 */}
      {NEED_KEYS.map(k => {
        const v = (player[k] ?? (k === 'fullness' ? player.hp : 0)) as number
        return (
          <div key={k} style={{ marginBottom: 5 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
              <span style={{ color: '#a0aec0' }}>{NEED_LABELS[k]} {NEED_FULL[k]}</span>
              <span style={{ fontVariantNumeric: 'tabular-nums' }}>{Math.floor(v)} / 100</span>
            </div>
            <Bar value={v} max={100} color={v < 25 ? '#e53e3e' : NEED_CSS[k]} />
          </div>
        )
      })}
      {emotionTags.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
          {emotionTags.map((t, i) => (
            <span key={i} style={{ background: '#2a2d3e', color: '#fbd38d', borderRadius: 3, padding: '1px 6px', fontSize: 11 }}>
              {t.key}{t.remaining !== null ? ` ${(t.remaining / 1000).toFixed(0)}s` : ''}
            </span>
          ))}
        </div>
      )}

      {/* 阿蝉操控台：她的分档（只读 /state）*/}
      {players.filter(p => p.controller === 'agent').map(p => {
        const v = playerVars[p.id]
        if (!v) return null
        const band = (x: number) => x < 10 ? ['紧急', '#e53e3e'] : x < 15 ? ['很差', '#ed8936'] : x < 25 ? ['偏低', '#ecc94b'] : x < 60 ? ['一般', '#a0aec0'] : ['不错', '#68d391']
        return (
          <div key={p.id} style={{ marginTop: 6 }}>
            <Divider />
            <div style={{ color: '#90cdf4', fontWeight: 600, marginBottom: 3 }}>🐳 {p.name}{p.online === false ? '（离线）' : ''}</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr auto', gap: '2px 8px', alignItems: 'center' }}>
              {NEED_KEYS.map(k => {
                const [label, color] = band(v.vars[k])
                return [
                  <span key={k + 'l'} style={{ color: '#a0aec0' }}>{NEED_LABELS[k]} {NEED_FULL[k]}</span>,
                  <Bar key={k + 'b'} value={v.vars[k]} max={100} color={color} />,
                  <span key={k + 'v'} style={{ color, fontSize: 11, minWidth: 28, textAlign: 'right' }}>{label}</span>,
                ]
              })}
            </div>
            {v.emotion_tags.length > 0 && <div style={{ color: '#fbd38d', fontSize: 11, marginTop: 3 }}>{v.emotion_tags.map(t => t.key).join(' · ')}</div>}
          </div>
        )
      })}

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
