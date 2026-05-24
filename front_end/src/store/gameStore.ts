import { create } from 'zustand'
import { Player, WorldState, ActionLogEntry, Tile, OtherPlayer } from '../types'

interface GameStore {
  player: Player | null
  worldState: WorldState | null
  actionLog: ActionLogEntry[]
  tiles: Tile[]
  myPlayerId: string | null
  otherPlayers: OtherPlayer[]
  setPlayer: (p: Player) => void
  setWorldState: (ws: WorldState) => void
  setActionLog: (log: ActionLogEntry[]) => void
  setTiles: (tiles: Tile[]) => void
  setMyPlayerId: (id: string) => void
  setOtherPlayers: (players: OtherPlayer[]) => void
}

export const useGameStore = create<GameStore>((set) => ({
  player: null,
  worldState: null,
  actionLog: [],
  tiles: [],
  myPlayerId: null,
  otherPlayers: [],
  setPlayer: (player) => set({ player }),
  setWorldState: (worldState) => set({ worldState }),
  setActionLog: (actionLog) => set({ actionLog }),
  setTiles: (tiles) => set({ tiles }),
  setMyPlayerId: (myPlayerId) => set({ myPlayerId }),
  setOtherPlayers: (otherPlayers) => set({ otherPlayers }),
}))
