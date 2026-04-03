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

## 6. Agent 扩展预留

Agent 接入时复用同一 `/action` 接口，`entityId` 改为 agent ID，其余结构完全一致：

```json
{
  "entityId": "agent_01",
  "action": {
    "type": "move",
    "payload": { "direction": "up" }
  }
}
```

以下接口为 agent 管理预留，当前不实现：

```
POST /agent/register     # 注册 agent
GET  /agent/{id}/status  # 查询 agent 状态
```
