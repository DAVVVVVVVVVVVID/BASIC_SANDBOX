import Phaser from 'phaser'
import { Tile, Position } from '../../types'

export const TILE_SIZE = 32

// ── TileType 定义表（前端）────────────────────────────────────────────────────
// sprite: Phaser 预加载的 key，null 表示用纯色兜底
interface TileTypeDef {
  sprite: string | null
  fallbackColor: number
}

export const TILE_TYPE_DEFS: Record<string, TileTypeDef> = {
  grass:          { sprite: 'tile_grass',  fallbackColor: 0x4a7c59 },
  wall:           { sprite: 'tile_wall',   fallbackColor: 0x5c3d2e },
  floor:          { sprite: 'tile_floor',  fallbackColor: 0xc8a96e },
  floor_occupied: { sprite: 'tile_floor',  fallbackColor: 0x9e7c4a },
}

// 未知类型的兜底
const TILE_TYPE_UNKNOWN: TileTypeDef = { sprite: null, fallbackColor: 0x888888 }

// ── 坐标转换 ──────────────────────────────────────────────────────────────────

export function tileToPixel(tileX: number, tileY: number) {
  return {
    x: tileX * TILE_SIZE,
    y: tileY * TILE_SIZE,
  }
}

export function pixelToTile(pixelX: number, pixelY: number): Position | null {
  const tileX = Math.floor(pixelX / TILE_SIZE)
  const tileY = Math.floor(pixelY / TILE_SIZE)
  if (tileX < 0 || tileY < 0) return null
  return { x: tileX, y: tileY }
}

// ── 预加载辅助（在 GameScene.preload 里调用）─────────────────────────────────

export function preloadTileAssets(scene: Phaser.Scene) {
  for (const [, def] of Object.entries(TILE_TYPE_DEFS)) {
    if (def.sprite) {
      scene.load.image(def.sprite, `assets/tiles/${def.sprite.replace('tile_', '')}.png`)
    }
  }
}

// ── TileMap 渲染 ──────────────────────────────────────────────────────────────

export default class TileMap {
  constructor(private scene: Phaser.Scene, private tiles: Tile[]) {}

  render() {
    const fallbackGraphics = this.scene.add.graphics().setDepth(0)

    for (const tile of this.tiles) {
      const { x, y } = tileToPixel(tile.x, tile.y)
      const def = TILE_TYPE_DEFS[tile.type] ?? TILE_TYPE_UNKNOWN

      if (def.sprite && this.scene.textures.exists(def.sprite)) {
        this.scene.add
          .image(x + TILE_SIZE / 2, y + TILE_SIZE / 2, def.sprite)
          .setDisplaySize(TILE_SIZE, TILE_SIZE)
          .setDepth(0)
      } else {
        fallbackGraphics.fillStyle(def.fallbackColor, 1)
        fallbackGraphics.fillRect(x, y, TILE_SIZE - 1, TILE_SIZE - 1)
      }
    }
  }
}
