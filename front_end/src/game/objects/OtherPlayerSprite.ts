import ActorSprite from './ActorSprite'
import type { Position, Facing } from '../../types'

/** 别人：位置来自 /world 轮询，由 ActorSprite 按时间插值 */
export default class OtherPlayerSprite extends ActorSprite {
  constructor(scene: Phaser.Scene, position: Position, facing: Facing, name: string) {
    super(scene, position, facing, { name, isSelf: false, showArrow: false })
  }
}
