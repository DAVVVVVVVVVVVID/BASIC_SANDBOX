import Phaser from 'phaser'
import { Position, Facing } from '../../types'
import { tileToPixel, TILE_SIZE } from '../map/TileMap'

const SCALE = 4
const ARROW_OFFSET = 30

const FACING_OFFSET: Record<Facing, [number, number]> = {
  right: [ ARROW_OFFSET,          0],
  left:  [-ARROW_OFFSET,          0],
  down:  [           0, ARROW_OFFSET],
  up:    [           0,-ARROW_OFFSET],
}

const ARROW_TRI: Record<Facing, [number, number, number, number, number, number]> = {
  right: [ 8,  0, -5, -5, -5,  5],
  left:  [-8,  0,  5, -5,  5,  5],
  down:  [ 0,  8, -5, -5,  5, -5],
  up:    [ 0, -8, -5,  5,  5,  5],
}

export default class OtherPlayerSprite {
  private scene: Phaser.Scene
  private sprite: Phaser.GameObjects.Sprite
  private arrow: Phaser.GameObjects.Graphics
  private label: Phaser.GameObjects.Text
  private facing: Facing
  private idleTimer: Phaser.Time.TimerEvent | null = null

  constructor(scene: Phaser.Scene, position: Position, facing: Facing, name: string) {
    this.scene  = scene
    this.facing = facing

    const { x, y } = tileToPixel(position.x, position.y)
    const cx = x + TILE_SIZE / 2
    const cy = y + TILE_SIZE / 2

    this.sprite = scene.add.sprite(cx, cy, 'player_idle')
    this.sprite.setScale(SCALE)
    this.sprite.setOrigin(0.5, 0.5)
    this.sprite.setDepth(cy)
    this.sprite.play('idle')

    this.arrow = scene.add.graphics()
    this.arrow.setDepth(cy + 1)
    this.drawArrow(cx, cy, facing)

    this.label = scene.add.text(cx, cy - 40, name, {
      fontSize: '12px', color: '#ffffff',
      stroke: '#000000', strokeThickness: 3,
    }).setOrigin(0.5, 1).setDepth(cy + 2)
  }

  private drawArrow(cx: number, cy: number, facing: Facing) {
    const [ox, oy] = FACING_OFFSET[facing]
    const ax = cx + ox
    const ay = cy + oy
    const [x1, y1, x2, y2, x3, y3] = ARROW_TRI[facing]
    this.arrow.clear()
    this.arrow.fillStyle(0xffffff, 1)
    this.arrow.lineStyle(1.5, 0x333333, 1)
    this.arrow.fillTriangle(ax + x1, ay + y1, ax + x2, ay + y2, ax + x3, ay + y3)
    this.arrow.strokeTriangle(ax + x1, ay + y1, ax + x2, ay + y2, ax + x3, ay + y3)
  }

  updatePosition(position: Position, facing: Facing) {
    const { x, y } = tileToPixel(position.x, position.y)
    const cx = x + TILE_SIZE / 2
    const cy = y + TILE_SIZE / 2

    const moved = cx !== this.sprite.x || cy !== this.sprite.y
    this.facing = facing

    this.sprite.setPosition(cx, cy)
    this.sprite.setFlipX(facing === 'left')
    this.sprite.setDepth(cy)
    this.drawArrow(cx, cy, facing)
    this.arrow.setDepth(cy + 1)
    this.label.setPosition(cx, cy - 40)
    this.label.setDepth(cy + 2)

    if (moved) {
      if (this.idleTimer) { this.idleTimer.destroy(); this.idleTimer = null }
      this.sprite.play('walk', true)
      this.idleTimer = this.scene.time.delayedCall(600, () => {
        this.sprite.play('idle')
        this.idleTimer = null
      })
    }
  }

  destroy() {
    if (this.idleTimer) { this.idleTimer.destroy() }
    this.sprite.destroy()
    this.arrow.destroy()
    this.label.destroy()
  }
}
