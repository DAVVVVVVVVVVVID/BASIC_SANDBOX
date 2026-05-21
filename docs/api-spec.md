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

获取当前玩家状态。

**响应：**

```json
{
  "id": "player_01",
  "position": { "x": 3, "y": 4 },
  "facing": "down",
  "state": "idle",
  "hp": 100,
  "energy": 80
}
```

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
| `move_to_area` | 移动到目标区域随机可行走位置 | `{ area_type, area_id }` | agent |
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

进入使用正前方对象。校验顺序：`interactable` → `available`（`currentUsers < maxUsers`）。

**payload：** `{}`

**响应（成功）：**

```json
{
  "success": true,
  "type": "use",
  "result": {
    "playerState": "player_01 正在游玩游戏机",
    "objectId": "arcade_01",
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
  "result": { "currentUsers": 1, "maxUsers": 1 }
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

## 5. 新增行为类型（扩展方式）

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

在目标区域内随机选取一个可行走 tile，将实体移动过去。

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

## 5. 管理接口（Admin）

用于调试和手动干预玩家状态，不记录行动日志。

### GET /admin/player/buffs

返回玩家当前所有 buff。

**响应：**
```json
{
  "buffs": [
    { "key": "no_move", "value": 0.0, "mode": "while_active", "remaining": null, "source": "bed_01" }
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
若玩家未使用任何对象，`left_object` 为 `null`。
