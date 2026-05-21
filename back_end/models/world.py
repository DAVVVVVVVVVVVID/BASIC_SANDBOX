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
    class Config:
        extra = "allow"

    type: str
    key: str
    value: Optional[float] = None


class GameObject(BaseModel):
    id: str
    type: str
    prototype: str
    name: str
    position: Position
    tiles: Optional[List[Position]] = None
    sprite: Optional[str] = None
    interactable: bool
    description: str
    effects: List[Effect]
    successMessage: Optional[str] = None
    failureMessage: Optional[str] = None
    currentUsers: int
    userList: List[str]
    # continuous 专有（instant 对象为 None）
    maxUsers: Optional[int] = None
    useStateLabel: Optional[str] = None
    maxDuration: Optional[float] = None
    leaveMessage: Optional[str] = None


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
