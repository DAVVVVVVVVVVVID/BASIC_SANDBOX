import Phaser from 'phaser'
import type { Tile, WorldState } from '../../types'
import { TILE_SIZE } from '../map/TileMap'
import { parseMapV2, arenaBBox, isIndoor, edgeLockedNow, arenaLockedNow, type MapV2, type MapEdge } from '../map/mapv2'
import { objTextureKey } from '../assets'
import { arenaName } from '../map/zones'

const DIM_ALPHA = 0.58
const DIM_DEPTH = 9000
const FADE_MS = 420
const ZOOM_MS = 650
const MAX_FOCUS_ZOOM = 1.5

/**
 * W7 按区域取景 + 楼层 + 锁门表现（只读呈现，不改世界）：
 *  - 跟随目标进室内：相机推近到该场所（同一楼层的 sector 包围盒），屋外压暗；出门还原
 *  - 楼梯边画楼梯图示；门边在锁定时段画成关着的门 + 时段提示
 *  - `locked` 动作事件由 GameScene 转成气泡
 */
export default class SceneFocus {
  private dim: Phaser.GameObjects.Graphics
  private dimAlpha = 0
  private dimTarget = 0
  private focusKey = ''
  private bbox: { x0: number; y0: number; x1: number; y1: number } | null = null
  private mapPx = { w: 0, h: 0 }
  private v2: MapV2
  private tileIndex = new Map<string, Tile>()
  private edgeNodes: Phaser.GameObjects.GameObject[] = []
  private edgeNodeTiles: { node: Phaser.GameObjects.GameObject; tile: { x: number; y: number } }[] = []
  private doorNodes: { edge: MapEdge; img: Phaser.GameObjects.Image; label: Phaser.GameObjects.Text }[] = []
  private lastLockSig = ''
  private indoor = false
  private labelScale = 1
  private labels: Phaser.GameObjects.Text[] = []

  constructor(private scene: Phaser.Scene, private opts: { enabled: boolean; baseZoom: () => number; snap: (z: number) => number }) {
    this.dim = scene.add.graphics().setDepth(DIM_DEPTH).setAlpha(0)
    this.v2 = parseMapV2({ tiles: [] })
  }

  /** 地图（重）建后调用 */
  setMap(world: { tiles: Tile[]; edges?: unknown[]; floors?: unknown; access?: unknown; arenas?: unknown[]; map?: unknown }, mapW: number, mapH: number) {
    this.mapPx = { w: mapW * TILE_SIZE, h: mapH * TILE_SIZE }
    this.v2 = parseMapV2(world)
    this.tileIndex = new Map(world.tiles.map(t => [`${t.x},${t.y}`, t]))
    for (const n of this.edgeNodes) n.destroy()
    this.edgeNodes = []
    this.edgeNodeTiles = []
    for (const d of this.doorNodes) { d.img.destroy(); d.label.destroy() }
    this.doorNodes = []
    this.labels = []
    this.lastLockSig = ''
    // 楼梯图示
    for (const e of this.v2.edges) {
      if (e.type !== 'stairs' || !this.scene.textures.exists(objTextureKey('stairs'))) continue
      for (const p of e.tiles) {
        const img = this.scene.add.image(p.x * TILE_SIZE + TILE_SIZE / 2, p.y * TILE_SIZE + TILE_SIZE / 2, objTextureKey('stairs')).setDisplaySize(TILE_SIZE - 8, TILE_SIZE - 8).setDepth(2)
        const f = e.floors ? `${e.floors[0]}F↔${e.floors[1]}F` : '楼梯'
        const t = this.scene.add.text(p.x * TILE_SIZE + TILE_SIZE / 2, p.y * TILE_SIZE - 2, f, { fontFamily: 'system-ui, sans-serif', fontSize: '12px', color: '#fff', stroke: '#000', strokeThickness: 3 }).setOrigin(0.5, 1).setDepth(3).setResolution(2)
        this.edgeNodes.push(img, t); this.labels.push(t); this.edgeNodeTiles.push({ node: img, tile: p }, { node: t, tile: p })
      }
    }
    // 门（有时段的）
    for (const e of this.v2.edges) {
      if (e.type !== 'door' || e.tiles.length === 0) continue
      const locksByAccess = (e.to && this.v2.access.get(e.to)?.lockHours) || (e.from && this.v2.access.get(e.from)?.lockHours)
      if (!e.openHours && !locksByAccess) continue
      if (!this.scene.textures.exists(objTextureKey('door_closed'))) continue
      for (const p of e.tiles.slice(-1)) {   // a=外侧格、b=内侧格：门画在内侧那一格
        const img = this.scene.add.image(p.x * TILE_SIZE + TILE_SIZE / 2, p.y * TILE_SIZE + TILE_SIZE / 2, objTextureKey('door_closed')).setDisplaySize(TILE_SIZE, TILE_SIZE).setDepth(2).setVisible(false)
        const fmt = (h: { start: string; end: string }, kind: '开' | '锁') => (h.start === '00:00' && h.end === '24:00') ? (kind === '锁' ? '常锁' : '常开') : `${kind} ${h.start}–${h.end}`
        const hours = e.openHours ? fmt(e.openHours, '开') : locksByAccess ? fmt(locksByAccess, '锁') : ''
        const who = e.to && this.v2.access.get(e.to)?.owner ? `（${arenaName(e.to)}）` : ''
        const label = this.scene.add.text(p.x * TILE_SIZE + TILE_SIZE / 2, p.y * TILE_SIZE - 4, `🔒 ${hours}${who}`, { fontFamily: 'system-ui, "PingFang SC", sans-serif', fontSize: '12px', color: '#ffd7d7', stroke: '#000', strokeThickness: 3 }).setOrigin(0.5, 1).setDepth(3).setResolution(2).setVisible(false)
        this.doorNodes.push({ edge: e, img, label }); this.labels.push(label)
      }
    }
  }

  get hasV2() { return this.v2.hasV2 }
  /** W8：屋顶视图下藏起楼梯 / 门标记（roofed = 有屋顶且当前没进入的 sector） */
  setRoofed(isRoofed: (tile: { x: number; y: number }) => boolean) {
    for (const { node, tile } of this.edgeNodeTiles) (node as unknown as { setVisible: (b: boolean) => void }).setVisible(!isRoofed(tile))
    for (const d of this.doorNodes) { const p = d.edge.tiles[d.edge.tiles.length - 1]; if (p && isRoofed(p)) { d.img.setVisible(false); d.label.setVisible(false) } }
  }
  /** W8：AI 室内底图里已经画了楼梯 → 这些格的像素楼梯图示不再叠画（文字标签保留） */
  /** 门 / 楼梯两端的格（装饰撒点要避开门口） */
  doorTiles(): { x: number; y: number }[] { return this.v2 ? this.v2.edges.flatMap(e => e.tiles) : [] }

  hideStairIcons(covered: (tile: { x: number; y: number }) => boolean) {
    for (const { node, tile } of this.edgeNodeTiles) if (node instanceof Phaser.GameObjects.Image && covered(tile)) node.setVisible(false)
  }
  /** 调试 */
  debugLabels() { return this.labels.map(l => ({ text: l.text, scale: l.scaleX, visible: l.visible, x: l.x, y: l.y, depth: l.depth })) }
  /** 某 sector 或 arena（可选楼层）的中心格，给 &focus= 用 */
  sectorCenter(id: string, floor = 1): { x: number; y: number } | null {
    const tiles = [...this.tileIndex.values()].filter(t => this.v2.floorOf(t) === floor)
    const b = arenaBBox(tiles, id) ?? arenaBBox(tiles, null, id)
    if (!b) return null
    return { x: Math.round((b.x0 + b.x1) / 2), y: Math.round((b.y0 + b.y1) / 2) }
  }
  floorOf(t: Tile | null | undefined) { return this.v2.floorOf(t) }
  tileAt(x: number, y: number) { return this.tileIndex.get(`${x},${y}`) }

  /** 每帧：focus = 跟随目标 / 自己所在格；返回当前是否室内（给相机用） */
  update(focus: { x: number; y: number } | null, dt: number, ws: WorldState | null): { indoor: boolean; zoom: number | null; label: string } {
    // 标签在屏幕上保持可读大小
    const ls = Phaser.Math.Clamp(1 / this.scene.cameras.main.zoom, 1, 6)
    if (Math.abs(ls - this.labelScale) > 1e-3) { this.labelScale = ls; for (const l of this.labels) l.setScale(ls) }
    // 门的开关状态（每秒级变化，签名变了才改）
    const time = ws?.time
    const sig = time?.slice(0, 5) ?? ''
    if (sig !== this.lastLockSig) {
      this.lastLockSig = sig
      for (const d of this.doorNodes) {
        const byAccess = (d.edge.to && arenaLockedNow(this.v2.access.get(d.edge.to), time)) || (d.edge.from && arenaLockedNow(this.v2.access.get(d.edge.from), time))
        const locked = edgeLockedNow(d.edge, time) || !!byAccess
        d.img.setVisible(locked); d.label.setVisible(locked)
      }
    }

    let indoor = false, key = '', label = ''
    let bbox: { x0: number; y0: number; x1: number; y1: number } | null = null
    if (this.opts.enabled && focus) {
      const t = this.tileIndex.get(`${focus.x},${focus.y}`)
      if (t && isIndoor(t)) {
        const f = this.v2.floorOf(t)
        key = `${t.sector}|${f}`
        const b = arenaBBox(this.tileIndex.size ? [...this.tileIndex.values()].filter(x => this.v2.floorOf(x) === f) : [], t.sector)
        if (b) { bbox = b; indoor = true; label = f > 1 ? `${f}F` : '' }
      }
    }
    if (key !== this.focusKey) {
      this.focusKey = key
      this.bbox = bbox
      this.dimTarget = indoor ? DIM_ALPHA : 0
      if (indoor && bbox) this.redraw()
    }
    // 渐变
    if (this.dimAlpha !== this.dimTarget) {
      const step = dt / FADE_MS * DIM_ALPHA
      this.dimAlpha = this.dimTarget > this.dimAlpha ? Math.min(this.dimTarget, this.dimAlpha + step) : Math.max(this.dimTarget, this.dimAlpha - step)
      this.dim.setAlpha(this.dimAlpha)
    }
    this.indoor = indoor
    // 推近 zoom：场所包围盒（外扩 1 格）放进画面
    let zoom: number | null = null
    if (indoor && bbox) {
      const cam = this.scene.cameras.main
      const w = (bbox.x1 - bbox.x0 + 3) * TILE_SIZE, h = (bbox.y1 - bbox.y0 + 3) * TILE_SIZE
      zoom = this.opts.snap(Phaser.Math.Clamp(Math.min(cam.width / w, cam.height / h), this.opts.baseZoom(), MAX_FOCUS_ZOOM))
    }
    return { indoor, zoom, label }
  }

  /** 相机想居中的点：室内时限制在场所包围盒内（画面别跑到屋外去） */
  clampCenter(x: number, y: number, zoom: number): { x: number; y: number } {
    if (!this.indoor || !this.bbox) return { x, y }
    const cam = this.scene.cameras.main
    const vw = cam.width / zoom, vh = cam.height / zoom
    const bx0 = (this.bbox.x0 - 1) * TILE_SIZE, bx1 = (this.bbox.x1 + 2) * TILE_SIZE
    const by0 = (this.bbox.y0 - 1) * TILE_SIZE, by1 = (this.bbox.y1 + 2) * TILE_SIZE
    const cx = bx1 - bx0 <= vw ? (bx0 + bx1) / 2 : Phaser.Math.Clamp(x, bx0 + vw / 2, bx1 - vw / 2)
    const cy = by1 - by0 <= vh ? (by0 + by1) / 2 : Phaser.Math.Clamp(y, by0 + vh / 2, by1 - vh / 2)
    return { x: cx, y: cy }
  }

  private redraw() {
    const g = this.dim
    g.clear()
    if (!this.bbox) return
    const x0 = this.bbox.x0 * TILE_SIZE, y0 = this.bbox.y0 * TILE_SIZE
    const x1 = (this.bbox.x1 + 1) * TILE_SIZE, y1 = (this.bbox.y1 + 1) * TILE_SIZE
    const W = Math.max(this.mapPx.w, x1) + TILE_SIZE * 40, H = Math.max(this.mapPx.h, y1) + TILE_SIZE * 40
    const M = TILE_SIZE * 40
    g.fillStyle(0x070812, 1)
    g.fillRect(-M, -M, W + M, y0 + M)                 // 上
    g.fillRect(-M, y1, W + M, H - y1 + M)             // 下
    g.fillRect(-M, y0, x0 + M, y1 - y0)               // 左
    g.fillRect(x1, y0, W - x1 + M, y1 - y0)           // 右
  }

  destroy() {
    this.dim.destroy()
    for (const n of this.edgeNodes) n.destroy()
    for (const d of this.doorNodes) { d.img.destroy(); d.label.destroy() }
  }
}
export { ZOOM_MS }
