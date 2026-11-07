import Phaser from 'phaser'
import { WorldData, Player, WorldEvent, Position, OtherPlayer, GameObject, Facing } from '../../types'
import TileMap, { preloadTileAssets, TILE_SIZE, SOURCE_TILE, mapSize, tileCenter } from '../map/TileMap'
import PlayerSprite from '../objects/Player'
import OtherPlayerSprite from '../objects/OtherPlayerSprite'
import GameObjectSprite from '../objects/GameObjectSprite'
import InputSystem from '../systems/InputSystem'
import { EventBus } from '../EventBus'
import { sendAction } from '../../api/world'
import { useGameStore } from '../../store/gameStore'
import { resolveFollowTarget } from '../systems/TickSystem'
import type { SpectateParams } from '../../spectate/params'
import { preloadGenAssets, createGenAnimations, charKeyFor } from '../assets'
import { buildTileIndex, zoneLabel } from '../map/zones'
import SceneFocus, { ZOOM_MS } from '../systems/SceneFocus'
import { preloadAiAssets, getAiManifest, aiBackdropKey, aiEnabled, type AiBackdrop } from '../aiAssets'

export interface SceneInitData {
  mode: 'play' | 'spectate'
  worldData: WorldData
  events: WorldEvent[]
  player?: Player
  myPlayerId?: string
  spectate?: SpectateParams
  /** 操控模式：登录框里输入的名字（/player/{id} 不带 name） */
  playerName?: string
}

const MIN_ZOOM = 1 / 6
const MAX_ZOOM = 2.0
const ZOOM_STEP = 1 / 6
/** 跟随镜头默认 zoom：96 × 2/3 = 64 px/格 = 4× 源像素 */
const FOLLOW_ZOOM = 2 / 3
/** 目标消失 / 离线多久后退到全景（ms）。agent 的 online=false 本身就有后端 10 s 心跳延迟 */
const TARGET_LOSS_MS = 500
const CAMERA_LERP_MS = 140

/** 把 zoom 吸附到 1/6 的整数倍（源像素整数缩放）。用户参数取最近值（0.3333 → 2/6），自适应全景向下取整（保证整图放得下） */
function snapZoom(z: number, mode: 'round' | 'floor' = 'round'): number {
  const steps = TILE_SIZE / SOURCE_TILE
  const k = Math.max(1, mode === 'floor' ? Math.floor(z * steps + 1e-6) : Math.round(z * steps))
  return k / steps
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

const LABEL_ICON: [RegExp, string][] = [
  [/睡|sleep/i, '💤'], [/吃|饭|eat|food/i, '🍴'], [/直播|stream/i, '📺'], [/聊|talk|chat/i, '💬'], [/洗|bath|shower/i, '🛁'],
  [/钓|fish/i, '🎣'], [/看书|读|read|book/i, '📖'], [/手机|phone|刷/i, '📱'], [/休息|坐|rest|sit/i, '🛋'], [/工作|desk|work|写/i, '🖥'],
]

/** 后端给的 stateLabel（W5 起 players[] 自带）前面配一个图标 */
export function iconize(label: string): string {
  if (/^\p{Extended_Pictographic}/u.test(label)) return label
  for (const [re, ic] of LABEL_ICON) if (re.test(label)) return `${ic} ${label}`
  return label
}

/** 别人正在干什么：优先后端 `stateLabel` / `tags`（W5），老后端退回 objects.userList 反查推断 */
export function deriveStateLabel(p: OtherPlayer, objects: GameObject[], tagsHint?: string[]): string | null {
  if (p.online === false) return '💤 离线'
  const tags = (tagsHint ?? []).concat(p.tags ?? [])
  if (tags.includes('sleeping')) return '💤 睡觉中'
  if (tags.includes('eating'))   return '🍴 吃饭中'
  if (tags.includes('streaming')) return '📺 直播中'
  if (p.stateLabel) return iconize(p.stateLabel)
  if (p.state === 'talking') return '💬 聊天中'
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
  private playerName: string | null = null

  private tileMap!: TileMap
  private focus!: SceneFocus
  private focusZoom: number | null = null
  private lastFocusIndoor = false
  private self: PlayerSprite | null = null
  private others: Map<string, OtherPlayerSprite> = new Map()
  private objectSprites: GameObjectSprite[] = []
  private objectTiles: Position[] = []
  /** W8 底图：name → image；roofed sectors = 有 exterior 底图的 sector */
  private backdrops: { name: string; meta: AiBackdrop; img: Phaser.GameObjects.Image }[] = []
  private roofedSectors = new Set<string>()
  private insideSector: string | null = null   // 当前取景进入的 sector（室内视图）
  private inputSystem: InputSystem | null = null
  private unsubs: (() => void)[] = []
  private busHandlers: [string, (...args: never[]) => void][] = []

  // 相机
  private camX = 0
  private camY = 0
  private currentZoom = 1
  private camMode: 'follow' | 'pan' = 'follow'
  private targetId: string | null = null
  private targetLostAt = 0
  private lastTargetPx: { x: number; y: number } | null = null
  private panZoom = MIN_ZOOM
  private followZoom = FOLLOW_ZOOM
  private mapPx = { w: 0, h: 0 }

  // 统计
  private statsAt = 0
  private tileIndex = new Map<string, import('../../types').Tile>()
  private lastZone = ''
  private lastUiScale = 0
  private lastPrune = 0

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
    this.playerName  = data.playerName ?? null
  }

  preload() {
    preloadGenAssets(this)
    preloadAiAssets(this)
    preloadTileAssets(this, this.worldData.tiled)
    for (const obj of this.worldData.objects) {
      if (obj.sprite && !this.textures.exists(`obj_${obj.sprite}`)) {
        this.load.image(`obj_${obj.sprite}`, `assets/sprites/${obj.sprite}.png`)
      }
    }
  }

  create() {
    createGenAnimations(this)
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

    // ── store 订阅 ──
    this.syncOthers(useGameStore.getState().players)
    this.unsubs.push(useGameStore.subscribe((s, prev) => {
      if (s.players !== prev.players || s.objects !== prev.objects) this.syncOthers(s.players)
      if (s.mapVersion !== prev.mapVersion && s.tiles.length > 0) {
        // 地图换了（B16 新地图 / 后端换版本 / 重启）：重建背景与物品
        this.worldData = { ...this.worldData, tiles: s.tiles, tiled: s.tiled ?? undefined, objects: s.objects }
        this.inputSystem?.setTiles(s.tiles)
        this.rebuildMap()
      }
      if (s.playerVars !== prev.playerVars) this.syncVars()
      if (s.myPlayerId !== prev.myPlayerId && s.myPlayerId && this.mode === 'play') {
        this.myPlayerId = s.myPlayerId
        this.inputSystem?.setPlayerId(s.myPlayerId)
      }
    }))

    this.on('player-snapshot', ({ player, sentAt }: { player: Player; sentAt: number }) => {
      this.player = player
      this.inputSystem?.applyServerSnapshot(player.position, player.facing, sentAt)
      this.inputSystem?.setEnabled(true)
      this.self?.setStateLabel(deriveStateLabel(
        { id: player.id, name: player.profile?.name ?? '', position: player.position, facing: player.facing, state: player.state, stateLabel: player.stateLabel, tags: player.tags, usingObjectId: player.usingObjectId },
        useGameStore.getState().objects))
    })
    this.on('player-rejoined', ({ player }: { playerId: string; player: Player }) => {
      this.player = player
      this.self?.snapTo(player.position, player.facing)
      this.inputSystem?.reset(player.position, player.facing)
    })
    window.addEventListener('whale-walk-to', (e) => EventBus.emit('walk-to', (e as CustomEvent).detail))
    this.on('walk-to', ({ x, y }: { x: number; y: number }) => {
      const n = this.inputSystem?.walkToAdjacent({ x, y }) ?? 0
      EventBus.emit('walk-to-result', { steps: n })
    })
    this.on('action-event', (msg: { entity?: string; action?: string; success?: boolean; reason?: string | null; object?: string | null }) => {
      if (msg.reason && /lock/i.test(msg.reason) && msg.entity) {
        useGameStore.getState().pushBubble(msg.entity, '咚咚咚……门锁着呢', 4000)
      }
    })
    this.on('chat-message', ({ entityId, content }: { entityId: string; content: string }) => {
      useGameStore.getState().pushBubble(entityId, content)
    })

    // 调试 / 自动化测量用（Playwright 读）：自己的像素位置、在途请求数
    ;(window as unknown as { __whaleDebug: unknown }).__whaleDebug = {
      selfPixel: () => this.self?.getPixelPosition() ?? null,
      selfTile: () => this.self?.getTile() ?? null,
      inflight: () => this.inputSystem?.hasInflight() ?? false,
      keys: () => this.inputSystem?.debugKeys() ?? null,
      focusLabels: () => this.focus?.debugLabels() ?? [],
      zoom: () => this.cameras.main.zoom,
      others: () => [...this.others.entries()].map(([id, s]) => ({ id, px: s.getPixelPosition(), tile: s.getTile(), moving: s.isMoving() })),
    }

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
    this.focus?.destroy()
    this.tileMap?.destroy()
  }

  // ── 地图 ─────────────────────────────────────────────────────────────────────

  /** W8：按 manifest 放 AI 底图（32 px/格 → ×3），exterior 默认显示、interior 进入该屋时显示；2F 室内（没有 exterior 的）常显 */
  private placeBackdrops() {
    const m = getAiManifest()
    if (!m || !aiEnabled()) return
    for (const [name, meta] of Object.entries(m.backdrops)) {
      const key = aiBackdropKey(name)
      if (!this.textures.exists(key)) continue
      const scale = TILE_SIZE / (meta.tile_px || m.tile_px || 32)
      const img = this.add.image(meta.x0 * TILE_SIZE, meta.y0 * TILE_SIZE, key).setOrigin(0, 0).setScale(scale).setDepth(0.6)
      this.backdrops.push({ name, meta, img })
      if (meta.view === 'exterior') this.roofedSectors.add(meta.sector)
    }
    this.applyView(this.insideSector, true)
  }

  /** 两套视图：inside = 当前镜头进入的 sector（室内视图），其余有屋顶的 sector 显示屋顶、藏起屋内物品与人物 */
  private applyView(inside: string | null, force = false) {
    if (!force && inside === this.insideSector) return
    this.insideSector = inside
    for (const b of this.backdrops) {
      const hasPair = this.roofedSectors.has(b.meta.sector)
      if (!hasPair) { b.img.setVisible(true); continue }           // 只有一张（如 2F 室内）→ 常显
      const showInterior = b.meta.sector === inside
      b.img.setVisible(b.meta.view === 'interior' ? showInterior : !showInterior)
    }
    // 屋内物品：所在 sector 有屋顶且不是当前进入的 → 隐藏（只对 1F；2F 另有位置，照常）
    this.objectSprites.forEach((o, i) => {
      const t = this.tileIndex.get(`${this.objectTiles[i]?.x},${this.objectTiles[i]?.y}`)
      const roofed = !!t?.sector && this.roofedSectors.has(t.sector) && t.sector !== inside && (this.focus?.floorOf(t) ?? 1) === 1
      o.setVisible(!roofed)
    })
  }

  /** 人物是否被屋顶挡住 */
  private underRoof(tile: Position): boolean {
    const t = this.tileIndex.get(`${tile.x},${tile.y}`)
    return !!t?.sector && this.roofedSectors.has(t.sector) && t.sector !== this.insideSector && (this.focus?.floorOf(t) ?? 1) === 1
  }

  /** 运行中换图：新 tileset 可能还没加载，先加载再重建 */
  private rebuildMap() {
    const world = this.worldData
    const missing = (world.tiled?.tilesets ?? []).filter(ts => !this.textures.exists(ts.imageSource))
    const missingObj = world.objects.filter(o => o.sprite && !this.textures.exists(`obj_${o.sprite}`))
    if (missing.length === 0 && missingObj.length === 0) { this.buildMap(world); return }
    preloadTileAssets(this, world.tiled)
    for (const o of missingObj) this.load.image(`obj_${o.sprite}`, `assets/sprites/${o.sprite}.png`)
    this.load.once(Phaser.Loader.Events.COMPLETE, () => this.buildMap(world))
    this.load.start()
  }

  private buildMap(world: WorldData) {
    this.tileMap?.destroy()
    for (const o of this.objectSprites) o.destroy()
    this.objectSprites = []
    this.objectTiles = []
    for (const b of this.backdrops) b.img.destroy()
    this.backdrops = []
    this.roofedSectors.clear()
    this.tileMap = new TileMap(this, world.tiles, world.tiled)
    this.tileMap.render()
    this.tileIndex = buildTileIndex(world.tiles)
    if (!this.focus) this.focus = new SceneFocus(this, { enabled: (this.params?.scene ?? 'follow') === 'follow', baseZoom: () => this.mode === 'spectate' ? this.followZoom : this.currentZoom, snap: snapZoom })
    const extras = useGameStore.getState().mapExtras
    this.focus.setMap({ tiles: world.tiles, edges: world.edges ?? extras.edges, floors: world.floors ?? extras.floors, access: world.access ?? extras.access, arenas: world.arenas ?? extras.arenas, map: world.map ?? extras.map } as Parameters<SceneFocus['setMap']>[0], Math.round(this.mapPx.w / TILE_SIZE) || 1, Math.round(this.mapPx.h / TILE_SIZE) || 1)
    const { w, h } = mapSize(world.tiles, world.tiled)
    this.mapPx = { w: w * TILE_SIZE, h: h * TILE_SIZE }
    for (const obj of world.objects) { this.objectSprites.push(new GameObjectSprite(this, obj)); this.objectTiles.push({ ...obj.position }) }
    this.placeBackdrops()

    const cam = this.cameras.main
    // 全景 zoom：整张图放进画面，吸附到 1/6 的整数倍
    const fit = Math.min(cam.width / this.mapPx.w, cam.height / this.mapPx.h)
    this.panZoom = this.params?.panzoom ? snapZoom(this.params.panzoom) : Math.max(MIN_ZOOM, snapZoom(fit, 'floor'))
    if (this.mode === 'spectate' && this.camMode === 'pan') cam.setZoom(this.panZoom)
  }

  // ── 自己 ─────────────────────────────────────────────────────────────────────

  private createSelf(player: Player) {
    const selfName = this.playerName ?? player.profile?.name ?? player.id
    this.self = new PlayerSprite(this, player.position, player.facing, selfName, charKeyFor(selfName, 'human'))
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
          ;(window as unknown as { __whaleTrace: unknown[] }).__whaleTrace?.push({ t: Math.round(performance.now()), ev: 'reconcile', pos: `${pos.x},${pos.y}`, end: `${end.x},${end.y}`, bounced, tile: `${this.self!.getTile().x},${this.self!.getTile().y}` })
          if (end.x === pos.x && end.y === pos.y) return
          const cur = this.self!.getTile()
          const far = Math.abs(cur.x - pos.x) + Math.abs(cur.y - pos.y) > 3
          if (far && !bounced) this.self!.snapTo(pos)   // 被服务器挪远了（teleport）直接贴过去
          else this.self!.setPath([pos], true)           // 回弹 / 小校正：平滑走回，朝向以服务器为准
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
        s = new OtherPlayerSprite(this, op.position, op.facing, op.name, charKeyFor(op.name, op.controller))
        this.others.set(op.id, s)
      } else {
        const end = s.getPathEnd()
        if (end.x !== op.position.x || end.y !== op.position.y) {
          const cur = s.getTile()
          const dist = Math.abs(cur.x - op.position.x) + Math.abs(cur.y - op.position.y)
          if (dist > 12) s.snapTo(op.position, op.facing)                       // 瞬移 / 重生：直接贴
          else for (const p of this.pathBetween(end, op.position)) s.pushWaypoint(p)  // 在现有路径末端续接
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

  /** 从 from（不含）到 to 的网格路点：曼哈顿折线（先横后竖），不做寻路（后端已保证合法） */
  private pathBetween(from: Position, to: Position): Position[] {
    const pts: Position[] = []
    let x = from.x, y = from.y
    while (x !== to.x) { x += Math.sign(to.x - x); pts.push({ x, y }) }
    while (y !== to.y) { y += Math.sign(to.y - y); pts.push({ x, y }) }
    return pts
  }

  private syncVars() {
    const { playerVars } = useGameStore.getState()
    // 有信息面板时跟随目标的数值在面板里，头顶不再重复画小条；bars=all 仍画全员
    let bars = this.params?.bars ?? 'none'
    if (bars === 'target' && (this.params?.panel ?? true)) bars = 'none'
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
      this.focusZoom = this.followZoom
      cam.zoomTo(this.followZoom, 700, 'Sine.easeInOut', true)
    } else if (!wantFollow && this.camMode !== 'pan') {
      this.camMode = 'pan'
      this.focusZoom = null
      cam.zoomTo(this.panZoom, 900, 'Sine.easeInOut', true)
    }

    let tx = this.mapPx.w / 2, ty = this.mapPx.h / 2
    let focusTile: Position | null = null
    if (this.camMode === 'follow') {
      const s = this.targetId ? this.others.get(this.targetId) : null
      if (s) { this.lastTargetPx = s.getPixelPosition(); focusTile = s.getTile() }
      // 目标刚消失的宽限期里停在它最后的位置，不要先滑向地图中心
      if (this.lastTargetPx) { tx = this.lastTargetPx.x; ty = this.lastTargetPx.y }
    }
    // &focus=<sector>[:floor]：不跟人，直接取景到该场所（评审截图）
    if (!focusTile && this.params?.focus) {
      const c = this.focus.sectorCenter(this.params.focus.sector, this.params.focus.floor)
      if (c) { focusTile = c; tx = c.x * TILE_SIZE + TILE_SIZE / 2; ty = c.y * TILE_SIZE + TILE_SIZE / 2 }
    }
    // W7 取景：进屋推近 + 屋外压暗
    const fr = this.focus.update(focusTile, dt, useGameStore.getState().worldState)
    this.applyView(fr.indoor && focusTile ? (this.tileIndex.get(`${focusTile.x},${focusTile.y}`)?.sector ?? null) : null)
    if (this.params?.focus && !this.targetId && focusTile) {
      const want = fr.indoor && fr.zoom ? fr.zoom : this.followZoom
      if (want !== this.focusZoom) { this.focusZoom = want; cam.zoomTo(want, ZOOM_MS, 'Sine.easeInOut', true) }
      const k0 = 1 - Math.exp(-dt / CAMERA_LERP_MS)
      this.camX += (tx - this.camX) * k0; this.camY += (ty - this.camY) * k0
      const c0 = this.focus.clampCenter(this.camX, this.camY, cam.zoom)
      this.centerClamped(c0.x, c0.y)
      return
    }
    if (this.camMode === 'follow') {
      const want = fr.indoor && fr.zoom ? fr.zoom : this.followZoom
      if (want !== this.focusZoom) { this.focusZoom = want; cam.zoomTo(want, ZOOM_MS, 'Sine.easeInOut', true) }
      if (fr.indoor !== this.lastFocusIndoor) { this.lastFocusIndoor = fr.indoor; EventBus.emit('focus-changed', { indoor: fr.indoor, label: fr.label }) }
    }
    const k = 1 - Math.exp(-dt / CAMERA_LERP_MS)
    this.camX += (tx - this.camX) * k
    this.camY += (ty - this.camY) * k
    const c = fr.indoor ? this.focus.clampCenter(this.camX, this.camY, cam.zoom) : { x: this.camX, y: this.camY }
    this.centerClamped(c.x, c.y)
    void playerVars
  }

  /** 居中到 (x, y)，但视野比地图小时不露出地图外的黑边；比地图大时居中整张图 */
  private centerClamped(x: number, y: number) {
    const cam = this.cameras.main
    const vw = cam.width / cam.zoom
    const vh = cam.height / cam.zoom
    const cx = vw >= this.mapPx.w ? this.mapPx.w / 2 : Phaser.Math.Clamp(x, vw / 2, this.mapPx.w - vw / 2)
    const cy = vh >= this.mapPx.h ? this.mapPx.h / 2 : Phaser.Math.Clamp(y, vh / 2, this.mapPx.h - vh / 2)
    cam.centerOn(cx, cy)
  }

  update(time: number, dt: number) {
    const store = useGameStore.getState()
    const speed = store.player?.moveSpeed ?? 1

    if (this.mode === 'play') {
      this.inputSystem?.update(time)
      this.self?.update(time, dt, speed)
      const p = this.self!.getPixelPosition()
      const fr0 = this.focus.update(this.self!.getTile(), dt, store.worldState)
      const st0 = this.self!.getTile()
      this.applyView(fr0.indoor ? (this.tileIndex.get(`${st0.x},${st0.y}`)?.sector ?? null) : null)
      this.centerClamped(p.x, p.y)
    } else {
      this.updateSpectateCamera(time, dt)
    }
    for (const s of this.others.values()) { s.update(time, dt, 1); if (this.roofedSectors.size) s.setHidden(this.underRoof(s.getTile())) }
    if (this.self && this.roofedSectors.size) this.self.setHidden(this.underRoof(this.self.getTile()))

    // 标签 / 气泡在屏幕上恒定大小
    const ui = Phaser.Math.Clamp(1 / this.cameras.main.zoom, 1, 6)
    if (Math.abs(ui - this.lastUiScale) > 1e-3) {
      this.lastUiScale = ui
      this.self?.setUiScale(ui)
      for (const s of this.others.values()) s.setUiScale(ui)
    }

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

    // 区域名（跟随目标 / 自己所在格）
    const focus = this.mode === 'play' ? this.self?.getTile() : (this.targetId ? this.others.get(this.targetId)?.getTile() : null)
    if (focus) {
      const t = this.tileIndex.get(`${focus.x},${focus.y}`)
      const fl = this.focus?.hasV2 ? this.focus.floorOf(t) : 1
      const z = zoneLabel(t) + (fl > 1 ? ` · ${fl}F` : '')
      if (z && z !== this.lastZone) { this.lastZone = z; EventBus.emit('zone-changed', { label: z, sector: t?.sector, arena: t?.arena }) }
    }

    if (time - this.statsAt > 1000) {
      this.statsAt = time
      const fps = this.game.loop.actualFps
      const stats = {
        fps: Math.round(fps * 10) / 10,
        actors: this.others.size + (this.self ? 1 : 0),
        inflight: this.inputSystem?.hasInflight() ? 1 : 0,
        connection: store.connection,
        transport: store.transport,
        camMode: this.camMode,
        target: this.targetId,
      }
      ;(window as unknown as { __whaleStats: typeof stats }).__whaleStats = stats
      EventBus.emit('stats', stats)
    }
  }
  private hadBubbles = false
}

export { tileCenter }
