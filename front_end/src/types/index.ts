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
  /** W10（B c0e75ef）：使用者站位（**绝对格**，按使用顺序分配）与朝向；后端 use 时已把人挪到该格并转向，null = 原地不动 */
  usePos?: { x: number; y: number }[] | null
  useFacing?: Facing | null
  /** W11：库存（商店 / 冰箱 {item: n}，其余 null） */
  stock?: Record<string, number> | null
  /** W10：商店物品（shop_counter / fish_stall / bar）；price = 卖价（null 不卖）、sell = 收购价、stock W11 起是实数 */
  shop?: { type?: string; item?: string; name?: string; price?: number | null; sell?: number | null; stock?: number | null }[] | null
  /** world-v1.1-a（B 11-13）：冰箱存储内容与容量；柜台 / 鱼摊每日供应与补货时刻（stock = 今日剩余）；餐桌 dining / 允许物品；灶台在做的饭 */
  contents?: { item: string; count: number; expires_at?: string | null; expires_in_days?: number | null; spoiled?: boolean }[] | null
  storage?: { capacity: number; used: number } | null
  daily_supply?: Record<string, number> | null
  restock_at?: string | null
  dining?: boolean
  dining_allow?: string[] | null
  cooking?: { by: string; product: string; portions: number; started_at?: string; ready_at?: string; ready_in_min?: number } | null
  /** world-v1.1-b：工作 / 创作类每日上限（daily_used_min 只在 GET 带 ?player= 时有值） */
  work?: boolean
  daily_limit_min?: number | null
  daily_used_min?: number | null
}
/** world-v1.1：进食 / 下厨 / 烧着的持续动作（players[] / GET /player / state 一致都有）；不忙 null */
export interface BusyState { kind: 'eating' | 'cooking' | 'burning' | string; item?: string; started_at?: string; ends_at?: string; remaining_s?: number; progress?: number; gain?: Record<string, number> | null }
/** world-v1.1-b：每日使用时长（分钟）按物品类型 */
export type DailyUse = Record<string, { used_min: number; limit_min: number }>
/** world-v1.1：房租（人类 null） */
export interface RentInfo { amount: number; due_at?: string; due_in_days?: number; overdue?: boolean; landlord?: string; items?: { kind: 'home' | 'shop' | string; amount: number }[] }

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
  /** world-v1.1：进食 / 下厨进度、每日使用时长、房租（B：三者在 players[] / GET /player / state 一致都有） */
  busy?: BusyState | null
  daily_use?: DailyUse | null
  rent?: RentInfo | null
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
  /** §3.40：主人视角待回应的敲门；访客视角最近一次敲门 */
  busy?: BusyState | null
  daily_use?: DailyUse | null
  rent?: RentInfo | null
  pending_knocks?: PendingKnock[]
  door_request?: { id: string; home?: string; home_name?: string; status?: string; expires_at?: string; responded_by?: string | null; answers?: { by: string; by_name?: string; text: string; at?: string }[]; door?: DoorRef | null } | null
  keys?: unknown[]
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
  ttl?: number    // 本条的时长（合并判断用）
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
/** W11（B fc051f1）：产出（钓到鱼 / 做好便当 / 写完歌 / 做完文稿）与委托（开出 / 交付） */
export interface WsProduce { type: 'produce'; entity: string; via?: 'fishing' | 'stove' | 'compose' | 'make_video' | string; item?: string; item_name?: string; qty?: number; object?: string | null }
export interface WsCommission { type: 'commission'; event: 'open' | 'deliver' | string; id?: string; client?: string; client_name?: string; fee?: number; title?: string; status?: string; entity?: string | null }
/** §3.41 门禁：钥匙 / 开门 / 敲门（B c3808ad，api-spec §11）。ws knock：访客在家门外敲门 → 门口气泡；
 *  ws door：answered（屋内有人隔门喊话，text）/ declined / no_answer / opened（有人站门内开门，敞开 60 游戏秒）/ closed（到期落锁）/ visitor_entered（访客进门） */
export interface DoorRef { id?: string; door_id?: string; name?: string; x: number; y: number; inside?: { x: number; y: number } | null }
export interface WsKnock { type: 'knock'; request_id: string; visitor: string; visitor_name?: string; home: string; home_name?: string; door?: DoorRef | null; owners?: string[]; expires_at?: string; notified?: string[] }
export interface WsDoor { type: 'door'; event: 'answered' | 'declined' | 'no_answer' | 'opened' | 'closed' | 'visitor_entered' | 'accepted' | 'pass_expired' | string; request_id?: string; visitor?: string; visitor_name?: string; home?: string; home_name?: string; by?: string | null; by_name?: string | null; text?: string | null; door?: DoorRef | null; door_id?: string; name?: string; x?: number; y?: number; open_until?: string | null }
/** world-v1.1 ws：吃完 / 坏食（背包或冰箱）/ 到每日上限自动离开 / 房租 / 下厨中断 */
export interface WsEatDone { type: 'eat_done' | 'eat_cancelled'; entity: string; item?: string; gain?: Record<string, number> | null }
export interface WsSpoiled { type: 'spoiled'; entity?: string; object?: string; object_type?: string; position?: Position; item?: string; qty?: number }
export interface WsDailyLimit { type: 'daily_limit'; entity: string; object?: string; object_type?: string; used_min?: number; limit_min?: number; resets_at?: string }
export interface WsRent { type: 'rent'; event: 'due_soon' | 'paid' | 'overdue' | 'cleared' | string; entity: string; amount?: number; balance?: number; due_in_days?: number }
export interface WsCookCancelled { type: 'cook_cancelled'; entity?: string; object?: string; item?: string; portions?: number }
export type WsMessage = WsSnapshot | WsPatch | WsAction | WsHeartbeat | WsQQ | WsProduce | WsCommission | WsKnock | WsDoor | WsEatDone | WsSpoiled | WsDailyLimit | WsRent | WsCookCancelled
/** 屋内人视角的待回应敲门（GET /player.pending_knocks[]） */
export interface PendingKnock { id: string; visitor?: string; visitor_name?: string; home?: string; home_name?: string; door?: DoorRef | null; status?: string; expires_at?: string }
/** GET /world.map.doors[]：带 owner 的家门（x,y = 外侧格） */
export interface MapDoor { door_id: string; name?: string; x: number; y: number; open?: boolean; open_until?: string | null; keys?: number; owners?: string[] }
