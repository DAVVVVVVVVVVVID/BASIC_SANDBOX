# WHALE_REPORT — 会话 B（BASIC_SANDBOX）

分支：`whale-integration`。最新：**W11 维护第 1 轮（2026-11-07 下午）**；W11、W10、W9、W8、W7–W1 记录在后。

---

# W11 维护 · 2026-11-07 下午：第 1 轮（巡检 + 给 B 条目 + Q2）

## 1. 巡检

| 实例 | 日期 | 日志行数 | 2xx / 4xx / 5xx | Traceback / ERROR / 401+403 | tick 间隔 p95 / max | tick 耗时 p95 / max | RSS | players / ws | actions / chat / state / external 行 | mapVersion |
|---|---|---|---|---|---|---|---|---|---|---|
| 主镇 8000（`bf58966`，uptime 18 h） | 2026-11-07 | 158946 | 158575 / 50 / 0 | 0 / 0 / 0 | 201.6 / 212.2 ms | 0.323 / 12.391 ms | 98.6 MB | 1 / 0 | 403 / 0 / 1581 / 13 | 阿蝉家与小镇@1b824832ace2 |
| 草图镇 8091（`fc051f1`，刚重置） | 2026-11-07 | 11 | 6 / 1 / 0 | 0 / 0 / 0 | 201.8 / 206.7 ms | 0.294 / 6.174 ms | 61.3 MB | 0 / 0 | 0 / 0 / 0 / 2 | 鲸鱼大学城·v1.0 草图@6918f8018e93 |

0 Traceback、0 5xx，无需热修。主镇鲸仔此刻 `using table_rest_1`（重起前记得看，README 第 9 条）。

## 2. 「给 B」条目

| 来源 | 条目 | 处理 |
|---|---|---|
| E（W10 联调回报，`e0be69a`） | ① ws `qq` 的 `read` 事件只当刷新信号；② 旁观面板要 `unread_total` 的位置 | ① 可以；② `GET /agent/perceive` 的 `phone.unread_total`，或 `GET /qq/inbox?player=` 顶层 `unread_total`——已回 |
| E（W11 回报） | produce / commission 事件 8091 上没法手动触发，想要 scenario op | **已加** `POST /admin/scenario` 两个 op：`give_item {player, item, qty?, meta?}`（往背包放物品）、`produce {player, via?, item?, qty?}`（模拟一次产出：背包 + ws `produce` + external 行 + pendingMessage）；commission 事件用 `POST /admin/commission` 即可触发 `open`，`give song` 给委托人触发 `deliver`。8091 已重起带上 |
| E（W11 回报 2，`dcaf304`） | 用两个 op 实测：produce → 头顶「🎣 钓到了鱼」+ 背包；give_item song → QQ 发文件成功；/admin/commission → 「📋 新委托」气泡。交付没测（8091 没有 NPC 实例当 target） | 已回：scenario `spawn` 直接造 `npc_rest_owner` agent 实例（不需要 brain）即可走 give song 交付；E 之前把 `file_ref` 发成字符串 422，已自己改成对象。**随后 E 测通交付**：gold 300→488、「完成委托《冒烟委托》收到 188」、ws action + commission deliver 都到——匹到的是我冒烟留下的最早 open 单（匹配顺序 payload.commission_id → 歌的 meta.commission_id → 最早 open），已确认给 E |
| D（report-D W10 回应） | 4b 字段一致，联调一局等 8000 切版本；perceive 时才拉 `/game/state` 同意 | 无需改 |
| A（W12 交接 / report-A） | 「B 的 export 字段」已在 W9 第 0 项落地；无新条目 | — |
| C | 报告停在 11-06，无新条目（v1 profile 接 QQ / buy / compose 时的字段问题优先答） | 等 |

## 3. 小队列 Q2（内存 / 检查点趋势）——今天一点 + 一处修

- RSS 数据点：主镇 11-06 71.5 MB → 11-07 98.6 MB（1 player，18 h）；同机 m2a 8010（uptime 25 h）88 MB、bench 8090（4.5 h）82 MB、刚起的 8091 61 MB——增长与负载不成比例，更像 Python / uvicorn 的基线爬升，**继续记点，三天后看斜率**。
- 代码里逐个核过模块级容器：有上限的（action `_LOG`、chat / external `_MEM` 200、qq 5000、recent_events 50、ticker 样本）都正常；`_use_history` 按时间窄口裁；**没有上限的只有 chat_state 的 `_chat_requests` / `_chat_rooms`**——结束的邀请和关闭的房间永远留在内存并每 5 s 跟着检查点重写（主镇今天 9 单 / 4 房，量小但无限）。**已修**：`chat_state.tick()` 末尾 `_purge_finished`——非 pending / walking_over 的邀请保留 1 h，关闭的房间保留 24 h（期间 `GET /chat/room/{id}` 仍可看；JSONL 是永久记录），关房时记 `closed_at`，旧检查点里没有 `closed_at` 的从第一次见到起算。2 例单测。
- 顺手把 `test_w8_q1` 那条同毫秒偶发断言改成 `>=`（上一节提过）。

## 4. 测试

`cd back_end && uv run pytest -q` → **291 passed**（W11 的 288 + 清理 2 + scenario op 1）。api-spec 的 scenario op 表加了两行。

Q3（m1c 真实负载巡检）等 C 起镇；Q4（freeform 使用统计）、Q5（api-spec 全文核对）下两轮各做一项。

## 5b. 总控（whale-68）X1 导航实验夹具 —— 完成

- **`docs/x1-fixtures.md`**（本仓库）：S01 / S02 / S03 / N1 / N2 / N3 / N4 / N5 在 v1 图上的 `POST /admin/scenario` 步骤、终止条件、关键坐标、每场景的最短路步数（按场景时刻与鲸仔身份算）。总控若要放进 `whale/docs/`，直接拷这个文件。
- **N5 需要的新 op**：`move_object {id, to{x,y}}`、`remove_object {id}`、`restore_object {id?}`——只改内存（tile 字符改地板 / 物品、`_OBJECTS` 重建保留 userList / stock、`usePos` 跟着算、`mapVersion` 重算，正在用的人请离），`reset` 与重启还原；恢复后 `mapVersion` 回到原值（按原顺序放回）。
- **最短路**：`GET /admin/path?from=x,y&to=x,y|to_object=|to_arena=[&ignore_locks][&mover=]`（所有实例、只读、按当前游戏时刻门禁）+ 离线 `scripts/path_table.py`（任意点 / 物品 / arena 两两矩阵，md / csv / json）。
- 4 例单测（`tests/test_w11_x1_fixtures.py`）：挪位 / 撤掉 / 非法目标 / 恢复 + 指纹复原；挪动请离使用者 + reset 还原；`/admin/path` 到 arena / 物品 / 同格 0 步 / 22:30 餐厅不可达 / ignore_locks / 400 / 404 / 小千家门禁按 mover。294 passed。8091 已重起带上；**bench 8090 要切到本提交才有这三个 op 与 `/admin/path`**。

## 5g. §3.40 敲门机制 —— 完成

- `game/doors.py` + `routers/door.py` + 动作 `knock`：家 = 带 `access.locked` 的 sector（商店不算）；访客在门外 ≤ 2 格 `knock {door_id | target_tile | home}` → `door_request`（90 游戏秒），动作日志 `knock`，ws `knock` 事件（带门坐标），在家且清醒的主人 `pendingMessage`「X 在敲门。」+ `pending_knocks[]` / perceive `knocks[]`；`POST /door/respond {request_id, entity_id, accept}` 只限主人：accept → `door_pass`（这家全部 arena，2 游戏小时或进屋后离家即失效，`edge_block` / `arena_block` 同一判定，日志 `door_pass_granted` / `door_pass_expired {timeout|left}`），decline → `declined`，到期 → `no_answer`（日志 `door_respond` outcome no_answer）；ws `door` 事件。`GET /player` 加 `door_request / pending_knocks / door_passes`，perceive 加 `knocks / door_request`，`GET /door/requests`。通行证与请求进检查点 meta `doors`。物品不设归属（§3.40 ①）：本来就没有物品级权限，无需改。
- **测试** `tests/test_w11_knock.py` 3 例：老渔夫敲合租房门（太远 `too_far`、重复 `already_knocking`）→ 阿蝉在客厅清醒收到 → 非主人不能回应 → accept → 老渔夫 `go_to kitchen` 真走进厨房、这家所有 arena 可达 → 2 小时后通行证没了、再进 `no_path`；鲸仔在睡 → 没人收到 → 95 秒后 `no_answer`；醒了 decline；商店 `not_a_home`、主人 `is_owner`；进屋再离家 → `door_pass_expired left`；检查点往返后通行证与请求都在。311 passed。
- api-spec 新「11. 敲门」一节 + 行为表 `knock` 行。

## 5f. §3.39 合租房门禁（「为什么老渔夫在我家」）—— 完成

- **原因**：v1 的 `access` 只有渔夫 / 小千 / 店主 / 阿蝉房，合租房三间与 `door_home` 没有任何规则，谁都能进（老渔夫 05:34 走进厨房、模板期睡过 `bed_whale`）。
- **改**（`gen_map_v1.py`，按 02-map §2.3）：`access.whale_room = {owner [whale], locked always, allow_when_locked [achan, npc_xiaoqian]}`、`living_room / kitchen = {owner [whale, achan], locked always, allow_when_locked [npc_xiaoqian]}`；`door_home` 加 `owner [whale, achan]`、`allow ["owner", "npc_xiaoqian"]`。小千按总控意见放进 allow（主播改口再去）。出门照 §3.38 放行。核过各家大门：渔夫屋 / 小千家 / 店主家本来就有 owner，餐厅 / 杂货店 §3.38 加了，现在六扇门都有 `owner`。v1 图重出（tiles / 物品不变，mapVersion 不变；access 11 条）。
- **「出门永远放行」的室内推广** `arena_cross_block`：站在自己不被允许的场所里的人，往同一 sector 相邻场所走一律放行（否则老渔夫会被锁在厨房——厨房 → 客厅跨的是 arena 不是门边）；出了门就回不来。所有跨场所判定（相邻格、楼梯、走路、首阻塞）走这一个函数。
- **人类放行（总控 11-08 定）**：`_allowed` 新关键字 `"human"`（controller=human 的玩家），加进合租房三处 `allow_when_locked` 与 `door_home.allow`——操控页演阿蝉的人类玩家进出自如。
- **NPC 冰箱（总控问「老渔夫冰箱空」）**：规则对所有 `fridge` 类型一样（`economy.json fridge`：初始 2、每日 08:00 +2、上限 4、use 吃 1），不是只有鲸仔家有补货。主镇 11-08 05:26 实况：`fridge_fisher / fridge_home / fridge_rest / fridge_owners` 都是 0，只有小千家还剩 2——每天只补 2 份而每人一天吃 3 顿，08:00 前必空；03-objects 的设计是「从杂货店买食材补」，NPC 的 agent 若不会 `buy ingredients` + `store`，冰箱就只够两顿。建议（配置项，不改代码）：`fridge.initial / restock_qty` 提到 3–4，或主播定 NPC 家冰箱另给水位；等总控 / 主播拍板。另：家里的最短路（`/admin/path`、`path_table.py`）要带 `mover=whale`，x1-fixtures 的数字本来就是按鲸仔算的，不变。
- **测试** `tests/test_w11_home_access.py` 2 例：老渔夫街道 `go_to kitchen` → `no_path/locked/blocked_at (12,33)`；小千进客厅、再去鲸仔房间；阿蝉进鲸仔房间；老渔夫已在厨房能走出去、回不来；鲸仔随时进；人类单格 `locked`；六扇门 owner 与三条 access 规则进了 `/world.map`。既有 1 例改（x1 的 `/admin/path` 家里加 `mover=whale`）。

## 5e. §3.38 门禁只管「进」不管「出」、主人随时双向 —— 完成

- **根因**（C / 总控查出）：21:00 餐厅门关后，店主从吧台回卧室要先出门 (51,30)→(51,31)，`edge_block` 不分方向、按 open_hours 判 `closed`，店主被锁在自己店里。
- **改**：`edge_block(edge, mover, ts, frm)` 有向——出发格是边的内侧 `b` 即「出」，任何人任何时候放行；主人（`edge.owner` ∪ 内侧场所 `access.owner` ∪ `homes` 住在内侧的人）随时双向，不受 `open_hours` / `allow`；`crossing_block`、`neighbors`（楼梯）、`first_block_on_path`、走路 `walk_tick`、`_blocked_detail` 全部传出发格。`gen_map_v1.py`：`door_restaurant.owner=[npc_rest_owner]`、`door_grocery.owner=[npc_grocer]`，v1 图重出（tiles / 物品没变，mapVersion 不变）。
- **测试** `tests/test_w11_access_direction.py` 2 例：21:30 店主从吧台到卧室可达（`/admin/path mover=npc_rest_owner` 与 `move_to_area` 真走到）、打烊后店主仍能回店；客人在店里能出（(51,30)→(51,31)）、出了进不来（`no_path/closed/11:00`）、从店里深处 `move_to_area square` 有路；小千家常锁外人能出不能进；杂货店关门后老板娘双向、外人 `closed`；边的 `owner` 进 `/world.map.edges`。既有用例全过。
- api-spec `map.edges` 表加「进 / 出语义」一行。

## 5d. §3.36 移动改为「必须有路、按固定速度花游戏时间」（主播 11-07 20:55 定）—— 完成

- **改法**（`game/world_state.py` 走路队列 + `routers/actions.py`）：`move / move_n / move_to_area / go_to` 统一先 BFS（复用 `bfs_path`，逐边判锁与时段）；有路 → `state="walking"`、路径入队、**立即返回** `{state:"walking", path_len, eta_game_s, position, facing, target}`；ticker 每 tick 按 **1 格 / 游戏秒**（`SANDBOX_WALK_TILE_SEC`，默认 1.0，env 可覆盖）逐格推进，每格到点前再查可走 / 门锁 / 时段 / `canMove`；到达 / 中断在动作日志写 `move_done {outcome: arrived|blocked|stopped, reason, position, path_len, steps_done, game_s, action, target, start}`（`success = arrived`）并推 ws `action` 事件；无路 → `no_path` + `result.{blocked_reason, blocked_at, opens_at}`（首个阻塞）。新 move 替换旧路径（`stopped/replaced`）；走路中 `use/interact` → `reason: walking`；`leave` 就地停；聊天接受进入 `walking_over` 的那一 tick 就地停（`stopped/state:walking_over`）；人类单格 `direction` 免排队（门锁照查，走路中按方向键 = 就地改手动）；夹具 `teleport` 取消路径；`usePos` 入座不变。`GET /player/{id}` 多 `walk: {remaining, path_len, eta_game_s, target, next, started_at, action}`。走路队列不进检查点（重启归 idle）；回放把 `move_done` 当位置同步点、回放中不写 move_done。
- **测试**：`tests/test_w11_walking.py` 7 例（1 格 / 游戏秒逐格推进与 `walk` 字段、到达 `move_done`；`SANDBOX_WALK_TILE_SEC`、人类单格立即 / targetTile 排队 / 走路中方向键改手动、agent 单格也排队；`no_path` 带 `blocked_reason/blocked_at/opens_at`、13:59:50 出发去餐厅 14:00 门关 → `blocked/closed`；走路中 use/interact 拒绝、leave 就地停、新 move 替换；聊天接受中途停下；move_n / go_to 排队；teleport 取消 + ws 字段）。既有 9 例按新语义改（`walk_done` 测试助手；`locked/closed` → `no_path + blocked_reason`；回放多一行 `move_done`）。**304 passed**。`verify_self_sync / verify_external / verify_game` 改成一次 `move targetTile` + 等 `state != walking`。
- **api-spec**：新「移动语义（§3.36）」一节 + move 响应示例 + `GET /player` `walk` + reason `no_path / walking` + 日志类型 `move_done`。
- **给 E**：`reason` 不再直接是 `locked/closed`（人类单格除外），锁门气泡请看 `result.blocked_reason`；`state == "walking"` 播走路帧，位置按 patch 逐格；ws `action` 事件多 `state / path_len / eta_game_s / blocked_reason / blocked_at`，新事件 `action: "move_done"`。**给 C**：发出移动后轮询 `GET /player/{id}` 到 `state != "walking"`（超时 eta×3+10 s）。
- **E 已接**（whale-frontend `048a118`，rebase 到 `489062a`）：去掉前端猜路、按每 tick 位置逐格推 waypoint、步速 1000 ms ÷ 倍速、人类单格 300 ms、walking 走路帧；气泡接 `result.blocked_reason` / `move_done blocked` / `reason: walking`。8091 实测人类 move 到 (44,24) path_len 60，采样位置全相邻、最大跳 1 格。接口无需改。
- **8091 自测（×6 速，提交 `910506f`）**：① 码头 (55,13) `go_to whale_room`：立即返回 `walking, path_len 71, eta 71.0`，12.1 s 真实时间走完（71 游戏秒），`move_done {outcome: arrived, position (9,30), path_len 71, steps_done 71, game_s 71.9, action: move_to_area}`；② 10:00 `move_to_area achan_room` → `no_path {blocked_reason: locked, blocked_at (3,37), opens_at 18:30}`；③ 广场出发去餐厅（16 格）走 3 格时小千邀请、鲸仔接受 → `walking_over`，就地停在 (41,29)，`move_done {outcome: stopped, reason: state:walking_over, steps_done 3, game_s 4.6}`。测试玩家已清。

## 5c. 总控（whale-68）追加：最短路 JSON、床的饱腹疑问 —— 完成，并查出 bench 的根因

- **`docs/x1-shortest.json`**：`{"S01": 13, "S02": 67, "S03": 71, "N1": 85, "N2": 24, "N3": null, "N4": 50, "N5": 17}`（按各场景时刻、鲸仔身份；N5 = 广场 (41,26) 12:30 到挪位后的 `table_rest_2` (50,28) 17 步，`table_rest_1` (48,26) 为 21，取「任一替代物」的最小值）。
- **床没有饱腹项**：`object_types.json` 全图共用（v0 / v1 同一张表），`bed` = energy +25/h、fun −1/h + no_move/no_interact/no_use；`bed_21` 同形 energy +20/h。bath / sofa / bench 只有 fullness **−**1/h。pilot 里「用床后饱腹 15 → 40」不是床。
- **根因（bench 8090 的 11-07 日志）**：S03 夹具 `reset` + `set_time 15:00` + `spawn` 后，self-sync 每 30 游戏秒与自我层对账，自我层 8390 回的 whale 值远低于本地（第一批 drift fullness −43.9 / energy −29 / social −22 / fun −37，之后几批继续往下），snap「以自我层为准」把本地**所有变量 2 游戏分钟内打到 0**（state 行 15:00:30 → 15:02:30 全 0）。同理 S01 直写 fullness 15 时自我层还是旧值 ~59，snap 把它拉回 40。即：**夹具直写的值被自我层旧状态覆盖**。
- **修**：`self_sync.assert_local(pid)`——scenario 的 `spawn` / `set_vars` 之后本地为准：漂移 > 0.5 时不 snap 本地，把差值当 delta 推回自我层（`external` `self_assert`、`/admin/self-sync` `asserts`），两边一致后恢复原规则；非夹具玩家照旧 snap。2 例单测（假自我层回显 60 → 直写 15 → 一批后仍 15、自我层两批内变 15；spawn 同理；旁人照旧 snap）。**另请 A 看一眼 8390**：它的 whale 状态为何在 15:00 时是 ~26 / 70 / 38 / 23 并持续下滑——可能是 bench 自我层数据没清或它按墙钟衰减（bench ×6）。bench 跑 X1 也可以干脆 `SELF_SYNC=0`。
- 296 passed。8091 已重起带上；bench 8090 请切到本提交。
- **追加（总控转 A 的要求）**：直写后不只「本地为准」，还要**立刻**让自我层一致——`self_sync.push_local_now()`：`GET /self/state` 取远端，`POST /self/state/delta` 发 (本地 − 远端)，`source: "scenario"`；`spawn` / `set_vars` 步骤结果带 `self_push {ok, pushed, remote_after}`；自我层不可达时直写照样成功、由对账兜底推回。3 例单测（直写即一致、spawn 带 vars 即一致、推送失败兜底），297 passed。

## 5. 总控（whale-68）两条

- **agent_id 全线统一**（04-npcs.md）：`whale / achan / npc_xiaoqian / npc_rest_owner / npc_grocer / npc_fisher`。核对：v1 `homes`、`economy.json`（初始金币 / 日薪 / 店主）、`qq_config.json`（显示名 / 通讯录 / 群）、`commissions.clients` 全部已是这组，无别名；只有 v0 兜底表 `AGENT_HOME_ARENA` 里还是旧名（`npc_cook` / `npc_regular`…）——已补上 `npc_rest_owner → cook_bedroom`、`npc_xiaoqian → regular_bedroom`，旧名保留给老检查点。
- **Q6（排队，冻结后做）**：实验 X4「靠近即可说」—— `POST /action say {text}`：曼哈顿 ≤ 2 格内的玩家在下一次 perceive 的 `nearby_speech[]`（`from, text, ts`）看到，不开房间不走邀请；进聊天 JSONL（`kind: say`）与 ws。C 的变体排在冻结之后。

---

# W11 · 2026-11-07：冻结前收口——产出链、直播收入、QQ 亲密度、库存补货、SANDBOX_MAP / world_reset

**v1 就位**（冻结清单第 2 步）：`SANDBOX_MAP=v1` 默认图 ✅、`scripts/world_reset.sh` ✅（已在 bench_v1 跑过一次）、`economy.json` / `items.json` / `qq_config.json` 三份配置 ✅（所有数值都在里面，冻结后只调数）、v1 全部物品 BFS 可达 ✅（`test_all_objects_reachable_including_2f`）。提交号见 git log 最新（本节）。主镇 8000 没动。

## 1. 进度（1–6 全部完成）

| # | 任务 | 状态 | 做了什么 |
|---|---|---|---|
| 1 | 产出链 | ✅ | `game/production.py` + `economy.json` `production`：**钓位** use 后每 40 游戏分钟掷一次（50%，有鱼饵 80% 并消耗 1 鱼饵）得「鱼」进背包；**灶台** use 需 1 份食材（否则 `no_ingredients`），use 时消耗，满 30 分钟产便当 ×2（提前 leave 不产）；**`compose`** 动作：正在用 `pc_music` 且用满 30 分钟 → 产「歌」（文件类，`meta.title / commission_id / text` 由 C 填；B 只做物品与交付）；**`make_video`**：在 `pc` / `pc_desk` / `stream_desk` 上用满 60 分钟 → 产「电台文稿」。随机数按 `SANDBOX_SEED` 定种（回放可复现），每次产出：`pendingMessage`、ws `produce` 事件、`external` 日志 `kind: produce`。**委托** `game/commissions.py`：`POST /admin/commission` 手动下单 + 每日 08:00 以 0.3 概率自动出一单（open ≤ 3）；`GET /commissions`；use 公告栏 `result.commissions`；`give song` 给委托人 → `status: delivered`、酬金入账（流水 `source: song_fee`）、委托人对她亲密度 +15。委托进检查点 |
| 2 | 直播收入 | ✅ | `POST /admin/income source=stream` 给 `viewers_avg` / `gifts` 自动折算 `viewers_avg × 0.5 + gifts × 1.0`（`live_income.per_viewer / gift_rate`），流水带 `viewers_avg, gifts, synthetic:false`；`live_income.synthetic: true`（默认）时 `leave` 直播物品即按 `synthetic_range` [20, 60] 随机入账一行 `source: stream, synthetic: true`（定种）。直播机接上后把 `synthetic` 改 false |
| 3 | QQ 亲密度 | ✅ | `qq_config.json` `unread_penalty {after_hours: 2, per_hour: 1, daily_cap: 5}`、`read_reply_bonus: 1`：1:1 消息未读超 2 游戏小时后，发件人对收件人每小时 −1（每对每日 ≤ 5）；收件人读到 → 发件人对他 +1；回一条 → +1。群消息不计；发件人不在线没处记。每条消息记 `penalized_hours`，日累计进检查点 |
| 4 | 库存与补货 | ✅ | 商店 `stock`（`shops[].stock`：柜台 面包 10 / 甜食 10 / 食材 10 / 鱼饵 10 / 礼物 3；鱼摊 鱼 5），买减卖加，`out_of_stock`，每日 `restock_at` 08:00 补到水位（只补不减，同日一次）；`/world` 物品 `stock` 字段 + `shop[].stock` 实数。**冰箱** `stock {ingredients}`：初始 2、每日 08:00 +2 不超过 4，`use` 吃一份（空 → `empty`），新动作 `store` 放食材。库存进检查点（`object_runtime.stock` 列，旧库自动迁移） |
| 5 | 冻结日准备 | ✅ | `SANDBOX_MAP=v1`（`world_state._resolve_map_dir`：`SANDBOX_MAP_DIR` 目录 > `SANDBOX_MAP` 名字 > v0）；`run_town.sh --map v1` 接受名字；`scripts/world_reset.sh --map v1 --data <dir> --port <p> [-- run_town 参数]`：停 pid → 旧目录改名 `<dir>.v0-<时间戳>`（`--no-archive` 直接删）→ 空目录起新世界。**bench_v1 验证**：`world_reset.sh --map v1 --data run/data/bench_v1/sandbox --port 8091 -- --no-sync --scenario --env SANDBOX_TOWN=bench_v1` → 旧数据归档到 `sandbox.v0-20261107-130749`，8091 起来 mapVersion `鲸鱼大学城·v1.0 草图@6918f8018e93`、0 玩家、12 边、柜台库存满、冰箱 4（启动在 08:00 后补了一次）、当日自动出了一单委托（老渔夫 244）。旧 v0 图仍是默认 |
| 6 | 文档 | ✅ | api-spec（物品 `stock`、`store` / `compose` / `make_video`、库存与产出链小节、新 reason、export external 新 kind、ws `produce` / `commission`、QQ 亲密度、`/admin/income stream`、`/admin/commission`、`/commissions`、地图开关）、data-models（商店与库存 / 产出链 / 委托）、README（W11 段 + 地图开关与重置） |

## 2. 测试命令与结果

```bash
cd back_end
uv run pytest -q                                   # 288 passed（W10 的 279 + 9）
scripts/world_reset.sh --map v1 --data /home/shan-dw/Project/run/data/bench_v1/sandbox --port 8091 -- --no-sync --scenario --env SANDBOX_TOWN=bench_v1
```

| 新增 | 用例 | 覆盖 |
|---|---|---|
| `tests/test_w11_production.py` | 9 | 钓位 40 分钟掷一次（p=1 必中、鱼饵消耗、p=0 不中、external `produce` 行）；灶台无食材拒绝 / 消耗 / 30 分钟产 2 便当且只产一次 / 提前走不产 / 便当可吃；compose 需在 pc_music 且满 30 分钟、`/admin/commission`、公告栏读到委托、`give song` 交付 → +200 金币 + 委托人亲密度 15、无委托时只是转交；make_video 满 60 分钟出文稿、每日 08:00 出单一次；直播收入公式 27 = 40×0.5+7、没 amount 400、下播 synthetic 20–60 一行、关 synthetic 不入账；QQ 未读 2h 内不扣 → −1 → 日上限 −5 → 读 +1 → 回 +1 → 群不计；商店 `out_of_stock`、`shop[].stock`、次日补到水位、同日一次；冰箱 use 减到空 → `empty`、`store` 不超 4 / `storage_full` / `not_storable`、08:00 +2 不超 4、检查点保留；`SANDBOX_MAP` 解析（v1 / v0 / 不存在 / `SANDBOX_MAP_DIR` 优先） |
| `tests/test_w10_economy.py` 改 1 | — | `shop[].stock` 从 null 变 10 |
| conftest | — | 测试里默认 `commissions.daily_p = 0`（要的测试自己设 1.0），避免随机出单打乱计数 |

注：`tests/test_w8_q1.py::test_replay_same_second_join_and_actions_unambiguous` 偶发（同一毫秒内 action 与 state 行的墙钟 ts 相等，断言用的是严格 `>`），与本轮无关，重跑即过；留着下轮把断言改成 `>=` + 行序。

## 3. 假设（都在配置里，冻结后改数不改代码）

- 产出链：钓鱼 40 min / 50% / 80%、灶台 30 min 产 2、compose 门槛 30 min、make_video 门槛 60 min（03 说「做视频 1–2 h」取下限）；C 的 agent 调 `compose` / `make_video` 前要先 `use` 对应物品并待够时间，否则 `not_ready`（带 `ready_in_min`）。
- 委托：酬金 150–300 随机、每日 0.3 概率出一单、委托人从 4 个 NPC 里随机、open ≤ 3；交付匹配顺序 payload.commission_id → 歌的 meta.commission_id → 该委托人最早的 open 单。
- 直播：synthetic 默认开；`gift_rate` 1.0（礼物按金币 1:1，07 说「礼物折算比例」待定）。
- QQ：发件人不在线（NPC 没 player）不扣不加；`read_reply_bonus` 每次读每个发件人 +1（不是每条 +1）。
- 库存：补货「只补不减」（卖给店多出来的不会被削回水位）；冰箱启动时若已过 08:00 会补一次；补货是确定性的，不记 external。
- 重置脚本只管沙盒自己的数据目录；自我层数据、supervisor 由总控 / C 按冻结清单第 5 步处理。

---

# W10 · 2026-11-07：南门与装饰层、使用者站位、QQ 消息、金币与背包、游戏机正式接口

提交：`17d6747`（①②）、`c0e75ef`（③④ + 4b + 文档）、本报告提交见 git log 最新。主镇 8000 未切（仍 v0 图 / 旧代码进程）；草图镇 **8091 已用新代码重起**（`run/data/bench_v1/sandbox`，v1 图，scenario 开，no-sync），E 可直接联调。

## 1. 进度（① ② ③ 4b ④ ⑤ 全部完成）

| # | 任务 | 状态 | 做了什么 |
|---|---|---|---|
| ① | v1 地图南门 + 装饰层 | ✅ | `gen_map_v1.py`：`door_home (12,34)→(12,33)`、`door_restaurant (51,31)→(51,30)`、`door_grocery (51,39)→(51,38)`、`door_xiaoqian (16,42)→(16,41)`、`door_owners (26,47)→(26,46)`，全部 a 外（小巷 `lane`）b 内（门格归所邻房间：合租房门归客厅、店主家门归杂货店主房），门前补小巷格；渔夫屋与校园三栋不动。`decor[]` 6 项：西草坪小径（街→合租房前，12 格）+ 3×3 池塘 + 晾衣绳；东草坪小径（校门→码头巷，19 格）+ 3×2 池塘 + 2×2 花坛；另加 9 棵 `tree` 物品（`tree_w1–5`、`tree_e1–4`）。小径改成可走地板、池塘改成水；其余只记位置。`GET /world.decor` 下发（`?fields=decor` 可单取）。61 物品 / 12 边 / 8 访问规则，BFS 全可达测试仍过 |
| ② | 使用者站位与朝向 | ✅ | `object_types.json` 加 `use_pos: [[dx,dy],…]`（相对格）与 `use_facing`：床 / 浴缸 `[[0,0]]` down（躺在床格上）、长椅 / 沙发 `[[0,0],[1,0]]` down、餐桌 4 座（南北各两格，朝向按相对位置推）、吧台 `[[0,1],[1,1]]` up、桌类（desk / pc / pc_desk / pc_music / reading_desk / classroom_desk / stream_desk / game_console / stove）南侧一格朝 up、`desk_12` `[[0,2]]`。`GET /world` 物品带 **绝对格 `usePos: [{x,y}]`** 与 `useFacing`（没站位的物品 `null`）；perceive 不带。**后端 `use` 时真的把人挪到站位并转向**（按使用顺序分配，已占的跳过），`leave` 回 use 前的格与朝向，`pos_seq` 各 +1；use 前位置进检查点（`extra.pre_use_pos`），旧检查点没有记录时 leave 落到相邻可走格。回填时站在物品格上算合法位置 |
| ③ | QQ 消息存储与接口 | ✅ | `game/qq.py` + `routers/qq.py` + `game/qq_config.json`：账号 = agent_id（人类 = player id），不在线也能收；`POST /qq/send`（text / file；file 只允许 `items.json` `class: file` 的 song / script / image，实物 `not_transferable`；文件是**复制**，在线收件人背包加一份）、`GET /qq/inbox?player=&since=&peer=&unread_only=`（含 `direction`、群消息按成员各自 read_at）、`POST /qq/read`（标已读、返回正文、加 timed buff `reading` 60 游戏秒：`canMove/canUse=false`、`tags` 带 `reading`，到期自动摘）、`GET /qq/contacts`（初始通讯录：鲸仔 = 阿蝉 / 小千 / 餐厅老板 / 杂货店老板；群 `g_live`「鲸仔直播组」= 鲸仔 + 阿蝉；`online` = 在场）。perceive `phone.unread: {显示名: 条数}` + `unread_total`（**`phone` 从「没刷过为 null」改为总是对象**）。睡觉 / 直播中 `phone_unavailable`。每条消息 / 每次读一行 `data/qq/<date>.jsonl`；ws 推 `{type:"qq", event: message|read, …平铺}`；检查点表 `qq_messages` / `qq_groups` + meta `qq_contacts`；`/admin/export` 新 kind `qq`。每条消息发送者 / 阅读者 `social +2`（可配） |
| 4b | 游戏机换 D 的正式接口 | ✅ | `external_effects.game_*` 改为：use 前置 **energy ≥ 25**（否则 `too_tired`）→ `GET /game/state`，`alive` 且有 `run_id` 就接着这局（`how: joined`），否则 `POST /game/start {"by":"sandbox"}` 后每 5 s 轮询到 `alive=true`（120 s 超时 `game_unavailable` / `start_timeout`）；局中 perceive 刷 `/game/state`（day / phase / health / hunger / sanity / goal / latest_png / usd_today…），新加一句话 `text`「饥荒第 6 天黄昏，HP 150，正在…」；leave → `POST /game/stop {"by":"sandbox","shutdown":false}`（不关服），记 `left_at_day` / `duration_s`，external 日志 `game/stop`。不再调 `/healthz` `/event` `/metrics`，不发 `/self/game/session`。**对真 brain 8110 联调 `scripts/verify_game.py` 7/7 PASS**（接上了 D 正在跑的 run-1794021101 第 6 天；stop 后 brain 仍 alive） |
| ④ | 金币与背包数据层 | ✅ | `game/items.json`（10 种，03-objects 3.2）、`game/economy.json`（初始金币 鲸仔 300 / 阿蝉 2000 / 小千 400 / 店主 3000 / 渔夫 800；日薪阿蝉 150@18:30、店主 100@21:00 / 20:00、渔夫 80@17:00；小千 12/h 13–17 点每整点；餐价 20；商店目录与店主）、`game/inventory.py`（≤ 10 种，`{type, count, meta?}`，视图加 `name / class`）、`game/economy.py`（流水 `ledger` → `data/economy/<date>.jsonl` + ws `economy` 事件；`on_tick` 按日程结薪，已付键进检查点）。动作 `buy / sell / eat / give`（`routers/economy_actions.py`，payload `item|item_id / object_id / target / qty`）；买的钱进店主账（在线才有人收）；**use 餐桌扣 20**，钱不够 `insufficient_funds` 不坐下；`POST /admin/income`（写歌酬金 / 直播收入由外部调，`amount` 可负）。`GET /world` 物品 `shop: [{type,item,name,price,sell,stock:null}]`；players[] / `GET /player` 带 `gold` / `inventory`；state 行加 `gold`；导出 kind `economy` |
| ⑤ | 文档 | ✅ | `docs/api-spec.md`（/world 新字段、行为表 + buy/sell/eat/give 节、错误 reason、perceive game/phone、external game 契约、export kinds、ws qq/economy 事件、新「9. QQ」「10. 金币与入账」两节）、`docs/data-models.md`（站位 / 装饰 / 商店 / 游戏机 / Player gold+inventory / InventoryEntry / QQMessage / 流水）、`README.md`（数据集两类、行为表、QQ / 金币一段、/admin/income）、`scripts/verify_game.py` |

## 2. 测试命令与结果

```bash
cd back_end
uv run pytest -q                                   # 279 passed（W9 的 256 + ①② 6 + QQ 7 + 经济 8 + 游戏机 +2）
uv run python scripts/gen_map_v1.py               # 64x48, format 2, 61 objects, 12 edges, 8 access rules, floors={'achan_room': 2}, decor=6
uv run python scripts/verify_game.py              # 对真 brain 8110：7/7 checks passed → PASS
```

| 新增 / 改动 | 用例 | 覆盖 |
|---|---|---|
| `tests/test_w10_map_use.py` | 6 | 五门全在南墙（a 在 b 正南、a 是小巷、b 是室内、门内一格是地板）、渔夫屋 / 校园不动；decor 下发且不是物品、小径可走池塘不可走、≥ 9 棵树；`usePos / useFacing` 下发、perceive 不含；use 挪到站位 + facing + pos_seq，leave 回原地并能走；多座位 / 无站位物品 |
| `tests/test_w10_qq.py` | 7 | send → perceive 只给条数不给正文 → inbox → read 返回正文并 60 游戏秒不能走 / 用 → 到期摘 tag；群消息每成员各自已读；文件类才可转交（鱼 / 礼物拒绝，歌复制到对方背包）；参数 reason；睡觉 / 直播 `phone_unavailable`；人类通讯录与给离线账号发；JSONL + 导出 + 检查点往返（seq 续号）；ws `qq` 事件 |
| `tests/test_w10_economy.py` | 8 | 初始金币按配置并在 players[] / `GET /player` 下发；`shop[]`；buy（含 `object_id` / `item_id` 写法、店主入账）/ eat（饱腹 +25）/ sell reason / `insufficient_funds`；营业时间 `shop_closed` + `opens_at`；give 礼物（对方亲密度 +8、心情 +5）、距离、满包不扣；餐桌扣餐价与钱不够；`/admin/income`、阿蝉 18:30 日薪一次、小千 4 个整点各 12、state 行 `gold`；检查点保留 gold / 背包 / 已付 |
| `tests/test_w6_game.py` 改 | 6（+2） | 假 brain 换成 `/game/state` `/game/start` `/game/stop`：alive 的局直接接（不发 start）、leave 发 stop 不关服；没活局 → start + `how: regenerated`；轮询到 alive 与 2 s 超时 `start_timeout`；energy < 25 `too_tired`；刷新失败保留旧值 |
| 既有用例改 5 处 | — | use 后躺到床格（persistence / effects / ws 三处按新站位摆人）、v1 物品数 52→61、导出默认 6 类、perceive `phone` 不再 null、ws upsert 字段集 + gold / inventory |

8091 冒烟（新代码）：阿蝉 `POST /qq/send` → 鲸仔 perceive `phone.unread {"阿蝉": 1}` → `POST /qq/read` 拿到正文、鲸仔 `tags: ["reading"]`，此时 `buy` 返回 `use_disabled`（符合「读消息期间不可做别的」）；阿蝉 teleport 到杂货店柜台 `buy bread×2` → gold 1990、背包 `[{type: bread, count: 2}]` → `eat` fullness 94.9；`/admin/income` whale +150；`/admin/export?kinds=qq,economy` 计数 2 / 2。

## 3. 给 E（字段名对齐 report-E.md §2 的差异）

| E 的假设 | 实际 | 说明 |
|---|---|---|
| `GET /qq/contacts` → `{contacts:[{id,name,unread}], groups:[{id,name,members,unread}]}` | **一致**（超集）：contacts 另有 `account`（= id）、`online`、`player_id`；groups 另有 `member_names`；顶层另有 `account` / `name` | — |
| `GET /qq/inbox` → `{messages:[{id,ts,from,to\|group,kind,text,file_ref,read_at}]}` | **一致**，另有 `from_name`、`game_time`、`direction: in\|out`；顶层另有 `account` / `unread` / `unread_total` | `since` 是 ISO 时间戳（不含） |
| `POST /qq/send {from, to\|group, kind, text\|file_ref+item}` | **接受**：`from` = `entity_id`，`item` 平铺 = `file_ref.item`，不给 `kind` 自动判 | 规范写法是 `entity_id` + `file_ref{item,…}` |
| `POST /qq/read {player, from\|group}` | **接受**：`player` = `entity_id`，`from` / `group` = `peer` | — |
| ws `{type:'qq', message:{…}}` 或平铺 | **平铺**：`{type:"qq", event:"message"\|"read", id, from, from_name, to, group, kind, text, file_ref, read_at, …}` | 另有 `{type:"economy", kind, account, delta, balance, item, …}` |
| `players[]` / `GET /player` 带 `gold:number`、`inventory:[{type,name,count}]` | **一致**，inventory 元素另有 `class`、可选 `meta` | — |
| `objects[].shop:[{type\|item, name, price, stock}]` | **一致**：`type` 与 `item` 都给（同值），另有 `sell`（收购价），`stock: null` = 不限量 | 只有 `shop_counter` / `fish_stall` / `bar` 有，其余 `null` |
| `POST /action` buy/eat/give/sell payload `item / item_id / object_id / target / qty` | **一致**，都接受；`object_id` 缺省 = 面前的物品 | `insufficient_funds` 在 `reason`，`result` 带 `price` / `gold` / `message` |
| ws `action` 事件带 `item / item_name / price\|gold_delta / target_name` | **一致**：`item, item_name, qty, price, gold_delta, gold, target, target_name`（有则带） | — |
| `use_pos` 相对物品 `position`、`use_facing` 四向 | **差异**：下发的是**绝对格** `usePos: [{x,y}]`（已换算）+ `useFacing`；相对偏移只在 `object_types.json` 里 | 而且后端 `use` 时已把人挪到该格并转向，E 的 `poseAnchorsFor` / `sleepAnchorFor` 可以退掉：人物就站（躺）在服务器给的位置，朝向跟服务器 |
| `decor[]` 在 `/world.decor` | **一致**：`/world.decor`，`[{id, kind: path\|pond\|clothesline\|flowerbed, tiles:[{x,y}]}]` | 树是普通 `tree` 物品 |
| `reading` 标签名 | **确认** `reading`（`tags` 里，60 游戏秒） | — |
| perceive `phone` | 以前没刷过为 `null`，现在总是 `{…digest?, unread, unread_total}` | 旁观页若按 `phone === null` 判「没手机」要改成看 `unread_total` |

## 4. 假设与未做

- 数值全是 06-economy / 03-objects 的草稿值（`economy.json` / `items.json` / `qq_config.json` 改即生效，不用改代码）。
- 日薪「人要在线才发」（不在线的 NPC 没有 player 实例，没处记）；重启后同日不重发（已付键进检查点）。
- 未做：钓鱼得鱼 / 灶台出便当 / 琴房产 `song` / 直播收入自动折算（配置 `live_income_per_viewer` 0.5 已留，直播侧回传后走 `/admin/income`）、「长时间不回消息降亲密度」（数值未定）、`stock` 库存（现在不限量）。
- QQ 文件转交是复制（发送者保留）；实物只能 `give`（2 格内）。
- 游戏机 `GAME_POLL_S` / `GAME_START_TIMEOUT_S` 环境变量可调；use 期间不主动每 20 s 拉状态，perceive 时才刷（她看一眼才更新，省 brain 的请求）。
- `phone` 形状从 `null | digest` 变成总是对象，是 W10 唯一一处「对外形状」变化（只加键），E / C 侧请注意。

---

# W9 · 2026-11-07：世界 v1.0 地图原型（连接边、楼层、锁门）

## 0. 第 0 项（A 的导出核对）——提交 `9c201b1`

`GET /admin/export` 的 state 旧行没有 `tags`（Q0d 只改了 `state_log` 新写的行）：导出现在按**规范字段集**回填（`EXPORT_FIELDS`：actions 13 项、chat 6 项公共 + message/event 自有、state 19 项、external 7 项公共），缺的按默认值补（`tags: []`、`facing: null`、`mood_base: null`、`objectId: null`…）并标 `backfilled`；`manifest.fields` 回显字段集。与 `docs/dataset-schema.md` 的 `sandbox_*` 行一致（state 的 `kind` 现有 `sample | join | rejoin | restore | scenario` 五值，请 A 把 schema 的「`kind: sample`」改写为枚举）。

## 1. 进度（任务 1–4 全部完成）

| # | 任务 | 状态 | 主要文件 |
|---|---|---|---|
| 1 | **地图格式 v2**：`map.json` 加 `format`、`edges[]`（door / gate / stairs，`a`/`b` 两端格，`open_hours`、`allow`、`owner`）、`floors`、`access`（owner / `locked` 时段或 `"always"` / `allow_when_locked`）、`homes`；`world_state.load_map()` 可切图（原地更新容器）；BFS 走 edges（楼梯 = 非相邻邻接），每步跨场所查边与 access；`move` / `move_n` / `move_to_area` / 新别名 `go_to` 被挡时返回 `locked` / `closed` 带 `opens_at`（忽略门禁能到才算门禁，否则 `no_path`）；`GET /world` 新顶层 `map`；perceive 的 arena 带 `floor` | ✅ | `game/world_state.py`（`load_map / neighbors / bfs_path / crossing_block / arena_block / edge_block / first_block_on_path`）、`routers/actions.py`、`models/world.py` |
| 2 | **v1.0 草图** `scripts/gen_map_v1.py` → `game/maps/v1/`：64×48，按 02-map 的相邻关系：鲸鱼大学（教学楼 / 图书馆 / 音乐楼，校门 06–23）、老渔夫家、码头（钓位×2、渔船、卖鱼摊）与河、东西主街 + 南北街 + 两条小巷、合租房 1F（鲸仔房 / 客厅 / 厨房）与 **2F 阿蝉房**（画在画布左下，楼梯边连客厅；09:00–18:30 锁、owner 阿蝉）、公园（树、长椅、小路）、广场（长椅×3、喷泉、公告栏）、餐厅（四人桌×2、吧台、后厨冰箱；门 11–14 / 17–21 朝广场）、杂货店（柜台、货架；门 09–20）、小千家、店主们的家（两间 + 共用厨房；NPC 家常锁 owner-only）；52 个物品按 03-objects 3.1 位置，类型沿用旧表或 **占位类型**（`pc / pc_desk / stove / sofa_tv / bar / fish_stall / notice_board / pc_music / reading_desk / classroom_desk` 克隆旧表数值，`tree / shelf / boat / fountain / piano` 为装饰，全部标 `placeholder: true`，数值不改）；出生点鲸仔房间，`homes` 给 6 个 agent id | ✅ | `scripts/gen_map_v1.py`、`game/maps/v1/{map,objects,tile_types,tile_gids}.json`、`game/object_types.json` |
| 3 | 草图镇起在 **8091**：`run_town.sh --port 8091 --data run/data/bench_v1/sandbox --map game/maps/v1 --no-sync --scenario`（新加 `--map`），`SANDBOX_TOWN=bench_v1`，mapVersion `鲸鱼大学城·v1.0 草图@6bf958223cd6`，`/world?fields=map` 可见 12 边 / floors / access；E 可直接渲染 | ✅ 运行中 | `scripts/run_town.sh` |
| 4 | 旧图保留 `game/maps/legacy_v0/`；默认目录 `game/maps/` 仍是 v0，主镇不切 | ✅ | — |

未做（按交接）：物品数值、背包、金币、QQ。

## 2. 测试命令与结果

```bash
cd back_end
uv run pytest -q
# 256 passed（W8 的 247 + 第 0 项 1 + v2 地图 8）

uv run python scripts/gen_map_v1.py          # 64x48, format 2, 52 objects, 12 edges, 8 access rules, floors={'achan_room': 2}
```

| 新增 | 用例 | 覆盖 |
|---|---|---|
| `tests/test_w6_dataset.py` +1 | 1 | 第 0 项：旧 state 行回填 `tags / facing / mood_base` 并标 backfilled；每行字段集齐全；`manifest.fields` |
| `tests/test_w9_map_v2.py` | 8 | v1 图 format 2、`/world.map` 的 edges / floors / access、perceive arena 带 floor、8 个 sector；6 个 agent 出生在各自的家、human 出生鲸仔房；**52 个物品从鲸仔房间出发全部可达（含 2F，经楼梯边）**；**阿蝉房 10:00 鲸仔 `move_to_area` / `go_to` → `locked` + `opens_at 18:30`，阿蝉本人能进，19:00 鲸仔能上楼再下楼**；单步 `move` 进渔夫家门 → `locked`（owner 可进，常锁 `opens_at null`）；校门 23:30 → `closed` + `06:00`，图书馆 08:30 → `closed` + `09:00`，音乐楼 8 点开；餐厅门 15:00 → `closed` + `17:00`、12:00 可进；河 `no_walkable_tiles`；legacy v0 图 format 1 行为不变 |

## 3. api-spec 改动摘要（只增不删）

`GET /world` 新顶层 `map`（edges / floors / access 字段表）；行为类型新 `go_to` 别名；`move` / `move_n` / `move_to_area` 新 reason `locked` / `closed` 带 `opens_at`；perceive arena 节点新 `floor`；`/admin/export` 规范字段集；v1.0 草图说明。`README.md`、`docs/data-models.md` 同步。

## 4. 对契约 / 其他会话

1. **给 E（渲染草图）**：8091 已起，`GET /world` 全量含 `tiled`（E 的 gid 表）、`zone_names`、`map.edges`（门 / 校门 / 楼梯两端坐标）、`map.floors`（`achan_room` = 2，画在 x2–9 / y36–41 的独立框里，按区域取景时当成另一层）、`map.access`（锁门表现：`locked` 时段可画门闩）。想换布局改 `gen_map_v1.py` 的坐标常量即可，欢迎直接提坐标。
2. **给 C（导航 V2）**：寻路已走边；`move_to_area` / `go_to` 返回 `locked / closed + opens_at` 时请当「现在不行、X 点再来」；2.5 的「初始空间树只含合租房三间 + 四个名字」是感知过滤，perceive 仍给整树（C 侧裁）。NPC id 我按 `npc_fisher / npc_xiaoqian / npc_rest_owner / npc_grocer` 建了 `homes`，A 的 persona id 定稿后告诉我改一行。
3. **给 A**：state 行 `kind` 五值枚举（见 §0）；`/admin/export` 的 state 旧行 `tags` 已回填为 `[]`（真实标签不可追溯，只保证字段齐全）。
4. **假设**（02-map 没写死的）：校门 06:00–23:00；码头栈道不设门（全天）；NPC 家「熟人可敲门」未做，先 owner-only 常锁；合租房大门不锁；楼梯边无时段；2F 画在画布左下角；餐厅后厨 / 渔夫厨房等内门不设边。
5. **运行台**：主镇不切（默认图仍 v0）；本提交对 v0 行为的唯一变化是 `/world` 多 `map` 字段与 `go_to` 别名，其余路径不变。

## 5. 本次提交

第 0 项 + v2 底层：`9c201b1`；草图、测试、8091、文档：见 `git log -1`。

---


# W8 · 维护节奏 · 2026-11-06 第 1 轮（原报告）

## 1. 巡检（每天一轮第 1 步）

| 日期 | 日志行数 | 2xx / 4xx / 5xx | Traceback / ERROR / 401+403 | tick 间隔 p95 / max | tick 耗时 p95 / max | RSS | players / ws | actions / chat / state / external 行 | mapVersion |
|---|---|---|---|---|---|---|---|---|---|
| 2026-11-06 | 105278 | 2xx 105086 / 4xx 27 / 5xx 0 | 0 / 0 / 0 | 201.7 / 211.4 ms | 0.338 / 11.202 ms | 71.5 MB | 1 / 1 | 398 / 9 / 94 / 1 | 阿蝉家与小镇@1b824832ace2 |

运行台已是 `1bfe54d`（11:30 游戏时切换，`external/` 开始有行：1 条 `self_seed`）。0 Traceback，无需热修。

## 2. 「给 B」条目（每天一轮第 2 步）

| 来源 | 条目 | 处理 |
|---|---|---|
| A（W9 §2「episodes 的依赖」） | 行动日志里 agent 的 `use` 没带 objectId，episodes 看不出「用了什么」 | **已落地**：行动日志每行新增 `objectId`（取自动作结果，use / leave / interact 有值，其余 null）；`GET /history` / `/history/log` / `/admin/export` 同步带。数据契约只加字段，api-spec `GET /history` 字段表已更新 |
| A（S60 质检 `chat_vs_ws na`） | 当天无 `chat/2026-11-06.jsonl` | 现已有 9 行（11:0x 起有对话）；`/history/chat` 可对账 |
| A（S77b） | 导出沙盒源 3 类 | W7 已多出 `external` 一类，请加 `kinds=external`（已在 W7 报告） |
| C | W1–W3 的旧条目（walking_over 字段、rejoin 路径、床可见） | 均已在 W3–W5 落地；C 报告无新条目 |
| E | W4 §4：`tile_gids.json`、`zone_names`、action `object_type` | W7 已落地；E W5 报告仍未出，等 |
| D | 无 | 维持过渡契约 |

## 3. 小队列 Q1（join / rejoin / 回填立即采样）——完成

- `state_log.sample_now(player, kind)`：join / rejoin / 检查点回填后各立即写一行（`kind: join | rejoin | restore`），并把 30 s 节拍对齐到此刻；state 行新增 `mood_base`、`facing`。
- 回放：同一游戏秒内按真实毫秒 `ts` 排序；窗口内后续 join / rejoin / restore 行作为**同步点**（对齐 vars、位置、朝向、正在用的物品——重启回填不是动作，没有这步无法复现）；聊天 JSONL 的房间事件作为第四个输入（对话期间 `chat_active` 让 leave 失败，决定钓鱼 / 睡觉的时长）；历史行缺 `facing` 时从窗口前最后一次 turn / 方向 move 推断；`--until` 时「实际值」取窗口内最后一行（修了一个 bug）；`--start-kind rejoin` 可从起点行回放。
- 验收：`tests/test_w8_q1.py` 3 例——join / rejoin / restore 三行 + 节拍对齐；行动日志 objectId；**rejoin 同一秒内瞬移 / 转向 / use 再睡 30 min，从 rejoin 行回放差 0、动作结果零不一致**；重启回填（restore 行）把「正在用的床」带回来，回放差 < 0.5。
- **对 11-06 主镇全天（含 11:30 的运行台重启）回放：**

```
replay main 2026-11-06  window 2026-11-06T11:01:45+08:00 → 2026-11-06T11:42:42+08:00 (2457 s)
  players=['e键测试_347b78', 'e键测试_3a4cad', 'e键测试_e41717', '阿蝉_5d3096', '阿蝉_6b53a8', '阿蝉_c7013d', '阿蝉_fb59b4', '鲸仔_ddba81'] state_rows=97 events=50 applied={'actions': 31, 'effects_push': 0, 'self_seed': 1, 'self_snap': 0, 'adjudication': 0, 'skipped': 0, 'action_result_mismatch': 4, 'chat_events': 2} actions_before_window_skipped=367
  nondeterministic inputs in window: 1  kinds=['self_seed:']
  player                 var          replay    actual     diff
  鲸仔_ddba81              fullness     63.763    63.766   -0.003
  鲸仔_ddba81              energy       76.621    76.623   -0.002
  鲸仔_ddba81              social       44.843    44.845   -0.002
  鲸仔_ddba81              fun          92.559    92.560   -0.001
  鲸仔_ddba81              mood         71.301    71.300   +0.001
  阿蝉_5d3096              fullness     69.296    69.298   -0.002
  阿蝉_5d3096              energy       99.531    99.532   -0.001
  阿蝉_5d3096              social       59.648    59.649   -0.001
  阿蝉_5d3096              fun          59.413    59.415   -0.002
  阿蝉_5d3096              mood         65.000    65.000   +0.000
max |diff| = 0.003  (threshold 0.5) → PASS
```

今天的分叉源依次是：① `--until` 口径 bug（已修）② 历史 state 行无 `facing`（她在码头面朝右才能钓鱼；现已记）③ 对话状态不在行动日志里（她钓鱼时在和 NPC 聊天，`leave` 被 `chat_active` 挡住所以一直钓；现把 chat JSONL 房间事件当输入）。三处修完，跨重启全天 **max |diff| 0.003**。剩下 4 个「结果不一致」动作全是 Q1 之前采样同秒的临时测试玩家，不影响七变量。

## 4. 测试与提交

```bash
cd back_end && uv run pytest -q      # 247 passed（W7 的 181 + Q1 5 + Q0 24 + Q0b 10 + Q0c 22 + Q0e 4 + 回放同步点 1）
uv run python scripts/replay.py --date 2026-11-06 --town main      # max |diff| 0.003 → PASS（跨重启）
uv run python scripts/inspect_runstation.py                        # §1 那一行
```

本轮用时约 1 小时。提交见 `git log -1`。回放原始输出 `back_end/scripts/replay_main_2026-11-06.txt`（全天）与 `…_until1130.txt`（重启前）。

## 5. 对契约 / 其他会话

1. **给 A（数据契约）**：行动日志行加 `objectId`；state 行加 `facing`、`kind` 多 `join | rejoin | restore` 三值。只加字段。
2. **给 A（质检）**：聊天 JSONL 的房间事件现在是回放输入，`dataset_check.py` 若校验 chat 行数请连事件行一起算（`kind=event`）。
3. **运行台**：建议下次重起切到本提交（含 Q1 的立即采样与 `facing`）；不切也不影响运行，只影响下一次重启那一刻的可复现性。

## 5b. Q0 紧急项（插队，同日）——钓位死锁

- **根因**（与交接单的 `no_use` 诊断略有出入）：`handle_leave` 唯一的拦截是 `chat_active`（对话中返回 `use_disabled`），`no_use` 并不挡 leave。死锁组合是：钓位 / 长椅 / 浴缸带 `no_move`（挡 move），同时她在对话里（`chat_active` 挡 leave）——对话不结束就两头都走不了；`chat_active` 没有 tick handler，`canUse` 每 tick 复位，所以对话中 `use` 钓位能成功（12:02 / 12:17 / 12:32 三次正是如此），然后被锁。重启不是诱因，但回填会把 `chat_active` 原样带回来。
- **修法**：① `leave` 对正在使用的物品永远放行，失败只剩 `not_using_any_object` / `player_not_found`；② 检查点回填后 `chat_active` 与活跃房间对账（没房间的清掉、有房间的补上）。
- **单测** `tests/test_w8_q0_leave.py`（24 例）：地图上 **19 个 continuous 物品逐个 use → tick → leave 必须成功**（覆盖所有 no_use / no_move 物品）；对话中 use 钓位 → move 仍 `move_disabled`（预期）但 leave 成功；use → 重启回填 → leave 成功；对同一物品再次 use 不重复计数 → leave 成功；回填清掉无房间的 `chat_active`。
- 行为契约：api-spec `leave` 小节已注明。提交：`3ec0fe1`（修复 + 单测）与其后一提交（单测时序修正），**请总控切到最新提交**；旧实例上被卡住的人仍可用 `POST /admin/player/force-reset` 解开。

## 5c. Q0b 行为验收夹具（插队，同日）

- `POST /admin/scenario {label, steps[]}`，14 个原子 op：`reset / set_time / spawn / remove / teleport / set_vars / effects / occupy(sticky) / release / invite / respond / say / exit_chat / clear_cooldowns`；按序执行遇错即停；`player` 可用唯一 name；只在 `SANDBOX_SCENARIO=1` 开放（`run_town.sh --scenario`），否则 403。
- 对数据集可见：每步一条 `external` 行（`kind=scenario`），受影响玩家立即一行 state（`kind=scenario`）；回放把 scenario 行当外部输入重现（`set_vars / teleport / spawn / remove / occupy / release / effects`）。
- 单测 `tests/test_w8_scenario.py` 10 例：门禁 403；S01 摆法端到端（reset → 11:30 → 广场放鲸仔 fullness 15，时间继续走，日志与采样）；teleport 校验可走格与 name 歧义；set_vars / effects / closeness 直写且不进 self-sync；occupy sticky 让别人 `object_full`、不触发自动离开、跳过营业时间、满员 / 非 continuous 报错、release；占直播台只本地切 live；对话四 op 跳过冷却并建房；remove / clear_cooldowns / 未知 op；S02 摆法 + `move_to_area(storage)` 可达；scenario 行回放一致。
- 给 C 的跑手：S01–S10 的「摆法」列都能用上表拼出（S04 用 `spawn` NPC + `invite`；S05 用 `occupy sticky`；S07 用 `set_time 19:50` + `teleport` 小仓库；S08 用 `set_time 22:30` + `set_vars fullness 20`）；S06 / S09 / S10 的记忆、inbox、Dream 部分在自我层，夹具只管沙盒侧。api-spec §6 新小节。提交号见下。

## 5d. Q0c leave 后同秒 move（插队，同日）

- **根因确认**：`leave_object` 当即移除了物品的 `no_move` buff，但 `canMove` 只在 `run_tick` 第 ② 步重置、第 ③ 步重算，要等下一个 200 ms tick；同一秒内的 move 读到旧的 `canMove=false` → `move_disabled`。use 时反向同理（`no_move` 也晚一个 tick 才生效，`test_w6_game` 里就有一条「tick 前 canMove 尚未置 False」的旧断言）。
- **修法**：`buff_tick.apply_control_flags(player)`——只跑 `no_move / no_interact / no_use / move_speed` 四个控制 handler、不碰需求值与计时；在 `enter_object`、`leave_object`、`/effects` 推送、admin 清 buff、force-reset 之后同步调用。leave 响应带离开后的 `canMove / canUse`。没有用 `movable_at`：同步清以后它恒为「现在」，多一个字段没有信息量。
- **单测** `tests/test_w8_q0c_leave_move.py` 22 例：19 个 continuous 物品逐个「use → 立刻 move 必须 `move_disabled`（带 no_move 的）→ leave → 同秒 move 必须成功」，全程不经过 tick；leave 后立刻 `move_to_area`；force-reset 与 admin 清 buff 后立刻可动；`/effects` 推 `no_move` 立刻生效。改 1 条旧断言（`test_w6_game`）。
- 提交号见下。

## 5e. Q0d state 行加 tags（插队，同日）

- `data/state/*.jsonl` 每行新增 `tags`（玩家当前 buff 标签：`sleeping / fishing / streaming / gaming / dining / resting / working / taking_bath / reading`），S02 看 `sleeping`、S07 看 `streaming`。数据契约只加字段；`/admin/export` 的 state 同步带。单测 1 例（use 床 → 下一样本 `["sleeping"]`，leave 后为空）。提交号见下。

## 5f. Q0e 人类 away 与床类无冷却（插队，11-07）

- **away**：human 连续 120 s 无输入（动作 / `GET /player` / `POST heartbeat` / 聊天请求、响应、发言）→ `away=true`，任一输入即清；agent 恒 false。按墙钟在每个 tick 更新（不依赖 game_delta）。away 的人不算在场：perceive 的 `players_in_view` / `needs.closeness`、`GET /chat/nearby` 不列出；邀请到 away 的人 → `reason=target_away`（先于冷却判断）。`GET /world` / `GET /player` / ws `players.upsert` 都带 `away`。回填后 `last_input` 置为现在（给 120 s 窗口）。
- **床类无冷却**：`object_types.json` 新增类型级 `cooldown_s`（缺省 1800；`bed` / `bed_21` 为 0），`object_cooldown_remaining` 按类型取；其余物品不变。三个老冷却测试改用桌子。
- 其余世界设定改动等 v1.0 定稿。单测 `tests/test_w8_q0e_away.py` 4 例（119 s 不 away / 121 s away / 三种输入清 away / agent 永不 away；away 不在 perceive、nearby，邀请 `target_away`，发邀请本身是输入；ws upsert 带 away；床立刻可再用而钓位仍冷却）。提交号见下。

## 6. 小队列余项

Q2（12 agent 七天内存 / 检查点趋势，每天一点）、Q3（m1c 真实负载巡检，等 C 起镇）、Q4（freeform 使用统计）、Q5（api-spec 全文核对）——明天起每轮做一项。

---


# W7 · 2026-11-06：可复现回放、作息与营业时间、七天长跑巡检、E 的新需求（原报告）

## 1. 进度（任务 1–6 全部完成）

| # | 编号 | 任务 | 状态 | 主要文件 |
|---|---|---|---|---|
| 1 | B19 | **可复现回放**：新增外部效果 / 不确定性日志 `data/external/<date>.jsonl`（`self_seed / self_snap / effects_push / adjudication / feed / live / game / nondeterministic`），`/admin/export` 多 `external` 一类；`scripts/replay.py --date --town --data-dir`：每个 player 从第一条 state 行起步，按游戏时间合成 actions + external 时间线，事件间 1 游戏秒步进跑同一套 tick，外部调用按日志打桩；在每个 player 最后一条 state 行时刻截取，逐变量作差（阈值 0.5），列出 nondeterministic 输入与「重放结果与日志 success 不一致」的动作；state 行加 `mood_base` | ✅ 见 §2 | `game/external_log.py`（新）、`game/replay.py`（新）、`scripts/replay.py`（新）、`self_sync / world_state / actions / time_control` 的日志挂点、`state_log.py` |
| 2 | B20 | **作息与营业时间**：`object_types.json` 加 `open_hours`（餐馆桌子 11–14 / 17–21、杂货店柜台 9–20、码头钓位 6–20「日出后」假设）；`GET /world` / perceive 的物品带 `open / opensAt / openHours`，**关门时 `advertise` 全 0**；关门 `use` → `closed` 带 `opens_at`，不计冷却；到点自动请出使用者；ws `objects` 带 `open` | ✅ | `world_state.open_state / _object_view / _kick_closed_objects`、`routers/actions.py`、`routers/agent.py`、`routers/ws.py`、`models/world.py` |
| 3 | 巡检 | `scripts/inspect_runstation.py`：读运行台日志（只读）+ `/admin/metrics` 出一行表；今日一行见 §5 | ✅ | `scripts/inspect_runstation.py`（新） |
| 4 | E 需求 | E 的 W5 报告**尚未写出**（report-E 最新是 W4）；按 W4 §4 与 W7 交接预告落地：① `GET /world` 顶层 `zone_names` ② `worldState.town`（多镇代理）③ ws `action` 事件带 `object_type` ④ E 交付的 `tile_gids.json` 落到 `game/maps/`（含 m1c），`gen_map.build_tiled` 读其 `_tileset` 覆盖 tileset → `tiled` 现为 `gen/tiles.png` ⑤ 回放页所需的 `/admin/export` 加 `external` 类（含 nondeterministic） | ✅ | `world_state.get_world`、`models/world.py`、`routers/actions.py`、`scripts/gen_map.py`、`game/maps/tile_gids.json` |
| 5 | D 接口 | D 的报告仍无正式游戏机接口 → 维持 W6 过渡契约；对 8110 重跑联调一局 8/8 PASS（run-1793933517） | ✅ | `scripts/verify_game.py` |
| 6 | B14 | 文档同步 | ✅ | `docs/api-spec.md`（`closed`、营业时间段、`zone_names / town`、`external` 类与回放、`object_type`）、`README.md`、`docs/data-models.md` |

未碰 `front_end/`。

## 2. 回放（任务 1 验收）

**对 11-06 主镇（运行台 `run/data/sandbox`，只读）回放：**

```
replay main 2026-11-06  window 2026-11-06T11:01:45+08:00 → 2026-11-06T11:23:19+08:00 (1294 s)
  seed=None map=阿蝉家与小镇@1b824832ace2
  mood_base from self-layer persona (历史 state 行缺字段): {'whale': 69.5}
  players=['e键测试_347b78', 'e键测试_3a4cad', 'e键测试_e41717', '阿蝉_5d3096', '阿蝉_6b53a8', '阿蝉_c7013d', '阿蝉_fb59b4', '鲸仔_ddba81'] state_rows=58 events=40 applied={'actions': 24, 'effects_push': 0, 'self_seed': 0, 'self_snap': 0, 'adjudication': 0, 'skipped': 0, 'action_result_mismatch': 4} actions_before_window_skipped=367
  ⚠ 4 个动作重放结果与日志不一致，例如：[{'game_time': '2026-11-06T11:14:01+08:00', 'entity': '阿蝉_fb59b4', 'type': 'move', 'logged': False, 'logged_reason': 'tile_not_walkable', 'replay': True, 'replay_reason': None}, {'game_time': '2026-11-06T11:16:57+08:00', 'entity': '阿蝉_6b53a8', 'type': 'move', 'logged': False, 'logged_reason': 'tile_not_walkable', 'replay': True, 'replay_reason': None}, {'game_time': '2026-11-06T11:16:58+08:00', 'entity': '阿蝉_6b53a8', 'type': 'use', 'logged': True, 'logged_reason': None, 'replay': False, 'replay_reason': 'no_object_in_front'}]
  nondeterministic inputs in window: 0
  player                 var          replay    actual     diff
  鲸仔_ddba81              fullness     68.006    68.006   -0.000
  鲸仔_ddba81              energy       79.739    79.739   +0.000
  鲸仔_ddba81              social       46.797    46.797   +0.000
  鲸仔_ddba81              fun          92.819    92.819   -0.000
  鲸仔_ddba81              mood         70.800    70.800   +0.000
  阿蝉_5d3096              fullness     69.296    69.298   -0.002
  阿蝉_5d3096              energy       99.531    99.532   -0.001
  阿蝉_5d3096              social       59.648    59.649   -0.001
  阿蝉_5d3096              fun          59.413    59.415   -0.002
  阿蝉_5d3096              mood         65.000    65.000   +0.000
  阿蝉_fb59b4              fullness     69.999    69.999   +0.000
  阿蝉_fb59b4              energy      100.000   100.000   +0.000
  阿蝉_fb59b4              social       60.000    60.000   +0.000
  阿蝉_fb59b4              fun          59.999    59.999   +0.000
  阿蝉_fb59b4              mood         65.000    65.000   +0.000
  阿蝉_c7013d              fullness     69.999    69.999   +0.000
  阿蝉_c7013d              energy      100.000   100.000   +0.000
  阿蝉_c7013d              social       60.000    60.000   +0.000
  阿蝉_c7013d              fun          59.999    59.999   +0.000
  阿蝉_c7013d              mood         65.000    65.000   +0.000
  e键测试_e41717            fullness     69.999    69.999   +0.000
  e键测试_e41717            energy      100.000   100.000   +0.000
  e键测试_e41717            social       60.000    60.000   +0.000
  e键测试_e41717            fun          59.999    59.999   +0.000
  e键测试_e41717            mood         65.000    65.000   +0.000
  e键测试_3a4cad            fullness     69.999    69.999   +0.000
  e键测试_3a4cad            energy      100.000   100.000   +0.000
  e键测试_3a4cad            social       60.000    60.000   +0.000
  e键测试_3a4cad            fun          59.999    59.999   +0.000
  e键测试_3a4cad            mood         65.000    65.000   +0.000
  e键测试_347b78            fullness     69.999    69.999   +0.000
  e键测试_347b78            energy      100.000   100.000   +0.000
  e键测试_347b78            social       60.000    60.000   +0.000
  e键测试_347b78            fun          59.999    59.999   +0.000
  e键测试_347b78            mood         65.000    65.000   +0.000
  阿蝉_6b53a8              fullness     69.999    69.999   +0.000
  阿蝉_6b53a8              energy      100.000   100.000   +0.000
  阿蝉_6b53a8              social       60.000    60.000   +0.000
  阿蝉_6b53a8              fun          59.999    59.999   +0.000
  阿蝉_6b53a8              mood         65.000    65.000   +0.000

max |diff| = 0.002  (threshold 0.5) → PASS
```

读法：
- 窗口是 11:01:45 → 11:23:19：运行台 11:05 才切到带 `state_log` 的版本（46a968b 在 W6 加的），之前没有 state 行无起点可回；8 个 player 里鲸仔与一个长驻的阿蝉有多条样本，其余是只采过一次的临时测试玩家（在各自那一刻截取，差值 0）。
- **鲸仔五变量差 ≤ 0.000，阿蝉 ≤ 0.002，max |diff| = 0.002**。历史 state 行没有 `mood_base`（鲸仔从自我层种入的 OCEAN 基线是 69.5），`replay.py` 对缺字段的 agent 用只读 token 从自我层 `GET /self/state` 取 ocean 算基线补上（输出里的 `mood_base from self-layer persona`）；本提交起 state 行自带 `mood_base`，不再依赖这一步。
- 4 个「重放结果与日志不一致」的动作全是临时测试玩家在采样同一秒的 move / use（30 s 采样粒度下动作落在快照前后的歧义），不影响七变量。
- 窗口内 0 条 nondeterministic 输入——因为外部日志是本提交才开始写的；运行台切换后，自我层种入 / 纠偏、`/effects` 回推、切倍率都会进 `external/`，全天回放才有完整输入。
- 合成验证（`tests/test_w7.py::test_replay_synthetic_day_matches_state_log`）：2 小时 21 分里睡觉 / 吃饭 / 两次 `/effects` 推送 / 切 live / 切倍率 / 四步移动，11 个动作 + 3 次推送全部重放，**五变量差 0.000**，`time_speed` 被记为 nondeterministic。
- 已知不可回放：不进日志的改动（测试里的 `place()`、直接改 `_players`）；W6 之前写的历史行。

## 3. 测试命令与结果

```bash
cd back_end
uv run pytest -q
# 181 passed（W6 的 170 个 + W7 新增 11 个：test_w7.py）

uv run python scripts/replay.py --date 2026-11-06 --town main      # 见 §2，max |diff| 0.002 → PASS
uv run python scripts/verify_game.py                               # 8/8 PASS（D 接口未变）
uv run python scripts/inspect_runstation.py                        # §5 的那一行
```

| 新增 | 用例 | 覆盖 |
|---|---|---|
| `tests/test_w7.py` | 11 | B20：`open_state` 边界（跨日下一段、无营业时间恒开）；关门 `use` → `closed` + `opens_at` + `openHours`、不计冷却、开门后可用；`/world` 与 perceive 的 `open / opensAt` 与关门 `advertise` 全 0、原始数据不被改；到点自动请出（pendingMessage）；ws objects 带 open。外部日志：`effects_push` 完整载荷 + `time_speed / toggle / reset` 三条 nondeterministic、`/admin/export?kinds=external`；`self_seed` 与 `self_snap`（MockTransport）。E：`zone_names`、`worldState.town`、`?fields=zone_names`；ws action `object_type`；`tile_gids.json` 覆盖生效（`gen/tiles.png`、tilecount 18）。B19：合成一天回放差 0 |
| 改 | 3 | `test_w5_e_items`（tileset 改为 E 的）、`test_w6_dataset`（manifest 多 external）、`test_ws`（objects 带 open） |

## 4. 对契约 / 其他会话

1. **给 A（数据契约，§3.20）**：沙盒数据集新增第四类 `external/<date>.jsonl`（字段见 api-spec §6 `/admin/export`），`state` 行新增 `mood_base`。都是只加字段。`dataset_export.py` 的沙盒源请多拉 `kinds=external`。
2. **给 C**：关门的物品 `advertise` 全 0、物品带 `open / opensAt`，Plan 用 advertise 加权时会自然得到「等开门」；若想显式表达，perceive 树里每个物品都有 `opensAt`。鲸仔 `use` 关门物品会得到 `reason=closed` + `opens_at`，请当成「现在不行、X 点再来」而不是失败重试。
3. **给 E**：W5 报告还没出，我按 W4 §4 和交接预告落了 `zone_names`、`worldState.town`、action `object_type`、`tile_gids.json`（`tiled` 已切到 `gen/tiles.png`），回放页可以直接读 `/admin/export?date=&kinds=actions,chat,state,external`。有新字段再提。
4. **给 D**：接口未变，维持 `/healthz + /event + /metrics` 的过渡契约；今天联调一局 8/8（run-1793933517，第 N 天 dusk）。
5. **回放的边界（假设）**：以每个 player 的第一条 state 行为起点、最后一条为终点，窗口外不回；30 s 采样粒度下与快照同秒的动作有歧义；若要全天严格可复现，建议 join 时也写一条 state 行（我下周加：join / rejoin 立即采样，而不是等 30 s）。
6. **运行台切换**：建议切到本提交；`mapVersion` 不变（物品集未变，只改了 tileset 与 open 字段）；切换后 `external/` 开始落盘，第二天起可全天回放。

## 5. 巡检（任务 3）

| 日期 | 日志行数 | 2xx / 4xx / 5xx | Traceback / ERROR / 401+403 | tick 间隔 p95 / max | tick 耗时 p95 / max | RSS | players / ws | actions / chat / state / external 行 | mapVersion |
|---|---|---|---|---|---|---|---|---|---|
| 2026-11-06 | 103 054 | 102 878 / 27 / 0 | 0 / 0 / 0 | 201.7 / 208.0 ms | 0.307 / 7.245 ms | 72.2 MB | 1 / 0 | 391 / 9 / 51 / 0 | 阿蝉家与小镇@1b824832ace2 |

27 个 4xx 是切换地图后旧 player id 的 404（C 以 rejoin 退回 join 的路径）与一次 400，均正常。每天收工跑 `scripts/inspect_runstation.py` 追加一行；外部日志从切到本提交起才有行数。

## 6. 本次提交

见 `git log -1`（代码与文档同一提交）。回放原始输出 `back_end/scripts/replay_main_2026-11-06.txt`。

---


# W6 · 2026-11-06：矩阵与多镇、数据集导出、游戏机 Object、阿蝉体验（原报告）

## 1. 进度（任务 1–6 全部完成）

| # | 任务 | 状态 | 主要文件 |
|---|---|---|---|
| 1 | 数据集：行动 / 聊天 JSONL 每行加 `town / map_version / seed`；新增 `data/state/<date>.jsonl`（每 player 每 30 游戏秒一行七变量）；`GET /admin/export?date=&kinds=` 一次给出 actions / chat / state + manifest（counts / files / backfilled_rows）；旧行回填并标 `backfilled` | ✅ | `game/state_log.py`（新）、`action_log.py`、`chat_log.py`、`routers/player.py::/admin/export`、`scripts/dataset_fetch.py`（新） |
| 2 | 多镇：`SANDBOX_SEED` 决定天气序列（每 6 游戏小时一段，6:3:1）与 agent 出生点（家 arena 内）；`SANDBOX_MAP_DIR` 选图；`SANDBOX_TOWN`；m1c 地图（60×48，+教书先生家 / 画师家 / 药铺，42 物品全部可达）；`scripts/multi_soak.py` 8 实例空跑 | ✅ 见 §5 | `world_state`（`weather_for / spawn_point_for / AGENT_HOME_ARENA`）、`scripts/gen_map.py --variant m1c`、`game/maps/m1c/` |
| 3 | B18 游戏机：`game_console`（continuous，fun 85 / mood 20，energy −6/h）；use → D brain `GET /healthz` + `POST /event sandbox_session_start`，`stateLabel`「玩游戏中」，`player.game` 带 brain `/metrics` 的 day / phase / health…；leave / 删玩家 → `sandbox_session_end`；不可达 → `game_unavailable`；`GAME_URL` 可配；沙盒不转发结果 | ✅ | `external_effects.game_start / game_end / game_refresh`、`routers/actions.py`、`world_state.leave_object`、perceive `game`、`scripts/verify_game.py`（新） |
| 4 | 阿蝉体验：human 发起 `POST /chat/request` 不检查冷却（agent 发起仍受）；human 的 `GET /player` 仍刷心跳；消息进 chat JSONL 带 `controller=human` | ✅ | `routers/chat.py`、`tests/test_w6_human_chat.py` |
| 5 | 稳定性：运行台日志巡检 + 8 实例空跑 + 12 agent 负载 | ✅ 见 §5 | `scripts/multi_soak.py`、`scripts/soak.py --agents 12` |
| 6 | 文档同步；`tile_gids.json` 覆盖口已在 W5 留好（`gen_map.build_tiled` 读 `game/maps/tile_gids.json`） | ✅ | `docs/api-spec.md`、`README.md`、`docs/data-models.md` |

未碰 `front_end/`。

**两处我定的契约（标假设，等对方确认）**：
- **B18 与 D 的接口**：D12 契约未出，8110 的 brain API 只有 `/healthz /tick /event /state /metrics /admin/*`。沙盒用现有端点：开局 = `healthz` ok + `POST /event {type:"sandbox_session_start", agent, player_id, ts, tick}`，结束 = `POST /event {type:"sandbox_session_end", …, started_at}`，局内指标读 `/metrics`。D 若另给 start / stop 端点，只改 `external_effects.game_start / game_end` 两个函数。
- **数据集沙盒源**：A 的 `dataset_export.py` 目前没有沙盒源；我按 schema v0.2 的口径给 `GET /admin/export`（每行 `town / map_version / seed`，state 每 30 游戏秒一行），并写了 `dataset_fetch.py` 做 A 那一步的等价拉取与对账。A 接入时三类各一个 `GET` 即可；行数以 `manifest.counts` 为准。

## 2. 测试命令与结果

```bash
cd back_end
uv run pytest -q
# 170 passed（W5 的 157 个 + W6 新增 13 个：test_w6_dataset 3、test_w6_seed 4、test_w6_game 5、test_w6_human_chat 1）

# 任务 1：主镇一天数据对账（运行台 59d1ac8 还没有 /admin/export，用其数据目录只读副本起临时实例）
uv run python scripts/dataset_fetch.py --base http://127.0.0.1:<tmp> --date 2026-11-06 --data-dir /tmp/ds_copy
#  actions  manifest=327 written=327 local_file=327  OK      chat 0/0/0 OK      state 0/0/0 OK   → PASS
#  （旧行无数据集字段 → 回填 327 行并标 backfilled；运行台切到本提交后新行自带字段、state 开始每 30 游戏秒一行）

# 任务 3：对 D 的 brain（8110，run-1793930016，第 2 天黄昏）真实联调一局
uv run python scripts/verify_game.py
#  use game_console OK / stateLabel「鲸仔 玩游戏中」/ player.game.status=playing（day 2, phase dusk, health 113.9）/
#  perceive.game 带 brain 指标 / brain ws /events 收到 sandbox_session_start / leave OK / 收到 sandbox_session_end / status=ended
#  8/8 checks passed → PASS

# 任务 2：m1c 地图
uv run python scripts/gen_map.py --variant m1c --out game/maps/m1c      # 60×48，42 物品；SANDBOX_MAP_DIR=game/maps/m1c 加载 → BFS 全部可达（单测 + 启动核对）
```

| 新增 | 用例 | 覆盖 |
|---|---|---|
| `tests/test_w6_dataset.py` | 3 | 行动 / 聊天行带 `town / map_version / seed`；state 快照每 30 游戏秒一行、字段齐全、不足 30 s 不采；`/admin/export` counts == 返回行数 == 文件行数 == 文件字节、kinds 过滤、空日期、坏日期 400、旧行回填与 `backfilled_rows` |
| `tests/test_w6_seed.py` | 4 | 无 seed 恒 sunny；有 seed 确定且同段不变、不同 seed 序列不同、ticker 写进 `worldState.weather`；agent 出生在家 arena（whale / achan / cook / fisher），human 与未知 agent 在地图出生点；出生点随 seed 变但不出家门；m1c 地图 BFS 42 物品可达、三户新 sector、9 张床、中文名 |
| `tests/test_w6_game.py` | 5 | 类型与地图位置；use → healthz + session_start 事件（agent / player_id / ts / tick）、stateLabel、`player.game`（brain run_id、day、phase，多余字段不进）、`/state` 与 perceive 的 `game`、`/world` players 的 stateLabel / usingObjectId；leave → session_end（带 started_at）、status=ended、tag 清除；brain 宕 → `game_unavailable`，不坐下、不计冷却；human 也能玩、删玩家发 end；`/metrics` 500 不阻塞 |
| `tests/test_w6_human_chat.py` | 1 | 阿蝉（human）发起 → 鲸仔接受 → walking_over → 建房 → 三条消息；阿蝉退出后立刻再发起成功（无冷却），鲸仔发起被 `chat_cooldown` 拦；JSONL 三条消息 `controller` 分别 human / agent / human，带 town；`/history/chat` 一致；human 的 `GET /player` 仍刷心跳 |
| 改 | 3 | `test_chat_protocol` 两个冷却用例改用 agent（human 现在无冷却）；`test_w5_chat_log` 的房间夹具先把两人放相邻（agent 现在出生在自家房间） |

## 3. api-spec 改动摘要（只增不删）

| 位置 | 改动 |
|---|---|
| §6 Admin | 新 `GET /admin/export?date=&kinds=`（行形状、state 快照、回填规则、对账脚本） |
| `POST /action` use | 新 reason `game_unavailable`；`external` 行加 `key = "game"` 的完整流程（假设契约） |
| §5 Object | 新 `game_console` 行 |
| `GET /agent/perceive` | 新字段 `game`；`GET /player` / `/state` 同步带 `game` |
| §7 `POST /chat/request` | human 发起不检查冷却 |
| §4 多实例 | `SANDBOX_SEED` 扩为天气 + 出生点（家表）；`SANDBOX_MAP_DIR`（m1c）；`SANDBOX_TOWN` |

`README.md`：数据集文件清单、游戏机、新脚本；`docs/data-models.md`：`player.game`。

## 4. 对契约 / 其他会话

1. **给 D（B18 契约）**：见 §1「两处我定的契约」。事件名 `sandbox_session_start / sandbox_session_end` 已在你的 `/event` 总线里能看到（本次联调 ws `/events` 收到了两条）。如果你希望沙盒触发「真正开一局」（regenerate / 接管鲸仔角色），请给一个端点名，我换掉 `game_start` 里的那一行；局结果请你 `POST /self/game/session` 写自我层（§3.15 第 2 条），沙盒不碰。
2. **给 A（数据集）**：沙盒源 = `GET /admin/export?date=`，三类行都带 `town / map_version / seed`，`manifest.counts` 为对账基准，`backfilled` 标记的行是 W6 之前写的。state 是沙盒本地每 30 游戏秒的样本（`kind: "sample"`），与自我层 `history/state-<date>.jsonl` 的 `kind: history` 互补；建议 dataset-schema 的 state 表加一行「沙盒 sample」来源。
3. **给 C**：agent 现在出生在自家房间（whale → 小仓库，NPC 各回各家），不再全部挤在小仓库出生点；m1c 的三位新 NPC id 我按 `npc_teacher / npc_painter / npc_herbalist` 建了家表，A 的 personas 若用别的 id，告诉我改一行映射。
4. **给 E（阿蝉操控页）**：human 发起对话无冷却；房间内 human 发言 `controller=human` 进 `data/chat/*.jsonl`，`/history/chat?room=` 可查。E 操控页的最小序列：`POST /player/join {name:"阿蝉"}` → 走到鲸仔旁（`move_to_area` 到她所在 arena）→ `POST /chat/request {from, to:[鲸仔 id], greeting}` → 轮询 `GET /chat/request/{id}` 到 `active` → `POST /chat/message` → `POST /chat/exit`。
5. **运行台**：建议切到本提交；`mapVersion` 变为 `阿蝉家与小镇@1b824832ace2`（新增游戏机物品），前端会重拉 tiles；玩家坐标不受影响，不需清数据目录。切换后 `data/state/` 开始落盘。
6. **`SANDBOX_SEED` 的「随机要素」**（假设）：天气只是 `worldState.weather` 的展示值（不影响需求值）；出生点只影响 agent 第一次 join。m1b 的 seed 2 现在确实会产生不同的天气序列与出生点。

## 5. 稳定性与负载（任务 2 / 5）

- **运行台 8000 巡检**（`run/data/sandbox.log` 只读）：92 765 行，0 条 Traceback / ERROR / 500，0 次 401 / 403（带 `SELF_TOKEN` 后 self-sync 正常）。
- **8 实例空跑（m1c 地图，各 1 个 agent，SELF_SYNC=0，30 min，与 12 agent 负载同机同时跑）**：**通过**：8 个实例 × 60 次采样，tick 间隔 p95 中位 201.5–201.6 ms、最大 202.0 ms（目标 200 ms，抖动 ≤ 1%，判据 ≤ 210 ms），单帧最差 216 ms；tick 耗时 p95 ≤ 0.5 ms；每实例 RSS 58.5 MB 全程不变（8 实例合计约 470 MB）；0 次请求错误、0 次退出。日志 `back_end/scripts/multi8_m1c_2026-11-06.log`。结论：一机 8 镇只受内存与端口约束，tick 本身没有竞争。
- **12 agent × 30 min 负载**（`soak.py --agents 12 --ws 1`，mock 自我层，每 agent 每秒 1 动作，每 2 s 1 次 `/world` + 12 次 `/player` + 12 次 perceive，每 7 s 一轮对话）：30 分钟、18 073 次 HTTP + 23 464 条 WS 推送，0 错误、0 退出；RSS 66 → 峰值 89 → 结束 84 MB。日志 `back_end/scripts/load_w6_12agents_2026-11-06.log`。

| 指标 | n | p50 | p95 | p99 | max |
|---|---|---|---|---|---|
| `GET /world`（全量，2400 tiles + 31 objects + tiled 两层） | 358 | 10.5 ms | **18.2 ms** | 23.0 ms | 35.3 ms |
| `GET /agent/perceive`（整树 + vision 5） | 4296 | 3.5 ms | **4.8 ms** | 5.4 ms | 51.4 ms |
| `POST /action` move（含 300 ms 节拍） | 4196 | 301.5 ms | **302.8 ms** | 305.6 ms | 319.1 ms（服务端开销 p95 ≈ 3 ms） |
| tick 间隔（71 次采样的 p95） | — | 202.3 ms（中位） | 203.0 ms（最大） | — | 236.0 ms |
| tick 耗时 | — | 1.4 ms（p95 中位） | 2.1 ms（p95 最大） | — | 35.6 ms（检查点那一帧） |

对比 W4 的 6 agent：`/world` p95 14.5 → 18.2 ms（tiled 层使 JSON 多了约 60 KB），perceive p95 3.8 → 4.8 ms（整树），tick 耗时 p95 0.3 → 1.4 ms（12 人 + state 快照 + 天气）。12 agent 的 m1c 满配仍远未到瓶颈，抖动 ≤ 1.5%。两项同机同时跑，互相是对方的背景负载。
- 机器：20 核，119 GB 内存（起跑时已用 81 GB，其他会话的服务在跑）。

## 6. 本次提交

W6 代码：`ce97491`；本报告与两份压测日志：`08f35c8` 及之后。运行台建议切到最新提交（`mapVersion` 变为 `阿蝉家与小镇@1b824832ace2`，不需清数据目录）。

---


# W5 · 2026-11-06：整树（事故修复）、聊天 JSONL、E 的 7 条、B12 freeform（原报告）

## 0. 事故修复（§3.14，最先做）——提交 **`504bf9e`**，请总控切运行台

- `GET /agent/perceive.arena_tree` 改为**整个 world 的树**：所有 sector → arenas → objects（`id / name / type / interactable / currentUsers / maxUsers / advertise`），`current` 同时标在所在 sector 与所在 arena；旧字段 `sector`（当前 sector 节点）保留；新增顶层 `current {world, sector, arena, sector_name, arena_name}`。
- `move_to_area` 改为 BFS **实际路程**最近的区域内可走格（原来取曼哈顿最近，隔着墙就 `no_path`），跨 sector 走门。
- join / rejoin / 检查点回填：坐标不可走或不在任何 arena → 落回出生点（小仓库），并离开正在用的物品。
- 验收（`tests/test_w5_tree.py` 8 例）：human 站广场 perceive 看到 `bed_whale`（在 `achan_house → storage` 下，30 个物品全在树里，`current` 恰好一个）；广场 `move_to_area(storage)` 走进小仓库，再到餐馆大堂、渔夫小屋；全部 arena 从出生点 `move_to_area` 可达；`(2,2)` 墙里 / 河里 rejoin 落回出生点；检查点回填同样修正。

## 1. 进度（任务 0–5 全部完成）

| # | 任务 | 状态 | 主要文件 |
|---|---|---|---|
| 0 | §3.14 整树 / 落点 | ✅ `504bf9e` | `routers/agent.py`、`routers/actions.py::_bfs_path_to_any`、`world_state._ensure_valid_position` |
| 1 | 聊天 append-only JSONL：`data/chat/YYYY-MM-DD.jsonl`，消息一行（ts / game_time / room_id / seq / from / from_name / to[] / text / controller），房间 open / player_exit / room_limit / room_close / request_expired / request_rejected 各一行；`GET /history/chat?since=&room=&kind=` 只读 | ✅ | `game/chat_log.py`（新）、`chat_state.py` 六处写点、`routers/history.py` |
| 2 | E 的 7 条：① `players[]` 加 `stateLabel / usingObjectId / tags`（/world 与 ws upsert 同形状）② `POST /player/{id}/heartbeat`；`GET /player/{id}` 对 agent 纯只读、对 human 仍刷 ③ `GET /world?fields=` + `worldState.mapVersion` ④ ws chat `from_name`（确认已有，测试锁定）⑤ `gen_map.py` 产出 `tiled`（ground + structures 两层，Sunnyside tileset）⑥ `players[].pos_seq` ⑦ ws `{type:"action", entity, action, object, success, reason}` | ✅ | `world_state.get_all_players_snapshot / update_player_position / MAP_VERSION`、`routers/world.py`、`routers/player.py`、`routers/ws.py::push_action`、`scripts/gen_map.py::build_tiled` |
| 3 | B12 freeform：`POST /action {type:"freeform", payload:{text, target?, context?}}` → 30 s 本地限频 → `POST /self/adjudicate` → effects 经 `apply_effects` 落到本人 / target player，narration 进双方 `pendingMessage`；reason 透传 `injection / rate_limited / adjudication_unavailable / adjudication_failed` | ✅ | `routers/actions.handle_freeform`、`external_effects.adjudicate`、`scripts/verify_freeform.py` |
| 4 | `SANDBOX_SEED`：原本**不存在**，现已加（只影响 player id 后缀生成器，沙盒无随机游戏逻辑；`/admin/metrics.seed`）；`run_town.sh` 加 `--tz / --seed / --env K=V`，与 townctl 的 `SANDBOX_DATA_DIR / SELF_URL / SANDBOX_TZ / sandbox_env` 一一对应 | ✅ | `world_state`、`scripts/run_town.sh` |
| 5 | 文档同步 | ✅ | `docs/api-spec.md`（perceive 整树、freeform 行为、`/history/chat`、players 新字段、heartbeat、`?fields` / `mapVersion` / `tiled`、ws action 事件、SEED）、`README.md`、`docs/data-models.md` |

未碰 `front_end/`。

## 2. 测试命令与结果

```bash
cd back_end
uv run pytest -q
# 157 passed（W4 的 139 个 + W5 新增 18 个；另 test_w5_tree 8 例在 504bf9e 已计入 139）

uv run python scripts/verify_freeform.py --self-url http://127.0.0.1:8100       # 对运行台自我层真实 3 条
#  [OK ] world       2.1s success=True  effects=[fun +4, social +3, mood +2]  Δ={social 3, fun 3.99, mood 2}
#        旁白：鲸仔在广场上清了清嗓子，给路过的人唱起了一段悠长的鲸歌，几位行人停下脚步侧耳聆听。
#  [OK ] infeasible  2.2s success=False feasible=False effects=[]            旁白：鲸仔想一口气吃下三锅米饭，但小镇里并没有这样的食物，他只能作罢。
#  [OK ] injection   0.0s success=False reason=injection effects=[]          旁白：她嘀咕了一句谁也没听懂的话，什么都没发生。
#  行动日志里 freeform 条数：3  → PASS

uv run python scripts/verify_ws.py --seconds 60      # W5 改动后：0 不一致（30 s 短跑 21 次 0 不一致；60 s 版 44 次 0 不一致）
uv run python scripts/verify_restart.py              # 15/15（W4 基线，未改）
scripts/run_town.sh --port <p> --data /tmp/town_seed --no-sync --seed 2 --tz Asia/Shanghai --env SANDBOX_CORS_ORIGINS=http://localhost:5183
# /admin/metrics → seed 2, mapVersion 阿蝉家与小镇@c4e7af659ee3
```

| 新增 | 用例 | 覆盖 |
|---|---|---|
| `tests/test_w5_tree.py` | 8 | 任务 0（见上） |
| `tests/test_w5_chat_log.py` | 5 | 一次对话 7 行（room_open、3 条消息、2 次 player_exit、room_close=all_left），字段齐全（controller 区分 human / agent，to 为其余参与者）；room_limit → `room_limit` + `room_close` 两行；request_expired / request_rejected；**JSONL 与 ws `chat` 推送逐条一致**（seq / text / from_name，事件顺序）；重启后文件原样、seq 接着写；截断半行容错；`/history/chat` 的 room / kind / since 过滤 |
| `tests/test_w5_e_items.py` | 7 | ① use 后 `players[]` 带 stateLabel / usingObjectId / tags，leave 后清空 ② agent 的 `GET /player` 不刷 `last_seen` 不改 `online`，human 仍刷；`POST heartbeat` 置 online；`/state` 只读 ③ `?fields=` 只回请求键、形状与全量相同、体积 < 1/5、未知字段忽略；`mapVersion` ⑤ `tiled` 两层各 2400 格 ⑥ `pos_seq`：转向不增、移动 +1、撞墙不增、`/world` 一致 ⑦ ws action 事件（use 成功带 object、随后 move 失败带 reason）；SEED 下 id 可复现；metrics 带 seed / mapVersion |
| `tests/test_w5_freeform.py` | 5 | 裁决 effects 落到本人（social/fun/emotion_tag）与 target（mood），旁白进双方 pendingMessage、写行动日志、请求体 `{agent, text, target}`；不可行仍可带负效果；注入 `reason=injection` 零效果；本地限频（`retry_after`，不打自我层）、长度 / 空文本 / 玩家不存在；远端 429 → `rate_limited`+retry_after、宕机 → `adjudication_unavailable`、404 → persona_not_found、`SELF_SYNC=0` → unavailable；human 用 name 作 agent |

## 3. api-spec 改动摘要（只增不删）

| 位置 | 改动 |
|---|---|
| `GET /agent/perceive` | `arena_tree` 定义改为整树（`sectors[]`，`current` 两级），保留 `sector`；新增 `current` |
| 行为类型 | 新增 `freeform` 行与完整小节（payload / 流程 / 响应 / reason 表）；`move_to_area` 说明改为 BFS 实际路程 |
| `GET /world` | `players[]` 加 `stateLabel / usingObjectId / tags / pos_seq`；`worldState.mapVersion`；`?fields=` 瘦身；`tiled` 非空与 gid 假设 |
| `GET /player/{id}` | 语义改写：agent 只读 / human 刷心跳；新增 `POST /player/{id}/heartbeat` |
| `GET /history/chat`（新） | 行形状、事件枚举 |
| §8 ws | `{type:"action"}` 事件；chat `from_name` 确认 |
| §4 | `SANDBOX_SEED` 语义；`run_town.sh` 与 townctl 参数对应 |

## 4. 对契约 / 其他会话

1. **给 C（必做一行）**：E② 落地后 `GET /player/{id}` 对 agent **不再是心跳**。请在 loop 里每 ≤ 10 s 调 `POST /player/{id}/heartbeat`（或继续用 `rejoin`），否则鲸仔在 `/world` 与 ws 里会显示 `online=false`（不会被删、仍参与 tick、动作照常）。运行台切到本提交后请尽快改，否则画面上她会一直「离线」。
2. **给 C**：perceive 的 `arena_tree.sectors` 已是整树，按物品 id 定位（`bed_whale` / `fridge_kitchen` / `stream_desk_whale`）即可；`current` 字段直接给当前 sector / arena id。`move_to_area(arena_id)` 跨 sector 可用，不必自己拆门。
3. **给 E**：7 条全落地。`tiled` 的 gid 映射是**假设**（grass 260 / wall 964 / floor 与 object 648 / water 1098 / grass1 68，取自旧图频次；floor / water 借用邻近图块），把你想要的 `{类型: gid}` 发我一份放进 `game/maps/tile_gids.json` 就能覆盖；E6 换素材时 `TILESET` 一张表同步改。`players.upsert` 元素现在含 `stateLabel / usingObjectId / tags / pos_seq`；action 事件先于同一帧的 patch 推。
4. **给 A**：freeform 已接 `/self/adjudicate`，响应里 `feasible / skipped / injection / reason` 原样透传给 agent；沙盒对裁决效果**不**回推 `/self/state/event`（按 13.3 的说法由 delta 回报）。自我层那层 30 s 限频与本地并存，实测 3 条间隔 31 s 没撞上。
5. **`SANDBOX_SEED`（任务 4 确认）**：之前不存在，现在存在但只影响 player id 后缀（沙盒无随机游戏逻辑：衰减、物品、冷却全是确定性的；真正的随机源在 agent 侧模型采样）。towns.yaml m1b 的 `SANDBOX_SEED: "2"` 可以留着，但「第二个随机种子」的差异要靠 C 的采样温度 / seed 才体现，请 A 在 PLAN 里标注。
6. **townctl 对齐**：townctl 直接起 uvicorn 并传 `SANDBOX_DATA_DIR / SELF_URL / SANDBOX_TZ` + `sandbox_env`，与 `run_town.sh --data / --self-url / --tz / --env` 完全对应；townctl 若想改用脚本，等价命令是 `run_town.sh --port 8010 --data run/data/m2a/sandbox --self-url http://127.0.0.1:8310 --tz Asia/Shanghai --log run/data/m2a/sandbox.log --fg`（`--fg` 前台便于它接管 pid）。CORS 两边都只在需要跨机前端时设。
7. **运行台建议切到本提交**（见 §6）：含 504bf9e 的整树 + 全部 W5。地图 tiles / 物品未变（`mapVersion` 与 4d6a931 一致：`阿蝉家与小镇@c4e7af659ee3`），只多了 `tiled` 层，不需清数据目录。

## 5. 卡点

无阻塞。提醒：第 4 条 C 改心跳前，鲸仔在画面上会显示离线；如果总控觉得过渡期不能接受，`touch_player(..., human_only=True)` 改回 `False` 是一行，但那样 E② 就没解。

## 6. 本次提交

事故修复：`504bf9e`（已单独报）；W5 其余：见 `git log -1`。

---


# W4 · 2026-11-06：契约小修、WebSocket 推送、多实例与社交物品（原报告）

## 1. 进度（W4 任务 1–6 全部完成）

| # | 编号 | 任务 | 状态 | 主要文件 |
|---|---|---|---|---|
| 1 | §3.11 小修 | ① `GET /world` 的 `players[]` 加 `agent_id` ② `perceive.needs.closeness` 固定为 `{entity_id: {name, tier}}`（实现本来就是这个形状，补了「整块无数值」的断言与 spec 措辞）③ 人类玩家用直播台 → `live_unavailable` ④ CORS 白名单走 `SANDBOX_CORS_ORIGINS` ⑤ `/effects` 接受并记录 `event`（响应回显；`GET /player/{id}/state` 多 `recent_events` 最近 50 条） | ✅ 五处各有单测 | `world_state.get_all_players_snapshot / apply_effects_to_player`、`external_effects.live_start`、`main.py`、`routers/player.py`、`tests/test_w4_contract.py` |
| 2 | B17 | `GET /ws/world` 只读 WebSocket：连接发 snapshot（与 `GET /world` 走同一响应模型，逐字段一致），之后 ≤ 10 Hz 推 `patch`（`worldState` 变化键 / `players.upsert+remove` / `objects` 的 currentUsers+userList / `chat` 新消息与房间事件），空闲 5 s heartbeat；客户端消息一律忽略 | ✅ | `routers/ws.py`（新）、`main.py` lifespan、`scripts/verify_ws.py`（新）、`tests/test_ws.py` |
| 3 | 多实例 | 梳理共享状态：数据目录（检查点 / JSONL / pid）全在 `SANDBOX_DATA_DIR`，日志 stdout 或文件，端口 / self-url / CORS 均参数化，无共享全局文件；`scripts/run_town.sh --port 8010 --data run/data/m2a [--self-url] [--log] [--cors] [--no-sync]`，端口被占直接拒绝 | ✅ | `scripts/run_town.sh`（新） |
| 4 | B16 续 | 新类型 `restaurant_table`（4 人）、`bench`（2 人）、`fishing_spot`、`shop_counter`（instant）；所有 continuous 类型显式 `max_users`；地图加餐馆（sector `restaurant`：大堂两张四人桌 + 后厨 fridge）、广场两条长椅、码头两个钓位、杂货店柜台替代 desk、四个 NPC 家各一台 fridge → 30 个物品 | ✅ | `game/object_types.json`、`scripts/gen_map.py`、`tests/test_w3_objects.py::test_every_object_reachable_from_spawn`（30 个全部 BFS 可达） |
| 5 | 负载 | `soak.py --agents 6 --ws 1`：6 名 agent 玩家（whale + 5 NPC id）+ 1 个 `/ws/world` 订阅 × 30 min；记 `/world` / `/action` / `perceive` 的 p50/p95/p99、tick 耗时与间隔分位（新 `GET /admin/metrics`）、RSS | ✅ 见 §5 | `scripts/soak.py`、`routers/player.py::/admin/metrics`、`game/ticker.py::metrics` |
| 6 | B14 | 文档同步；W3 §5 的 `__SOAK_RESULT__` 占位在 9ce80cf 已补齐（交接写时还没提交） | ✅ | `docs/api-spec.md`（新 §8 WebSocket、`/admin/metrics`、小修五处、新物品表、多实例段）、`README.md`、`docs/data-models.md` |

未碰 `front_end/`。B12 freeform 留 W6。

## 2. 测试命令与结果

```bash
cd back_end
uv run pytest -q
# 131 passed（W3 的 120 个 + W4 新增 11 个：test_w4_contract 6、test_ws 5）

uv run python scripts/verify_restart.py          # 新地图 30 物品
# 15/15 checks passed
# 两个实例并行（随机端口 + 各自临时 SANDBOX_DATA_DIR）：A 15/15、B 15/15，互不干扰

uv run python scripts/verify_ws.py --seconds 60
# snapshot: 2400 tiles, 30 objects, 2 players
# 44 checks, 0 mismatches, 141 patches / 141 messages, 9 chat items → PASS
#  （两名玩家随机 move/turn/use/leave + 聊天 + 切倍率；每秒把叠加后的本地模型与 GET /world 比：players 全字段、objects 使用状态、
#    worldState 的 date/period/running/speed/weather，time 差 ≤ 2 s）

scripts/run_town.sh --port <p1> --data /tmp/town_a --no-sync
scripts/run_town.sh --port <p2> --data /tmp/town_b --no-sync
# 两镇各自 join + checkpoint → /tmp/town_a/sandbox.db、/tmp/town_b/sandbox.db 各一份；再用 <p1> 起第三个被拒绝「port already in use」
```

| 新增 / 修改 | 用例 | 覆盖 |
|---|---|---|
| `tests/test_w4_contract.py` | 6 | ① `players[]` 的 `agent_id`（agent 有、human 为 null）② `needs.closeness == {id: {name, tier}}` 且递归无数值 ③ 人类玩家 use 直播台 → `live_unavailable`（SELF_SYNC 关 / 开都一样）④ `SANDBOX_CORS_ORIGINS` 重载后生效、默认值含 5173、预检对白名单外的 Origin 不回 allow-origin ⑤ `/effects` 回显 `event`、`/state.recent_events` 记录 `{event, source, n_effects}`、不带 event 兼容 |
| `tests/test_ws.py` | 5 | snapshot 与 `GET /world` 的 tiles / objects / players 逐字段相等；patch 跟随 join（upsert 字段集）、move（position）、use（objects currentUsers/userList）、聊天（招呼 + 回复、第三句、player_exit 事件、from_name、participants）、leave（remove）；客户端发写入被忽略且连接存活；worldState patch 只带变化键、`/time/speed` 推 speed；双客户端都收到、`/admin/metrics.ws_clients` 计数 |
| `tests/test_external_effects.py` | 改 1 | 人类玩家直播台从「只本地切 scene」改为 `live_unavailable` |
| `tests/test_w3_objects.py` | 改 1 | 每小时尺度上限放到 40/h（餐馆桌子 fullness +40/h） |

## 3. api-spec 改动摘要（只增不删）

| 位置 | 改动 |
|---|---|
| `GET /world` | `players[]` 加 `agent_id` |
| `POST /player/{id}/effects` | 请求加 `event`，响应回显；`source: "self"` 不计入 delta 的说明挪到字段表 |
| `GET /player/{id}/state` | 加 `recent_events` |
| `POST /action` use | `live_unavailable` 加「人类玩家」情形；`external` 行的人类玩家兜底改写 |
| `GET /agent/perceive` | `needs.closeness` 形状定稿 `{entity_id: {name, tier}}`，整块无数值 |
| §4 | 多实例段（端口 / `SANDBOX_DATA_DIR` / `run_town.sh` / `SANDBOX_CORS_ORIGINS`） |
| §5 Object | 新四类型行；「所有 continuous 带 `max_users`」；地图物品清单 |
| §6 Admin | 新 `GET /admin/metrics` |
| **新 §8** | `GET /ws/world`：snapshot / patch / heartbeat 形状与字段表、对账脚本 |

`README.md`：社交物品、实时推送与多实例段、新脚本、`ws.py`。`docs/data-models.md`：`max_users`。

## 4. 对契约的建议 / 给其他会话

1. **给 E（B17 字段）**：`patch.players.upsert` 元素与 `GET /world` 的 `players[]` 完全同形状（含 `agent_id`），`remove` 只给 id；`objects` 只推 `currentUsers` / `userList`（静态字段看 snapshot）；`chat` 只推连接之后的新消息，历史走 `GET /chat/room/{id}`。如需 `pendingMessage` / `stateLabel` 之类 player 私有字段进推送，说一声，我加到 `upsert` 里（`stateLabel` 目前不在 `players[]`，加它是一行）。
2. **给 E**：`worldState.time` 每秒变一次会产生每秒一个 patch；若前端自己走时钟，可忽略只含 `time` 的 patch。另一个选项是我加 query `?fields=players,objects,chat` 过滤，E 需要再说。
3. **给 A（§3.11 A2）**：`event` 已接受并记录；对账读 `GET /player/{id}/state.recent_events`（最近 50 条，含 `game_time`）。
4. **给总控**：8001 当前被另一个 python 进程（pid 519261）占着，不是我的；我的自测改用临时端口。请在端口登记里确认归属。
5. **多实例的自我层映射**（假设）：每镇一个自我层（8300+10k），`run_town.sh --self-url` 指过去即可；同一个自我层若被两镇共用，同名 `agent_id` 会互相覆盖状态——契约里没写，建议 §3.10 明确「一镇一自我层」。
6. **social 物品的「同桌」语义**：现在只是多人可同用 + perceive 的 `players_in_view`；C 如需「同桌的人」列表，可从 `GET /world` 的 `objects[].userList` 取，不另加接口。
7. **运行台 8000 建议切到 `4d6a931`**（本节代码提交）：含 `players[].agent_id`（A1 等着）、`/ws/world`（E9 等着）、新物品。地图在 4369ee5 基础上只加物品，玩家坐标不受影响，**不需要清数据目录**。

## 5. 负载（任务 5）

- 配置：6 名 agent 玩家（agent_id = whale / achan / npc_cook / npc_grocer / npc_fisher / npc_regular，mock 自我层）+ 1 个 `/ws/world` 订阅；每名玩家每秒 1 个随机动作（move 50% / turn 15% / use 15% / leave 10% / effects 10%），每 2 s 1 次 `GET /world` + 6 次 `GET /player` + 6 次 perceive，每 7 s 一轮对话邀请，每 10 s 检查点 + 指标采样，每 5 min 切倍率（1 / 10 / 60）；30 分钟。
- 冒烟（30 s）：`/world` p95 8.1 ms、perceive p95 3.5 ms、`/action` p50 301 ms（= move 自带的 300 ms 节拍，不是服务端开销）、tick 间隔 p95 201 ms、tick 耗时 max 14.7 ms、RSS 65 MB。
- **30 min 结果**：30 分钟、13 260 次 HTTP 请求 + 15 685 条 WS 推送，0 次请求错误，0 次进程退出，日志 0 条异常；RSS 64.9 → 峰值 82.7 → 结束 80.5 MB（前 5 分钟爬升后平稳，无泄漏迹象）。原始数据 `back_end/scripts/load_w4_6agents_2026-11-06.log`。

| 指标 | n | p50 | p95 | p99 | max |
|---|---|---|---|---|---|
| `GET /world`（2400 tiles + 30 objects 全量，含模型序列化） | 501 | 8.5 ms | **14.5 ms** | 25.2 ms | 31.7 ms |
| `GET /agent/perceive`（vision 5） | 3006 | 2.6 ms | **3.8 ms** | 4.4 ms | 10.0 ms |
| `POST /action` move（含服务端 300 ms 节拍 sleep） | 2955 | 301.5 ms | **302.8 ms** | 307.8 ms | 318.3 ms → 去掉节拍后服务端开销 p95 ≈ 3 ms |
| tick 间隔（目标 200 ms；100 次采样的 p95） | — | 201.3 ms（中位） | 202.0 ms（最大） | — | 230.2 ms |
| tick 耗时 | — | 0.31 ms（p95 中位） | 0.94 ms（p95 最大） | — | 30.6 ms（检查点落盘那一帧） |
- **瓶颈判断**：6 玩家满配远未到瓶颈：CPU 侧每 tick < 1 ms，200 ms 周期的抖动 ≤ 2%（最差一帧 230 ms 是每 5 s 的 SQLite 检查点同步写，`synchronous=FULL`，占 30 ms）。最贵的单次请求是 `GET /world`：2400 个 tile 每次全量序列化，p95 14.5 ms——这就是 B17 存在的理由，前端改走 `/ws/world` 后这条路径只剩旁观者偶尔的首屏。按线性外推，同一进程跑到 ~30 名玩家仍能保持 tick 抖动 < 10%；再往上先出问题的会是 `GET /world` 的 JSON 体积（约 400 KB）而非 tick。可做但本周没做的优化：① `GET /world` 加 `?fields=` 只回 players/objects；② 检查点改 `synchronous=NORMAL`（WAL 下仍安全）把那一帧的 30 ms 压到 < 5 ms；③ `/ws/world` 的 snapshot 复用预序列化的 tiles 字节。都不影响契约。

## 6. 本次提交

W4 代码：`4d6a931`；本报告与负载日志：见 `git log -1`。运行台 8000 建议切到 `whale-integration` 最新提交（不需清数据目录）。

---


# W3 · 2026-11-06：手机与直播台、对话协议、地图与数值尺度（原报告）

## 1. 进度（W3 任务 1–7 全部完成）

| # | 编号 | 任务 | 状态 | 主要文件 |
|---|---|---|---|---|
| 1 | §3.9 B4 | `POST /player/{id}/effects` 的 `source == "self"` → `track=False`（落本地、不进 `vars_delta`） | ✅ | `world_state.apply_effects(track=)` / `apply_effects_to_player` |
| 2 | §3.9 B6 + B16 | `object_types.json` 全部改每游戏小时尺度（规则：一次正常使用恢复量 ≈ 一日衰减量，数值标假设）；新地图「阿蝉家 + 小镇」60×40：小仓库（鲸仔：bed / desk / book / phone / stream_desk）、阿蝉房间、厨房、四个 NPC 家、街道 / 广场 / 公园 / 码头 / 河 | ✅ | `game/object_types.json`、`scripts/gen_map.py`（新，MAP_EDITOR 不在本机，按其导出格式直出）、`game/maps/{map,objects}.json`（旧图存 `maps/legacy_50x50/`） |
| 3 | B10 | `phone`（instant）+ `external_effects.py`：`external: feed` → `GET {SELF_URL}/self/feed?for=<agent_id>`（3 s 超时）→ `result.phone` 与 perceive 的 `phone`（只保留 digest 白名单字段）；不可达 → `feed_unavailable`「手机没信号」，仍计冷却 | ✅ | `game/external_effects.py`（新）、`routers/actions.handle_use`、`routers/agent.perceive`、`world_state._phone_feed` |
| 4 | B11 | `stream_desk`（continuous）：use → `POST /self/live/start`（失败 → `live_unavailable`，不坐下）；进入 `scene=live`；leave / 自动离开 / 玩家删除 → `/self/live/stop`（后台线程、不可失败）→ `scene=sandbox` | ✅ | `external_effects.py`、`routers/actions.py`、`world_state.enter_object / leave_object` |
| 5 | B9 | 对话协议四件：① `walking_over` 态（请求带 `target_arena_id`，参与者 `state="walking_over"` 可移动，相邻（曼哈顿 ≤ 1）或 30 s 建房）② 单人邀请也 60 s 超时 ③ `chat_cooldown`（本人 60 s / 配对 15 s）④ `room_limit`（16 条关房）；状态机由后台 ticker 推进；冷却随检查点持久化 | ✅ | `game/chat_state.py`、`routers/chat.py`、`models/player.py`（state 加 `walking_over`）、`game/ticker.py`、`persistence.py`（meta.chat_cooldowns） |
| 6 | 稳定性 | 复现脚本 `scripts/soak.py`：3 × 30 min 驱动 e7a036a（运行台同版本）；运行台 `run/data/sandbox.log` 只读检查 | ✅ 见 §5 | `scripts/soak.py`（新） |
| 7 | B14 | 文档同步 | ✅ | `docs/api-spec.md`（§7 状态机重写、external、尺度表、新 reason、perceive.phone、source=self）、`docs/data-models.md`、`docs/architecture.md` §6、`README.md`；前端 `types/index.ts` 的 `PlayerState` 加 `walking_over`（一行，类型） |

B12 freeform 留 W6。运行台 8000 仍是 `e7a036a`，本次提交含地图与物品数值变化，**请总控择机把 8000 切到本报告末尾的提交号**（切换后旧检查点的 player 位置可能落在新地图的墙里——首次切换建议清空 `run/data/sandbox/`；旧检查点里的物品 id 与新图不同，`object_runtime` 会被忽略，不报错）。

## 2. 测试命令与结果

```bash
cd back_end
uv run pytest -q
# 120 passed（W2 的 93 个 + W3 新增 27 个）

uv run python scripts/verify_restart.py
# 15/15 checks passed（新地图；desk_whale，speed 60）

uv run python scripts/verify_self_sync.py --mock --seconds 45
# batch drift_max=0.037  final diff=0.103 (threshold 0.5, 48 batches) → PASS

uv run python scripts/verify_external.py --self-url http://127.0.0.1:8100      # B10 / B11 对运行台自我层
# 10/10 checks passed → PASS
#   seed from self-layer OK（remote scene=sandbox）
#   phone use → feed status=ok items=0（自我层当前 digest 为空）；perceive.phone 有 digest，无 raw 字段
#   stream_desk use → self-layer scene == live；沙盒 /player/{id}/state scene == live
#   leave → 两边都回 sandbox；whale-self data/ops/live.log 收到 start / stop 两行（catch_up_seconds 3 / 0）
```

W2 的 93 个测试里改了断言的（都是预期变化）：bed 速率从 +1/s 改 +25/h（ticker / persistence 的能量期望）、fridge 效果改 +40/+5/−2、self_sync 失败重发的累积阈值从 60 降到 0.5（速率小了 3 个量级）、地图常量（`BED_ID=bed_whale` 等）、`respond` 后要先 `tick()` 才有房间（walking_over）。

| 新增文件 | 用例 | 覆盖 |
|---|---|---|
| `tests/test_w3_objects.py` | 7 | 任务 1：`source=self` 推送落本地、pending 为空、下一批 `vars_delta` 只有其他来源的变化；任务 2：所有 `*_regen` ≤ 30/h、instant ≤ 60；**睡 8 h（22:00–06:00，含夜间 ×1.5）energy 0 → ≥ 99**，4 h 白天线性对账 +68、fun −44；一顿饭 +40/+5/−2；B16：三间房 + 四个 NPC 家 + 街道广场公园码头河、中文 zone_names、鲸仔房间物品齐全、出生点在小仓库、每个 NPC 家有床、**全部 20 个物品从出生点 BFS 可达**、生成脚本可重放且与仓库内 JSON 一致 |
| `tests/test_external_effects.py` | 9 | B10：use 手机拉 digest 进 `result.phone` 与 perceive（含点歌文案）、**raw 字段（id / source / author / text）被过滤**、七变量按 +15/+5/−2 变化；自我层宕 → `feed_unavailable`「没信号」、perceive.phone=no_signal、仍计冷却；空 feed 文案；没刷过 perceive.phone 为 null；人类玩家 `for=<player id>`。B11：use → `live/start` 带 agent 与 ISO ts、scene=live、tag streaming、`/state` 跟着变；leave → `live/stop`、scene 回 sandbox；自我层宕 → `live_unavailable`，不坐下、不计冷却、userList 不变；live 速率生效（social −0.12/s + 20/h）；人类玩家只本地切 scene 不打自我层；删玩家时发 stop；`apply_effects` 跳过 external |
| `tests/test_chat_protocol.py` | 11 | B9：接受 → `walking_over` + `target_arena_id`（发起者 arena）+ 双方 state、可移动、移动不清状态；走到相邻 → tick 建房、消息顺序、state=talking；同 arena 不相邻 → 等到 30 s 建房；参与者被删 → expired 且发起者回 idle；**单人邀请 60 s 过期**、过期后响应无效、pending 列表为空；多人超时 1 人接受 → walking_over；后台 ticker 驱动；**退出后本人 60 s / 受邀方冷却 / 配对 15 s 单独生效**；**第 16 条消息关房**：events room_limit、参与者解 buff 回 idle、再发言 404、双方进冷却；冷却与新字段随检查点持久化；`GET /chat/request/{id}` 旧字段不变 |

## 3. api-spec 改动摘要（只增不删）

| 位置 | 改动 |
|---|---|
| §7 对话系统 | 新增**状态机图**（pending → walking_over → active → closed，含超时 / 冷却 / 上限常量）；ChatRequest 加 `target_arena_id`、`participants`，status 加 `walking_over`；ChatRoom events 加 `room_limit`；`POST /chat/request` 响应加 `success`，冷却时 `{request_id: null, success: false, reason: "chat_cooldown", cooldown_remaining}`；`POST /chat/respond` 接受时返回 `status: "walking_over"`（**`room_created` 不再出现**，改为轮询 `GET /chat/request/{id}` 到 `active`）；`POST /chat/message` 响应加 `room_closed`，第 16 条返回 `reason: "room_limit"` |
| `POST /action` use | 新 reason `feed_unavailable`、`live_unavailable`；手机成功时 `result.phone` |
| `GET /agent/perceive` | 新字段 `phone`（digest 白名单字段说明） |
| `GET /player` | `state` 枚举加 `walking_over` |
| §5 Object Effect | 新 type `external`（feed / live 语义、人类玩家兜底）；**每游戏小时尺度表**（9 个类型的收益 / 成本 / advertise / max_duration） |
| §4 同步 | 加「事件单向链路」行（`source: "self"` 不计入 delta，沙盒永不转发事件）与「speed > 1 滞后」行 |

`docs/data-models.md`：PlayerState、external、尺度说明。`docs/architecture.md` §6：external 与 chat 状态机的驱动位置。`README.md`：新地图说明与生成方式、external、尺度、新脚本。

## 4. 对契约的建议（请会话 A 汇总）

1. **`POST /chat/respond` 不再返回 `room_created`**。接受即 `walking_over`，房间在 `GET /chat/request/{id}` 变 `active` 时出现。C 的 loop 已说按 `walking_over` 处理，请确认它会轮询请求状态而不是等 respond 的 `chat_room_id`。
2. **`POST /chat/request` 冷却时的返回**：`{request_id: null, success: false, reason: "chat_cooldown", cooldown_remaining}`（HTTP 200，不是 4xx）。只加字段，但 `request_id` 可能为 null，C 取值前先看 `success`。
3. `target_arena_id` 在发起者站在 arena 外（街道以外的草地）时为 `null`，此时只看曼哈顿距离。相邻阈值 1、walking 超时 30 s、消息上限 16 为假设（AI Town 常量）。
4. **人类玩家的 external 物品**（假设）：没有 `agent_id` → 手机用 player id 查 feed（自我层目前对 `for` 不区分，返回同一份 digest）；直播台只本地切 `scene`，不打自我层。若要禁止人类用直播台，一行改成 `live_unavailable`。
5. **物品数值表**（§3.9 第 6 条要求标假设）见 api-spec §5：bed +25 energy/h、fridge +40 fullness、book +60 fun、stream_desk social +20/h 等。stream_desk 的 `max_duration` 3 h 沿用 B11 的假设。A 若在 persona 层有「一天几顿 / 睡几小时」的设定，请对齐。
6. **地图不是 MAP_EDITOR 画的**（假设可接受）：本机没有 MAP_EDITOR，`scripts/gen_map.py` 按其导出格式直出，`tiled` 渲染层省略（前端回退到按 tile 类型着色）。如需用 MAP_EDITOR 再编辑，可把生成的 `map.json / objects.json` 作为导入起点。地图 60×40，zone_names 已填中文。
7. **运行台观察**：联调时 `GET /self/state?agent=whale` 读到 fun = 0.0、mood = 94.7、social 81、energy 96。fun 长时间贴 0 说明运行台上没有任何东西在恢复 fun（8000 跑的 e7a036a 旧地图 + agent 可能没在用物品）。切到本提交后新地图有 book / phone / bath 可恢复 fun；建议 C 的 Plan 把 `advertise` 纳入软偏好，否则 fun 会一直在地板上。
8. **8000 换版本**：请切到本节末尾提交号；首次切换建议清空 `run/data/sandbox/`（旧检查点里的 player 位置是旧地图坐标）。

## 5. 稳定性（任务 6）

- **运行台 8000**（`run/data/sandbox.log`，只读）：自 11-06 起 9 行日志，全是正常请求，0 条 Traceback / ERROR，进程未重启。
- **复现**：`scripts/soak.py --minutes 30 --rounds 3 --backend-dir /tmp/sandbox_soak_e7a036a/back_end`（`git worktree` 的 e7a036a，与运行台同版本；内置参考自我层；两名玩家每秒随机 move / turn / use / leave / effects，每 2 s 读 world / player / perceive，每 7 s 一轮对话邀请，每 10 s 检查点 + self-sync 统计，每 5 min 切倍率；每秒 poll 进程、每 30 s 记 RSS）。
- **结论**：**未复现，排除为可复现缺陷。** 3 轮 × 30 min 全部正常：第 1 轮 6752 次请求、第 2 轮 6571 次、第 3 轮 6505 次，共 19 828 次请求，0 次请求错误，0 次进程退出，沙盒日志 0 条 Traceback / ERROR；RSS 三轮分别 67→74.6 MB、61→66 MB、61→66 MB，前 5 分钟后趋平，无泄漏迹象。原始日志存 `back_end/scripts/soak_e7a036a_2026-11-06.log`。运行台 8000 同版本自 11-06 起长跑亦无异常。
- **对 W2 那次「意外退出」的解释**：W2 那次只发生在 `verify_self_sync.py` 的**第一次**运行，当时沙盒的 stdout/stderr 被丢到 DEVNULL，没有日志；之后同脚本连跑 3 次、本次 90 分钟高频压测、运行台长跑都没有再出现。在没有日志的情况下无法定位根因，倾向于一次性环境因素（当时刚 `uv add httpx` 改过 lockfile，首次 `uv run` 可能在子进程启动前后重同步 `.venv`；或与同一进程内刚起的 mock uvicorn 线程竞争端口 / 文件描述符）。已做的防范：`verify_self_sync.py`、`verify_external.py`、`soak.py` 都把沙盒日志落到临时目录并在异常退出时打印尾部，再出现即可直接定位。建议：运行台若再出现退出，把 `run/data/sandbox.log` 尾部贴进 handoff，我这边 `soak.py` 可按同一版本复跑。

## 6. 本次提交

W3 代码：`4369ee5`；本报告与压测日志：见 `git log -1`。运行台 8000 建议切到 **本仓库 `whale-integration` 最新提交**（含新地图、每小时尺度、B9/B10/B11）。

---


# W2 · 2026-11-06：需求值管线、controller、对接自我层（原报告）

## 1. 进度（W2 任务 1–7 全部完成）

| # | 编号 | 任务 | 状态 | 主要文件 |
|---|---|---|---|---|
| 1 | §3.7 B3 | `last_tick_ts` 改 ISO 8601（游戏时刻，含时区） | ✅ | `buff_tick.run_tick`、`world_state._ensure_player_fields`（旧 float 检查点自动转 ISO） |
| 2 | B4 | `EFFECT_HANDLERS` 工厂（`<var>_regen` / `<var>_delta` / `emotion_tag` / `closeness_delta`）、`decay` 元 buff（§2.5 速率表，按 `scene` 切换）、catch_up 分段：fullness / energy 4 h，其余 8 h | ✅ | `back_end/game/buff_tick.py`（重写）、`persistence.catch_up` |
| 3 | B5 | 7 个类型加 `advertise` 与成本项，`hp` / `hp_regen` 全改 `fullness` / `fullness_regen`；同一物品 30 游戏分钟冷却 → `object_cooldown`；6 h 使用计数 `recent_uses`；`GET /world` 下发 `advertise` | ✅ | `object_types.json`、`world_state`（`_last_used` / `_use_history`）、`routers/actions.handle_use`、`models/world.GameObject` |
| 4 | B6 | `JoinRequest.controller: str = "human"`、`profile: dict \| None`（与 C 的 `join_player` 同名）；agent 无心跳只标 `online=False` 不删、仍参与 tick；`POST /player/rejoin`；snapshot 带 `controller` / `online` | ✅ | `routers/player.py`、`world_state`（`_cleanup_stale_players` / `rejoin_player` / `touch_player`） |
| 5 | B13 | `perceive` 加 `needs`（分档文字，不给数值）、`closeness` 分档、`recent_uses`、`players_in_view`；`GET /player/{id}/state`；`POST /player/{id}/effects`（与 object_types 同格式，带 `scene`） | ✅ | `routers/agent.py`、`routers/player.py`、`game/needs.py`（新）、`world_state.apply_effects` |
| 6 | §2.5 | 每 30 游戏秒 `POST {SELF_URL}/self/state/delta`（带 `ts`），不可达时本地继续 tick、累积重发；join / 重启时 `GET /self/state` 种入；`SELF_URL` / `SELF_TOKEN` / `SELF_SYNC` 可配；`GET /admin/self-sync` | ✅ | `back_end/game/self_sync.py`（新）、`main.py`、`persistence.seed_agents_from_self` |
| 7 | B14 | 文档同步 | ✅ | `docs/api-spec.md`、`docs/data-models.md`、`docs/architecture.md` §6、`README.md` |

B9 / B10 / B11 / B12 按 §3.6 未动。前端未改（`hp` 别名仍在）。

**关键设计（读了 whale-self/state.py 后定的，请 A 确认）**：自我层的 `apply_delta` 在加 `vars_delta` 之前会先把自己的状态按衰减表 catch_up 到 `ts`。因此沙盒**只上报非衰减变化**（物品 buff、instant_effect、`/effects` 推送，取 clamp 后的实际变化量），自然衰减两边各自按同一张速率表算。否则衰减会被加两遍。实现上 `buff_tick.set_var/add_var` 有 `track` 标志与 `ON_VAR_CHANGE` 钩子，`decay` handler 用 `track=False`。

## 2. 测试命令与结果

```bash
cd back_end
uv run pytest -q
# 93 passed（W1 的 51 个 + W2 新增 42 个）

uv run python scripts/verify_restart.py
# 15/15 checks passed（W1 回归基线，含 kill -9 重启）

uv run python scripts/verify_self_sync.py --mock --seconds 60
# batch drift_max=0.020  final diff=0.037  (threshold 0.5, 63 batches) → PASS   （连跑两次：0.020 / 0.026）
uv run python scripts/verify_self_sync.py --self-url http://127.0.0.1:8100
# 对真实自我层：本次会话期间 8100 端口无服务（见 §5），未能跑；脚本已就绪，A 的服务起来后一条命令即可
```

W1 的 51 个测试里有 7 个因 W2 的**预期变化**改了断言（不是放宽）：`last_tick_ts` 变字符串、buffs 恒含 `decay`、snapshot 多 `controller` / `online`、能量期望值减去 1 s 自然衰减（8/3600）。

| 新增文件 | 用例 | 覆盖 |
|---|---|---|
| `tests/test_decay.py` | 13 | B4：工厂 key 齐全；新 player 带 decay 元 buff；**一游戏小时对账**（12:00–13:00，200 ms 步长：fullness 58、energy 92、social 54、fun 50、mood 65+10·0.5^0.5、closeness 72−1/24，误差 1e-6）；夜间 ×1.5（02–03 点 energy 88；05:30–06:30 半夜间）；`night_seconds`；live 速率（social −0.12/s、mood 半衰期 70 s）；mood 回 profile 基线；decay 不触发同步钩子而 regen 触发；一次性 `<var>_delta` / `closeness_delta` / `emotion_tag` 用后移除；**catch_up 8 h 停机 fullness / energy 只扣 4 h、social / fun 扣满 8 h**；30 h 停机等同 8 h；短停机全量；第二阶段保留物品 buff 不应用；admin 清 buff / force-reset 保留 decay |
| `tests/test_cooldown.py` | 7 | B5：7 类型都有 `advertise`、至少一项成本、无 `hp` 键；`GET /world` 下发 advertise；use → leave → use 返回 `object_cooldown`（剩余 1790–1800 s），1801 s 后可用，`recent_uses` 计 2；冷却按（实体, 物品）隔离；6 h 窗口滚动；instant 物品成本（fridge fun −2）与冷却、tag 不挂；冷却与计数随检查点持久化 |
| `tests/test_controller.py` | 6 | B6：join 带 controller / profile（mood 69.5、agent_id）；默认 human、非法 controller 400、agent_id 缺省 slug；**stale agent 标 offline 不删、human 照旧删**；offline agent 仍衰减；GET /player 心跳与 rejoin 恢复 online、rejoin 未知 404；offline agent 仍可行动且随检查点恢复 |
| `tests/test_effects_api.py` | 7 | B13：`/state` 形状、404；`/effects` 一次推 instant / emotion_tag / closeness_delta / timed regen / tag + scene=live（applied 6 skipped 1）；scene 校验 400、不带 scene 不切；hp 别名 clamp；**perceive `needs` 全是文字无数值**（low / critical / emergency / mood 低 / tag 文案 / hard 列表）；closeness 分档与 `players_in_view`、`recent_uses`；分档边界 |
| `tests/test_self_sync.py` | 9 | 任务 6：对端是 `httpx.MockTransport` 跑的 whale-self `state.py` 参考移植（decay / catch_up / apply_delta，sandbox + live）。join 时种入自我层值（energy 70 而非 100）、human 不登记；每 30 游戏秒出批、纯衰减时 `vars_delta` 为空；**两小时场景（23:00→01:00 跨夜间倍率，床上 40 分钟 regen 顶到 100，两次 /effects 推送）240 批后 max\|diff\| < 0.5、drift_max < 0.01、0 次纠偏**；自我层宕机 120 s 后恢复：失败批合回待发池、累积增量一次补发、仍 < 0.5；自我层另有写入 → snap 纠偏一次，关掉 snap 只记 drift；live 场景速率一致；重启回填 + 1 h 停机后重新种入仍 < 0.5；`/admin/self-sync` 形状；`SELF_SYNC=0` 完全不动 |

`verify_self_sync.py` 的判据：① 每批被确认时自我层返回 `vars` 与发批瞬间本地快照之差（`drift_max`）< 0.5；② 结束时两边直读之差 < 0.5；③ 无失败批。采样期间会看到瞬时差 ≈ 1.3——那是**批间延迟**：物品 buff 的连续变化最多滞后 30 游戏秒才上报，量级 = 速率 × 30 s（现有 bed 的 fun 成本 0.05/s → 1.5）。按 §2.5 速率尺度（每小时个位数）这项 < 0.1；现有 object_types 里 ±1/秒的数值是 W1 之前的旧内容，B16 做地图时应改成每小时尺度（见 §4 第 6 条）。

## 3. api-spec 改动摘要（只增不删，形状不变）

| 位置 | 改动 |
|---|---|
| `GET /world` | `objects[].advertise`（新）；`players[]` 加 `controller`、`online` |
| `GET /player/{id}` | 新字段 `mood_base`、`online`、`scene`、`agent_id`；`last_tick_ts` 改为 ISO 字符串；写明七变量衰减速率、`buffs` 恒含 `decay`、agent 初值来自自我层 |
| `POST /player/join` | 请求体加 `controller`、`profile`；写明 agent 的自我层种入 |
| `POST /player/rejoin`（新） | `{playerId}` → 与 join 同形状 |
| `GET /player/{id}/state`（新） | 七变量原始数值 + `last_tick_ts` + `recent_uses` 等 |
| `POST /player/{id}/effects`（新） | effect 列表 + `scene` + `source` → `{ok, applied, skipped, state}` |
| `POST /action` use | 新 reason `object_cooldown`（`result.cooldownRemaining`） |
| §4 Tick | catch_up 分段上限；新增「与自我层同步」小节（对象、种入、上报内容、失败重发、对账、配置、验证） |
| §5 Buff / Effect | key 表改为工厂形式（`<var>_regen` / `<var>_delta` / `emotion_tag` / `closeness_delta` / `decay`）；扩展字段 `tag` / `target`；Object 类型新增 `advertise` 与成本项说明；`hp` 键全部改名 |
| §6 perceive | 新增 `players_in_view`、`needs`（分档规则、阈值、文案同源、closeness 分档阈值为假设） |
| §6 Admin | 新增 `GET /admin/self-sync` |

`docs/data-models.md`：Player 新字段、buff key 表、advertise 段、catch_up 分段、同步说明。`docs/architecture.md` §6：工厂注册表、decay 元 buff、钩子与同步、catch_up。`README.md`：Object/需求值段、Agent API 表、项目结构、测试命令。

## 4. 对契约的建议（请会话 A 汇总）

1. **自我层默认初值与 §2.5 / B3 不一致**。`whale-self/state.py` 的 `DEFAULT_VARS` 是 fullness/energy/social/fun 全 70；B3（已确认）是 70 / 100 / 60 / 60。沙盒对 agent 以自我层为准（种入覆盖），所以运行时不冲突，但请 A 定一个写进 §2.5。
2. **上报语义写进 §2.5**：「`vars_delta` 只含非衰减变化；衰减由自我层按 `ts` 自己 catch_up」。这是两边不重复扣的前提，目前只在我的 api-spec 与自我层代码注释里。
3. **沙盒 catch_up 4 h / 8 h 分段 vs 自我层 8 h 单段**：两边同时停机 > 4 h 时沙盒的 fullness / energy 会比自我层高（最多 48 / 32）。沙盒重启后会重新从 `GET /self/state` 种入，所以最终以自我层为准，沙盒的 4 h 上限只在自我层不可达时生效。若希望自我层也「离线等于在睡」，请 A 在 state.py 对 fullness / energy 同样截 4 h。
4. **自我层的 emotion_tags / closeness 不走 delta**。`POST /self/state/delta` 只收 `vars_delta`，emotion_tag 与 closeness 只能经 `POST /self/state/event`。W2 沙盒的 `/effects` 推送只落本地并把七变量变化并入 delta；**沙盒不转发 event**（否则 mood 会被加两遍，且双写记忆的归属不清）。建议：直播服务同一事件同时推自我层 `/self/state/event` 与沙盒 `/player/{id}/effects`（自我层那一路负责记忆），或 W3 定一个单向链路。
5. **snap 纠偏（假设）**：批确认时 `max|drift| > 0.5` 就把差值加回本地（以自我层为准）。`SELF_SYNC_SNAP=0` 可关。请确认方向。
6. **现有 object_types 的数值尺度**：bed `energy_regen +1/游戏秒`（= +3600/h）、desk `−1/s` 等是旧内容，与 §2.5 的每小时尺度相差 3 个量级，使用物品几秒就顶满 / 清零。本次只按 B5 要求加 `advertise` 与成本、改键名，没动旧数值；建议 B16 画新地图时统一改成每小时尺度（我在报告里标为假设，可由 B 在 W3 顺手改）。
7. **`agent_id` 字段**（假设）：`profile.agent_id` 指定自我层 agent id，缺省取 name 的 slug。请 C 在 `join_player` 的 profile 里带 `agent_id: "whale"`，否则中文名 slug 对不上 persona。
8. **closeness 分档阈值**（假设）：≥70 很亲近 / ≥40 熟悉 / ≥15 认识 / 其余陌生。
9. **speed > 1 时自我层的 `GET /self/state`** 以其墙钟 catch_up，而沙盒上报的 `ts` 是游戏时刻（可能领先）；自我层那边 `now − last_tick_ts < 0` 不补算，读到的是「上一批时刻」的值。生产 speed=1.0 无影响，调试加速时读 `/self/state` 会滞后一批（≤ 30 游戏秒）。

## 5. 卡点

- **真实联调未跑**：本次会话期间 `http://127.0.0.1:8100` 没有服务，而规矩第 3 条不允许我启动 whale-self。已用 whale-self `state.py` 的参考移植（测试内 MockTransport + 脚本 `--mock`）验证 < 0.5。A 的服务起来后请任意一方跑：`cd back_end && uv run python scripts/verify_self_sync.py --self-url http://127.0.0.1:8100`，输出最后一行 PASS/FAIL 与 drift。
- `verify_self_sync.py` 第一次运行时沙盒进程曾意外退出一次（Connection refused），之后三次均正常，日志现已落到临时目录 `sandbox.log` 便于复现；若再出现会附在下次报告。

---

# W1 · 2026-11-05：持久化、时间、七变量（原报告）

## 1. 进度

| # | 编号 | 任务 | 状态 | 主要文件 |
|---|---|---|---|---|
| 1 | B7 | 时间系统改「真实起点 + 倍率」 | ✅ 完成 | `back_end/game/time_state.py`（重写）、`routers/world.py`、`routers/time_control.py`（未改，签名兼容） |
| 2 | B8 | buff tick 独立 asyncio 后台任务（200 ms），`GET /world` 只读 | ✅ 完成 | `back_end/game/ticker.py`（新）、`world_state.py`（`get_world` 只读、`STATE_LOCK`）、`main.py` lifespan |
| 3 | B2 | SQLite 检查点，每 5 s 与关停写，启动回填 | ✅ 完成 | `back_end/game/persistence.py`（新）、`paths.py`（新）、`world_state.py` / `chat_state.py` / `time_state.py` 各加 export/import、`main.py` |
| 4 | B1 | 行动日志 append-only JSONL + `read_log(since, entity)` | ✅ 完成 | `back_end/game/action_log.py`（重写）、`routers/history.py`（新增 `GET /history/log`） |
| 5 | B3 | Player 加七变量、`hp` 作 `fullness` 别名 | ✅ 完成 | `models/player.py`、`world_state.py`（`_make_player` / `apply_var_delta`）、`buff_tick.py`（`set_var` / `add_var`） |
| 6 | B14 | 文档同步 | ✅ 完成 | `docs/api-spec.md`、`docs/data-models.md`、`docs/architecture.md` §6、`README.md` 时间系统段 / 项目结构 / 测试 |

前端未改（`hp` 别名使 HUD 继续工作）。W2 预留口：`create_player(name, controller, profile)` 已接受 `controller` 与 `{E, N}`（路由层未暴露，等 B6）；`run_tick` 已处理 `emotion_tags` 到期（B4 接衰减元 buff 时无需再改 tick 主循环）；`persistence.catch_up()` 跑的就是 `_run_buff_tick_all`，B4 的 decay buff 挂上后停机补算自动生效。

## 2. 测试命令与结果

仓库原先没有任何测试。本次新建 `back_end/tests/`（pytest + httpx，已加入 `pyproject.toml` dev 组），其中 `test_api_shapes.py` 固定现有对外接口形状作为回归基线。

```bash
cd back_end
uv sync
uv run pytest -q
# 51 passed in 1.6s

uv run python scripts/verify_restart.py            # kill -9 后重启续跑验证
# 15/15 checks passed（连续运行两次均通过，可复跑；--downtime 可调停机秒数，--keep-data 保留临时数据目录）
```

| 文件 | 用例数 | 覆盖 |
|---|---|---|
| `tests/test_time_state.py` | 12 | B7：默认 speed 1.0、首启取真实日期、倍率切换 / 暂停 / 恢复 / 重启后时间连续、`advance_time` 签名与返回值、`/time/*` 响应形状 |
| `tests/test_ticker.py` | 7 | B8：假时钟下 `tick_once` 按速率改能量、按 speed 缩放、暂停不动、`GET /world` 轮询 5 次不改状态、stale 清理、5 s 检查点、真实事件循环下 lifespan 启动 ticker 并在 0.7 s 内改变能量 |
| `tests/test_persistence.py` | 9 | B2：players / object_runtime / time_state / chat 全部往返、停机 20 s × speed 3 后时间与 catch_up 对账、8 h 上限、回填后 grace 期不被当 stale、旧 schema 补字段、表与 meta 存在、`/admin/checkpoint`、带 lifespan 真实重启回填 |
| `tests/test_action_log.py` | 6 | B1：25 次动作 = 25 行 JSONL 且内存只留 20、`skipLog` 两处都不写、失败动作带 reason、`read_log` 的 since / entity / limit、`GET /history/log`、被截断半行容错 |
| `tests/test_player_vars.py` | 9 | B3：`GET /player` 七变量 + 旧字段齐全、join 响应、Pydantic 模型可解析、mood 基线公式、通用 clamp 与 `hp→fullness`、instant_effect 走通用路径、`hp_regen` 保持别名同步、emotion_tags 到期、床的 use/leave 端到端 |
| `tests/test_api_shapes.py` | 8 | 现有接口形状：`/world`、join/leave/404、move/turn 响应、未知 action 400、perceive、events、admin buffs |

`verify_restart.py` 的 15 项：BFS 走到 desk_12 旁、use 成功、检查点写出、kill -9 重启后 player 存在、位置相同、仍在使用同一物品、物品 userList 恢复、speed=3 保持、七变量齐全、能量按「停机时长 × speed」被补算（97.0 → 78.3，停机 6 s × 3 ≈ 18）、`hp == fullness`、游戏时间增量 ≈ 真实时长 × speed（+19 s / 期望 19 s）、JSONL 行数与动作数一致（23）、`GET /history` 仍为数组、重启后可继续 `leave`。

## 3. api-spec 改动摘要（全部为新增 / 澄清，无删除、无形状变化）

| 位置 | 改动 |
|---|---|
| `GET /world` | `worldState` 示例从过时的 `isDay` 改成实际的 `{date, time, period, running, speed, weather}`；加字段表与时间系统说明；注明接口**只读** |
| `GET /player/{id}` | 示例与字段表新增 `fullness, social, fun, mood, emotion_tags, closeness, controller, last_tick_ts`；说明 `hp` 是 `fullness` 别名、过渡一版后删除（假设）；去掉「每次调用触发 tick」的旧描述；补写 `POST /player/join` 与 `DELETE /player/{id}/leave` |
| `GET /history` | 元素新增 `label`（原本就返回但未写）、`game_time`、`controller`；说明 JSONL 落盘 |
| `GET /history/log`（新） | query `since / entity / limit`，返回与 `/history` 同形状数组 |
| §4 Tick 说明 | 改为后台 ticker + 5 s SQLite 检查点 + 启动回填 + catch_up ≤ 8 h；新增「时间控制」小节记录 `/time/toggle|speed|reset`（原文档缺失） |
| §6 管理接口 | 新增 `POST /admin/checkpoint` |
| §5 Effect 表 | `instant_effect` 的 `key` 从「energy 或 hp」扩为七变量（hp 视为 fullness），clamp 0–100；`hp_regen` 说明改为作用于 fullness |

`docs/data-models.md`：Player 类型加七变量与说明、WorldState 改成实际字段并附时间系统说明、tick 顺序加 emotion_tags 与 last_tick_ts、补持久化说明。`docs/architecture.md` §6：tick 由后台任务驱动、handler 表加 hp_regen→fullness、需求值统一走 `set_var`。`README.md`：时间系统段重写、项目结构加新模块、加「运行测试」。

## 4. 对契约的建议（请会话 A 汇总后统一改 ARCHITECTURE.md）

1. **默认 `running=true`**（假设）。原代码启动即暂停，等前端点 ▶ 才走。B8 的目的就是无人在线也要演化，所以改为启动即运行，`SANDBOX_TIME_RUNNING=0` 可恢复旧行为。建议写进 §3.1 B7。
2. **时区**（假设）。本机系统时区是 Asia/Tokyo，而 README 规矩第 8 条说与北京时间 1:1，所以游戏时间固定用 `Asia/Shanghai`（`SANDBOX_TZ` 可改），不跟随系统时区。建议契约里明确写时区而不是「真实日期」。
3. **`last_tick_ts` 类型**。§2.5 JSON 示例是 ISO 字符串，B3 写的是 `float`。沙盒按 B3 用 epoch 秒 float；行动日志的 `game_time` 用 ISO。建议 §2.5 与 B3 统一（沙盒侧改成 ISO 也只是一行）。
4. **初始 energy**。原代码 80，B3 写 100（报告 §4.3 基线），已按 B3 改成 100；请确认。
5. **catch_up 的语义**。B7 写「按停机时长补一次衰减，不补事件」。W1 没有衰减 buff，`catch_up` 跑的是现有物品 buff（在床上睡的时间会补 energy_regen，在桌前的时间会补 energy 消耗）——我认为这正是「续上」应有的语义，但它意味着 B4 的 decay 元 buff 挂上后，停机 8 h 会一次性扣 8 h 的饱腹 / 体力。请确认 8 h 上限是否仍合适，或在 B4 时对不同变量设不同上限。
6. **`controller` 的日志来源**。B1 要求日志带 `controller`，目前从 player dict 读（W1 全是 `human`）；B6 加 join 参数后自动正确。若 agent 在 W1 就想被标记为 agent，需要会话 C 等 B6 的 `JoinRequest.controller`。
7. **`GET /history/log` 是否算接口新增**。为了让自我层能真正拉到完整日志，`read_log` 之外多加了一个只读路由。若契约希望只保留函数，可删路由（一行）。
8. **`POST /admin/checkpoint`**（假设）新增，验证脚本与测试用；也方便运维在升级前手动落盘。

## 5. 卡点

无阻塞。两点提醒：
- 心跳清理仍是「10 s 无 `GET /player` 即删」（B6 范围）。检查点回填后给了 10 s grace，重启后 agent 若 10 s 内没来读 `/player`，她仍会被清掉——这是 B6 要解的问题，W1 没碰。
- `uvicorn --reload` 每次热重载都走一遍关停写检查点 + 启动回填，日志会多两行 INFO，属正常。

## 6. 本次提交涉及的文件

新增：`back_end/game/{persistence,ticker,paths}.py`、`back_end/scripts/verify_restart.py`、`back_end/tests/*`（7 个文件）、`WHALE_REPORT.md`。
修改：`back_end/game/{time_state,action_log,buff_tick,world_state,chat_state}.py`、`back_end/main.py`、`back_end/models/player.py`、`back_end/routers/{world,history,player}.py`、`back_end/pyproject.toml`、`back_end/uv.lock`、`.gitignore`（忽略 `back_end/data/`）、`docs/{api-spec,data-models,architecture}.md`、`README.md`。
