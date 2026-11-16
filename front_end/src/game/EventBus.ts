import Phaser from 'phaser'

// Phaser ↔ React 通信的事件总线
// 事件列表：
//   'show-interaction' { message: string }                 — 显示交互结果面板
//   'player-snapshot'  { player: Player, sentAt: number }   — /player 轮询结果（位置校正）
//   'player-rejoined'  { playerId: string, player: Player } — 后端重启后自动重新 join
//   'walk-to-tile'     { x, y, label? }                      — HUD 上楼 / 下楼：后端寻路走到目标格（跨层）
//   'director-cmd'     { cmd: 'self' | 'free' } | { cmd: 'follow', id }   — 操控页导播视角（主播 11-16）
//   'director-state'   { mode: 'self' | 'free' | 'follow', follow: string | null }
//   'thought-event'    ws thought 原样；'director-thoughts' { on } — 导播栏 💭 想法开关
//   'chat-row'         WsChatEvent 原样（message / event）— 导播跟随的只读对话
//   'chat-message'     { entityId: string, content: string }— 聊天室新消息（叠加层气泡）
//   'stats'            { fps: number, ... }                 — 每秒一次帧率统计
export const EventBus = new Phaser.Events.EventEmitter()
