import Phaser from 'phaser'
import Overlay from '../systems/Overlay'
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
  private mode: 'play' | 'spectate' = 'play'
  private params: SpectateParams | null = null
  private onStats = (s: { fps: number; actors: number; connection: string; camMode: string; target: string | null }) => {
    this.statsText?.setText(`${s.fps} fps · ${s.actors} actors · ${s.connection} · ${s.camMode}${s.target ? ' → ' + s.target : ''}`)
  }

  constructor() { super({ key: 'UIScene' }) }

  init(data: UISceneData) {
    this.mode = data.mode
    this.params = data.params
  }

  create() {
    this.overlay = new Overlay(this, { clock: this.mode === 'spectate' ? (this.params?.clock ?? true) : false })
    if (this.params?.stats) {
      this.statsText = this.add.text(12, this.scale.height - 12, '', {
        fontFamily: 'monospace', fontSize: '14px', color: '#9ae6b4',
        backgroundColor: 'rgba(0,0,0,0.5)', padding: { x: 6, y: 3 },
      }).setOrigin(0, 1).setDepth(10004)
      EventBus.on('stats', this.onStats)
    }
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
      EventBus.off('stats', this.onStats)
      this.overlay.destroy()
    })
  }

  update() {
    const s = useGameStore.getState()
    this.overlay.update(s.worldState)
    const showBadge = this.mode === 'spectate' ? (this.params?.hud ?? true) : false
    this.overlay.setBadge(showBadge && s.connection === 'offline' ? '后端连接中断，重连中…' : null)
  }
}
