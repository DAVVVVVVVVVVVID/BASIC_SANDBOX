import Phaser from 'phaser'
import Overlay from '../systems/Overlay'
import ThoughtBar from '../systems/ThoughtBar'
import InfoPanel from '../systems/InfoPanel'
import GameWindow from '../systems/GameWindow'
import { useGameStore } from '../../store/gameStore'
import { EventBus } from '../EventBus'
import type { SpectateParams } from '../../spectate/params'

export interface UISceneData {
  mode: 'play' | 'spectate'
  params: SpectateParams | null
}

/**
 * 屏幕空间 UI 场景：与 GameScene 并行运行，自己的相机 zoom 恒为 1，
 * 所以日夜色调 / 雨 / 时钟 / 徽标不受游戏相机缩放影响（scrollFactor(0) 的对象仍会被 zoom 放缩）。
 */
export default class UIScene extends Phaser.Scene {
  private overlay!: Overlay
  private statsText: Phaser.GameObjects.Text | null = null
  private thought: ThoughtBar | null = null
  private panel: InfoPanel | null = null
  private gameWin: GameWindow | null = null
  private zoneText: Phaser.GameObjects.Text | null = null
  private zoneTween: Phaser.Tweens.Tween | null = null
  private onZone = ({ label }: { label: string }) => {
    if (!this.zoneText) return
    this.zoneTween?.stop()
    this.zoneText.setText(label).setAlpha(0).setVisible(true)
    this.zoneTween = this.tweens.add({ targets: this.zoneText, alpha: 1, duration: 500, hold: 2200, yoyo: true, onComplete: () => this.zoneText?.setVisible(false) })
  }
  private mode: 'play' | 'spectate' = 'play'
  private params: SpectateParams | null = null
  private onStats = (s: { fps: number; actors: number; connection: string; transport?: string; camMode: string; target: string | null }) => {
    this.statsText?.setText(`${s.fps} fps · ${s.actors} actors · ${s.connection}/${s.transport ?? '-'} · ${s.camMode}${s.target ? ' → ' + s.target : ''}`)
  }

  constructor() { super({ key: 'UIScene' }) }

  init(data: UISceneData) {
    this.mode = data.mode
    this.params = data.params
  }

  create() {
    this.overlay = new Overlay(this, { clock: this.mode === 'spectate' ? (this.params?.clock ?? true) : false, clockSide: this.params?.safe === 'tr' ? 'left' : 'right' })
    const safe = this.params?.safe ?? null
    // 首次进入某区域时顶部居中淡入区域名
    this.zoneText = this.add.text(this.scale.width / 2, safe === 'tr' || safe === 'tl' ? 96 : 56, '', {
      fontFamily: 'system-ui, "PingFang SC", "Microsoft YaHei", sans-serif', fontSize: '30px', color: '#ffffff',
      stroke: '#000000', strokeThickness: 6, letterSpacing: 4,
    }).setOrigin(0.5, 0).setDepth(10005).setResolution(2).setVisible(false)
    EventBus.on('zone-changed', this.onZone)
    if (this.mode === 'spectate' && (this.params?.panel ?? true)) {
      this.panel = new InfoPanel(this, { follow: this.params?.follow ?? null, side: safe === 'bl' ? 'right' : 'left' })
    }
    if (this.mode === 'spectate' && this.params?.follow) {
      // E15：时钟下方（safe=tr 时放左侧）
      this.gameWin = new GameWindow(this, { follow: this.params.follow, side: safe === 'tr' ? 'left' : 'right', topOffset: 56 })
    }
    if (this.mode === 'spectate' && (this.params?.thought ?? true)) {
      // 安全区：右下被占 → 字幕靠左；左下被占 → 靠右
      const align = safe === 'br' ? 'center' : safe === 'bl' ? 'left' : 'center'
      // follow 可能是 player id（鲸仔_ddba81）或 agent_id（whale），字幕前缀统一显示名字
      const raw = this.params?.follow ?? '鲸仔'
      const name = /^[a-z0-9_-]+$/i.test(raw) ? '鲸仔' : raw.replace(/_[0-9a-f]{6}$/i, '')
      this.thought = new ThoughtBar(this, { name, align })
    }
    if (this.params?.stats) {
      // 左上（时钟在右上、字幕在底部）；safe=tl 时挪到左下
      this.statsText = this.add.text(12, safe === 'tl' ? this.scale.height - 12 : 12, '', {
        fontFamily: 'monospace', fontSize: '14px', color: '#9ae6b4',
        backgroundColor: 'rgba(0,0,0,0.5)', padding: { x: 6, y: 3 },
      }).setOrigin(0, safe === 'tl' ? 1 : 0).setDepth(10004)
      EventBus.on('stats', this.onStats)
    }
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
      EventBus.off('stats', this.onStats)
      EventBus.off('zone-changed', this.onZone)
      this.overlay.destroy()
      this.thought?.destroy()
      this.panel?.destroy()
      this.gameWin?.destroy()
    })
  }

  update(time: number, dt: number) {
    const s = useGameStore.getState()
    this.overlay.update(s.worldState)
    this.thought?.update(time, dt)
    this.panel?.update()
    this.gameWin?.update()
    const showBadge = this.mode === 'spectate' ? (this.params?.hud ?? true) : false
    this.overlay.setBadge(showBadge && s.connection === 'offline' ? '后端连接中断，重连中…' : null)
  }
}
