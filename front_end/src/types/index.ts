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
  /** v2：楼层（缺省 1） */
  floor?: number
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
  /** W9（B W10 任务 2）：使用者站位（相对格）与朝向 */
  use_pos?: { x: number; y: number } | [number, number] | null
  use_facing?: Facing | null
  /** W9（B W10 任务 4）：商店物品（柜台 / 卖鱼摊） */
  shop?: { type?: string; item?: string; name?: string; price?: number; stock?: number }[]
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
  /** W5：地图静态内容指纹，变了才重拉 tiles / tiled */
  mapVersion?: string
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
  /** W4（B 4d6a931）：自我层 agent id，human 为 null */
  agent_id?: string | null
  /** W5（B 59d1ac8）：与 GET /player 同义，叠加层直接读 */
  stateLabel?: string | null
  usingObjectId?: string | null
  tags?: string[]
  /** W5：坐标每次实际变化 +1 */
  pos_seq?: number
  /** W9：金币与背包（假设 players[] 也带） */
  gold?: number
  inventory?: unknown[]
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
  /** 地图格式 v2（B W9，字段名未冻结）：由 game/map/mapv2.ts 宽容解析 */
  edges?: unknown[]
  floors?: unknown
  access?: unknown
  arenas?: unknown[]
  /** v2：地图块 { format, edges, floors, access } */
  map?: unknown
  /** B W6+：区域中文名 */
  zone_names?: { world?: Record<string, string>; sector?: Record<string, string>; arena?: Record<string, string> }
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
  /** W9（B W10 任务 4）：金币与背包；字段形状是假设，前端 normalizeInventory 宽容解析 */
  gold?: number
  inventory?: unknown[]
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
  /** B18（W6）：她在用游戏机时 brain 的局内指标 */
  game?: GameSession | null
}

export interface GameSession {
  status: 'playing' | 'ended' | string
  started_at?: string
  brain_run_id?: string
  run_id?: string
  ticks?: number
  day?: number
  phase?: string
  health?: number
  hunger?: number
  sanity?: number
  deaths?: number
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
export type Transport = 'ws' | 'poll' | 'none'

/** B17 /ws/world 消息 */
export interface WsSnapshot extends WorldData { type: 'snapshot'; ts: string }
export interface WsPatch {
  type: 'patch'
  ts: string
  worldState?: Partial<WorldState>
  players?: { upsert?: OtherPlayer[]; remove?: string[] }
  objects?: Partial<GameObject>[]
  chat?: WsChatEvent[]
}
export interface WsChatEvent {
  chat_room_id: string
  participants: string[]
  kind: 'message' | 'event'
  seq: number
  from_entity_id?: string
  from_name?: string
  content?: string
  type?: string
  timestamp?: string
}
export interface WsAction { type: 'action'; ts: string; entity: string; action: string; object?: string | null; success: boolean; reason?: string | null; item?: string | null; item_name?: string | null; price?: number | null; gold_delta?: number | null; target?: string | null; target_name?: string | null; message?: string | null }
export interface WsHeartbeat { type: 'heartbeat'; ts: string }
/** W9（B W10 任务 3）：QQ 消息推送，字段形状见 api/qq.ts normalizeMessage */
export interface WsQQ { type: 'qq'; ts?: string; message?: unknown; [k: string]: unknown }
export type WsMessage = WsSnapshot | WsPatch | WsAction | WsHeartbeat | WsQQ
