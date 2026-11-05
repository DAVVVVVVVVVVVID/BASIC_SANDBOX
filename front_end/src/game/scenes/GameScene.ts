import Phaser from 'phaser'
import { WorldData, Player, WorldEvent, Position, OtherPlayer, GameObject, Facing } from '../../types'
import TileMap, { preloadTileAssets, TILE_SIZE, SOURCE_TILE, mapSize, tileCenter } from '../map/TileMap'
import PlayerSprite from '../objects/Player'
import OtherPlayerSprite from '../objects/OtherPlayerSprite'
import GameObjectSprite from '../objects/GameObjectSprite'
import InputSystem from '../systems/InputSystem'
import Overlay from '../systems/Overlay'
import { EventBus } from '../EventBus'
import { sendAction } from '../../api/world'
import { useGameStore } from '../../store/gameStore'
import { resolveFollowTarget } from '../systems/TickSystem'
import type { SpectateParams } from '../../spectate/params'

export interface SceneInitData {
  mode: 'play' | 'spectate'
  worldData: WorldData
  events: WorldEvent[]
  player?: Player
  myPlayerId?: string
  spectate?: SpectateParams
}

const MIN_ZOOM = 1 / 6
const MAX_ZOOM = 2.0
const ZOOM_STEP = 1 / 6
/** 跟随镜头默认 zoom：96 × 2/3 = 64 px/格 = 4× 源像素 */
const FOLLOW_ZOOM = 2 / 3
/** 目标消失 / 离线多久后退到全景（ms）。agent 的 online=false 本身就有后端 10 s 心跳延迟 */
const TARGET_LOSS_MS = 500
const CAMERA_LERP_MS = 140

/** 把 zoom 吸附到 1/6 的整数倍（源像素整数缩放） */
function snapZoom(z: number): number {
  const k = Math.max(1, Math.floor(z * (TILE_SIZE / SOURCE_TILE) + 1e-6))
  return k / (TILE_SIZE / SOURCE_TILE)
}

const USE_ICONS: [RegExp, string][] = [
  [/bed|sofa_bed/i, '💤 睡觉中'],
  [/cook|stove|fridge|kitchen|table|eat/i, '🍴 吃饭中'],
  [/bath|shower/i, '🛁 洗澡中'],
  [/toilet/i, '🚻'],
  [/sink/i, '🚰 洗漱中'],
  [/desk|book|study|computer|phone/i, '📖 专注中'],
  [/stream/i, '📺 直播中'],
  [/sofa|chair|bench/i, '🛋 休息中'],
  [/well/i, '🪣 打水中'],
]

/** 从 /world 的 objects / state 推断别人正在干什么（players[] 没有 stateLabel，见报告需求） */
export function deriveStateLabel(p: OtherPlayer, objects: GameObject[], tagsHint?: string[]): string | null {
  if (p.online === false) return '💤 离线'
  const obj = objects.find(o => o.userList?.includes(p.id))
  if (obj) {
    const tags = (tagsHint ?? []).concat(obj.effects?.filter(e => e.type === 'tag').map(e => e.key) ?? [])
    if (tags.includes('sleeping')) return '💤 睡觉中'
    if (tags.includes('eating'))   return '🍴 吃饭中'
    if (tags.includes('streaming')) return '📺 直播中'
    const key = `${obj.type} ${obj.name} ${obj.sprite ?? ''}`
    for (const [re, label] of USE_ICONS) if (re.test(key)) return label
    return `🔧 ${obj.name}`
  }
  switch (p.state) {
    case 'talking':         return '💬 聊天中'
    case 'requesting_talk': return '💬 想找人聊'
    case 'walking_over':    return '💬 走过去聊'
    case 'using':           return '🔧 使用中'
    default:                return null
  }
}

export default class GameScene extends Phaser.Scene {
  private mode!: 'play' | 'spectate'
  private worldData!: WorldData
  private worldEvents!: WorldEvent[]
  private player: Player | null = null
  private myPlayerId: string | null = null
  private params: SpectateParams | null = null

  private tileMap!: TileMap
  private self: PlayerSprite | null = null
  private others: Map<string, OtherPlayerSprite> = new Map()
  private objectSprites: GameObjectSprite[] = []
  private inputSystem: InputSystem | null = null
  private overlay!: Overlay
  private unsubs: (() => void)[] = []
  private busHandlers: [string, (...args: never[]) => void][] = []

  // 相机
  private camX = 0
  private camY = 0
  private currentZoom = 1
  private camMode: 'follow' | 'pan' = 'follow'
  private targetId: string | null = null
  private targetLostAt = 0
  private panZoom = MIN_ZOOM
  private followZoom = FOLLOW_ZOOM
  private mapPx = { w: 0, h: 0 }

  // 统计
  private statsText: Phaser.GameObjects.Text | null = null
  private statsAt = 0
  private lastPrune = 0
  private lastWorldLen = 0

  constructor() {
    super({ key: 'GameScene' })
  }

  init(data: SceneInitData) {
    this.mode        = data.mode
    this.worldData   = data.worldData
    this.worldEvents = data.events
    this.player      = data.player ?? null
    this.myPlayerId  = data.myPlayerId ?? null
    this.params      = data.spectate ?? null
  }

  preload() {
    preloadTileAssets(this, this.worldData.tiled)
    this.load.spritesheet('player_walk', 'assets/sprites/player_walk.png', { frameWidth: 96, frameHeight: 64 })
    this.load.spritesheet('player_idle', 'assets/sprites/player_idle.png', { frameWidth: 96, frameHeight: 64 })
    for (const obj of this.worldData.objects) {
      if (obj.sprite && !this.textures.exists(`obj_${obj.sprite}`)) {
        this.load.image(`obj_${obj.sprite}`, `assets/sprites/${obj.sprite}.png`)
      }
    }
  }

  private createAnimations() {
    if (!this.anims.exists('walk')) {
      this.anims.create({ key: 'walk', frames: this.anims.generateFrameNumbers('player_walk', { start: 0, end: 7 }), frameRate: 10, repeat: -1 })
    }
    if (!this.anims.exists('idle')) {
      this.anims.create({ key: 'idle', frames: this.anims.generateFrameNumbers('player_idle', { start: 0, end: 8 }), frameRate: 6, repeat: -1 })
    }
  }

  create() {
    this.createAnimations()
    this.buildMap(this.worldData)

    const cam = this.cameras.main
    cam.roundPixels = true

    if (this.mode === 'play' && this.player && this.myPlayerId) {
      this.createSelf(this.player)
      this.currentZoom = 1
      cam.setZoom(1)
      const p = this.self!.getPixelPosition()
      this.camX = p.x; this.camY = p.y
      cam.centerOn(p.x, p.y)
      this.input.on('wheel', (_p: unknown, _o: unknown, _dx: number, deltaY: number) => {
        this.adjustZoom(deltaY > 0 ? -ZOOM_STEP : ZOOM_STEP)
      })
    } else {
      this.followZoom = this.params?.zoom ? snapZoom(this.params.zoom) : FOLLOW_ZOOM
      this.currentZoom = this.panZoom
      this.camMode = 'pan'
      cam.setZoom(this.panZoom)
      this.camX = this.mapPx.w / 2; this.camY = this.mapPx.h / 2
      cam.centerOn(this.camX, this.camY)
    }

    this.overlay = new Overlay(this, { clock: this.mode === 'spectate' ? (this.params?.clock ?? true) : false })

    if (this.params?.stats) {
      this.statsText = this.add.text(12, 12, '', {
        fontFamily: 'monospace', fontSize: '14px', color: '#9ae6b4',
        backgroundColor: 'rgba(0,0,0,0.5)', padding: { x: 6, y: 3 },
      }).setScrollFactor(0).setDepth(10004)
    }

    // ── store 订阅 ──
    this.syncOthers(useGameStore.getState().players)
    this.unsubs.push(useGameStore.subscribe((s, prev) => {
      if (s.players !== prev.players || s.objects !== prev.objects) this.syncOthers(s.players)
      if (s.tiles !== prev.tiles && s.tiles.length > 0 && s.tiles.length !== this.lastWorldLen) {
        // 地图换了（B16 新地图 / 后端换版本）：重建背景
        this.inputSystem?.setTiles(s.tiles)
      }
      if (s.playerVars !== prev.playerVars) this.syncVars()
      if (s.myPlayerId !== prev.myPlayerId && s.myPlayerId && this.mode === 'play') {
        this.myPlayerId = s.myPlayerId
        this.inputSystem?.setPlayerId(s.myPlayerId)
      }
    }))
    this.lastWorldLen = this.worldData.tiles.length

    this.on('player-snapshot', ({ player, sentAt }: { player: Player; sentAt: number }) => {
      this.player = player
      this.inputSystem?.applyServerSnapshot(player.position, player.facing, sentAt)
      this.inputSystem?.setEnabled(true)
      this.self?.setStateLabel(player.stateLabel ?? deriveStateLabel(
        { id: player.id, name: player.profile?.name ?? '', position: player.position, facing: player.facing, state: player.state },
        useGameStore.getState().objects, player.tags))
    })
    this.on('player-rejoined', ({ player }: { playerId: string; player: Player }) => {
      this.player = player
      this.self?.snapTo(player.position, player.facing)
      this.inputSystem?.applyServerSnapshot(player.position, player.facing, performance.now() + 1)
    })
    this.on('chat-message', ({ entityId, content }: { entityId: string; content: string }) => {
      useGameStore.getState().pushBubble(entityId, content)
    })

    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => this.teardown())
  }

  private on(evt: string, fn: (...args: never[]) => void) {
    EventBus.on(evt, fn)
    this.busHandlers.push([evt, fn])
  }

  private teardown() {
    for (const u of this.unsubs) u()
    this.unsubs = []
    for (const [e, f] of this.busHandlers) EventBus.off(e, f)
    this.busHandlers = []
    this.inputSystem?.destroy()
    this.others.forEach(s => s.destroy())
    this.others.clear()
    this.self?.destroy()
    this.overlay?.destroy()
    this.tileMap?.destroy()
  }

  // ── 地图 ─────────────────────────────────────────────────────────────────────

  private buildMap(world: WorldData) {
    this.tileMap?.destroy()
    this.objectSprites = []
    this.tileMap = new TileMap(this, world.tiles, world.tiled)
    this.tileMap.render()
    const { w, h } = mapSize(world.tiles, world.tiled)
    this.mapPx = { w: w * TILE_SIZE, h: h * TILE_SIZE }
    for (const obj of world.objects) this.objectSprites.push(new GameObjectSprite(this, obj))

    const cam = this.cameras.main
    // 全景 zoom：整张图放进画面，吸附到 1/6 的整数倍
    const fit = Math.min(cam.width / this.mapPx.w, cam.height / this.mapPx.h)
    this.panZoom = Math.max(MIN_ZOOM, snapZoom(fit))
    cam.setBounds(-this.mapPx.w, -this.mapPx.h, this.mapPx.w * 3, this.mapPx.h * 3)
  }

  // ── 自己 ─────────────────────────────────────────────────────────────────────

  private createSelf(player: Player) {
    this.self = new PlayerSprite(this, player.position, player.facing, player.profile?.name ?? player.id)
    this.inputSystem = new InputSystem(
      this,
      player.id,
      this.worldData.tiles,
      player.position,
      player.facing,
      {
        onPredictStep: (target, facing) => {
          this.self!.pushWaypoint(target)
          this.self!.setFacing(facing)
          this.checkWorldEvents(target)
        },
        onFacing: (facing: Facing) => this.self!.setFacing(facing),
        onReconcile: (pos, bounced) => {
          const end = this.self!.getPathEnd()
          if (end.x === pos.x && end.y === pos.y) return
          const cur = this.self!.getTile()
          const far = Math.abs(cur.x - pos.x) + Math.abs(cur.y - pos.y) > 3
          if (far && !bounced) this.self!.snapTo(pos)   // 被服务器挪远了（teleport）直接贴过去
          else this.self!.setPath([pos])                 // 回弹 / 小校正：平滑走回
        },
        onInteract: () => this.handleInteract(),
        onUse: () => this.handleUse(),
        onLeave: () => this.handleLeave(),
      },
    )
  }

  // ── 别人 ─────────────────────────────────────────────────────────────────────

  private syncOthers(players: OtherPlayer[]) {
    const objects = useGameStore.getState().objects
    const seen = new Set<string>()
    for (const op of players) {
      if (this.mode === 'play' && op.id === this.myPlayerId) continue
      seen.add(op.id)
      let s = this.others.get(op.id)
      if (!s) {
        s = new OtherPlayerSprite(this, op.position, op.facing, op.name)
        this.others.set(op.id, s)
      } else {
        const end = s.getPathEnd()
        if (end.x !== op.position.x || end.y !== op.position.y) {
          const cur = s.getTile()
          const dist = Math.abs(cur.x - op.position.x) + Math.abs(cur.y - op.position.y)
          if (dist > 12) s.snapTo(op.position, op.facing)         // 瞬移 / 重生：直接贴
          else s.setPath(this.pathBetween(end, op.position, cur))  // 否则沿网格平滑走过去
        }
        if (!s.isMoving()) s.setFacing(op.facing)
      }
      s.setDimmed(op.online === false)
      s.setStateLabel(deriveStateLabel(op, objects))
    }
    for (const [id, sprite] of this.others) {
      if (!seen.has(id)) { sprite.destroy(); this.others.delete(id) }
    }
    this.syncVars()
  }

  /** 从 from 到 to 的网格路点：优先曼哈顿折线（先横后竖），不做寻路（后端已保证合法） */
  private pathBetween(from: Position, to: Position, cur: Position): Position[] {
    const pts: Position[] = []
    const start = (from.x === cur.x && from.y === cur.y) ? cur : from
    if (start !== cur) pts.push({ ...from })
    let x = start.x, y = start.y
    while (x !== to.x) { x += Math.sign(to.x - x); pts.push({ x, y }) }
    while (y !== to.y) { y += Math.sign(to.y - y); pts.push({ x, y }) }
    return pts
  }

  private syncVars() {
    const { playerVars } = useGameStore.getState()
    const bars = this.params?.bars ?? 'none'
    for (const [id, s] of this.others) {
      const show = bars === 'all' || (bars === 'target' && id === this.targetId)
      const v = playerVars[id]
      s.setVars(show && v ? v.vars : null)
    }
  }

  /** 旁观：当前需要拉 /state 的 id（跟随目标；还没解析出目标时拉所有 agent 以匹配 agent_id） */
  getVarTargetIds(): string[] {
    const { players } = useGameStore.getState()
    if (this.params?.bars === 'all') return players.map(p => p.id)
    if (this.targetId) return [this.targetId]
    if (this.params?.follow) return players.filter(p => p.controller === 'agent').map(p => p.id)
    return []
  }

  private checkWorldEvents(pos: Position) {
    for (const event of this.worldEvents) {
      if (event.tiles.some(t => t.x === pos.x && t.y === pos.y)) {
        EventBus.emit('show-interaction', { message: event.description })
        return
      }
    }
  }

  // ── 动作 ─────────────────────────────────────────────────────────────────────

  private entityId() { return useGameStore.getState().myPlayerId ?? this.myPlayerId ?? '' }

  private async handleInteract() {
    try {
      const res = await sendAction(this.entityId(), 'interact')
      if (res.success) EventBus.emit('show-interaction', { message: res.result?.message })
      else if (res.reason === 'no_object_in_front') EventBus.emit('show-interaction', { message: '面前没有可交互的对象' })
    } catch (err) { console.error('[Interact Error]', err) }
  }

  private async handleUse() {
    try {
      const res = await sendAction(this.entityId(), 'use')
      if (res.success) {
        EventBus.emit('show-interaction', { message: res.result?.message })
      } else if (res.reason === 'no_object_in_front') {
        EventBus.emit('show-interaction', { message: '面前没有可使用的对象' })
      } else if (res.reason === 'use_disabled') {
        EventBus.emit('show-interaction', { message: '当前无法使用对象' })
      } else if (res.reason === 'object_cooldown') {
        const s = Math.ceil(Number(res.result?.cooldownRemaining ?? 0) / 60)
        EventBus.emit('show-interaction', { message: `刚用过，还要等 ${s} 分钟` })
      } else {
        const msg = res.result?.message
          ?? (res.reason === 'object_full'
            ? `正在使用中（${res.result?.currentUsers}/${res.result?.maxUsers}）`
            : '无法使用')
        EventBus.emit('show-interaction', { message: msg })
      }
    } catch (err) { console.error('[Use Error]', err) }
  }

  private async handleLeave() {
    try {
      const res = await sendAction(this.entityId(), 'leave')
      if (res.success) EventBus.emit('show-interaction', { message: '已离开' })
      else if (res.reason === 'not_using_any_object') EventBus.emit('show-interaction', { message: '当前没有正在使用的对象' })
    } catch (err) { console.error('[Leave Error]', err) }
  }

  private adjustZoom(delta: number) {
    this.currentZoom = snapZoom(Phaser.Math.Clamp(this.currentZoom + delta, MIN_ZOOM, MAX_ZOOM))
    this.cameras.main.setZoom(this.currentZoom)
  }

  // ── 相机（旁观） ──────────────────────────────────────────────────────────────

  private updateSpectateCamera(time: number, dt: number) {
    const { players, playerVars } = useGameStore.getState()
    const target = resolveFollowTarget(players, this.params?.follow ?? null)
    const alive = !!target && target.online !== false && this.others.has(target.id)
    const newTargetId = alive ? target!.id : null
    if (newTargetId !== this.targetId) {
      this.targetId = newTargetId
      this.syncVars()
    }

    let wantFollow = false
    if (alive) { wantFollow = true; this.targetLostAt = 0 }
    else if (this.params?.follow) {
      if (this.targetLostAt === 0) this.targetLostAt = time
      wantFollow = time - this.targetLostAt < TARGET_LOSS_MS && this.camMode === 'follow'
    }

    const cam = this.cameras.main
    if (wantFollow && this.camMode !== 'follow') {
      this.camMode = 'follow'
      cam.zoomTo(this.followZoom, 700, 'Sine.easeInOut')
    } else if (!wantFollow && this.camMode !== 'pan') {
      this.camMode = 'pan'
      cam.zoomTo(this.panZoom, 900, 'Sine.easeInOut')
    }

    let tx = this.mapPx.w / 2, ty = this.mapPx.h / 2
    if (this.camMode === 'follow' && this.targetId) {
      const s = this.others.get(this.targetId)
      if (s) { const p = s.getPixelPosition(); tx = p.x; ty = p.y }
    }
    const k = 1 - Math.exp(-dt / CAMERA_LERP_MS)
    this.camX += (tx - this.camX) * k
    this.camY += (ty - this.camY) * k
    cam.centerOn(this.camX, this.camY)
    void playerVars
  }

  update(time: number, dt: number) {
    const store = useGameStore.getState()
    const speed = store.player?.moveSpeed ?? 1

    if (this.mode === 'play') {
      this.inputSystem?.update(time)
      this.self?.update(time, dt, speed)
      const p = this.self!.getPixelPosition()
      this.cameras.main.centerOn(p.x, p.y)
    } else {
      this.updateSpectateCamera(time, dt)
    }
    for (const s of this.others.values()) s.update(time, dt, 1)

    // 气泡
    if (time - this.lastPrune > 250) {
      this.lastPrune = time
      store.pruneBubbles(performance.now())
    }
    const bubbles = store.bubbles
    if (bubbles.length > 0 || this.hadBubbles) {
      const byId = new Map(bubbles.map(b => [b.entityId, b.content]))
      for (const [id, s] of this.others) s.setBubble(byId.get(id) ?? null)
      if (this.self && this.myPlayerId) this.self.setBubble(byId.get(this.myPlayerId) ?? null)
      this.hadBubbles = bubbles.length > 0
    }

    this.overlay.update(store.worldState)
    if (this.mode === 'spectate' && (this.params?.hud ?? true)) {
      this.overlay.setBadge(store.connection === 'offline' ? '后端连接中断，重连中…' : null)
    }

    if (time - this.statsAt > 1000) {
      this.statsAt = time
      const fps = this.game.loop.actualFps
      const stats = {
        fps: Math.round(fps * 10) / 10,
        actors: this.others.size + (this.self ? 1 : 0),
        inflight: this.inputSystem?.hasInflight() ? 1 : 0,
        connection: store.connection,
        camMode: this.camMode,
        target: this.targetId,
      }
      ;(window as unknown as { __whaleStats: typeof stats }).__whaleStats = stats
      EventBus.emit('stats', stats)
      this.statsText?.setText(`${stats.fps} fps · ${stats.actors} actors · ${stats.connection} · ${stats.camMode}${stats.target ? ' → ' + stats.target : ''}`)
    }
  }
  private hadBubbles = false
}

export { tileCenter }
