import Phaser from 'phaser'
import type { WorldState, Weather } from '../../types'

/**
 * 屏幕空间叠加层：日夜色调（按 worldState.time 连续插值）、天气（雨 / 多云）、时钟。
 * 全部 setScrollFactor(0)，深度 10000+。
 */

// 时刻（小时）→ 乘法色。白色 = 无影响
const TINT_KEYS: [number, number][] = [
  [0,    0x5a6aa8],
  [4.5,  0x5a6aa8],
  [6,    0xd9a070],  // 日出
  [7.5,  0xffe8c8],
  [9,    0xffffff],
  [17,   0xffffff],
  [18.5, 0xffc27a],  // 日落
  [20,   0xc08a8a],
  [21.5, 0x7a7cb8],
  [23,   0x5a6aa8],
  [24,   0x5a6aa8],
]

export function tintForHour(h: number): number {
  const hh = ((h % 24) + 24) % 24
  for (let i = 0; i < TINT_KEYS.length - 1; i++) {
    const [h0, c0] = TINT_KEYS[i]
    const [h1, c1] = TINT_KEYS[i + 1]
    if (hh >= h0 && hh <= h1) {
      const t = h1 === h0 ? 0 : (hh - h0) / (h1 - h0)
      const a = Phaser.Display.Color.IntegerToColor(c0)
      const b = Phaser.Display.Color.IntegerToColor(c1)
      const r = Phaser.Display.Color.Interpolate.ColorWithColor(a, b, 1, t)
      return Phaser.Display.Color.GetColor(r.r, r.g, r.b)
    }
  }
  return 0xffffff
}

export function parseHour(ws: WorldState | null): number {
  if (!ws?.time) return 12
  const [h, m, s] = ws.time.split(':').map(Number)
  return (h || 0) + (m || 0) / 60 + (s || 0) / 3600
}

const WEATHER_TINT: Record<Weather, number> = { sunny: 0xffffff, cloudy: 0xb9bfcc, rain: 0x9aa4b8 }
const WEATHER_LABEL: Record<Weather, string> = { sunny: '☀ 晴', cloudy: '☁ 多云', rain: '🌧 雨' }
const PERIOD_LABEL: Record<string, string> = { morning: '早晨', day: '白天', dusk: '黄昏', night: '夜晚' }

export default class Overlay {
  private tint: Phaser.GameObjects.Rectangle
  private rain: Phaser.GameObjects.Particles.ParticleEmitter | null = null
  private clock: Phaser.GameObjects.Text | null = null
  private badge: Phaser.GameObjects.Text | null = null
  private lastColor = -1
  private lastWeather: Weather | null = null
  private w: number
  private h: number

  constructor(private scene: Phaser.Scene, opts: { clock: boolean }) {
    const cam = scene.cameras.main
    this.w = cam.width
    this.h = cam.height
    this.tint = scene.add.rectangle(0, 0, this.w, this.h, 0xffffff, 1)
      .setOrigin(0, 0)
      .setScrollFactor(0)
      .setDepth(10000)
      .setBlendMode(Phaser.BlendModes.MULTIPLY)

    if (!scene.textures.exists('raindrop')) {
      const g = scene.make.graphics({ x: 0, y: 0 }, false)
      g.fillStyle(0xcfe3ff, 0.9)
      g.fillRect(0, 0, 2, 14)
      g.generateTexture('raindrop', 2, 14)
      g.destroy()
    }

    if (opts.clock) {
      this.clock = scene.add.text(this.w - 16, 12, '', {
        fontFamily: 'system-ui, "PingFang SC", "Microsoft YaHei", sans-serif',
        fontSize: '20px',
        color: '#ffffff',
        stroke: '#000000', strokeThickness: 4,
      }).setOrigin(1, 0).setScrollFactor(0).setDepth(10002).setResolution(2)
    }

    scene.scale.on(Phaser.Scale.Events.RESIZE, this.onResize, this)
  }

  private onResize() {
    const cam = this.scene.cameras.main
    this.w = cam.width
    this.h = cam.height
    this.tint.setSize(this.w, this.h)
    this.clock?.setPosition(this.w - 16, 12)
    this.badge?.setPosition(this.w / 2, 12)
    if (this.rain) {
      // 尺寸变了就重建雨幕，避免处理 emitZone 类型差异
      this.setRain(false)
      this.setRain(true)
    }
  }

  update(ws: WorldState | null) {
    const hour = parseHour(ws)
    const weather = ws?.weather ?? 'sunny'
    const day = Phaser.Display.Color.IntegerToColor(tintForHour(hour))
    const wt = Phaser.Display.Color.IntegerToColor(WEATHER_TINT[weather] ?? 0xffffff)
    const color = Phaser.Display.Color.GetColor(
      Math.round(day.red * wt.red / 255),
      Math.round(day.green * wt.green / 255),
      Math.round(day.blue * wt.blue / 255),
    )
    if (color !== this.lastColor) {
      this.lastColor = color
      this.tint.setFillStyle(color, 1)
      this.tint.setVisible(color !== 0xffffff)
    }

    if (weather !== this.lastWeather) {
      this.lastWeather = weather
      this.setRain(weather === 'rain')
    }

    if (this.clock && ws) {
      const txt = `${ws.date.slice(5)}  ${ws.time.slice(0, 5)}  ${PERIOD_LABEL[ws.period] ?? ws.period}  ${WEATHER_LABEL[weather] ?? weather}${ws.running ? '' : '  ⏸'}${ws.speed !== 1 ? `  ×${ws.speed}` : ''}`
      if (this.clock.text !== txt) this.clock.setText(txt)
    }
  }

  private setRain(on: boolean) {
    if (on && !this.rain) {
      this.rain = this.scene.add.particles(0, -20, 'raindrop', {
        x: { min: 0, max: this.w + 200 },
        speedY: { min: 900, max: 1200 },
        speedX: { min: -140, max: -100 },
        lifespan: 1600,
        quantity: 3,
        frequency: 16,
        alpha: { start: 0.7, end: 0.2 },
        scale: { min: 0.8, max: 1.3 },
        rotate: 8,
      }).setScrollFactor(0).setDepth(10001)
    } else if (!on && this.rain) {
      this.rain.destroy()
      this.rain = null
    }
  }

  /** 顶部小提示（连接中断等）；null 隐藏 */
  setBadge(text: string | null) {
    if (!text) { this.badge?.setVisible(false); return }
    if (!this.badge) {
      this.badge = this.scene.add.text(this.w / 2, 12, '', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '14px',
        color: '#fed7d7',
        backgroundColor: 'rgba(120,20,20,0.75)',
        padding: { x: 10, y: 4 },
      }).setOrigin(0.5, 0).setScrollFactor(0).setDepth(10003).setResolution(2)
    }
    this.badge.setText(text).setVisible(true)
  }

  destroy() {
    this.scene.scale.off(Phaser.Scale.Events.RESIZE, this.onResize, this)
    this.tint.destroy()
    this.rain?.destroy()
    this.clock?.destroy()
    this.badge?.destroy()
  }
}
