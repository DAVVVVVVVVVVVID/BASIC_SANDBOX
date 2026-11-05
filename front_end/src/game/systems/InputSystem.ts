import Phaser from 'phaser'
import { Position, Facing, Tile } from '../../types'
import { pixelToTile } from '../map/TileMap'
import { sendAction } from '../../api/world'
import { useGameStore } from '../../store/gameStore'

export type Direction = 'up' | 'down' | 'left' | 'right'

const DIR_LABEL: Record<Direction, string> = { up: '上', down: '下', left: '左', right: '右' }

export const DELTAS: Record<Direction, Position> = {
  up:    { x:  0, y: -1 },
  down:  { x:  0, y:  1 },
  left:  { x: -1, y:  0 },
  right: { x:  1, y:  0 },
}

export function bfs(tiles: Tile[], start: Position, end: Position, maxLen = 400): Direction[] {
  const walkable = new Set<string>()
  for (const t of tiles) if (t.walkable) walkable.add(`${t.x},${t.y}`)
  if (!walkable.has(`${end.x},${end.y}`)) return []
  if (start.x === end.x && start.y === end.y) return []

  const queue: { pos: Position; path: Direction[] }[] = [{ pos: start, path: [] }]
  const visited = new Set([`${start.x},${start.y}`])
  let head = 0
  while (head < queue.length) {
    const { pos, path } = queue[head++]
    if (path.length > maxLen) break
    for (const [dir, delta] of Object.entries(DELTAS) as [Direction, Position][]) {
      const nx = pos.x + delta.x, ny = pos.y + delta.y
      const key = `${nx},${ny}`
      if (!walkable.has(key) || visited.has(key)) continue
      visited.add(key)
      const np = [...path, dir]
      if (nx === end.x && ny === end.y) return np
      queue.push({ pos: { x: nx, y: ny }, path: np })
    }
  }
  return []
}

export const BASE_MOVE_INTERVAL = 300  // ms，基准移动间隔（一格）

export function getMoveInterval(): number {
  const speed = useGameStore.getState().player?.moveSpeed ?? 1.0
  return BASE_MOVE_INTERVAL / Math.max(0.1, speed)
}

/** 同时在途的 move 请求上限：按键节奏 300 ms/格、往返 < 100 ms 时通常只有 1 个 */
const MAX_INFLIGHT = 3

interface Inflight {
  dir: Direction
  from: Position     // 发出时的预测位置
  to: Position       // 预测目标
  sentAt: number
}

export interface InputCallbacks {
  /** 本地预测：立刻走向 target（带朝向） */
  onPredictStep: (target: Position, facing: Facing) => void
  /** 只改朝向（撞墙 / Ctrl 转向） */
  onFacing: (facing: Facing) => void
  /** 与服务器对齐：actor 应当最终站在 pos。bounced=true 表示被拒回弹 */
  onReconcile: (pos: Position, bounced: boolean) => void
  onInteract?: () => void
  onUse?: () => void
  onLeave?: () => void
}

/**
 * 客户端预测 + 服务器校正。
 *  - serverPos：最后一次服务器确认的位置
 *  - inflight：已发出未回包的 move；predicted = serverPos + Σ inflight 位移
 *  - 回包成功：serverPos = result.position；失败：丢掉该步 → predicted 回退（回弹）
 *  - 轮询到的服务器位置只在没有在途请求、且该轮询晚于最后一次回包时才用于校正
 * 前端不判定合法性：所有 move 都照发，本地只是「先动起来」；是否可走由后端回包决定（CLAUDE.md 后端权限）。
 */
export default class InputSystem {
  private cursors: Phaser.Types.Input.Keyboard.CursorKeys
  private wasd: Record<Direction, Phaser.Input.Keyboard.Key>
  private interactKey: Phaser.Input.Keyboard.Key
  private useKey: Phaser.Input.Keyboard.Key
  private leaveKey: Phaser.Input.Keyboard.Key
  private ctrlKey: Phaser.Input.Keyboard.Key

  private serverPos: Position
  private facing: Facing
  private inflight: Inflight[] = []
  private lastAckAt = 0
  private nextStepAt = 0
  private walkable = new Set<string>()

  // 鼠标路径
  private pathQueue: Direction[] = []
  private pathDestination: Position | null = null
  private isFirstPathStep = false

  private enabled = true
  private destroyed = false

  constructor(
    private scene: Phaser.Scene,
    private playerId: string,
    tiles: Tile[],
    initialPos: Position,
    initialFacing: Facing,
    private cb: InputCallbacks,
  ) {
    this.serverPos = { ...initialPos }
    this.facing = initialFacing
    this.setTiles(tiles)
    const kb = scene.input.keyboard!
    this.cursors     = kb.createCursorKeys()
    this.wasd = {
      up:    kb.addKey(Phaser.Input.Keyboard.KeyCodes.W),
      down:  kb.addKey(Phaser.Input.Keyboard.KeyCodes.S),
      left:  kb.addKey(Phaser.Input.Keyboard.KeyCodes.A),
      right: kb.addKey(Phaser.Input.Keyboard.KeyCodes.D),
    }
    this.interactKey = kb.addKey(Phaser.Input.Keyboard.KeyCodes.I)
    this.useKey      = kb.addKey(Phaser.Input.Keyboard.KeyCodes.E)
    this.leaveKey    = kb.addKey(Phaser.Input.Keyboard.KeyCodes.Q)
    this.ctrlKey     = kb.addKey(Phaser.Input.Keyboard.KeyCodes.CTRL)
    this.setupMouseInput()
  }

  setPlayerId(id: string) { this.playerId = id }
  setEnabled(v: boolean) { this.enabled = v }
  setTiles(tiles: Tile[]) {
    this.walkable.clear()
    for (const t of tiles) if (t.walkable) this.walkable.add(`${t.x},${t.y}`)
  }

  predicted(): Position {
    let x = this.serverPos.x, y = this.serverPos.y
    for (const f of this.inflight) { x += DELTAS[f.dir].x; y += DELTAS[f.dir].y }
    return { x, y }
  }
  getServerPos(): Position { return { ...this.serverPos } }
  hasInflight() { return this.inflight.length > 0 }

  /**
   * 轮询 /player 得到的位置。sentAt = 该请求发出的时刻（performance.now）。
   * 有在途请求或该轮询早于最后一次回包时忽略（它反映的是旧状态）。
   */
  applyServerSnapshot(pos: Position, facing: Facing, sentAt: number) {
    if (this.inflight.length > 0) return
    if (sentAt < this.lastAckAt) return
    if (pos.x !== this.serverPos.x || pos.y !== this.serverPos.y) {
      this.serverPos = { ...pos }
      this.pathQueue = []
      this.cb.onReconcile(this.serverPos, false)
    }
    if (facing !== this.facing) {
      this.facing = facing
      this.cb.onFacing(facing)
    }
  }

  // ── 步进 ─────────────────────────────────────────────────────────────────────

  private step(dir: Direction, logOptions: { skipLog?: boolean; logLabel?: string }) {
    if (!this.enabled) return
    if (this.inflight.length >= MAX_INFLIGHT) return
    const from = this.predicted()
    const to = { x: from.x + DELTAS[dir].x, y: from.y + DELTAS[dir].y }
    const entry: Inflight = { dir, from, to, sentAt: performance.now() }
    this.facing = dir

    // 本地只「先动起来」；格子在地图数据里不可走时不预测位移，只转身，等后端裁定
    const locallyWalkable = this.walkable.has(`${to.x},${to.y}`)
    if (locallyWalkable) {
      this.inflight.push(entry)
      this.cb.onPredictStep(to, dir)
    } else {
      this.cb.onFacing(dir)
    }

    sendAction(this.playerId, 'move', { direction: dir }, logOptions)
      .then(res => {
        if (this.destroyed) return
        this.lastAckAt = performance.now()
        const idx = this.inflight.indexOf(entry)
        if (idx >= 0) this.inflight.splice(idx, 1)
        const f = res.result?.facing
        if (res.success && res.result?.position) {
          this.serverPos = { ...res.result.position }
          // 让场景对齐到 serverPos + 剩余在途位移；与当前路径终点一致时场景会忽略
          this.cb.onReconcile(this.predicted(), false)
        } else {
          // 被拒：该步作废 → 回弹到 serverPos + 剩余在途位移
          this.pathQueue = []
          if (idx >= 0) this.cb.onReconcile(this.predicted(), true)
          if (f) { this.facing = f; this.cb.onFacing(f) }
        }
      })
      .catch(err => {
        if (this.destroyed) return
        console.error('[Move Error]', err)
        const idx = this.inflight.indexOf(entry)
        if (idx >= 0) this.inflight.splice(idx, 1)
        this.pathQueue = []
        this.cb.onReconcile(this.predicted(), true)
      })
  }

  private setupMouseInput() {
    this.scene.input.on('pointerdown', (pointer: Phaser.Input.Pointer) => {
      if (!this.enabled || pointer.rightButtonDown()) return
      const tile = pixelToTile(pointer.worldX, pointer.worldY)
      if (!tile) return
      const tiles = useGameStore.getState().tiles
      const path = bfs(tiles, this.predicted(), tile)
      if (path.length === 0) return
      this.pathQueue = path
      this.pathDestination = tile
      this.isFirstPathStep = true
    })
  }

  update(now: number) {
    if (!this.enabled) return
    const { up, down, left, right } = this.cursors
    const heldDir: Direction | null =
      (up.isDown || this.wasd.up.isDown)       ? 'up'    :
      (down.isDown || this.wasd.down.isDown)   ? 'down'  :
      (left.isDown || this.wasd.left.isDown)   ? 'left'  :
      (right.isDown || this.wasd.right.isDown) ? 'right' : null

    const interval = getMoveInterval()

    if (heldDir) {
      this.pathQueue = []
      if (this.ctrlKey.isDown) {
        const dirKey = this.cursors[heldDir]
        const wKey = this.wasd[heldDir]
        if (Phaser.Input.Keyboard.JustDown(dirKey) || Phaser.Input.Keyboard.JustDown(wKey)) {
          this.facing = heldDir
          this.cb.onFacing(heldDir)
          sendAction(this.playerId, 'turn', { direction: heldDir }, { logLabel: `转向${DIR_LABEL[heldDir]}` })
            .then(res => { if (res.result?.facing) this.cb.onFacing(res.result.facing) })
            .catch(err => console.error('[Turn Error]', err))
        }
      } else if (now >= this.nextStepAt) {
        // 长按连走：每 interval 一步，不等回包
        this.nextStepAt = now + interval
        this.step(heldDir, { logLabel: `向${DIR_LABEL[heldDir]}移动` })
      }
    } else if (this.pathQueue.length > 0 && now >= this.nextStepAt) {
      this.nextStepAt = now + interval
      const dir = this.pathQueue.shift()!
      let logOptions: { skipLog?: boolean; logLabel?: string }
      if (this.isFirstPathStep && this.pathDestination) {
        logOptions = { logLabel: `点击前往 (${this.pathDestination.x}, ${this.pathDestination.y})` }
        this.isFirstPathStep = false
      } else {
        logOptions = { skipLog: true }
      }
      this.step(dir, logOptions)
    }

    if (Phaser.Input.Keyboard.JustDown(this.interactKey)) this.cb.onInteract?.()
    if (Phaser.Input.Keyboard.JustDown(this.useKey))      this.cb.onUse?.()
    if (Phaser.Input.Keyboard.JustDown(this.leaveKey))    this.cb.onLeave?.()
  }

  destroy() {
    this.destroyed = true
    this.scene.input.off('pointerdown')
  }
}
