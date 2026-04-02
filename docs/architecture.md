# 系统架构设计

## 1. 整体架构

本项目采用**前后端分离**架构，前端负责渲染与交互，后端负责状态管理与逻辑结算。

```
┌─────────────────────────────────────┐
│            Browser (前端)            │
│                                     │
│  ┌────────────┐  ┌────────────────┐ │
│  │  React UI  │  │ Phaser 游戏引擎 │ │
│  │  (面板/HUD) │←→│ (地图/角色/输入)│ │
│  └────────────┘  └───────┬────────┘ │
└──────────────────────────┼──────────┘
                           │ HTTP REST
                           ↓
┌─────────────────────────────────────┐
│           Python FastAPI (后端)      │
│                                     │
│  ┌──────────┐   ┌─────────────────┐ │
│  │  路由层   │   │   游戏状态管理   │ │
│  │ (Router) │→  │  (WorldState)   │ │
│  └──────────┘   └─────────────────┘ │
└─────────────────────────────────────┘
```

---

## 2. 技术选型

| 层级 | 技术 | 版本建议 |
|------|------|----------|
| 前端框架 | React + TypeScript | React 18+ |
| 游戏引擎 | Phaser | Phaser 3 |
| 后端框架 | Python FastAPI | FastAPI 0.100+ |
| 包管理（前端） | npm | - |
| 包管理（后端） | uv | - |

---

## 3. 模块划分

### 3.1 前端模块

```
front_end/
├── src/
│   ├── game/              # Phaser 游戏核心
│   │   ├── scenes/        # 游戏场景
│   │   ├── objects/       # 游戏对象（Player、Object）
│   │   ├── map/           # 地图与 Tile 管理
│   │   └── systems/       # 时间系统、坐标转换等
│   ├── ui/                # React UI 组件
│   │   ├── HUD/           # 玩家状态面板
│   │   ├── WorldInfo/     # 世界状态面板
│   │   └── Interaction/   # 交互提示组件
│   ├── api/               # 后端接口调用封装
│   └── store/             # 状态管理（Zustand）
```

### 3.2 后端模块

```
back_end/
├── main.py                # FastAPI 入口
├── routers/
│   ├── world.py           # GET /world
│   ├── player.py          # GET /player
│   ├── objects.py         # GET /objects
│   ├── events.py          # GET /events
│   └── actions.py         # POST /action/*
├── models/                # 数据模型（Pydantic）
│   ├── world.py
│   ├── player.py
│   └── game_object.py
└── game/                  # 游戏逻辑
    ├── world_state.py     # 世界状态管理
    ├── tick_engine.py     # Tick 推进引擎
    └── interaction.py     # 交互逻辑处理
```

---

## 4. 数据流

### 4.1 游戏启动流程

```
1. 前端启动 → React App 挂载
2. 调用 GET /world → 获取地图、对象、世界状态
3. Phaser 初始化场景 → 渲染地图与玩家
4. 启动 Tick 轮询（或 WebSocket，未来扩展）
```

### 4.2 玩家移动流程

```
用户输入（键盘/鼠标点击）
  → Phaser 捕获输入
  → POST /action/move { direction 或 targetTile }
  → 后端校验 walkable
  → 返回新坐标
  → Phaser 更新玩家位置
  → React HUD 同步状态
```

### 4.3 对象交互流程

```
玩家靠近 Object → 右键点击
  → POST /action/interact { objectId }
  → 后端返回 description 文本
  → React UI 显示反馈面板
```

---

## 5. 扩展预留

以下为 MVP 后阶段预留的扩展点：

- **Agent 接口**：后端 `/action` 接口设计为通用行为接口，agent 可复用
- **多人支持**：玩家操作全走后端，状态集中管理，天然支持多人
- **WebSocket**：当前 REST 轮询，未来可替换为 WebSocket 实现实时推送
