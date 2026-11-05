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
    "date": "2026-11-05",
    "time": "21:03:17",
    "period": "dusk",
    "running": true,
    "speed": 1.0,
    "weather": "sunny"
  }
}
```

| worldState 字段 | 说明 |
|------|------|
| `date` / `time` | 游戏时刻（`YYYY-MM-DD` / `HH:MM:SS`）。时间系统为「真实起点 + 倍率」：首次启动取真实当前时间（时区 `Asia/Shanghai`，环境变量 `SANDBOX_TZ` 可改），`game_now = anchor_game + (now − anchor_real) × speed`；重启后从检查点恢复锚点，游戏时间连续 |
| `period` | `morning`(06–08) / `day`(08–20) / `dusk`(20–22) / `night`(22–06) |
| `running` | 是否推进。默认 `true`（环境变量 `SANDBOX_TIME_RUNNING=0` 可改） |
| `speed` | 倍率，默认 `1.0`（与现实 1:1），下限 1.0 |

> **只读**：`GET /world` 不推进时间、不跑 buff tick、不清理离线玩家。这些都由后端的独立后台 tick 任务（200 ms）完成，没有任何客户端轮询时状态照样演化。

| objects[] 新增字段 | 说明 |
|------|------|
| `advertise` | **B5** Sims 式广告值 `{ fullness \| energy \| social \| fun \| mood: 0–100 }`，供规划器做软偏好打分；来自 `object_types.json` 的 `advertise`，可能为空对象 |

| players[] 字段 | 说明 |
|------|------|
| `id` / `name` / `position` / `facing` / `state` | 不变 |
| `controller` | **B6** `"human"` \| `"agent"` |
| `online` | **B6** agent 10 s 无心跳为 `false`（身体仍在原地、仍参与 tick）；human 无心跳直接从列表消失 |

---

### GET /player/{player_id}

获取玩家状态，并刷新该玩家的心跳（10 s 无心跳的人类玩家会被清除）。buff tick 由后台任务驱动，与本接口无关。

**响应：**

```json
{
  "id": "player_01",
  "position": { "x": 3, "y": 4 },
  "facing": "down",
  "state": "idle",
  "stateLabel": null,
  "hp": 70.0,
  "fullness": 70.0,
  "energy": 100.0,
  "social": 60.0,
  "fun": 60.0,
  "mood": 65.0,
  "emotion_tags": [],
  "closeness": {},
  "controller": "human",
  "last_tick_ts": 1762347797.42,
  "usingObjectId": null,
  "buffs": [],
  "tags": [],
  "canMove": true,
  "canInteract": true,
  "canUse": true,
  "moveSpeed": 1.0,
  "pendingMessage": null
}
```

| 字段 | 说明 |
|------|------|
| `fullness` / `energy` / `social` / `fun` / `mood` | 需求值，范围 0–100（ARCHITECTURE §2.5 七变量）。human 初值：fullness 70、energy 100、social 60、fun 60、mood = 65 + 0.2·(E−50) − 0.3·(N−50)（E、N 来自 join 的 `profile`，默认 50 → 65）；agent 初值从自我层 `GET /self/state` 种入（不可达时同 human）。**自然衰减（B4）**由每个 player 常驻的 `decay` 元 buff 执行：fullness −12/游戏小时、energy −8/h（凌晨 0–6 点 ×1.5）、social −6/h（`scene=live` 时 −0.12/s）、fun −10/h、mood 指数回 `mood_base`（半衰期 sandbox 120 分钟、live 70 s）、closeness 每游戏日 −1 |
| `hp` | **`fullness` 的别名**，两者始终相等。过渡一个版本后删除（假设），新对接请读 `fullness` |
| `mood_base` | **W2** mood 回归基线 = 65 + 0.2·(E−50) − 0.3·(N−50)；agent 种入时按自我层的 `ocean` 重算 |
| `emotion_tags` | 情绪标签列表，复用 Buff 结构（`key` = 标签名如 `smug`，`mode="timed"`，`remaining` 毫秒倒计时，到期自动移除）。来源：`POST /player/{id}/effects` 的 `emotion_tag`，或自我层种入 |
| `closeness` | `{ entity_id: 0–100 }` 亲密度。来源：`closeness_delta` 效果；每游戏日 −1 |
| `controller` | `"human"` \| `"agent"`，由 `POST /player/join` 的 `controller` 决定 |
| `online` | **B6** 心跳状态。human 10 s 无心跳被删除；agent 只标 `false`，`GET /player/{id}` 或 `POST /player/rejoin` 恢复 `true` |
| `scene` | **B4** `"sandbox"` \| `"live"`，决定衰减速率；由 `POST /player/{id}/effects` 的 `scene` 切换（B11 直播台接入后由 use/leave 切） |
| `agent_id` | controller=agent 时对接自我层的 agent id（`profile.agent_id`，缺省取 name 的 slug，假设）；human 为 `null` |
| `last_tick_ts` | 上次 buff tick 的**游戏时刻**，ISO 8601 含时区（§3.7 裁定 3），如 `"2026-11-06T21:03:00+08:00"`；供自我层 catch_up 对账 |
| `buffs` | 恒含一条 `{"key":"decay","source":"decay","mode":"persistent"}` 元 buff（admin 清 buff / force-reset 不会清它） |
| `pendingMessage` | 后端自动触发的事件消息（如 max_duration 到期自动退出），读取后自动清除；无事件时为 `null` |

> 字段只增不删：旧字段形状不变。

---

### POST /player/join

```json
{ "name": "鲸仔", "controller": "agent", "profile": { "E": 80, "N": 55, "agent_id": "whale" } }
```

| 字段 | 说明 |
|------|------|
| `name` | 必填，非空 |
| `controller` | **B6** `"human"`（默认）\| `"agent"`；其他值 400。与 AGENT_V2 `join_player(controller, profile)` 同名 |
| `profile` | **B6** 可选 `{ E, N, agent_id? }`：E、N 决定 `mood_base`；`agent_id` 是自我层里的 agent id（缺省取 name 的 slug，假设） |

**响应：** `{ "playerId": "鲸仔_a1b2c3", "player": { ...与 GET /player 相同... } }`

> controller=agent 时，后端会同步 `GET {SELF_URL}/self/state?agent=<agent_id>`（3 s 超时）把七变量 / closeness / emotion_tags / ocean 种入本地；失败则按 §2.5 初值创建，不阻塞 join。

---

### POST /player/rejoin

**B6**：agent 进程崩溃 / 被 supervisor 重拉后，用同一 `playerId` 续接（她的身体一直留在原地）。

```json
{ "playerId": "鲸仔_a1b2c3" }
```

**响应：** 与 join 相同 `{ "playerId", "player" }`，`player.online` 置回 `true`、心跳刷新。不存在返回 404（此时应改调 join）。

---

### GET /player/{player_id}/state

**B13 ②**：七变量原始数值 + `last_tick_ts`，给自我层同步与评测。只读：不刷新心跳、不清 `pendingMessage`。

**响应：**

```json
{
  "id": "鲸仔_a1b2c3",
  "vars": { "fullness": 62.0, "energy": 71.5, "social": 48.0, "fun": 35.0, "mood": 68.0 },
  "mood_base": 69.5,
  "emotion_tags": [ { "key": "smug", "value": 0.0, "mode": "timed", "remaining": 31200.0, "source": "live:praise" } ],
  "closeness": { "achan": 72.0 },
  "scene": "sandbox",
  "controller": "agent",
  "online": true,
  "agent_id": "whale",
  "last_tick_ts": "2026-11-06T21:03:00+08:00",
  "recent_uses": { "fridge_01": 2 }
}
```

| 字段 | 说明 |
|------|------|
| `recent_uses` | **B5** 6 游戏小时内各物品的使用次数（供 novelty 折减） |

---

### POST /player/{player_id}/effects

**B13 ③**：推送与 `object_types.json` 同格式的 effect 列表（直播服务经自我层推「观众进入 +12 social +4 mood」等），可同时切换 `scene`。

```json
{
  "scene": "live",
  "source": "live:viewer_arrived",
  "effects": [
    { "type": "instant_effect", "key": "social", "value": 12 },
    { "type": "instant_effect", "key": "mood", "value": 4 },
    { "type": "buff", "key": "emotion_tag", "tag": "smug", "mode": "timed", "duration": 40000 },
    { "type": "closeness_delta", "target": "viewer_12345", "value": 3 },
    { "type": "buff", "key": "fun_regen", "value": 0.5, "mode": "timed", "duration": 5000 },
    { "type": "tag", "key": "streaming" }
  ]
}
```

| 字段 | 说明 |
|------|------|
| `effects[]` | 见 §5「Object Effect」。支持 `instant_effect`、`buff`（任意 handler key，含 `<var>_regen` / `<var>_delta` / `emotion_tag` / `closeness_delta`）、`tag`，以及简写 `{"type":"<var>_delta"}` / `{"type":"closeness_delta"}` / `{"type":"emotion_tag"}`。不认识的 key 计入 `skipped` |
| `scene` | 可选 `"sandbox"` \| `"live"`，非空即切换该 player 的衰减场景；其他值 400 |
| `source` | 可选，写进 buff 的 `source`，默认 `"effects"` |

**响应：** `{ "ok": true, "applied": 6, "skipped": 0, "state": { ...与 GET /player/{id}/state 相同... } }`；player 不存在 404。

---

### DELETE /player/{player_id}/leave

主动离开，返回 `{ "ok": true }`。

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

获取最近的行为日志列表（内存，最多保留 20 条，按时间升序，最新在末尾）。

**响应：**

```json
[
  {
    "timestamp": "2026-11-05T21:03:01.234",
    "entityId": "player_01",
    "type": "move",
    "payload": { "direction": "up" },
    "success": true,
    "reason": null,
    "label": null,
    "game_time": "2026-11-05T21:03:01+08:00",
    "controller": "human"
  },
  {
    "timestamp": "2026-11-05T21:03:02.456",
    "entityId": "player_01",
    "type": "interact",
    "payload": {},
    "success": false,
    "reason": "no_object_in_front",
    "label": null,
    "game_time": "2026-11-05T21:03:02+08:00",
    "controller": "human"
  }
]
```

| 字段 | 说明 |
|------|------|
| `timestamp` | ISO 8601 格式（真实时间），记录 action 执行时刻 |
| `entityId` | 执行行为的实体 ID |
| `type` | 行为类型（move / turn / interact / …） |
| `payload` | 行为参数（原样记录） |
| `success` | 是否执行成功 |
| `reason` | 失败原因，成功时为 null |
| `label` | `POST /action` 的 `logLabel`，没有则 null |
| `game_time` | **新增** 执行时刻的游戏时间（ISO，含时区） |
| `controller` | **新增** 执行者是 `human` 还是 `agent` |

> 每条日志同时 append 到 `data/actions/YYYY-MM-DD.jsonl`（按真实日期分文件，append-only，重启不丢）；内存只保留最近 20 条供本接口返回。`skipLog=true` 的 action 两处都不写。

---

### GET /history/log

从 JSONL 文件读取完整行动日志（供评测与自我层拉取）。

**Query：**

| 参数 | 说明 |
|------|------|
| `since` | ISO 时间（可只含日期），只返回 `timestamp >= since` 的记录；缺省 = 全部 |
| `entity` | 只返回该 `entityId` 的记录 |
| `limit` | 最多返回最新 N 条 |

**响应：** 与 `GET /history` 元素形状相同的数组，按时间升序。

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
| `object_cooldown` | **B5** 同一实体对同一物品 30 游戏分钟内再次 use（从上次 use 成功算起，instant 与 continuous 都算）。`result` 含 `objectId`、`cooldownRemaining`（剩余游戏秒）、`message` |
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

## 4. Tick 与持久化说明

- 后端有一个独立的 asyncio 后台任务，每 200 ms 一次 tick：`real_delta × speed → game_delta`，对所有 player 跑 buff handler、检测 max_duration、清理 10 s 无心跳的玩家。**不依赖任何客户端轮询。**
- 前端通过轮询 `GET /world` / `GET /player` 同步状态（只读）。
- 每 5 s 以及进程正常关停时，后端把全部运行时状态写入 SQLite 检查点 `data/sandbox.db`（players、object 使用状态、时间锚点、chat 请求与房间、`meta.last_tick_ts`）。启动时若有检查点则回填，并按停机时长补算一次 tick（`dt ≤ 8 游戏小时`，running=false 时不补）。`kill -9` 最多丢最后 5 s 的变化。
- 停机补算分段（§3.7 裁定 5）：前 4 游戏小时全量（物品 buff + 衰减）；4–8 h 只补 social / fun / mood / closeness 的衰减，fullness / energy 不再扣（她离线等于在睡，假设）。
- 数据目录默认 `back_end/data/`，环境变量 `SANDBOX_DATA_DIR` 可改。
- 未来可升级为 WebSocket 实时推送。

### 与自我层同步（§2.5）

| 项 | 说明 |
|---|---|
| 对象 | 只同步 `controller=agent` 的 player，自我层 agent id = `player.agent_id` |
| 种入 | join 与重启回填后 `GET {SELF_URL}/self/state?agent=…`，用返回的 `vars / closeness / emotion_tags / ocean / scene` 覆盖本地 |
| 上报 | 每 **30 游戏秒** `POST {SELF_URL}/self/state/delta`：`{"agent","scene","ts":<游戏时刻 ISO>,"vars_delta":{…},"source":"sandbox_tick"}`。**`vars_delta` 只含非衰减变化**（物品 buff、instant_effect、/effects 推送，取 clamp 后的实际变化量）；自然衰减两边各自按同一张速率表计算，自我层在收到 delta 前会先把自己的状态 catch_up 到 `ts`，所以不能把衰减再报一遍 |
| 失败 | 自我层不可达时本地照常 tick，失败批的 `vars_delta` 合回待发池，指数退避（≤ 30 s）后与后续变化一起重发 |
| 对账 | 自我层返回的 `vars` 与发批瞬间的本地快照之差记为 drift；`max|drift| > 0.5` 时把差值加回本地（以自我层为准，`SELF_SYNC_SNAP=0` 关闭只记录） |
| 观测 | `GET /admin/self-sync` |
| 配置 | `SELF_URL`（默认 `http://127.0.0.1:8100`）、`SELF_TOKEN`（Bearer，可空）、`SELF_SYNC=0` 整体关闭、`SELF_SYNC_SNAP_THRESHOLD`（默认 0.5） |
| 验证 | `uv run python scripts/verify_self_sync.py --self-url http://127.0.0.1:8100`（无服务时 `--mock`） |

### 时间控制

| 方法与路径 | 请求 | 响应 |
|---|---|---|
| `POST /time/toggle` | — | `worldState`（不含 weather）。暂停时游戏时间静止，恢复后从暂停点继续 |
| `POST /time/speed` | `{ "value": 60 }` | `{ "speed": 60.0 }`。切换前把当前游戏时刻折算成新锚点，时间不跳变；下限 1.0 |
| `POST /time/reset` | — | `worldState`。游戏时间回到真实当前时间，倍率回默认 |

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
  "front_object": { "id": "sofa_01", "name": "沙发" },
  "players_in_view": [ { "id": "achan_1a2b3c", "name": "阿蝉", "position": { "x": 3, "y": 2 }, "state": "idle" } ],
  "needs": {
    "fullness": "饿了",
    "energy": "还好",
    "social": "还好",
    "fun": "有点无聊，想找新鲜事",
    "mood": "开心",
    "emotion_tags": ["得意（刚被夸了）"],
    "lines": ["饿了", "有点无聊，想找新鲜事", "得意（刚被夸了）"],
    "hard": [],
    "closeness": { "achan_1a2b3c": { "name": "阿蝉", "tier": "很亲近" } },
    "recent_uses": { "fridge_01": 2 }
  }
}
```

**说明：**
- `arena_tree`：嵌套树 `world → sector → arenas[]`，展示当前 sector 内**所有** arena 及其 objects，**不含坐标**；`current: true` 标记当前所在 arena；当 cognitive_map 中找不到对应名称时，`name` 回退为原始 ID
- `vision_tiles`：以实体当前位置为中心，边长 `vision_size`（偶数自动取奇）的正方形内所有合法 tile，超出地图边界的 tile 不返回
- `front_object`：正前方一格的 object 信息，无 object 时为 `null`
- `players_in_view`（**B13**）：视野正方形内的其他 player
- `needs`（**B13**）：**只给分档文字，不给数值**（报告 §4.3）。阈值 low 25 / critical 15 / emergency 10；文案与自我层 `state.py` 的 `LABELS` 同源（沿用 mood.py `label()`）。`<var>` 未越阈值为 `"还好"`；`mood` < 35 为「有点委屈…」、> 75 为「开心」；`lines` 是越过阈值的全部文字（含 emotion_tags），`hard` 是 `<var><15` 的硬约束；`closeness` 对视野内 player 分档（≥70 很亲近 / ≥40 熟悉 / ≥15 认识 / 其余 陌生，阈值为假设）；`recent_uses` 同 `GET /player/{id}/state`

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
| `<var>_regen` | **B4** `fullness_regen` / `energy_regen` / `social_regen` / `fun_regen` / `mood_regen`：每游戏秒连续变化 | 点/游戏秒，正 = 恢复，负 = 消耗 |
| `<var>_delta` | **B4** 一次性加 value，应用后自动移除 | 点 |
| `emotion_tag` | **B4** 进入 `emotion_tags`（需字段 `tag`），`timed` 到期移除 | 无 |
| `closeness_delta` | **B4** `closeness[target] += value`（需字段 `target`），一次性 | 点 |
| `decay` | **B4** 自然衰减元 buff，每个 player 常驻（`source="decay"`），速率见 `GET /player` 字段表 | 无 |
| `hp_regen` | 兼容别名 = `fullness_regen` | 点/游戏秒 |
| `move_speed` | 移动速度倍率 | 倍数 |

Buff 可带扩展字段：`tag`（emotion_tag 用）、`target`（closeness_delta 用）。

### Object Effect

Object 的 `effects` 列表支持三种 type，适用原型不同：

| type | 适用原型 | 触发时机 | 说明 |
|------|---------|---------|------|
| `buff` | continuous | 进入时创建，离开/计时结束时移除 | 见上方 Buff 结构；mode 可为 `persistent` 或 `timed` |
| `instant_effect` | instant / continuous | 进入时一次性结算，不进 buff 列表 | `key` 为七变量之一（`fullness` / `energy` / `social` / `fun` / `mood`；`hp` 视为 `fullness`），`value` 为变化量，结果 clamp 到 0–100 |
| `tag` | continuous | 进入时加入，离开时移除 | 纯标记字符串，不参与运算 |

> instant 原型的 `effects` 中，`buff` 只允许 `timed` mode 与一次性 key（`<var>_delta` / `emotion_tag` / `closeness_delta`）；`persistent` buff 和 `tag` 被忽略（没有 leave 时机）。

**Object 类型新增字段（B5）：**

| 字段 | 说明 |
|------|------|
| `advertise` | `{ <var>: 0–100 }` 广告值，随 `GET /world` 的 objects 下发 |
| 成本项 | 每个类型至少一项负向效果（如 fridge `fullness +30, fun −2`；book `fun +8, energy −1`；bed `fun_regen −0.05`；desk `energy_regen −1, fullness_regen −1`）。所有 `hp` / `hp_regen` 键已改为 `fullness` / `fullness_regen` |

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

### POST /admin/checkpoint

立即写一份 SQLite 检查点（正常情况下后台每 5 s 自动写；此接口用于测试与手动保障）。

**响应：**
```json
{ "ok": true, "players": 1, "rooms": 0, "requests": 0, "saved_at": 1762347797.4, "path": ".../data/sandbox.db" }
```

---

### GET /admin/self-sync

自我层同步状态（联调用）。

```json
{ "enabled": true, "self_url": "http://127.0.0.1:8100", "sent": 240, "failed": 0, "seeded": 1, "resyncs": 0,
  "drift_max": 0.023, "drift_last": { "fullness": 0.001, "energy": 0.0, "social": -0.002, "fun": 0.0, "mood": 0.0 },
  "last_error": null, "last_ok_ts": 1762440180.2, "pending": { "鲸仔_a1b2c3": { "energy": 0.4 } }, "queue": 0 }
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
