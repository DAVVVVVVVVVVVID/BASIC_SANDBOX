import Phaser from 'phaser'

export default class BootScene extends Phaser.Scene {
  constructor() {
    super({ key: 'BootScene' })
  }

  create() {
    this.add
      .text(400, 300, 'Town Game\nPhase 0 - 初始化完成', {
        fontSize: '20px',
        color: '#a8d8a8',
        align: 'center',
      })
      .setOrigin(0.5)
  }
}
