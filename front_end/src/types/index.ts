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

export interface GameObject {
  id: string
  type: string
  name: string
  position: Position
  tiles?: Position[]
  sprite?: string
  interactable: boolean
  description: string
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
  state: 'idle' | 'moving' | 'interacting'
  hp: number
  energy: number
}
