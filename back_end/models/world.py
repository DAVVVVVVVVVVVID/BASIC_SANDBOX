from pydantic import BaseModel
from typing import Literal, Optional, List


class Position(BaseModel):
    x: int
    y: int


class Tile(BaseModel):
    x: int
    y: int
    type: str
    walkable: bool
    objectId: Optional[str] = None


class GameObject(BaseModel):
    id: str
    type: str
    name: str
    position: Position
    tiles: Optional[List[Position]] = None
    sprite: Optional[str] = None
    interactable: bool
    description: str


class WorldState(BaseModel):
    date: str
    time: str
    isDay: bool
    weather: Literal["sunny", "cloudy", "rain"]


class WorldEvent(BaseModel):
    id: str
    tiles: List[Position]
    description: str


class WorldData(BaseModel):
    tiles: List[Tile]
    objects: List[GameObject]
    worldState: WorldState
