import Phaser from 'phaser'
import { Position, Facing, Tile } from '../../types'
import { pixelToTile } from '../map/TileMap'
import { movePlayer, turnPlayer } from '../../api/world'

export interface MoveResult {
  success: boolean
  facing: Facing
  position?: Position
}

type OnMoveResultCallback = (result: MoveResult) => void
type OnInteractCallback   = () => void

type Direction = 'up' | 'down' | 'left' | 'right'

const DELTAS: Record<Direction, Position> = {
  up:    { x:  0, y: -1 },
  down:  { x:  0, y:  1 },
  left:  { x: -1, y:  0 },
  right: { x:  1, y:  0 },
}

function bfs(tiles: Tile[], start: Position, end: Position): Direction[] {
  const walkable = new Set(tiles.filter(t => t.walkable).map(t => `${t.x},${t.y}`))
  // 终点必须可行走
  if (!walkable.has(`${end.x},${end.y}`)) return []

  const queue: { pos: Position; path: Direction[] }[] = [{ pos: start, path: [] }]
  const visited = new Set([`${start.x},${start.y}`])

  while (queue.length > 0) {
    const { pos, path } = queue.shift()!
    if (pos.x === end.x && pos.y === end.y) return path

    for (const [dir, delta] of Object.entries(DELTAS) as [Direction, Position][]) {
      const nx = pos.x + delta.x
      const ny = pos.y + delta.y
      const key = `${nx},${ny}`
      if (walkable.has(key) && !visited.has(key)) {
        visited.add(key)
        queue.push({ pos: { x: nx, y: ny }, path: [...path, dir] })
      }
    }
  }
  return []
}

const MOVE_INTERVAL = 300  // ms，键盘连续移动 & 鼠标路径步进统一速率

export default class InputSystem {
  private cursors: Phaser.Types.Input.Keyboard.CursorKeys
  private interactKey: Phaser.Input.Keyboard.Key
  private ctrlKey: Phaser.Input.Keyboard.Key
  private isMoving = false
  private pathQueue: Direction[] = []
  private currentPos: Position
  // 速率限制：上次移动完成的时间戳
  private lastMoveTime = 0

  constructor(
    private scene: Phaser.Scene,
    private playerId: string,
    private tiles: Tile[],
    initialPos: Position,
    private onMoveResult: OnMoveResultCallback,
    private onInteract?: OnInteractCallback,
  ) {
    this.currentPos  = { ...initialPos }
    this.cursors     = scene.input.keyboard!.createCursorKeys()
    this.interactKey = scene.input.keyboard!.addKey(Phaser.Input.Keyboard.KeyCodes.I)
    this.ctrlKey     = scene.input.keyboard!.addKey(Phaser.Input.Keyboard.KeyCodes.CTRL)
    this.setupMouseInput()
  }

  private async sendMove(params: { direction?: string; targetTile?: Position }) {
    if (this.isMoving) return
    this.isMoving = true
    try {
      const res = await movePlayer(this.playerId, params)
      const result: MoveResult = {
        success:  res.success,
        facing:   res.facing,
        position: res.success ? res.position : undefined,
      }
      if (res.success && res.position) {
        this.currentPos = res.position
      }
      this.onMoveResult(result)
    } catch (err) {
      console.error('[Move Error]', err)
      this.pathQueue = []
    } finally {
      this.isMoving = false
      this.lastMoveTime = Date.now()
    }
  }

  private async executePathStep() {
    if (this.pathQueue.length === 0 || this.isMoving) return
    const direction = this.pathQueue.shift()!
    await this.sendMove({ direction })
    if (this.pathQueue.length > 0) {
      this.scene.time.delayedCall(MOVE_INTERVAL, () => this.executePathStep())
    }
  }

  private setupMouseInput() {
    this.scene.input.on('pointerdown', (pointer: Phaser.Input.Pointer) => {
      if (pointer.rightButtonDown()) return
      const tile = pixelToTile(pointer.x, pointer.y)
      if (!tile) return

      this.pathQueue = bfs(this.tiles, this.currentPos, tile)
      if (this.pathQueue.length === 0) return

      const elapsed = Date.now() - this.lastMoveTime
      const delay = Math.max(0, MOVE_INTERVAL - elapsed)
      if (delay > 0) {
        this.scene.time.delayedCall(delay, () => this.executePathStep())
      } else {
        this.executePathStep()
      }
    })
  }

  update() {
    const { up, down, left, right } = this.cursors

    const heldDir: Direction | null =
      up.isDown    ? 'up'    :
      down.isDown  ? 'down'  :
      left.isDown  ? 'left'  :
      right.isDown ? 'right' : null

    if (heldDir) {
      this.pathQueue = []
      const ctrlDown = this.ctrlKey.isDown
      const dirKey = this.cursors[heldDir]
      if (ctrlDown) {
        // Ctrl + 方向键：只转向不移动
        if (Phaser.Input.Keyboard.JustDown(dirKey)) {
          turnPlayer(this.playerId, heldDir).then(res => {
            this.onMoveResult({ success: false, facing: res.facing })
          }).catch(err => console.error('[Turn Error]', err))
        }
      } else {
        const elapsed = Date.now() - this.lastMoveTime
        if (!this.isMoving && elapsed >= MOVE_INTERVAL) {
          this.sendMove({ direction: heldDir })
        }
      }
    }

    if (Phaser.Input.Keyboard.JustDown(this.interactKey)) {
      this.onInteract?.()
    }
  }
}
