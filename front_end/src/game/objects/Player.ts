import ActorSprite from './ActorSprite'
import type { Position, Facing } from '../../types'
import type { CharKey } from '../assets'

/** 自己：带朝向箭头 */
export default class PlayerSprite extends ActorSprite {
  constructor(scene: Phaser.Scene, position: Position, facing: Facing, name: string, charKey: CharKey, who: { controller?: string | null; agentId?: string | null } = {}) {
    super(scene, position, facing, { name, charKey, isSelf: true, showArrow: true, ...who })
  }
}
