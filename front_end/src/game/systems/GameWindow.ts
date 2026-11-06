import Phaser from 'phaser'
import { useGameStore } from '../../store/gameStore'
import { resolveFollowTarget } from './TickSystem'
import type { GameSession } from '../../types'

const W = 360, H = 250
const PHASE_LABEL: Record<string, string> = { day: '白天', dusk: '黄昏', night: '夜晚' }

/**
 * E15 游戏机小窗：跟随目标 `use game_console`（/state 的 game.status === "playing"）时，画布右上角出一个小窗：
 * D 的 brain 局内指标（第几天 / 时段 / 生命 / 饥饿 / 理智 / 死亡数）+ 该局最新的回放 GIF（只读 /gameruns/<run_id>/*.gif）。
 */
export default class GameWindow {
  private bg: Phaser.GameObjects.Graphics
  private title: Phaser.GameObjects.Text
  private lines: Phaser.GameObjects.Text
  private img: Phaser.GameObjects.Image | null = null
  private imgKey: string | null = null
  private visible = false
  private lastSig = ''
  private gifLookupFor: string | null = null
  private x = 0
  private y = 0

  constructor(private scene: Phaser.Scene, private opts: { follow: string | null; side: 'left' | 'right'; topOffset: number }) {
    const f = (size: string, color = '#ffffff') => ({ fontFamily: 'system-ui, "PingFang SC", "Microsoft YaHei", sans-serif', fontSize: size, color, stroke: '#000000', strokeThickness: 3 })
    this.bg = this.scene.add.graphics().setDepth(10005).setVisible(false)
    this.title = this.scene.add.text(0, 0, '🎮 她在玩游戏', f('18px', '#ffe9a8')).setDepth(10006).setResolution(2).setVisible(false)
    this.lines = this.scene.add.text(0, 0, '', { ...f('14px', '#e2e8f0'), lineSpacing: 4 }).setDepth(10006).setResolution(2).setVisible(false)
    this.layout()
    this.scene.scale.on(Phaser.Scale.Events.RESIZE, this.layout, this)
  }

  private layout() {
    const sw = this.scene.scale.width
    this.x = this.opts.side === 'right' ? sw - W - 16 : 16
    this.y = this.opts.topOffset
    this.bg.clear(); this.bg.fillStyle(0x0f1020, 0.82); this.bg.fillRoundedRect(this.x, this.y, W, H, 12); this.bg.lineStyle(2, 0x4a5568, 0.9); this.bg.strokeRoundedRect(this.x, this.y, W, H, 12)
    this.title.setPosition(this.x + 14, this.y + 10)
    this.lines.setPosition(this.x + 14, this.y + 40)
    this.img?.setPosition(this.x + W - 14 - 150 / 2, this.y + 40 + 100 / 2)
  }

  private setVisible(v: boolean) {
    if (v === this.visible) return
    this.visible = v
    this.bg.setVisible(v); this.title.setVisible(v); this.lines.setVisible(v); this.img?.setVisible(v)
  }

  /** 该局最新 GIF（D 的 tools/replay.py 产物）：列目录找最新的 .gif，装成静态纹理（Phaser 不播 GIF 动画，取首帧） */
  private async loadGif(runId: string) {
    if (this.gifLookupFor === runId) return
    this.gifLookupFor = runId
    try {
      const list = await fetch(`/gameruns/${encodeURIComponent(runId)}/`).then(r => r.ok ? r.json() : [])
      const gifs = (list as { name: string; dir: boolean }[]).filter(e => !e.dir && /\.(gif|png)$/i.test(e.name)).map(e => e.name).sort()
      if (gifs.length === 0) return
      const url = `/gameruns/${encodeURIComponent(runId)}/${encodeURIComponent(gifs[gifs.length - 1])}`
      const key = `gamegif_${runId}_${gifs[gifs.length - 1]}`
      if (!this.scene.textures.exists(key)) {
        await new Promise<void>((resolve) => {
          this.scene.load.image(key, url)
          this.scene.load.once(Phaser.Loader.Events.COMPLETE, () => resolve())
          this.scene.load.start()
        })
      }
      if (!this.scene.textures.exists(key)) return
      this.img?.destroy()
      this.imgKey = key
      this.img = this.scene.add.image(0, 0, key).setDepth(10006).setVisible(this.visible)
      const tex = this.scene.textures.get(key).getSourceImage() as HTMLImageElement
      const s = Math.min(150 / tex.width, 100 / tex.height)
      this.img.setScale(s)
      this.layout()
    } catch { /* 没有产物就只显示指标 */ }
  }

  update() {
    const s = useGameStore.getState()
    const target = resolveFollowTarget(s.players, this.opts.follow)
    const vars = target ? s.playerVars[target.id] : undefined
    const game: GameSession | null | undefined = vars?.game
    const playing = !!target && (game?.status === 'playing' || /玩游戏|gaming/.test(target.stateLabel ?? '') || (target.tags ?? []).includes('gaming'))
    this.setVisible(playing)
    if (!playing) return
    const sig = JSON.stringify([game?.day, game?.phase, game?.health, game?.hunger, game?.sanity, game?.deaths, game?.ticks])
    if (sig !== this.lastSig) {
      this.lastSig = sig
      const g: Partial<GameSession> = game ?? {}
      const row = (k: string, v: unknown) => `${k}：${v === undefined || v === null ? '–' : typeof v === 'number' ? Math.round(v) : v}`
      this.lines.setText([
        row('第几天', g.day), row('时段', g.phase ? (PHASE_LABEL[g.phase] ?? g.phase) : undefined),
        row('生命', g.health), row('饥饿', g.hunger), row('理智', g.sanity), row('死亡', g.deaths),
        g.run_id || g.brain_run_id ? `局 ${g.run_id ?? g.brain_run_id}` : '（等 brain 指标…）',
      ].join('\n'))
    }
    const run = game?.run_id ?? game?.brain_run_id
    if (run) void this.loadGif(run)
  }

  destroy() {
    this.scene.scale.off(Phaser.Scale.Events.RESIZE, this.layout, this)
    this.bg.destroy(); this.title.destroy(); this.lines.destroy(); this.img?.destroy()
    if (this.imgKey && this.scene.textures.exists(this.imgKey)) this.scene.textures.remove(this.imgKey)
  }
}
