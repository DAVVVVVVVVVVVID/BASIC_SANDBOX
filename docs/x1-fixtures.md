# X1 导航实验 · 摆场步骤（B 夹具，给 C 直接用；**world-v1.2 紧凑图坐标**，v1 图版本见 git 历史与 `docs/x1-shortest-v1.json`）

对应 `paper/plans/X1-navigation.md` §3。bench 镇：沙盒 **8090**（v1 图，`SANDBOX_SCENARIO=1`，须 ≥ 本文件所在提交）、自我层 8390。所有步骤都是 `POST /admin/scenario {"label": "...", "steps": [...]}` 一次打完；玩家用名字 `"鲸仔"` 引用（C 先以 `controller=agent, profile.agent_id=whale` join，名字 `鲸仔`）。坐标是 v1 图（`鲸鱼大学城·v1.0 草图`）的格，`GET /world.map.edges` 为准。

## 0. 每遍开始前

1. 总控清 bench（behavior-acceptance.md「每遍开始前先清 bench」：`townctl stop bench` → 删 `run/data/bench/{self,sandbox}` → `townctl start bench`）。清不动时至少 `{"op": "reset"}`（清玩家 / 冷却 / 聊天 / 物品改动，时间回到真实当前）。
2. C 让鲸仔 join。
3. 按下面某场景打一次 scenario；`set_time` 之后时间继续走（bench ×6 速由总控的 `SANDBOX_TIME_SPEED` / `/time` 定）。
4. 终止条件由 C 的跑手判；步数比用 `GET /admin/path`（见 §3）或下表的最短路。

## 1. 场景步骤

| # | 摆法 | steps | 终止 | 最短路（BFS 步数，按场景时刻、鲸仔身份） |
|---|---|---|---|---|
| **S01** 饿了就吃 | 饱腹 15，11:30，客厅 | `[{"op":"set_time","time":"11:30"}, {"op":"teleport","player":"鲸仔","x":9,"y":13,"facing":"down"}, {"op":"set_vars","player":"鲸仔","vars":{"fullness":15}}]` | 行动日志出现 `use` 成功且 `objectId: "fridge_home"`（冰箱在厨房 (5,15)，站 (5,16) 朝 up）/ 60 游戏分钟 | 客厅 (9,13) → `fridge_home` 站位 **7** |
| **S02** 到点睡觉 | 01:50，街道 | `[{"op":"set_time","time":"01:50"}, {"op":"teleport","player":"鲸仔","x":30,"y":9,"facing":"left"}]` | `use` 成功 `objectId: "bed_whale"`（床 (3,11)-(3,12)，站 (3,13)…）/ 60 分钟 | 街道 (30,9) → `bed_whale` **41**（合租房门 (9,18)→(9,17)，全天开） |
| **S03** 跨区寻路 | 码头 → 鲸仔房间 | `[{"op":"set_time","time":"10:00"}, {"op":"teleport","player":"鲸仔","x":43,"y":5,"facing":"up"}]` | `GET /player/{id}` 的位置落在 arena `whale_room`（`GET /agent/perceive` 的 `current.arena`）/ 300 步 | 码头 (43,5) → `whale_room` 最近格 **56** |
| **N1** 去用指定物品 | 在家，目标码头钓位 | `[{"op":"set_time","time":"10:00"}, {"op":"teleport","player":"鲸仔","x":4,"y":13,"facing":"down"}]`（目标告诉她：`fishing_spot_1`，码头 (45,2)，站 (45,3) 朝 up；06:00–20:00 开） | `use` 成功 `objectId: "fishing_spot_1"` / 60 分钟 | 鲸仔房 (4,13) → `fishing_spot_1` **63** |
| **N2** 探索新区域 | 第一次去餐厅（营业中） | `[{"op":"set_time","time":"12:00"}, {"op":"teleport","player":"鲸仔","x":28,"y":14,"facing":"right"}, {"op":"set_vars","player":"鲸仔","vars":{"fullness":45}}]`；餐厅 sector `restaurant`，arena `dining`（餐桌 `table_rest_1` (34,11)、`table_rest_2` (34,14)、吧台 `bar` (37,11)、冰箱 `fridge_rest` (41,11)），门 (36,18)→(36,17)，11–14 / 17–21 开。「树里只有名字」由 C 的变体控制 | 进入 `dining`（`current.arena`）后再离开 / 30 分钟 | 广场 (28,14) → `table_rest_1` **19**；餐厅坐下免费、`eat meal` 扣 20（v1.1） |
| **N3** 地点问答 | N2 之后，克劳蒂娜在广场问 | 接着 N2 的世界：`[{"op":"spawn","name":"克劳蒂娜","controller":"agent","agent_id":"claudine"}, {"op":"teleport","player":"克劳蒂娜","x":28,"y":13,"facing":"down"}, {"op":"teleport","player":"鲸仔","x":28,"y":14,"facing":"up"}, {"op":"invite","from":"克劳蒂娜","to":["鲸仔"],"greeting":"餐厅里有什么？"}]`；鲸仔接受后 C 收她的回答（`/chat/room/{id}`），需要再追问用 `{"op":"say","player":"克劳蒂娜","room":"<room>","text":"..."}` | 她在房间里回答 | — （判分 A：实词匹配 table_rest_1/2、bar、fridge_rest 的名字「餐馆桌子 / 吧台 / 冰箱」） |
| **N4** 关门绕路 | 22:30，饱腹 20，餐厅关门 | `[{"op":"set_time","time":"22:30"}, {"op":"teleport","player":"鲸仔","x":28,"y":14,"facing":"right"}, {"op":"set_vars","player":"鲸仔","vars":{"fullness":20}}]` | `use` 成功任一能吃的东西（`fridge_home`；杂货店 `counter` 20:00 也关了）/ 30 分钟 | 22:30：广场 → `table_rest_1` **不可达**（门 `closed`，`opens_at 11:00`）、→ `counter` **不可达**（杂货店 22:00 关，`opens_at 09:00`）、→ `fridge_home` **29** |
| **N5** 记忆过期 | 她去过餐厅后，餐厅两件物品挪位、一件撤掉，再让她去用 | 先跑完一次 N2（她进过餐厅、树里有了物品）。然后：`[{"op":"set_time","time":"12:30"}, {"op":"teleport","player":"鲸仔","x":28,"y":14,"facing":"right"}, {"op":"set_vars","player":"鲸仔","vars":{"fullness":30}}, {"op":"move_object","id":"table_rest_1","to":{"x":36,"y":14}}, {"op":"move_object","id":"table_rest_2","to":{"x":34,"y":16}}, {"op":"remove_object","id":"bar"}]`。此时 `table_rest_1` 在 (36,14)-(37,14)（站 (36,15)/(37,15) 或北侧 (36,13)/(37,13)），`table_rest_2` 在 (34,16)-(35,16)，吧台没了；旧位置 (34,11)/(35,11)、(34,14)/(35,14)、(37,11)/(38,11) 全是地板。`worldState.mapVersion` 会变（E 的前端据此重拉）。跑完 `{"op":"restore_object"}`（或下一遍的 `reset`）复原 | `use` 成功 `table_rest_1` / `table_rest_2` 任一（替代物）/ 30 分钟 | 广场 → 新位置的 `table_rest_1` **15**（`GET /admin/path?from=28,14&to_object=table_rest_1` 摆完可再查） |

说明：
- `teleport` 会先让她离开正在用的物品；`set_vars` 直写 clamp 到 0–100。
- 所有步骤同时写 `external` 日志（`kind: scenario`）与一行 state（`kind: scenario`），回放能重现。
- 物品挪位 / 撤掉只改内存：bench 重启或 `reset` 即还原，不会动地图文件。

## 2. 关键坐标（v1.2 紧凑图）

| 名 | arena | 格 | 备注 |
|---|---|---|---|
| 鲸仔房间 | `whale_room` | 出生点 (4,13)；床 `bed_whale` (3,11)-(3,12)，站 (3,13) | 合租房 sector `home`，大门 (9,18)→(9,17)（北巷 y18） |
| 客厅 | `living_room` | (9,13)；餐桌 `table_home` (7,11)，座位 (7,12)(8,12) | 楼梯 (10,16)↔(3,30) 到 2F 阿蝉房（09:00–18:30 锁） |
| 厨房 | `kitchen` | 冰箱 `fridge_home` (5,15)，站 (5,16)；灶台 `stove` (3,15)，站 (3,16) | v1.1：冰箱是储物柜不补货 |
| 街道 | `street` | (30,9)（主街 y8–9）；南北街 x20–21（y8–26，穿校园校门 (20,7)(21,7)） | |
| 广场 | `square` | (28,14)；喷泉 (26,12) 2×2，长椅 ×3（(23,11)(29,11)(26,16)），公告栏 (22,17) | |
| 码头 | `dock` | (43,5)；钓位 `fishing_spot_1` (45,2) 站 (45,3)、`fishing_spot_2` (45,6) 站 (45,7)；鱼摊 `fish_stall` (42,1) | 钓位 06–20 |
| 餐厅 | `dining` / `rest_kitchen` | 门 (35,18)→(35,17)；`table_rest_1` (34,11)、`table_rest_2` (34,14)（2×1，站南北）、`bar` (37,11)（站 (37,12)/(38,12)）、`fridge_rest` (41,11)、`stove_rest` (40,15) | 11–14 / 17–21；一餐 20 金币（eat meal） |
| 杂货店 | `grocery_shop` | 门 (23,25)→(23,24)（朝南开到短巷 y25，v1.2.1）；柜台 `counter` (28,22) 站 (27,22) 朝 right | 09–22 |

## 3. 最短路怎么算

- 运行中：`GET http://127.0.0.1:8090/admin/path?from=55,13&to_arena=whale_room`、`...&to_object=fridge_home`、`...&to=12,26`，可加 `&mover=whale`（按她的门禁）、`&ignore_locks=true`；按**当前游戏时刻**算营业时间，所以 N4 要在 22:30 之后查。
- 离线整表：`cd BASIC_SANDBOX/back_end && uv run python scripts/x1_shortest.py --map v1.2`（整表一键，写 docs/x1-shortest.json）或 `uv run python scripts/path_table.py --map v1.2 --at 11:30 --as whale --points 客厅=9,13 街道=30,9 码头=43,5 鲸仔房=4,13 广场=28,14 --objects fridge_home bed_whale fishing_spot_1 table_rest_1 table_rest_2 bar counter --arenas whale_room dining [--format csv]`。上表的数字就是它算的。
- 步数比 = 她实际 `move` 成功次数 / 对应最短路（`move_to_area` / `go_to` 一次内部多步，按行动日志里 `skipLog=false` 的那一条算一次时请 A 注明口径）。
