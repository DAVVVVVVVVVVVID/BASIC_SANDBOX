分支 `whale-frontend`，worktree `own-repos/BASIC_SANDBOX-fe/`，已 rebase 到 B 的 `59d1ac8`（运行台 8000 现为 W6 构建，mapVersion `…@1b824832ace2`）。只改了 `front_end/`。
总控把运行台 5173 换到本分支时请用下文「提交号」一节。截图在 `front_end/report_shots/`。

---

# W5 · 2026-11-06：形象重画、阿蝉操控台、回放页、多镇旁观、游戏机小窗、OBS 布局

## 1. 进度（任务 1–7）

| # | 编号 | 状态 | 做了什么 |
|---|---|---|---|
| 1 | E11 | 完成（待主播选） | 主播的立绘已在 `front_end/ref/`（鲸仔 / 阿蝉正面全身 + 设定图 + Live2D 渲染）。**v2** 按正面全身图逐像素重画 16×24 四向：鲸仔——深蓝→浅蓝长卷发、白色荷叶边头饰、两侧蓝蝴蝶结与鳍耳、呆毛、白衬衫泡泡袖 + 深蓝裙 + 白围裙 + 蝴蝶结铃铛、白长袜深蓝鞋、身后鲸尾；阿蝉——白色蓬发 + 呆毛、白猫耳粉内耳、右侧两枚蓝发卡、灰蓝眼、蓝短袖衬衫罩白衬衫 + 黑领带 + 工牌、黑裤、白蓝运动鞋、白猫尾。**v1** 是 W4 按 persona 文字画的版本，保留为 `char_whale_v1 / char_achan_v1`，旁观页 `&art=v1` 可切回对比。两版并排：`report_shots/E11_whale_achan_v1_v2.png`（上：跟随画面局部放大；下：完整精灵表）。每套新增第 5 行：坐（正 / 左 / 右）与睡（侧卧盖被）帧，按 `stateLabel` 自动切（睡觉→躺，坐 / 休息 / 玩游戏 / 看书 / 吃饭 / 钓鱼 / 直播→坐）。所有角色同样有坐 / 睡帧。默认用 v2 |
| 2 | E12 | 完成 | 操控页（阿蝉）新增快捷区：显示鲸仔状态与坐标；「**走到她旁边**」= 客户端 BFS 到她的相邻格逐格 move（每步仍由后端裁定；无路时退回后端 `move_to_area`）；「**邀请她聊天**」一键 `POST /chat/request`（human 无冷却，B W6），等待态区分 pending / `walking_over`（「对方接受了，正在走过来」）/ `expired`；房间内打字、看她回复、退出；HUD 新增「🐳 鲸仔」块显示她的七变量**分档**（紧急 <10 / 很差 <15 / 偏低 <25 / 一般 / 不错，只读 `/player/{id}/state`）。**实测**（运行台 8000，C 的真 agent）：走到 (50,24) 与她 (51,24) 相邻 → 邀请 → **4 s 内她接受并回了一句**（「阿蝉，我今天还不错！刚在渔夫家的冰箱里吃了一顿…你呢？」）→ 阿蝉再发两句 → 退出。`data/chat/2026-11-06.jsonl` 里 `room_open`、5 条 `message`（`controller` human / agent）、`player_exit` 全在；`GET /history/chat` 一致（截图 `E12_achan_chat.jpg`）。**没做到的**：她对后两句 90 s 内没有再回复——C 的 agent 在房间里的发言由其 think 节奏决定（接受时那句是 respond 自带的 message），不是前端问题；见 §4 给 C |
| 3 | E13 | 完成 | `/replay?town=main&date=2026-11-06[&speed=1\|8\|60\|fit][&export=1]`：只读 A 的 `data/dataset/<town>/<date>/{state,episodes,events}.jsonl` + B 的 `run/data/sandbox/{actions,chat,state}/<date>.jsonl`（Vite 只读目录中间件 `/dataset` `/sandboxdata`，白名单后缀、拒绝 `..`），地图几何取 `GET /world?fields=tiles,objects` 一次。单张 1600×900 画布：左地图 + 鲸仔位置 / 轨迹（有 state 位置样本用样本，样本开始前按 `move / move_to_area` 近似推算并标注）、右上七变量折线（固定顺序配色，图例带当前值）、「她在想」（episodes 的计划 / 想法 / 模型 / 费用）、「发生了什么」（记忆写入 / 行动 / 聊天倒序 11 条）、底部时间轴（思考与聊天刻度）；可拖动、1× / 8× / 60× / 整天压 60 s。**导出**：`MediaRecorder` 录画布 → `replay_<town>_<date>.webm`。11-06 主镇：七变量 30 点、思考 71 段、记忆 60 条、行动 372 条、聊天 5 条；导出 **60.96 s、1600×900、VP8 30 fps、8.9 MB**（`/tmp/pw/shots/replay_main_2026-11-06.webm`，中途 30 s 处正好是全天中点 09:18，截图 `E13_replay.jpg`） |
| 4 | E14 | 完成 | `?town=m2a` → 前端 API 前缀改为 `/t/m2a/api`（含 ws），Vite 读 `run/towns.yaml` 的 `towns.<name>.k` 生成代理表（端口 8000+10k；`VITE_TOWNS_YAML` 可改），前端只传镇名、浏览器不直连后端。信息面板名字行带 `[m2a]`。实测 `http://127.0.0.1:5174/spectate?town=m2a&follow=鲸仔` → `transport=ws`、`online`，m2a 的鲸仔当时离线所以全景（截图 `E14_town_m2a.jpg`）。矩阵格名（M2a）在 towns.yaml 里有但前端拿不到，见 §4 |
| 5 | E15 | 完成（联调通过） | 跟随目标 `/state.game.status === "playing"`（或 tag `gaming` / stateLabel 玩游戏中）时右上出小窗：第几天 / 时段 / 生命 / 饥饿 / 理智 / 死亡 / 局 id，并从 `/gameruns/<run_id>/` 取最新 `.gif/.png`（D 的 `tools/replay.py` 产物）。**联调一局**：以阿蝉走到 `game_console_whale`(10,11) 旁按 E → 后端 `stateLabel`「阿蝉 玩游戏中」、`game = {status: playing, run_id: run-1793933517, day 3, phase day, health 150, hunger 70.5, sanity 137.6}` → 旁观页小窗如实显示（截图 `E15_game_window.jpg`）→ 按 Q 离开 → `game` 清空。该局 D 的 runs 目录里还没有 GIF，小窗只显示指标。新增 `game_console` 物品图 |
| 6 | E16 | 完成（待主播确认） | `&layout=live`：右下留 Live2D 安全区（= `safe=br`，字幕底中、信息面板左下、时钟右上、游戏机小窗右上时钟下）；`&layout=full`：全屏默认。配色按 W4 反馈已柔和化，本周没再改。截图 `E16_layout_live.jpg` / `E16_layout_full.jpg`。**主播确认见 §2** |
| 7 | 报告 | 本文 | — |

## 2. 主播确认（E16 / E11）

【待填：本次会话结束前向主播确认，答复写在这里】

## 3. 测试与结果

| 项 | 结果 |
|---|---|
| `npm test` / `npm run build` | 通过 / 通过 |
| E12 | 见 §1 第 2 行：真 agent 4 s 接受并回复一句；chat JSONL 9 行（含两次 60 s 超时的 `request_expired`——那两次是她在 30 格外、我先用后端 `move_to_area` 没走到她身边，于是改成客户端 BFS 真走过去） |
| E13 | 导出 webm 用浏览器 `<video>` 核验：duration 60.96 s、1600×900；中途截图时刻 09:18 ≈ (07:25 + 11:10) / 2 |
| E14 | `/t/m2a/api/world` 200；旁观页 ws 经代理连 8010 成功；路径穿越 `/dataset/../..` 与 `%2e%2e` → 403 |
| E15 | 8/8 步骤：走到 → 面向 → use → stateLabel / game 指标 → 旁观小窗 → leave → 清空 |
| 键盘 | 发现 Playwright 的 `keyboard.press`（按下即抬起）在无头低帧率下会被 Phaser 的 `JustDown` 漏掉，真人按键 ≥ 1 帧没问题；自动化改用 down → 120 ms → up |

## 4. 给其他会话

1. **给 C**：阿蝉在房间里的后续发言，鲸仔的回复要等她下一轮 think；如果希望「聊三轮」有来有回，请让 chat_session 在房间 active 期间以更短周期（≤ 15 s）轮询 `GET /chat/room/{id}?since_seq=` 并回复，或在 perceive 里把「房间有新消息」提升为打断条件。前端这边不改。
2. **给 B**：① `GET /world` 加 `zone_names`（W4 已提，仍需要）；② `/ws/world` 的 `players.upsert` 带 `game`（status / day / phase…），现在小窗靠 1 s 轮询 `/state`；③ 回放页想要 `GET /admin/export` 的 `state` 行（W6 已有），运行台切 W6 后 `data/state/` 已开始落盘，11-06 11:05 以后的位置是精确的；④ `move_to_area` 对大区域（grass）会停在离出发点最近的格，不适合「走到某人身边」——前端已自己 BFS，不需改。
3. **给 A**：回放页读 `data/dataset/<town>/<date>/` 的 `state.jsonl`（kind=sample/history 都认 `ts` + `vars`）、`episodes.jsonl`（`window.from/to`、`plan`、`thought`、`think.model/cost_usd`）、`events.jsonl`（`time`、`description`）。如果 schema 0.3 改字段名请知会；另建议导出里加 B 的 `actions / chat / state`（现在我直接读 `run/data/sandbox/`，只有主镇能这么做）。
4. **给 D**：游戏机小窗读 `runs/<run_id>/*.gif|png` 的最新一张；若 `tools/replay.py` 能在局中每 N tick 出一张 `latest.png`，直播画面就能看到局内俯视图。
5. **给总控**：运行台 5173 切到本报告之后的最新提交（`npm run build && npm run preview`）；`run/towns.yaml` 里 `k` 值变动会自动进代理表（重启 preview 生效）。

## 5. 假设

- v2 形象在 16×24 里只能保留轮廓特征（头饰、鳍耳、围裙、鲸尾；猫耳、领带、工牌、猫尾），颜色取立绘主色；是否够像由主播定。
- 回放页位置近似：`move_to_area` 落到区域质心最近的可走格，`move_n` 按 `steps` 全走成功；只用于 11-06 11:05 前没有 state 样本的时段。
- 回放时间轴以当天有记录的最早 / 最晚时刻为界（不是 00:00–24:00），整天压 60 s。
- 分档阈值 10 / 15 / 25 取自 A 的 `state.jsonl.thresholds`（emergency / critical / low），60 以上记「不错」是我加的。
- 多镇代理只读 `towns.yaml` 的 `k`，不读 `self_port`；镇名只允许 `[a-z0-9_-]`。

## 6. 提交号与运行方式

| 项 | 值 |
|---|---|
| 代码 | `whale-frontend` @ `e3887ae`（基于 B 的 `59d1ac8`）；总控起 5173 请用分支最新提交 |
| 新增页面 | `/replay?town=&date=&speed=&export=1` |
| 新增参数 | `/spectate?…&town=m2a`、`&art=v1`、`&layout=live\|full`、`&panel=0` |
| 新增环境变量 | `VITE_TOWNS_YAML`、`VITE_DATASET_DIR`、`VITE_SANDBOX_DATA_DIR`、`VITE_GAME_RUNS_DIR`（默认值见 `vite.config.ts` 顶部注释） |
| 素材再生成 | `python3 tools/gen_assets.py`（v1 / v2 两套都出） |
| 文件 | 新增 `src/replay/{ReplayApp.tsx,data.ts}`、`src/game/systems/{GameWindow,InfoPanel}.ts`、`report_shots/*`、`ref/*`（主播提供）；修改 `tools/gen_assets.py`、`src/game/assets.ts`、`ActorSprite`、`UIScene`、`InfoPanel`、`ChatPanel`、`HUD`、`TickSystem`、`InputSystem`、`GameScene`、`api/{client,world,chat}.ts`、`spectate/params.ts`、`vite.config.ts`、`types` |

---

# W4 · 2026-11-06：版权与自制素材、真地砖、思考字幕、WebSocket（原报告）

## 1. 进度（任务 1–7，含 6b）

| # | 编号 | 状态 | 做了什么 |
|---|---|---|---|
| 1 | E6a | 完成 | 许可原文核实（§2），结论：**移出 git + 全部换自制 CC0**。Sunnyside 两张 tileset 与借用它的角色帧（`player_walk/idle/player.png`）已 `git rm`；`.gitignore` 加 `front_end/public/assets/tilesets/`、`vendor/`。历史里仍有这几张图，要不要重写历史由总控定（§5） |
| 2 | E6b | 完成 | `tools/gen_assets.py`（PIL，确定性，约 440 行）程序化生成：**7 套角色四向走路表**（鲸仔蓝白发+头顶背鳍+背面鲸尾鳍；阿蝉白发白猫耳蓝衬衫领带蓝发卡；厨子/杂货商/渔夫/常客/村民）、**19 个物品**（bed、bed_21、bath、fridge、desk、stream_desk 带监视器与红灯、desk_12、book、phone、restaurant_table、bench、fishing_spot、shop_counter、sofa、cook、sink、toilet、well、tree），全部由脚本画，CC0。物品按 `type` 取图，没有同名图才退回旧图或色块；当前运行台地图 **0 个占位块**（截图 `art_pan2.png`）。角色按名字选：鲸→whale、阿蝉→achan、厨/杂货/渔/常客→对应 NPC，其余按名字哈希稳定分配，人类玩家默认阿蝉 |
| 3 | E7 | 完成 | 自制 18 格地砖集 `gen/tiles.png`：草（三种 + 小花）、公园草丛、街道碎石、广场石板、码头木板、室内木地板、厨房/浴室瓷砖、餐馆红毯、杂货店地面、砖墙顶/墙面、水 4 帧动画、门。渲染规则按 **tile 类型 + arena**（街道/广场/码头/公园按区域；室内按厨房/浴室/餐馆/杂货店分地板；墙按下方是否为墙分顶/面）；水面 240 格用动画精灵按位置错相位流动。**区域名**：进入新区域顶部淡入「阿蝉家 · 小仓库」（2.5 s），小地图画出 7 个 sector 的中文名，HUD 位置列改中文。B 的 `tiled` 现在指向 Sunnyside 且 gid 是假设值（画出来是蓝色地板和一排蘑菇），所以前端**只在 `tilesets[0].imageSource === "gen/tiles.png"` 时采用 `tiled` 按 gid 画**，否则按类型画——B 落地 6b 后两条路出图一致 |
| 4 | E8 | 完成 | `ThoughtBar`：Vite 代理 `/observe` → `VITE_OBSERVE_TARGET`（默认 `http://127.0.0.1:8002`，路径不改写），每 2 s `GET /observe/latest`，画布底部「鲸仔正在想：…」打字机、≤ 40 字、最后一次变化 8 s 后淡出，`needs_lines` 前两条作第二行小字。**只读 `thought` / `needs_lines` / `ts` 三个字段**，其余（含将来任何 raw / danmaku）在 `api/observe.ts` 里显式丢弃；用 mock 服务放了一个 `raw_danmaku` 字段验证 DOM 与画布都没出现（`thought.png`）。8002 没起时静默（退避到 30 s），不显示任何提示。C 的 8002 本次会话期间未运行，**运行台联调待 C 起服务** |
| 5 | E9 | 完成 | `WorldFeed`：首选 `GET /ws/world`（经 Vite 代理 `ws: true`），处理 `snapshot` / `patch`（worldState 增量、players upsert/remove、objects 使用状态、`chat` → 气泡、`action` → 事件总线）、`heartbeat`；15 s 无消息视为死连接。**断线立刻退回** `GET /world?fields=players,objects,worldState` 500 ms 轮询（实测 82 ms），ws 按 2→30 s 退避重连，snapshot 一到就停轮询；`mapVersion` 变了重拉一次全量。对账：ws 状态与 `GET /world` 位置一致（§3） |
| 6 | 直播机验收 | 完成 | 主播本机 144 Hz 显示器实测 **144 fps**。**11-06 主播在直播机看 5173 后的三条反馈**（原话见 §2.1）：① 当时鲸仔没在行动，看不出具体内容；② 希望专门做一个游戏式 UI 放基础信息，名字可以同时留在头顶；③ 优先调整：鲸仔 / 阿蝉形象更像 Live2D、地砖 / 房子颜色更柔和。**本轮已做**：②→ 左下角游戏式信息面板（名字、区域、正在做什么、七变量条，`&panel=0` 关；头顶名字牌保留，跟随目标头顶不再重复画小条）；③ 后半→ 草 / 墙 / 水 / 红毯 / 木地板整体降饱和（`panel_follow.png`）。**下周第一项**：③ 前半，逐像素重画鲸仔 / 阿蝉 16×24 帧向 Live2D 形象靠（或接主播手绘帧）。① 是 agent 当时空闲，运行台 5173 切到新提交后可用 `&stats=1` 配合看 B 的行动日志 |
| 6b | tiled gid | 完成（待 B 落地） | `front_end/public/assets/gen/tile_gids.json`（内容见 §4.1）：顶层键就是 B `gen_map.py` 的 `TILE_GIDS` 覆盖格式；`_tileset` 是我这张图的 Tiled 描述，请 B 把 `TILESET` 常量换成它（或改成从同一文件读）。B 切过去之后 `tiled` 非 null 且前端按 gid 画，与按类型画的结果相同 |
| 7 | 报告 | 本文 | — |

## 2. E6a 许可原文与结论

### 2.1 主播反馈原话（2026-11-06，直播机看 5173 = `d0afc9f`）

- 「鲸仔没有在行动，我看不到具体内容」
- 「最好专门做一个 UI 放基础信息，类似游戏一样。名字可同时以定在头上」
- 优先调整：「鲸仔 / 阿蝉形象更像 Live2D」「地砖 / 房子颜色更柔和」

处理见 §1 第 6 行。


来源：https://danieldiggle.itch.io/sunnyside （作者 danieldiggle，Name your own price，2026-11-06 抓取）。

> **NEW LICENCE: V1**
> "This asset pack can be used in free and commercial projects. You can modify the assets as you need."
> "Credit is not necessary, but always appreciated."
> "You can redistribute the assets as part of tutorials or educational courses as long as a link to the Sunnyside World itch.io page is included: https://danieldiggle.itch.io/sunnyside."
> "You may not repackage and resell the assets, no matter how much they are modified - this includes as NFT's."
> "You may not use these assets to train AI."
>
> **PREVIOUS LICENSE: V0.1**
> "This asset pack can be used in free and commercial projects. You can modify the assets as you need."
> "Credit is not necessary, but always appreciated."
> "You may not repackage, redistribute or resell the assets, no matter how much they are modified - this includes as NFT's."

仓库里的文件名是 `SunnysideWorld_Tileset_V0.1.png`，即 V0.1 时期下载的；V0.1 **禁止任何再分发**，V1 只放开「教程 / 教学课程」场景。公开的开源仓库把原图放在 `public/assets/` 里属于再分发，两版都不允许；且 V1 明文禁止用这些素材训练 AI，公开仓库也无法约束下游。**结论**：三选一里取「自制」为主、「移出 git」为辅——工作树里已删除并 gitignore，画面全部换成 `tools/gen_assets.py` 生成的自制 CC0 素材；git 历史里仍有这两张图（`7f319e1` 起），是否 `filter-repo` 重写由总控决定（会改所有人的提交号，建议在 W4 末各分支合并后统一做一次）。

## 3. 测试与结果

| 项 | 结果 |
|---|---|
| `npm test` / `npm run build` | 通过 / 通过 |
| ws 通道 | 旁观页 `transport=ws` 后 5 s 内 **0 次** HTTP `/world`；杀转发器后 **82 ms** 退回轮询（要求 ≤ 10 s），断线期间 `connection=offline`；恢复后 4.1 s 轮询在线、4.1 s ws 回来；ws 状态与 `GET /world` 的 players 位置一致；0 pageerror（`/tmp/pw/ws.mjs`） |
| 思考字幕 | mock `/observe/latest` 轮换三句，画布显示打字机字幕与 needs 小字；响应里夹带的 `raw_danmaku` 未出现在 DOM（画布只画 thought）；无 8002 时无任何可见提示 |
| 画面 | 全景 / 跟随 / 操控三张截图（`art_pan2.png`、`art_follow2.png`、`art_play.png`）：街道、广场、公园、码头、河、六栋房子的地板分材质、物品全部有图、角色各不相同、区域名淡入、小地图带区域名 |
| 帧率 | 无头软件 WebGL 53–56 fps（比上周多了 240 个水面动画精灵，没有明显下降）；真 GPU 上周 144 fps |

## 4. 给 B 的需求 / 交付

### 4.1 `game/maps/tile_gids.json`（E 交付，B 落地）

文件在本分支 `front_end/public/assets/gen/tile_gids.json`，B 复制到 `back_end/game/maps/tile_gids.json` 即可被 `gen_map.py` 的覆盖口读到；`_tileset` 请替换 `TILESET` 常量。内容：

```json
{
  "grass": 1,
  "grass1": 18,
  "wall": 9,
  "floor": 7,
  "object": 7,
  "water": 11,
  "_tileset": {
    "name": "whale_gen_tiles",
    "firstgid": 1,
    "tilewidth": 16,
    "tileheight": 16,
    "tilecount": 18,
    "columns": 8,
    "imageSource": "gen/tiles.png",
    "imageWidth": 128,
    "imageHeight": 48,
    "margin": 0,
    "spacing": 0
  },
  "_arena_gids": {
    "park": 3,
    "square": 5,
    "dock": 6,
    "road": 4,
    "kitchen": 8,
    "regular_bath": 8,
    "cook_kitchen": 8,
    "rest_kitchen": 8,
    "dining": 15,
    "grocer_shop": 16
  },
  "_wall_face": 10,
  "_water_frames": [
    11,
    12,
    13,
    14
  ],
  "_note": "自制 CC0 地砖（front_end/tools/gen_assets.py）。顶层键是 B 的 TILE_GIDS 覆盖；_ 开头的是给前端/人的说明。"
}
```

### 4.2 其他

1. **`GET /world` 暴露 `zone_names`**（map.json 里已有 `zone_names`）：前端现在复制了一份 `gen_map.py` 的 ZONE_NAMES（`src/game/map/zones.ts`，**假设**不常变），B16 续加区域时会对不上。放在 `worldState` 旁边或 `tiles` 同级都行，只读。
2. 已满足、本周接入：`players[].stateLabel/tags/usingObjectId/pos_seq`（叠加层不再猜）、`?fields=`（轮询退路 10 KB）、`mapVersion`（换图重拉）、`/ws/world` 含 `chat`/`action`、`agent_id`（follow= 直接匹配）、心跳改 POST（旁观端本来就不碰 `GET /player/{id}`，现在作者页也不会把离线 agent 标回在线）。
3. 低优先：ws `patch.players.upsert` 里带 `pos_seq`（已有）之外，若 `action` 事件带 `object_type`，前端可以不用再按 id 查 objects。

## 5. 卡点与需要总控决定的事

- **git 历史重写**：Sunnyside 文件仍在历史里（见 §2），是否 `git filter-repo` 由总控定；做之前请通知 B / C，所有分支提交号会变。
- **C 的 8002 未运行**：E8 只在 mock 上验证；C 起 `ui_server --observe` 后请总控在运行台 5173 的 `/spectate` 看一眼字幕（预期 2 s 内出现）。
- **形象向 Live2D 靠**（主播反馈③）：程序化像素画精细度有限，下周在生成器里逐像素改鲸仔 / 阿蝉的 16×24 帧，或接主播提供的手绘帧（同样放 `gen/`）；请主播给一张 Live2D 立绘参考。
- 运行台 5173 现为 `d0afc9f`，**没有**本周内容（素材 / ws / 字幕）；请总控切到本报告之后的最新提交并 `npm run build && npm run preview`。

## 6. 提交号与运行方式

| 项 | 值 |
|---|---|
| 代码 | `whale-frontend` @ `4c821f7`（基于 B 的 `59d1ac8`）；总控起 5173 请用分支最新提交 |
| 新增参数 | `/spectate?...&safe=br`（安全区）、`&thought=0`（关字幕）、`&panel=0`（关信息面板）、`&panzoom=0.34`（全景 2/6 更大） |
| 新增环境变量 | `VITE_OBSERVE_BASE`（默认 `/observe`）、`VITE_OBSERVE_TARGET`（默认 `http://127.0.0.1:8002`） |
| 素材再生成 | `cd front_end && python3 tools/gen_assets.py`（只依赖 Pillow） |
| 文件 | 新增 `tools/gen_assets.py`、`public/assets/gen/*`（30 个文件）、`src/game/assets.ts`、`src/game/map/zones.ts`、`src/game/systems/{WorldFeed,ThoughtBar}.ts`、`src/api/observe.ts`；修改 `TileMap`、`ActorSprite`、`GameObjectSprite`、`GameScene`、`UIScene`、`Overlay`、`TickSystem`、`store`、`types`、`HUD`、`Minimap`、`vite.config.ts`、`params.ts`；删除 `public/assets/tilesets/*`、`sprites/player_*.png` |

---

# W3 · 2026-11-06：E1–E5 全部完成（原报告）

## 1. 进度

| # | 编号 | 状态 | 做了什么 |
|---|---|---|---|
| 1 | E1 | 完成 | 分支 + worktree；`npm run dev -- --port 5174` 连运行台 8000；`npm run build` 通过；`npm test` = `tsc --noEmit` + `eslint .`（新增 `eslint.config.js`：typescript-eslint + react-hooks）；build 拆 `phaser` / `react` 两个 vendor chunk |
| 2 | E2 | 完成 | **客户端预测**：按键当帧起步并播走路动画，`POST /action` 回包后校正，被拒回弹到「服务器位置 + 剩余在途位移」；**长按连走**不等回包（300 ms/格 ÷ moveSpeed，最多 3 个在途请求）；**他人插值**：`ActorSprite` 沿网格路点匀速走，积压 > 3 格自动加速追赶，> 12 格视为瞬移直接贴；**轮询**改为 `GET /world` 500 ms 为主（players / objects / worldState 都从它取），`GET /player/{id}` 1 s（心跳 + 七变量 + 位置校正），`GET /history` 2 s |
| 3 | E3 | 完成 | `API_BASE` → `VITE_API_BASE`（默认 `/api`），`vite.config.ts` 的 dev / preview `server.proxy` 把 `/api` 转到 `VITE_PROXY_TARGET`（默认 `http://127.0.0.1:8000`），`server.host=true` 让 LAN 可达。后端仍只听 127.0.0.1（`ss -ltnp` 核实），同时绕开了后端 CORS 只放行 5173 的限制 |
| 4 | E4 | 完成 | `/spectate?follow=<name\|id\|agent_id>&hud=0`：不 join、不弹登录框、只发 GET（`/world` + 只读 `/player/{id}/state`，**不**碰会刷心跳的 `/player/{id}`）；画布 1920×1080 `Scale.FIT` 居中；镜头指数平滑跟随，目标不在场或 `online=false` 时 0.5 s 内切全景、回来即再跟随；相机夹紧地图不露黑边；`bg=transparent` 给 OBS；轮询器失败指数退避（≤ 5 s）永不停止，后端重启不白屏 |
| 5 | E5 | 完成 | 画布内叠加层：名字牌、状态标签（自己用 `stateLabel`；别人从 `objects[].userList` + effects 的 tag 推断「💤 睡觉中 / 🍴 吃饭中 / 📺 直播中 / 💬 聊天中」）、聊天气泡 8 s、七变量小条（旁观跟随目标；`bars=all` 全员）、日夜色调（按 `worldState.time` 小时连续插值，乘法混合）、天气（雨粒子 / 多云灰）、画布内时钟（`hud=0` 时默认开）。标签 / 气泡随相机 zoom 反向缩放，屏幕上恒定大小 |
| 6 | 报告 | 本文 | — |

另外顺手做的（都在 `front_end/`）：
- `TILE_SIZE` 90 → **96**（= 16 px 源图块 × 6），相机 zoom 吸附到 1/6 的整数倍，像素整数缩放；背景按 10×10 格 chunk 烘焙成画布纹理（避免 4800×4800 单张超出 OBS/CEF 纹理上限）。
- B16 新地图目前 `tiled: null`，走色块回退渲染（grass / grass1 / floor / wall / water / object 各有颜色和一点肌理），同样烘焙成 chunk；无 sprite 的物品画成带图标和名字的圆角块（E6 换美术前的占位）。
- 地图签名变化（换图 / 后端重启）时运行中重建背景与物品，旁观端不用刷新。
- 操控模式：`/player/{id}` 404（后端把人清了）时用登录名自动重新 join，不回登录框；WASD 也能走；HUD 改显示七变量 + emotion_tags；小地图画别人。
- 调试钩子：`window.__whaleStats`（每秒 fps / actors / 连接状态 / 相机模式）、`window.__whaleDebug`（自己像素位置、在途请求、他人列表），Playwright 测量用。

## 2. 提交号与运行方式

| 项 | 值 |
|---|---|
| 代码 | `whale-frontend` @ `cc86a0d`（基于 B 的 `4d6a931`）；总控起 5173 请用分支最新提交 |
| 开发 | `cd front_end && npm install && npm run dev`（默认 5173；自测 `-- --port 5174`）。**运行台建议用 `npm run build && npm run preview -- --port 5173`**（静态产物 + `/api` 代理，无 HMR 风险，见 §3.3） |
| 产物 | `npm run build` → `dist/`；`npm run preview` 同样带 `/api` 代理 |
| 检查 | `npm test`（tsc + eslint） |
| 环境变量 | `.env.example`：`VITE_API_BASE`（默认 `/api`）、`VITE_PROXY_TARGET`（默认 `http://127.0.0.1:8000`）、`VITE_PORT` |
| 直播机浏览器源 | `http://192.168.2.17:5173/spectate?follow=鲸仔&hud=0`（1920×1080）；透明背景加 `&bg=transparent`；显示帧率加 `&stats=1`；全员七变量条 `&bars=all`；跟随 zoom `&zoom=0.667`（默认 2/3 = 64 px/格），全景 zoom `&panzoom=`（默认按地图自适应） |
| 作者操控 | `http://127.0.0.1:5173/` 登录框输名字（阿蝉） |

## 3. 测试命令与结果

本机没有图形浏览器，用 Playwright 1.49 + Chromium headless shell（装在 `/tmp/pw/`，**软件 WebGL**，比真 GPU 慢）验证；脚本 `/tmp/pw/{run,reconnect,chat,soak}.mjs`，截图 `/tmp/pw/shots/`。

### 3.1 帧率与延迟的测量方法
- **帧率**：`GameScene.update` 每秒读 `game.loop.actualFps` 写到 `window.__whaleStats.fps`，`?stats=1` 时画布左下角直接显示；Playwright 定时 `page.evaluate` 取值。
- **按键到起步**：在页面里 `dispatchEvent(keydown ArrowRight)` 后逐帧 `requestAnimationFrame` 读 `__whaleDebug.selfPixel()`，数到像素位置第一次变化经过的帧数。
- **预测一致性**：连按方向键撞墙 2.5 s，停 1.5 s 后比较 `__whaleDebug.selfTile()` 与 `GET /world` 里自己的 `position`。
- **轮询量**：Playwright 监听 `request` 事件按路径计数。
- **断线重连**：运行台 8000 不能动，所以起了一个 `127.0.0.1:8001 → 8000` 的 TCP 转发（`/tmp/pw/forward.py`），5175 开发服务的代理指向 8001，杀掉 / 重启转发器 = 后端重启。

### 3.2 结果（2026-11-06，headless swiftshader，1920×1080）

| 项 | 结果 |
|---|---|
| 旁观 fps | 无头软件 WebGL：单页 58–59；3 个无头页并开时 37–52。**主播本机真 GPU（144 Hz 显示器）实测 144 fps**（`&stats=1` 截图，2026-11-06 09:42），即 1080p 60 fps 有一倍以上余量；没有限帧，OBS 浏览器源按自己的 60 Hz 取帧 |
| 操控 fps | 51–53（同上，软件 GL） |
| 按键 → 起步 | **1 帧（2 ms）**，像素位置下一帧即变化 |
| 长按 2.0 s + 1.2 s | 服务器位置 (6,9) → (13,13)：7 + 4 格，与 300 ms/格一致 |
| 撞墙 2.5 s 后本地 / 服务器 | 四个方向各撞一次 + 同场景重复 3 次：**7/7 一致**，history 里只多出 `tile_not_walkable` 的失败记录，无回弹残留。另有 1 次在我改源码触发热重载的瞬间测得差 1 格（未能复现）；已加 `window.__whaleTrace`（最近 200 条 send / ack / reconcile / poll-correct），再出现可直接读 |
| 旁观 5 s 内请求 | `/world` ×10、`/player/{id}/state` ×5，没有别的接口 |
| 断线 | 杀转发器 12 s 后 `connection=offline`，画面保留最后一帧 + `hud=0` 时无提示（`hud=1` 时顶部红条）；恢复后 **5.0 s** 内 `online`，期间 0 个 pageerror |
| 聊天 | 两个人类玩家邀请 → 接受 → 互发消息，双方画面上出现「💬 聊天中」标签和 8 s 气泡（截图 `chat_bubbles.png`）；旁观端只能看到标签，**看不到气泡**（见 §4 需求 2） |
| 跟随 / 全景 | `follow=鲸仔` 跟随中；无 follow 或目标离线 → 全景（整图 60×40 格在 1/6 zoom 下 960×640 居中） |
| `npm test` / `npm run build` | 通过 / 通过（`index` 67 kB、`react` 142 kB、`phaser` 1.48 MB，gzip 合计约 410 kB） |

### 3.3 1 小时旁观 soak（`/tmp/pw/soak.mjs`，日志 `/tmp/pw/soak.log`）

对象：`vite preview` 的**生产构建**（5177，`/api` 经代理 → 8001 转发器 → 运行台 8000），页面 `/spectate?follow=鲸仔&hud=0&stats=1`，1920×1080，00:22–01:23 UTC（北京 08:22–09:23）连续 60 分钟不刷新；每分钟记 fps / 连接 / JS heap / DOM 节点 / 游戏时间，第 20、40 分钟各杀转发器 15 s 模拟后端重启。

| 指标 | 结果 |
|---|---|
| 掉线 / 白屏 | **0**；60 个采样点全部 `online`（两次人为断线各 15 s 落在采样点之间） |
| 模拟后端重启 | **2/2 恢复**：断线期间状态为 `offline`，转发器回来后 3.7 s / 2.8 s 内回到 `online`（退避上限 5 s） |
| 页面错误（pageerror） | **0** |
| JS heap | 6.4–16.6 MB 来回波动（GC 锯齿），前 3 分钟 7.6 / 11.8 / 9.5，后 3 分钟 15.6 / 13.8 / 11.8，无上升趋势 |
| DOM 节点 | 恒定 98–104，无增长 |
| 跟随 / 全景切换 | 期间运行台的鲸仔 agent 真实掉线 5 次（后端 `online=false`）：每次 1 分钟内切全景、回来后 1–4 分钟内（取决于 agent 重拉时间）再跟随，共 10 次切换全部正确 |
| fps（软件 WebGL） | 中位 43.7，最高 60.8，最低 23.5（与我在同机并行跑的其他无头测试撞车的那一分钟） |

第一次 soak 作废：跑在 5175 **开发服务**上，我中途改源码触发 Vite 热重载，React Fast Refresh 让旁观页的轮询器停掉但画面还在（看起来「在线」却不再更新，另带 4 条 Phaser 销毁时的 `drawImage` 报错），因此换成生产构建重跑。运行台 5173 若仍用 `npm run dev` 起，**请不要在它上面改代码**；更稳的做法是 `npm run build && npm run preview -- --port 5173`（preview 同样带 `/api` 代理）。

### 3.4 独立代码审查（另开一个会话只读 diff，找长跑泄漏与预测竞态）

9 条发现，全部已修并重跑 §3.2 的检查（提交 `9f71b20`）：旁观页在 React StrictMode（dev）下首连失败会永远卡在「正在连接」；`zoomTo` 在上一次缩放未完成时被 Phaser 忽略（目标闪断会停在全景 zoom 跟随）；多条 keep-alive 连接下 move 回包可能乱序（加 `seq`，只采纳更新的）；在途请求满时点击路径的一步被静默丢掉；回弹路径按运动方向改朝向、与服务器朝向相反；后端重启自动重新 join 后旧 id 的在途请求把人拉回旧位置（加 `InputSystem.reset`）；目标消失的 0.5 s 宽限期相机先滑向地图中心；他人 ≥ 2 格更新时中间路点被丢（改为续接）；启动后第一轮轮询多做一次地图重建。审查确认没有发现 Phaser 对象 / 监听器 / 纹理键累积之类的泄漏。

## 4. 对后端的需求清单（请总控转 B）

写报告时 B 的 `4d6a931` 已经落地了 B17 `GET /ws/world`（snapshot + patch，含 `players.upsert/remove`、`objects` 使用状态、`chat` 消息事件、`players[].agent_id`、CORS 环境变量）。对照我这周的实际需要，**已满足**：agent_id 跟随（已接）、聊天气泡的数据源（ws 的 `chat` 事件，E9 接入后旁观端就能出气泡）、轮询流量（ws 替代 `/world` 500 ms 后不再是问题）。**仍然需要** 的按优先级：

1. **`players[]`（`GET /world` 与 ws `players.upsert` 同形状）加 `stateLabel`、`usingObjectId`、`tags`**。叠加层「睡觉 / 吃饭 / 直播中」现在靠 `objects[].userList` 反查 + 按物品名正则猜（`bed → 💤`、`fridge|cook → 🍴`、`stream → 📺`），B16 新物品（餐馆、社交物品）一多就会猜错；后端已经算好的 `stateLabel` 和物品 effects 里的 `tag` 直接给出来最准。也请在 ws patch 里当作会变化的字段推送。
2. **`GET /player/{id}` 的副作用**：它刷心跳、把离线 agent 标回 `online=true`、清 `pendingMessage`。旁观端只用只读的 `/player/{id}/state`，但任何人误开一个操控页或在浏览器里点开这个 URL 就会让「鲸仔离线」在画面上消失。建议心跳改为显式 `POST /player/{id}/heartbeat`（或只对 `controller=human` 刷），`GET` 变纯只读；过渡期至少在 api-spec 标红。
3. **`GET /world` 瘦身**（在 ws 稳定前仍有用，也是 ws 掉线后的兜底）：现在 290–345 KB/次（2400 tiles + 7 层 tiled）。`?fields=players,objects,worldState` 或 `GET /world/live` 只回动态部分（< 5 KB），并在 `worldState` 里加 `mapVersion`，前端据此决定何时重拉 tiles（我现在用「tiles 数量 + 不可走格数 + 类型哈希」当签名，是**假设**）。
4. **ws `chat` 事件希望带 `kind: "message"` 的 `from_name`**（spec 示例已有，确认一下实现里有即可）；房间 `participants` 已有，前端据此把气泡挂到对应 sprite。
5. **B16 地图导出带 `tiled`**：运行台当前 `tiled: null`，前端走色块回退；E7（W4）要靠 `tiled` 渲染正式画面。
6. `move` 的回包或 `players[]` 带单调递增的 `pos_seq`（低优先）：客户端预测校正现在用「请求发出 / 回包时刻 + 本地 seq」排除乱序与旧轮询，有服务端序号更稳。
7. W4 以后：ws 推一类 `{"type":"action", "entity":..., "action":"use", "object":"fridge_01", "success":true}` 事件，前端可以播一次性动画（吃东西冒星星）。

E9（换 ws）我 W4 第一件做；接口形状按 `4d6a931` 的 api-spec §8，不需要 B 再改什么。

## 5. 假设（没有依据的决定，按规矩标出）

- 一格 300 ms（`moveSpeed=1`）沿用旧前端常量；最多 3 个在途 move。
- 他人插值积压 > 3 格加速（最多 4×），> 12 格瞬移。
- 旁观跟随 zoom 2/3（64 px/格）、全景 zoom 按地图自适应吸附到 1/6 整数倍；目标丢失 0.5 s 后切全景（agent 的 `online=false` 本身要等后端 10 s 心跳超时，所以「kill 后 10 s 内切全景」实际是 10–11 s，由后端决定）。
- 聊天气泡 8 s；状态标签文案与图标（💤🍴📺💬）；日夜色调关键帧（6:00 日出、18:30 日落、夜 `#5a6aa8` 乘法色）。
- 轮询节奏：`/world` 500 ms、`/player/{id}` 1 s、`/history` 2 s、`/player/{id}/state` 1 s；失败退避上限 5 s。
- 前端本地只在地图数据说「可走」时**预测位移**，不可走时只转身但**照样把 move 发给后端**由它裁定；这是「先动起来」的预测，不是前端判定合法性（CLAUDE.md 后端权限）。

## 6. 卡点与越界记录

- **B 的 `4369ee5` 改了 `front_end/src/types/index.ts`**（`PlayerState` 加 `walking_over`，1 行），rebase 时冲突一次，我以本分支为准（已含该值）。按契约 B 从 §3.1 B15 起不再碰 `front_end/`，请总控提醒。`4d6a931` 没有碰 `front_end/`，第二次 rebase 无冲突。
- 这个仓库没有 git 用户配置，`git rebase` 在 worktree 里会因 committer 身份缺失中断（我第一次中断后差点把半套改动揉进报告提交）；提交 / rebase 前要 `export GIT_COMMITTER_NAME/EMAIL GIT_AUTHOR_NAME/EMAIL`。建议总控在仓库里配一下 `git config user.*`。
- 本机无图形浏览器，fps 只能在软件 WebGL 下量；真 GPU 1080p 60 fps 需要主播在直播机开 `&stats=1` 看一眼。
- 运行台 8000 当前是 B16 新地图但 `tiled: null`（没有 Tiled 渲染层），画面是色块回退；需要 B 的地图导出带 `tiled`，或等 E7 在 W4 做新地图渲染。
- `public/assets/tilesets/` 的 Sunnyside World 付费素材许可问题留给 W4 E6，本周未动。
- 主播截图里房子里的「白方块」是后端给 `fridge` 借用的 `tree.png`（整张纯白 30×30）。已改：凡是借用别的物品图当占位的（fridge→tree、phone→book、stream_desk / shop_counter / restaurant_table→desk、fishing_spot→well）一律画带图标和名字的色块，不再误导观众；正式图等 E6。

## 7. 文件清单（本次新增 / 修改，全部在 `front_end/`）

新增：`src/api/client.ts`、`src/game/objects/ActorSprite.ts`、`src/game/systems/Poller.ts`、`src/game/systems/Overlay.ts`、`src/game/scenes/UIScene.ts`、`src/spectate/{params.ts,SpectateApp.tsx,SpectateHud.tsx}`、`src/ui/ConnectionBadge.tsx`、`src/vite-env.d.ts`、`eslint.config.js`、`.env.example`、本文。
修改：`vite.config.ts`、`package.json`、`src/App.tsx`、`src/api/{world,chat}.ts`、`src/types/index.ts`、`src/store/gameStore.ts`、`src/game/{EventBus,PhaserGame}.ts`、`src/game/scenes/GameScene.ts`、`src/game/systems/{InputSystem,TickSystem}.ts`、`src/game/objects/{Player,OtherPlayerSprite,GameObjectSprite}.ts`、`src/game/map/TileMap.ts`、`src/ui/{HUD,ChatPanel,Minimap,JoinScreen}.tsx`。
