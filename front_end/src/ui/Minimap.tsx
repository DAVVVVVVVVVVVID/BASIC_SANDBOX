import { useEffect, useRef } from 'react'
import { useGameStore } from '../store/gameStore'

const TILE_COLORS: Record<string, string> = {
  grass:          '#4a7c59',
  wall:           '#5c3d2e',
  floor:          '#c8a96e',
  floor_occupied: '#9e7c4a',
}
const UNKNOWN_COLOR  = '#888888'
const PLAYER_COLOR   = '#63b3ed'
const MINIMAP_MAX_W  = 180
const MINIMAP_MAX_H  = 140
const BORDER_RADIUS  = 6
const PADDING        = 8

export default function Minimap() {
  const tiles  = useGameStore((s) => s.tiles)
  const player = useGameStore((s) => s.player)
  const canvasRef = useRef<HTMLCanvasElement>(null)

  const mapW = tiles.length > 0 ? Math.max(...tiles.map(t => t.x)) + 1 : 0
  const mapH = tiles.length > 0 ? Math.max(...tiles.map(t => t.y)) + 1 : 0

  const cellW = mapW > 0 ? Math.max(2, Math.floor(MINIMAP_MAX_W / mapW)) : 4
  const cellH = mapH > 0 ? Math.max(2, Math.floor(MINIMAP_MAX_H / mapH)) : 4
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

    if (player) {
      const px = player.position.x * cell + cell / 2
      const py = player.position.y * cell + cell / 2
      const r  = Math.max(2, cell * 0.7)
      ctx.fillStyle = PLAYER_COLOR
      ctx.beginPath()
      ctx.arc(px, py, r, 0, Math.PI * 2)
      ctx.fill()
    }
  }, [tiles, player, canvasW, canvasH, cell, mapW])

  if (mapW === 0) return null

  return (
    <div style={{
      position: 'fixed',
      bottom: PADDING,
      right: PADDING,
      background: 'rgba(0,0,0,0.65)',
      borderRadius: BORDER_RADIUS,
      padding: 4,
      border: '1px solid rgba(255,255,255,0.15)',
      pointerEvents: 'none',
    }}>
      <canvas ref={canvasRef} width={canvasW} height={canvasH} />
    </div>
  )
}
