# 游戏机制说明

## 1. 世界结构

### 层级关系

```
world（游戏世界）
  └── section（区域，如：村庄）
        └── arena（子区域，如：房间）
              └── tile（格子，最小单位）
```

### Tile 规则

- 每个 tile 有坐标 `(x, y)` 和可行走标志 `walkable`
- `walkable: false` 的 tile 不可进入（墙、水面、障碍物等）
- 每个 tile 最多有一个 object

---

## 2. 时间系统

### Tick 机制

- 世界以固定频率推进：`1 tick = 200ms`
- 每 tick 后端结算一次世界状态（时间、天气等）
- 前端通过轮询同步

### 时间参数

| 参数 | 类型 | 说明 |
|------|------|------|
| date | string | 游戏内日期，格式 `"YYYY-MM-DD"` |
| time | string | 游戏内时间，格式 `"HH:MM"` |
| isDay | boolean | 白天为 `true`，夜晚为 `false` |
| weather | enum | `sunny` / `cloudy` / `rain` |

---

## 3. 坐标系统

### 像素 ↔ Tile 转换

```
tileX = Math.floor(pixelX / tileSize)
tileY = Math.floor(pixelY / tileSize)

pixelX = tileX * tileSize
pixelY = tileY * tileSize
```

- `tileSize` 为单格像素大小（建议 32px 或 48px）
- 坐标原点 `(0, 0)` 在地图左上角

### Tile → 区域映射

每个 tile 可查询其归属：

```
getTileArea(tile) → { worldId, sectionId, arenaId }
```

---

## 4. 玩家角色

### 状态机

```
idle ←→ moving
 ↓         ↑
interacting
```

| 状态 | 说明 | 进入条件 |
|------|------|----------|
| idle | 静止 | 无输入 |
| moving | 移动中 | 方向键按下 / 点击目标 tile |
| interacting | 交互中 | 右键点击相邻 object |

### 属性

- **HP**：生命值，范围 0–100（MVP 阶段仅展示，不消耗）
- **Energy**：体力值，范围 0–100（MVP 阶段仅展示，不消耗）

---

## 5. 移动系统

### 键盘控制

| 按键 | 行为 |
|------|------|
| ↑ | 向上移动一格 |
| ↓ | 向下移动一格 |
| ← | 向左移动一格 |
| → | 向右移动一格 |

### 鼠标点击移动

- 点击地图上可行走的 tile
- 玩家自动移动到目标位置（MVP：直线移动或简单路径）
- 若目标 tile 不可行走，则忽略

### 移动校验（后端）

1. 计算目标 tile
2. 检查 `walkable`
3. 检查是否有 object 占据
4. 通过则更新玩家坐标，返回新位置

---

## 6. 交互系统

### 触发条件

- 玩家与 object 处于**相邻位置**（上下左右四格之一）
- 在 object 上**右键点击**

### 交互流程

```
1. 玩家右键点击 object
2. 前端检查相邻关系
3. POST /action/interact { playerId, objectId }
4. 后端验证相邻关系
5. 返回 object.description 文本
6. 前端弹出交互面板显示文本
7. 玩家按 Esc 或点击关闭面板
8. 玩家状态恢复 idle
```

### Object 显示规则

- **鼠标悬停（Hover）**：显示 object 名称（tooltip）
- **右键点击**：触发交互，显示完整 description

---

## 7. 世界事件（World Event）

- 每个事件包含一组触发 tile
- 玩家进入任意触发 tile 时，UI 显示事件提示文字
- MVP 阶段仅展示，不影响游戏逻辑

---

## 8. MVP 不包含的功能

以下功能明确排除在 MVP 之外：

| 功能 | 状态 |
|------|------|
| Generative Agent 系统 | ❌ 排除 |
| 聊天系统 | ❌ 排除 |
| 多角色 / NPC | ❌ 排除 |
| Object buff / 多人使用 | ❌ 排除 |
| 行为计划系统 | ❌ 排除 |
| Memory 系统 | ❌ 排除 |
| HP / Energy 消耗逻辑 | ❌ 排除（仅展示）|
