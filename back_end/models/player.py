from pydantic import BaseModel
from typing import Literal, Optional, List
from models.world import Position


class PlayerProfile(BaseModel):
    id: str
    name: str
    age: int


class Buff(BaseModel):
    key: str
    value: float = 0.0
    mode: Literal["persistent", "timed"]
    remaining: Optional[float] = None  # None = 永久（persistent）；毫秒 = 剩余时间（timed）
    source: str                         # 来源 object id


class Player(BaseModel):
    id: str
    position: Position
    facing: Literal["up", "down", "left", "right"]
    state: Literal["idle", "walking", "requesting_talk", "talking", "using"]
    stateLabel: Optional[str] = None
    hp: float
    energy: float
    usingObjectId: Optional[str] = None
    buffs: List[Buff] = []
    tags: List[str] = []
    canMove: bool = True
    canInteract: bool = True
    canUse: bool = True
    moveSpeed: float = 1.0
    pendingMessage: Optional[str] = None
