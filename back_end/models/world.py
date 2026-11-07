from pydantic import BaseModel
from typing import Any, Literal, Optional, List


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
    advertise: Optional[dict[str, float]] = None   # B5：广告值 {fullness|energy|social|fun|mood: 0–100}（关门时全 0）
    open: Optional[bool] = None                     # B20：当前是否营业（无营业时间的物品恒 true）
    opensAt: Optional[str] = None                   # B20：关门时下次开门 "HH:MM"，开门时 null
    openHours: Optional[List[List[str]]] = None     # B20：[["11:00","14:00"],["17:00","21:00"]]
    usePos: Optional[List[Position]] = None         # W10：使用者站位（绝对格，按使用顺序分配）；null = 原地
    useFacing: Optional[str] = None                 # W10：使用者朝向；null = 面向物品
    shop: Optional[List[dict]] = None               # W10 ④：商店物品 [{type,item,name,price,sell,stock}]；非商店 null
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
    mapVersion: Optional[str] = None     # E③：地图静态内容指纹
    town: Optional[str] = None           # W7 E：镇名（SANDBOX_TOWN）


class WorldEvent(BaseModel):
    id: str
    tiles: List[Position]
    description: str


class OtherPlayer(BaseModel):
    id: str
    name: str
    position: Position
    facing: str
    state: str
    controller: Optional[str] = None   # B6
    online: Optional[bool] = None      # B6
    agent_id: Optional[str] = None     # §3.11 A1
    away: Optional[bool] = None        # W8 Q0e：human 120 s 无输入
    stateLabel: Optional[str] = None   # E①
    usingObjectId: Optional[str] = None  # E①
    tags: List[str] = []               # E①
    pos_seq: int = 0                   # E⑥
    gold: Optional[int] = None         # W10 ④
    inventory: Optional[List[dict]] = None   # W10 ④：[{type, name, class, count, meta?}]


class WorldData(BaseModel):
    tiles: Optional[List[Tile]] = None          # ?fields= 瘦身时可省略（E③）
    objects: Optional[List[GameObject]] = None
    worldState: Optional[WorldState] = None
    players: Optional[List[OtherPlayer]] = None
    tiled: Optional[Any] = None
    zone_names: Optional[dict] = None    # W7 E：{world:{id:name}, sector:{...}, arena:{...}}
    map: Optional[dict] = None           # W9：{format, edges[], floors{}, access{}}
    decor: Optional[List[dict]] = None   # W10：装饰层
