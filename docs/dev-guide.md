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
├── api/world.ts                   # 所有后端接口调用
├── store/gameStore.ts             # Zustand 全局状态（player、worldState）
├── types/index.ts                 # TypeScript 类型定义
├── game/
│   ├── PhaserGame.ts              # Phaser 实例初始化
│   ├── EventBus.ts                # Phaser ↔ React 事件通信
│   ├── scenes/GameScene.ts        # 主游戏场景
│   ├── map/TileMap.ts             # Tile 渲染 + 坐标转换 + TileType 定义表
│   ├── objects/
│   │   ├── Player.ts              # 玩家精灵
│   │   └── GameObjectSprite.ts    # 场景对象精灵
│   └── systems/
│       ├── InputSystem.ts         # 键盘/鼠标输入处理
│       └── TickSystem.ts          # 200ms 轮询同步
└── ui/
    ├── HUD.tsx                    # HP / Energy 面板
    ├── WorldInfoPanel.tsx         # 时间 / 天气面板
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
│   ├── world.py           # GET /world
│   ├── player.py          # GET /player
│   ├── actions.py         # POST /action/move、/action/turn、/action/interact
│   └── events.py          # GET /events
├── models/
│   ├── world.py           # Pydantic 数据模型（Tile、GameObject、WorldState …）
│   ├── player.py          # Player 模型
│   └── action.py          # 请求/响应模型
└── game/
    ├── world_state.py     # 游戏状态管理（唯一可信数据源）
    └── map_data.py        # 地图字符串定义
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

Object 采用**类型 + 实例分离**架构。类型定义在 `back_end/game/object_types.py`，实例只存坐标，`tiles`、`name`、`sprite`、`description` 全部从类型定义自动生成。

**贴图尺寸规则**：`像素尺寸 / TILE_SIZE = 占用格数`。当前 `TILE_SIZE = 32`。例如 64×32 的图片对应 `size: (2, 1)`。

### 新增 Object 类型

在 `back_end/game/object_types.py` 的 `OBJECT_TYPES` 里加一条：

```python
OBJECT_TYPES: dict[str, dict] = {
    "chair": {
        "name": "椅子",
        "interactable": True,
        "description": "一把普通的木椅。",
        "size": (1, 1),       # (width, height)，单位 tile
        "sprite": "chair",    # 对应 assets/sprites/chair.png，None 表示无贴图
        "tags": ["furniture", "sit"],
    },
    # ...
}
```

将贴图放入 `front_end/public/assets/sprites/`。

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

## 9. 地图的更新方法

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

玩家状态在 `back_end/game/world_state.py` 的 `_player` 字典中定义：

```python
_player = {
    "id":       "player_01",
    "position": {"x": 2, "y": 2},           # 初始位置
    "facing":   "down",                      # 初始朝向：up/down/left/right
    "state":    "idle",                      # idle / moving / interacting
    "hp":       100,                         # 生命值（0-100）
    "energy":   80,                          # 体力值（0-100）
}
```

**朝向规则**：由最后一次移动操作决定，无论目标格是否可行走。

**状态说明**：

| 状态 | 说明 |
|------|------|
| idle | 静止 |
| moving | 移动中 |
| interacting | 与对象交互中 |

---

## 12. 玩家基本交互

| 操作 | 效果 |
|------|------|
| 方向键（单次） | 向对应方向移动一格 |
| 方向键（按住） | 持续移动，每 300ms 一格 |
| Ctrl + 方向键 | 只改变朝向，不移动 |
| 鼠标左键点击 Tile | BFS 寻路后逐格移动，每 300ms 一格 |
| `I` 键 | 与正前方一格的 Object 交互，显示 description |
| 鼠标悬停 Object | 显示 Object 名称 tooltip |
| 移入世界事件区域 | 自动弹出事件提示文本 |
| 点击 / Esc | 关闭交互/事件弹窗 |

**交互条件**：玩家必须**面朝**目标 Object 所在格（正前方一格），按 `I` 触发。后端根据玩家当前 `position` + `facing` 计算目标格，与 Object 的 `tiles`（或 `position`）比对。

---

## 13. 接口总结

Base URL：`http://localhost:8000`

### 查询接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/world` | 返回地图 tiles、objects、worldState |
| GET | `/player` | 返回当前玩家状态 |
| GET | `/events` | 返回世界事件列表 |

### 行为接口

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| POST | `/action/move` | `{playerId, direction?}` 或 `{playerId, targetTile?}` | 移动玩家 |
| POST | `/action/turn` | `{playerId, direction}` | 只改变朝向 |
| POST | `/action/interact` | `{playerId}` | 与正前方 Object 交互 |

### POST /action/move 响应

```json
// 成功
{ "success": true, "facing": "up", "position": {"x": 3, "y": 2}, "state": "idle" }

// 失败（不可行走）
{ "success": false, "facing": "up", "reason": "tile_not_walkable" }
```

### POST /action/interact 响应

```json
// 成功
{ "success": true, "message": "一张舒适的沙发。", "playerState": "interacting" }

// 失败（前方无对象）
{ "success": false, "reason": "no_object_in_front" }
```

### 未来预留接口（MVP 后）

```
POST /agent/register
POST /agent/action
GET  /agent/{id}/status
```
