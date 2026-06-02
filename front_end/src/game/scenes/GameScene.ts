import Phaser from 'phaser'
import { WorldData, Player, WorldEvent, Position, OtherPlayer } from '../../types'
import TileMap, { preloadTileAssets, TILE_SIZE } from '../map/TileMap'
import PlayerSprite from '../objects/Player'
import OtherPlayerSprite from '../objects/OtherPlayerSprite'
import GameObjectSprite from '../objects/GameObjectSprite'
import InputSystem, { MoveResult, Direction, DELTAS, bfs, getMoveInterval } from '../systems/InputSystem'
import { EventBus } from '../EventBus'
import { sendAction } from '../../api/world'
import { useGameStore } from '../../store/gameStore'

interface SceneInitData {
  worldData: WorldData
  player: Player
  myPlayerId: string
  events: WorldEvent[]
}

const MIN_ZOOM = 0.3
const MAX_ZOOM = 2.0
const ZOOM_STEP = 0.1

export default class GameScene extends Phaser.Scene {
  private worldData!: WorldData
  private player!: Player
  private myPlayerId!: string
  private worldEvents!: WorldEvent[]
  private playerSprite!: PlayerSprite
  private otherSprites: Map<string, OtherPlayerSprite> = new Map()
  private inputSystem!: InputSystem
  private storeUnsub!: () => void
  private otherUnsub!: () => void
  // tracks the sprite's current tile (updated by both player input and external animation)
  private spritePos!: Position
  // target of an in-progress external animation; null when idle
  private animTarget: Position | null = null
  private isExternalAnim = false
  private currentZoom = 1.0

  constructor() {
    super({ key: 'GameScene' })
  }

  preload() {
    preloadTileAssets(this, this.worldData.tiled)
    this.load.spritesheet('player_walk', 'assets/sprites/player_walk.png', { frameWidth: 96, frameHeight: 64 })
    this.load.spritesheet('player_idle', 'assets/sprites/player_idle.png', { frameWidth: 96, frameHeight: 64 })
  }

  init(data: SceneInitData) {
    this.worldData   = data.worldData
    this.player      = data.player
    this.myPlayerId  = data.myPlayerId
    this.worldEvents = data.events
  }

  private createAnimations() {
    const anims = this.anims
    anims.create({
      key: 'walk',
      frames: anims.generateFrameNumbers('player_walk', { start: 0, end: 7 }),
      frameRate: 8,
      repeat: -1,
    })
    anims.create({
      key: 'idle',
      frames: anims.generateFrameNumbers('player_idle', { start: 0, end: 8 }),
      frameRate: 6,
      repeat: -1,
    })
  }

  create() {
    const tileMap = new TileMap(this, this.worldData.tiles, this.worldData.tiled)
    tileMap.render()
    this.createAnimations()


    for (const obj of this.worldData.objects) {
      new GameObjectSprite(this, obj)
    }

    this.spritePos = { ...this.player.position }
    this.playerSprite = new PlayerSprite(this, this.player.position, this.player.facing)

    this.inputSystem = new InputSystem(
      this,
      this.player.id,
      this.worldData.tiles,
      this.player.position,
      (result: MoveResult) => {
        if (result.position) {
          this.spritePos = { ...result.position }
          this.playerSprite.moveToWithFacing(result.position, result.facing)
          this.checkWorldEvents(result.position)
        } else {
          this.playerSprite.setFacing(result.facing)
        }
      },
      () => this.handleInteract(),
      () => this.handleUse(),
      () => this.handleLeave(),
    )

    this.otherUnsub = useGameStore.subscribe((state) => {
      this._syncOtherPlayers(state.otherPlayers)
    })

    this.storeUnsub = useGameStore.subscribe((state, prev) => {
      const p = state.player
      const q = prev.player
      if (!p) return
      if (q && p.position.x === q.position.x && p.position.y === q.position.y && p.facing === q.facing) return

      // only facing changed — update sprite directly, no movement animation needed
      if (q && p.position.x === q.position.x && p.position.y === q.position.y) {
        this.playerSprite.setFacing(p.facing)
        return
      }

      // already animating to this exact target — ignore duplicate polls
      if (this.animTarget && p.position.x === this.animTarget.x && p.position.y === this.animTarget.y) return
      this.runExternalAnim(p.position)
    })

    // ── 滚轮缩放 ─────────────────────────────────────────────────────────────
    this.input.on('wheel', (_p: unknown, _o: unknown, _dx: number, deltaY: number) => {
      this.adjustZoom(deltaY > 0 ? -ZOOM_STEP : ZOOM_STEP)
    })

    this.events.on(Phaser.Scenes.Events.SHUTDOWN, () => {
      this.storeUnsub()
      this.otherUnsub()
      this.otherSprites.forEach(s => s.destroy())
      this.otherSprites.clear()
    })
  }

  private runExternalAnim(target: Position) {
    this.animTarget = { ...target }
    if (this.isExternalAnim) return   // loop already running; it will pick up the updated animTarget
    this.isExternalAnim = true

    const step = () => {
      const t = this.animTarget!
      if (this.spritePos.x === t.x && this.spritePos.y === t.y) {
        this.inputSystem.syncFromServer(t)
        this.isExternalAnim = false
        this.animTarget = null
        return
      }

      const path = bfs(this.worldData.tiles, this.spritePos, t)
      if (path.length === 0) {
        // no walkable path — snap to server position
        this.spritePos = { ...t }
        this.playerSprite.moveToWithFacing(t, this.player.facing)
        this.inputSystem.syncFromServer(t)
        this.isExternalAnim = false
        this.animTarget = null
        return
      }

      const dir = path[0] as Direction
      const delta = DELTAS[dir]
      const next: Position = { x: this.spritePos.x + delta.x, y: this.spritePos.y + delta.y }
      this.spritePos = next
      this.playerSprite.moveToWithFacing(next, dir)
      this.checkWorldEvents(next)
      this.time.delayedCall(getMoveInterval(), step)
    }

    step()
  }

  private _syncOtherPlayers(others: OtherPlayer[]) {
    const seen = new Set<string>()
    for (const op of others) {
      seen.add(op.id)
      const existing = this.otherSprites.get(op.id)
      if (existing) {
        existing.updatePosition(op.position, op.facing)
      } else {
        this.otherSprites.set(op.id, new OtherPlayerSprite(this, op.position, op.facing, op.name))
      }
    }
    for (const [id, sprite] of this.otherSprites) {
      if (!seen.has(id)) {
        sprite.destroy()
        this.otherSprites.delete(id)
      }
    }
  }

  private checkWorldEvents(pos: Position) {
    for (const event of this.worldEvents) {
      if (event.tiles.some(t => t.x === pos.x && t.y === pos.y)) {
        EventBus.emit('show-interaction', { message: event.description })
        return
      }
    }
  }

  private async handleInteract() {
    try {
      const res = await sendAction(this.player.id, 'interact')
      if (res.success) {
        EventBus.emit('show-interaction', { message: res.result?.message })
      } else if (res.reason === 'no_object_in_front') {
        EventBus.emit('show-interaction', { message: 'Nothing interactable in front' })
      }
    } catch (err) {
      console.error('[Interact Error]', err)
    }
  }

  private async handleUse() {
    try {
      const res = await sendAction(this.player.id, 'use')
      if (res.success) {
        EventBus.emit('show-interaction', { message: res.result?.message })
      } else if (res.reason === 'no_object_in_front') {
        EventBus.emit('show-interaction', { message: 'Nothing usable in front' })
      } else if (res.reason === 'use_disabled') {
        EventBus.emit('show-interaction', { message: 'Cannot use object right now' })
      } else {
        const msg = res.result?.message
          ?? (res.reason === 'object_full'
            ? `In use (${res.result?.currentUsers}/${res.result?.maxUsers})`
            : 'Cannot use')
        EventBus.emit('show-interaction', { message: msg })
      }
    } catch (err) {
      console.error('[Use Error]', err)
    }
  }

  private async handleLeave() {
    try {
      const res = await sendAction(this.player.id, 'leave')
      if (res.success) {
        EventBus.emit('show-interaction', { message: 'Left' })
      } else if (res.reason === 'not_using_any_object') {
        EventBus.emit('show-interaction', { message: 'Not currently using any object' })
      }
    } catch (err) {
      console.error('[Leave Error]', err)
    }
  }

  private adjustZoom(delta: number) {
    this.currentZoom = Phaser.Math.Clamp(this.currentZoom + delta, MIN_ZOOM, MAX_ZOOM)
    this.cameras.main.setZoom(this.currentZoom)
    const { x, y } = this.playerSprite.getPixelPosition()
    this.cameras.main.centerOn(x, y)
  }

  update() {
    this.inputSystem.update()
    const { x, y } = this.playerSprite.getPixelPosition()
    this.cameras.main.centerOn(x, y)
    this.playerSprite.updateDepth()
  }
}
