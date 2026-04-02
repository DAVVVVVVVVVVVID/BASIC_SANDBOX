from pydantic import BaseModel
from typing import Literal


class Position(BaseModel):
    x: int
    y: int


class Player(BaseModel):
    id: str
    position: Position
    facing: Literal["up", "down", "left", "right"]
    state: Literal["idle", "moving", "interacting"]
    hp: int
    energy: int
