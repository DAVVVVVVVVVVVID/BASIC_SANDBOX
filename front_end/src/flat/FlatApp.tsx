import { useEffect, useRef, useState } from 'react'
import { API_BASE } from '../api/client'
import { parseMapV2, arenaBBox } from '../game/map/mapv2'
import type { Tile, WorldData } from '../types'

/**
 * `/flat?sector=home&floor=1&px=32&view=interior|exterior&margin=1`
 * 美术管线（W8）第一步：把某区域的平涂版式画成一张整数倍 tile 的 PNG，作为 gpt-image-2 `images.edit` 的版式输入。
 * 只画墙 / 地板 / 门 / 楼梯口 / 周边地面，不画可变物品与角色。exterior 视图把室内填成屋顶色、墙成外墙色，给模型画屋顶用。
 * 画完后 window.__flatMeta 写入 {x0,y0,w,h,px,view}，供导出脚本裁剪与对齐 QA。
 */
const COLORS: Record<string, string> = {
  grass: '#7fb87a', grass1: '#6ea36d', wall: '#7a6a63', floor: '#d9b98c', object: '#d9b98c', water: '#6aa2d6',
  road: '#b9a98a', square: '#cfc3ad', park: '#73ad72', dock: '#b48a5a', carpet: '#b86a62', tile: '#e8e2d2', door: '#9a6a3e', stairs: '#c9a673',
  roof: '#5b6fb5', roof_edge: '#3f4f8a', outer_wall: '#8a7a72',
}

export default function FlatApp() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [status, setStatus] = useState('加载中…')
  useEffect(() => {
    const q = new URLSearchParams(window.location.search)
    const sector = q.get('sector') || 'home'
    const floor = Number(q.get('floor') || 1)
    const px = Math.max(8, Math.min(96, Number(q.get('px') || 32)))
    const view = q.get('view') === 'exterior' ? 'exterior' : 'interior'
    const margin = Math.max(0, Math.min(4, Number(q.get('margin') ?? 1)))
    fetch(`${API_BASE}/world`).then(r => r.json()).then((world: WorldData) => {
      const v2 = parseMapV2(world as unknown as Parameters<typeof parseMapV2>[0])
      const tiles = world.tiles.filter(t => v2.floorOf(t) === floor)
      const b = arenaBBox(tiles, sector) ?? arenaBBox(tiles, null, sector)
      if (!b) { setStatus(`找不到区域 ${sector}`); return }
      const x0 = b.x0 - margin, y0 = b.y0 - margin, w = b.x1 - b.x0 + 1 + margin * 2, h = b.y1 - b.y0 + 1 + margin * 2
      const idx = new Map<string, Tile>(); for (const t of world.tiles) idx.set(`${t.x},${t.y}`, t)
      const c = canvasRef.current!; c.width = w * px; c.height = h * px
      const g = c.getContext('2d')!
      const inSector = (t: Tile | undefined) => !!t && (t.sector === sector || t.arena === sector) && v2.floorOf(t) === floor
      // 外观：区域包围盒最下一行当「正面墙」（3/4 视角能看见门窗的那一面）
      const facadeRow = b.y1
      for (let ty = 0; ty < h; ty++) for (let tx = 0; tx < w; tx++) {
        const t = idx.get(`${x0 + tx},${y0 + ty}`)
        let col = COLORS.grass
        if (t) {
          const arena = t.arena ?? ''
          if (t.type === 'water') col = COLORS.water
          else if (view === 'exterior' && inSector(t)) col = (t.y === facadeRow) ? COLORS.outer_wall : COLORS.roof
          else if (t.type === 'wall') col = COLORS.wall
          else if (/road|street|lane/.test(arena)) col = COLORS.road
          else if (/square|campus/.test(arena)) col = COLORS.square
          else if (arena === 'park') col = COLORS.park
          else if (arena === 'dock') col = COLORS.dock
          else if (t.type === 'floor' || t.type === 'object') col = /kitchen|bath/.test(arena) ? COLORS.tile : arena === 'dining' ? COLORS.carpet : COLORS.floor
          else if (t.type === 'grass1') col = COLORS.grass1
        }
        g.fillStyle = col; g.fillRect(tx * px, ty * px, px, px)
        // 室内地板画淡格线，帮模型保持网格；屋顶画斜向瓦线
        if (t && view === 'interior' && (t.type === 'floor' || t.type === 'object') && inSector(t)) { g.strokeStyle = 'rgba(0,0,0,0.07)'; g.strokeRect(tx * px + 0.5, ty * px + 0.5, px - 1, px - 1) }
      }
      // 门 / 楼梯口
      for (const e of v2.edges) {
        for (const p of e.tiles) {   // 门：a 外 b 内；楼梯：a 1F b 2F —— 在本区域内的那一端画出来
          const t = idx.get(`${p.x},${p.y}`)
          if (!t || !inSector(t)) continue
          g.fillStyle = e.type === 'stairs' ? COLORS.stairs : COLORS.door
          g.fillRect((p.x - x0) * px + px * 0.15, (p.y - y0) * px + px * 0.15, px * 0.7, px * 0.7)
        }
      }
      if (view === 'exterior') {
        // 屋顶边线：与非屋顶相邻的屋顶格描边
        g.strokeStyle = COLORS.roof_edge; g.lineWidth = Math.max(2, px / 8)
        for (let ty = 0; ty < h; ty++) for (let tx = 0; tx < w; tx++) {
          const t = idx.get(`${x0 + tx},${y0 + ty}`); if (!inSector(t)) continue
          const nb = [[1, 0], [-1, 0], [0, 1], [0, -1]].some(([dx, dy]) => !inSector(idx.get(`${x0 + tx + dx},${y0 + ty + dy}`)))
          if (nb) g.strokeRect(tx * px + 1, ty * px + 1, px - 2, px - 2)
        }
      }
      ;(window as unknown as { __flatMeta: unknown }).__flatMeta = { sector, floor, view, x0, y0, w, h, px, margin, mapVersion: world.worldState?.mapVersion ?? null }
      setStatus(`${sector} ${floor}F ${view} ${w}×${h} 格 @${px}px`)
      document.title = `flat:${sector}:${floor}:${view}`
    }).catch(e => setStatus(String(e)))
  }, [])
  return (
    <div style={{ background: '#111', minHeight: '100vh', color: '#ccc', fontFamily: 'monospace', padding: 8 }}>
      <div id="flat-status" style={{ fontSize: 12, marginBottom: 6 }}>{status}</div>
      <canvas ref={canvasRef} style={{ imageRendering: 'pixelated', display: 'block' }} />
    </div>
  )
}
