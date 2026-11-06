import Phaser from 'phaser'
import { fetchObserveLatest } from '../../api/observe'
import { startPoller, PollerHandle } from './Poller'

const POLL_MS = 2000
const MAX_CHARS = 40
const HOLD_MS = 8000          // 最后一次变化后多久淡出
const TYPE_MS = 45            // 打字机：每字
const FADE_MS = 700

/**
 * E8 思考字幕：画布底部一行「鲸仔正在想：…」打字机效果，≤ 40 字，8 s 后淡出；`needs_lines` 作第二行小字。
 * 只显示 C 的摘要字段；C 没起 8002 时静默（请求失败不提示）。
 */
export default class ThoughtBar {
  private poller: PollerHandle
  private main: Phaser.GameObjects.Text
  private sub: Phaser.GameObjects.Text
  private bg: Phaser.GameObjects.Graphics
  private full = ''
  private shown = 0
  private nextCharAt = 0
  private changedAt = 0
  private lastKey = ''
  private alpha = 0
  private w: number
  private h: number

  constructor(private scene: Phaser.Scene, private opts: { name: string; align: 'center' | 'left' | 'right' }) {
    this.w = scene.scale.width
    this.h = scene.scale.height
    this.bg = scene.add.graphics().setDepth(10005).setAlpha(0)
    this.main = scene.add.text(0, 0, '', {
      fontFamily: 'system-ui, "PingFang SC", "Microsoft YaHei", sans-serif',
      fontSize: '26px', color: '#ffffff', stroke: '#000000', strokeThickness: 5,
    }).setDepth(10006).setResolution(2).setAlpha(0)
    this.sub = scene.add.text(0, 0, '', {
      fontFamily: 'system-ui, "PingFang SC", "Microsoft YaHei", sans-serif',
      fontSize: '16px', color: '#cbd5e0', stroke: '#000000', strokeThickness: 4,
    }).setDepth(10006).setResolution(2).setAlpha(0)
    this.layout()
    scene.scale.on(Phaser.Scale.Events.RESIZE, this.onResize, this)

    this.poller = startPoller({
      name: 'observe',
      intervalMs: POLL_MS,
      maxBackoffMs: 30000,
      fn: async () => {
        const r = await fetchObserveLatest()
        if (!r) return false
        const key = `${r.ts}|${r.thought}`
        if (key !== this.lastKey) {
          this.lastKey = key
          this.setThought(r.thought, r.needs)
        }
        return true
      },
    })
  }

  private onResize() {
    this.w = this.scene.scale.width
    this.h = this.scene.scale.height
    this.layout()
  }

  private layout() {
    const y = this.h - 64
    const x = this.opts.align === 'left' ? 48 : this.opts.align === 'right' ? this.w - 48 : this.w / 2
    const ox = this.opts.align === 'left' ? 0 : this.opts.align === 'right' ? 1 : 0.5
    this.main.setOrigin(ox, 1).setPosition(x, y)
    this.sub.setOrigin(ox, 1).setPosition(x, y + 24)
  }

  private setThought(thought: string, needs: string[]) {
    let t = thought.replace(/\s+/g, ' ').trim()
    if (t.startsWith('→')) t = ''   // 纯工具调用（→ finish / → move_to_tile）不是「念头」，不上屏
    if (!t) { this.full = ''; this.shown = 0; return }
    if ([...t].length > MAX_CHARS) t = [...t].slice(0, MAX_CHARS - 1).join('') + '…'
    this.full = t
    this.shown = 0
    this.changedAt = this.scene.time.now
    this.nextCharAt = this.changedAt
    this.sub.setText(needs.slice(0, 2).join('  ·  '))
  }

  update(time: number, dt: number) {
    // 打字机
    if (this.full && this.shown < [...this.full].length && time >= this.nextCharAt) {
      this.shown++
      this.nextCharAt = time + TYPE_MS
      this.main.setText(`${this.opts.name}正在想：${[...this.full].slice(0, this.shown).join('')}`)
      this.redrawBg()
    }
    // 可见性：有内容且距最后一次变化 < HOLD → 显示；否则淡出
    const visible = !!this.full && time - this.changedAt < HOLD_MS
    const target = visible ? 1 : 0
    if (this.alpha !== target) {
      const step = dt / FADE_MS
      this.alpha = target > this.alpha ? Math.min(1, this.alpha + step) : Math.max(0, this.alpha - step)
      this.main.setAlpha(this.alpha)
      this.sub.setAlpha(this.alpha * 0.9)
      this.bg.setAlpha(this.alpha * 0.55)
    }
  }

  private redrawBg() {
    const b = this.main.getBounds()
    const s = this.sub.text ? this.sub.getBounds() : null
    const x0 = Math.min(b.left, s ? s.left : b.left) - 14
    const x1 = Math.max(b.right, s ? s.right : b.right) + 14
    const y0 = b.top - 8
    const y1 = (s ? s.bottom : b.bottom) + 8
    this.bg.clear()
    this.bg.fillStyle(0x0f1020, 1)
    this.bg.fillRoundedRect(x0, y0, x1 - x0, y1 - y0, 10)
  }

  destroy() {
    this.poller.stop()
    this.scene.scale.off(Phaser.Scale.Events.RESIZE, this.onResize, this)
    this.main.destroy(); this.sub.destroy(); this.bg.destroy()
  }
}
