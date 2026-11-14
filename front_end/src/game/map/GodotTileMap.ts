/**
 * Godot 口径的地图渲染（同步 ②）：语义格 → 自动拼接 → ground / overlay 两层按 10×10 格分块烘焙成画布（48 px/格 ×2，NEAREST），
 * structures（门 / 楼梯格）逐格贴图并可按开关态换 door / door_open。屋顶 / 外观 / focus-only 层由 GameScene（③④）处理。
 */
import Phaser from 'phaser'
import type { Tile, GameObject } from '../../types'
import { TILE_SIZE } from '../constants'
import { planMap, tileCell, type Cell, type EdgeLike, type MapPlan } from '../godotMap'
import { godotRules, godotTiles, godotTilesFallback, godotTilesTex } from '../godotMapLoad'

const CHUNK = 10
export const DEPTH_GROUND = 0
export const DEPTH_OVERLAY = 0.05
export const DEPTH_STRUCT = 0.2

export default class GodotTileMap {
  private nodes: Phaser.GameObjects.GameObject[] = []
  private textureKeys: string[] = []
  private doorNodes = new Map<string, Phaser.GameObjects.Image>()
  private plan: MapPlan | null = null

  constructor(private scene: Phaser.Scene, private tiles: Tile[], private objects: GameObject[], private edges: EdgeLike[]) {}

  render() {
    const rules = godotRules(), main = godotTiles()
    if (!rules || !main) return
    const fb = godotTilesFallback()
    this.plan = planMap(this.tiles, this.objects, this.edges, rules, main, fb && this.scene.textures.exists(godotTilesTex('fb')) ? fb : null)
    this.bake(this.plan.ground, DEPTH_GROUND, 'g')
    this.bake(this.plan.overlay, DEPTH_OVERLAY, 'o')
    for (const c of this.plan.structures) this.nodes.push(this.cellImage(c, DEPTH_STRUCT))
    const miss = Object.entries(this.plan.missing)
    if (miss.length) console.info('[godotMap] semantic tiles missing in set (fell back to grass):', Object.fromEntries(miss))
  }

  private frameOf(c: Cell) {
    const meta = c.src === 'main' ? godotTiles()! : godotTilesFallback()!
    return { tex: godotTilesTex(c.src), sx: (c.idx % meta.columns) * meta.tile, sy: Math.floor(c.idx / meta.columns) * meta.tile, tile: meta.tile }
  }

  private cellImage(c: Cell, depth: number): Phaser.GameObjects.Image {
    const f = this.frameOf(c)
    const tex = this.scene.textures.get(f.tex)
    const fname = `c_${c.idx}`
    if (!tex.has(fname)) tex.add(fname, 0, f.sx, f.sy, f.tile, f.tile)
    return this.scene.add.image(c.x * TILE_SIZE, c.y * TILE_SIZE, f.tex, fname).setOrigin(0, 0).setDisplaySize(TILE_SIZE, TILE_SIZE).setDepth(depth)
  }

  /** 一层的格子按块烘焙（源 48 px/格，显示 ×2） */
  private bake(cells: Cell[], depth: number, tag: string) {
    if (!cells.length) return
    const unit = godotTiles()!.tile
    const scale = TILE_SIZE / unit
    const srcMain = this.scene.textures.get(godotTilesTex('main')).getSourceImage() as CanvasImageSource
    const srcFb = this.scene.textures.exists(godotTilesTex('fb')) ? this.scene.textures.get(godotTilesTex('fb')).getSourceImage() as CanvasImageSource : null
    const chunks = new Map<string, Cell[]>()
    for (const c of cells) {
      const k = `${Math.floor(c.x / CHUNK)}_${Math.floor(c.y / CHUNK)}`
      let arr = chunks.get(k); if (!arr) { arr = []; chunks.set(k, arr) }
      arr.push(c)
    }
    const stamp = Date.now().toString(36)
    for (const [k, arr] of chunks) {
      const [cxs, cys] = k.split('_').map(Number)
      const canvas = document.createElement('canvas')
      canvas.width = CHUNK * unit; canvas.height = CHUNK * unit
      const ctx = canvas.getContext('2d')!
      ctx.imageSmoothingEnabled = false
      for (const c of arr) {
        const f = this.frameOf(c)
        const src = c.src === 'main' ? srcMain : srcFb
        if (!src) continue
        ctx.drawImage(src, f.sx, f.sy, f.tile, f.tile, (c.x - cxs * CHUNK) * unit, (c.y - cys * CHUNK) * unit, unit, unit)
      }
      const key = `gmap_${tag}_${stamp}_${k}`
      const tex = this.scene.textures.addCanvas(key, canvas)
      tex?.setFilter(Phaser.Textures.FilterMode.NEAREST)
      this.textureKeys.push(key)
      this.nodes.push(this.scene.add.image(cxs * CHUNK * TILE_SIZE, cys * CHUNK * TILE_SIZE, key).setOrigin(0, 0).setScale(scale).setDepth(depth))
    }
  }

  /** 门开关：structures 层换 door / door_open（同 MapRenderer.set_door） */
  setDoor(doorId: string, open: boolean) {
    const cell = this.plan?.doors.get(doorId)
    const main = godotTiles(); if (!cell || !main) return
    const c = tileCell(main, godotTilesFallback(), open ? 'door_open' : 'door', cell.x, cell.y)
    if (!c) return
    this.doorNodes.get(doorId)?.destroy()
    const img = this.cellImage(c, DEPTH_STRUCT + 0.01)
    this.doorNodes.set(doorId, img)
    this.nodes.push(img)
  }

  /** 某格的语义名（调试 / ③④ 用） */
  semanticAt(x: number, y: number) { return this.plan?.semOf.get(`${x},${y}`) ?? null }

  destroy() {
    for (const n of this.nodes) n.destroy()
    this.nodes = []
    this.doorNodes.clear()
    for (const k of this.textureKeys) if (this.scene.textures.exists(k)) this.scene.textures.remove(k)
    this.textureKeys = []
  }
}
