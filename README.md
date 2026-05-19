# BASIC_SANDBOX

一个前后端分离的 2D 像素风格沙盒游戏。玩家可以在 tile 构成的世界中自由移动、与场景对象交互，并观察实时变化的世界时间与状态。

---

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | React 18 + TypeScript + Phaser 3 + Zustand |
| 后端 | Python 3.11+ + FastAPI + uv |
| 构建工具 | Vite（前端）/ uvicorn（后端） |

---

## 项目结构

```
BASIC_SANDBOX/
├── back_end/
│   ├── main.py                # FastAPI 入口，注册路由，配置 CORS
│   ├── pyproject.toml         # 依赖声明（uv）
│   ├── routers/
│   │   ├── actions.py         # POST /action 统一行为入口
│   │   ├── world.py           # GET /world
│   │   ├── player.py          # GET /player
│   │   ├── events.py          # GET /events
│   │   ├── history.py         # GET /history
│   │   └── time_control.py    # POST /time/toggle|speed|reset
│   ├── models/
│   │   ├── world.py           # Pydantic 数据模型
│   │   ├── player.py          # Player / Buff 模型
│   │   └── action.py          # ActionRequest / ActionResponse
│   └── game/
│       ├── world_state.py     # 全局游戏状态（唯一可信数据源）
│       ├── time_state.py      # 游戏时间推进逻辑
│       ├── object_types.py    # Object 类型定义表
│       ├── action_log.py      # 行为日志（内存，最多 20 条）
│       ├── buff_tick.py       # Buff Tick 引擎
│       └── maps/
│           ├── map_data.py        # 地形字符图
│           ├── world_map.py       # World 层区域图
│           ├── sector_map.py      # Sector 层区域图
│           ├── arena_map.py       # Arena 层区域图
│           └── cognitive_map.py   # 语义树（worlds → sectors → arenas）
├── front_end/
│   ├── index.html
│   ├── package.json
│   ├── public/assets/
│   │   ├── tiles/             # Tile 贴图（grass / wall / floor）
│   │   └── sprites/           # Object 精灵图（sofa / bed / desk 等）
│   └── src/
│       ├── App.tsx            # 根组件
│       ├── api/world.ts       # 所有后端接口调用
│       ├── store/gameStore.ts # Zustand 全局状态
│       ├── types/index.ts     # TypeScript 类型定义
│       ├── game/
│       │   ├── PhaserGame.ts          # Phaser 实例初始化
│       │   ├── EventBus.ts            # Phaser ↔ React 事件通信
│       │   ├── scenes/GameScene.ts    # 主游戏场景
│       │   ├── map/TileMap.ts         # Tile 渲染 + 坐标转换
│       │   ├── objects/
│       │   │   ├── Player.ts          # 玩家精灵
│       │   │   └── GameObjectSprite.ts # 场景对象精灵
│       │   └── systems/
│       │       ├── InputSystem.ts     # 键盘/鼠标输入（含 BFS 寻路）
│       │       └── TickSystem.ts      # 200ms 轮询同步
│       └── ui/
│           ├── HUD.tsx                # 玩家状态面板（HP / Energy / 位置 / Buff）
│           ├── ActionLog.tsx          # 行为日志面板
│           ├── WorldInfoPanel.tsx     # 时间 / 天气面板
│           ├── TimeControlPanel.tsx   # 时间控制（暂停 / 加速 / 重置）
│           └── InteractionPanel.tsx   # 交互文本弹窗
└── docs/                      # 详细设计文档
```

---

## 核心功能

### 世界结构

地图采用四级层级：`world → section → arena → tile`。每个 tile 有坐标 `(x, y)` 和可行走标志，最多放置一个 Object。

### 时间系统

- 世界以固定频率推进：`1 tick = 200ms`
- 每 tick 结算游戏内时间、天气（sunny / cloudy / rain）、昼夜状态
- 前端通过轮询同步，支持暂停、加速、重置

### 玩家控制

| 操作 | 效果 |
|------|------|
| 方向键 | 移动一格（每 300ms / moveSpeed） |
| Ctrl + 方向键 | 仅改变朝向，不移动 |
| 鼠标左键点击 Tile | BFS 寻路后自动逐格移动 |
| `I` 键 | 读取正前方 Object 的描述文本 |
| `E` 键 | 进入正前方 Object（触发 Buff） |
| `Q` 键 | 离开当前 Object（清除 while_active Buff） |
| 鼠标悬停 Object | 显示名称与使用人数 tooltip |

> 交互要求玩家**面朝**目标 Object（正前方一格），后端统一校验。

### Object 与 Buff 系统

每种 Object 可配置 effects（buff / tag），玩家使用（E 键）后生效：

- **while_active buff**：使用期间持续生效，Q 键离开后清除（如 `no_move`、`energy_regen`）
- **instant buff**：进入时触发，`duration` 毫秒后自动消失（如短暂 `hp_regen`）
- **tag**：纯标记，只展示，不参与运算（如 `sleeping`）

### 行为 API（Action-Driven）

所有玩家操作通过统一接口执行：

```
POST /action
{ "entityId": "player_01", "action": { "type": "move", "payload": { "direction": "up" } } }
```

支持的行为类型：`move` / `turn` / `interact` / `use` / `leave`

---

## 如何使用

### 环境要求

- Python 3.11+
- Node.js 18+
- [uv](https://docs.astral.sh/uv/)（Python 包管理器）

### 启动后端

```bash
cd back_end
uv sync                              # 首次安装依赖
uv run uvicorn main:app --reload     # 启动，监听 http://localhost:8000
```

API 文档（自动生成）：[http://localhost:8000/docs](http://localhost:8000/docs)

### 启动前端

```bash
cd front_end
npm install          # 首次安装依赖
npm run dev          # 启动，监听 http://localhost:5173
```

浏览器打开 [http://localhost:5173](http://localhost:5173) 即可游玩。

---

## 详细文档

| 文档 | 说明 |
|------|------|
| [docs/SRS.md](docs/SRS.md) | 软件需求规格说明书 |
| [docs/architecture.md](docs/architecture.md) | 系统架构设计 |
| [docs/dev-guide.md](docs/dev-guide.md) | 开发指南（地图 / Object / Buff 的增删改方法） |
| [docs/game-mechanics.md](docs/game-mechanics.md) | 游戏机制说明 |
| [docs/api-spec.md](docs/api-spec.md) | 后端 API 规范 |
| [docs/frontend-design.md](docs/frontend-design.md) | 前端架构与组件设计 |
| [docs/milestone.md](docs/milestone.md) | 开发里程碑 |
