import Phaser from 'phaser'
import { Position, Facing } from '../../types'
import { tileToPixel, TILE_SIZE } from '../map/TileMap'

const COLOR_BODY   = 0xe8a030
const COLOR_BORDER = 0xb07020
const COLOR_NOSE   = 0xffffff

const FACING_OFFSET: Record<Facing, [number, number]> = {
  up:    [ 0, -1],
  down:  [ 0,  1],
  left:  [-1,  0],
  right: [ 1,  0],
}

export default class OtherPlayerSprite {
  private container: Phaser.GameObjects.Container
  private graphics: Phaser.GameObjects.Graphics
  private label: Phaser.GameObjects.Text
  private facing: Facing

  constructor(scene: Phaser.Scene, position: Position, facing: Facing, name: string) {
    this.facing   = facing
    this.graphics = scene.add.graphics()
    this.label    = scene.add.text(0, 0, name, {
      fontSize: '11px', color: '#ffffff',
      stroke: '#000000', strokeThickness: 3,
    }).setOrigin(0.5, 1)

    const { x, y } = tileToPixel(position.x, position.y)
    this.container = scene.add.container(x + TILE_SIZE / 2, y + TILE_SIZE / 2, [this.graphics, this.label])
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

    this.label.setPosition(0, -r - 2)
  }

  updatePosition(position: Position, facing: Facing) {
    const { x, y } = tileToPixel(position.x, position.y)
    this.container.x = x + TILE_SIZE / 2
    this.container.y = y + TILE_SIZE / 2
    if (facing !== this.facing) {
      this.facing = facing
      this.redraw()
    }
  }

  destroy() {
    this.container.destroy()
  }
}
