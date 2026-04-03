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

### 阶段 6：Object 使用系统

**目标：** Object 支持进入/退出使用，追踪使用者，前端展示使用状态

**步骤 1 — 后端：扩展 Object 类型定义**

- [ ] `object_types.py`：所有类型加 `max_users`、`use_state_label`、`effects`
- [ ] `world_state.py`：`_build_objects()` 补充运行时字段 `current_users=0`、`user_list=[]`；新增 `enter_object(obj_id, entity_id)` / `leave_object(entity_id)` 函数

**步骤 2 — 后端：新增 use / leave handler**

- [ ] `models/world.py`：`GameObject` 加 `maxUsers`、`currentUsers`、`userList`、`useStateLabel`、`effects` 字段
- [ ] `models/player.py`：`state` 改为 `str`（支持自定义文字，如"player_01 正在游玩游戏机"）
- [ ] `routers/actions.py`：注册 `use` handler（校验 available，调用 `enter_object`，更新玩家 state）；注册 `leave` handler（调用 `leave_object`，玩家 state 恢复 idle）

**步骤 3 — 前端：更新类型与 UI**

- [ ] `types/index.ts`：`GameObject` 接口加新字段；`Player.state` 改为 `string`
- [ ] `InputSystem.ts`：新增 `E` 键触发 `use`，`Q` 键触发 `leave`
- [ ] `GameObjectSprite.ts`：tooltip 改为 `名称 (currentUsers/maxUsers)`，已满时追加"— 使用中"

**验收：**
- I 键阅读描述，E 键进入使用，Q 键退出，功能互不干扰
- 使用中玩家 state 显示自定义文字（如"player_01 正在游玩游戏机"）
- 对象已满时 E 键返回失败，tooltip 显示 `1/1 — 使用中`
- effects 字段在对象数据中存在并可正确返回（展示用，不运算）

---

## 未来阶段

| 阶段 | 内容 |
|------|------|
| 阶段 7 | WebSocket 替换轮询，实时状态同步 |
| 阶段 8 | 多 NPC / Agent 系统接入 |
| 阶段 9 | 聊天系统 |
