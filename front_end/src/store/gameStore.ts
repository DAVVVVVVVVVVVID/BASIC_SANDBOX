import { create } from 'zustand'
import { qqSetContacts, qqMerge, qqReplaceThread } from '../game/qqState'
import type {
  Player, WorldState, ActionLogEntry, Tile, OtherPlayer, GameObject,
  PlayerStateVars, ChatBubble, ConnectionStatus, TiledRenderData, Transport,
} from '../types'

export type AppMode = 'play' | 'spectate'

/** 便宜的地图签名：数量 + 不可走格数 + 类型哈希 + 图层数；足够区分换图与重启 */
export function mapSignature(world: { tiles: { walkable: boolean; type: string }[]; tiled?: { layers: unknown[] } | null }): string {
  let blocked = 0
  let typeHash = 0
  for (const t of world.tiles) { if (!t.walkable) blocked++; typeHash = (typeHash * 31 + t.type.length) >>> 0 }
  return `${world.tiles.length}:${blocked}:${typeHash}:${world.tiled?.layers?.length ?? 0}`
}

interface GameStore {
  mode: AppMode
  player: Player | null
  worldState: WorldState | null
  actionLog: ActionLogEntry[]
  tiles: Tile[]
  tiled: TiledRenderData | null
  /** 地图 v2 附加字段（edges / floors / access / arenas），随 setMap 更新 */
  mapExtras: Pick<import('../types').WorldData, 'edges' | 'floors' | 'access' | 'arenas' | 'map'>
  /** tiles / tiled 内容变化时 +1（后端换地图、重启），GameScene 据此重建背景 */
  mapVersion: number
  /** 最近一次 setMap 的签名（TickSystem.mapSignature），避免启动后第一轮轮询重复重建 */
  mapSig: string
  objects: GameObject[]
  myPlayerId: string | null
  /** 以某身份登录（world-v1.3：achan = 主播接管阿蝉；离开时不删人、勿扰归位） */
  identity: string | null
  /** 所有 player（含自己）；GameScene 自行过滤 */
  players: OtherPlayer[]
  /** 旁观目标等需要七变量的人：id → /player/{id}/state */
  playerVars: Record<string, PlayerStateVars>
  bubbles: ChatBubble[]
  connection: ConnectionStatus
  /** 当前数据通道：ws 推送 / 轮询 / 还没连上 */
  transport: Transport
  /** 连续失败次数，用于 UI 显示与退避 */
  failures: number
  /** 后端 /world 快照时间（performance.now），用于插值 */
  lastWorldAt: number

  setMode: (m: AppMode) => void
  setPlayer: (p: Player | null) => void
  setIdentity: (id: string | null) => void
  setWorldState: (ws: WorldState) => void
  setActionLog: (log: ActionLogEntry[]) => void
  setTiles: (tiles: Tile[]) => void
  setMap: (tiles: Tile[], tiled: TiledRenderData | null | undefined, sig?: string, extras?: Pick<import('../types').WorldData, 'edges' | 'floors' | 'access' | 'arenas' | 'map'>) => void
  /** 初始 fetch 之后调用：记下签名（不 +1 版本） */
  setMapSeen: (world: { tiles: Tile[]; tiled?: TiledRenderData | null }) => void
  setObjects: (objects: GameObject[]) => void
  setMyPlayerId: (id: string | null) => void
  setPlayers: (players: OtherPlayer[]) => void
  setPlayerVars: (id: string, vars: PlayerStateVars | null) => void
  pushBubble: (entityId: string, content: string, ttlMs?: number) => void
  pruneBubbles: (now: number) => void
  setConnection: (c: ConnectionStatus) => void
  setTransport: (t: Transport) => void
  /** ws patch：按 id 合并 players（upsert / remove） */
  patchPlayers: (upsert: OtherPlayer[] | undefined, remove: string[] | undefined) => void
  /** ws thought 事件：落到对应玩家的 last_thought */
  setPlayerThought: (id: string, thought: import('../types').PlayerThought | null) => void
  /** ws patch：按 id 合并 objects 的使用状态 */
  patchObjects: (partials: Partial<GameObject>[]) => void
  patchWorldState: (partial: Partial<WorldState>) => void
  /** W9 QQ：按玩家 id 存联系人与消息（操控页存自己的，旁观页存跟随目标的） */
  qq: { contacts: import('../api/qq').QQContact[]; messages: import('../api/qq').QQMessage[]; available: boolean | null }
  setQQContacts: (c: import('../api/qq').QQContact[] | null) => void
  mergeQQMessages: (m: import('../api/qq').QQMessage[]) => void
  /** 以后端为准覆盖某个会话（peer 的 1:1 / 群）：先删本地属于该会话的，再放入拉回来的（ws 广播混进来的别人消息就此被清） */
  replaceQQThread: (belongs: (m: import('../api/qq').QQMessage) => boolean, m: import('../api/qq').QQMessage[]) => void
  markQQRead: (peer: string) => void
}

export const BUBBLE_TTL_MS = 8000

export const useGameStore = create<GameStore>((set, get) => ({
  mode: 'play',
  player: null,
  worldState: null,
  actionLog: [],
  tiles: [],
  tiled: null,
  mapExtras: {},
  mapVersion: 0,
  mapSig: '',
  objects: [],
  myPlayerId: null,
  identity: null,
  players: [],
  playerVars: {},
  bubbles: [],
  connection: 'connecting',
  transport: 'none',
  failures: 0,
  lastWorldAt: 0,

  setMode: (mode) => set({ mode }),
  setPlayer: (player) => set({ player }),
  setIdentity: (identity) => set({ identity }),
  setWorldState: (worldState) => set({ worldState }),
  setActionLog: (actionLog) => set({ actionLog }),
  setTiles: (tiles) => set({ tiles }),
  setMap: (tiles, tiled, sig, extras) => set((s) => ({ tiles, tiled: tiled ?? null, mapVersion: s.mapVersion + 1, mapSig: sig ?? mapSignature({ tiles, tiled }), mapExtras: extras ?? {} })),
  setMapSeen: (world) => set({ mapSig: (world as { worldState?: { mapVersion?: string } }).worldState?.mapVersion ?? mapSignature(world) }),
  setObjects: (objects) => set({ objects }),
  setMyPlayerId: (myPlayerId) => set({ myPlayerId }),
  setPlayers: (players) => set({ players, lastWorldAt: performance.now() }),
  setPlayerVars: (id, vars) => set((s) => {
    const next = { ...s.playerVars }
    if (vars) next[id] = vars
    else delete next[id]
    return { playerVars: next }
  }),
  // W9：同一人头顶 2 s 内连来两条（如 give 的动作气泡 + commission deliver）→ 合成两行一起显示，不再后到的盖掉先到的；更久的直接替换
  pushBubble: (entityId, content, ttlMs = BUBBLE_TTL_MS) => set((s) => {
    const now = performance.now()
    const prev = s.bubbles.find(b => b.entityId === entityId)
    const fresh = prev && prev.until - now > (prev.ttl ?? BUBBLE_TTL_MS) - 2000 && prev.content !== content && !prev.content.includes(content)
    const merged = fresh ? `${prev!.content}\n${content}`.split('\n').slice(-3).join('\n') : content
    return { bubbles: [...s.bubbles.filter(b => b.entityId !== entityId), { entityId, content: merged, until: now + Math.max(ttlMs, fresh ? prev!.until - now : 0), ttl: ttlMs }] }
  }),
  pruneBubbles: (now) => {
    const cur = get().bubbles
    if (cur.length === 0) return
    const next = cur.filter(b => b.until > now)
    if (next.length !== cur.length) set({ bubbles: next })
  },
  setTransport: (transport) => set({ transport }),
  patchPlayers: (upsert, remove) => set((s) => {
    if ((!upsert || upsert.length === 0) && (!remove || remove.length === 0)) return {}
    const byId = new Map(s.players.map(p => [p.id, p]))
    for (const p of upsert ?? []) byId.set(p.id, { ...byId.get(p.id), ...p })
    for (const id of remove ?? []) byId.delete(id)
    return { players: [...byId.values()], lastWorldAt: performance.now() }
  }),
  setPlayerThought: (id, thought) => set((s) => ({ players: s.players.map(p => (p.id === id || p.agent_id === id || p.name === id) ? { ...p, last_thought: thought } : p) })),
  patchObjects: (partials) => set((s) => {
    if (!partials || partials.length === 0) return {}
    const byId = new Map(partials.filter(p => p.id).map(p => [p.id as string, p]))
    return { objects: s.objects.map(o => byId.has(o.id) ? { ...o, ...byId.get(o.id) } : o) }
  }),
  patchWorldState: (partial) => set((s) => ({ worldState: s.worldState ? { ...s.worldState, ...partial } : (partial as WorldState) })),
  qq: { contacts: [], messages: [], available: null },
  setQQContacts: (c) => set((s) => ({ qq: qqSetContacts(s.qq, c) })),
  mergeQQMessages: (m) => set((s) => (m.length ? { qq: qqMerge(s.qq, m) } : {})),
  replaceQQThread: (belongs, m) => set((s) => ({ qq: qqReplaceThread(s.qq, belongs, m) })),
  markQQRead: (peer) => set((s) => ({ qq: { ...s.qq, messages: s.qq.messages.map(x => (x.from === peer || x.group === peer) && !x.readAt ? { ...x, readAt: new Date().toISOString() } : x), contacts: s.qq.contacts.map(c => c.id === peer ? { ...c, unread: 0 } : c) } })),
  setConnection: (connection) => set((s) => ({
    connection,
    failures: connection === 'online' ? 0 : s.failures + (connection === 'offline' ? 1 : 0),
  })),
}))

/** 自己之外的 player（兼容旧调用） */
export const selectOthers = (s: GameStore) =>
  s.myPlayerId ? s.players.filter(p => p.id !== s.myPlayerId) : s.players
