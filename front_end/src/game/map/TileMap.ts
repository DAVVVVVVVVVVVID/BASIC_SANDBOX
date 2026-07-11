import Phaser from 'phaser'
import { Tile, Position, TiledRenderData, TiledTilesetInfo } from '../../types'

export const TILE_SIZE = 90

// ── Coordinate helpers ────────────────────────────────────────────────────────

export function tileToPixel(tileX: number, tileY: number) {
  return { x: tileX * TILE_SIZE, y: tileY * TILE_SIZE }
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
    scene.load.image(ts.imageSource, `assets/tilesets/${ts.imageSource}`)
  }
}

// ── TileMap ───────────────────────────────────────────────────────────────────

export default class TileMap {
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

  private renderTiledLayers() {
    const { tilesets, layers } = this.tiledData!
    if (layers.length === 0) return

    const mapW = layers[0].width
    const mapH = layers[0].height
    const canvasW = mapW * TILE_SIZE
    const canvasH = mapH * TILE_SIZE

    const offscreen = document.createElement('canvas')
    offscreen.width  = canvasW
    offscreen.height = canvasH
    const ctx = offscreen.getContext('2d')!
    ctx.imageSmoothingEnabled = false

    for (const layer of layers) {
      for (let i = 0; i < layer.data.length; i++) {
        const gid = layer.data[i]
        if (gid <= 0) continue
        const col = i % layer.width
        const row = Math.floor(i / layer.width)
        const ts = getTilesetForGid(gid, tilesets)
        if (!ts) continue

        const srcTexture = this.scene.textures.get(ts.imageSource)
        const imgEl = srcTexture?.getSourceImage() as HTMLImageElement | undefined
        if (!imgEl || !imgEl.naturalWidth) {
          ctx.fillStyle = 'rgba(180,0,180,0.5)'
          ctx.fillRect(col * TILE_SIZE, row * TILE_SIZE, TILE_SIZE, TILE_SIZE)
          continue
        }

        const { sx, sy, sw, sh } = getGidRect(gid, ts)
        ctx.drawImage(imgEl, sx, sy, sw, sh, col * TILE_SIZE, row * TILE_SIZE, TILE_SIZE, TILE_SIZE)
      }
    }

    this.scene.textures.addCanvas('tiled_bg', offscreen)
    this.scene.add.image(0, 0, 'tiled_bg').setOrigin(0, 0).setDepth(0)
  }

  private renderFallbackTiles() {
    const FALLBACK_COLORS: Record<string, number> = {
      grass:          0x4a7c59,
      wall:           0x555566,
      floor:          0xc8a97a,
      floor_occupied: 0xa07850,
    }
    const g = this.scene.add.graphics().setDepth(0)
    for (const tile of this.tiles) {
      const { x, y } = tileToPixel(tile.x, tile.y)
      const color = FALLBACK_COLORS[tile.type] ?? 0x888888
      g.fillStyle(color, 1)
      g.fillRect(x, y, TILE_SIZE - 1, TILE_SIZE - 1)
    }
  }
}
