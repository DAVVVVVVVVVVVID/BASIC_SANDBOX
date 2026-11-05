export interface Position {
  x: number
  y: number
}

export interface Tile {
  x: number
  y: number
  type: string
  walkable: boolean
  objectId: string | null
  world:    string | null
  sector:   string | null
  arena:    string | null
}

export interface Effect {
  type: string
  key: string
  value?: number | null
  tag?: string
}

export interface GameObject {
  id: string
  type: string
  name: string
  position: Position
  tiles?: Position[]
  sprite?: string
  interactable: boolean
  description: string
  maxUsers: number
  currentUsers: number
  userList: string[]
  useStateLabel: string
  effects: Effect[]
  advertise?: Record<string, number>
}

export type TimePeriod = 'morning' | 'day' | 'dusk' | 'night'
export type Weather = 'sunny' | 'cloudy' | 'rain'

export interface WorldState {
  date: string
  time: string
  period: TimePeriod
  running: boolean
  speed: number
  weather: Weather
}

export type Controller = 'human' | 'agent'

/** GET /world players[] 的元素（B6：带 controller / online） */
export interface OtherPlayer {
  id: string
  name: string
  position: Position
  facing: Facing
  state: PlayerState
  controller?: Controller
  online?: boolean
}

export interface TiledTilesetInfo {
  name: string
  firstgid: number
  tilewidth: number
  tileheight: number
  tilecount: number
  columns: number
  imageSource: string
  imageWidth: number
  imageHeight: number
  margin: number
  spacing: number
}

export interface TiledLayer {
  id: number
  name: string
  data: number[]
  width: number
  height: number
}

export interface TiledRenderData {
  tilesets: TiledTilesetInfo[]
  layers: TiledLayer[]
}

export interface WorldData {
  tiles: Tile[]
  objects: GameObject[]
  worldState: WorldState
  players: OtherPlayer[]
  tiled?: TiledRenderData
}

export type Facing = 'up' | 'down' | 'left' | 'right'

export interface WorldEvent {
  id: string
  tiles: Position[]
  description: string
}

export type PlayerState =
  | 'idle' | 'walking' | 'requesting_talk' | 'walking_over' | 'talking' | 'using'
  | (string & {})

export interface PlayerProfile {
  id: string
  name: string
  age: number
}

export interface Buff {
  key: string
  value: number
  mode: 'persistent' | 'timed'
  remaining: number | null  // null = 永久（persistent）；毫秒 = 剩余时间（timed）
  source: string
}

/** 七变量（ARCHITECTURE §2.5）。hp 是 fullness 的别名，过渡期保留 */
export const NEED_KEYS = ['fullness', 'energy', 'social', 'fun', 'mood'] as const
export type NeedKey = typeof NEED_KEYS[number]
export type NeedVars = Record<NeedKey, number>

export interface Player extends Partial<NeedVars> {
  id: string
  profile: PlayerProfile
  position: Position
  facing: Facing
  state: PlayerState
  stateLabel: string | null
  hp: number
  energy: number
  usingObjectId: string | null
  buffs: Buff[]
  tags: string[]
  canMove: boolean
  canInteract: boolean
  canUse: boolean
  moveSpeed: number
  pendingMessage?: string | null
  emotion_tags?: Buff[]
  closeness?: Record<string, number>
  controller?: Controller
  online?: boolean
  scene?: 'sandbox' | 'live'
  agent_id?: string | null
  mood_base?: number
}

/** GET /player/{id}/state（B13，只读，不刷心跳） */
export interface PlayerStateVars {
  id: string
  vars: NeedVars
  mood_base: number
  emotion_tags: Buff[]
  closeness: Record<string, number>
  scene: 'sandbox' | 'live'
  controller: Controller
  online: boolean
  agent_id: string | null
  last_tick_ts: string
  recent_uses: Record<string, number>
}

export interface ActionLogEntry {
  timestamp: string
  entityId: string
  type: string
  payload: Record<string, unknown>
  success: boolean
  reason: string | null
  label: string | null
  game_time?: string
  controller?: Controller
}

/** 叠加层聊天气泡 */
export interface ChatBubble {
  entityId: string
  content: string
  until: number   // performance.now() 毫秒
}

export type ConnectionStatus = 'connecting' | 'online' | 'offline'
