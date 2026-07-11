import Phaser from 'phaser'
import GameScene from './scenes/GameScene'
import { WorldData, Player, WorldEvent } from '../types'

export function initGame(worldData: WorldData, player: Player, myPlayerId: string, events: WorldEvent[]) {
  const game = new Phaser.Game({
    type: Phaser.AUTO,
    width: window.innerWidth,
    height: window.innerHeight,
    parent: 'game-container',
    backgroundColor: '#1a1a2e',
    pixelArt: true,
    input: { mouse: { preventDefaultDown: false } },
  })

  game.events.once(Phaser.Core.Events.READY, () => {
    game.canvas.addEventListener('contextmenu', (e) => e.preventDefault())
    game.scene.add('GameScene', GameScene, true, { worldData, player, myPlayerId, events })
  })
}
