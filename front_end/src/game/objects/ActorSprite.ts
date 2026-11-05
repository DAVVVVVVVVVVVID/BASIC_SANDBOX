import Phaser from 'phaser'
import { Position, Facing, NeedVars, NEED_KEYS } from '../../types'
import { tileCenter, TILE_SIZE } from '../map/TileMap'

const SCALE = 4
const BASE_STEP_MS = 300            // 一格基准用时（与 InputSystem 一致）
const ARROW_OFFSET = 30
const NAME_Y   = -58
const STATE_Y  = -44
const BUBBLE_Y = -82
const BAR_Y    = 34
const BAR_W    = 64
const BAR_H    = 4
const BAR_GAP  = 2
const CATCHUP_PATH = 3              // 积压超过这么多格就加速追赶

const FACING_OFFSET: Record<Facing, [number, number]> = {
  right: [ ARROW_OFFSET,  0],
  left:  [-ARROW_OFFSET,  0],
  down:  [ 0,  ARROW_OFFSET],
  up:    [ 0, -ARROW_OFFSET],
}
const ARROW_TRI: Record<Facing, [number, number, number, number, number, number]> = {
  right: [ 8,  0, -5, -5, -5,  5],
  left:  [-8,  0,  5, -5,  5,  5],
  down:  [ 0,  8, -5, -5,  5, -5],
  up:    [ 0, -8, -5,  5,  5,  5],
}

export const NEED_COLORS: Record<keyof NeedVars, number> = {
  fullness: 0xf6ad55,
  energy:   0x63b3ed,
  social:   0xb794f4,
  fun:      0x68d391,
  mood:     0xfbd38d,
}
export const NEED_LABELS: Record<keyof NeedVars, string> = {
  fullness: '饱', energy: '力', social: '社', fun: '乐', mood: '心',
}

export interface ActorOptions {
  name: string
  isSelf?: boolean
  showArrow?: boolean
}

/**
 * 场上一个人的精灵：沿路点按时间匀速移动（而不是跳格），自带名字牌、状态标签、聊天气泡、七变量小条。
 * 自己与他人共用；自己由 InputSystem 的预测驱动，他人由 /world 轮询驱动。
 */
export default class ActorSprite {
  private scene: Phaser.Scene
  private sprite: Phaser.GameObjects.Sprite
  private arrow: Phaser.GameObjects.Graphics | null = null
  private nameText: Phaser.GameObjects.Text
  private stateText: Phaser.GameObjects.Text
  private bubble: Phaser.GameObjects.Container | null = null
  private bubbleText: Phaser.GameObjects.Text | null = null
  private bubbleBg: Phaser.GameObjects.Graphics | null = null
  private bar: Phaser.GameObjects.Graphics | null = null
  private barVars: NeedVars | null = null

  private facing: Facing
  /** 逻辑上「已经到达 / 正在走向」的最后一个格 */
  private tile: Position
  private path: Position[] = []
  private moving = false
  private idleAt = 0
  private stateLabel: string | null = null
  private dimmed = false
  readonly name: string
  readonly isSelf: boolean

  constructor(scene: Phaser.Scene, position: Position, facing: Facing, opts: ActorOptions) {
    this.scene  = scene
    this.facing = facing
    this.tile   = { ...position }
    this.name   = opts.name
    this.isSelf = !!opts.isSelf

    const { x, y } = tileCenter(position.x, position.y)
    this.sprite = scene.add.sprite(x, y, 'player_idle')
      .setScale(SCALE)
      .setOrigin(0.5, 0.5)
      .setDepth(y)
    this.sprite.play('idle')
    this.sprite.setFlipX(facing === 'left')

    if (opts.showArrow) {
      this.arrow = scene.add.graphics().setDepth(y + 1)
      this.redrawArrow()
    }

    this.nameText = scene.add.text(x, y + NAME_Y, opts.name, {
      fontFamily: 'system-ui, "PingFang SC", "Microsoft YaHei", sans-serif',
      fontSize: '14px',
      color: this.isSelf ? '#ffe9a8' : '#ffffff',
      stroke: '#000000', strokeThickness: 4,
    }).setOrigin(0.5, 1).setDepth(y + 2).setResolution(2)

    this.stateText = scene.add.text(x, y + STATE_Y, '', {
      fontFamily: 'system-ui, "PingFang SC", "Microsoft YaHei", sans-serif',
      fontSize: '12px',
      color: '#c3dafe',
      stroke: '#000000', strokeThickness: 3,
    }).setOrigin(0.5, 1).setDepth(y + 2).setResolution(2).setVisible(false)
  }

  // ── 位置与移动 ───────────────────────────────────────────────────────────────

  getTile(): Position { return { ...this.tile } }
  getPixelPosition() { return { x: this.sprite.x, y: this.sprite.y } }
  getFacing() { return this.facing }
  /** 路径终点（没有路径时就是当前格） */
  getPathEnd(): Position { return this.path.length ? { ...this.path[this.path.length - 1] } : { ...this.tile } }
  isMoving() { return this.moving }

  /** 追加一个相邻路点（预测步 / 轮询差分） */
  pushWaypoint(p: Position) {
    const end = this.getPathEnd()
    if (end.x === p.x && end.y === p.y) return
    this.path.push({ ...p })
  }

  /** 用新路径替换（校正 / 回弹）：从当前像素位置平滑走到路径上 */
  setPath(points: Position[]) {
    this.path = points.map(p => ({ ...p }))
    if (this.path.length === 0) return
    // 如果第一个点就是当前格而我们正站在格中心，丢掉它
    const first = this.path[0]
    const c = tileCenter(first.x, first.y)
    if (Math.abs(c.x - this.sprite.x) < 0.5 && Math.abs(c.y - this.sprite.y) < 0.5) {
      this.tile = { ...first }
      this.path.shift()
    }
  }

  /** 直接瞬移 */
  snapTo(p: Position, facing?: Facing) {
    this.path = []
    this.tile = { ...p }
    const c = tileCenter(p.x, p.y)
    this.sprite.setPosition(c.x, c.y)
    if (facing) this.setFacing(facing)
    this.setMoving(false)
    this.layout()
  }

  setFacing(facing: Facing) {
    if (this.facing === facing) return
    this.facing = facing
    this.sprite.setFlipX(facing === 'left')
    this.redrawArrow()
  }

  private setMoving(m: boolean) {
    if (m === this.moving) return
    this.moving = m
    if (m) {
      this.sprite.play('walk', true)
    } else {
      this.sprite.play('idle', true)
    }
  }

  /** 每帧调用。speedMul = 玩家 moveSpeed（1.0 = 300 ms/格） */
  update(_time: number, dt: number, speedMul = 1) {
    if (this.path.length > 0) {
      const target = this.path[0]
      const c = tileCenter(target.x, target.y)
      // 面朝方向跟随路点
      const dx = c.x - this.sprite.x
      const dy = c.y - this.sprite.y
      if (Math.abs(dx) > Math.abs(dy)) this.setFacing(dx > 0 ? 'right' : 'left')
      else if (Math.abs(dy) > 0.5) this.setFacing(dy > 0 ? 'down' : 'up')

      const catchup = this.path.length > CATCHUP_PATH ? Math.min(4, this.path.length / CATCHUP_PATH) : 1
      const pxPerMs = (TILE_SIZE / BASE_STEP_MS) * Math.max(0.1, speedMul) * catchup
      let budget = pxPerMs * dt
      const dist = Math.hypot(dx, dy)
      if (dist <= budget) {
        this.sprite.setPosition(c.x, c.y)
        this.tile = { ...target }
        this.path.shift()
        budget -= dist
        // 余量继续走下一段，保证连续移动时速度恒定
        if (this.path.length > 0 && budget > 0) {
          const n = this.path[0]
          const nc = tileCenter(n.x, n.y)
          const ndx = nc.x - c.x, ndy = nc.y - c.y
          const nd = Math.hypot(ndx, ndy) || 1
          const step = Math.min(nd, budget)
          this.sprite.setPosition(c.x + ndx / nd * step, c.y + ndy / nd * step)
        }
      } else {
        this.sprite.setPosition(this.sprite.x + dx / dist * budget, this.sprite.y + dy / dist * budget)
      }
      this.setMoving(true)
      this.idleAt = 0
    } else if (this.moving) {
      // 短暂滞后再切 idle，避免连走时帧间抖动
      if (this.idleAt === 0) this.idleAt = _time + 90
      else if (_time >= this.idleAt) { this.setMoving(false); this.idleAt = 0 }
    }
    this.layout()
  }

  private layout() {
    const x = this.sprite.x, y = this.sprite.y
    const d = y
    this.sprite.setDepth(d)
    if (this.arrow) { this.arrow.setDepth(d + 1); this.redrawArrow() }
    this.nameText.setPosition(x, y + NAME_Y).setDepth(d + 2)
    this.stateText.setPosition(x, y + STATE_Y).setDepth(d + 2)
    if (this.bubble) this.bubble.setPosition(x, y + BUBBLE_Y).setDepth(d + 3)
    if (this.bar) this.bar.setPosition(x - BAR_W / 2, y + BAR_Y).setDepth(d + 2)
  }

  private redrawArrow() {
    if (!this.arrow) return
    const cx = this.sprite.x, cy = this.sprite.y
    const [ox, oy] = FACING_OFFSET[this.facing]
    const ax = cx + ox, ay = cy + oy
    const [x1, y1, x2, y2, x3, y3] = ARROW_TRI[this.facing]
    this.arrow.clear()
    this.arrow.fillStyle(0xffffff, 0.9)
    this.arrow.lineStyle(1.5, 0x333333, 1)
    this.arrow.fillTriangle(ax + x1, ay + y1, ax + x2, ay + y2, ax + x3, ay + y3)
    this.arrow.strokeTriangle(ax + x1, ay + y1, ax + x2, ay + y2, ax + x3, ay + y3)
  }

  // ── 叠加层 ───────────────────────────────────────────────────────────────────

  setStateLabel(label: string | null) {
    if (label === this.stateLabel) return
    this.stateLabel = label
    if (label) this.stateText.setText(label).setVisible(true)
    else this.stateText.setVisible(false)
  }

  /** 离线（agent 进程挂了但身体还在）→ 半透明 */
  setDimmed(dim: boolean) {
    if (dim === this.dimmed) return
    this.dimmed = dim
    const a = dim ? 0.45 : 1
    this.sprite.setAlpha(a)
    this.nameText.setAlpha(a)
    this.stateText.setAlpha(a)
    this.bar?.setAlpha(a)
  }

  setBubble(text: string | null) {
    if (!text) {
      if (this.bubble) { this.bubble.destroy(true); this.bubble = null; this.bubbleText = null; this.bubbleBg = null }
      return
    }
    if (this.bubble && this.bubbleText && this.bubbleText.text === text) return
    if (!this.bubble) {
      this.bubbleBg = this.scene.add.graphics()
      this.bubbleText = this.scene.add.text(0, 0, '', {
        fontFamily: 'system-ui, "PingFang SC", "Microsoft YaHei", sans-serif',
        fontSize: '13px',
        color: '#1a202c',
        wordWrap: { width: 220, useAdvancedWrap: true },
        align: 'left',
      }).setOrigin(0.5, 1).setResolution(2)
      this.bubble = this.scene.add.container(this.sprite.x, this.sprite.y + BUBBLE_Y, [this.bubbleBg, this.bubbleText])
    }
    const t = this.bubbleText!
    t.setText(text)
    const padX = 8, padY = 5
    const w = t.width + padX * 2
    const h = t.height + padY * 2
    const g = this.bubbleBg!
    g.clear()
    g.fillStyle(0xffffff, 0.95)
    g.lineStyle(1, 0x2d3748, 0.6)
    g.fillRoundedRect(-w / 2, -h - 8, w, h, 6)
    g.strokeRoundedRect(-w / 2, -h - 8, w, h, 6)
    g.fillTriangle(-6, -8, 6, -8, 0, 0)
    t.setPosition(0, -8 - padY)
    this.bubble.setAlpha(1)
    this.layout()
  }

  /** 七变量小图标条（null 隐藏） */
  setVars(vars: NeedVars | null) {
    if (!vars) {
      if (this.bar) { this.bar.destroy(); this.bar = null }
      this.barVars = null
      return
    }
    if (this.barVars && NEED_KEYS.every(k => Math.abs(this.barVars![k] - vars[k]) < 0.5)) return
    this.barVars = { ...vars }
    if (!this.bar) this.bar = this.scene.add.graphics()
    const g = this.bar
    g.clear()
    const totalH = NEED_KEYS.length * (BAR_H + BAR_GAP) + 2
    g.fillStyle(0x000000, 0.55)
    g.fillRoundedRect(-2, -2, BAR_W + 4, totalH + 2, 3)
    NEED_KEYS.forEach((k, i) => {
      const y = i * (BAR_H + BAR_GAP)
      const v = Math.max(0, Math.min(100, vars[k] ?? 0)) / 100
      g.fillStyle(0x2d3748, 1)
      g.fillRect(0, y, BAR_W, BAR_H)
      g.fillStyle(v < 0.25 ? 0xe53e3e : NEED_COLORS[k], 1)
      g.fillRect(0, y, Math.round(BAR_W * v), BAR_H)
    })
    this.layout()
  }

  destroy() {
    this.sprite.destroy()
    this.arrow?.destroy()
    this.nameText.destroy()
    this.stateText.destroy()
    this.bubble?.destroy(true)
    this.bar?.destroy()
  }
}
