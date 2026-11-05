# WHALE_REPORT — 会话 B（BASIC_SANDBOX）

分支：`whale-integration`。日期：2026-11-05。范围：W1 任务 1–6（B7、B8、B2、B1、B3、B14）。

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
