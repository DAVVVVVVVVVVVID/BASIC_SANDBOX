# WHALE_REPORT — 会话 B（BASIC_SANDBOX）

分支：`whale-integration`。最新：**W6（2026-11-06）**；W5、W4、W3、W2、W1 记录在后。

---

# W6 · 2026-11-06：矩阵与多镇、数据集导出、游戏机 Object、阿蝉体验

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

见 `git log -1`。

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
