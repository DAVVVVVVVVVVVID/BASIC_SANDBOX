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
│  │  路由层   │   │  Action          │ │
│  │ (Router) │→  │  Dispatcher     │ │
│  └──────────┘   └────────┬────────┘ │
│                           ↓         │
│               ┌─────────────────┐   │
│               │   游戏状态管理   │   │
│               │  (WorldState)   │   │
│               └─────────────────┘   │
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
│   │   └── systems/       # 输入系统、Tick 轮询
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
├── main.py                # FastAPI 入口，注册路由，配置 CORS
├── routers/
│   ├── world.py           # GET /world
│   ├── player.py          # GET /player
│   ├── events.py          # GET /events
│   └── actions.py         # POST /action（统一入口 + Dispatcher）
├── models/                # Pydantic 数据模型
│   ├── world.py           # Tile、GameObject、WorldState 等
│   ├── player.py          # Player 模型
│   └── action.py          # ActionRequest / ActionResponse
└── game/                  # 游戏逻辑
    ├── world_state.py     # 世界状态管理（唯一可信数据源）
    ├── action_log.py      # 行为日志（内存，最多 20 条，重启清空）
    ├── map_data.py        # 地图字符串定义
    └── object_types.py    # Object 类型定义表
```

---

## 4. Action-Driven 架构（核心设计）

### 4.1 设计原则

所有实体（玩家、未来的 agent）对世界的所有修改，**必须且只能**通过 `POST /action` 执行。

```
Action = 世界唯一输入
```

这保证了：
- 玩家与 agent 走完全相同的代码路径
- 新增行为只需注册新 handler，不需要新增接口
- 状态变更有统一的审计入口

### 4.2 Action 数据结构

```python
# 请求
{
    "entityId": "player_01",   # 执行行为的实体
    "action": {
        "type": "move",        # 行为类型
        "payload": { ... }     # 行为参数，由 type 决定
    }
}

# 响应（通用）
{
    "success": bool,
    "type": "<action_type>",
    "result": { ... }          # 成功时的结果数据
    # 或
    "reason": "<error_code>"   # 失败时的原因
}
```

### 4.3 Action Dispatcher

后端路由层接收请求后，转发给 Dispatcher，由 Dispatcher 根据 `type` 调用对应 handler，执行完毕后写入日志：

```python
def dispatch(action_request):
    handlers = {
        "move":     handle_move,
        "turn":     handle_turn,
        "interact": handle_interact,
        # 新增行为：在此注册
    }
    handler = handlers.get(action_request.action.type)
    if not handler:
        return error("unknown_action_type")
    result = handler(action_request)
    append_action_log(...)   # 记录到 action_log，超出 20 条自动丢弃最旧
    return result
```

### 4.4 新增行为的步骤

1. 在 `action.py` 定义新的 payload 结构
2. 实现 handler 函数
3. 在 Dispatcher 的 `handlers` 字典中注册
4. 更新 `api-spec.md` 的"行为类型一览"表

**不需要**新增路由、新增接口路径、修改前端请求封装结构。

---

## 5. 数据流

### 5.1 游戏启动流程

```
1. 前端启动 → React App 挂载
2. 调用 GET /world → 获取地图、对象、世界状态
3. Phaser 初始化场景 → 渲染地图与玩家
4. 启动 Tick 轮询（GET /world，每 200ms）
```

### 5.2 玩家行为流程（统一）

```
用户输入（键盘/鼠标）
  → Phaser 捕获输入
  → POST /action { entityId, action: { type, payload } }
  → Action Dispatcher 路由到对应 handler
  → handler 读写 WorldState
  → 返回 ActionResponse
  → 前端更新本地状态（位置、朝向等）
  → 下一个 Tick 轮询同步完整世界状态
```

### 5.3 对象交互流程

```
玩家面朝目标方向 → 按 I 键
  → POST /action { type: "interact", payload: {} }
  → 后端根据 position + facing 计算正前方格子
  → 命中 object.tiles 中任意格 → 返回 description
  → React UI 弹出交互面板
```

---

## 6. 扩展预留

- **Agent 接入**：agent 复用 `POST /action`，`entityId` 改为 agent ID，其余完全一致
- **多人支持**：所有状态集中在后端 WorldState，天然支持多实体并发
- **WebSocket**：当前 REST 轮询，未来可替换为 WebSocket 实现实时推送
- **Tick 收集模式**：未来可将 action 改为先入队、统一结算，避免并发竞争
