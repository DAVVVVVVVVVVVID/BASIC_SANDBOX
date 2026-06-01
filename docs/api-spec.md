# 后端 API 规范

**Base URL：** `http://localhost:8000`

**说明：** 所有实体（玩家、未来的 agent）的行为均通过统一的 `POST /action` 接口执行。查询接口只读，不触发任何状态变化。

---

## 1. 查询接口

### GET /world

获取完整世界数据（地图、对象、世界状态）。

**响应：**

```json
{
  "tiles": [
    { "x": 0, "y": 0, "type": "wall", "walkable": false, "objectId": null },
    { "x": 1, "y": 0, "type": "floor", "walkable": true, "objectId": "tree_01" }
  ],
  "objects": [
    {
      "id": "tree_01",
      "type": "tree",
      "name": "老橡树",
      "position": { "x": 1, "y": 0 },
      "tiles": [{ "x": 1, "y": 0 }],
      "sprite": "tree",
      "interactable": true,
      "description": "一棵粗壮的老橡树，树皮上刻着一些符文。"
    }
  ],
  "worldState": {
    "date": "2001-12-30",
    "time": "08:00",
    "isDay": true,
    "weather": "sunny"
  }
}
```

---

### GET /player

获取当前玩家状态。每次调用会触发一次 buff tick 并检测 max_duration 是否到期。

**响应：**

```json
{
  "id": "player_01",
  "position": { "x": 3, "y": 4 },
  "facing": "down",
  "state": "idle",
  "stateLabel": null,
  "hp": 100,
  "energy": 80,
  "usingObjectId": null,
  "buffs": [],
  "tags": [],
  "canMove": true,
  "canInteract": true,
  "canUse": true,
  "moveSpeed": 1.0,
  "pendingMessage": null,
  "profile": { "id": "player_01", "name": "玩家", "age": 25 }
}
```

| 字段 | 说明 |
|------|------|
| `pendingMessage` | 后端自动触发的事件消息（如 max_duration 到期自动退出），读取后自动清除；无事件时为 `null` |

---

### GET /events

获取当前世界事件列表。

**响应：**

```json
[
  {
    "id": "event_entrance",
    "tiles": [
      { "x": 0, "y": 5 },
      { "x": 0, "y": 6 }
    ],
    "description": "你来到了村庄入口。"
  }
]
```

---

### GET /history

获取最近的行为日志列表（最多保留 20 条，按时间升序，最新在末尾）。

**响应：**

```json
[
  {
    "timestamp": "2001-12-30T08:00:01.234",
    "entityId": "player_01",
    "type": "move",
    "payload": { "direction": "up" },
    "success": true,
    "reason": null
  },
  {
    "timestamp": "2001-12-30T08:00:02.456",
    "entityId": "player_01",
    "type": "interact",
    "payload": {},
    "success": false,
    "reason": "no_object_in_front"
  }
]
```

| 字段 | 说明 |
|------|------|
| `timestamp` | ISO 8601 格式，记录 action 执行时刻 |
| `entityId` | 执行行为的实体 ID |
| `type` | 行为类型（move / turn / interact / …） |
| `payload` | 行为参数（原样记录） |
| `success` | 是否执行成功 |
| `reason` | 失败原因，成功时为 null |

> 日志存于内存，最多保留最新 20 条，超出时自动丢弃最旧的记录。重启后清空。

---

## 2. 统一行为接口

### POST /action

**所有实体（玩家、agent）的行为均通过此接口执行。**

后端通过 `action.type` 路由到对应的 handler，payload 由 type 决定。

#### 请求体结构

```json
{
  "entityId": "player_01",
  "action": {
    "type": "<action_type>",
    "payload": { ... }
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `entityId` | string | 执行行为的实体 ID（玩家或 agent） |
| `action.type` | string | 行为类型（见下表） |
| `action.payload` | object | 行为参数，由 type 决定结构 |

#### 通用响应结构

```json
{
  "success": true,
  "type": "<action_type>",
  "result": { ... }
}
```

失败时：

```json
{
  "success": false,
  "type": "<action_type>",
  "reason": "<error_code>"
}
```

---

### 行为类型一览

| type | 说明 | payload | 触发键 |
|------|------|---------|--------|
| `move` | 移动一格或前往目标 tile | `{ direction }` 或 `{ targetTile }` | 方向键 / 鼠标 |
| `move_n` | 向某方向移动 N 格，逐格校验，遇阻停止 | `{ direction, steps }` | agent |
| `move_to_area` | 移动到目标区域距离当前位置最近的可行走 tile | `{ area_type, area_id }` | agent |
| `turn` | 仅改变朝向，不移动 | `{ direction }` | Ctrl + 方向键 |
| `interact` | 阅读正前方对象描述，不改变状态 | `{}` | `I` |
| `use` | 进入使用正前方对象，加入 userList | `{}` | `E` |
| `leave` | 退出当前正在使用的对象 | `{}` | `Q` |

---

### move

**payload（方向移动）：**

```json
{
  "direction": "up"
}
```

`direction` 可选值：`"up"` | `"down"` | `"left"` | `"right"`

**payload（目标 tile 移动）：**

```json
{
  "targetTile": { "x": 5, "y": 3 }
}
```

**响应（成功）：**

```json
{
  "success": true,
  "type": "move",
  "result": {
    "facing": "up",
    "position": { "x": 3, "y": 3 },
    "state": "idle"
  }
}
```

**响应（失败，tile 不可行走）：**

```json
{
  "success": false,
  "type": "move",
  "reason": "tile_not_walkable",
  "result": {
    "facing": "up"
  }
}
```

> `facing` 在成功和失败时均返回。即使目标格不可行走，朝向也会更新为尝试移动的方向。

---

### move_n

向某方向连续移动最多 N 格，逐格校验可行走性，遇到不可行走格立即停止。不修改原有 `move` 行为。

**payload：**

```json
{
  "direction": "up",
  "steps": 3
}
```

`direction` 可选值：`"up"` | `"down"` | `"left"` | `"right"`
`steps`：正整数，最多尝试移动的格数。

**响应（成功移动至少一格）：**

```json
{
  "success": true,
  "type": "move_n",
  "result": {
    "facing": "up",
    "position": { "x": 3, "y": 1 },
    "steps_taken": 2
  }
}
```

**响应（第一格即不可行走）：**

```json
{
  "success": false,
  "type": "move_n",
  "reason": "tile_not_walkable",
  "result": {
    "facing": "up",
    "position": { "x": 3, "y": 3 },
    "steps_taken": 0
  }
}
```

> `steps_taken` 为实际移动的格数，可能小于请求的 `steps`。朝向始终更新为请求的 `direction`。

---

### turn

**payload：**

```json
{
  "direction": "left"
}
```

**响应：**

```json
{
  "success": true,
  "type": "turn",
  "result": {
    "facing": "left"
  }
}
```

---

### interact

阅读正前方对象的描述，**不改变任何状态**。

**payload：** `{}`

后端根据实体当前 `position + facing` 自动计算正前方格子。

**响应（成功）：**

```json
{
  "success": true,
  "type": "interact",
  "result": {
    "message": "一棵粗壮的老橡树，树皮上刻着一些符文。"
  }
}
```

**响应（失败，前方无对象）：**

```json
{
  "success": false,
  "type": "interact",
  "reason": "no_object_in_front"
}
```

---

### use

使用正前方对象。行为根据对象原型（`prototype`）分为两种：

- **instant（瞬间使用型）**：应用效果后立即完成，不进入 `using` 状态
- **continuous（持续使用型）**：进入 `using` 状态，等待 `Q` 键或 `max_duration` 到期退出

校验顺序（共同）：`canUse` → `interactable` → （continuous：`currentUsers < maxUsers`）

**payload：** `{}`

**响应（instant 成功）：**

```json
{
  "success": true,
  "type": "use",
  "result": {
    "message": "你使用了马桶，感觉轻松多了。",
    "objectId": "toilet_01"
  }
}
```

**响应（continuous 成功）：**

```json
{
  "success": true,
  "type": "use",
  "result": {
    "message": "你躺在床上，闭上眼睛，困意慢慢袭来。",
    "playerState": "using",
    "stateLabel": "玩家 正在睡觉",
    "objectId": "bed_01",
    "currentUsers": 1,
    "maxUsers": 1
  }
}
```

**响应（失败，已满）：**

```json
{
  "success": false,
  "type": "use",
  "reason": "object_full",
  "result": {
    "message": "床上已经有人了。",
    "currentUsers": 1,
    "maxUsers": 1
  }
}
```

**响应（失败，前方无对象）：**

```json
{
  "success": false,
  "type": "use",
  "reason": "no_object_in_front"
}
```

| reason | 说明 |
|--------|------|
| `no_object_in_front` | 正前方没有对象 |
| `not_interactable` | 对象不可交互，`result.message` 为对象的 `failureMessage` |
| `object_full` | 对象已满（仅 continuous），`result.message` 为对象的 `failureMessage` |
| `use_disabled` | 当前无法使用对象（buff 限制）|

---

### leave

退出当前正在使用的对象，从 `userList` 移除，玩家状态恢复 `idle`。

**payload：** `{}`

**响应（成功）：**

```json
{
  "success": true,
  "type": "leave",
  "result": {
    "playerState": "idle",
    "objectId": "arcade_01",
    "currentUsers": 0,
    "maxUsers": 1
  }
}
```

**响应（失败，当前未在使用任何对象）：**

```json
{
  "success": false,
  "type": "leave",
  "reason": "not_using_any_object"
}
```

---

## 3. 错误码

| HTTP 状态码 | 含义 |
|-------------|------|
| 200 | 成功（含业务逻辑失败，见 `success` 字段） |
| 400 | 请求参数错误（entityId 缺失、action.type 不合法等） |
| 404 | 实体不存在 |
| 500 | 服务器内部错误 |

---

## 4. Tick 说明

- 后端世界状态以 `tickRate = 1 tick / 200ms` 为参考推进
- 前端通过轮询 `GET /world` 同步状态（每 200ms）
- 未来可升级为 WebSocket 实时推送

---

## 4. 新增行为类型（扩展方式）

需要新增行为时，**不修改接口路径**，只需：

1. 在后端 Action Dispatcher 中注册新的 `type` → handler
2. 定义 payload 结构与响应格式
3. 更新此文档的"行为类型一览"表

**示例（未来预留）：**

| type | 说明 | payload |
|------|------|---------|
| `pick` | 拾取物品 | `{ itemId }` |
| `cook` | 使用灶台烹饪 | `{ recipeId }` |
| `talk` | 与 NPC 对话 | `{ npcId }` |
| `sleep` | 使用床休息 | `{}` |

---

## 6. Agent 专用接口

### GET /agent/perceive

一次返回 agent 感知所需的全部信息。

**Query 参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `entity_id` | string | `player_01` | 实体 ID |
| `vision_size` | int | `3` | 视野边长（正方形），奇数直接使用，偶数自动 +1 取奇，范围 1–21 |

**响应：**

```json
{
  "arena_tree": {
    "id": "town", "name": "小镇",
    "sector": {
      "id": "house_A", "name": "A号房子",
      "arenas": [
        {
          "id": "bedroom", "name": "卧室", "current": true,
          "objects": [
            { "id": "sofa_01", "name": "沙发", "interactable": true },
            { "id": "bed_01",  "name": "床",   "interactable": true }
          ]
        },
        {
          "id": "kitchen", "name": "厨房", "current": false,
          "objects": [
            { "id": "fridge_01", "name": "冰箱", "interactable": true }
          ]
        }
      ]
    }
  },
  "vision_tiles": [
    {
      "x": 2, "y": 2,
      "type": "floor", "walkable": true,
      "world": "town", "sector": "house_A", "arena": "bedroom",
      "object": null
    }
  ],
  "front_object": { "id": "sofa_01", "name": "沙发" }
}
```

**说明：**
- `arena_tree`：嵌套树 `world → sector → arenas[]`，展示当前 sector 内**所有** arena 及其 objects，**不含坐标**；`current: true` 标记当前所在 arena；当 cognitive_map 中找不到对应名称时，`name` 回退为原始 ID
- `vision_tiles`：以实体当前位置为中心，边长 `vision_size`（偶数自动取奇）的正方形内所有合法 tile，超出地图边界的 tile 不返回
- `front_object`：正前方一格的 object 信息，无 object 时为 `null`

---

### GET /agent/arena-tiles

返回指定 arena 内所有 tile 的坐标列表。

**Query 参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `arena_id` | string | 目标 arena ID |

**响应：**

```json
{
  "arena_id": "bedroom",
  "tiles": [
    { "x": 3, "y": 1 },
    { "x": 4, "y": 1 }
  ]
}
```

---

### GET /agent/object-position

返回指定 object 的坐标（锚点 position）。

**Query 参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `object_id` | string | 目标 object ID |

**响应（成功）：**

```json
{
  "object_id": "bed_01",
  "position": { "x": 3, "y": 1 },
  "tiles": [
    { "x": 3, "y": 1 },
    { "x": 4, "y": 1 }
  ]
}
```

- `position`：对象锚点（左上角）
- `tiles`：对象占用的所有 tile 坐标（单格对象 tiles 长度为 1）
- `adjacent_walkable`：对象所有占用格的四邻域中可行走的格子列表（已去重），可直接用于导航

**失败（object 不存在）：** HTTP 404

---

### move_to_area

在目标区域内选取距离当前位置最近的可行走 tile（曼哈顿距离），将实体移动过去。

**payload：**

```json
{
  "area_type": "arena",
  "area_id": "bedroom"
}
```

`area_type` 可选值：`"arena"` | `"sector"` | `"world"`

**响应（成功）：**

```json
{
  "success": true,
  "type": "move_to_area",
  "result": {
    "facing": "down",
    "position": { "x": 4, "y": 2 },
    "area_type": "arena",
    "area_id": "bedroom"
  }
}
```

**响应（失败，目标区域无可行走格）：**

```json
{
  "success": false,
  "type": "move_to_area",
  "reason": "no_walkable_tiles"
}
```

| reason | 说明 |
|--------|------|
| `invalid_area_type` | area_type 不在允许值内 |
| `missing_area_id` | area_id 为空 |
| `no_walkable_tiles` | 目标区域内无可行走 tile |
| `move_disabled` | 实体当前无法移动 |

---

## 5. 数据结构说明

### Buff

玩家身上的持续/限时状态修改器。

| 字段 | 类型 | 说明 |
|------|------|------|
| `key` | string | 效果标识，如 `no_move`、`energy_regen` |
| `value` | float | 数值（无意义的 key 为 0.0） |
| `mode` | string | `"persistent"` 持续型 / `"timed"` 限时型 |
| `remaining` | float \| null | `persistent` 时为 null；`timed` 时为剩余游戏毫秒数 |
| `source` | string | 来源标识（通常为 object id，如 `"bed_01"`） |

**Buff key 一览：**

| key | 作用 | value 含义 |
|-----|------|-----------|
| `no_move` | 禁止移动 | 无 |
| `no_interact` | 禁止交互 | 无 |
| `no_use` | 禁止使用 Object | 无 |
| `energy_regen` | Energy 每秒变化 | 正 = 恢复，负 = 消耗（点/秒） |
| `hp_regen` | HP 每秒变化 | 正 = 恢复，负 = 消耗（点/秒） |
| `move_speed` | 移动速度倍率 | 倍数 |

### Object Effect

Object 的 `effects` 列表支持三种 type，适用原型不同：

| type | 适用原型 | 触发时机 | 说明 |
|------|---------|---------|------|
| `buff` | continuous | 进入时创建，离开/计时结束时移除 | 见上方 Buff 结构；mode 可为 `persistent` 或 `timed` |
| `instant_effect` | instant / continuous | 进入时一次性结算，不进 buff 列表 | `key` 为 `energy` 或 `hp`，`value` 为变化量 |
| `tag` | continuous | 进入时加入，离开时移除 | 纯标记字符串，不参与运算 |

> instant 原型的 `effects` 中，`buff` 只允许 `timed` mode；不允许 `persistent` buff 和 `tag`。

### Object 原型

| prototype | 说明 | 专有字段 |
|-----------|------|---------|
| `instant` | 瞬间使用型，应用效果后立即完成 | 无 `max_users`、`use_state_label` |
| `continuous` | 持续使用型，进入 using 状态直至退出 | `maxUsers`、`useStateLabel`、`maxDuration`、`leaveMessage` |

`maxDuration`：`float`（秒）或 `null`（无限）。到期时后端自动触发 leave，`pendingMessage` 中写入 `leaveMessage` 内容。

---

## 6. 管理接口（Admin）

用于调试和手动干预玩家状态，不记录行动日志。

### GET /admin/player/buffs

返回玩家当前所有 buff。

**响应：**
```json
{
  "buffs": [
    { "key": "no_move", "value": 0.0, "mode": "persistent", "remaining": null, "source": "bed_01" }
  ]
}
```

---

### DELETE /admin/player/buffs

强制清除玩家所有 buff（不离开当前对象）。

**响应：**
```json
{ "ok": true, "cleared": 3 }
```

---

### POST /admin/player/force-reset

强制重置玩家状态：若正在使用对象则先 leave，然后清除所有 buff 和 tag，状态归 idle。

**请求体（可选）：**
```json
{ "entity_id": "player_01" }
```

**响应：**
```json
{ "ok": true, "left_object": "bed_01", "cleared_buffs": 3 }
```

---

## 7. 对话系统（Chat）

对话系统支持两个 Player 之间（或多人）进行即时文字对话。

### 新增状态

**ChatRequest（对话邀请）**
```json
{
  "request_id": "abc123",
  "from_entity_id": "player_01",
  "to_entity_ids": ["player_02"],
  "greeting": "你好，有时间聊聊吗？",
  "status": "pending | active | rejected | expired",
  "accepted_ids": [],
  "rejected_ids": [],
  "chat_room_id": null
}
```

**ChatRoom（聊天室）**
```json
{
  "chat_room_id": "def456",
  "participants": ["player_01", "player_02"],
  "messages": [
    { "seq": 1, "from_entity_id": "player_01", "content": "你好", "timestamp": "..." }
  ],
  "events": [
    { "seq": 2, "type": "player_exit", "entity_id": "player_02", "timestamp": "..." }
  ],
  "status": "active | closed"
}
```

**Buff：`chat_active`**
进入聊天室时对参与者施加，退出时移除。效果：
- `canMove = false`（移动动作失败，reason: `move_disabled`）
- `canUse = false`（use/leave 动作失败，reason: `use_disabled`）
- `state = "talking"`

---

### GET /chat/nearby

查询与请求方处于同一 Arena 的其他 Player。

**Query:** `entity_id=<str>`

**响应：**
```json
{
  "players": [
    { "entity_id": "player_02", "name": "小刚", "arena_id": "living_room" }
  ]
}
```

---

### POST /chat/request

向一个或多个 Player 发起对话邀请。

**请求体：**
```json
{
  "from_entity_id": "player_01",
  "to_entity_ids": ["player_02"],
  "greeting": "你好，有时间聊聊吗？"
}
```

**响应：**
```json
{ "request_id": "abc123" }
```

---

### GET /chat/request/{request_id}

查询对话请求当前状态。发起方用于轮询是否被接受（检测 `chat_active` buff 后调用以获取 `chat_room_id`）。

**响应：**
```json
{
  "request_id": "abc123",
  "status": "pending | active | rejected | expired",
  "chat_room_id": "def456",
  "accepted_ids": ["player_02"],
  "rejected_ids": []
}
```

---

### GET /chat/pending

查询该 entity 收到的待处理对话请求。

**Query:** `entity_id=<str>`

**响应：**
```json
{
  "requests": [
    {
      "request_id": "abc123",
      "from_entity_id": "player_01",
      "from_name": "小明",
      "greeting": "你好，有时间聊聊吗？"
    }
  ]
}
```

---

### POST /chat/respond

接受或拒绝对话邀请。

**请求体：**
```json
{
  "entity_id": "player_02",
  "request_id": "abc123",
  "accept": true,
  "message": "好啊，说吧"
}
```

**响应（接受 + 聊天室已创建）：**
```json
{
  "chat_room_id": "def456",
  "status": "room_created",
  "participants": ["player_01", "player_02"]
}
```

**响应（多人邀请，等待其他人）：**
```json
{ "chat_room_id": null, "status": "waiting" }
```

**响应（拒绝）：**
```json
{ "chat_room_id": null, "status": "rejected" }
```

聊天室创建时机：
- 单人邀请：被邀请者接受后立即创建
- 多人邀请：所有人响应后（或超时 60 秒后），将接受者放入同一聊天室

---

### GET /chat/room/{chat_room_id}

轮询聊天室状态（增量拉取）。

**Query:** `entity_id=<str>&since_seq=<int>`

`since_seq` 用于增量拉取，只返回 seq > since_seq 的消息和事件。

**响应：**
```json
{
  "status": "active",
  "participants": ["player_01", "player_02"],
  "messages": [
    { "seq": 1, "from_entity_id": "player_01", "from_name": "小明", "content": "你好", "timestamp": "..." }
  ],
  "events": [
    { "seq": 2, "type": "player_exit", "entity_id": "player_02", "name": "小刚", "timestamp": "..." }
  ]
}
```

---

### POST /chat/message

在聊天室中发言。

**请求体：**
```json
{
  "entity_id": "player_01",
  "chat_room_id": "def456",
  "content": "最近过得怎么样？"
}
```

**响应：**
```json
{ "seq": 3 }
```

---

### POST /chat/exit

退出聊天室。移除 `chat_active` buff，恢复移动/使用能力。若房间内无人则关闭房间。

**请求体：**
```json
{
  "entity_id": "player_01",
  "chat_room_id": "def456"
}
```

**响应：**
```json
{ "room_closed": false }
```
若玩家未使用任何对象，`left_object` 为 `null`。
