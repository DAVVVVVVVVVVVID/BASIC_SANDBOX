# 开发指南

## 1. 项目概览

2D 像素风格沙盒游戏，前后端分离架构。前端负责渲染与输入，后端负责所有游戏逻辑与状态管理。

```
浏览器（React + Phaser）  ←HTTP REST→  Python FastAPI
```

- 前端端口：`http://localhost:5173`
- 后端端口：`http://localhost:8000`
- API 文档：`http://localhost:8000/docs`（FastAPI 自动生成）

---

## 2. 前端基本情况

**技术栈**：React 18 + TypeScript + Phaser 3 + Zustand

**目录结构**：
```
front_end/src/
├── App.tsx                        # 根组件，初始化游戏，挂载 UI
├── api/world.ts                   # 所有后端接口调用（sendAction、fetchHistory …）
├── store/gameStore.ts             # Zustand 全局状态（player、worldState、actionLog）
├── types/index.ts                 # TypeScript 类型定义
├── game/
│   ├── PhaserGame.ts              # Phaser 实例初始化
│   ├── EventBus.ts                # Phaser ↔ React 事件通信
│   ├── scenes/GameScene.ts        # 主游戏场景
│   ├── map/TileMap.ts             # Tile 渲染 + 坐标转换 + TileType 定义表
│   ├── objects/
│   │   ├── Player.ts              # 玩家精灵
│   │   └── GameObjectSprite.ts    # 场景对象精灵（tooltip 含使用人数）
│   └── systems/
│       ├── InputSystem.ts         # 键盘/鼠标输入处理（含 BFS 寻路）
│       └── TickSystem.ts          # 200ms 轮询同步（world、player、history）
└── ui/
    ├── HUD.tsx                    # 玩家完整状态面板（档案、HP/Energy、buffs/tags，instant buff 本地倒计时）
    ├── ActionLog.tsx              # 左下角行为日志面板（最多 20 条）
    ├── WorldInfoPanel.tsx         # 时间 / 天气 / 时段面板
    ├── TimeControlPanel.tsx       # 右下角时间控制面板（▶⏸ 开关、加减速、重置、倍率显示）
    └── InteractionPanel.tsx       # 交互文本弹窗
```

**静态资源**：
```
front_end/public/assets/
├── tiles/     # Tile 贴图（grass.png、wall.png、floor.png …）
└── sprites/   # 对象精灵（sofa.png、bed.png …）
```

---

## 3. 后端基本情况

**技术栈**：Python 3.11+ + FastAPI + uv

**目录结构**：
```
back_end/
├── main.py                # FastAPI 入口，注册路由，配置 CORS
├── pyproject.toml         # uv 项目依赖
├── routers/
│   ├── world.py           # GET /world（返回前推进游戏时间）
│   ├── player.py          # GET /player（调用 buff tick 后返回）
│   ├── actions.py         # POST /action（统一入口 + Dispatcher）
│   ├── history.py         # GET /history（行为日志）
│   ├── time_control.py    # POST /time/toggle|speed|reset（时间控制）
│   └── events.py          # GET /events
├── models/
│   ├── world.py           # Pydantic 数据模型（Tile、GameObject、WorldState …）
│   ├── player.py          # Player / PlayerProfile / Buff 模型
│   └── action.py          # ActionRequest / ActionResponse
└── game/
    ├── world_state.py     # 游戏状态管理（唯一可信数据源）
    ├── time_state.py      # 游戏时间状态（advance_time、TIME_SPEED、昼夜计算）
    ├── object_types.py    # Object 类型定义表（name、size、effects …）
    ├── action_log.py      # 行为日志（内存，最多 20 条）
    ├── buff_tick.py       # Buff Tick 引擎（EFFECT_HANDLERS 注册表）
    └── maps/              # 所有地图数据（地形 + 区域 + 认知地图）
        ├── map_data.py        # 地形字符图
        ├── world_map.py       # World 层区域字符图 + WORLD_CHARS
        ├── sector_map.py      # Sector 层区域字符图 + SECTOR_CHARS
        ├── arena_map.py       # Arena 层区域字符图 + ARENA_CHARS
        └── cognitive_map.py   # 认知地图语义树（worlds → sectors → arenas，零坐标）
```

---

## 4. 项目启动方法

### 后端

```bash
cd back_end
uv sync                          # 安装依赖（首次）
uv run uvicorn main:app --reload # 启动，监听 localhost:8000
```

### 前端

```bash
cd front_end
npm install                      # 安装依赖（首次）
npm run dev                      # 启动，监听 localhost:5173
```

---

## 5. Tile 类型的增删改

Tile 类型定义分两层：**后端**控制类型名与可行走默认值，**前端**控制对应贴图。

### 新增 Tile 类型

**步骤 1 — 后端** `back_end/game/world_state.py`：

```python
TILE_TYPES: dict[str, dict] = {
    "grass":          {"walkable_default": True},
    "wall":           {"walkable_default": False},
    "floor":          {"walkable_default": True},
    "floor_occupied": {"walkable_default": False},
    "water":          {"walkable_default": False},  # 新增
}

CHAR_TO_TYPE: dict[str, str] = {
    "#": "wall",
    ".": "grass",
    "f": "floor",
    "F": "floor_occupied",
    "~": "water",              # 新增：地图字符 → 类型名
}
```

**步骤 2 — 前端** `front_end/src/game/map/TileMap.ts`：

```typescript
export const TILE_TYPE_DEFS: Record<string, TileTypeDef> = {
  grass:          { sprite: 'tile_grass',  fallbackColor: 0x4a7c59 },
  wall:           { sprite: 'tile_wall',   fallbackColor: 0x5c3d2e },
  floor:          { sprite: 'tile_floor',  fallbackColor: 0xc8a96e },
  floor_occupied: { sprite: 'tile_floor',  fallbackColor: 0x9e7c4a },
  water:          { sprite: 'tile_water',  fallbackColor: 0x3182ce },  // 新增
}
```

**步骤 3**：将贴图 `water.png` 放入 `front_end/public/assets/tiles/`。

### 删除 Tile 类型

在 `TILE_TYPES`、`CHAR_TO_TYPE`（后端）和 `TILE_TYPE_DEFS`（前端）各删除对应条目。确认地图字符串中没有使用该字符。

### 修改 Tile 类型

直接修改对应条目的 `walkable_default`（后端）或 `sprite` / `fallbackColor`（前端）。

---

## 6. Tile 的增删改（地图编辑）

地图在 `back_end/game/map_data.py` 中以字符串二维数组定义，每个字符对应一个 tile。

### 字符对照表

| 字符 | 类型 | 可行走 |
|------|------|--------|
| `#` | wall | 否 |
| `.` | grass | 是 |
| `f` | floor | 是 |
| `F` | floor_occupied | 否 |

### 编辑规则

- 每行长度必须相同（= 地图宽度）
- 行数 = 地图高度，两者由字符串自动推导，无需手动设置
- 地图左上角为坐标原点 `(0, 0)`，x 向右，y 向下

```python
MAP: list[str] = [
    "##########",   # y=0
    "#ffffffff#",   # y=1
    "#f######f#",   # y=2
    "##########",   # y=3
]
```

### 运行时修改单个 Tile

```python
from game.world_state import set_tile_type
set_tile_type(x=3, y=2, new_type="wall")
```

---

## 7. Object 类型的增删改

Object 采用**类型 + 实例分离**架构。类型定义在 `back_end/game/object_types.py`，实例只存坐标，运行时状态（`currentUsers`、`userList`）在 `_build_objects()` 中自动补充。

**贴图尺寸规则**：`像素尺寸 / TILE_SIZE = 占用格数`。当前 `TILE_SIZE = 32`。例如 64×32 的图片对应 `size: (2, 1)`。

### 字段说明

| 字段 | 层级 | 说明 |
|------|------|------|
| `name` | 类型 | 显示名称 |
| `interactable` | 类型 | 是否可交互（I 键阅读描述） |
| `description` | 类型 | I 键返回的描述文本 |
| `size` | 类型 | `(width, height)`，单位 tile |
| `sprite` | 类型 | 贴图文件名（不含 .png），None 表示无贴图 |
| `max_users` | 类型 | 最多同时使用人数 |
| `use_state_label` | 类型 | E 键使用后玩家状态文字，`{entity}` 替换为实体名 |
| `effects` | 类型 | buff/tag 列表，进入时生效，离开时（while_active）清除 |
| `currentUsers` | 实例运行时 | 当前使用人数，自动初始化为 0 |
| `userList` | 实例运行时 | 当前使用者 ID 列表，自动初始化为 [] |

### effects 字段格式

```python
"effects": [
    # buff：进入时创建 buff 实例，驱动玩家属性
    {"type": "buff", "key": "energy_regen", "value": 1, "mode": "while_active"},
    {"type": "buff", "key": "no_move",                  "mode": "while_active"},
    # instant buff：进入时触发，duration 毫秒后自动消失（离开 object 不清除）
    {"type": "buff", "key": "hp_regen", "value": 2, "mode": "instant", "duration": 5000},
    # tag：纯标记，仅展示，不参与运算
    {"type": "tag",  "key": "sleeping",                 "mode": "while_active"},
]
```

**支持的 buff key：**

| key | 效果 | value 含义 |
|-----|------|-----------|
| `energy_regen` | 每 tick 恢复体力 | 恢复量（每 200ms） |
| `hp_regen` | 每 tick 恢复生命 | 恢复量 |
| `no_move` | 禁止移动 | 忽略 |
| `no_interact` | 禁止 I 键交互 | 忽略 |
| `no_use` | 禁止 E 键使用 | 忽略 |
| `move_speed` | 改变移速 | 倍率（0.5 = 减速，2.0 = 加速） |

新增 buff 效果只需在 `back_end/game/buff_tick.py` 的 `EFFECT_HANDLERS` 注册表里加一条 lambda，不修改 tick 主循环。

### 新增 Object 类型

在 `back_end/game/object_types.py` 的 `OBJECT_TYPES` 里加一条：

```python
"arcade": {
    "name":            "游戏机",
    "interactable":    True,
    "description":     "一台经典街机，投币即可游玩。",
    "size":            (1, 1),
    "sprite":          "arcade",
    "max_users":       1,
    "use_state_label": "{entity} 正在游玩游戏机",
    "effects": [
        {"type": "buff", "key": "no_move",     "mode": "while_active"},
        {"type": "buff", "key": "no_interact", "mode": "while_active"},
        {"type": "buff", "key": "no_use",      "mode": "while_active"},
        {"type": "tag",  "key": "gaming",      "mode": "while_active"},
    ],
},
```

将贴图放入 `front_end/public/assets/sprites/`，重启后端生效。

### 删除 Object 类型

从 `OBJECT_TYPES` 删除对应条目，确认 `_OBJECTS_RAW` 中没有实例引用该类型。

### 修改 Object 类型

直接修改 `OBJECT_TYPES` 中的字段，重启后端生效。

---

## 8. Object 的增删改

Object 实例在 `back_end/game/world_state.py` 的 `_OBJECTS_RAW` 列表中定义，**只需提供 id、type、position**，其余字段自动补全。

### 新增 Object 实例

```python
_OBJECTS_RAW = [
    {"id": "chair_01", "type": "chair", "position": {"x": 5, "y": 3}},
]
```

- `id`：唯一字符串
- `type`：必须是 `OBJECT_TYPES` 中已定义的类型
- `position`：锚点坐标（左上角），`tiles` 根据类型 `size` 自动展开

### 删除 Object 实例

从 `_OBJECTS_RAW` 删除对应条目，同时将地图上该位置的字符由 `F` 改回 `f` 或其他合适类型。

### 修改 Object 实例

- 改位置：修改 `position`，同步更新 `map_data.py` 中的字符
- 改属性（名字/描述/贴图）：修改 `object_types.py` 中的类型定义

---

## 9. 空间层级（World / Sector / Arena）

地图支持三级区域划分，每个 tile 可归属于 world（世界）、sector（区域）、arena（场馆）。层级稀疏，tile 可以只有 world 而没有 sector/arena，未归属字段为 `None`。

所有地图数据文件统一放在 `back_end/game/maps/` 子包。

### 数据来源分工

| 文件 | 职责 |
|------|------|
| `maps/cognitive_map.py` | 语义树：`worlds[] → sectors[] → arenas[]`，只存 id/name，零坐标 |
| `maps/world_map.py` | 字符网格：标记每个 tile 属于哪个 world；`WORLD_CHARS` 做字符映射 |
| `maps/sector_map.py` | 字符网格：标记每个 tile 属于哪个 sector；`SECTOR_CHARS` 做字符映射 |
| `maps/arena_map.py` | 字符网格：标记每个 tile 属于哪个 arena；`ARENA_CHARS` 做字符映射 |

三张区域图尺寸必须与 `maps/map_data.py` 完全一致，`.` 代表该层级未归属。

### 修改区域边界

直接修改对应字符图中的字符，不影响认知地图。

### 修改区域名称 / 增删区域

只修改 `maps/cognitive_map.py` 中的语义树，不影响字符图。字符图里的字符只是 ID，改名不需要动字符图。

### 一致性约束

有 arena 必须有 sector，有 sector 必须有 world。后端启动时 `_build_zone_lookup()` 自动校验，违反则抛出 `ValueError`。

### Object 的区域归属

Object 本身不存三级参数，运行时按其 `position` 对应的 tile 查询 `world / sector / arena` 即可。

### HUD 显示

前端 HUD 的"位置"行实时显示玩家当前 tile 的层级信息，格式为 `world / sector / arena`，未归属显示 `—`。

---

## 10. 地图的更新方法（map_data.py）

编辑 `back_end/game/map_data.py` 中的 `MAP` 字符串，保存后**重启后端**生效（后端启动时一次性解析地图）。

**有 Object 的格子**建议使用 `F`（floor_occupied），无 Object 的可行走地面使用 `f`（floor）或 `.`（grass），墙使用 `#`（wall）。

### 调整世界尺寸

世界尺寸由三个参数共同决定，修改时需保持一致：

| 参数 | 位置 | 说明 |
|------|------|------|
| 地图行列数 | `back_end/game/map_data.py` | 字符串行数 = 高度，每行字符数 = 宽度，自动推导 |
| Tile 像素大小 | `front_end/src/game/map/TileMap.ts` → `TILE_SIZE` | 每个 tile 渲染多少像素，当前 `32` |
| 画布尺寸 | `front_end/src/game/PhaserGame.ts` → `width` / `height` | 应等于 `地图宽度 × TILE_SIZE` 和 `地图高度 × TILE_SIZE` |

**示例：50 宽 × 25 高，tile 大小 32px**

```python
# map_data.py：每行 50 个字符，共 25 行
MAP = [
    "##################################################",  # × 25 行
    ...
]
```

```typescript
// TileMap.ts
export const TILE_SIZE = 32

// PhaserGame.ts
width: 50 * 32,   // 1600
height: 25 * 32,  // 800
```

> 画布尺寸不匹配时，地图右侧或底部会出现黑边，或 tile 被截断。

---

## 10. 世界事件的设置方法

世界事件在 `back_end/game/world_state.py` 的 `_EVENTS` 列表中定义。玩家每次移动后，前端检测新坐标是否命中任意事件的触发区域，命中则弹出提示。

```python
_EVENTS = [
    {
        "id": "event_01",               # 唯一 ID
        "tiles": [                       # 触发区域，可多格
            {"x": 5, "y": 3},
            {"x": 6, "y": 3},
        ],
        "description": "你进入了神秘区域。",   # 弹出的提示文本
    },
]
```

> 事件只做展示，不影响游戏逻辑（不阻止移动、不修改状态）。

---

## 11. 角色参数

玩家数据分为两部分，均在 `back_end/game/world_state.py` 中定义。

### 静态档案（不随运行时变化）

```python
_player_profile = {
    "id":   "player_01",
    "name": "玩家",        # 角色名称，用于 useStateLabel 中 {entity} 替换
    "age":  25,
}
```

### 运行时状态（动态变化）

```python
_player = {
    "id":            "player_01",
    "position":      {"x": 2, "y": 2},   # 初始位置
    "facing":        "down",              # 初始朝向：up/down/left/right
    "state":         "idle",              # 系统枚举状态（见下表）
    "stateLabel":    None,                # 展示文字，仅 state == "using" 时有值
    "hp":            100.0,               # 生命值（0-100，float，buff tick 实时修改）
    "energy":        80.0,                # 体力值（0-100，float，buff tick 实时修改）
    "usingObjectId": None,                # 当前使用的 object id
    "buffs":         [],                  # 当前 buff 实例列表（含 mode/remaining/source）
    "tags":          [],                  # 当前 tag 列表
    # 状态控制字段：每次 GET /player 前 tick 重置为 True，buff handler 可覆盖
    "canMove":       True,
    "canInteract":   True,
    "canUse":        True,
    "moveSpeed":     1.0,                 # 移速倍率，前端据此调整移动间隔
}
```

**朝向规则**：由最后一次移动操作决定，无论目标格是否可行走。

**state 枚举说明**：

| state | 说明 |
|-------|------|
| `idle` | 静止 |
| `walking` | 移动中 |
| `requesting_talk` | 发起对话请求 |
| `talking` | 对话中 |
| `using` | 正在使用 object |

**stateLabel 规则**：
- `state != "using"` 时为 `None`
- `state == "using"` 时由 object 的 `useStateLabel` 生成，`{entity}` 替换为角色名称
- 例：`"玩家 正在沙发上休息"`

**Buff 生命周期**：
- `while_active`：E 键进入时创建，Q 键离开后立即清除
- `instant`：进入时创建，`remaining = duration`；每 tick 递减，归零自动移除；离开 object 不清除

---

## 12. Buff 系统

### 整体结构

Buff 系统由三层组成：

```
object_types.py          →   world_state.py           →   buff_tick.py
effects（配置）              enter/leave_object（触发）     run_tick（运算）
```

- **effects**：配置在 `object_types.py` 每个 object 类型里，描述"这个 object 会施加什么效果"
- **enter/leave_object**：玩家 E/Q 键时，`world_state.py` 根据 effects 创建或清除玩家身上的 buff 实例
- **run_tick**：每次 `GET /player` 前执行，遍历玩家当前 buff 实例，调用 `EFFECT_HANDLERS` 修改玩家属性

### Buff 实例结构

玩家身上的每条 buff（`player["buffs"]` 列表）格式如下：

```python
{
    "key":       "energy_regen",   # 效果标识，对应 EFFECT_HANDLERS 注册表
    "value":     1.0,              # 数值（状态控制型忽略此字段）
    "mode":      "while_active",   # "while_active" | "instant"
    "remaining": None,             # while_active = None；instant = 剩余毫秒
    "source":    "sofa_01",        # 来源 object id，用于 leave 时精准清除
}
```

### Buff 分三类

| 类型 | 代表 key | 机制 |
|------|---------|------|
| 属性修改型 | `energy_regen`、`hp_regen` | tick 时直接修改 `player.energy` / `player.hp` |
| 状态控制型 | `no_move`、`no_interact`、`no_use` | tick 先重置为 True，handler 设为 False，action 执行前校验 |
| 行为参数型 | `move_speed` | tick 计算倍率写入 `moveSpeed`，前端据此调整移动间隔 |

### Tick 执行顺序（每 200ms，`GET /player` 触发）

```
① 递减 instant buff 的 remaining（-200ms），remaining ≤ 0 自动移除
② 重置：canMove=True、canInteract=True、canUse=True、moveSpeed=1.0
③ 遍历 player.buffs → 查 EFFECT_HANDLERS → 逐一执行 handler
```

**注意**：步骤 ② 在 ③ 之前，所以 `no_move` 等控制型 buff 每 tick 都会重新设值，不会因为重置而失效。

### Buff 生命周期

| mode | 创建时机 | 清除时机 |
|------|---------|---------|
| `while_active` | E 键进入 object | Q 键离开时，按 source + mode 匹配清除 |
| `instant` | E 键进入 object | tick 递减至 0 自动移除；离开 object **不**清除；再次进入同 source+key 时覆盖（重置 remaining） |

---

### 如何新增 Buff 类型

只需在 `back_end/game/buff_tick.py` 的 `EFFECT_HANDLERS` 里加一条：

```python
def _handler_hunger(player: dict, buff: dict, delta: float) -> None:
    player["energy"] = max(0.0, player["energy"] - buff["value"])

EFFECT_HANDLERS: dict = {
    # ... 现有条目 ...
    "hunger": _handler_hunger,   # 新增
}
```

之后在任意 object 的 `effects` 里使用 `"key": "hunger"` 即可生效。**不需要修改 tick 主循环**。

### 如何删除 Buff 类型

1. 从 `EFFECT_HANDLERS` 删除对应条目
2. 检查 `object_types.py` 中所有 object 的 `effects`，移除含该 key 的条目

> 如果 object 的 effects 里引用了不在 `EFFECT_HANDLERS` 里的 key，buff 实例仍会创建（HUD 展示），但不执行任何逻辑，不会报错。

### 如何修改 Buff 类型

直接修改 `EFFECT_HANDLERS` 中对应的 handler 函数体，重启后端生效。

---

### 如何给 Object 增删改 Buff

所有 object 的 buff 配置都在 `back_end/game/object_types.py` 的 `effects` 字段里，修改后**重启后端**生效。

**新增一条 buff：**
```python
# 在 effects 列表里追加
{"type": "buff", "key": "hp_regen", "value": 2, "mode": "while_active"},
```

**新增一条 instant buff（有时限）：**
```python
{"type": "buff", "key": "energy_regen", "value": 5, "mode": "instant", "duration": 3000},
# 进入后恢复 3 秒，离开后继续计时直到归零
```

**新增一条 tag（纯标记，不运算）：**
```python
{"type": "tag", "key": "cooking", "mode": "while_active"},
```

**删除一条 buff：** 直接从 `effects` 列表里删除对应的字典条目。

**修改 buff 数值：** 修改 `value` 或 `duration` 字段。

---

### Object 触发 Buff 的完整逻辑

**E 键（进入）— `enter_object(obj_id, entity_id)`：**

```
① 将 entity_id 加入 obj["userList"]，currentUsers +1
② 设置 player.state = "using"，stateLabel 由 useStateLabel 模板生成
③ 遍历 obj["effects"]：
    - type == "buff"：
        · 从 player.buffs 移除同 source + 同 key 的旧条目（覆盖逻辑）
        · 创建新 buff 实例，mode="while_active" → remaining=None；
          mode="instant" → remaining=duration
        · 追加到 player.buffs
    - type == "tag"：
        · 若 tag 不存在，追加到 player.tags
```

**Q 键（离开）— `leave_object(entity_id)`：**

```
① 从 obj["userList"] 移除 entity_id，currentUsers -1
② 从 player.buffs 移除所有 mode=="while_active" 且 source==obj_id 的条目
   （instant buff 保留，继续倒计时）
③ 从 player.tags 移除来源于该 object 的所有 tag
④ 重置 player.state = "idle"，stateLabel = None，usingObjectId = None
```

**Tick（每 200ms）— `run_tick(player, delta)`：**

```
① instant buff：remaining -= 200，≤0 移除
② 重置控制字段：canMove/canInteract/canUse = True，moveSpeed = 1.0
③ 遍历 player.buffs → EFFECT_HANDLERS[buff.key](player, buff, delta)
```

**Action 校验（在 Tick 之后的下一个 action）：**

```
handle_move    → 检查 player.canMove，False → 返回 reason: "move_disabled"
handle_interact → 检查 player.canInteract，False → 返回 reason: "interact_disabled"
handle_use     → 检查 player.canUse，False → 返回 reason: "use_disabled"
```

---

## 13. 玩家基本交互

| 操作 | 效果 |
|------|------|
| 方向键（单次/按住） | 移动，每 `300ms / moveSpeed` 一格 |
| Ctrl + 方向键 | 只改变朝向，不移动 |
| 鼠标左键点击 Tile | BFS 寻路后逐格移动 |
| `I` 键 | 读取正前方 Object 的 description（不改变状态） |
| `E` 键 | 进入正前方 Object 使用（校验 available + canUse） |
| `Q` 键 | 退出当前使用的 Object |
| 鼠标悬停 Object | 显示 `名称 (currentUsers/maxUsers)` tooltip |
| 移入世界事件区域 | 自动弹出事件提示文本 |
| 点击 / Esc | 关闭交互/事件弹窗 |

**交互条件**：I / E 键均要求玩家**面朝**目标 Object（正前方一格）。后端根据 `position + facing` 计算目标格，与 Object 的 `tiles` 比对。

**行为限制**：使用中角色默认携带 `no_move` / `no_interact` / `no_use` buff，方向键、I 键、E 键均返回失败，直到 Q 键离开后恢复。

---

## 13. 接口总结

Base URL：`http://localhost:8000`

### 查询接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/world` | 返回地图 tiles、objects、worldState |
| GET | `/player` | 执行 buff tick 后返回玩家完整状态（含 profile） |
| GET | `/events` | 返回世界事件列表 |
| GET | `/history` | 返回行为日志（最多 20 条） |

### 行为接口

所有行为统一走 `POST /action`，由后端 Dispatcher 根据 `type` 路由到对应 handler。

```json
// 请求体
{
    "entityId": "player_01",
    "action": { "type": "<type>", "payload": { ... } },
    "skipLog": false,
    "logLabel": "自定义日志文字"
}
```

**行为类型一览：**

| type | payload | 说明 |
|------|---------|------|
| `move` | `{direction?}` 或 `{targetTile?}` | 移动，校验 canMove |
| `turn` | `{direction}` | 只改变朝向 |
| `interact` | `{}` | I 键，读取正前方 Object 描述，校验 canInteract |
| `use` | `{}` | E 键，进入正前方 Object 使用，校验 canUse + available |
| `leave` | `{}` | Q 键，退出当前 Object |

### 响应格式

```json
// 成功
{ "success": true, "type": "move", "result": { "facing": "up", "position": {"x": 3, "y": 2} } }

// 失败
{ "success": false, "type": "move", "reason": "move_disabled" }
```

**常见 reason 值：**

| reason | 触发条件 |
|--------|---------|
| `tile_not_walkable` | 目标格不可行走 |
| `move_disabled` | 玩家携带 no_move buff |
| `no_object_in_front` | 正前方无 Object |
| `interact_disabled` | 玩家携带 no_interact buff |
| `object_full` | Object 已达 maxUsers |
| `use_disabled` | 玩家携带 no_use buff |
| `not_using_any_object` | Q 键时玩家未在使用任何 Object |

### 新增行为的步骤

1. 在 `models/action.py` 定义新 payload（如需要）
2. 在 `routers/actions.py` 实现 handler 函数
3. 在 `_HANDLERS` 字典中注册 `"type": handler`
4. 更新本文档行为类型一览表

**不需要**新增路由、修改前端请求封装。
