import ActorSprite from './ActorSprite'
import type { Position, Facing } from '../../types'
import type { CharKey } from '../assets'

/** 别人：位置来自 /world 轮询，由 ActorSprite 按时间插值 */
export default class OtherPlayerSprite extends ActorSprite {
  constructor(scene: Phaser.Scene, position: Position, facing: Facing, name: string, charKey: CharKey, who: { controller?: string | null; agentId?: string | null; skin?: 'dark' | 'rpg' } = {}) {
    super(scene, position, facing, { name, charKey, isSelf: false, showArrow: false, ...who })
  }
}
