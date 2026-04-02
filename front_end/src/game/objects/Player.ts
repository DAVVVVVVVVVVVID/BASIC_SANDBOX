import Phaser from 'phaser'
import { Position, Facing } from '../../types'
import { tileToPixel, TILE_SIZE } from '../map/TileMap'

const COLOR_BODY   = 0x63b3ed
const COLOR_BORDER = 0x2b6cb0
const COLOR_NOSE   = 0xffffff

const FACING_OFFSET: Record<Facing, [number, number]> = {
  up:    [ 0, -1],
  down:  [ 0,  1],
  left:  [-1,  0],
  right: [ 1,  0],
}

export default class PlayerSprite {
  private graphics: Phaser.GameObjects.Graphics
  private position: Position
  private facing: Facing

  constructor(scene: Phaser.Scene, position: Position, facing: Facing = 'down') {
    this.graphics = scene.add.graphics()
    this.graphics.setDepth(2)
    this.position = { ...position }
    this.facing = facing
    this.redraw()
  }

  private redraw() {
    const { x, y } = tileToPixel(this.position.x, this.position.y)
    const cx = x + TILE_SIZE / 2
    const cy = y + TILE_SIZE / 2
    const r  = Math.max(Math.floor(TILE_SIZE / 2) - 1, 2)

    this.graphics.clear()

    this.graphics.fillStyle(COLOR_BODY, 1)
    this.graphics.fillCircle(cx, cy, r)
    this.graphics.lineStyle(1, COLOR_BORDER, 1)
    this.graphics.strokeCircle(cx, cy, r)

    // 朝向指示点
    const [dx, dy] = FACING_OFFSET[this.facing]
    const dotR = Math.max(1, Math.floor(r / 3))
    this.graphics.fillStyle(COLOR_NOSE, 1)
    this.graphics.fillCircle(cx + dx * (r - dotR - 1), cy + dy * (r - dotR - 1), dotR)
  }

  moveTo(position: Position) {
    this.position = { ...position }
    this.redraw()
  }

  setFacing(facing: Facing) {
    this.facing = facing
    this.redraw()
  }

  moveToWithFacing(position: Position, facing: Facing) {
    this.position = { ...position }
    this.facing   = facing
    this.redraw()
  }
}
