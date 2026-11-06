from pydantic import BaseModel
from typing import Dict, Literal, Optional, List
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
    state: Literal["idle", "walking", "requesting_talk", "walking_over", "talking", "using"]
    stateLabel: Optional[str] = None
    # ── 需求值（七变量，ARCHITECTURE §2.5 / B3），范围 0–100 ──
    hp: float                                   # fullness 的别名（过渡一个版本后删除，假设）
    energy: float
    fullness: float = 70.0
    social: float = 60.0
    fun: float = 60.0
    mood: float = 65.0
    mood_base: float = 65.0                     # mood 指数回归基线（B4）
    emotion_tags: List[Buff] = []               # 复用 Buff 模型，mode="timed"
    closeness: Dict[str, float] = {}            # entity_id -> 0–100
    controller: Literal["human", "agent"] = "human"
    online: bool = True                         # B6：agent 10 s 无心跳标 False，不删除
    away: bool = False                          # W8 Q0e：human 120 s 无输入；agent 恒 False
    scene: Literal["sandbox", "live"] = "sandbox"   # B4：衰减速率按 scene
    agent_id: Optional[str] = None              # 自我层 agent id（controller=agent 时）
    last_tick_ts: str = ""                      # 上次 tick 的游戏时刻，ISO 8601（§3.7 裁定 3）
    usingObjectId: Optional[str] = None
    buffs: List[Buff] = []
    tags: List[str] = []
    canMove: bool = True
    canInteract: bool = True
    canUse: bool = True
    moveSpeed: float = 1.0
    pendingMessage: Optional[str] = None
    game: Optional[dict] = None                 # B18：游戏机局内状态
    pos_seq: int = 0
