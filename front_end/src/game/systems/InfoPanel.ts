import Phaser from 'phaser'
import { useGameStore } from '../../store/gameStore'
import { resolveFollowTarget } from './TickSystem'
import { NEED_KEYS } from '../../types'
import { NEED_COLORS, NEED_LABELS } from '../objects/ActorSprite'
import { zoneLabel, buildTileIndex } from '../map/zones'
import { deriveStateLabel } from '../stateLabel'
import { TOWN } from '../../api/client'
import type { Tile } from '../../types'
import { itemMeta, normalizeInventory } from '../items'
import { gameNowMs, busyText, dailyUseLines, rentText } from '../v11'

const W = 300
const PAD = 14
const BAR_W = 150
const BAR_H = 10
const NEED_FULL: Record<string, string> = { fullness: '饱腹', energy: '精力', social: '社交', fun: '乐趣', mood: '心情' }

/**
 * 旁观画面的游戏式基础信息面板（主播 11-06 反馈）：左下角一张卡，名字、所在区域、正在做什么、七变量、在线状态。
 * 名字牌仍同时留在头顶。safe=bl 时挪到右下。
 */
export default class InfoPanel {
  private bg: Phaser.GameObjects.Graphics
  private name: Phaser.GameObjects.Text
  private sub: Phaser.GameObjects.Text
  private state: Phaser.GameObjects.Text
  private bars: Phaser.GameObjects.Graphics
  private wallet: Phaser.GameObjects.Text
  private extra1: Phaser.GameObjects.Text   // v1.1：进食 / 下厨进度 或 今日上限
  private extra2: Phaser.GameObjects.Text   // v1.1：房租
  private labels: Phaser.GameObjects.Text[] = []
  private values: Phaser.GameObjects.Text[] = []
  private x = 0
  private y = 0
  private h = 0
  private tileIndex = new Map<string, Tile>()
  private tilesRef: Tile[] | null = null
  private lastSig = ''

  constructor(private scene: Phaser.Scene, private opts: { follow: string | null; side: 'left' | 'right' }) {
    const f = (size: string, color = '#ffffff') => ({
      fontFamily: 'system-ui, "PingFang SC", "Microsoft YaHei", sans-serif', fontSize: size, color, stroke: '#000000', strokeThickness: 3,
    })
    this.bg = scene.add.graphics().setDepth(10005)
    this.name = scene.add.text(0, 0, '', f('24px', '#ffe9a8')).setDepth(10006).setResolution(2)
    this.sub = scene.add.text(0, 0, '', f('14px', '#cbd5e0')).setDepth(10006).setResolution(2)
    this.state = scene.add.text(0, 0, '', f('17px', '#c3dafe')).setDepth(10006).setResolution(2)
    this.bars = scene.add.graphics().setDepth(10006)
    this.wallet = scene.add.text(0, 0, '', f('14px', '#ffe9a8')).setDepth(10006).setResolution(2)
    this.extra1 = scene.add.text(0, 0, '', f('13px', '#9ae6b4')).setDepth(10006).setResolution(2)
    this.extra2 = scene.add.text(0, 0, '', f('13px', '#a0aec0')).setDepth(10006).setResolution(2)
    for (const k of NEED_KEYS) {
      this.labels.push(scene.add.text(0, 0, `${NEED_LABELS[k]} ${NEED_FULL[k]}`, f('13px', '#e2e8f0')).setDepth(10006).setResolution(2))
      this.values.push(scene.add.text(0, 0, '', f('13px', '#ffffff')).setOrigin(1, 0).setDepth(10006).setResolution(2))
    }
    this.h = PAD * 2 + 30 + 20 + 26 + NEED_KEYS.length * 20 + 6 + 22 + 18 + 18   // 末行：金币 + 背包（W9）+ v1.1 两行（进度 / 上限、房租）
    this.layout()
    scene.scale.on(Phaser.Scale.Events.RESIZE, this.layout, this)
  }

  private layout() {
    const sw = this.scene.scale.width, sh = this.scene.scale.height
    this.x = this.opts.side === 'left' ? 16 : sw - W - 16
    this.y = sh - this.h - 16
    this.redrawBg()
    let cy = this.y + PAD
    this.name.setPosition(this.x + PAD, cy); cy += 30
    this.sub.setPosition(this.x + PAD, cy); cy += 20
    this.state.setPosition(this.x + PAD, cy); cy += 26
    NEED_KEYS.forEach((_, i) => {
      this.labels[i].setPosition(this.x + PAD, cy + i * 20)
      this.values[i].setPosition(this.x + W - PAD, cy + i * 20)
    })
    this.wallet.setPosition(this.x + PAD, cy + NEED_KEYS.length * 20 + 4)
    this.extra1.setPosition(this.x + PAD, cy + NEED_KEYS.length * 20 + 4 + 22)
    this.extra2.setPosition(this.x + PAD, cy + NEED_KEYS.length * 20 + 4 + 40)
    this.redrawBars()
  }

  private redrawBg() {
    this.bg.clear()
    this.bg.fillStyle(0x0f1020, 0.78)
    this.bg.fillRoundedRect(this.x, this.y, W, this.h, 12)
    this.bg.lineStyle(2, 0x4a5568, 0.9)
    this.bg.strokeRoundedRect(this.x, this.y, W, this.h, 12)
  }

  private vals: number[] | null = null
  private redrawBars() {
    this.bars.clear()
    const baseY = this.y + PAD + 30 + 20 + 26
    NEED_KEYS.forEach((k, i) => {
      const y = baseY + i * 20 + 6
      const x0 = this.x + PAD + 72
      this.bars.fillStyle(0x2d3748, 1)
      this.bars.fillRoundedRect(x0, y, BAR_W, BAR_H, 4)
      const v = this.vals ? Math.max(0, Math.min(100, this.vals[i])) : 0
      if (v > 0) {
        this.bars.fillStyle(v < 25 ? 0xe53e3e : NEED_COLORS[k], 1)
        this.bars.fillRoundedRect(x0, y, Math.max(6, BAR_W * v / 100), BAR_H, 4)
      }
    })
  }

  update() {
    const s = useGameStore.getState()
    if (s.tiles !== this.tilesRef) { this.tilesRef = s.tiles; this.tileIndex = buildTileIndex(s.tiles) }
    const target = resolveFollowTarget(s.players, this.opts.follow)
    const vars = target ? s.playerVars[target.id] : undefined
    const tile = target ? this.tileIndex.get(`${target.position.x},${target.position.y}`) : undefined
    const zone = zoneLabel(tile)
    const label = target ? (deriveStateLabel(target, s.objects) ?? (target.state === 'idle' ? '发呆中' : target.state)) : ''
    const online = target ? target.online !== false : false
    const inv = normalizeInventory(target?.inventory)
    const nowMs = gameNowMs(s.worldState)
    const busyLine = target?.busy ? busyText(target.busy, nowMs) : null
    const useLine = target ? dailyUseLines(target.daily_use).map(l => l.text).join('  ') : ''
    const rent = target ? rentText(target.rent) : null
    const sig = JSON.stringify([target?.name, zone, label, online, vars?.vars, s.worldState?.time?.slice(0, 5), s.transport, target?.gold, inv, busyLine, useLine, rent?.text])
    if (sig === this.lastSig) return
    this.lastSig = sig
    if (!target) {
      this.name.setText(TOWN ? `${TOWN} · ${this.opts.follow ?? '全景'}` : (this.opts.follow ?? '鲸仔小镇'))
      this.sub.setText(this.opts.follow ? '目标不在场 · 全景' : `${s.players.length} 人在镇上`)
      this.state.setText('')
      this.wallet.setText(''); this.extra1.setText(''); this.extra2.setText('')
      this.vals = null
      this.values.forEach(v => v.setText('–'))
    } else {
      this.name.setText(target.name)
      this.sub.setText(`${TOWN ? `[${TOWN}] ` : ''}${zone || '小镇'}${online ? '' : ' · 离线'}`)
      this.state.setText(label)
      const gold = typeof target.gold === 'number' ? `💰 ${target.gold}` : ''
      const bag = inv.slice(0, 8).map(it => { const m = itemMeta(it.type, it.name); return `${m.icon}${it.count > 1 ? it.count : ''}` }).join(' ')
      this.wallet.setText([gold, bag].filter(Boolean).join('   '))
      this.extra1.setText(busyLine ?? useLine)
      this.extra2.setText(rent ? rent.text : '').setColor(rent?.overdue ? '#fc8181' : '#a0aec0')
      this.vals = vars ? NEED_KEYS.map(k => vars.vars[k]) : null
      this.values.forEach((v, i) => v.setText(this.vals ? String(Math.round(this.vals[i])) : '–'))
    }
    this.redrawBars()
  }

  destroy() {
    this.scene.scale.off(Phaser.Scale.Events.RESIZE, this.layout, this)
    this.bg.destroy(); this.name.destroy(); this.sub.destroy(); this.state.destroy(); this.bars.destroy(); this.wallet.destroy(); this.extra1.destroy(); this.extra2.destroy()
    this.labels.forEach(t => t.destroy()); this.values.forEach(t => t.destroy())
  }
}
