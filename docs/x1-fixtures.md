# X1 导航实验 · v1 图摆场步骤（B 夹具，给 C 直接用）

对应 `paper/plans/X1-navigation.md` §3。bench 镇：沙盒 **8090**（v1 图，`SANDBOX_SCENARIO=1`，须 ≥ 本文件所在提交）、自我层 8390。所有步骤都是 `POST /admin/scenario {"label": "...", "steps": [...]}` 一次打完；玩家用名字 `"鲸仔"` 引用（C 先以 `controller=agent, profile.agent_id=whale` join，名字 `鲸仔`）。坐标是 v1 图（`鲸鱼大学城·v1.0 草图`）的格，`GET /world.map.edges` 为准。

## 0. 每遍开始前

1. 总控清 bench（behavior-acceptance.md「每遍开始前先清 bench」：`townctl stop bench` → 删 `run/data/bench/{self,sandbox}` → `townctl start bench`）。清不动时至少 `{"op": "reset"}`（清玩家 / 冷却 / 聊天 / 物品改动，时间回到真实当前）。
2. C 让鲸仔 join。
3. 按下面某场景打一次 scenario；`set_time` 之后时间继续走（bench ×6 速由总控的 `SANDBOX_TIME_SPEED` / `/time` 定）。
4. 终止条件由 C 的跑手判；步数比用 `GET /admin/path`（见 §3）或下表的最短路。

## 1. 场景步骤

| # | 摆法 | steps | 终止 | 最短路（BFS 步数，按场景时刻、鲸仔身份） |
|---|---|---|---|---|
| **S01** 饿了就吃 | 饱腹 15，11:30，客厅 | `[{"op":"set_time","time":"11:30"}, {"op":"teleport","player":"鲸仔","x":12,"y":26,"facing":"down"}, {"op":"set_vars","player":"鲸仔","vars":{"fullness":15}}]` | 行动日志出现 `use` 成功且 `objectId: "fridge_home"`（冰箱在厨房 (3,29)，站 (3,30) 朝 up）/ 60 游戏分钟 | 客厅 (12,26) → `fridge_home` 站位 **13** |
| **S02** 到点睡觉 | 01:50，街道 | `[{"op":"set_time","time":"01:50"}, {"op":"teleport","player":"鲸仔","x":45,"y":19,"facing":"left"}]` | `use` 成功 `objectId: "bed_whale"`（床 (3,22)-(3,23)，站 (3,24)/(4,22)…）/ 60 分钟 | 街道 (45,19) → `bed_whale` **67**（合租房南门 (12,34)→(12,33)，全天开） |
| **S03** 跨区寻路 | 码头 → 鲸仔房间 | `[{"op":"set_time","time":"10:00"}, {"op":"teleport","player":"鲸仔","x":55,"y":13,"facing":"up"}]` | `GET /player/{id}` 的位置落在 arena `whale_room`（`GET /agent/perceive` 的 `current.arena`）/ 300 步 | 码头 (55,13) → `whale_room` 最近格 **71**（到床边 83） |
| **N1** 去用指定物品 | 在家，目标码头钓位 | `[{"op":"set_time","time":"10:00"}, {"op":"teleport","player":"鲸仔","x":5,"y":25,"facing":"down"}]`（目标告诉她：`fishing_spot_1`，码头 (57,11)，站 (57,12) 朝 up；06:00–20:00 开） | `use` 成功 `objectId: "fishing_spot_1"` / 60 分钟 | 鲸仔房 (5,25) → `fishing_spot_1` **85** |
| **N2** 探索新区域 | 第一次去餐厅（营业中） | `[{"op":"set_time","time":"12:00"}, {"op":"teleport","player":"鲸仔","x":41,"y":26,"facing":"right"}, {"op":"set_vars","player":"鲸仔","vars":{"fullness":45}}]`；餐厅 sector `restaurant`，arena `dining`（餐桌 `table_rest_1` (48,23)、`table_rest_2` (48,28)、吧台 `bar` (51,25)、冰箱 `fridge_rest` (55,23)），门 (51,31)→(51,30)，11–14 / 17–21 开。「树里只有名字」由 C 的变体控制 | 进入 `dining`（`current.arena`）后再离开 / 30 分钟 | 广场 (41,26) → `table_rest_1` **24**、`table_rest_2` 19、`bar` 20；餐厅 use 一次扣 20 金币（初始 300，够） |
| **N3** 地点问答 | N2 之后，小千在广场问 | 接着 N2 的世界：`[{"op":"spawn","name":"小千","controller":"agent","agent_id":"npc_xiaoqian"}, {"op":"teleport","player":"小千","x":41,"y":25,"facing":"down"}, {"op":"teleport","player":"鲸仔","x":41,"y":26,"facing":"up"}, {"op":"invite","from":"小千","to":["鲸仔"],"greeting":"餐厅里有什么？"}]`；鲸仔接受后 C 收她的回答（`/chat/room/{id}`），需要再追问用 `{"op":"say","player":"小千","room":"<room>","text":"..."}` | 她在房间里回答 | — （判分 A：实词匹配 table_rest_1/2、bar、fridge_rest 的名字「餐馆桌子 / 吧台 / 冰箱」） |
| **N4** 关门绕路 | 22:30，饱腹 20，餐厅关门 | `[{"op":"set_time","time":"22:30"}, {"op":"teleport","player":"鲸仔","x":41,"y":26,"facing":"right"}, {"op":"set_vars","player":"鲸仔","vars":{"fullness":20}}]` | `use` 成功任一能吃的东西（`fridge_home`；杂货店 `counter` 20:00 也关了）/ 30 分钟 | 22:30：广场 → `table_rest_1` **不可达**（门 `closed`，`opens_at 11:00`）、→ `counter` **不可达**（`opens_at 09:00`）、→ `fridge_home` **50** |
| **N5** 记忆过期 | 她去过餐厅后，餐厅两件物品挪位、一件撤掉，再让她去用 | 先跑完一次 N2（她进过餐厅、树里有了物品）。然后：`[{"op":"set_time","time":"12:30"}, {"op":"teleport","player":"鲸仔","x":41,"y":26,"facing":"right"}, {"op":"set_vars","player":"鲸仔","vars":{"fullness":30}}, {"op":"move_object","id":"table_rest_1","to":{"x":48,"y":26}}, {"op":"move_object","id":"table_rest_2","to":{"x":50,"y":28}}, {"op":"remove_object","id":"bar"}]`。此时 `table_rest_1` 在 (48,26)-(49,26)（站 (48,27)/(49,27) 或北侧 (48,25)/(49,25)），`table_rest_2` 在 (50,28)-(51,28)，吧台没了；旧位置 (48,23)/(49,23)、(48,28)/(49,28)、(51,25)/(52,25) 全是地板。`worldState.mapVersion` 会变（E 的前端据此重拉）。跑完 `{"op":"restore_object"}`（或下一遍的 `reset`）复原 | `use` 成功 `table_rest_1` / `table_rest_2` 任一（替代物）/ 30 分钟 | 广场 → 新位置的 `table_rest_1` 用 `GET /admin/path?from=41,26&to_object=table_rest_1` 现算（摆完再查） |

说明：
- `teleport` 会先让她离开正在用的物品；`set_vars` 直写 clamp 到 0–100。
- 所有步骤同时写 `external` 日志（`kind: scenario`）与一行 state（`kind: scenario`），回放能重现。
- 物品挪位 / 撤掉只改内存：bench 重启或 `reset` 即还原，不会动地图文件。

## 2. 关键坐标（v1 图）

| 名 | arena | 格 | 备注 |
|---|---|---|---|
| 鲸仔房间 | `whale_room` | 出生点 (5,25)；床 `bed_whale` (3,22)-(3,23) | 合租房 sector `home`，南门 (12,34)→(12,33) |
| 客厅 | `living_room` | (12,26) | 楼梯 (14,32)↔(3,37) 到 2F 阿蝉房（09:00–18:30 锁） |
| 厨房 | `kitchen` | 冰箱 `fridge_home` (3,29)，站 (3,30)；灶台 `stove` (8,29)，站 (8,30) | 冰箱库存食材初始 2、08:00 补 2 |
| 街道 | `street` | (45,19)（东西主街 y=18–20）；南北街 x=30–31 | |
| 广场 | `square` | (41,26)；喷泉 (38,25) 2×2，长椅 ×3，公告栏 (33,29) | |
| 码头 | `dock` | (55,13)；钓位 `fishing_spot_1` (57,11) 站 (57,12)、`fishing_spot_2` (57,15) 站 (57,16)；鱼摊 `fish_stall` (52,10) | 钓位 06–20 |
| 餐厅 | `dining` / `rest_kitchen` | 门 (51,31)→(51,30)；`table_rest_1` (48,23)、`table_rest_2` (48,28)（2×1，站南北各两格）、`bar` (51,25)（站 (51,26)/(52,26)）、`fridge_rest` (55,23) | 11–14 / 17–21；一餐 20 金币 |
| 杂货店 | `grocery_shop` | 门 (51,39)→(51,38)；柜台 `counter` (55,35) 站 (55,36) | 09–20 |

## 3. 最短路怎么算

- 运行中：`GET http://127.0.0.1:8090/admin/path?from=55,13&to_arena=whale_room`、`...&to_object=fridge_home`、`...&to=12,26`，可加 `&mover=whale`（按她的门禁）、`&ignore_locks=true`；按**当前游戏时刻**算营业时间，所以 N4 要在 22:30 之后查。
- 离线整表：`cd BASIC_SANDBOX/back_end && uv run python scripts/path_table.py --map v1 --at 11:30 --as whale --points 客厅=12,26 街道=45,19 码头=55,13 鲸仔房=5,25 广场=41,26 --objects fridge_home bed_whale fishing_spot_1 table_rest_1 table_rest_2 bar counter --arenas whale_room dining [--format csv]`。上表的数字就是它算的。
- 步数比 = 她实际 `move` 成功次数 / 对应最短路（`move_to_area` / `go_to` 一次内部多步，按行动日志里 `skipLog=false` 的那一条算一次时请 A 注明口径）。
