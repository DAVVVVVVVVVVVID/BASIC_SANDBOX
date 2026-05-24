import Phaser from 'phaser'
import { Position, Facing, Tile } from '../../types'
import { pixelToTile } from '../map/TileMap'
import { sendAction } from '../../api/world'
import { useGameStore } from '../../store/gameStore'

export interface MoveResult {
  success: boolean
  facing: Facing
  position?: Position
}

type OnMoveResultCallback = (result: MoveResult) => void
type OnInteractCallback   = () => void
type OnUseCallback        = () => void
type OnLeaveCallback      = () => void

export type Direction = 'up' | 'down' | 'left' | 'right'

const DIR_LABEL: Record<Direction, string> = {
  up:    '上',
  down:  '下',
  left:  '左',
  right: '右',
}

export const DELTAS: Record<Direction, Position> = {
  up:    { x:  0, y: -1 },
  down:  { x:  0, y:  1 },
  left:  { x: -1, y:  0 },
  right: { x:  1, y:  0 },
}

export function bfs(tiles: Tile[], start: Position, end: Position): Direction[] {
  const walkable = new Set(tiles.filter(t => t.walkable).map(t => `${t.x},${t.y}`))
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

const BASE_MOVE_INTERVAL = 300  // ms，基准移动间隔

export function getMoveInterval(): number {
  const speed = useGameStore.getState().player?.moveSpeed ?? 1.0
  return BASE_MOVE_INTERVAL / Math.max(0.1, speed)
}

export default class InputSystem {
  private cursors: Phaser.Types.Input.Keyboard.CursorKeys
  private interactKey: Phaser.Input.Keyboard.Key
  private useKey: Phaser.Input.Keyboard.Key
  private leaveKey: Phaser.Input.Keyboard.Key
  private ctrlKey: Phaser.Input.Keyboard.Key
  private isMoving = false
  private pathQueue: Direction[] = []
  private currentPos: Position
  private lastMoveTime = 0
  // 鼠标路径：目的地和首步标记
  private pathDestination: Position | null = null
  private isFirstPathStep = false

  constructor(
    private scene: Phaser.Scene,
    private playerId: string,
    private tiles: Tile[],
    initialPos: Position,
    private onMoveResult: OnMoveResultCallback,
    private onInteract?: OnInteractCallback,
    private onUse?: OnUseCallback,
    private onLeave?: OnLeaveCallback,
  ) {
    this.currentPos  = { ...initialPos }
    this.cursors     = scene.input.keyboard!.createCursorKeys()
    this.interactKey = scene.input.keyboard!.addKey(Phaser.Input.Keyboard.KeyCodes.I)
    this.useKey      = scene.input.keyboard!.addKey(Phaser.Input.Keyboard.KeyCodes.E)
    this.leaveKey    = scene.input.keyboard!.addKey(Phaser.Input.Keyboard.KeyCodes.Q)
    this.ctrlKey     = scene.input.keyboard!.addKey(Phaser.Input.Keyboard.KeyCodes.CTRL)
    this.setupMouseInput()
  }

  private async sendMove(
    params: { direction?: string; targetTile?: Position },
    logOptions: { skipLog?: boolean; logLabel?: string } = {},
  ) {
    if (this.isMoving) return
    this.isMoving = true
    this.lastMoveTime = Date.now()
    try {
      const res = await sendAction(
        this.playerId,
        'move',
        params as Record<string, unknown>,
        logOptions,
      )
      const result: MoveResult = {
        success:  res.success,
        facing:   res.result?.facing,
        position: res.success ? res.result?.position : undefined,
      }
      if (res.success && res.result?.position) {
        this.currentPos = res.result.position
      }
      this.onMoveResult(result)
    } catch (err) {
      console.error('[Move Error]', err)
      this.pathQueue = []
    } finally {
      this.isMoving = false
    }
  }

  private async executePathStep() {
    if (this.pathQueue.length === 0 || this.isMoving) return
    const direction = this.pathQueue.shift()!

    let logOptions: { skipLog?: boolean; logLabel?: string }
    if (this.isFirstPathStep && this.pathDestination) {
      logOptions = { logLabel: `点击前往 (${this.pathDestination.x}, ${this.pathDestination.y})` }
      this.isFirstPathStep = false
    } else {
      logOptions = { skipLog: true }
    }

    await this.sendMove({ direction }, logOptions)
    if (this.pathQueue.length > 0) {
      this.scene.time.delayedCall(getMoveInterval(), () => this.executePathStep())
    }
  }

  private setupMouseInput() {
    this.scene.input.on('pointerdown', (pointer: Phaser.Input.Pointer) => {
      if (pointer.rightButtonDown()) return
      const tile = pixelToTile(pointer.worldX, pointer.worldY)
      if (!tile) return

      this.pathQueue = bfs(this.tiles, this.currentPos, tile)
      if (this.pathQueue.length === 0) return

      this.pathDestination = tile
      this.isFirstPathStep = true

      const elapsed = Date.now() - this.lastMoveTime
      const delay = Math.max(0, getMoveInterval() - elapsed)
      if (delay > 0) {
        this.scene.time.delayedCall(delay, () => this.executePathStep())
      } else {
        this.executePathStep()
      }
    })
  }

  syncFromServer(pos: Position) {
    if (pos.x !== this.currentPos.x || pos.y !== this.currentPos.y) {
      this.currentPos = { ...pos }
      this.pathQueue = []
    }
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
        if (Phaser.Input.Keyboard.JustDown(dirKey)) {
          sendAction(
            this.playerId,
            'turn',
            { direction: heldDir },
            { logLabel: `转向${DIR_LABEL[heldDir]}` },
          ).then(res => {
            this.onMoveResult({ success: false, facing: res.result?.facing })
          }).catch(err => console.error('[Turn Error]', err))
        }
      } else {
        const elapsed = Date.now() - this.lastMoveTime
        if (!this.isMoving && elapsed >= getMoveInterval()) {
          this.sendMove(
            { direction: heldDir },
            { logLabel: `向${DIR_LABEL[heldDir]}移动` },
          )
        }
      }
    }

    if (Phaser.Input.Keyboard.JustDown(this.interactKey)) {
      this.onInteract?.()
    }

    if (Phaser.Input.Keyboard.JustDown(this.useKey)) {
      this.onUse?.()
    }

    if (Phaser.Input.Keyboard.JustDown(this.leaveKey)) {
      this.onLeave?.()
    }
  }
}
