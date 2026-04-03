# 开发里程碑

## MVP 完成标准

MVP 通过标准（必须全部满足）：

- [x] 页面打开 → 显示地图
- [x] 玩家可以通过键盘或鼠标移动
- [x] 能点击 object 并触发文本反馈
- [x] UI 能显示玩家状态和世界信息

---

## 阶段划分

### 阶段 0：项目初始化 ✅

**目标：** 前后端项目可以运行

- [x] 后端：FastAPI 项目初始化，`GET /world` 返回静态测试数据
- [x] 前端：React + TypeScript + Phaser 项目初始化
- [x] 前端能调用后端接口并打印数据

**验收：** 浏览器控制台能看到后端返回的 world 数据

---

### 阶段 1：地图渲染 ✅

**目标：** 在浏览器中看到 2D 像素地图

- [x] 定义测试用地图数据（tile 坐标 + walkable）
- [x] Phaser 渲染 TileMap
- [x] 区分可行走 tile 和不可行走 tile（颜色或贴图）
- [x] 玩家初始位置可见（占位图）

**验收：** 页面显示地图，玩家位置可见

---

### 阶段 2：玩家移动 ✅

**目标：** 玩家可以在地图上移动

- [x] 键盘方向键控制移动（每次一格）
- [x] 后端移动接口实现（含 walkable 校验）
- [x] 鼠标点击 tile 移动（BFS 寻路）
- [x] 玩家不能移动到 `walkable: false` 的 tile

**验收：** 玩家可以用键盘和鼠标在地图上移动，墙壁无法穿越

---

### 阶段 3：场景对象与交互 ✅

**目标：** 地图上有对象，玩家可以与之交互

- [x] 后端返回 object 数据，前端渲染 object 精灵
- [x] 鼠标悬停 object 显示名称（tooltip）
- [x] 按 `I` 键触发交互（后端根据玩家位置+朝向判断正前方对象）
- [x] 前端弹出面板显示返回文本
- [x] 正前方无对象时提示"面前没有可交互的对象"

**验收：** 能与地图上的对象交互并看到文字反馈

---

### 阶段 4：UI 面板 ✅

**目标：** HUD 信息完整显示

- [x] 玩家状态面板：HP 和 Energy 显示
- [x] 世界信息面板：游戏内时间、天气
- [x] 世界事件提示（进入触发区域时显示）
- [x] Tick 轮询同步（每 200ms 更新世界状态）

**验收：** UI 信息实时更新，MVP 完成标准全部满足

---

### 阶段 5：Action-Driven 后端重构 ✅

**目标：** 将后端从多个分散接口重构为统一的 `POST /action` 行为执行器，为 agent 接入做好基础

**步骤 1 — 后端：定义统一 Action 模型**

- [x] 在 `back_end/models/action.py` 中定义 `ActionRequest`（含 `entityId`、`action.type`、`action.payload`、`skipLog`、`logLabel`）和 `ActionResponse`（含 `success`、`type`、`result` / `reason`）

**步骤 2 — 后端：实现 Action Dispatcher**

- [x] 在 `back_end/routers/actions.py` 中实现单一路由 `POST /action`
- [x] 实现 Dispatcher：`handlers` 字典映射 `type` → handler 函数
- [x] 将现有 `move`、`turn`、`interact` 逻辑迁移为独立 handler，注册到 Dispatcher
- [x] 删除旧路由 `/action/move`、`/action/turn`、`/action/interact`

**步骤 3 — 前端：更新 API 调用层**

- [x] 在 `front_end/src/api/world.ts` 中将旧的独立函数替换为统一的 `sendAction(entityId, type, payload, options)`

**步骤 4 — 前端：更新调用方**

- [x] 更新 `InputSystem.ts` 和 `GameScene.ts`：所有行为调用改用 `sendAction`

**步骤 5 — 后端：行为日志**

- [x] 新建 `back_end/game/action_log.py`：内存列表，`append_log()` 超出 20 条自动丢弃最旧记录，`get_log()` 返回完整列表
- [x] 在 `actions.py` 的 Dispatcher 中，支持 `skipLog` 跳过记录，`logLabel` 自定义显示文字
- [x] 新建 `back_end/routers/history.py`：`GET /history` 返回日志列表
- [x] 在 `main.py` 中注册 history 路由

**步骤 6 — 前端：行为日志面板**

- [x] 在 `front_end/src/api/world.ts` 中新增 `fetchHistory()`
- [x] 在 Zustand store 中新增 `actionLog` 字段
- [x] 新建 `front_end/src/ui/ActionLog.tsx`：左下角滚动面板，优先显示 `label`，绿色=成功，红色=失败
- [x] 在 `TickSystem.ts` 的轮询里顺带拉取 `GET /history` 更新 store

**验收：**
- 键盘移动、鼠标点击移动、Ctrl+方向键转向、I 键交互，功能全部正常
- 后端只有 `/action`，不存在旧的分散路径
- 新增一个 `type` 只需改后端 Dispatcher，前端无需改动
- 日志面板显示：鼠标点击→"点击前往 (x,y)"，键盘→"向X移动"，转向→"转向X"，最多 20 条

---

---

### 阶段 6：Object 使用系统 ✅

**目标：** Object 支持进入/退出使用，追踪使用者，前端展示使用状态

**步骤 1 — 后端：扩展 Object 类型定义**

- [x] `object_types.py`：所有类型加 `max_users`、`use_state_label`、`effects`
- [x] `world_state.py`：`_build_objects()` 补充运行时字段 `currentUsers=0`、`userList=[]`；新增 `enter_object()` / `leave_object()` 函数

**步骤 2 — 后端：新增 use / leave handler 及角色参数重构**

- [x] `models/world.py`：`GameObject` 加 `maxUsers`、`currentUsers`、`userList`、`useStateLabel`、`effects` 字段
- [x] `models/player.py`：新增 `PlayerProfile`（id/name/age）；`Player` 拆分 `state`（枚举）+ `stateLabel`（展示文字）；加 `buffs`、`tags`、`usingObjectId`
- [x] `world_state.py`：新增 `_player_profile`；`enter_object` 时设置 `stateLabel` 并复制 effects 到 `buffs/tags`；`leave_object` 时清除
- [x] `routers/actions.py`：注册 `use` handler（校验 available，调用 `enter_object`）；注册 `leave` handler（调用 `leave_object`，state 恢复 idle）
- [x] `routers/player.py`：`GET /player` 响应合并 `profile`（name/age）

**步骤 3 — 前端：更新类型与 UI**

- [x] `types/index.ts`：`GameObject` 接口加新字段；`Player` 加 `profile`、`stateLabel`、`buffs`、`tags`、`usingObjectId`；`state` 改为 `PlayerState` 枚举；新增 `PlayerProfile` 接口
- [x] `InputSystem.ts`：新增 `E` 键触发 `use`，`Q` 键触发 `leave`
- [x] `GameObjectSprite.ts`：tooltip 改为 `名称 (currentUsers/maxUsers)`，已满时追加"— 使用中"
- [x] `HUD.tsx`：展示档案（名称/年龄/ID）、位置/朝向、state/stateLabel/usingObjectId、HP/Energy 进度条、buffs/tags 标签

**验收：**
- I 键阅读描述，E 键进入使用，Q 键退出，功能互不干扰
- 使用中玩家 `state == "using"`，`stateLabel` 显示如"玩家 正在沙发上休息"
- 进入/离开时 `buffs`/`tags` 在 HUD 正确同步显示/清除
- 对象已满时 E 键返回失败，tooltip 显示 `1/1 — 使用中`
- HUD 实时展示所有角色信息（档案、位置、状态、属性、效果）

---

---

### 阶段 7：Buff 系统实装 ✅

**目标：** Buff 从纯展示升级为实际运算，驱动玩家属性和行为约束

**步骤 1 — 后端：重构 Buff 数据结构**

- [x] `object_types.py`：effects 每条加 `mode`（`while_active` / `instant`）、`duration`（instant 专用）
- [x] `world_state.py`：`_player` 加 `canMove`、`canInteract`、`canUse`、`moveSpeed`；重构 `enter_object`，按 mode 创建 buff 实例（含 `source`、`remaining`）；`leave_object` 只移除 `while_active` 且 `source` 匹配的 buff
- [x] `models/player.py`：`Buff` 模型加 `mode`、`remaining`、`source`；`Player` 加四个新字段

**步骤 2 — 后端：实现 Buff Tick 引擎**

- [x] 新建 `back_end/game/buff_tick.py`：实现 `run_tick(player, delta)`，步骤：① 递减/移除 instant buff ② 重置状态控制字段 ③ 遍历 buffs 执行 EFFECT_HANDLERS
- [x] 在 `EFFECT_HANDLERS` 中注册：`energy_regen`、`hp_regen`、`no_move`、`no_interact`、`no_use`、`move_speed`
- [x] `routers/player.py`：`GET /player` 返回前调用 `run_tick()`

**步骤 3 — 后端：action 校验**

- [x] `routers/actions.py`：`handle_move` 校验 `canMove`；`handle_interact` 校验 `canInteract`；`handle_use` 校验 `canUse`

**步骤 4 — 前端：更新类型与 HUD**

- [x] `types/index.ts`：`Buff` 加 `mode`、`remaining`、`source`；`Player` 加 `canMove`、`canInteract`、`canUse`、`moveSpeed`
- [x] `InputSystem.ts`：读取 `player.moveSpeed`，动态调整 `MOVE_INTERVAL`
- [x] `HUD.tsx`：buff 标签展示 `remaining`（instant 型显示剩余秒数）

**验收：**
- 使用沙发时 `energy_regen` buff 每 tick 实际恢复体力，HUD 数值变化
- 使用含 `no_move` buff 的 object 时，方向键无效，返回 `move_disabled`
- 离开 object 后 `while_active` buff 清除，`instant` buff 继续计时直到归零
- `move_speed` buff 实际改变移动速度（前端 MOVE_INTERVAL 随之变化）

---

## 未来阶段

| 阶段 | 内容 |
|------|------|
| 阶段 8 | WebSocket 替换轮询，实时状态同步 |
| 阶段 9 | 多 NPC / Agent 系统接入 |
| 阶段 10 | 聊天系统 |
