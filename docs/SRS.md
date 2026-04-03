# 一、项目总体说明（重构版）

## 1. 项目目标

本项目为一个**前后端分离的 2D 像素风格沙盒小游戏**。

玩家可以在游戏世界中：

- 自由移动
- 与场景中的对象（object）进行交互
- 查看自身与世界状态信息

---

## 2. 技术选型

- 前端：React + TypeScript
- 游戏引擎：Phaser 3
- 后端：Python + FastAPI
- 包管理（前端）：npm
- 包管理（后端）：uv

---

## 3. 当前开发范围（MVP）

本阶段仅实现：

👉 **单人玩家沙盒系统（无 agent、无聊天系统）**

但需满足：

👉 为未来 agent 系统预留接口能力

---

# 二、沙盒系统（Sandbox）

## 2.1 基本结构（Maze）

沙盒世界采用层级结构：

```
world → section → arena → tile
```

### 定义：

- **world**：整个游戏世界
- **section**：区域（例如：村庄）
- **arena**：子区域（例如：房间）
- **tile**：最小单位（格子）

---

## 2.2 Tile 定义

```tsx
type Tile = {
  x: number
  y: number
  walkable: boolean
  objectId?: string
}
```

---

## 2.3 Object（简化版）

👉 第一版必须极简：

```tsx
type Object = {
  id: string
  name: string
  position: { x: number; y: number }
  interactable: boolean
  description: string
}
```

### 行为规则：

- 玩家靠近 object（相邻 tile，曼哈顿距离 = 1）
- 按 `I` 键 → 触发交互
- 返回一段文本反馈

---

# 三、时间系统（Tick）

## 3.1 Tick 机制

- 世界以固定 tick 推进
- 每个 tick 进行一次状态结算

```tsx
tickRate = 1 tick / 200ms（建议）
```

---

## 3.2 世界时间参数

```tsx
type WorldState = {
  date: string        // "2001-12-30"
  time: string        // "08:00"
  isDay: boolean
  weather: "sunny" | "cloudy" | "rain"
}
```

---

# 四、坐标系统

必须支持：

---

## 4.1 像素 ↔ tile 转换

```tsx
tileX = Math.floor(pixelX / tileSize)
tileY = Math.floor(pixelY / tileSize)
```

---

## 4.2 tile → 像素范围

```tsx
pixelX = tileX * tileSize
pixelY = tileY * tileSize
```

---

## 4.3 tile → 区域映射

```tsx
getTileArea(tile) → {
  worldId
  sectionId
  arenaId
}
```

---

# 五、世界事件（World Event）（保留但简化）

👉 保留你最优秀的设计，但先做“展示用”

---

## 5.1 数据结构

```tsx
type WorldEvent = {
  id: string
  tiles: { x: number; y: number }[]
  description: string
}
```

---

## 5.2 行为

- 玩家进入范围 → 显示提示（UI 或文字）
- 不影响游戏逻辑

---

# 🧍 六、角色系统（Persona）（简化）

## 6.1 玩家角色

```tsx
type Player = {
  id: string
  position: { x: number; y: number }
  facing: "up" | "down" | "left" | "right"
  state: "idle" | "moving" | "interacting"
  hp: number
  energy: number
}
```

---

## 6.2 行为状态（最小集）

- idle（静止）
- moving（移动）
- interacting（交互中）

---

# 七、交互系统（核心）

## 7.1 移动

### 方式 1：键盘

- ↑ ↓ ← → 控制移动

---

### 方式 2：鼠标点击

- 点击 tile
- 前端 BFS 计算路径，逐格向后端发送移动请求，每格间隔 300ms
- 途中再次点击立即切换新路径，键盘按键取消鼠标路径

---

## 7.2 Object 交互

条件：

- 玩家在 object 相邻位置（曼哈顿距离 = 1）

操作：

- 按 `I` 键

结果：

- 返回文本提示（显示在 UI 面板）
- 若附近无可交互对象，提示"附近没有可交互的对象"
- 若后端校验不相邻，提示"距离太远"

---

## 7.3 信息查看

支持：

- 玩家状态（HP / energy）
- 世界状态（时间 / 天气）
- object 描述（hover）

---

# 八、前端结构建议

## 分层结构

```
React（UI）
  ├── UI组件（面板、按钮）
  ├── 状态管理
  ↓
Phaser（游戏）
  ├── 地图
  ├── 玩家
  ├── 输入控制
```

---

# 九、后端 API（Action-Driven 架构）

## 9.1 查询接口（只读）

```
GET /world     # 地图、对象、世界状态
GET /player    # 当前玩家状态
GET /events    # 世界事件列表
```

---

## 9.2 统一行为接口

```
POST /action
```

**所有实体（玩家、未来 agent）的行为均通过此接口执行。**

请求结构：

```json
{
  "entityId": "player_01",
  "action": {
    "type": "move",
    "payload": { "direction": "up" }
  }
}
```

当前支持的 `type`：

| type | 说明 |
|------|------|
| `move` | 移动一格或前往目标 tile |
| `turn` | 仅改变朝向，不移动 |
| `interact` | 与正前方对象交互 |

新增行为只需在后端 Dispatcher 注册新 handler，**不修改接口路径**。

---

👉 注意：

虽然现在是单人游戏：

👉 **所有操作仍走后端接口**

这是为了未来接 agent / 多人，且 agent 将直接复用 `POST /action`，无需额外接口。

---

# 十、当前不实现的功能（明确排除）

以下全部移出 MVP：

- ❌ generative agent 系统
- ❌ Chat 系统（聊天室）
- ❌ 多 Persona
- ❌ 复杂 object（buff / 多人使用）
- ❌ 行为计划系统
- ❌ memory 系统

---

# 十一、开发目标（里程碑）

## 🎯 MVP 完成标准

你必须做到：

- 页面打开 → 显示地图
- 玩家可移动
- 能点击 object 并触发反馈
- UI 能显示基本信息

---