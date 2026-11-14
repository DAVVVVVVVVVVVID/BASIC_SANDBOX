# X5 规划与需求实验 · 摆场步骤（B 夹具）

对应 `paper/plans/X5-planning.md` §3。bench 8090 / 8390 与 bench2 8092 / 8392（v1 图，`SANDBOX_SCENARIO=1`，×6 速）。**无 NPC agent**：克劳蒂娜 / 阿蝉只以夹具（`qq_send` / `spawn` 没有 brain 的壳）出现。鲸仔由 C join（`controller=agent, profile.agent_id=whale`，名字 `鲸仔`；join 自动拿合租房钥匙）。经济值：每镇 `SANDBOX_ECONOMY_PATH` 指独立 `economy.json`（X5 钉现值 `fridge: initial 2 / restock_qty 2 / max 4 / restock_at 08:00`），`GET /admin/metrics.economy.sha256` 记进 manifest。

## 新 op（X5）

| op | 参数 | 作用 |
|---|---|---|
| `set_fridge` | `id`（缺省 `fridge_home`）, `qty` | 直接写冰箱食材库存（含 0） |
| `set_stock` | `shop`（物品 id：`counter` / `fish_stall`）, `item`, `qty` | 写商店库存，`/world.objects[].shop[].stock` 同步 |
| `force_closed` | `object` \| `door_id` \| `arena` \| `shop`（任一 id）, `until: "HH:MM"` \| ISO \| `null` | 强制关门不等真实时钟：物品 `use → closed`（`opens_at = until`）、所在 arena / 门边进入 → `no_path / closed`、正在用的人下一 tick 被请出；到点自动解除，`clear_closed {key?}` / `reset` 也解除 |
| `clear_closed` | `key?` | 解除（不给 = 全部） |

| `set_gold` | `player`, `gold` | **v1.1** 把余额写成 gold（流水 adjust，账户同步） |
| `set_supply` | `shop`, `item`, `qty` | **v1.1** 写商店当日上新量 `daily_supply`（08:00 补货按它；0 = 今天不上这货）；清今日剩余用 `set_stock` |

共用（既有）：`set_time`、`teleport`、`set_vars`、`spawn`、`give_item`、`qq_send`、`reset`。

**判分归属**：十场景 + S11 / S12 的通过判定以 A 的 judge（`docs/behavior-acceptance.md` 末段）为准，本表「判定要点」是跑手级预判 / 提示；C 的跑手写每场 `scenario.json` 时 `scenario` 字段用 **S11 / S12**（judge 按它取场景，目录 `S11-rN` / `S12-rN`）。

**world-v1.1 起的夹具语义变化**：`set_fridge` 不带 `item` = 整台清空后放 qty 份食材（qty 0 = 空冰箱），带 `item` 只重写该种；冰箱**不自动补货**（`economy.fridge.restock_enabled` 默认 false，`restock_pinned` 只在开着补货时有意义）；商店 08:00 `stock := daily_supply`（卖完即止）；进食必须 `use` 餐桌类再 `eat`（长椅只许面包 / 甜食 / 饭菜；直播中 `streaming`）；`occupy` 的时长计入每日上限（创作 / 娱乐类无冷却）；房租默认开着（`rent.enabled`），bench 短场景无影响（只在每月 1 日 08:00 扣）。核验脚本：`cd back_end && uv run python scripts/verify_fixtures_v11.py --base http://127.0.0.1:8091`（摆好 S01 / R1 / R5 / R6 并断言前置条件）。

## 坐标（**v1.2 紧凑图**，world-v1.2 起；v1 图坐标见 git 历史）

鲸仔房间 `whale_room` 出生点 (4,13)、床 `bed_whale` (3,11)-(3,12)（站 (3,13) 朝 up）、电脑 `pc_whale` (5,11)（站 (5,12) 朝 up，直播 / 电台）、手机 `phone_whale` (4,11)（站 (4,12) 朝 up 刷 feed，v1.3.1）、书架 (5,13)；客厅 `living_room` (9,13)、餐桌 `table_home` (7,11)（座位 (7,12)(8,12)）、沙发 (7,15)、楼梯格 (10,16)↔2F (3,30)；厨房 `kitchen` 冰箱 `fridge_home` (5,15)（站 (5,16) 朝 up）、灶台 `stove` (3,15)（站 (3,16) 朝 up）；合租房大门 `door_home` (9,17)→门外 (9,18)（北巷 y18）。
街道 `street`：主街 y8–9（如 (30,9)），南北街 x20–21（y8–26）；北巷 `lane` y18、南巷 y26。广场 `square` x22–31,y10–17：(28,14)（喷泉 (26,12) 2×2 旁），长椅 `bench_square_1` (23,11)（走到 (23,12) 朝 up 坐）、`_2` (29,11)、`_3` (26,16)，公告栏 (22,17)。公园 `park` x13–19,y10–17（v1.2.5 起没有长椅 / 简餐处，室外吃东西去广场长椅）。
餐厅：门 `door_restaurant` (35,17)→门外 (35,18)；`table_rest_1` (34,11)（站 (34,12) 朝 up）、`table_rest_2` (34,14)（站 (34,13)/(34,15)）、`bar` (37,11)（站 (37,12)）、后厨 `fridge_rest` (41,11)、`stove_rest` (40,15)。杂货店：门 `door_grocery` (23,24)→门外 (23,25)（南墙最西，门朝南开到短巷 y25；短巷西接南北街 (21,25)、南接南巷 y26）；柜台 `counter` (28,22)（站 (27,22) 朝 right）。
码头 `dock` x42–45,y1–9：(43,5)；钓位 `fishing_spot_1` (45,2)（站 (45,3) 朝 up）、`_2` (45,6)；鱼摊 (42,1)。校园：校门 (20,7)(21,7)→(20,8)(21,8)；琴房电脑 `pc_music` (24,2)（站 (24,3) 朝 up）；教学楼门 (5,5)→(5,6)、图书馆门 (14,5)→(14,6)、音乐楼门 (24,5)→(24,6)。渔夫家门 (36,6)→门外 (36,7)；克劳蒂娜家门 (15,25)→(15,26)；店主家门 (34,25)→(34,26)（门内 (34,24) 为过道，左老板房 / 右厨房）。（v1.2.1：门格跟 E 的外观图走，楼 / 门 id / 物品不变；杂货店 shelf_2 挪到 (24,23)）空草地（给人 / 当面交接）：(3,19)(4,19)。2F 阿蝉房 `achan_room` x3–6,y30–32（楼梯 1F (10,16) ↔ 2F 落点 (3,30)）：床 `bed_achan` (3,32)-(4,32)（站 (3,31) 或 (4,31) 朝 down）、书桌电脑 `pc_achan` (6,30)（站 (6,31) 朝 up）、书架 `shelf_achan` (6,32)（站 (5,32) 朝 right）；空地 (4,30)(5,30)(4,31)(5,31)。公园树（v1.2.2，只影响外观）：tree_1 (13,10) 2×2、tree_2 (17,16) 2×2、tree_3 (14,16)、tree_4 (15,11)。室外装饰（v1.2.3，不可用、占格）：灌木 (13,17)(19,17)(37,7)(10,19)(36,19)(24,25)(14,27)(35,27)、花坛 (18,12)、垃圾桶 (31,17)、邮筒 (22,11)、码头侧向长椅 (42,4)-(42,5)（座面朝东看河）——都不在任何夹具站位 / 门前格 / 巷子上。渔船 `boat`（装饰）v1.2.4 起在水上 (46,8)-(47,8)，码头 (43,9)(44,9) 变回可走。

## 场景

| # | 摆法（steps） | 终止 | 判定要点 |
|---|---|---|---|
| **S01** 饿了就吃（**v1.1 三步版**） | `set_time 11:30`；`teleport 鲸仔 28,14 up`（广场）；`set_vars {fullness: 15}`；`set_fridge fridge_home 0`（整台清空）→ `set_fridge {id: fridge_home, item: home_meal, qty: 2}`（两份家常菜）；`set_stock counter bread 8`（备选路：买面包到长椅 / 餐桌吃） | `eat_done` / 60 游戏分钟 | **A judge：`eat` 成功后 35 分钟内饱腹涨 ≥ 5**（饱腹 ≤ 15 起算）。跑手级预判（提示）：45 分钟内完成「拿 / 买 → 到餐桌类 → `eat`」三步，不许原地 `eat`（`not_at_table` ≤ 1 次）；餐厅 11–14 开着，去餐厅 `eat meal`（−20）也算 |
| **S02** 到点睡觉 | `set_time 01:50`；`teleport 鲸仔 30,9 left`（街道） | 睡着 / 60 分钟 | 40 分钟内 `use bed_whale`、`tags` 含 `sleeping`；她有合租房钥匙，门禁不挡 |
| **S07** 直播段上台 | `set_time 19:50`；`teleport 鲸仔 4,13 down`（`whale_room`，验收台原文「小仓库」为 v0 名） | 20:30 | 20:15 前 `use pc_whale`（`external: live`，bench `SELF_SYNC=0` 时会 `live_unavailable`——**X5 bench 请开自我层同步或由 C 用 `scenario occupy` 认 use**）成功、`scene=live`、`tags` 含 `streaming` |
| **S08** 不敲关门店 | `set_time 22:30`；`teleport 鲸仔 28,14 right`；`set_vars {fullness: 20}`；（22:30 餐厅 / 杂货店本就关；要不等时钟可 `force_closed {object: table_rest_1, until: "11:00"}` + `force_closed {shop: counter, until: "09:00"}`） | 30 分钟 | 不对 `closed` 物品连续 `use` > 1；转向可用物品（家冰箱 2 份） |
| **D1** 一日时间分配 | `reset` → C join 鲸仔 → `set_time 09:30` → `teleport 鲸仔 3,13 up` + `occupy {player: 鲸仔, object: bed_whale}`（睡着起）→ `set_vars {fullness: 60, energy: 95}`；`set_fridge fridge_home 2`；金币 300（join 默认）；不放 NPC | 次日 09:30 | 锚点（persona.yaml）：起 10:00 / 早饭 10:30 / 午饭 12:30 硬 / 电台 13:30–18:00 / 晚饭 19:00 硬 / 直播 20:00–23:00 / 睡 01:30；补货 08:00、日薪、店开关由 tick 自动触发（`scripts/verify_day_cycle.py` 已核：×600 一日 14/14） |
| **R1** 资源不可得（**v1.1**） | `set_time 22:30`；`teleport 鲸仔 28,14 right`；`set_vars {fullness: 18}`；`set_fridge fridge_home 0`（整台清空；**v1.1 冰箱不自动补货，不会再被 08:00 盖回**）；背包空（残留先 `reset`）；22:30 餐厅 / 杂货店（22:00 关）都关 | 23:30 | 没有任何门路：不撞冰箱（`use` 冰箱回 `empty`，≤ 2 次）、不在关门店前反复 `buy`（`shop_closed` ≤ 2）、同一失败动作连续 ≤ 3 次；可接受：回家睡 / 等 09:00 杂货店 / 明早餐厅 11:00；Think 里说出「没吃的、明天买」 |
| **R2** 冲突目标 | `set_time 19:40`；`teleport 鲸仔 4,13 down`；`set_vars {fullness: 22}`；`set_fridge fridge_home 1` | 21:00 | 20:15 前上播 **且** 21:00 前饱腹未跌破 15；取舍顺序 |
| **R3** 突发打断 | `set_time 14:30`；`teleport 鲸仔 5,12 up`；`occupy {player: 鲸仔, object: pc_whale}`（电台段写稿中——注：`pc_whale` 是直播物品，`occupy` 只本地切 live；若 C 的「电台」用 `make_video` 在 `pc_whale` 上写稿，同一物品）；`spawn 克劳蒂娜` + `qq_send {from: 克劳蒂娜, to: 鲸仔, text: "来广场一下？有事"}` | 30 游戏分钟 | 是否回复（`/qq/send`）/ 是否中断当前段 / 回来是否续上；无来回跑 |
| **R4** 晨间启动 | `set_time 09:55`；`teleport 鲸仔 3,13 up`；`occupy {player: 鲸仔, object: bed_whale}`（`tags` 含 `sleeping`） | 60 分钟 | 醒来 → 第一个有效动作（刷手机 / 早饭）的游戏分钟数与 Think 数；10:30 早饭锚点 |
| **S11** 两头空 → 去餐厅（**v1.1 新**，A judge 目录 S11-rN） | `set_time 12:10`（餐厅 11–14 开）；`teleport 鲸仔 9,13 up`（客厅）；`set_vars {fullness: 15}`；`set_fridge fridge_home 0`（`contents` 空）；`set_stock` + `set_supply` 各对 `counter` 的 `ingredients` / `bread` / `sweets` 置 0（杂货店食物**今日剩余 `stock` 与当日上新量 `daily_supply` 都为 0**，A judge 看 `daily_supply`）；`set_gold 鲸仔 300` | 13:00 | 13:00 前 `use table_rest_1 / table_rest_2` + `eat {item: "meal"}` 完成（ws `eat_done {item: "meal", object: table_rest_*}`，金币 −20）；在别处吃到 = 夹具未生效；柜台 `out_of_stock` ≤ 2 次、冰箱 `empty` ≤ 1 次 |
| **S12** 房租在前钱不够（**v1.1 新**，A judge 目录 S12-rN） | `set_time {date: <下月 1 日 − 1 天>, time: 14:00}`（离 1 日 08:00 到期 18 小时，`rent.due_in_days` 0）；`teleport 鲸仔 4,13 down`；`set_vars {fullness: 60, energy: 90}`；`set_fridge {id: fridge_home, item: home_meal, qty: 2}`；`set_gold 鲸仔 120`（< 房租 300）；**必摆** `POST /admin/commission {client: 餐厅老板, title: 店歌, fee: 150}`（公告栏有 open 委托） | 60 分钟（阶段一）+ **阶段二必摆**（S12 的一部分，A judge 无阶段二判 na）`set_time {date: 1 日, time: 08:01}` 再 30 分钟 | 阶段一：Think 出「得挣钱」类文本（`GET /player.rent` 的 `due_in_days 0`、`balance 120 < amount 300` 两条事实已给）+ `use` 公告栏 / 琴房电脑 / `compose` / 开播任一动作；不去餐厅花 20 加分；阶段二：到期当刻判欠租并**立即**收到镇公所第一条催租 QQ（之后每日 08:00 一条），30 分钟内 `read_qq` 并回应（不编「已经交了」） |

## 日驱动核验（③）

`cd back_end && uv run python scripts/verify_day_cycle.py --base http://127.0.0.1:8091 --speed 600`：07:50 起跑满一个游戏日，记录实际触发时刻。11-10 在 8091（v1，×600，一日 144 s 墙钟）：08:00 冰箱 0→2、商店 3→10；09:00 / 20:00 杂货店开关、11:00 / 14:00 / 17:00 / 21:00 餐厅开关；17:00 渔夫 +80、18:30 阿蝉 +150、20:00 老板娘 +100、21:00 餐厅老板 +100、克劳蒂娜 14–17 点 4 × 12——全部按时（见脚本输出）。单测 `test_full_game_day_at_x6_triggers_restock_wages_and_hours` 以 60 游戏秒步长模拟同一日。

## 注意

- **同一游戏日内把时间拨回去，补货 / 日薪不会再触发**（已付键按游戏日期记）：夹具若需在同一天重跑 08:00 补货，先 `reset`（现在会清这些记录），或 `set_time` 给明天的 `date`。D1 从 09:30 跑到次日 09:30 不受影响。

- 每遍前清 bench + `seed_initial_memory.py`；`SELF_DREAM_MODE=none`、`SELF_CLOCK_SOURCE=sandbox` 在自我层侧（A）。
- `force_closed` 只在内存里，重启或 `reset` 即解除；`set_fridge` / `set_stock` 写的是运行时库存，进检查点。
- 店主不在线时商店交易没人收钱（买照样成功）；D1 无 NPC 不影响鲸仔侧。
- `spawn` 的克劳蒂娜没有 brain，`qq_send` 由夹具代发；鲸仔回复落 `data/qq/<date>.jsonl`。
