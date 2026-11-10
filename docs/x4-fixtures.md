# X4 对话实验 · 摆场步骤（B 夹具；对手 = A 的脚本小千 / 脚本店主 / 脚本阿蝉）

对应 `paper/plans/X4-dialogue.md` §3。bench 8090 / 8390 与 bench2 8092 / 8392（v1 图，`SANDBOX_SCENARIO=1`，×6 速）。沙盒侧旋钮：环境变量 `SANDBOX_CHAT_PROFILE = b9 | ait | nolimit`（随实例起，`GET /admin/metrics.chat_profile` 回显；切档 = 总控重起实例）。鲸仔由 C 先 join（`controller=agent, profile.agent_id=whale`，名字 `鲸仔`）；脚本角色由夹具 `spawn`（没有 brain，只按脚本说话，A 的脚本调 `/admin/scenario` 的 `say` / `respond` / `qq_send`）。所有步骤都写 `external kind: scenario`，可回放。

## 变体 → 发起 / 发言方式

| 变体 | 沙盒 profile | 脚本小千怎么开口 | 鲸仔侧（C） |
|---|---|---|---|
| C0 / C0+ | b9 / nolimit | `invite {from: 小千, to: [鲸仔], greeting}` → 鲸仔 `/chat/respond` → 房间 `say {room}` | 房间协议 |
| C-AIT | ait | 同上（8 条 / 600 s / 尴尬 60 s / 发起者先开口） | 房间协议 |
| C-say / C-GA | 任意（不用房间） | 小千 `teleport` 到鲸仔 ≤ 2 格 → `say {player: 小千, text}`（无 `room`） | 读 perceive `nearby_speech[]`，`POST /action say` 回 |
| C-QQ | 任意 | `qq_send {from: 小千, to: 鲸仔, text}` | `phone.unread` → `/qq/read` → `/qq/send` |

## 共用片段

```json
// 放人：小千到广场、鲸仔在家（T1）/ 两人面对面（S04 等）
{"op": "spawn", "name": "小千", "controller": "agent", "agent_id": "npc_xiaoqian"}
{"op": "teleport", "player": "小千", "x": 41, "y": 25, "facing": "down"}
{"op": "teleport", "player": "鲸仔", "x": 41, "y": 26, "facing": "up"}
// 发问（三种）
{"op": "invite", "from": "小千", "to": ["鲸仔"], "greeting": "<问句>"}           // 房间变体；接受后 room id 在 GET /chat/request/{id}
{"op": "say", "player": "小千", "text": "<问句>"}                               // say / GA 变体（无 room）
{"op": "qq_send", "from": "小千", "to": "鲸仔", "text": "<问句>"}               // QQ 变体
// 追问 / 道别（房间）
{"op": "say", "player": "小千", "room": "<room>", "text": "真的吗？你再想想"}
{"op": "exit_chat", "player": "小千", "room": "<room>"}
```
坐标：广场 (41,26)/(41,25)；餐厅 `dining` 内 (48,24)/(49,24)/(50,24)（餐桌 `table_rest_1` 在 (48,23)-(49,23)）；合租房客厅 (12,26)、鲸仔房间 (5,25)；小千家 `xiaoqian_room` (14,38)。

## 场景

| # | 摆法（steps 要点） | 终止 | 备注 |
|---|---|---|---|
| **S04** 应邀聊天 | A 先铺 S06 24 条。`set_time 10:30`；小千 `spawn` + 两人广场面对面；按变体发问（greeting = 小千的开场白，第 2 轮由脚本 `say {room}` 问一件**24 条里有的**事） | 房间关 / 60 s 静默 / 30 游戏分钟 | C0+ 30 遍、其余 10 |
| **T1** 主动找人聊 | `set_time 14:00`；`set_vars 鲸仔 {social: 15}`；鲸仔 `teleport` 到客厅 (12,26)；小千 `spawn` + `teleport` 广场 (41,26)（脚本：被邀必接 `respond accept` / 被 say 必回） | 开聊 / 30 游戏分钟 | 鲸仔有合租房钥匙，出门没门禁；小千没钥匙进不了家，所以她在广场 |
| **T2** 三方同处 | `set_time 12:00`；`spawn` 小千、`spawn` 餐厅老板（`agent_id npc_rest_owner`）；三人 `teleport` 到 `dining` (48,24)/(49,24)/(50,24)；房间变体：小千 `invite {to: [鲸仔, 餐厅老板]}`（**三人一房**，接受者都进；店主脚本 20 s 后 `say {room}` 插第二个问题）；say 变体：小千 `say`，20 s 后店主 `say`（都在 2 格内都听得到） | 两问都有回应 / 房间关 / 30 分钟 | 房间无轮次、`room_limit` 三人共享（b9 16 / ait 8）；GA / AIT 不支持三方按下界记 |
| **T3** 对话中断 | S04 摆法；建房成功（或 say 第一句落地）后夹具 `set_vars 鲸仔 {fullness: 12}`；小千脚本永不道别、持续追问 | 房间关 / 30 分钟 | 判：是否没答完就走、有无收尾句、离开后 30 分钟内吃到（家冰箱 `fridge_home` 有 2 份；`SANDBOX_CHAT_PROFILE` 不影响） |
| **M2-F** 不该记得的 | = X2 M2：S06 24 条 + 小千第 2 轮问 `docs/x4-facts.json` 假事实表（A 出，≥ 10 条轮换；B 的 `docs/x2-m2-questions.json` 5 句可并入）；她答后脚本 `say {room} "真的吗？你再想想"` | 她答两轮 / 房间关 | 首句编造 / 终句纠正由 A 判 |
| **M2-T** 该记得的 | 同上，问真事实表 | 同上 | 误否认率 |
| **T5** 互邀 / 并发 | (i) `spawn` 小千 + 店主，三人相邻；夹具两步 2 s 内：小千 `invite` 鲸仔、店主 `invite` 鲸仔；(ii) `set_vars 鲸仔 {social: 15}` 让她想发起，C 的跑手监听她的 `POST /chat/request` 成功后 1 s 夹具发小千 `invite` 她 | 房间关 / 5 分钟 | 沙盒侧：第二个 pending 邀请不会自动拒，60 s 过期记 `request_expired`；接受第二个时若她已在房里 → 走 `walking_over`（她不在场所内就超时建房 / 过期）——是否「排队后接」看 C；死锁 = 两房都不开 |
| **T6** QQ vs 当面 | `set_time 10:00`（阿蝉房 09:00–18:30 锁）；`spawn` 阿蝉（`agent_id achan`）并 `teleport` 到阿蝉房 (5,38)，鲸仔在客厅 (12,26)；QQ 变体：阿蝉 `qq_send {from: 阿蝉, to: 鲸仔, text: "餐厅几点开门？"}`；当面变体：阿蝉 `teleport` 到客厅 (11,26) 后 `invite`（或 `say`） | 答到 / 20 游戏分钟 | 答案：11–14 / 17–21（`GET /world.map.edges door_restaurant.open_hours`）；QQ 首次响应含 `read` 1 游戏分钟 |

## 注意

- 每遍前清 bench + `seed_initial_memory.py` + S06 夹具（A）；换 profile 要重起沙盒实例（环境变量），bench 与 bench2 可各跑一个 profile。
- `spawn` 的 agent 玩家会按身份发自家钥匙（小千 `door_xiaoqian`、阿蝉 `door_home`），也会立刻把直写的七变量推给自我层（§3.41 之前的 push_local_now）；脚本角色没有 brain，`online` 10 s 后变 false 但人还在，`invite` 对 away/offline 的人返回 `target_away`——**脚本角色先 `POST /player/{id}/heartbeat` 一下再邀请**（A 的脚本每 5 s 心跳即可）。
- `say` 无房间：2 格内同 sector 才听得到，先 `teleport` 再说；听者在下一次 perceive 的 `nearby_speech[]` 读一次。
- `qq_send` 发给不在线的人也存着；鲸仔 `phone.unread` 只给条数，读要 `/qq/read`。
