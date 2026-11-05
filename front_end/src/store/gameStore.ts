import { create } from 'zustand'
import type {
  Player, WorldState, ActionLogEntry, Tile, OtherPlayer, GameObject,
  PlayerStateVars, ChatBubble, ConnectionStatus,
} from '../types'

export type AppMode = 'play' | 'spectate'

interface GameStore {
  mode: AppMode
  player: Player | null
  worldState: WorldState | null
  actionLog: ActionLogEntry[]
  tiles: Tile[]
  objects: GameObject[]
  myPlayerId: string | null
  /** 所有 player（含自己）；GameScene 自行过滤 */
  players: OtherPlayer[]
  /** 旁观目标等需要七变量的人：id → /player/{id}/state */
  playerVars: Record<string, PlayerStateVars>
  bubbles: ChatBubble[]
  connection: ConnectionStatus
  /** 连续失败次数，用于 UI 显示与退避 */
  failures: number
  /** 后端 /world 快照时间（performance.now），用于插值 */
  lastWorldAt: number

  setMode: (m: AppMode) => void
  setPlayer: (p: Player | null) => void
  setWorldState: (ws: WorldState) => void
  setActionLog: (log: ActionLogEntry[]) => void
  setTiles: (tiles: Tile[]) => void
  setObjects: (objects: GameObject[]) => void
  setMyPlayerId: (id: string | null) => void
  setPlayers: (players: OtherPlayer[]) => void
  setPlayerVars: (id: string, vars: PlayerStateVars | null) => void
  pushBubble: (entityId: string, content: string, ttlMs?: number) => void
  pruneBubbles: (now: number) => void
  setConnection: (c: ConnectionStatus) => void
}

export const BUBBLE_TTL_MS = 8000

export const useGameStore = create<GameStore>((set, get) => ({
  mode: 'play',
  player: null,
  worldState: null,
  actionLog: [],
  tiles: [],
  objects: [],
  myPlayerId: null,
  players: [],
  playerVars: {},
  bubbles: [],
  connection: 'connecting',
  failures: 0,
  lastWorldAt: 0,

  setMode: (mode) => set({ mode }),
  setPlayer: (player) => set({ player }),
  setWorldState: (worldState) => set({ worldState }),
  setActionLog: (actionLog) => set({ actionLog }),
  setTiles: (tiles) => set({ tiles }),
  setObjects: (objects) => set({ objects }),
  setMyPlayerId: (myPlayerId) => set({ myPlayerId }),
  setPlayers: (players) => set({ players, lastWorldAt: performance.now() }),
  setPlayerVars: (id, vars) => set((s) => {
    const next = { ...s.playerVars }
    if (vars) next[id] = vars
    else delete next[id]
    return { playerVars: next }
  }),
  pushBubble: (entityId, content, ttlMs = BUBBLE_TTL_MS) => set((s) => ({
    bubbles: [
      ...s.bubbles.filter(b => b.entityId !== entityId),
      { entityId, content, until: performance.now() + ttlMs },
    ],
  })),
  pruneBubbles: (now) => {
    const cur = get().bubbles
    if (cur.length === 0) return
    const next = cur.filter(b => b.until > now)
    if (next.length !== cur.length) set({ bubbles: next })
  },
  setConnection: (connection) => set((s) => ({
    connection,
    failures: connection === 'online' ? 0 : s.failures + (connection === 'offline' ? 1 : 0),
  })),
}))

/** 自己之外的 player（兼容旧调用） */
export const selectOthers = (s: GameStore) =>
  s.myPlayerId ? s.players.filter(p => p.id !== s.myPlayerId) : s.players
