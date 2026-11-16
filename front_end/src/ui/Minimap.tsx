import { useEffect, useRef } from 'react'
import { useGameStore } from '../store/gameStore'
import { sectorName } from '../game/map/zones'

const TILE_COLORS: Record<string, string> = {
  grass:          '#4a7c59',
  grass1:         '#3f6f4c',
  wall:           '#5c3d2e',
  floor:          '#c8a96e',
  floor_occupied: '#9e7c4a',
  object:         '#b08a5a',
  water:          '#3d7fc4',
}
const UNKNOWN_COLOR  = '#888888'
const PLAYER_COLOR   = '#63b3ed'
const OTHER_COLOR    = '#f6ad55'
const MINIMAP_MAX_W  = 240
const MINIMAP_MAX_H  = 160
const BORDER_RADIUS  = 6
const PADDING        = 8

interface Props {
  /** W9 任务 0：旁观页用——点一格跳过去；viewport = 当前镜头覆盖的格（画白框） */
  onClickTile?: (x: number, y: number) => void
  viewport?: { x0: number; y0: number; x1: number; y1: number } | null
  followId?: string | null
  /** 旁观页：在面板内部排版（不用 fixed 居右） */
  inline?: boolean
  /** 「地图」面板：放大一倍 */
  large?: boolean
}

export default function Minimap({ onClickTile, viewport, followId, inline, large }: Props = {}) {
  const tiles  = useGameStore((s) => s.tiles)
  const player = useGameStore((s) => s.player)
  const players = useGameStore((s) => s.players)
  const myId = useGameStore((s) => s.myPlayerId)
  const canvasRef = useRef<HTMLCanvasElement>(null)

  const mapW = tiles.length > 0 ? Math.max(...tiles.map(t => t.x)) + 1 : 0
  const mapH = tiles.length > 0 ? Math.max(...tiles.map(t => t.y)) + 1 : 0

  const K = large ? 2 : 1
  const cellW = mapW > 0 ? Math.max(2, Math.floor(MINIMAP_MAX_W * K / mapW)) : 4
  const cellH = mapH > 0 ? Math.max(2, Math.floor(MINIMAP_MAX_H * K / mapH)) : 4
  const cell  = Math.min(cellW, cellH)

  const canvasW = mapW * cell
  const canvasH = mapH * cell

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || mapW === 0) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    ctx.clearRect(0, 0, canvasW, canvasH)

    for (const t of tiles) {
      ctx.fillStyle = TILE_COLORS[t.type] ?? UNKNOWN_COLOR
      ctx.fillRect(t.x * cell, t.y * cell, cell, cell)
    }

    // 区域名：每个室内 sector 的质心
    const cent = new Map<string, { sx: number; sy: number; n: number }>()
    for (const t of tiles) {
      if (!t.sector || t.sector === 'outside') continue
      const c = cent.get(t.sector) ?? { sx: 0, sy: 0, n: 0 }
      c.sx += t.x; c.sy += t.y; c.n++
      cent.set(t.sector, c)
    }
    ctx.font = `${Math.max(8, cell * 2.2)}px system-ui, sans-serif`
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
    for (const [sec, c] of cent) {
      const x = (c.sx / c.n + 0.5) * cell, y = (c.sy / c.n + 0.5) * cell
      ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(0,0,0,0.8)'; ctx.strokeText(sectorName(sec), x, y)
      ctx.fillStyle = '#ffffff'; ctx.fillText(sectorName(sec), x, y)
    }

    for (const op of players) {
      if (op.id === myId) continue
      ctx.fillStyle = op.id === followId ? PLAYER_COLOR : OTHER_COLOR
      ctx.globalAlpha = op.online === false ? 0.4 : 1
      ctx.beginPath()
      ctx.arc(op.position.x * cell + cell / 2, op.position.y * cell + cell / 2, Math.max(2, cell * 0.6), 0, Math.PI * 2)
      ctx.fill()
      ctx.globalAlpha = 1
    }

    if (player) {
      const px = player.position.x * cell + cell / 2
      const py = player.position.y * cell + cell / 2
      const r  = Math.max(2, cell * 0.7)
      ctx.fillStyle = PLAYER_COLOR
      ctx.beginPath()
      ctx.arc(px, py, r, 0, Math.PI * 2)
      ctx.fill()
    }
    if (viewport) {
      ctx.strokeStyle = 'rgba(255,255,255,0.9)'; ctx.lineWidth = 1.5
      ctx.strokeRect(viewport.x0 * cell, viewport.y0 * cell, (viewport.x1 - viewport.x0) * cell, (viewport.y1 - viewport.y0) * cell)
    }
  }, [tiles, player, players, myId, canvasW, canvasH, cell, mapW, viewport, followId])

  if (mapW === 0) return null

  const onClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!onClickTile) return
    const r = e.currentTarget.getBoundingClientRect()
    onClickTile(Math.floor((e.clientX - r.left) / cell), Math.floor((e.clientY - r.top) / cell))
  }
  return (
    <div style={inline ? { background: 'rgba(0,0,0,0.65)', borderRadius: BORDER_RADIUS, padding: 4, border: '1px solid rgba(255,255,255,0.15)', display: 'inline-block' } : {
      position: 'fixed',
      top: '50%',
      right: PADDING,
      transform: 'translateY(-50%)',
      background: 'rgba(0,0,0,0.65)',
      borderRadius: BORDER_RADIUS,
      padding: 4,
      border: '1px solid rgba(255,255,255,0.15)',
      pointerEvents: onClickTile ? 'auto' : 'none',
    }}>
      <canvas ref={canvasRef} width={canvasW} height={canvasH} onClick={onClick} style={{ cursor: onClickTile ? 'crosshair' : 'default', display: 'block' }} />
    </div>
  )
}
