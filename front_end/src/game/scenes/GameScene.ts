import Phaser from 'phaser'
import { WorldData, Player, WorldEvent, Position } from '../../types'
import TileMap, { preloadTileAssets } from '../map/TileMap'
import PlayerSprite from '../objects/Player'
import GameObjectSprite from '../objects/GameObjectSprite'
import InputSystem, { MoveResult, Direction, DELTAS, bfs, getMoveInterval } from '../systems/InputSystem'
import { EventBus } from '../EventBus'
import { sendAction } from '../../api/world'
import { useGameStore } from '../../store/gameStore'

interface SceneInitData {
  worldData: WorldData
  player: Player
  events: WorldEvent[]
}

export default class GameScene extends Phaser.Scene {
  private worldData!: WorldData
  private player!: Player
  private worldEvents!: WorldEvent[]
  private playerSprite!: PlayerSprite
  private inputSystem!: InputSystem
  private storeUnsub!: () => void
  // tracks the sprite's current tile (updated by both player input and external animation)
  private spritePos!: Position
  // target of an in-progress external animation; null when idle
  private animTarget: Position | null = null
  private isExternalAnim = false

  constructor() {
    super({ key: 'GameScene' })
  }

  preload() {
    preloadTileAssets(this)
    for (const obj of this.worldData.objects) {
      if (obj.sprite) {
        this.load.image(`obj_${obj.sprite}`, `assets/sprites/${obj.sprite}.png`)
      }
    }
  }

  init(data: SceneInitData) {
    this.worldData = data.worldData
    this.player    = data.player
    this.worldEvents = data.events
  }

  create() {
    const tileMap = new TileMap(this, this.worldData.tiles)
    tileMap.render()

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

    this.events.on(Phaser.Scenes.Events.SHUTDOWN, () => this.storeUnsub())
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
        EventBus.emit('show-interaction', { message: '面前没有可交互的对象' })
      }
    } catch (err) {
      console.error('[Interact Error]', err)
    }
  }

  private async handleUse() {
    try {
      const res = await sendAction(this.player.id, 'use')
      if (res.success) {
        EventBus.emit('show-interaction', { message: res.result?.playerState })
      } else if (res.reason === 'no_object_in_front') {
        EventBus.emit('show-interaction', { message: '面前没有可使用的对象' })
      } else if (res.reason === 'object_full') {
        const { currentUsers, maxUsers } = res.result ?? {}
        EventBus.emit('show-interaction', { message: `正在使用中（${currentUsers}/${maxUsers}）` })
      } else if (res.reason === 'not_interactable') {
        EventBus.emit('show-interaction', { message: '这个对象无法使用' })
      }
    } catch (err) {
      console.error('[Use Error]', err)
    }
  }

  private async handleLeave() {
    try {
      const res = await sendAction(this.player.id, 'leave')
      if (res.success) {
        EventBus.emit('show-interaction', { message: '已离开' })
      } else if (res.reason === 'not_using_any_object') {
        EventBus.emit('show-interaction', { message: '当前没有正在使用的对象' })
      }
    } catch (err) {
      console.error('[Leave Error]', err)
    }
  }

  update() {
    this.inputSystem.update()
  }
}
