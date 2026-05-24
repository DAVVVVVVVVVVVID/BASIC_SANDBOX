import Phaser from 'phaser'
import { Position, Facing } from '../../types'
import { tileToPixel, TILE_SIZE } from '../map/TileMap'
import { getMoveInterval } from '../systems/InputSystem'

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
  private scene: Phaser.Scene
  private container: Phaser.GameObjects.Container
  private graphics: Phaser.GameObjects.Graphics
  private facing: Facing

  constructor(scene: Phaser.Scene, position: Position, facing: Facing = 'down') {
    this.scene   = scene
    this.facing  = facing

    const { x, y } = tileToPixel(position.x, position.y)
    this.graphics  = scene.add.graphics()
    this.container = scene.add.container(x + TILE_SIZE / 2, y + TILE_SIZE / 2, [this.graphics])
    this.container.setDepth(2)
    this.redraw()
  }

  private redraw() {
    const r    = Math.max(Math.floor(TILE_SIZE / 2) - 1, 2)
    const dotR = Math.max(1, Math.floor(r / 3))
    const [dx, dy] = FACING_OFFSET[this.facing]

    this.graphics.clear()
    this.graphics.fillStyle(COLOR_BODY, 1)
    this.graphics.fillCircle(0, 0, r)
    this.graphics.lineStyle(1, COLOR_BORDER, 1)
    this.graphics.strokeCircle(0, 0, r)
    this.graphics.fillStyle(COLOR_NOSE, 1)
    this.graphics.fillCircle(dx * (r - dotR - 1), dy * (r - dotR - 1), dotR)
  }

  moveTo(position: Position) {
    const { x, y } = tileToPixel(position.x, position.y)
    this.scene.tweens.add({
      targets:  this.container,
      x:        x + TILE_SIZE / 2,
      y:        y + TILE_SIZE / 2,
      duration: getMoveInterval(),
      ease:     'Linear',
    })
  }

  setFacing(facing: Facing) {
    this.facing = facing
    this.redraw()
  }

  moveToWithFacing(position: Position, facing: Facing) {
    this.facing = facing
    this.redraw()
    this.moveTo(position)
  }

  getPixelPosition(): { x: number; y: number } {
    return { x: this.container.x, y: this.container.y }
  }
}
