import { create } from 'zustand'
import { Player, WorldState } from '../types'

interface GameStore {
  player: Player | null
  worldState: WorldState | null
  setPlayer: (p: Player) => void
  setWorldState: (ws: WorldState) => void
}

export const useGameStore = create<GameStore>((set) => ({
  player: null,
  worldState: null,
  setPlayer: (player) => set({ player }),
  setWorldState: (worldState) => set({ worldState }),
}))
