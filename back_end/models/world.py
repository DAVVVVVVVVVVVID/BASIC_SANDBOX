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
    world:    Optional[str] = None
    sector:   Optional[str] = None
    arena:    Optional[str] = None


class Effect(BaseModel):
    type: str
    key: str
    value: Optional[float] = None


class GameObject(BaseModel):
    id: str
    type: str
    name: str
    position: Position
    tiles: Optional[List[Position]] = None
    sprite: Optional[str] = None
    interactable: bool
    description: str
    maxUsers: int
    currentUsers: int
    userList: List[str]
    useStateLabel: str
    effects: List[Effect]


class WorldState(BaseModel):
    date: str
    time: str
    period: Literal["morning", "day", "dusk", "night"]
    running: bool
    speed: float
    weather: Literal["sunny", "cloudy", "rain"]


class WorldEvent(BaseModel):
    id: str
    tiles: List[Position]
    description: str


class WorldData(BaseModel):
    tiles: List[Tile]
    objects: List[GameObject]
    worldState: WorldState
