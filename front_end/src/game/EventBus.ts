import Phaser from 'phaser'

// Phaser ↔ React 通信的事件总线
// 事件列表：
//   'show-interaction' { message: string }                 — 显示交互结果面板
//   'player-snapshot'  { player: Player, sentAt: number }   — /player 轮询结果（位置校正）
//   'player-rejoined'  { playerId: string, player: Player } — 后端重启后自动重新 join
//   'chat-message'     { entityId: string, content: string }— 聊天室新消息（叠加层气泡）
//   'stats'            { fps: number, ... }                 — 每秒一次帧率统计
export const EventBus = new Phaser.Events.EventEmitter()
