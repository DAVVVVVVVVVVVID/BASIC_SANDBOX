# BASIC_SANDBOX

一个前后端分离的 2D 像素风格沙盒游戏。玩家可以在 tile 构成的世界中自由移动、与场景对象交互，并观察实时变化的世界时间与状态。同时提供完整的 Agent API，供自主 Agent 感知世界并执行行动。

> **版本说明：** 当前版本为 **Sandbox v1.0.1**，对应可稳定运行的 Agent 版本为 **Agent v1.0.0** 与 **Agent v2.0.0**。

---

## 更新日志

### v1.0.1
- 地图数据（tile、object、区域）全部迁移至 JSON 文件，与 [MAP_EDITOR](https://github.com/DAVVVVVVVVVVVID/MAP_EDITOR) 联动，支持可视化编辑后直接导入
- Tile 类型、Object 类型、地图布局均可通过 MAP_EDITOR 增删改，无需修改代码
- 前端新增镜头跟随（平滑跟随玩家）与小地图（右下角全局位置显示）
- 角色移动改为平滑 tween 动画，连续移动无卡顿
- 修复鼠标快速多次点击导致移动加速的 bug
- 修复镜头偏移后鼠标点击坐标错位的 bug

### v1.0.0
- 初始版本

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
│   │   ├── player.py          # GET /player，管理接口（/admin/player/...）
│   │   ├── agent.py           # Agent 感知与导航接口（/agent/...）
│   │   ├── events.py          # GET /events
│   │   ├── history.py         # GET /history，GET /history/log（JSONL 全量）
│   │   ├── ws.py              # GET /ws/world 只读推送（B17）
│   │   └── time_control.py    # POST /time/toggle|speed|reset
│   ├── scripts/
│   │   ├── verify_restart.py  # kill -9 后重启续跑验证脚本
│   │   ├── verify_self_sync.py # 与自我层 delta 同步联调脚本
│   │   ├── verify_external.py # 手机 / 直播台对自我层联调
│   │   ├── soak.py            # 稳定性复现 / 负载（--agents --ws）
│   │   ├── verify_ws.py       # /ws/world 推送对账
│   │   ├── run_town.sh        # 一机多镇：起一个独立实例
│   │   └── gen_map.py         # 地图生成器（阿蝉家 + 小镇 + 餐馆）
│   ├── tests/                 # pytest（uv run pytest）
│   ├── data/                  # 运行时生成：sandbox.db 检查点、actions/*.jsonl（不进 git）
│   ├── models/
│   │   ├── world.py           # Pydantic 数据模型
│   │   ├── player.py          # Player / Buff 模型
│   │   └── action.py          # ActionRequest / ActionResponse
│   └── game/
│       ├── world_state.py     # 全局游戏状态（唯一可信数据源）
│       ├── time_state.py      # 游戏时间：真实起点 + 倍率
│       ├── ticker.py          # 后台 tick 任务（200 ms）+ 定时检查点
│       ├── persistence.py     # SQLite 检查点（保存 / 回填 / catch_up 分段上限）
│       ├── self_sync.py       # 自我层同步：GET /self/state 种入、30 游戏秒批量 POST /self/state/delta
│       ├── external_effects.py # external effect：feed（手机）/ live（直播台）调自我层
│       ├── needs.py           # 需求值分档文字（perceive 的 needs）
│       ├── paths.py           # 数据目录（SANDBOX_DATA_DIR）
│       ├── object_types.py    # 从 object_types.json 加载 Object 类型
│       ├── object_types.json  # ← MAP_EDITOR 导出，Object 类型定义
│       ├── action_log.py      # 行为日志：JSONL append-only + 内存最近 20 条
│       ├── buff_tick.py       # Buff Tick 引擎：handler 工厂、decay 元 buff、catch_up 分段
│       └── maps/
│           ├── map.json           # ← MAP_EDITOR 导出，地形 + 区域 + 事件
│           ├── objects.json       # ← MAP_EDITOR 导出，Object 实例列表
│           ├── tile_types.json    # ← MAP_EDITOR 导出，Tile 类型定义
│           └── cognitive_map.py   # 语义树（worlds → sectors → arenas）
├── front_end/
│   ├── index.html
│   ├── package.json
│   ├── public/assets/
│   │   ├── tiles/             # ← MAP_EDITOR 导出，Tile 贴图
│   │   └── sprites/           # ← MAP_EDITOR 导出，Object 精灵图
│   └── src/
│       ├── App.tsx            # 根组件
│       ├── api/world.ts       # 所有后端接口调用
│       ├── store/gameStore.ts # Zustand 全局状态
│       ├── types/index.ts     # TypeScript 类型定义
│       ├── game/
│       │   ├── PhaserGame.ts          # Phaser 实例初始化（全屏画布）
│       │   ├── EventBus.ts            # Phaser ↔ React 事件通信
│       │   ├── scenes/GameScene.ts    # 主游戏场景（含镜头跟随）
│       │   ├── map/TileMap.ts         # Tile 渲染 + 坐标转换
│       │   ├── objects/
│       │   │   ├── Player.ts          # 玩家精灵（平滑 tween 移动）
│       │   │   └── GameObjectSprite.ts # 场景对象精灵
│       │   └── systems/
│       │       ├── InputSystem.ts     # 键盘/鼠标输入（含 BFS 寻路）
│       │       └── TickSystem.ts      # 200ms 轮询同步
│       └── ui/
│           ├── HUD.tsx                # 玩家状态面板（HP / Energy / 位置 / Buff）
│           ├── ActionLog.tsx          # 行为日志面板
│           ├── WorldInfoPanel.tsx     # 时间 / 天气面板
│           ├── TimeControlPanel.tsx   # 时间控制（暂停 / 加速 / 重置）
│           ├── InteractionPanel.tsx   # 交互文本弹窗
│           └── Minimap.tsx            # 小地图（右下角全局位置）
└── docs/                      # 详细设计文档
```

---

## 核心功能

### 世界结构

地图采用四级层级：`world → sector → arena → tile`。每个 tile 有坐标 `(x, y)` 和可行走标志，最多放置一个 Object。坐标系以左上角为原点，x 向右递增，y 向下递增。

当前地图「阿蝉家与小镇」（60 × 40）由 `back_end/scripts/gen_map.py` 生成（MAP_EDITOR 不在本机，按其导出格式直出；旧 50 × 50 地图在 `game/maps/legacy_50x50/`）：阿蝉家（小仓库 = 鲸仔房间：bed / desk / book / phone / stream_desk；阿蝉房间；厨房 fridge）、四个 NPC 家（厨子、杂货商、渔夫、常客，对应 whale-self `personas/`）、街道、广场、公园、码头与河。出生点在小仓库。改地图：改脚本常量后重新运行 `uv run python scripts/gen_map.py`。

### 时间系统

- **真实起点 + 倍率**：游戏时间 = `anchor_game + (now − anchor_real) × speed`。首次启动取真实当前时间（北京时间 1:1，`SANDBOX_TZ` 可改），默认 `speed = 1.0`、运行中（`SANDBOX_TIME_RUNNING=0` 可改为启动即暂停）
- 暂停 / 加速时先把当前游戏时刻折算成新锚点，时间不跳变；时段 morning(06–08) / day(08–20) / dusk(20–22) / night(22–06)
- **后台 tick**：后端独立 asyncio 任务每 200 ms 推进一次（buff 结算、max_duration、离线清理），不依赖客户端轮询；`GET /world` 只读
- **持久化**：每 5 s 与关停时写 SQLite 检查点 `back_end/data/sandbox.db`（players、物品使用状态、时间锚点、对话）；行动日志 append-only 写 `back_end/data/actions/YYYY-MM-DD.jsonl`。`kill -9` 后重启，玩家位置、正在用的物品、游戏时间全部续上，并按停机时长补算一次 tick（≤ 8 游戏小时）。数据目录可用 `SANDBOX_DATA_DIR` 覆盖
- 前端通过轮询同步，支持暂停、加速、重置

### 玩家控制（前端）

| 操作 | 效果 |
|------|------|
| 方向键 | 移动一格（每 300ms / moveSpeed，平滑动画） |
| Ctrl + 方向键 | 仅改变朝向，不移动 |
| 鼠标左键点击 Tile | BFS 寻路后自动逐格平滑移动 |
| `I` 键 | 读取正前方 Object 的描述文本 |
| `E` 键 | 进入正前方 Object（触发 Buff） |
| `Q` 键 | 离开当前 Object（清除 while_active Buff） |
| 鼠标悬停 Object | 显示名称与使用人数 tooltip |

> 交互要求玩家**面朝**目标 Object（正前方一格），后端统一校验。

### Object 与 Buff 系统

每种 Object 可配置 effects（buff / tag），玩家使用（E 键）后生效：

- **persistent buff**：使用期间持续生效，离开后清除（如 `no_move`、`energy_regen`）
- **timed buff**：进入时触发，`duration` 毫秒后自动消失
- **instant_effect**：瞬间修改需求值（`fullness` / `energy` / `social` / `fun` / `mood`，clamp 0–100）
- **tag**：纯标记，不参与运算（如 `sleeping`、`reading`）
- **advertise**：每种 Object 的广告值 `{var: 0–100}`，随 `GET /world` 下发给规划器；每个物品至少一项成本；同一物品 30 游戏分钟冷却
- **external**：`phone`（use 拉自我层 `/self/feed` 摘要进 perceive 的 `phone`）与 `stream_desk`（use 开播 / leave 下播，期间按 live 速率衰减）
- 数值为**每游戏小时尺度**：睡 8 h energy ≈ +200，一顿饭 fullness +40，一本书 fun +60（见 api-spec §5）
- **社交物品**（W4）：餐馆四人桌（`max_users` 4）、广场长椅（2 人）、码头钓位、杂货店柜台；NPC 家各有 fridge

### 实时推送与多实例

- `GET /ws/world`：只读 WebSocket，连接发全量，之后 ≤ 10 Hz 推 world / players / objects / chat 的变化（字段与 `GET /world` 同名），给前端用；写仍走 `POST /action`
- 一机多镇：`back_end/scripts/run_town.sh --port 8010 --data run/data/m2a`，每个实例独立端口 + 独立 `SANDBOX_DATA_DIR`，无共享文件；`SANDBOX_CORS_ORIGINS` 配前端来源
- `GET /admin/metrics`：tick 耗时 / 间隔分位、玩家数、WS 订阅数、RSS

### 需求值与自我层

每个 player 有七变量（fullness / energy / social / fun / mood + emotion_tags + closeness），常驻一条 `decay` 元 buff 按 ARCHITECTURE §2.5 的速率自然衰减（fullness −12/h、energy −8/h 夜间 ×1.5、social −6/h、fun −10/h、mood 指数回基线、closeness −1/天；`scene=live` 时 social −0.12/s、mood 半衰期 70 s）。`controller=agent` 的 player 在 join / 重启时从自我层 `GET /self/state` 种入初值，之后每 30 游戏秒把**非衰减**变化 `POST /self/state/delta`（自我层自己算衰减），不可达时累积重发；`GET /admin/self-sync` 看同步状态。环境变量：`SELF_URL`（默认 `http://127.0.0.1:8100`）、`SELF_TOKEN`、`SELF_SYNC=0` 关闭。

---

## 使用 MAP_EDITOR 更新地图

地图、Tile 类型、Object 类型均通过 [MAP_EDITOR](https://github.com/DAVVVVVVVVVVVID/MAP_EDITOR) 可视化编辑后导出，替换到 SANDBOX 对应位置即可生效。

### 导出方式

在 MAP_EDITOR 右侧面板点击 **「导出完整包 (.zip)」**，得到 `<地图名>_export.zip`。

### 文件放置位置

解压后按以下路径覆盖：

| zip 内路径 | 放置到 SANDBOX 的位置 |
|---|---|
| `back_end/game/maps/map.json` | `back_end/game/maps/map.json` |
| `back_end/game/maps/objects.json` | `back_end/game/maps/objects.json` |
| `back_end/game/maps/tile_types.json` | `back_end/game/maps/tile_types.json` |
| `back_end/game/object_types.json` | `back_end/game/object_types.json` |
| `front_end/public/assets/sprites/*.png` | `front_end/public/assets/sprites/` |
| `front_end/public/assets/tiles/*.png` | `front_end/public/assets/tiles/` |

也可以用命令一键解压覆盖（在 SANDBOX 根目录执行）：

```bash
unzip -o <地图名>_export.zip "back_end/*" -d .
unzip -o <地图名>_export.zip "front_end/*" -d .
```

### 重启后端生效

文件替换后重启后端服务，新地图即生效：

```bash
cd back_end
uv run uvicorn main:app --reload
```

---

## 行为 API

所有玩家/Agent 操作通过统一接口执行：

```
POST /action
{ "entityId": "player_01", "action": { "type": "<type>", "payload": { ... } } }
```

| 行为类型 | 说明 |
|---------|------|
| `move` | 向指定方向移动一格，或移动到指定 tile 坐标 |
| `move_n` | 向指定方向移动 N 格（遇到不可行走 tile 提前停止） |
| `move_to_area` | 随机传送至指定 world / sector / arena 内的可行走 tile |
| `turn` | 改变朝向，不移动 |
| `interact` | 读取正前方 Object 的描述文本 |
| `use` | 进入正前方 Object，触发 effects |
| `leave` | 离开当前 Object，清除 persistent buff |

---

## Agent API

供自主 Agent 使用的感知与导航接口：

| 接口 | 说明 |
|------|------|
| `GET /agent/perceive` | 当前 arena 语义树、视野范围 tile、正前方物体、视野内 player，以及 `needs` 需求分档文字（不给数值） |
| `GET /agent/arena-tiles` | 指定 arena 内所有 tile 坐标 |
| `GET /agent/object-position` | 指定 object 的锚点坐标 |
| `POST /player/join` | `controller: human \| agent`、`profile: {E, N, agent_id}` |
| `POST /player/rejoin` | agent 进程重拉后用同一 playerId 续接 |
| `GET /player/{id}/state` | 七变量原始数值、`last_tick_ts`、`recent_uses` |
| `POST /player/{id}/effects` | 推送与 object_types 同格式的 effect 列表，可带 `scene` |

---

## 管理接口（调试用）

用于手动干预玩家状态，不记录行动日志：

| 接口 | 说明 |
|------|------|
| `GET /admin/player/buffs` | 查看当前所有 buff |
| `DELETE /admin/player/buffs` | 强制清除所有 buff（不离开对象） |
| `POST /admin/player/force-reset` | 离开当前对象并清除所有 buff / tag，状态归 idle |
| `POST /admin/checkpoint` | 立即写一份 SQLite 检查点 |
| `GET /admin/self-sync` | 自我层同步状态（发送 / 失败 / drift / 待发） |
| `GET /admin/metrics` | tick 耗时 / 间隔分位、玩家数、WS 订阅数、RSS |

> 当 Agent 循环意外中断导致玩家被 `no_move` / `no_interact` / `no_use` buff 卡住时，调用 `force-reset` 即可恢复。

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

> `--reload` 每次重载都会走一遍「关停写检查点 → 启动回填」，开发时属正常现象。

### 运行测试

```bash
cd back_end
uv run pytest -q                              # 单元 / 接口测试
uv run python scripts/verify_restart.py       # kill -9 后重启续跑验证（约 20 s）
uv run python scripts/verify_self_sync.py --self-url http://127.0.0.1:8100   # 与自我层联调：两边数值差 < 0.5
uv run python scripts/verify_self_sync.py --mock                             # 没有自我层时用内置参考实现自测
uv run python scripts/verify_external.py --self-url http://127.0.0.1:8100     # B10 手机 / B11 直播台对自我层联调（自测沙盒起 8001）
uv run python scripts/soak.py --minutes 30 --rounds 3                         # 稳定性：长时间驱动，监控进程是否意外退出
uv run python scripts/soak.py --minutes 30 --rounds 1 --agents 6 --ws 1       # 负载：6 名 agent + 1 个 WS 订阅，记 p95 / tick / RSS
uv run python scripts/verify_ws.py --seconds 60                               # /ws/world 推送与轮询对账
uv run python scripts/gen_map.py                                              # 重新生成地图
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
| [docs/game-mechanics.md](docs/game-mechanics.md) | 游戏机制说明 |
| [docs/api-spec.md](docs/api-spec.md) | 后端 API 完整规范 |
| [docs/frontend-design.md](docs/frontend-design.md) | 前端架构与组件设计 |
| [docs/milestone.md](docs/milestone.md) | 开发里程碑 |
