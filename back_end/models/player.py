from pydantic import BaseModel
from typing import Literal, Optional
from models.world import Position


class Player(BaseModel):
    id: str
    position: Position
    facing: Literal["up", "down", "left", "right"]
    state: str   # "idle" | "moving" | 自定义文字（如 "player_01 正在睡觉"）
    hp: int
    energy: int
    usingObjectId: Optional[str] = None
