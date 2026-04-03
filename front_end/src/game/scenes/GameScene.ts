import Phaser from 'phaser'
import { WorldData, Player, WorldEvent, Position } from '../../types'
import TileMap, { preloadTileAssets } from '../map/TileMap'
import PlayerSprite from '../objects/Player'
import GameObjectSprite from '../objects/GameObjectSprite'
import InputSystem, { MoveResult } from '../systems/InputSystem'
import { EventBus } from '../EventBus'
import { sendAction } from '../../api/world'

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

    this.playerSprite = new PlayerSprite(this, this.player.position, this.player.facing)

    this.inputSystem = new InputSystem(
      this,
      this.player.id,
      this.worldData.tiles,
      this.player.position,
      (result: MoveResult) => {
        if (result.position) {
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
