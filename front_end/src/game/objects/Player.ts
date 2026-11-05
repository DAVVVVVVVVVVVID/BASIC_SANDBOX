import ActorSprite from './ActorSprite'
import type { Position, Facing } from '../../types'

/** 自己：带朝向箭头 */
export default class PlayerSprite extends ActorSprite {
  constructor(scene: Phaser.Scene, position: Position, facing: Facing, name: string) {
    super(scene, position, facing, { name, isSelf: true, showArrow: true })
  }
}
