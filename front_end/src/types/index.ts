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
}

export interface Effect {
  type: string
  key: string
  value?: number
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
}

export interface WorldState {
  date: string
  time: string
  isDay: boolean
  weather: 'sunny' | 'cloudy' | 'rain'
}

export interface WorldData {
  tiles: Tile[]
  objects: GameObject[]
  worldState: WorldState
}

export type Facing = 'up' | 'down' | 'left' | 'right'

export interface WorldEvent {
  id: string
  tiles: Position[]
  description: string
}

export interface Player {
  id: string
  position: Position
  facing: Facing
  state: string
  hp: number
  energy: number
  usingObjectId: string | null
}

export interface ActionLogEntry {
  timestamp: string
  entityId: string
  type: string
  payload: Record<string, unknown>
  success: boolean
  reason: string | null
  label: string | null
}
