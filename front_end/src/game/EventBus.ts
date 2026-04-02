import Phaser from 'phaser'

// Phaser ↔ React 通信的事件总线
// 事件列表：
//   'show-interaction' { message: string }  — 显示交互结果面板
export const EventBus = new Phaser.Events.EventEmitter()
