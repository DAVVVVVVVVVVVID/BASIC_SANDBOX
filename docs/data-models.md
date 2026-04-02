# 数据模型设计

## 1. 世界结构层级

```
world → section → arena → tile
```

| 层级 | 说明 | 示例 |
|------|------|------|
| world | 整个游戏世界 | 镇（Town） |
| section | 区域 | 村庄、森林 |
| arena | 子区域 | 房间、院子 |
| tile | 最小格子单位 | 单格地面 |

---

## 2. Tile

```typescript
type Tile = {
  x: number           // tile 列坐标
  y: number           // tile 行坐标
  walkable: boolean   // 是否可行走
  objectId?: string   // 该 tile 上的 object（可选）
}
```

### 坐标转换

```typescript
// 像素 → tile
tileX = Math.floor(pixelX / tileSize)
tileY = Math.floor(pixelY / tileSize)

// tile → 像素（左上角）
pixelX = tileX * tileSize
pixelY = tileY * tileSize

// tile → 所属区域
getTileArea(tile) → { worldId, sectionId, arenaId }
```

---

## 3. Object（场景对象）

```typescript
type GameObject = {
  id: string
  name: string
  position: { x: number; y: number }   // tile 坐标
  interactable: boolean
  description: string                   // 交互返回文本
}
```

**行为规则：**
- 玩家与 object 相邻（上下左右任意一格，曼哈顿距离 = 1）时可交互
- 按 `I` 键触发交互，返回 `description` 文本

---

## 4. 玩家（Player）

```typescript
type Player = {
  id: string
  position: { x: number; y: number }            // tile 坐标
  facing: "up" | "down" | "left" | "right"      // 当前朝向
  state: "idle" | "moving" | "interacting"
  hp: number                                     // 生命值，范围 0-100
  energy: number                                 // 体力值，范围 0-100
}
```

**朝向规则：**
- 由最后一次移动操作决定（无论目标格是否可行走）
- 键盘方向键：朝向 = 按键方向
- 鼠标点击：朝向 = 当前位置到目标格的主轴方向（取 |dx| 与 |dy| 较大者）
- 初始朝向：`"down"`

**状态说明：**

| 状态 | 触发条件 |
|------|----------|
| idle | 静止不动 |
| moving | 正在移动中 |
| interacting | 正在与 object 交互 |

---

## 5. 世界状态（WorldState）

```typescript
type WorldState = {
  date: string                            // 格式 "2001-12-30"
  time: string                            // 格式 "08:00"
  isDay: boolean                          // 是否白天
  weather: "sunny" | "cloudy" | "rain"   // 天气状态
}
```

---

## 6. 世界事件（WorldEvent）

```typescript
type WorldEvent = {
  id: string
  tiles: { x: number; y: number }[]   // 触发区域（tile 坐标集合）
  description: string                  // 事件提示文本
}
```

**行为规则：**
- 玩家进入 `tiles` 中任意一格 → 触发事件提示
- 仅展示效果，不影响游戏逻辑

---

## 7. Python 后端模型（Pydantic）

```python
from pydantic import BaseModel
from typing import Literal, Optional, List

class Position(BaseModel):
    x: int
    y: int

class Tile(BaseModel):
    x: int
    y: int
    walkable: bool
    object_id: Optional[str] = None

class GameObject(BaseModel):
    id: str
    name: str
    position: Position
    interactable: bool
    description: str

class Player(BaseModel):
    id: str
    position: Position
    facing: Literal["up", "down", "left", "right"]
    state: Literal["idle", "moving", "interacting"]
    hp: int
    energy: int

class WorldState(BaseModel):
    date: str
    time: str
    is_day: bool
    weather: Literal["sunny", "cloudy", "rain"]

class WorldEvent(BaseModel):
    id: str
    tiles: List[Position]
    description: str
```
