# 后端 API 规范

**Base URL：** `http://localhost:8000`

**说明：** 所有操作均走后端接口，为未来 agent 系统与多人扩展做准备。

---

## 1. 查询接口

### GET /world

获取完整世界数据（地图、对象、世界状态）。

**响应：**

```json
{
  "tiles": [
    { "x": 0, "y": 0, "walkable": true, "objectId": null },
    { "x": 1, "y": 0, "walkable": false, "objectId": "tree_01" }
  ],
  "objects": [
    {
      "id": "tree_01",
      "name": "老橡树",
      "position": { "x": 1, "y": 0 },
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

### GET /objects

获取所有场景对象列表。

**响应：**

```json
[
  {
    "id": "well_01",
    "name": "古老的水井",
    "position": { "x": 5, "y": 5 },
    "interactable": true,
    "description": "井水清澈，似乎深不见底。"
  }
]
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

## 2. 行为接口

### POST /action/move

玩家移动。

**请求体：**

```json
{
  "playerId": "player_01",
  "direction": "up"
}
```

或点击移动（目标 tile）：

```json
{
  "playerId": "player_01",
  "targetTile": { "x": 5, "y": 3 }
}
```

`direction` 可选值：`"up"` | `"down"` | `"left"` | `"right"`

**响应（成功）：**

```json
{
  "success": true,
  "facing": "up",
  "position": { "x": 3, "y": 3 },
  "state": "idle"
}
```

**响应（失败，tile 不可行走）：**

```json
{
  "success": false,
  "facing": "up",
  "reason": "tile_not_walkable"
}
```

> `facing` 字段在成功和失败时均返回。即使目标格不可行走，玩家朝向也会更新为尝试移动的方向。

---

### POST /action/interact

玩家与对象交互。

**请求体：**

```json
{
  "playerId": "player_01",
  "objectId": "tree_01"
}
```

**响应（成功）：**

```json
{
  "success": true,
  "message": "一棵粗壮的老橡树，树皮上刻着一些符文。",
  "playerState": "interacting"
}
```

**响应（失败，距离不够）：**

```json
{
  "success": false,
  "reason": "not_adjacent"
}
```

---

## 3. 错误码

| HTTP 状态码 | 含义 |
|-------------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |

---

## 4. Tick 说明

- 后端以 `tickRate = 1 tick / 200ms` 推进世界状态
- MVP 阶段前端通过轮询 `GET /world` 同步状态
- 未来可升级为 WebSocket 实时推送

---

## 5. 扩展预留

以下接口为未来 agent 系统预留，MVP 阶段不实现：

```
POST /agent/register     # 注册 agent
POST /agent/action       # agent 执行行为
GET  /agent/{id}/status  # 查询 agent 状态
```
