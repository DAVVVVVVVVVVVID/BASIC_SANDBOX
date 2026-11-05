# WHALE_REPORT — 会话 B（BASIC_SANDBOX）

分支：`whale-integration`。最新：**W3（2026-11-06）**；W2、W1 记录在后。

---

# W3 · 2026-11-06：手机与直播台、对话协议、地图与数值尺度

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
- **结论**：__SOAK_RESULT__
- **对 W2 那次「意外退出」的解释**：__SOAK_EXPLANATION__

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
