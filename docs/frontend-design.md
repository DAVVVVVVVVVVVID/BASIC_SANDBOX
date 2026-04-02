# 前端设计文档

## 1. 技术栈

| 技术 | 用途 |
|------|------|
| React 18 + TypeScript | UI 框架与状态管理 |
| Phaser 3 | 2D 游戏引擎（地图渲染、角色、输入） |
| Zustand | 全局状态管理 |
| Fetch API | 后端 API 调用 |

---

## 2. 分层架构

```
React（UI 层）
  ├── HUD（HP / Energy 显示）
  ├── WorldInfoPanel（时间 / 天气）
  ├── InteractionPanel（交互文本弹窗）
  └── 全局状态（Store）
        ↕  共享状态
Phaser（游戏层）
  ├── GameScene（主场景）
  ├── MapLayer（Tile 地图渲染）
  ├── PlayerSprite（玩家角色）
  ├── ObjectSprites（场景对象）
  └── InputHandler（键盘 / 鼠标输入）
        ↕  HTTP
后端 API
```

---

## 3. 目录结构

```
front_end/
├── public/
│   └── assets/              # 像素风格图片资源
│       ├── tiles/           # Tile 贴图
│       ├── sprites/         # 角色与对象精灵图
│       └── ui/              # UI 图标
├── src/
│   ├── main.tsx             # 入口
│   ├── App.tsx              # 根组件，挂载 Phaser + React UI
│   ├── game/
│   │   ├── PhaserGame.ts    # Phaser 实例初始化与 React 桥接
│   │   ├── EventBus.ts      # Phaser ↔ React 事件总线
│   │   ├── scenes/
│   │   │   └── GameScene.ts # 主游戏场景
│   │   ├── objects/
│   │   │   ├── Player.ts           # 玩家精灵逻辑（含朝向指示）
│   │   │   └── GameObjectSprite.ts # 场景对象精灵（含 hover tooltip）
│   │   ├── map/
│   │   │   └── TileMap.ts   # Tile 地图渲染与坐标转换
│   │   └── systems/
│   │       ├── InputSystem.ts    # 输入处理
│   │       └── TickSystem.ts     # Tick 轮询（阶段 4 实现）
│   ├── ui/
│   │   ├── HUD.tsx               # 玩家状态面板（阶段 4 实现）
│   │   ├── WorldInfoPanel.tsx    # 世界信息面板（阶段 4 实现）
│   │   └── InteractionPanel.tsx  # 交互结果展示
│   ├── api/
│   │   └── world.ts         # 所有后端调用封装
│   ├── store/
│   │   └── gameStore.ts     # Zustand 状态管理（阶段 4 实现）
│   └── types/
│       └── index.ts         # TypeScript 类型定义
```

---

## 4. 核心组件说明

### 4.1 App.tsx

- 挂载 Phaser 游戏画布
- 叠加 React UI 层（绝对定位覆盖在 Canvas 上）
- 初始化时并发调用 `GET /world` 与 `GET /player` 加载数据
- 挂载 `InteractionPanel` 覆盖层

### 4.2 GameScene.ts（Phaser 主场景）

负责：
- 渲染 TileMap
- 渲染玩家和对象精灵
- 监听输入，调用 API
- 同步后端返回的状态到 Phaser 渲染

### 4.3 InputSystem.ts

**键盘移动：**
```typescript
// 方向键（JustDown，每次触发一格）→ POST /action/move { direction }
cursors.up    → direction: "up"
cursors.down  → direction: "down"
cursors.left  → direction: "left"
cursors.right → direction: "right"
```

**鼠标点击移动：**
```typescript
// 左键点击 tile → BFS 计算路径 → 逐格发送 POST /action/move { direction }，间隔 300ms
// 途中再次点击：丢弃旧路径，立即开始新路径
// 键盘按键：取消当前鼠标路径
onClick(pixelX, pixelY) → pixelToTile() → bfs(tiles, currentPos, target) → 每步 POST /action/move { direction }
```

**I 键交互：**
```typescript
// 按 I 键 → POST /action/interact（后端根据玩家位置+朝向判断正前方对象）
onKeyI() → POST /action/interact { playerId }
```

**移动结果回调：**
```typescript
// 无论成败都返回 facing；成功时额外返回新 position
onMoveResult({ success, facing, position? })
```

### 4.4 HUD.tsx

显示：
- HP 进度条（0-100）
- Energy 进度条（0-100）
- 玩家当前状态标签

### 4.5 WorldInfoPanel.tsx

显示：
- 游戏内日期与时间
- 天气图标与文字
- 昼夜状态

### 4.6 InteractionPanel.tsx

- 按 I 键交互后弹出（通过 EventBus 接收消息）
- 显示 object 返回的 `description`，或系统提示（如"附近没有可交互的对象"）
- 点击面板或按 `Esc` 关闭

---

## 5. 状态管理（gameStore.ts）

```typescript
interface GameStore {
  player: Player | null
  worldState: WorldState | null
  objects: GameObject[]
  interactionMessage: string | null
  setPlayer: (p: Player) => void
  setWorldState: (ws: WorldState) => void
  setObjects: (objs: GameObject[]) => void
  setInteractionMessage: (msg: string | null) => void
}
```

---

## 6. Tick 同步策略

MVP 阶段使用轮询：

```typescript
// 每 200ms 调用一次 GET /world 同步世界状态
setInterval(() => {
  fetchWorld().then(data => {
    setWorldState(data.worldState)
    setObjects(data.objects)
  })
}, 200)
```

---

## 7. Phaser ↔ React 通信

使用**事件总线（EventBus）**模式：

```typescript
// Phaser 触发事件
EventBus.emit('show-interaction', { message: '...' })

// React 监听事件
useEffect(() => {
  EventBus.on('show-interaction', ({ message }) => {
    setMessage(message)
  })
}, [])
```
