import Phaser from 'phaser'
import { Position, Facing } from '../../types'
import { tileToPixel, TILE_SIZE } from '../map/TileMap'
import { getMoveInterval } from '../systems/InputSystem'

const SCALE = 4
const ARROW_OFFSET = 30  // 角色中心到箭头中心的距离（像素）

const FACING_OFFSET: Record<Facing, [number, number]> = {
  right: [ ARROW_OFFSET,           0],
  left:  [-ARROW_OFFSET,           0],
  down:  [          0,  ARROW_OFFSET],
  up:    [          0, -ARROW_OFFSET],
}

// 相对于箭头中心的三角形顶点
const ARROW_TRI: Record<Facing, [number, number, number, number, number, number]> = {
  right: [ 8,  0, -5, -5, -5,  5],
  left:  [-8,  0,  5, -5,  5,  5],
  down:  [ 0,  8, -5, -5,  5, -5],
  up:    [ 0, -8, -5,  5,  5,  5],
}

export default class PlayerSprite {
  private scene: Phaser.Scene
  private sprite: Phaser.GameObjects.Sprite
  private arrow: Phaser.GameObjects.Graphics
  private facing: Facing
  private idleTimer: Phaser.Time.TimerEvent | null = null

  constructor(scene: Phaser.Scene, position: Position, facing: Facing = 'down') {
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
    this._redrawArrow()
  }

  private _redrawArrow() {
    const cx = this.sprite.x
    const cy = this.sprite.y
    const [ox, oy] = FACING_OFFSET[this.facing]
    const ax = cx + ox
    const ay = cy + oy
    const [x1, y1, x2, y2, x3, y3] = ARROW_TRI[this.facing]

    this.arrow.clear()
    this.arrow.fillStyle(0xffffff, 1)
    this.arrow.lineStyle(1.5, 0x333333, 1)
    this.arrow.fillTriangle(ax + x1, ay + y1, ax + x2, ay + y2, ax + x3, ay + y3)
    this.arrow.strokeTriangle(ax + x1, ay + y1, ax + x2, ay + y2, ax + x3, ay + y3)
  }

  private cancelIdleTimer() {
    if (this.idleTimer) { this.idleTimer.destroy(); this.idleTimer = null }
  }

  private scheduleIdle() {
    this.cancelIdleTimer()
    this.idleTimer = this.scene.time.delayedCall(100, () => {
      this.sprite.play('idle')
      this.idleTimer = null
    })
  }

  moveTo(position: Position) {
    const { x, y } = tileToPixel(position.x, position.y)
    const cx = x + TILE_SIZE / 2
    const cy = y + TILE_SIZE / 2
    this.scene.tweens.add({
      targets:  this.sprite,
      x: cx, y: cy,
      duration: getMoveInterval(),
      ease: 'Linear',
      onComplete: () => this.scheduleIdle(),
    })
  }

  setFacing(facing: Facing) {
    this.facing = facing
    this.sprite.setFlipX(facing === 'left')
    this._redrawArrow()
  }

  moveToWithFacing(position: Position, facing: Facing) {
    this.cancelIdleTimer()
    this.facing = facing
    this.sprite.setFlipX(facing === 'left')
    this.sprite.play('walk', true)
    this.moveTo(position)
  }

  // 每帧由 GameScene.update() 调用
  updateDepth() {
    const d = this.sprite.y
    this.sprite.setDepth(d)
    this.arrow.setDepth(d + 1)
    this._redrawArrow()
  }

  getPixelPosition(): { x: number; y: number } {
    return { x: this.sprite.x, y: this.sprite.y }
  }
}
