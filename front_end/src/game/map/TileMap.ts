import Phaser from 'phaser'
import { Tile, Position, TiledRenderData, TiledTilesetInfo } from '../../types'

/**
 * 一格的屏幕像素数。源图块为 16 px，96 = 16 × 6，相机 zoom 取 1/6 的整数倍时屏幕上是整数像素缩放。
 * （旧值 90 不是 16 的整数倍，像素会不均匀。）
 */
export const TILE_SIZE = 96
export const SOURCE_TILE = 16
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
    if (!scene.textures.exists(ts.imageSource)) {
      scene.load.image(ts.imageSource, `assets/tilesets/${ts.imageSource}`)
    }
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
    if (this.tiledData && this.tiledData.layers.length > 0) {
      this.renderTiledLayers()
    } else {
      this.renderFallbackTiles()
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
