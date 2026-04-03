import { create } from 'zustand'
import { Player, WorldState, ActionLogEntry } from '../types'

interface GameStore {
  player: Player | null
  worldState: WorldState | null
  actionLog: ActionLogEntry[]
  setPlayer: (p: Player) => void
  setWorldState: (ws: WorldState) => void
  setActionLog: (log: ActionLogEntry[]) => void
}

export const useGameStore = create<GameStore>((set) => ({
  player: null,
  worldState: null,
  actionLog: [],
  setPlayer: (player) => set({ player }),
  setWorldState: (worldState) => set({ worldState }),
  setActionLog: (actionLog) => set({ actionLog }),
}))
