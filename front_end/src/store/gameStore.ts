import { create } from 'zustand'
import { Player, WorldState, ActionLogEntry, Tile } from '../types'

interface GameStore {
  player: Player | null
  worldState: WorldState | null
  actionLog: ActionLogEntry[]
  tiles: Tile[]
  setPlayer: (p: Player) => void
  setWorldState: (ws: WorldState) => void
  setActionLog: (log: ActionLogEntry[]) => void
  setTiles: (tiles: Tile[]) => void
}

export const useGameStore = create<GameStore>((set) => ({
  player: null,
  worldState: null,
  actionLog: [],
  tiles: [],
  setPlayer: (player) => set({ player }),
  setWorldState: (worldState) => set({ worldState }),
  setActionLog: (actionLog) => set({ actionLog }),
  setTiles: (tiles) => set({ tiles }),
}))
