import Phaser from 'phaser'
import { GameObject } from '../../types'
import { tileToPixel, TILE_SIZE } from '../map/TileMap'

const COLOR_OBJECT = 0xf6ad55

export default class GameObjectSprite {
  constructor(scene: Phaser.Scene, obj: GameObject) {
    const footprint = obj.tiles ?? [obj.position]
    const size = Math.max(TILE_SIZE - 2, 2)

    // 计算 footprint 包围盒
    const xs = footprint.map(p => p.x)
    const ys = footprint.map(p => p.y)
    const minX = Math.min(...xs)
    const minY = Math.min(...ys)
    const maxX = Math.max(...xs)
    const maxY = Math.max(...ys)
    const cols  = maxX - minX + 1
    const rows  = maxY - minY + 1

    const spriteKey = obj.sprite ? `obj_${obj.sprite}` : null

    if (spriteKey && scene.textures.exists(spriteKey)) {
      // 用一张图覆盖整个 footprint
      const { x: px, y: py } = tileToPixel(minX, minY)
      const imgW = cols * TILE_SIZE
      const imgH = rows * TILE_SIZE
      const img = scene.add
        .image(px + imgW / 2, py + imgH / 2, spriteKey)
        .setDisplaySize(imgW, imgH)
        .setDepth(1)
        .setInteractive()

      const tooltip = scene.add
        .text(px + imgW / 2, py - 2, obj.name, {
          fontSize: '10px',
          color: '#ffffff',
          backgroundColor: '#1a1a2e',
          padding: { x: 4, y: 2 },
        })
        .setOrigin(0.5, 1)
        .setDepth(10)
        .setVisible(false)

      img.on('pointerover', () => tooltip.setVisible(true))
      img.on('pointerout',  () => tooltip.setVisible(false))
    } else {
      // 无 sprite：每格画一个色块，tooltip 挂第一格
      footprint.forEach((pos, index) => {
        const { x, y } = tileToPixel(pos.x, pos.y)
        const cx = x + TILE_SIZE / 2
        const cy = y + TILE_SIZE / 2

        const rect = scene.add.rectangle(cx, cy, size, size, COLOR_OBJECT)
        rect.setDepth(1)
        rect.setInteractive()

        if (index === 0) {
          const tooltip = scene.add
            .text(cx, y - 2, obj.name, {
              fontSize: '10px',
              color: '#ffffff',
              backgroundColor: '#1a1a2e',
              padding: { x: 4, y: 2 },
            })
            .setOrigin(0.5, 1)
            .setDepth(10)
            .setVisible(false)

          rect.on('pointerover', () => tooltip.setVisible(true))
          rect.on('pointerout',  () => tooltip.setVisible(false))
        }
      })
    }
  }
}
