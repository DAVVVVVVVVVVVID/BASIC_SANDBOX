import Phaser from 'phaser'
import { WorldData, Player, WorldEvent, Position, OtherPlayer, Facing, Tile } from '../../types'
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
import { preloadAiAssets, getAiManifest, aiBackdropKey, aiEnabled, setAiTexturesLinear, type AiBackdrop } from '../aiAssets'
import { arenaBBox, isIndoor } from '../map/mapv2'

/** 自由镜头命令（React 控件 / 小地图 / 画布点击 → 场景） */
export type FreeCmd = { cmd: 'free' } | { cmd: 'world' } | { cmd: 'follow'; id: string } | { cmd: 'jump'; x: number; y: number } | { cmd: 'enter'; sector: string; floor: number } | { cmd: 'exit' }
import { itemMeta } from '../items'
import DecoLayer from '../systems/DecoLayer'

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

export { poseAnchorsFor, deriveStateLabel, iconize } from '../stateLabel'
import { deriveStateLabel, poseAnchorsFor } from '../stateLabel'

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
  private backdrops: { name: string; meta: AiBackdrop; img: Phaser.GameObjects.Image; shadow?: Phaser.GameObjects.Graphics }[] = []
  private debugWalls: Phaser.GameObjects.Graphics | null = null   // W9 0c：&debug=walls 叠层
  private debugTexts: Phaser.GameObjects.Text[] = []
  private deco: DecoLayer | null = null
  private roofedSectors = new Set<string>()
  private insideSector: string | null = null   // 当前取景进入的 sector（室内视图）
  private inputSystem: InputSystem | null = null
  private unsubs: (() => void)[] = []
  private busHandlers: [string, (...args: never[]) => void][] = []

  // 相机
  private camX = 0
  private camY = 0
  private currentZoom = 1
  private camMode: 'follow' | 'pan' | 'free' = 'follow'
  /** W9 任务 0 自由镜头 */
  private freeZoom = FOLLOW_ZOOM
  private drag: { x: number; y: number; moved: boolean } | null = null
  private keys: Record<string, Phaser.Input.Keyboard.Key> | null = null
  private lastCamEmit = 0
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
    setAiTexturesLinear(this)
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
      this.setupFreeCamera()
      if (this.params?.mode === 'free') this.enterFree()
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
      const me = { id: player.id, name: player.profile?.name ?? '', position: player.position, facing: player.facing, state: player.state, stateLabel: player.stateLabel, tags: player.tags, usingObjectId: player.usingObjectId }
      this.self?.setStateLabel(deriveStateLabel(me, useGameStore.getState().objects))
      this.self?.setPoseAnchors(poseAnchorsFor(me, useGameStore.getState().objects))
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
    this.on('action-event', (msg: import('../../types').WsAction) => {
      if (!msg.entity) return
      const push = (t: string, ms = 4000) => useGameStore.getState().pushBubble(msg.entity, t, ms)
      // §3.36（B 910506f）：无路统一 reason no_path，锁门 / 关门在 blocked_reason（人类单格 direction 仍直接 locked / closed）
      const ext = msg as unknown as { blocked_reason?: string; outcome?: string; result?: { blocked_reason?: string; opens_at?: string | null } ; opens_at?: string | null }
      const br = ext.blocked_reason ?? ext.result?.blocked_reason ?? msg.reason ?? ''
      if (/lock/i.test(br)) { push('咚咚咚……门锁着呢'); return }
      if (/^closed$/i.test(br)) { push(`🚪 还没开门${ext.opens_at ?? ext.result?.opens_at ? `（${ext.opens_at ?? ext.result?.opens_at} 开）` : ''}`); return }
      if ((msg.action ?? '') === 'move_done') {
        if (ext.outcome === 'blocked') push(br === 'no_path' ? '🚧 这边走不过去' : '🚧 被挡住了')
        return
      }
      if (!msg.success && msg.reason === 'walking') { push('🚶 还在走呢，先到地方再说'); return }
      // W9 任务 3：买 / 吃 / 送 / 卖的反馈气泡（字段 item / price / gold_delta / target_name 是假设，缺了就只说动作）
      const a = (msg.action ?? '').toLowerCase()
      // W11 新失败原因（use / buy）
      if (!msg.success && msg.reason) {
        const r = msg.reason
        if (r === 'empty') { push('🧊 冰箱空了……'); return }
        if (r === 'no_ingredients') { push('🥬 没有食材，做不了饭'); return }
        if (r === 'out_of_stock') { push('📦 卖完了'); return }
      }
      if (a === 'store' && msg.success) { push(`🧊 把${msg.item_name ?? itemMeta(msg.item ?? undefined).label}放进了冰箱`); return }
      if (!/^(buy|eat|give|sell|use_item)$/.test(a)) return
      const meta = itemMeta(msg.item ?? undefined, msg.item_name ?? undefined)
      const name = msg.item_name ?? meta.label
      const delta = typeof msg.gold_delta === 'number' ? msg.gold_delta : typeof msg.price === 'number' ? (a === 'sell' ? msg.price : -msg.price) : null
      const money = delta === null ? '' : ` ${delta > 0 ? '+' : ''}${delta} 金币`
      if (!msg.success) { push(/insufficient_funds|no_money|poor/i.test(msg.reason ?? '') ? `💸 钱不够，买不了${name}` : `✗ ${msg.reason ?? '没成功'}`); return }
      if (a === 'buy') push(`🛒 买了${meta.icon}${name}${money}`)
      else if (a === 'eat' || a === 'use_item') push(`${meta.icon} 吃了${name}`)
      else if (a === 'give') push(`🎁 把${name}送给了${msg.target_name ?? msg.target ?? '对方'}`)
      else if (a === 'sell') push(`💰 卖了${meta.icon}${name}${money}`)
    })
    // W11：产出与委托
    this.on('produce-event', (msg: import('../../types').WsProduce) => {
      if (!msg.entity) return
      const meta = itemMeta(msg.item ?? undefined, msg.item_name ?? undefined), name = msg.item_name ?? meta.label, n = msg.qty && msg.qty > 1 ? ` ×${msg.qty}` : ''
      const verb = msg.via === 'fishing' ? '🎣 钓到了' : msg.via === 'stove' ? '🍳 做好了' : msg.via === 'compose' ? '🎼 写完了' : msg.via === 'make_video' ? '🎬 做完了' : '✨ 得到了'
      useGameStore.getState().pushBubble(msg.entity, `${verb}${meta.icon}${name}${n}`, 5000)
    })
    this.on('commission-event', (msg: import('../../types').WsCommission) => {
      // 委托没有 entity 时挂在鲸仔（委托都是给她的）头上
      const whale = useGameStore.getState().players.find(p => /鲸|whale/.test(p.name))
      const who = msg.entity ?? whale?.id
      if (!who) return
      const title = msg.title ? `《${msg.title}》` : '一首歌', fee = typeof msg.fee === 'number' ? ` ${msg.fee} 金币` : ''
      useGameStore.getState().pushBubble(who, msg.event === 'deliver' ? `✅ 交付了${title}给${msg.client_name ?? '委托人'}${fee ? ` +${fee.trim()}` : ''}` : `📋 新委托：${msg.client_name ?? '有人'}想要${title}${fee}`, 6000)
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
      state: () => ({ camMode: this.camMode, focus: this.params?.focus ?? null, follow: this.params?.follow ?? null, keyboard: !!this.input.keyboard }),
      setFocus: (sector: string | null, floor = 1) => { if (this.params) this.params.focus = sector ? { sector, floor } : null },   // W9 任务 4 录屏：运行时切取景
      others: () => [...this.others.entries()].map(([id, s]) => ({ id, px: s.getPixelPosition(), tile: s.getTile(), moving: s.isMoving(), ...s.debugPose() })),
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
      if (!this.backdropFits(meta)) { console.debug('[ai] backdrop skipped (map layout differs):', name); continue }
      const tp = meta.tile_px || m.tile_px || 32
      const scale = TILE_SIZE / tp
      const mg = meta.margin ?? 1   // 版式导出时四周多带的地面格：裁掉，只贴建筑本体（setCrop 用纹理坐标，图仍从 x0,y0 起放）
      const img = this.add.image(meta.x0 * TILE_SIZE, meta.y0 * TILE_SIZE, key).setOrigin(0, 0).setScale(scale).setDepth(0.6)
      img.setCrop(mg * tp, mg * tp, (meta.w - 2 * mg) * tp, (meta.h - 2 * mg) * tp)
      let shadow: Phaser.GameObjects.Graphics | undefined
      if (meta.view === 'exterior') {
        // 建筑落地阴影（11-07 主播：整体不好看——建筑像浮着）：footprint 向右下偏一点的两层半透明圆角矩形
        const x = (meta.x0 + mg) * TILE_SIZE, y = (meta.y0 + mg) * TILE_SIZE, w = (meta.w - 2 * mg) * TILE_SIZE, h = (meta.h - 2 * mg) * TILE_SIZE
        shadow = this.add.graphics().setDepth(0.55)
        shadow.fillStyle(0x000000, 0.10).fillRoundedRect(x + 10, y + 16, w + 4, h + 4, 14)
        shadow.fillStyle(0x000000, 0.14).fillRoundedRect(x + 6, y + 10, w, h, 10)
      }
      this.backdrops.push({ name, meta, img, shadow })
      if (meta.view === 'exterior') this.roofedSectors.add(`${meta.sector}|${meta.floor}`)   // 键 = 区域|楼层：2F 单独一张外观（主播 11-07：2F 也画成房子）
    }
    this.applyView(this.insideSector, true)
    // 室内底图覆盖到的格：不再叠画像素楼梯图示
    const interiors = this.backdrops.filter(b => b.meta.view === 'interior')
    this.focus?.hideStairIcons((t) => interiors.some(b => t.x >= b.meta.x0 && t.x < b.meta.x0 + b.meta.w && t.y >= b.meta.y0 && t.y < b.meta.y0 + b.meta.h))
  }

  /**
   * W9 0c：`&debug=walls` 调试叠层——引擎的 wall 格（红）、门 / 楼梯格（黄 / 青）、室内相邻 arena 之间的墙上开口（绿，即室内门）、
   * 各 arena 边界（白虚线）、格线与每 5 格的坐标；画在所有东西之上（半透明），不随屋顶 / 室内视图切换。供核对 AI 底图与引擎格子的错位。
   */
  private drawDebugWalls() {
    this.debugWalls?.destroy(); this.debugWalls = null
    for (const t of this.debugTexts) t.destroy(); this.debugTexts = []
    if (this.params?.debug !== 'walls') return
    const g = this.add.graphics().setDepth(100000)
    const T = TILE_SIZE
    const idx = this.tileIndex
    const mapW = Math.round(this.mapPx.w / T), mapH = Math.round(this.mapPx.h / T)
    // 格线
    g.lineStyle(1, 0xffffff, 0.18)
    for (let x = 0; x <= mapW; x++) g.lineBetween(x * T, 0, x * T, mapH * T)
    for (let y = 0; y <= mapH; y++) g.lineBetween(0, y * T, mapW * T, y * T)
    g.lineStyle(1, 0xffffff, 0.4)
    for (let x = 0; x <= mapW; x += 5) g.lineBetween(x * T, 0, x * T, mapH * T)
    for (let y = 0; y <= mapH; y += 5) g.lineBetween(0, y * T, mapW * T, y * T)
    // 墙格 / arena 边界 / 室内开口
    for (const t of idx.values()) {
      const x = t.x * T, y = t.y * T
      if (t.type === 'wall') { g.fillStyle(0xff3030, 0.28).fillRect(x, y, T, T); g.lineStyle(1, 0xff3030, 0.6).strokeRect(x + 0.5, y + 0.5, T - 1, T - 1) }
      const n = [idx.get(`${t.x + 1},${t.y}`), idx.get(`${t.x},${t.y + 1}`)]
      g.lineStyle(2, 0xffffff, 0.55)
      if (n[0] && (n[0].arena ?? null) !== (t.arena ?? null)) g.lineBetween(x + T, y, x + T, y + T)
      if (n[1] && (n[1].arena ?? null) !== (t.arena ?? null)) g.lineBetween(x, y + T, x + T, y + T)
      // 室内开口：地板格，左右（或上下）都是墙、另一轴两侧是不同 arena 的非墙格
      if (t.type !== 'wall' && isIndoor(t)) {
        const L = idx.get(`${t.x - 1},${t.y}`), R = idx.get(`${t.x + 1},${t.y}`), U = idx.get(`${t.x},${t.y - 1}`), D = idx.get(`${t.x},${t.y + 1}`)
        const w = (q?: Tile) => q?.type === 'wall'
        const gapV = w(L) && w(R) && U && D && !w(U) && !w(D) && (U.arena ?? null) !== (D.arena ?? null)
        const gapH = w(U) && w(D) && L && R && !w(L) && !w(R) && (L.arena ?? null) !== (R.arena ?? null)
        if (gapV || gapH) { g.fillStyle(0x40ff80, 0.35).fillRect(x, y, T, T); g.lineStyle(2, 0x40ff80, 0.9).strokeRect(x + 1, y + 1, T - 2, T - 2) }
      }
    }
    // 门 / 楼梯格（edges）
    for (const e of this.focus?.edges() ?? []) {
      const col = e.type === 'stairs' ? 0x40e0ff : 0xffd040
      for (const p of e.tiles) { g.fillStyle(col, 0.35).fillRect(p.x * T, p.y * T, T, T); g.lineStyle(2, col, 0.95).strokeRect(p.x * T + 1, p.y * T + 1, T - 2, T - 2) }
    }
    // 坐标
    for (let x = 0; x < mapW; x += 5) for (let y = 0; y < mapH; y += 5) {
      this.debugTexts.push(this.add.text(x * T + 2, y * T + 1, `${x},${y}`, { fontFamily: 'monospace', fontSize: '9px', color: '#fff', stroke: '#000', strokeThickness: 2 }).setDepth(100001).setResolution(2).setAlpha(0.8))
    }
    this.debugWalls = g
  }

  /** 底图是照 8091 草图镇某一版地图画的：当前地图里该 sector / arena 同层的包围盒必须与 manifest 一致才贴（主镇 / 改图后自动跳过，不会贴错位） */
  private backdropFits(meta: AiBackdrop): boolean {
    const mg = meta.margin ?? 1
    const tiles = this.worldData.tiles.filter(t => (this.focus?.floorOf(t) ?? 1) === meta.floor)
    const b = arenaBBox(tiles, meta.sector) ?? arenaBBox(tiles, null, meta.sector)
    if (!b) return false
    return b.x0 - mg === meta.x0 && b.y0 - mg === meta.y0 && b.x1 - b.x0 + 1 + 2 * mg === meta.w && b.y1 - b.y0 + 1 + 2 * mg === meta.h
  }

  /** 两套视图：inside = 当前镜头进入的 sector（室内视图），其余有屋顶的 sector 显示屋顶、藏起屋内物品与人物 */
  private applyView(inside: string | null, force = false) {
    if (!force && inside === this.insideSector) return
    this.insideSector = inside
    for (const b of this.backdrops) {
      const hasPair = this.backdrops.some(o => o.meta.view === 'exterior' && o.meta.sector === b.meta.sector && o.meta.floor === b.meta.floor)
      if (!hasPair) { b.img.setVisible(true); continue }           // 同层没有外观图 → 常显
      const showInterior = `${b.meta.sector}|${b.meta.floor}` === inside
      b.img.setVisible(b.meta.view === 'interior' ? showInterior : !showInterior)
      b.shadow?.setVisible(!showInterior)
    }
    this.focus?.setRoofed((tile) => this.underRoof(tile))
    // 屋内物品：所在 sector 有屋顶且不是当前进入的 → 隐藏（只对 1F；2F 另有位置，照常）
    this.objectSprites.forEach((o, i) => {
      const t = this.tileIndex.get(`${this.objectTiles[i]?.x},${this.objectTiles[i]?.y}`)
      const k = this.roofKeyOf(t)
      o.setVisible(!(k && k !== inside))
    })
  }

  /** 该格属于哪张外观底图的建筑：manifest 的 backdrop.sector 既可能是 sector（home）也可能是 arena（classroom / library / music_room 都在 sector=university 里） */
  private roofKeyOf(t: Tile | undefined): string | null {
    if (!t) return null
    const f = this.focus?.floorOf(t) ?? 1
    if (t.sector && this.roofedSectors.has(`${t.sector}|${f}`)) return `${t.sector}|${f}`
    if (t.arena && this.roofedSectors.has(`${t.arena}|${f}`)) return `${t.arena}|${f}`
    return null
  }

  /** 镜头所在格对应的室内视图键（不在任何有屋顶的建筑里 → null，显示全部外观） */
  private insideKeyAt(tile: { x: number; y: number } | null | undefined): string | null {
    return tile ? this.roofKeyOf(this.tileIndex.get(`${tile.x},${tile.y}`)) : null
  }

  /** 人物是否被屋顶挡住 */
  private underRoof(tile: Position): boolean {
    const t = this.tileIndex.get(`${tile.x},${tile.y}`)
    const k = this.roofKeyOf(t)
    return !!k && k !== this.insideSector
  }

  /** W9 任务 4：进屋 / 出门 / 上下楼的过渡——快速压黑（140 ms），黑场里直接切 zoom 与视图，再亮起（260 ms）；上下楼多一个「2F ↑ / 1F ↓」提示。
   *  黑场期间不跑 zoomTo 渐变（两种动画叠着会抽），transition 结束后恢复正常跟随 */
  private transitioning = false
  private doorTransition(kind: 'enter' | 'exit' | 'floor' | 'move', zoom: number | null, label: string) {
    const cam = this.cameras.main
    if (this.transitioning) { if (zoom !== null) this.focusZoom = zoom; return }
    this.transitioning = true
    const outMs = kind === 'floor' ? 180 : 140, inMs = kind === 'floor' ? 320 : 260
    cam.fadeOut(outMs, 0, 0, 0)
    cam.once(Phaser.Cameras.Scene2D.Events.FADE_OUT_COMPLETE, () => {
      if (zoom !== null) { this.focusZoom = zoom; cam.setZoom(zoom) }
      cam.fadeIn(inMs, 0, 0, 0)
      if (kind === 'floor') {
        const t = this.add.text(cam.width / 2, cam.height / 2, label ? `${label} ↑` : '1F ↓', { fontFamily: 'system-ui, "PingFang SC", sans-serif', fontSize: '40px', color: '#ffffff', stroke: '#000000', strokeThickness: 6 })
          .setOrigin(0.5).setScrollFactor(0).setDepth(20000).setAlpha(0).setResolution(2)
        this.tweens.add({ targets: t, alpha: { from: 0, to: 1 }, y: cam.height / 2 - 30, duration: 300, yoyo: true, hold: 500, onComplete: () => t.destroy() })
      }
      cam.once(Phaser.Cameras.Scene2D.Events.FADE_IN_COMPLETE, () => { this.transitioning = false })
    })
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
    this.deco?.destroy()
    const decor = ((world as unknown as { decor?: unknown[] }).decor ?? (world.map as unknown as { decor?: unknown[] } | undefined)?.decor ?? []) as unknown[]
    this.deco = new DecoLayer(this, world.tiles, world.objects, this.focus?.doorTiles() ?? [], decor)
    this.tileIndex = buildTileIndex(world.tiles)
    if (!this.focus) this.focus = new SceneFocus(this, { enabled: (this.params?.scene ?? 'follow') === 'follow', baseZoom: () => this.mode === 'spectate' ? this.followZoom : this.currentZoom, snap: snapZoom })
    const extras = useGameStore.getState().mapExtras
    this.focus.setMap({ tiles: world.tiles, edges: world.edges ?? extras.edges, floors: world.floors ?? extras.floors, access: world.access ?? extras.access, arenas: world.arenas ?? extras.arenas, map: world.map ?? extras.map } as Parameters<SceneFocus['setMap']>[0], Math.round(this.mapPx.w / TILE_SIZE) || 1, Math.round(this.mapPx.h / TILE_SIZE) || 1)
    const { w, h } = mapSize(world.tiles, world.tiled)
    this.mapPx = { w: w * TILE_SIZE, h: h * TILE_SIZE }
    for (const obj of world.objects) { this.objectSprites.push(new GameObjectSprite(this, obj)); this.objectTiles.push({ ...obj.position }) }
    this.placeBackdrops()
    this.drawDebugWalls()

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
          // W9 任务 0b（§3.36）：服务器 1 格 / 游戏秒逐格推进，前端只续接相邻一格；跨 ≥ 2 格（瞬移 / 重生 / 漏 tick）直接贴齐，不再「先横后竖」猜路（会穿墙）
          const dist = Math.abs(end.x - op.position.x) + Math.abs(end.y - op.position.y)
          if (dist === 1) s.pushWaypoint(op.position)
          else s.snapTo(op.position, op.facing)
        }
        if (!s.isMoving()) s.setFacing(op.facing)
      }
      {
        const speed = useGameStore.getState().worldState?.speed || 1
        s.setStepMs(op.controller === 'human' ? 300 : 1000 / speed)
        s.setServerWalking(op.state === 'walking' || op.state === 'walking_over')
      }
      s.setDimmed(op.online === false)
      s.setStateLabel(deriveStateLabel(op, objects))
      s.setPoseAnchors(poseAnchorsFor(op, objects))
    }
    for (const [id, sprite] of this.others) {
      if (!seen.has(id)) { sprite.destroy(); this.others.delete(id) }
    }
    this.syncVars()
  }

  /** 从 from（不含）到 to 的网格路点：曼哈顿折线（先横后竖），不做寻路（后端已保证合法） */
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

  // ── 自由镜头（W9 任务 0）──────────────────────────────────────────────────────

  private setupFreeCamera() {
    const cam = this.cameras.main
    this.keys = this.input.keyboard?.addKeys('W,A,S,D,UP,DOWN,LEFT,RIGHT,ESC') as Record<string, Phaser.Input.Keyboard.Key> | null
    this.input.keyboard?.on('keydown-ESC', () => this.freeCmd({ cmd: 'exit' }))
    this.input.on('pointerdown', (p: Phaser.Input.Pointer) => { this.drag = { x: p.x, y: p.y, moved: false } })
    this.input.on('pointermove', (p: Phaser.Input.Pointer) => {
      if (!this.drag || !p.isDown) return
      const dx = p.x - this.drag.x, dy = p.y - this.drag.y
      if (!this.drag.moved && Math.hypot(dx, dy) < 5) return
      if (!this.drag.moved) { this.drag.moved = true; if (this.camMode !== 'free') this.enterFree() }
      this.camX -= dx / cam.zoom; this.camY -= dy / cam.zoom
      this.drag.x = p.x; this.drag.y = p.y
    })
    this.input.on('pointerup', (p: Phaser.Input.Pointer) => {
      const d = this.drag; this.drag = null
      if (!d || d.moved) return
      this.clickAt(p)
    })
    this.input.on('wheel', (p: Phaser.Input.Pointer, _o: unknown, _dx: number, deltaY: number) => {
      if (this.camMode !== 'free') this.enterFree()
      const before = cam.getWorldPoint(p.x, p.y)
      const z = snapZoom(Phaser.Math.Clamp(this.freeZoom + (deltaY > 0 ? -ZOOM_STEP : ZOOM_STEP), MIN_ZOOM, MAX_ZOOM))
      if (z === this.freeZoom) return
      this.freeZoom = z; cam.setZoom(z)
      const after = cam.getWorldPoint(p.x, p.y)
      this.camX += before.x - after.x; this.camY += before.y - after.y   // 以鼠标为中心缩放
      this.centerClamped(this.camX, this.camY)
    })
    this.on('spectate-cmd', (c: FreeCmd) => this.freeCmd(c))
  }

  /** 切到自由镜头：保留当前镜头中心与 zoom */
  private enterFree() {
    const cam = this.cameras.main
    this.camX = cam.midPoint.x; this.camY = cam.midPoint.y
    this.freeZoom = snapZoom(Phaser.Math.Clamp(cam.zoom, MIN_ZOOM, MAX_ZOOM))
    cam.setZoom(this.freeZoom)
    this.camMode = 'free'
    if (this.params) this.params.follow = null
    this.targetId = null; this.lastTargetPx = null; this.focusZoom = null
    this.syncVars(); this.emitSpectateState()
  }

  private freeCmd(c: FreeCmd) {
    if (!this.params) return
    const cam = this.cameras.main
    switch (c.cmd) {
      case 'free': this.enterFree(); this.params.focus = null; break
      case 'world': this.params.follow = null; this.params.focus = null; this.camMode = 'pan'; this.focusZoom = null; cam.zoomTo(this.panZoom, 600, 'Sine.easeInOut', true); break
      case 'follow': this.params.focus = null; this.params.follow = c.id; this.camMode = 'follow'; this.focusZoom = this.followZoom; cam.zoomTo(this.followZoom, 500, 'Sine.easeInOut', true); break
      case 'jump': if (this.camMode !== 'free') this.enterFree(); this.camX = (c.x + 0.5) * TILE_SIZE; this.camY = (c.y + 0.5) * TILE_SIZE; this.params.focus = null; break
      case 'enter': if (this.camMode !== 'free') this.enterFree(); this.params.focus = { sector: c.sector, floor: c.floor }; break
      case 'exit':
        if (this.params.focus) { this.params.focus = null; if (this.camMode !== 'free') this.enterFree() }
        else if (this.camMode === 'follow') this.enterFree()
        break
    }
    this.emitSpectateState()
  }

  /** 点一下：点到人 → 跟随；点到室内格 → 进那栋楼（含 2F）；在屋里点屋外 → 回小镇 */
  private clickAt(p: Phaser.Input.Pointer) {
    if (this.mode !== 'spectate') return
    const w = this.cameras.main.getWorldPoint(p.x, p.y)
    for (const [id, s] of this.others) { if (s.containsPoint(w.x, w.y)) { this.freeCmd({ cmd: 'follow', id }); return } }
    const tx = Math.floor(w.x / TILE_SIZE), ty = Math.floor(w.y / TILE_SIZE)
    const t = this.tileIndex.get(`${tx},${ty}`)
    if (t && isIndoor(t) && t.sector) {
      const floor = this.focus?.floorOf(t) ?? 1
      const cur = this.params?.focus
      if (cur && cur.sector === t.sector && cur.floor === floor) return
      this.freeCmd({ cmd: 'enter', sector: t.sector, floor })
    } else if (this.params?.focus) {
      this.freeCmd({ cmd: 'exit' })
    }
  }

  private emitSpectateState() {
    EventBus.emit('spectate-state', { mode: this.camMode === 'pan' ? 'world' : this.camMode, follow: this.params?.follow ?? null, focus: this.params?.focus ?? null })
  }

  private updateFreeCamera(dt: number) {
    const cam = this.cameras.main
    // WASD / 方向键平移（屏幕像素速度恒定）
    if (this.keys) {
      const v = 900 / cam.zoom * dt / 1000
      if (this.keys.W?.isDown || this.keys.UP?.isDown) this.camY -= v
      if (this.keys.S?.isDown || this.keys.DOWN?.isDown) this.camY += v
      if (this.keys.A?.isDown || this.keys.LEFT?.isDown) this.camX -= v
      if (this.keys.D?.isDown || this.keys.RIGHT?.isDown) this.camX += v
    }
    let focusTile: Position | null = null
    if (this.params?.focus) {
      const c = this.focus.sectorCenter(this.params.focus.sector, this.params.focus.floor)
      if (c) focusTile = c
    }
    const fr = this.focus.update(focusTile, dt, useGameStore.getState().worldState)
    this.applyView(fr.indoor ? this.insideKeyAt(focusTile) : null)
    if (fr.indoor && focusTile) {
      const want = fr.zoom ?? this.freeZoom
      if (fr.transition) { this.doorTransition(fr.transition, want, fr.label); this.camX = (focusTile.x + 0.5) * TILE_SIZE; this.camY = (focusTile.y + 0.5) * TILE_SIZE }
      else if (want !== this.focusZoom && !this.transitioning) { this.focusZoom = want; cam.zoomTo(want, ZOOM_MS, 'Sine.easeInOut', true) }
      const c0 = this.focus.clampCenter(this.camX, this.camY, cam.zoom)
      this.camX = c0.x; this.camY = c0.y
      this.centerClamped(c0.x, c0.y)
    } else {
      if (fr.transition) this.doorTransition(fr.transition, this.freeZoom, fr.label)
      else if (!this.transitioning && Math.abs(cam.zoom - this.freeZoom) > 1e-4 && this.focusZoom !== this.freeZoom) { this.focusZoom = this.freeZoom; cam.zoomTo(this.freeZoom, 200, 'Sine.easeInOut', true) }
      this.centerClamped(this.camX, this.camY)
      // clamp 后把中心写回，免得按住键一直往外推
      this.camX = cam.midPoint.x; this.camY = cam.midPoint.y
    }
    const now = performance.now()
    if (now - this.lastCamEmit > 120) {
      this.lastCamEmit = now
      const vw = cam.width / cam.zoom / TILE_SIZE, vh = cam.height / cam.zoom / TILE_SIZE
      EventBus.emit('spectate-camera', { x0: cam.midPoint.x / TILE_SIZE - vw / 2, y0: cam.midPoint.y / TILE_SIZE - vh / 2, x1: cam.midPoint.x / TILE_SIZE + vw / 2, y1: cam.midPoint.y / TILE_SIZE + vh / 2 })
    }
  }

  private updateSpectateCamera(time: number, dt: number) {
    if (this.camMode === 'free') { this.updateFreeCamera(dt); return }
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
    this.applyView(fr.indoor ? this.insideKeyAt(focusTile) : null)
    if (this.params?.focus && !this.targetId && focusTile) {
      const want = fr.indoor && fr.zoom ? fr.zoom : this.followZoom
      if (fr.transition) this.doorTransition(fr.transition, want, fr.label)
      else if (want !== this.focusZoom && !this.transitioning) { this.focusZoom = want; cam.zoomTo(want, ZOOM_MS, 'Sine.easeInOut', true) }
      const k0 = 1 - Math.exp(-dt / CAMERA_LERP_MS)
      this.camX += (tx - this.camX) * k0; this.camY += (ty - this.camY) * k0
      const c0 = this.focus.clampCenter(this.camX, this.camY, cam.zoom)
      this.centerClamped(c0.x, c0.y)
      return
    }
    if (this.camMode === 'follow') {
      const want = fr.indoor && fr.zoom ? fr.zoom : this.followZoom
      if (fr.transition) this.doorTransition(fr.transition, want, fr.label)
      else if (want !== this.focusZoom && !this.transitioning) { this.focusZoom = want; cam.zoomTo(want, ZOOM_MS, 'Sine.easeInOut', true) }
      if (fr.indoor !== this.lastFocusIndoor) { this.lastFocusIndoor = fr.indoor; EventBus.emit('focus-changed', { indoor: fr.indoor, label: fr.label }) }
    }
    const k = 1 - Math.exp(-dt / CAMERA_LERP_MS)
    this.camX += (tx - this.camX) * k
    this.camY += (ty - this.camY) * k
    const c = fr.indoor ? this.focus.clampCenter(this.camX, this.camY, cam.zoom) : { x: this.camX, y: this.camY }
    this.centerClamped(c.x, c.y)
    void playerVars
    const now = performance.now()
    if (now - this.lastCamEmit > 120) {
      this.lastCamEmit = now
      const vw = cam.width / cam.zoom / TILE_SIZE, vh = cam.height / cam.zoom / TILE_SIZE
      EventBus.emit('spectate-camera', { x0: cam.midPoint.x / TILE_SIZE - vw / 2, y0: cam.midPoint.y / TILE_SIZE - vh / 2, x1: cam.midPoint.x / TILE_SIZE + vw / 2, y1: cam.midPoint.y / TILE_SIZE + vh / 2 })
    }
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
      this.applyView(fr0.indoor ? this.insideKeyAt(st0) : null)
      if (fr0.transition) this.doorTransition(fr0.transition, null, fr0.label)
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
