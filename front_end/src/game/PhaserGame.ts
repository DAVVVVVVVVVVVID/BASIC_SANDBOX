import Phaser from 'phaser'
import GameScene, { SceneInitData } from './scenes/GameScene'

export const SPECTATE_W = 1920
export const SPECTATE_H = 1080

export function initGame(init: SceneInitData): Phaser.Game {
  const spectate = init.mode === 'spectate'
  const transparent = spectate && init.spectate?.bg === 'transparent'

  const game = new Phaser.Game({
    type: Phaser.AUTO,
    parent: 'game-container',
    backgroundColor: transparent ? undefined : '#0f1020',
    transparent,
    pixelArt: true,
    antialias: false,
    roundPixels: true,
    fps: { target: 60, forceSetTimeOut: false, smoothStep: true },
    render: { powerPreference: 'high-performance' },
    input: { mouse: { preventDefaultDown: false }, keyboard: !spectate },
    scale: spectate
      ? { mode: Phaser.Scale.FIT, autoCenter: Phaser.Scale.CENTER_BOTH, width: SPECTATE_W, height: SPECTATE_H }
      : { mode: Phaser.Scale.RESIZE, width: window.innerWidth, height: window.innerHeight },
    banner: false,
  })

  game.events.once(Phaser.Core.Events.READY, () => {
    game.canvas.addEventListener('contextmenu', (e) => e.preventDefault())
    game.scene.add('GameScene', GameScene, true, init)
  })
  return game
}
