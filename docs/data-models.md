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

采用**类型 + 实例分离**架构：
- 类型定义在 `back_end/game/object_types.py`（名称、尺寸、贴图、描述）
- 实例只存 `id`、`type`、`position`，其余字段自动补全

```typescript
type GameObject = {
  id: string
  type: string                          // 对应 OBJECT_TYPES 中的类型键
  name: string
  position: { x: number; y: number }   // 锚点坐标（左上角）
  tiles: { x: number; y: number }[]    // 占据的所有格子（自动生成）
  sprite?: string                       // 贴图文件名（不含 .png）
  interactable: boolean
  description: string                   // I 键阅读的描述文本
  maxUsers: number                      // 最多同时使用人数
  currentUsers: number                  // 当前使用人数（运行时）
  userList: string[]                    // 当前使用者 ID 列表（运行时）
  useStateLabel: string                 // 使用中状态文字模板，"{entity}" 替换为实体名
  effects: { type: string; key: string; value?: number }[]  // buff/tag，当前仅展示
}
```

**派生字段（不存储，实时计算）：**
- `available = currentUsers < maxUsers`

**行为规则：**

| 键 | Action | 说明 |
|----|--------|------|
| `I` | `interact` | 读取描述信息，不改变任何状态 |
| `E` | `use` | 进入使用，校验 available，加入 userList，玩家 state 改为 useStateLabel 渲染文字 |
| `Q` | `leave` | 退出使用，从 userList 移除，玩家 state 恢复 idle |

`use` 失败时 reason 为 `object_full`，响应含 `currentUsers` / `maxUsers` 供前端展示。

---

## 4. 玩家（Player）

玩家数据分为两层：**静态档案**（不随运行时变化）和**运行时状态**（动态变化）。

### 静态档案（PlayerProfile）

```typescript
type PlayerProfile = {
  id: string
  name: string    // 角色名称，用于 useStateLabel 中 {entity} 替换
  age: number     // 角色年龄
}
```

### 运行时状态（Player）

```typescript
type Player = {
  id: string
  position: { x: number; y: number }        // tile 坐标
  facing: "up" | "down" | "left" | "right"  // 当前朝向
  state: PlayerState                         // 系统枚举状态
  stateLabel: string | null                  // 展示文字，仅 state == "using" 时有值
  hp: number                                 // 生命值，范围 0-100
  energy: number                             // 体力值，范围 0-100
  usingObjectId: string | null               // 当前使用的 object id
  buffs: Buff[]                              // 当前 buff 实例列表
  tags: string[]                             // 当前 tag 列表
  // 状态控制字段（每 tick 重置为 true，buff handler 可设为 false）
  canMove: boolean
  canInteract: boolean
  canUse: boolean
  moveSpeed: number                          // 移速倍率，默认 1.0
}

type PlayerState = "idle" | "walking" | "requesting_talk" | "talking" | "using"

type Buff = {
  key: string
  value: number
  mode: "while_active" | "instant"
  remaining: number | null    // null = 永久（while_active），毫秒 = 剩余时间（instant）
  source: string              // 来源 object id
}
```

**状态说明：**

| state | 说明 |
|-------|------|
| `idle` | 静止 |
| `walking` | 移动中 |
| `requesting_talk` | 发起对话请求 |
| `talking` | 对话中 |
| `using` | 正在使用 object，stateLabel 有值 |

**stateLabel 规则：**
- `state != "using"` 时：`stateLabel = null`
- `state == "using"` 时：`stateLabel = useStateLabel.replace("{entity}", profile.name)`
- 前端展示：优先显示 `stateLabel`，否则显示 `state`

**朝向规则：**
- 由最后一次移动操作决定（无论目标格是否可行走）
- 键盘方向键：朝向 = 按键方向
- 鼠标点击：朝向 = 当前位置到目标格的主轴方向（取 |dx| 与 |dy| 较大者）
- 初始朝向：`"down"`

**Buff 系统说明：**

Buff 分三类，处理位置和机制不同：

| 类型 | 代表 key | 处理位置 | 机制 |
|------|---------|---------|------|
| 属性修改型 | `energy_regen`、`hp_regen` | 后端 tick | 每 tick 直接修改 player.energy / hp |
| 状态控制型 | `no_move`、`no_interact`、`no_use` | 后端 action 校验 | tick 重置为 true，handler 设为 false，action 执行前校验 |
| 行为参数型 | `move_speed` | 前后端协作 | tick 计算倍率写入 `moveSpeed`，前端据此调整 MOVE_INTERVAL |

**当前支持的 buff key：**

| key | 类型 | value 含义 |
|-----|------|-----------|
| `energy_regen` | 属性修改型 | 每 tick 恢复体力值 |
| `hp_regen` | 属性修改型 | 每 tick 恢复生命值 |
| `no_move` | 状态控制型 | 无（value 忽略），禁止移动 |
| `no_interact` | 状态控制型 | 无，禁止 I 键物品描述交互 |
| `no_use` | 状态控制型 | 无，禁止 E 键使用物品 |
| `move_speed` | 行为参数型 | 倍率（0.5 = 减速，2.0 = 加速） |

**Buff 生命周期：**
- `while_active`：进入 object 时创建，`remaining = null`；离开时（同 source）清除
- `instant`：进入 object 时创建，`remaining = duration`；tick 递减，归零自动移除；离开 object 不清除；同 source + 同 key 再次进入时覆盖（重置 remaining）

**Tick 执行顺序（每 200ms）：**
1. 递减 `instant` buff 的 `remaining`，移除归零项
2. 重置：`canMove = true`、`canInteract = true`、`canUse = true`、`moveSpeed = 1.0`
3. 遍历所有 buff，调用对应 Effect Handler
4. handler 修改 player 属性（energy、hp、canMove 等）

**tag 说明：**
- 纯标记字符串，如 `"sleeping"`、`"cooking"`
- 来源：进入 object 时从 effects 复制，离开时清除
- 当前仅展示，不参与运算

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
    type: str
    name: str
    position: Position
    tiles: Optional[List[Position]] = None
    sprite: Optional[str] = None
    interactable: bool
    description: str
    max_users: int
    current_users: int
    user_list: List[str]
    use_state_label: str
    effects: List[dict]

class PlayerProfile(BaseModel):
    id: str
    name: str
    age: int

class Buff(BaseModel):
    key: str
    value: float
    mode: Literal["while_active", "instant"]
    remaining: Optional[float] = None  # None = 永久；毫秒 = 剩余时间
    source: str                        # 来源 object id

class Player(BaseModel):
    id: str
    position: Position
    facing: Literal["up", "down", "left", "right"]
    state: Literal["idle", "walking", "requesting_talk", "talking", "using"]
    stateLabel: Optional[str] = None
    hp: int
    energy: int
    usingObjectId: Optional[str] = None
    buffs: List[Buff] = []
    tags: List[str] = []
    canMove: bool = True
    canInteract: bool = True
    canUse: bool = True
    moveSpeed: float = 1.0

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
