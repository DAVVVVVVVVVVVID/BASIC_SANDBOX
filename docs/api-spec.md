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
| `mapVersion` | **W5 E③** 地图静态内容指纹（名字@sha1 前 12 位，含 tiles 类型 / 可走与物品 id / 类型 / 位置）；变了才需要重拉 `tiles` / `tiled` |
| `town` | **W7 E** 镇名（`SANDBOX_TOWN`，towns.yaml 的 key），多镇代理用 |

**顶层新增（W7 E）：** `zone_names`：`{world: {id: 名}, sector: {...}, arena: {...}}`，地图区域中文名（只读，`?fields=zone_names` 可单取）。`tiled` 的 tileset 现为 E 交付的自制 CC0 地砖 `gen/tiles.png`（`game/maps/tile_gids.json` 覆盖 gid 与 `_tileset`）。

**瘦身（W5 E③）：** `GET /world?fields=players,objects,worldState` 只回这些顶层键（可选值：`tiles` / `objects` / `worldState` / `players` / `tiled`），形状与全量相同（同一响应模型）；全量约 300 KB，`players,objects,worldState` 约 10 KB。`tiled`（**E⑤**）现在非空：`{tilesets: [Sunnyside 信息], layers: [ground, structures]}`，gid 映射为假设值，见 `scripts/gen_map.py` 的 `TILE_GIDS`（可用 `game/maps/tile_gids.json` 覆盖）。

> **只读**：`GET /world` 不推进时间、不跑 buff tick、不清理离线玩家。这些都由后端的独立后台 tick 任务（200 ms）完成，没有任何客户端轮询时状态照样演化。

| objects[] 新增字段 | 说明 |
|------|------|
| `advertise` | **B5** Sims 式广告值 `{ fullness \| energy \| social \| fun \| mood: 0–100 }`，供规划器做软偏好打分；来自 `object_types.json` 的 `advertise`，可能为空对象 |

| players[] 字段 | 说明 |
|------|------|
| `id` / `name` / `position` / `facing` / `state` | 不变 |
| `controller` | **B6** `"human"` \| `"agent"` |
| `online` | **B6** agent 10 s 无心跳为 `false`（身体仍在原地、仍参与 tick）；human 无心跳直接从列表消失 |
| `agent_id` | **W4（§3.11 A1）** 自我层 agent id（join 时 `profile.agent_id`），human 为 `null`；自我层据此做 agent↔player 映射 |
| `stateLabel` / `usingObjectId` / `tags` | **W5 E①** 与 `GET /player` 同义；前端叠加层（睡觉 / 吃饭 / 直播中）直接读，不必反查 userList |
| `pos_seq` | **W5 E⑥** 位置单调序号：每次坐标实际变化 +1（转向不变），重启后保留；客户端预测校正用它排乱序 |

---

### GET /player/{player_id}

获取玩家状态。**W5 E②：对 `controller=agent` 纯只读**（不刷心跳、不改 `online`）；对 `controller=human` 仍刷心跳（人类前端的老路径，10 s 无心跳会被清除）。两者都会读取并清空 `pendingMessage`。buff tick 由后台任务驱动，与本接口无关。

### POST /player/{player_id}/heartbeat

**W5 E②** 显式心跳（任何 controller）：刷新 `last_seen`、置 `online=true`。**agent 必须用它**（C 的 loop 每 ≤ 10 s 一次，或用 `rejoin`）才能保持 `online=true`。

**响应：** `{ "ok": true, "online": true, "last_tick_ts": "2026-11-06T21:03:00+08:00" }`；不存在 404。

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
| `state` | `idle` \| `walking` \| `requesting_talk` \| `walking_over`（**B9** 接受邀请后走向对方）\| `talking` \| `using` |
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
| `recent_events` | **W4** 最近 50 条 `POST /player/{id}/effects` 的 `{event, source, scene, n_effects, game_time}` |

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
| `source` | 可选，写进 buff 的 `source`，默认 `"effects"`。**`"self"`（自我层回推）时变化不计入 vars_delta** |
| `event` | **W4（§3.11 A2）** 可选事件名（如 `viewer_praised`），只记录不参与运算；出现在响应与 `GET /player/{id}/state` 的 `recent_events`（最近 50 条 `{event, source, scene, n_effects, game_time}`）供两边日志对账 |

**响应：** `{ "ok": true, "applied": 6, "skipped": 0, "event": "viewer_praised", "state": { ...与 GET /player/{id}/state 相同... } }`；player 不存在 404。

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
| `objectId` | **W8** `use / leave / interact` 涉及的物品 id（取自 `result.objectId`），其他动作为 `null`。A 的 episodes 用它看「用了什么」 |

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

### GET /history/chat

**W5 任务 1（数据集优先）**：聊天 append-only JSONL 回放，只读。文件 `data/chat/YYYY-MM-DD.jsonl`，与 `/ws/world` 的 `chat` 推送同一处写入。

**Query：** `since`（ISO）、`room`（room_id）、`kind`（`message` | `event`）、`limit`。

**行形状：**
```json
{ "kind": "message", "ts": "2026-11-06T21:03:01.234", "game_time": "2026-11-06T21:03:01+08:00", "room_id": "def456",
  "seq": 3, "from": "achan_1a2b3c", "from_name": "阿蝉", "to": ["鲸仔_a1b2c3"], "text": "晚饭吃什么", "controller": "human" }
{ "kind": "event", "event": "room_open | player_exit | room_limit | room_close | request_expired | request_rejected",
  "ts": "...", "game_time": "...", "room_id": "def456", "request_id": null, "participants": ["..."], "reason": "all_left" }
```
`room_close` 事件带 `reason`（`all_left` / `room_limit`）；`player_exit` 带 `entity`。

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
| `move_to_area` | 移动到目标区域内**按 BFS 实际路程**最近的可行走 tile（跨 sector 走门；W5 前取曼哈顿最近可能隔墙 → `no_path`） | `{ area_type, area_id }` | agent |
| `turn` | 仅改变朝向，不移动 | `{ direction }` | Ctrl + 方向键 |
| `interact` | 阅读正前方对象描述，不改变状态 | `{}` | `I` |
| `use` | 进入使用正前方对象，加入 userList | `{}` | `E` |
| `leave` | 退出当前正在使用的对象 | `{}` | `Q` |
| `freeform` | **B12（W5）** 自然语言动作，由自我层 `POST /self/adjudicate` 裁决后把效果落到 player | `{ text, target?, context? }` | agent |

---

### freeform（B12）

```json
{ "entityId": "鲸仔_a1b2c3", "action": { "type": "freeform", "payload": { "text": "我在广场上给路过的人唱一段鲸歌", "target": "achan_1a2b3c" } } }
```

| payload 字段 | 说明 |
|---|---|
| `text` | 必填，≤ 200 字；她想做的一件事（第一人称） |
| `target` | 可选，对方 `entity_id` 或 `object_id`，原样传给自我层；裁决返回的效果若 `target` 是在场 player 则落到对方 |
| `context` | 可选 ≤ 1000 字，附加情境 |

后端：每实体 **30 s 本地限频**（自我层另有一层）→ `POST {SELF_URL}/self/adjudicate {agent: player.agent_id（human 用 name）, text, target?, context?}`（15 s 超时）→ 返回的 `effects`（已是 `instant_effect` / `emotion_tag` buff 形式）经与 `/effects` 同一条管线落到 player（`source="freeform"`），`narration` 写进本人与 `target` 的 `pendingMessage`。**不**再把这组效果转发回自我层（由 30 s delta 上报）。

**响应：**
```json
{ "success": true, "type": "freeform", "reason": null,
  "result": { "narration": "鲸仔在广场上清了清嗓子，给路过的人唱起了一段悠长的鲸歌……",
              "effects": [ { "type": "instant_effect", "key": "fun", "value": 4.0, "target": "self" }, ... ],
              "applied": 3, "skipped": 0, "feasible": true, "injection": false } }
```

| reason | 说明 |
|---|---|
| `null` 且 `success=false` | 裁决为不可行（`result.feasible=false`），通常仍有旁白与小幅负效果 |
| `injection` | 文本试图改规则 / 索要提示词；`effects` 为空，旁白固定「她嘀咕了一句谁也没听懂的话」 |
| `rate_limited` | 本地 30 s 内重复（`result.retry_after`），或自我层 429 |
| `adjudication_unavailable` | 自我层不可达 / 超时 / persona 不存在 / `SELF_SYNC=0`（`result.error`） |
| `adjudication_failed` | 自我层模型调用失败（透传） |
| `missing_text` / `text_too_long` / `player_not_found` | 本地校验 |

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
| `feed_unavailable` | **B10** 手机（`external: feed`）拉自我层 `GET /self/feed` 失败（不可达 / 超时 3 s）。`result.message` 为「手机没信号…」，`result.phone.status = "no_signal"`；物品仍算使用过（有冷却），其余 instant 效果已结算 |
| `live_unavailable` | **B11** 直播台（`external: live`）向自我层 `POST /self/live/start` 失败，**或使用者是人类玩家（没有 `agent_id`，§3.11 B4：阿蝉不能替她开播）**。不进入物品、不计冷却，`result.error` 为错误摘要 |
| `game_unavailable` | **B18（W6）** 游戏机（`external: game`）向 D 的 brain `GET {GAME_URL}/healthz` / `POST /event` 失败（不可达 / 超时 3 s / ok=false）。不进入物品、不计冷却，`result.error` 为错误摘要 |
| `closed` | **B20（W7）** 物品不在营业时间（按游戏时间）。`result` 含 `opens_at`（下次开门 `"HH:MM"`）、`openHours`、`objectId`、`message`。不计冷却。营业中途关门时还在用的玩家被自动请出（`pendingMessage` = `leaveMessage`） |

**手机 use 成功时** `result` 多两个字段：`message` = digest 文字（「手机上有 N 条新动态：…」/「手机上没有新消息。」），`phone` = 与 `GET /agent/perceive` 的 `phone` 相同的 digest 对象。
| `use_disabled` | 当前无法使用对象（buff 限制）|

---

### leave

> **Q0（W8）：离开正在使用的物品永远放行。** `no_use` / `no_move` / 对话中的 `chat_active` 只约束「去用别的物品」与移动，不再挡 `leave`（此前 `chat_active` 会让 `leave` 返回 `use_disabled`，与钓位 / 长椅 / 浴缸的 `no_move` 组合成死锁）。失败只剩 `not_using_any_object` 与 `player_not_found`。检查点回填时若 `chat_active` 没有对应的活跃房间会被清掉。

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
- **多实例（W4）**：一机多镇时每个实例用不同端口 + 不同 `SANDBOX_DATA_DIR`（检查点 `sandbox.db`、`actions/*.jsonl`、pid 文件都在该目录内，进程间没有共享全局文件；日志走 stdout 或 `run_town.sh --log`）。`back_end/scripts/run_town.sh --port 8010 --data run/data/m2a [--self-url http://127.0.0.1:8310] [--cors ...]` 一键起一个镇，端口被占直接拒绝。CORS 白名单走环境变量 `SANDBOX_CORS_ORIGINS`（逗号分隔，默认 `http://localhost:5173,http://127.0.0.1:5173`）。**`SANDBOX_SEED`（W5 / W6）**：决定 ① player id 后缀生成器 ② **天气序列**（每 6 游戏小时一段，由 (seed, 游戏日, 段) 确定，sunny:cloudy:rain = 6:3:1，假设；未设置恒 `sunny`）③ **agent 出生点**（`controller=agent` 出生在其家 arena 内由 (seed, agent_id) 选的可走格；未设置取该 arena 第一个可走格；家表 `AGENT_HOME_ARENA`：whale→storage、achan→achan_room、npc_cook→cook_bedroom、npc_grocer→grocer_bedroom、npc_fisher→fisher_hut、npc_regular→regular_bedroom、npc_teacher→teacher_room、npc_painter→painter_room、npc_herbalist→herbalist_room；不在表里 → 地图出生点）。human 始终在地图出生点。`GET /admin/metrics.seed` 可查。**`SANDBOX_MAP_DIR`（W6）**：地图目录，默认 `game/maps`；`game/maps/m1c` 是「NPC 8 个」版本（60×48，+教书先生家 / 画师家 / 药铺，42 个物品，`scripts/gen_map.py --variant m1c`）。**`SANDBOX_TOWN`**：数据集每行的 `town`（towns.yaml 的 key，默认 `main`）。`run_town.sh` 的 `--tz / --seed / --env K=V` 与总控 townctl 传的 `SANDBOX_TZ` / `sandbox_env` 一一对应。
- 实时推送见 §8 `GET /ws/world`。

### 与自我层同步（§2.5）

| 项 | 说明 |
|---|---|
| 对象 | 只同步 `controller=agent` 的 player，自我层 agent id = `player.agent_id` |
| 种入 | join 与重启回填后 `GET {SELF_URL}/self/state?agent=…`，用返回的 `vars / closeness / emotion_tags / ocean / scene` 覆盖本地 |
| 上报 | 每 **30 游戏秒** `POST {SELF_URL}/self/state/delta`：`{"agent","scene","ts":<游戏时刻 ISO>,"vars_delta":{…},"source":"sandbox_tick"}`。**`vars_delta` 只含非衰减变化**（物品 buff、instant_effect、/effects 推送，取 clamp 后的实际变化量）；自然衰减两边各自按同一张速率表计算，自我层在收到 delta 前会先把自己的状态 catch_up 到 `ts`，所以不能把衰减再报一遍 |
| 失败 | 自我层不可达时本地照常 tick，失败批的 `vars_delta` 合回待发池，指数退避（≤ 30 s）后与后续变化一起重发 |
| 对账 | 自我层返回的 `vars` 与发批瞬间的本地快照之差记为 drift；`max|drift| > 0.5` 时把差值加回本地（以自我层为准，`SELF_SYNC_SNAP=0` 关闭只记录） |
| 事件单向链路 | §3.9 第 4 条：直播服务只给自我层 `POST /self/state/event`；自我层应用后回推沙盒 `POST /player/{id}/effects` 并带 `source: "self"`。沙盒对 `source == "self"` 的变化 **`track=False`**：落本地、不进 `vars_delta`；沙盒永不转发事件到自我层 |
| speed > 1 | 自我层 `GET /self/state` 按其墙钟 catch_up，而沙盒上报的 `ts` 是游戏时刻；加速调试时读到的值滞后 ≤ 30 游戏秒。生产 speed = 1 无影响 |
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
- `arena_tree`（**W5 §3.14 改为整个 world 的树**）：`{id, name, current, sectors: [{id, name, current, arenas: [{id, name, current, objects: [...]}]}], sector: <当前 sector 节点>}`，列出**所有** sector → arenas → objects，**不含坐标**；`current: true` 同时标在所在 sector 与所在 arena 上（恰好各一个）；旧字段 `sector`（当前 sector 节点）保留。objects 元素：`{id, name, type, interactable, currentUsers, maxUsers?, advertise?}`。室外也能看到每个室内物品（如 `bed_whale`），配合 `move_to_area` 跨 sector 走门过去；当 cognitive_map 中找不到对应名称时，`name` 回退为原始 ID
- `current`（**W5**）：`{world, sector, arena, sector_name, arena_name}`，站在 arena 外时 `arena` 为 `null`
- `vision_tiles`：以实体当前位置为中心，边长 `vision_size`（偶数自动取奇）的正方形内所有合法 tile，超出地图边界的 tile 不返回
- `front_object`：正前方一格的 object 信息，无 object 时为 `null`
- `players_in_view`（**B13**）：视野正方形内的其他 player
- `game`（**B18，W6**）：游戏机局内状态 `{status: "playing" | "ended", started_at, ended_at?, brain_run_id, run_id, ticks, day, phase, health, hunger, sanity, deaths}`，没玩过为 `null`；`playing` 时每次 perceive 向 brain `GET /metrics` 刷新一次（3 s 超时，失败保留旧值）。`GET /player/{id}` 与 `/state` 也带 `game`
- `phone`（**B10**）：最近一次刷手机的信息流摘要，没刷过为 `null`：`{"status": "ok" | "no_signal", "items": [{"ts", "topic", "sentiment", "is_question", "is_song_request", "summary", "injection"}], "digest_ts", "fetched_at", "for"}`。只有自我层 Quarantine 后的 digest 字段，**不含 id / source / author / 原文**（沙盒侧再做一次白名单过滤）
- `needs`（**B13**）：**只给分档文字，不给数值**（报告 §4.3）。阈值 low 25 / critical 15 / emergency 10；文案与自我层 `state.py` 的 `LABELS` 同源（沿用 mood.py `label()`）。`<var>` 未越阈值为 `"还好"`；`mood` < 35 为「有点委屈…」、> 75 为「开心」；`lines` 是越过阈值的全部文字（含 emotion_tags），`hard` 是 `<var><15` 的硬约束；`closeness` 对视野内 player 分档，形状固定为 **`{entity_id: {"name", "tier"}}`**（§3.11 第 9 条；tier ≥70 很亲近 / ≥40 熟悉 / ≥15 认识 / 其余 陌生，阈值为假设，整个 `needs` 块里没有任何数值）；`recent_uses` 同 `GET /player/{id}/state`

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
| `external` | instant / continuous | use 时调自我层 | **B10 / B11** `key = "feed"`：`GET {SELF_URL}/self/feed?for=<agent_id>&n=8`，结果进 `result.phone` 与 perceive 的 `phone`；`key = "live"`：use → `POST /self/live/start`（失败则 use 失败 `live_unavailable`），leave → `POST /self/live/stop`（后台发送、不可失败），使用期间 `player.scene = "live"`。没有 `agent_id` 的人类玩家：feed 用 player id 查；**live 直接 `live_unavailable`**（§3.11 B4）。**`key = "game"`（B18，W6，契约为假设——D12 未出）**：use → `GET {GAME_URL}/healthz` 须 ok，再 `POST {GAME_URL}/event {type:"sandbox_session_start", agent, player_id, ts, tick}`；成功后 `player.game = {status:"playing", started_at, brain_run_id, run_id, ticks, day, phase, health, hunger, sanity, deaths}`（后几项取自 brain `GET /metrics`，perceive 时刷新）；leave / 自动离开 / 删玩家 → `POST /event {type:"sandbox_session_end", agent, player_id, ts, started_at}`（后台、不可失败），`player.game.status = "ended"`。局的结果由 D 自己 `POST /self/game/session` 写自我层，沙盒不转发。`GAME_URL` 默认 `http://127.0.0.1:8110`。human 也能玩（agent 名用 player name） |

> instant 原型的 `effects` 中，`buff` 只允许 `timed` mode 与一次性 key（`<var>_delta` / `emotion_tag` / `closeness_delta`）；`persistent` buff 和 `tag` 被忽略（没有 leave 时机）。

**Object 类型新增字段（B5）：**

| 字段 | 说明 |
|------|------|
| `advertise` | `{ <var>: 0–100 }` 广告值，随 `GET /world` 的 objects 下发 |
| 成本项 | 每个类型至少一项负向效果。所有 `hp` / `hp_regen` 键已改为 `fullness` / `fullness_regen` |

**数值尺度（W3，§3.9 第 6 条）：** 全部物品改为**每游戏小时尺度**。`*_regen` 的 `value` 单位仍是点 / 游戏秒（tick 乘 `delta/1000`），JSON 里写的是 `X/3600`。规则：一次正常使用的恢复量 ≈ 该变量一日衰减量（fullness 288、energy 192+夜间、social 144、fun 240），具体数值为假设：

| 类型 | 原型 | 收益 / 成本（每游戏小时或每次） | advertise | max_duration |
|---|---|---|---|---|
| `bed` / `bed_21` | continuous | energy +25 / +20 每小时（睡 8 h ≈ +200）；fun −1/h | energy 80 / 70 | 8 h |
| `bath` | continuous | fun +20/h、energy +10/h、mood +6/h；fullness −2/h | fun 25、energy 30、mood 10 | 30 min |
| `fridge` | instant | fullness +40（≈ 日衰减 / 3 餐）、energy +5；fun −2 | fullness 60、fun 5 | — |
| `desk` / `desk_12` | continuous | mood +3/h；fun −3/h、energy −4/h | fun 5、mood 15（desk_12 另 social 5） | 1 h |
| `book` | instant | fun +60（≈ 日衰减 / 4 次）；energy −2 | fun 40 | — |
| `phone` | instant | `external: feed`；fun +15、social +5；energy −2 | fun 10、social 3 | — |
| `stream_desk` | continuous | `external: live`；social +20/h、fun +8/h；energy −6/h、fullness −3/h；`no_move`、tag `streaming` | social 70、fun 40 | 3 h（假设） |
| `restaurant_table` | continuous，**`max_users` 4** | **W4 B16 续** fullness +40/h、social +16/h、fun +4/h；energy −2/h；tag `dining` | fullness 55、social 45、fun 10 | 45 min |
| `bench` | continuous，**`max_users` 2** | **W4** energy +6/h、fun +6/h、social +6/h；fullness −1/h；tag `resting` | fun 20、social 25、energy 15 | 1 h |
| `fishing_spot` | continuous，`max_users` 1 | **W4** fun +18/h、mood +4/h；energy −3/h、fullness −2/h；tag `fishing` | fun 35、mood 15 | 2 h |
| `shop_counter` | instant | **W4** fullness +15、social +6；energy −1 | fullness 25、social 15 | — |
| `game_console` | continuous，`max_users` 1 | **B18（W6）** `external: game`；fun +30/h、mood +4/h；energy −6/h、social −2/h；`no_move`、tag `gaming`；`stateLabel`「{entity} 玩游戏中」 | fun 85、mood 20 | 2 h（假设） |

所有 continuous 类型都带 `max_users`（`GET /world` 的 `maxUsers`）；社交物品靠多人同用产生「在同一处」的 `players_in_view`。

**营业时间（B20，W7）：** `object_types.json` 的 `open_hours: [["HH:MM","HH:MM"], ...]`（游戏时间，Asia/Shanghai）。餐馆桌子 `11:00–14:00 / 17:00–21:00`，杂货店柜台 `09:00–20:00`，码头钓位 `06:00–20:00`（「日出后」，假设）；其他物品全天。`GET /world` 与 perceive 的每个物品带 `open`（bool）、`opensAt`（关门时 `"HH:MM"`，开门时 `null`）、`openHours`；**关门时 `advertise` 全部为 0**（`GET /world`、perceive 一致，让规划器的软偏好自然变成「等开门」）。`/ws/world` 的 `objects` 推送带 `open`。地图上：餐馆（sector `restaurant`：`dining` 两张四人桌 + `rest_kitchen` fridge）、广场两条长椅、码头两个钓位、杂货店柜台（替代原 desk），四个 NPC 家各有 fridge；共 30 个物品，全部从出生点 BFS 可达。

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

### GET /admin/metrics

**W4** 运行指标（负载测试用）：最近 600 次 tick 的耗时 / 间隔分位、玩家数、WebSocket 订阅数、进程 RSS。

```json
{ "tick_count": 9000, "interval_target_ms": 200.0,
  "tick_duration_ms": { "p50": 0.1, "p95": 0.2, "max": 14.7 },
  "tick_gap_ms": { "p50": 200.4, "p95": 201.3, "max": 214.6 },
  "running": true, "players": 6, "ws_clients": 1, "rss_mb": 68.2 }
```

---

### GET /admin/export

**W6 任务 1（数据集 schema v0.2 的沙盒源）**：一次性给出当日 actions / chat / state 与 manifest，供总控 `dataset_export.py` 拉。只读。

**Query：** `date=YYYY-MM-DD`（必填，400 校验）、`kinds=actions,chat,state`（默认全部）。

```json
{ "schema": "sandbox-0.1", "date": "2026-11-06", "town": "main", "map_version": "阿蝉家与小镇@1b824832ace2", "seed": null,
  "generated_at": "2026-11-06T10:15:12+08:00",
  "actions": [ { ...GET /history/log 的行... , "town": "main", "map_version": "...", "seed": null } ],
  "chat":    [ { ...GET /history/chat 的行... } ],
  "state":   [ { "kind": "sample", "ts": "...", "game_time": "...", "town": "main", "map_version": "...", "seed": null,
                 "player_id": "鲸仔_a1b2c3", "agent_id": "whale", "controller": "agent", "scene": "sandbox",
                 "vars": { "fullness": 62.0, "energy": 71.5, "social": 48.0, "fun": 35.0, "mood": 68.0 },
                 "emotion_tags": ["smug"], "closeness": { "achan": 72.0 }, "online": true, "position": {"x": 6, "y": 9}, "using": null } ],
  "manifest": { "counts": { "actions": 327, "chat": 0, "state": 0 },
                "files": { "actions": { "path": ".../data/actions/2026-11-06.jsonl", "exists": true, "bytes": 123456 }, ... },
                "backfilled_rows": 327 } }
```

| 项 | 说明 |
|---|---|
| 行来源 | `data/actions/<date>.jsonl`、`data/chat/<date>.jsonl`、`data/state/<date>.jsonl`，行序即文件序；`manifest.counts` 与文件行数一致 |
| 每行新增字段 | **W6** `town`（环境变量 `SANDBOX_TOWN`，默认 `main`）、`map_version`、`seed`。W6 之前写的旧行没有这三项，导出时按当前配置回填并加 `"backfilled": true`，`manifest.backfilled_rows` 计数 |
| `state` | **W6** 每个 player 每 30 游戏秒一行（与自我层 delta 同节拍），由后台 ticker 写 `data/state/<date>.jsonl`，`kind: "sample"`；**W8 Q1**：join / rejoin / 检查点回填时立即各写一行（`kind: "join" | "rejoin" | "restore"`，并把 30 s 节拍对齐到此刻），每行带 `mood_base` |
| `external` | **W7 B19** `data/external/<date>.jsonl`：外部效果与不确定性输入——`self_seed`（种入的七变量）、`self_snap`（纠偏差值）、`effects_push`（`/effects` 完整载荷）、`adjudication`（freeform 裁决结果）、`feed` / `live` / `game`（外部调用结果）、`nondeterministic`（`time_speed / time_toggle / time_reset`）、**`scenario`（W8：验收夹具的每一步）**。每行带 `ts / game_time / town / map_version / seed / entity`。`kinds` 默认含它 |

**可复现回放（B19）：** `cd back_end && uv run python scripts/replay.py --date 2026-11-06 --town main --data-dir run/data/sandbox`：从每个 player 当日第一条 state 行起步，按游戏时间把 actions 与 external 合成时间线，事件之间以 1 游戏秒步进跑同一套 tick（外部调用按日志打桩，不打网络），末态与 state 最后一行逐变量作差（阈值 0.5），并列出窗口内的 nondeterministic 输入与「重放结果与日志 success 不一致」的动作。同一游戏秒内的事件按真实毫秒时间戳（`ts` / `timestamp`）排序，配合 join / rejoin 的立即采样，同秒动作无歧义（W8 Q1）；窗口内后续的 join / rejoin / restore 行作为**同步点**（重启回填 / 续接那一刻的 vars、位置、朝向、正在用的物品）；聊天 JSONL 的 `room_open / player_exit / room_close / room_limit` 事件是第四个输入（对话期间 `chat_active` 让 move / use / leave 失败，决定物品使用时长）；state 行自 W8 起带 `facing`。`--start-kind rejoin` 可从某类起点行回放。注意：用 `place()` 之类不进日志的改动无法回放；回放只覆盖有 state 行的时间窗。
| 对账脚本 | `cd back_end && uv run python scripts/dataset_fetch.py --base http://127.0.0.1:8000 --date 2026-11-06 --data-dir run/data/sandbox` 写出 `<out>/<town>/<date>/{actions,chat,state}.jsonl + manifest.json` 并校验 写出行数 == manifest == 本地文件行数 |

---

### POST /admin/scenario

**W8 Q0b 行为验收夹具**（`docs/behavior-acceptance.md`「分工 B」）：一次把世界摆成指定状态。**只在 `SANDBOX_SCENARIO=1` 的实例开放**（运行台主镇不开，townctl 的 `bench` 镇开；`run_town.sh --scenario`），否则 403。

```json
{ "label": "S01", "steps": [
    { "op": "reset" },
    { "op": "set_time", "time": "11:30", "date": "2026-11-10" },
    { "op": "spawn", "name": "鲸仔", "agent_id": "whale", "x": 35, "y": 25, "facing": "up", "vars": { "fullness": 15 } } ] }
```

按序执行，遇错即停；响应 `{ ok, label, steps: [{op, ok, detail}], world: {time, players[]} }`，失败时 `ok=false`、`error="step i (op): …"`、`steps` 为已完成的步。`player` / `from` / `to[]` 可填 id 或**唯一的** name。

| op | 参数 | 作用 |
|---|---|---|
| `reset` | `running?` | 清空所有玩家 / 对话 / 物品占用 / 冷却 / 待发同步；时间回真实当前 |
| `set_time` | `time:"HH:MM[:SS]"`, `date?`, `speed?`, `running?` | 游戏时间拨到该时刻（锚点重设，之后照常走）；天气按 seed 重算 |
| `spawn` | `name`, `agent_id?`, `controller?="agent"`, `x?`, `y?`, `facing?`, `vars?`, `profile?` | 放一个玩家（agent 会照常从自我层种入，之后再按 `vars` 直写）；不传坐标落出生点 / 家 |
| `remove` | `player` | 删玩家（自动退出物品与对话） |
| `teleport` | `player`, `x`, `y`, `facing?` | 必须可走格；正在用物品先离开；`pos_seq` +1 |
| `set_vars` | `player`, `vars{…}`, `mood_base?`, `scene?`, `closeness?` | 七变量直写（clamp，`hp` 视为 fullness），**不进自我层 vars_delta** |
| `effects` | `player`, `effects[]`, `scene?`, `event?` | 同 `POST /player/{id}/effects`，`source="scenario"` |
| `occupy` | `player`, `object`, `sticky?` | 让玩家占住 continuous 物品：跳过距离 / 冷却 / 营业时间 / 外部调用（直播台只本地切 live）；站到相邻可走格并面向它；`sticky=true` 关掉 max_duration 自动离开（S05「占着不走」）。满员 → 错 |
| `release` | `player` | 离开正在用的物品 |
| `invite` | `from`, `to[]`, `greeting` | 代某玩家发邀请，**跳过冷却**，返回 `request_id` |
| `respond` | `player`, `request_id`, `accept`, `message`, `tick?=true` | 代某玩家响应；默认立刻推进一次状态机（相邻则建房），返回 `status_now` / `chat_room_id` |
| `say` | `player`, `room`, `text` | 代某玩家发言 |
| `exit_chat` | `player`, `room` | 代某玩家退出房间 |
| `clear_cooldowns` | `player?` | 清物品冷却 / 使用计数与对话冷却 |

**可见性：** 每步写一条 `external` 日志（`kind: "scenario"`，含 label / step / op / args / result），`spawn / teleport / set_vars / effects / occupy / release` 另给受影响玩家立即写一行 state（`kind: "scenario"`）。回放把 scenario 行当外部输入重现。

---

### GET /admin/self-sync

自我层同步状态（联调用）。

```json
{ "enabled": true, "self_url": "http://127.0.0.1:8100", "sent": 240, "failed": 0, "seeded": 1, "resyncs": 0,
  "drift_max": 0.023, "drift_last": { "fullness": 0.001, "energy": 0.0, "social": -0.002, "fun": 0.0, "mood": 0.0 },
  "last_error": null, "last_ok_ts": 1762440180.2, "pending": { "鲸仔_a1b2c3": { "energy": 0.4 } }, "queue": 0 }
```

---

## 8. WebSocket 推送（B17，W4）

### GET /ws/world

只读 WebSocket。连接后先发全量，之后 **≤ 10 Hz** 推送变化；字段与 `GET /world` 同名、同形状（经同一个响应模型序列化）。客户端发来的任何消息都被忽略，不接受写操作；写仍走 `POST /action`。

**连接时（全量）：**
```json
{ "type": "snapshot", "ts": "2026-11-06T21:03:00+08:00",
  "tiles": [...], "objects": [...], "worldState": {...}, "players": [...], "tiled": null }
```

**之后（增量，只带变化的部分，每项可选）：**
```json
{ "type": "patch", "ts": "2026-11-06T21:03:00+08:00",
  "worldState": { "time": "21:03:00", "period": "dusk" },
  "players": { "upsert": [ { "id": "鲸仔_a1b2c3", "name": "鲸仔", "position": {"x": 6, "y": 9}, "facing": "down",
                             "state": "walking_over", "controller": "agent", "online": true, "agent_id": "whale" } ],
               "remove": [ "human_9f8e7d" ] },
  "objects": [ { "id": "bed_whale", "currentUsers": 1, "userList": ["鲸仔_a1b2c3"] } ],
  "chat": [ { "chat_room_id": "def456", "participants": ["鲸仔_a1b2c3", "achan_1a2b3c"], "kind": "message", "seq": 3,
              "from_entity_id": "achan_1a2b3c", "from_name": "阿蝉", "content": "晚饭吃什么", "timestamp": "..." },
            { "chat_room_id": "def456", "participants": [...], "kind": "event", "seq": 4, "type": "player_exit",
              "from_entity_id": "achan_1a2b3c", "timestamp": "..." } ] }
```

| 字段 | 说明 |
|---|---|
| `worldState` | 只含变化的键（`time` 每秒变、`period` / `date` / `running` / `speed` / `weather` 偶尔变） |
| `players.upsert` | 变化了的 player，元素与 `GET /world` 的 `players[]` 同形状（含 `controller` / `online` / `agent_id`）；新 join 的也在这里 |
| `players.remove` | 消失的 player id（leave / 心跳超时） |
| `objects` | `currentUsers` / `userList` 变化了的物品；静态字段（位置、effects、advertise）看 snapshot |
| `chat` | 连接之后新产生的聊天消息（`kind: "message"`）与房间事件（`kind: "event"`：`player_exit` / `room_limit`），按 `seq` 升序，给前端气泡用。连接前的历史不重放，要历史走 `GET /chat/room/{id}` |

**动作事件（W5 E⑦）：** 每次 `POST /action` 分派后推一条，先于同一帧的 patch：
```json
{ "type": "action", "ts": "...", "entity": "鲸仔_a1b2c3", "action": "use", "object": "fridge_kitchen", "success": true, "reason": null }
```
`object` 为该动作涉及的物品 id（use / leave / interact），其他动作为 `null`，**W7 另带 `object_type`**（如 `fridge`）；move 成功时另带 `position`。前端可据此播一次性动画。

`chat` 事件的 `kind: "message"` 带 `from_name`（E④，已实现）。

空闲 5 s 没有变化时发 `{"type": "heartbeat", "ts": ...}`。多个客户端共享同一份 diff 计算；没有订阅者时不计算。
对账：`cd back_end && uv run python scripts/verify_ws.py --seconds 60`（订阅并叠加 patch，与每秒轮询 `GET /world` 比较，W4 实测 44 次比较 0 不一致）。

---

## 7. 对话系统（Chat）

对话系统支持两个 Player 之间（或多人）进行即时文字对话。

### 状态机（B9，按 AI Town 常量：邀请 60 s、walking_over 30 s、本人冷却 60 s、配对冷却 15 s、房间 16 条）

```
POST /chat/request ──(cooldown?)──▶ {success:false, reason:"chat_cooldown"}
        │
        ▼
     pending ──60 s 无人接受──▶ expired
        │ 单人：接受 / 多人：全部响应或 60 s 超时且 ≥1 人接受
        ▼
  walking_over  ── 请求带 target_arena_id（= 发起者所在 arena）；参与者 player.state = "walking_over"，可移动
        │ 全员在 target_arena 内且与发起者曼哈顿距离 ≤ 1（假设） ── 或 30 s 超时直接建房
        ▼
     active（chat_room_id 有值；参与者挂 chat_active，state = "talking"）
        │ 任一方 POST /chat/exit → 本人 60 s 冷却、与房内每人 15 s 配对冷却；房间空了 → closed
        │ 消息数达 16 → events 写 {type: "room_limit"}，房间 closed，所有人解 buff 并进冷却
        ▼
     closed
```

拒绝（`accept: false`）：单人邀请直接 `rejected`；多人邀请全部拒绝为 `rejected`。walking_over 期间参与者被删除 / 离线，不足两人 → `expired`。后台 ticker 每 200 ms 推进一次状态机，`GET /chat/request/{id}` 与 `GET /chat/pending` 前也会推进。

### 新增状态

**ChatRequest（对话邀请）**
```json
{
  "request_id": "abc123",
  "from_entity_id": "player_01",
  "to_entity_ids": ["player_02"],
  "greeting": "你好，有时间聊聊吗？",
  "status": "pending | walking_over | active | rejected | expired",
  "accepted_ids": [],
  "rejected_ids": [],
  "chat_room_id": null,
  "target_arena_id": "storage",
  "participants": ["player_01", "player_02"]
}
```

| 字段 | 说明 |
|---|---|
| `target_arena_id` | **B9**（§3.9 C3 定名）walking_over 阶段的汇合 arena = 发起者接受时所在 arena；发起者在 arena 外为 `null`（此时只看距离） |
| `participants` | walking_over / active 阶段的参与者列表 |

**ChatRoom（聊天室）**
```json
{
  "chat_room_id": "def456",
  "participants": ["player_01", "player_02"],
  "messages": [
    { "seq": 1, "from_entity_id": "player_01", "content": "你好", "timestamp": "..." }
  ],
  "events": [
    { "seq": 2, "type": "player_exit", "entity_id": "player_02", "timestamp": "..." },
    { "seq": 17, "type": "room_limit", "entity_id": null, "timestamp": "..." }
  ],
  "status": "active | closed"
}
```

事件 `type`：`player_exit`（某人退出）、`room_limit`（**B9** 消息达 16 条自动关闭）。

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
{ "request_id": "abc123", "success": true }
```

**冷却中（B9 ③）：** 发起方或任一受邀方在退出对话后 60 s 内，或这对人在 15 s 内刚聊过（**W6 任务 4：发起方是 `controller=human` 时不检查冷却**——作者 / 阿蝉随时可以找她说话；agent 发起仍受约束）：
```json
{ "request_id": null, "success": false, "reason": "chat_cooldown", "cooldown_remaining": 42.5 }
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

**响应（接受 → walking_over，B9 ①）：**
```json
{
  "chat_room_id": null,
  "status": "walking_over",
  "target_arena_id": "storage",
  "participants": ["player_01", "player_02"]
}
```

**响应（多人邀请，等待其他人）：**
```json
{ "chat_room_id": null, "status": "waiting" }
```

**响应（拒绝，或请求已不是 pending）：**
```json
{ "chat_room_id": null, "status": "rejected" }
```

聊天室创建时机（旧版的 `room_created` 不再出现）：
- 接受后进入 `walking_over`，双方走向 `target_arena_id`；全员到达且与发起者相邻（曼哈顿 ≤ 1）或 30 s 超时 → 建房
- 发起方 / 接受方轮询 `GET /chat/request/{id}`，`status == "active"` 时拿 `chat_room_id`
- 多人邀请：所有人响应后（或超时 60 秒后），接受者与发起者一起进入 walking_over

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
{ "seq": 3, "room_closed": false }
```

**第 16 条消息（B9 ④）：** 房间立即关闭，所有参与者解除 `chat_active` 并进入冷却：
```json
{ "seq": 16, "room_closed": true, "reason": "room_limit" }
```
之后再发言返回 404。

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
