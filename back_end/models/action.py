from pydantic import BaseModel
from typing import Optional, Literal
from models.world import Position


class MoveRequest(BaseModel):
    playerId: str
    direction: Optional[Literal["up", "down", "left", "right"]] = None
    targetTile: Optional[Position] = None


class MoveResponse(BaseModel):
    success: bool
    facing: str                   # 无论成败都返回新朝向
    position: Optional[Position] = None
    state: Optional[str] = None
    reason: Optional[str] = None


class TurnRequest(BaseModel):
    playerId: str
    direction: Literal["up", "down", "left", "right"]


class TurnResponse(BaseModel):
    facing: str


class InteractRequest(BaseModel):
    playerId: str


class InteractResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    playerState: Optional[str] = None
    reason: Optional[str] = None
