import Phaser from 'phaser'
import { Tile, Position, TiledRenderData, TiledTilesetInfo } from '../../types'
import { GEN_TILES_KEY, GEN_TILE_COLS, TILE_INDEX, TileName, WATER_FRAMES } from '../assets'
import { AI_TILES_KEY, aiEnabled, getAiManifest, tileHash } from '../aiAssets'

/**
 * 一格的屏幕像素数。源图块为 16 px，96 = 16 × 6，相机 zoom 取 1/6 的整数倍时屏幕上是整数像素缩放。
 * （旧值 90 不是 16 的整数倍，像素会不均匀。）
 */
export { TILE_SIZE, SOURCE_TILE } from '../constants'
import { TILE_SIZE, SOURCE_TILE } from '../constants'
/** 背景按 chunk 分块烘焙，避免单张 4800×4800 超过 OBS/CEF 的纹理上限 */
const CHUNK_TILES = 10

// ── Coordinate helpers ────────────────────────────────────────────────────────

export function tileToPixel(tileX: number, tileY: number) {
  return { x: tileX * TILE_SIZE, y: tileY * TILE_SIZE }
}

export function tileCenter(tileX: number, tileY: number) {
  return { x: tileX * TILE_SIZE + TILE_SIZE / 2, y: tileY * TILE_SIZE + TILE_SIZE / 2 }
}

export function pixelToTile(pixelX: number, pixelY: number): Position | null {
  const tileX = Math.floor(pixelX / TILE_SIZE)
  const tileY = Math.floor(pixelY / TILE_SIZE)
  if (tileX < 0 || tileY < 0) return null
  return { x: tileX, y: tileY }
}

// ── GID helpers ───────────────────────────────────────────────────────────────

function getTilesetForGid(gid: number, tilesets: TiledTilesetInfo[]): TiledTilesetInfo | null {
  if (gid <= 0) return null
  let result: TiledTilesetInfo | null = null
  for (const ts of tilesets) {
    if (ts.firstgid <= gid) result = ts
    else break
  }
  return result
}

function getGidRect(gid: number, ts: TiledTilesetInfo) {
  const localId = gid - ts.firstgid
  const col = localId % ts.columns
  const row = Math.floor(localId / ts.columns)
  const sx = col * (ts.tilewidth + ts.spacing) + ts.margin
  const sy = row * (ts.tileheight + ts.spacing) + ts.margin
  return { sx, sy, sw: ts.tilewidth, sh: ts.tileheight }
}

// ── Preload helper ────────────────────────────────────────────────────────────

export function preloadTileAssets(scene: Phaser.Scene, tiledData?: TiledRenderData) {
  if (!tiledData) return
  for (const ts of tiledData.tilesets) {
    // 第三方 tileset（Sunnyside）已移出仓库（许可不允许再分发，见 WHALE_REPORT E6a）；只认 gen/ 下的自制图
    if (!ts.imageSource.startsWith('gen/')) continue
    if (!scene.textures.exists(ts.imageSource)) scene.load.image(ts.imageSource, `assets/${ts.imageSource}`)
  }
}

/** 地图尺寸（格） */
export function mapSize(tiles: Tile[], tiled?: TiledRenderData) {
  if (tiled && tiled.layers.length > 0) {
    return { w: tiled.layers[0].width, h: tiled.layers[0].height }
  }
  let w = 0, h = 0
  for (const t of tiles) { if (t.x + 1 > w) w = t.x + 1; if (t.y + 1 > h) h = t.y + 1 }
  return { w, h }
}

// ── TileMap ───────────────────────────────────────────────────────────────────

export default class TileMap {
  private images: Phaser.GameObjects.GameObject[] = []
  private textureKeys: string[] = []

  constructor(
    private scene: Phaser.Scene,
    private tiles: Tile[],
    private tiledData?: TiledRenderData,
  ) {}

  render() {
    const own = this.tiledData?.tilesets?.[0]?.imageSource === 'gen/tiles.png'
    const ai = getAiManifest()?.tiles
    if (ai && aiEnabled() && this.scene.textures.exists(AI_TILES_KEY) && this.scene.textures.exists(GEN_TILES_KEY)) {
      // W8：gpt-image-2 地砖表（32 px/格，同类多变体按格哈希挑），没有的类型（墙 / 门 / 店铺地板）退回像素表
      this.renderGenerated(ai)
    } else if (this.scene.textures.exists(GEN_TILES_KEY)) {
      // 首选：按 tile 类型 + 区域（街道 / 广场 / 公园 / 码头 / 厨房 / 餐厅…）用自制地砖画。
      // B 的 tiled 层（W5 起已指向 gen/tiles.png）只有按类型的 6 个 gid，画不出区域差异，所以只作兜底。
      this.renderGenerated()
    } else if (this.tiledData && this.tiledData.layers.length > 0 && own) {
      this.renderTiledLayers()
    } else {
      this.renderFallbackTiles()
    }
  }

  /** 类型 / 区域 → 自制地砖索引 */
  static pickTile(t: Tile, below: Tile | undefined): TileName {
    const arena = t.arena ?? ''
    // 室外按区域优先：街道 / 广场 / 码头 / 公园（后端用 grass1 标街道，类型本身不区分）
    if (t.type !== 'water' && t.type !== 'wall') {
      if (arena === 'road' || arena === 'street' || arena === 'lane') return 'road'
      if (arena === 'square' || arena === 'campus') return 'square'
      if (arena === 'dock') return 'dock'
      if (arena === 'park') return (((t.x * 73856093) ^ (t.y * 19349663)) >>> 0) % 100 < 10 ? 'grass_flower' : 'grass_park'
    }
    switch (t.type) {
      case 'water': return 'water0'
      case 'wall': return below && below.type !== 'wall' ? 'wall_face' : 'wall_top'
      case 'grass1': return 'grass_dark'
      case 'grass':
        return (((t.x * 73856093) ^ (t.y * 19349663)) >>> 0) % 100 < 6 ? 'grass_flower' : 'grass'
      case 'floor':
      case 'object':
      case 'floor_occupied':
        if (/kitchen|bath/.test(arena)) return 'floor_tile'
        if (arena === 'dining') return 'carpet'
        if (arena === 'grocer_shop') return 'shop_floor'
        if (arena === 'dock') return 'dock'
        if (arena === 'road') return 'road'
        if (arena === 'square') return 'square'
        return 'floor_wood'
      default:
        if (arena === 'road') return 'road'
        if (arena === 'square') return 'square'
        return 'grass'
    }
  }

  private renderGenerated(ai?: import('../aiAssets').AiTiles) {
    const { w: mapW, h: mapH } = mapSize(this.tiles)
    const byKey = new Map<string, Tile>()
    for (const t of this.tiles) byKey.set(`${t.x},${t.y}`, t)
    const tex = this.scene.textures.get(GEN_TILES_KEY)
    const src = tex.getSourceImage() as HTMLImageElement | HTMLCanvasElement
    const unit = ai ? ai.tile : SOURCE_TILE            // 烘焙分辨率：AI 表 32 px/格，像素表 16
    const scale = TILE_SIZE / unit
    const aiSrc = ai ? this.scene.textures.get(AI_TILES_KEY).getSourceImage() as HTMLImageElement | HTMLCanvasElement : null
    const aiFrame = (t: Tile, name: TileName): number | null => {
      if (!ai) return null
      const group = name === 'square' && t.arena === 'campus' ? 'campus' : name === 'water0' ? 'water' : name
      const vs = ai.variants[group]
      if (!vs || !vs.length) return null
      const idx = ai.index[vs[Math.floor(tileHash(t.x, t.y, 7) * vs.length) % vs.length]]
      return typeof idx === 'number' ? idx : null
    }
    const stamp = Date.now().toString(36)
    const waterTiles: Tile[] = []

    for (let cy = 0; cy < mapH; cy += CHUNK_TILES) {
      for (let cx = 0; cx < mapW; cx += CHUNK_TILES) {
        const cw = Math.min(CHUNK_TILES, mapW - cx)
        const ch = Math.min(CHUNK_TILES, mapH - cy)
        const canvas = document.createElement('canvas')
        canvas.width  = cw * unit
        canvas.height = ch * unit
        const ctx = canvas.getContext('2d')!
        ctx.imageSmoothingEnabled = !!ai
        let drew = false
        for (let ty = 0; ty < ch; ty++) {
          for (let tx = 0; tx < cw; tx++) {
            const t = byKey.get(`${cx + tx},${cy + ty}`)
            if (!t) continue
            if (t.type === 'water') { waterTiles.push(t); continue }   // 水单独做动画精灵
            const name = TileMap.pickTile(t, byKey.get(`${t.x},${t.y + 1}`))
            const af = aiFrame(t, name)
            if (ai && aiSrc && af !== null) {
              ctx.drawImage(aiSrc, (af % ai.columns) * ai.tile, Math.floor(af / ai.columns) * ai.tile, ai.tile, ai.tile, tx * unit, ty * unit, unit, unit)
            } else {
              const idx = TILE_INDEX[name]
              const sx = (idx % GEN_TILE_COLS) * SOURCE_TILE
              const sy = Math.floor(idx / GEN_TILE_COLS) * SOURCE_TILE
              ctx.drawImage(src, sx, sy, SOURCE_TILE, SOURCE_TILE, tx * unit, ty * unit, unit, unit)
            }
            drew = true
          }
        }
        if (ai) TileMap.shadeEdges(ctx, byKey, cx, cy, cw, ch, unit)
        if (!drew) continue
        const key = `gen_bg_${stamp}_${cx}_${cy}`
        const tex = this.scene.textures.addCanvas(key, canvas)
        if (ai && tex) tex.setFilter(Phaser.Textures.FilterMode.LINEAR)
        this.textureKeys.push(key)
        this.images.push(this.scene.add.image(cx * TILE_SIZE, cy * TILE_SIZE, key).setOrigin(0, 0).setScale(scale).setDepth(0))
      }
    }
    for (const t of waterTiles) {
      const aiWater = ai && this.scene.anims.exists('ai_water')
      const spr = aiWater
        ? this.scene.add.sprite(t.x * TILE_SIZE, t.y * TILE_SIZE, AI_TILES_KEY, ai!.index[ai!.variants.water[0]]).setOrigin(0, 0).setScale(TILE_SIZE / ai!.tile).setDepth(0)
        : this.scene.add.sprite(t.x * TILE_SIZE, t.y * TILE_SIZE, GEN_TILES_KEY, WATER_FRAMES[0]).setOrigin(0, 0).setScale(TILE_SIZE / SOURCE_TILE).setDepth(0)
      if (aiWater) { spr.play('ai_water'); spr.anims.setProgress(tileHash(t.x, t.y, 3)) }
      else if (this.scene.anims.exists('gen_water')) {
        spr.play('gen_water')
        // 按列错相位，像流水
        spr.anims.setProgress(((t.x + t.y) % 4) / 4)
      }
      this.images.push(spr)
    }
  }

  /** 地面交界处的软阴影：路 / 石板 / 木板 与草地相接的边描一条半透明暗线，草地一侧再压一条更淡的，让平涂的格子有「边」 */
  private static shadeEdges(ctx: CanvasRenderingContext2D, byKey: Map<string, Tile>, cx: number, cy: number, cw: number, ch: number, unit: number) {
    const kind = (t: Tile | undefined): string => {
      if (!t) return 'none'
      if (t.type === 'water') return 'water'
      if (t.type === 'wall') return 'wall'
      const a = t.arena ?? ''
      if (/street|lane|road/.test(a) || t.type === 'road') return 'road'
      if (/square|campus/.test(a)) return 'stone'
      if (a === 'dock') return 'wood'
      if (t.type === 'floor' || t.type === 'object' || t.type === 'floor_occupied') return 'floor'
      return 'grass'
    }
    const w = Math.max(1, Math.round(unit / 16))
    for (let ty = 0; ty < ch; ty++) for (let tx = 0; tx < cw; tx++) {
      const t = byKey.get(`${cx + tx},${cy + ty}`); if (!t) continue
      const k = kind(t)
      if (k !== 'grass') continue
      const px = tx * unit, py = ty * unit
      for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]] as const) {
        const nk = kind(byKey.get(`${t.x + dx},${t.y + dy}`))
        if (nk === 'grass' || nk === 'none' || nk === 'wall' || nk === 'floor') continue
        ctx.fillStyle = nk === 'water' ? 'rgba(60,110,140,0.30)' : 'rgba(60,45,25,0.13)'
        if (dx === 1) ctx.fillRect(px + unit - w, py, w, unit)
        if (dx === -1) ctx.fillRect(px, py, w, unit)
        if (dy === 1) ctx.fillRect(px, py + unit - w, unit, w)
        if (dy === -1) ctx.fillRect(px, py, unit, w)
      }
    }
  }

  destroy() {
    for (const img of this.images) img.destroy()
    this.images = []
    for (const k of this.textureKeys) {
      if (this.scene.textures.exists(k)) this.scene.textures.remove(k)
    }
    this.textureKeys = []
  }

  private renderTiledLayers() {
    const { tilesets, layers } = this.tiledData!
    const mapW = layers[0].width
    const mapH = layers[0].height
    // 以源像素烘焙（16 px/格），显示时整体放大 TILE_SIZE/16，像素更干净、内存更小
    const scale = TILE_SIZE / SOURCE_TILE

    const sources = new Map<string, HTMLImageElement | null>()
    for (const ts of tilesets) {
      const tex = this.scene.textures.get(ts.imageSource)
      const img = tex?.getSourceImage() as HTMLImageElement | undefined
      sources.set(ts.imageSource, img && img.naturalWidth ? img : null)
    }

    const stamp = Date.now().toString(36)
    for (let cy = 0; cy < mapH; cy += CHUNK_TILES) {
      for (let cx = 0; cx < mapW; cx += CHUNK_TILES) {
        const cw = Math.min(CHUNK_TILES, mapW - cx)
        const ch = Math.min(CHUNK_TILES, mapH - cy)
        const canvas = document.createElement('canvas')
        canvas.width  = cw * SOURCE_TILE
        canvas.height = ch * SOURCE_TILE
        const ctx = canvas.getContext('2d')!
        ctx.imageSmoothingEnabled = false
        let drew = false

        for (const layer of layers) {
          for (let ty = 0; ty < ch; ty++) {
            for (let tx = 0; tx < cw; tx++) {
              const col = cx + tx
              const row = cy + ty
              const gid = layer.data[row * layer.width + col]
              if (!gid || gid <= 0) continue
              const ts = getTilesetForGid(gid, tilesets)
              if (!ts) continue
              const imgEl = sources.get(ts.imageSource)
              if (!imgEl) {
                ctx.fillStyle = 'rgba(180,0,180,0.5)'
                ctx.fillRect(tx * SOURCE_TILE, ty * SOURCE_TILE, SOURCE_TILE, SOURCE_TILE)
                drew = true
                continue
              }
              const { sx, sy, sw, sh } = getGidRect(gid, ts)
              ctx.drawImage(imgEl, sx, sy, sw, sh, tx * SOURCE_TILE, ty * SOURCE_TILE, SOURCE_TILE, SOURCE_TILE)
              drew = true
            }
          }
        }
        if (!drew) continue

        const key = `tiled_bg_${stamp}_${cx}_${cy}`
        this.scene.textures.addCanvas(key, canvas)
        this.textureKeys.push(key)
        const img = this.scene.add.image(cx * TILE_SIZE, cy * TILE_SIZE, key)
          .setOrigin(0, 0)
          .setScale(scale)
          .setDepth(0)
        this.images.push(img)
      }
    }
  }

  /** 没有 Tiled 数据（B16 新地图当前如此）：按 tile.type 画色块，同样烘焙成 chunk 画布 */
  private renderFallbackTiles() {
    const FALLBACK_COLORS: Record<string, string> = {
      grass:          '#4f8a5a',
      grass1:         '#5b9663',
      floor:          '#c9ad7c',
      floor_occupied: '#a88a5e',
      wall:           '#6b5a52',
      water:          '#3e78b4',
      object:         '#b89a6c',
      road:           '#9a8f7c',
      sand:           '#d9c48a',
    }
    const { w: mapW, h: mapH } = mapSize(this.tiles)
    const byKey = new Map<string, Tile>()
    for (const t of this.tiles) byKey.set(`${t.x},${t.y}`, t)
    const scale = TILE_SIZE / SOURCE_TILE
    const stamp = Date.now().toString(36)
    // 简单的确定性噪声，让草地 / 水面有一点肌理
    const hash = (x: number, y: number) => { let h = (x * 374761393 + y * 668265263) | 0; h = (h ^ (h >>> 13)) * 1274126177; return ((h ^ (h >>> 16)) >>> 0) / 4294967295 }

    for (let cy = 0; cy < mapH; cy += CHUNK_TILES) {
      for (let cx = 0; cx < mapW; cx += CHUNK_TILES) {
        const cw = Math.min(CHUNK_TILES, mapW - cx)
        const ch = Math.min(CHUNK_TILES, mapH - cy)
        const canvas = document.createElement('canvas')
        canvas.width  = cw * SOURCE_TILE
        canvas.height = ch * SOURCE_TILE
        const ctx = canvas.getContext('2d')!
        ctx.imageSmoothingEnabled = false
        let drew = false
        for (let ty = 0; ty < ch; ty++) {
          for (let tx = 0; tx < cw; tx++) {
            const t = byKey.get(`${cx + tx},${cy + ty}`)
            if (!t) continue
            const base = FALLBACK_COLORS[t.type] ?? '#888888'
            ctx.fillStyle = base
            ctx.fillRect(tx * SOURCE_TILE, ty * SOURCE_TILE, SOURCE_TILE, SOURCE_TILE)
            const n = hash(t.x, t.y)
            if (t.type.startsWith('grass') || t.type === 'water') {
              ctx.fillStyle = t.type === 'water' ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.07)'
              if (n > 0.6) ctx.fillRect(tx * SOURCE_TILE + 4, ty * SOURCE_TILE + 6, 3, 2)
              if (n > 0.85) ctx.fillRect(tx * SOURCE_TILE + 10, ty * SOURCE_TILE + 11, 2, 2)
            }
            if (t.type === 'wall') {
              ctx.fillStyle = 'rgba(0,0,0,0.25)'
              ctx.fillRect(tx * SOURCE_TILE, ty * SOURCE_TILE + SOURCE_TILE - 2, SOURCE_TILE, 2)
              ctx.fillStyle = 'rgba(255,255,255,0.10)'
              ctx.fillRect(tx * SOURCE_TILE, ty * SOURCE_TILE, SOURCE_TILE, 1)
            }
            if (t.type === 'floor' || t.type === 'object') {
              ctx.fillStyle = 'rgba(0,0,0,0.08)'
              ctx.fillRect(tx * SOURCE_TILE, ty * SOURCE_TILE, SOURCE_TILE, 1)
              ctx.fillRect(tx * SOURCE_TILE, ty * SOURCE_TILE, 1, SOURCE_TILE)
            }
            drew = true
          }
        }
        if (!drew) continue
        const key = `fallback_bg_${stamp}_${cx}_${cy}`
        this.scene.textures.addCanvas(key, canvas)
        this.textureKeys.push(key)
        this.images.push(this.scene.add.image(cx * TILE_SIZE, cy * TILE_SIZE, key).setOrigin(0, 0).setScale(scale).setDepth(0))
      }
    }
  }
}
