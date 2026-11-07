分支 `whale-frontend`，worktree `own-repos/BASIC_SANDBOX-fe/`，已 rebase 到 B 的 `489062a`（§3.36 `910506f` 之后；W10 / W11 / 走路都已联调）。只改了 `front_end/`。截图在 `front_end/report_shots/`（W9 在 `report_shots/w9/`，美术在 `report_shots/v1art/`）。

---

# W9 · 2026-11-07：美术收尾与 v1 UI（QQ 面板、金币背包、室内过渡、主播评分）— 第 1 天 + 与 B 的 W10 联调

## 0. 联调结果（B 的 W10 `c0e75ef` 下午上线 8091 后）

全部通过，截图 `report_shots/w9/W9_integ_*.jpg`：

| 项 | 结果 |
|---|---|
| QQ 一来一回 | 操控页加入人类玩家，在 QQ 面板选「鲸仔」发文字 → 旁观页鲸仔的手机出现「E测试」会话与未读（`W9_integ_spectate_qq_unread`）；反向：阿蝉账号发给人类玩家 → 操控页面板收到 → 点「标记已读」→ `POST /qq/read` 成功、`tags: [reading]`、buff `reading +1 (57 s)` → 旁观页头顶 `📱 看手机`（`W9_integ_read_phone` / `W9_integ_play_read`）。鲸仔本人 `/qq/read` 也成功（count 1、busy 60 s），但 8091 的鲸仔 agent 没有 brain 在线、标签被「💤 离线」盖住，所以用在线的人类玩家演示 |
| 购买一次 | 传送到杂货店柜台南侧 → 背包面板列出柜台 5 种商品（鱼饵 3 / 面包 5 / 小礼物 25 / 食材 8 / 甜食 6）→ 买面包：金币 300 → 295、背包出现 🍞×1、头顶气泡 `🛒 买了🍞面包 -5 金币`、面板回显「买了 1 个面包，花了 5 金币」（`W9_integ_play_bought`）→ 吃：背包清空、气泡（`W9_integ_play_ate`） |
| 坐姿 | `use classroom_desk` 后后端把人挪到 `usePos` (5,3) 并转向 up，前端直接画服务器位置 → 人坐在课桌下沿的椅子上（`W9_integ_play_sit`）；前端按类型猜座位的逻辑在物品带 `usePos` 时不再介入 |
| 南门 | 五栋门边已在南墙正中，外观底图的门与之吻合；5 张室内底图（合租房 1F / 餐馆 / 杂货店 / 小千屋 / 老板屋）按新版式重出（门洞改到南墙）（QA：合租房 1F 0.962、杂货店 0.999、小千屋 0.949、老板屋 0.998、餐馆 0.844——餐馆两次都 0.8 左右，看叠图是模型把内墙画厚了一点、门洞位置和房间分隔都对，放行），其余 18 张尺寸位置不变直接复用（版式全部重导核对过） |
| `decor[]` | 小径（路砖）、池塘（水砖）、花坛（每格一个花坛）、晾衣绳（暂用围栏图）都渲染出来（`W9_integ_decor` / `W9_integ_overview`）；两块大草坪不再空。装饰层占的格自动避开我的撒点 |

**B 的 W11（`fc051f1`，只加字段）也接了**：ws `produce` 事件 → 头顶气泡「🎣 钓到了🐟鱼 / 🍳 做好了🍱便当 ×2 / 🎼 写完了🎵歌 / 🎬 做完了📄文稿」；ws `commission` 事件 → 鲸仔头顶「📋 新委托：餐厅老板想要《…》200 金币 / ✅ 交付了《…》+200 金币」；`use` / `buy` 新失败原因 `empty`（🧊 冰箱空了）/ `no_ingredients`（🥬 没有食材）/ `out_of_stock`（📦 卖完了）；`store` 成功气泡；商店列表显示 `shop[].stock`（实数）、0 时「卖完」并禁用买。B 随后加了 scenario op `produce` / `give_item` 与 `POST /admin/commission`，已实测：钓鱼产出 → 头顶「🎣 钓到了🐟鱼」+ 背包出现鱼（`W9_integ_w11_produce`）；往背包放一首歌 → QQ 面板下拉出现「🎵 歌（文件）」→ 发给阿蝉成功，inbox 里 `kind: file, file_ref.item: song`（`W9_integ_w11_qq_file`；第一次 422 是我把 `file_ref` 发成了字符串，按 B 的 schema 改成 `{item, name, meta}` 对象）；开委托 → 鲸仔头顶「📋 新委托：餐厅老板想要《店里要一首背景歌》 200 金币」（`W9_integ_w11_commission`，8091 没有鲸仔玩家，用名字带「鲸」的人类演示）。交付也测了（B 用 scenario `spawn` 造了餐厅老板实例）：开委托 → 背包放歌 → 传送到老板旁 → 点背包面板「送餐厅」→ 金币 300 → 488、歌离开背包、面板回显「完成委托《冒烟委托》，收到 188 金币」（匹配到的是沙盒每日自动开出的另一单，不是我那单 200 的）、头顶气泡（`W9_integ_w11_deliver`）。一个小瑕疵：give 的 action 气泡和 commission deliver 气泡几乎同时到，同一人头顶只留最后一条，所以截图里看到的是「把歌送给了餐厅老板」而不是「交付了…+188」；两条合并成一条留给下轮。`out_of_stock` / `empty` / `no_ingredients` 提示未实测。另修了一处：操控页 QQ 面板的背包下拉之前取的是渲染时的快照，不跟背包变化，改成订阅 store。

**按 B 的差异表改的**：`usePos` 是绝对格数组 + `useFacing`（不是相对偏移）→ 坐姿交给服务器位置；ws `qq` 事件平铺且分 `event: message | read`（read 只刷状态）；`decor` 用 `kind` 字段、`tiles[]`；`shop[]` 另有 `sell`（收购价）。perceive 的 `phone` 形状变化与前端无关。

## 0b. 总控追加（11-07 晚）：任务 0 自由镜头、0b 走路跟服务器、主播评分处理

全部完成，截图 `report_shots/w9/W9_free_*.jpg`、`W9_rating_*.jpg`、录屏 `W9_walk_server_20s.webm`。主镇 8000（world-v1.0 地图、六个 agent）上验的，只读。

**任务 0 自由镜头**（`/spectate?mode=free|follow|world`，默认有 `follow=` 就跟随、否则全景）

| 操作 | 实现 | 验证 |
|---|---|---|
| 拖动平移 | 画布上按住拖（> 5 px 才算拖，否则算点击）；任何拖动 / 滚轮都从跟随 / 全景切到自由镜头，保留当前镜头中心与 zoom | `W9_free_2_drag` |
| 滚轮缩放 | 以鼠标为中心缩放，档位沿用 `snapZoom`，边界 `centerClamped` | `W9_free_3_wheel_zoom` |
| WASD / 方向键 | 900 px/s ÷ zoom | `W9_free_4_wasd` |
| 小地图点哪跳哪 | 右下角内嵌小地图（`Minimap` 加 `inline / onClickTile / viewport`），画当前视口框 | `W9_free_5_minimap_jump` |
| 点建筑进屋 | 点到室内格 → `focus={sector, floor}`，走任务 4 的进屋过渡；2F 按 `SceneFocus.floorOf` 判层；在屋里点屋外 / Esc / 「🚪 出」→ 回小镇 | `W9_free_6_click_enter_home` / `W9_free_7_esc_exit` |
| 点角色跟随 | 点到人（`ActorSprite.containsPoint`）→ 跟随她；右下「跟随（点名字）」列表同样 | `W9_free_8_list_follow` |
| 全景 | 「🗺 全景」按钮 → 原来的 pan 镜头 | `W9_free_9_world` |

控件 `SpectateControls.tsx` 放右下，`layout=live` 或 `hud=0` 时不渲染、也不吃键盘（Phaser 键盘只在带控件的旁观页开——这是本轮修的一个 bug：旁观页原来整体关了键盘，WASD / Esc 都没反应）。镜头状态通过 EventBus `spectate-state` 给 React（HUD 的「旁观 · 跟随 小千 / 全景」标题跟着变），`spectate-camera` 给小地图画视口框。`__whaleDebug.state()` 看 camMode / focus / follow。

**任务 0b 走路跟服务器（B §3.36 `910506f`）**：删掉前端 `pathBetween` 猜路；`syncOthers` 收到相邻一格就 `pushWaypoint`、跳格才 `snapTo`；步速 `setStepMs(1000 / 小镇倍速)`（人类单格 300 ms），`setServerWalking(state === 'walking')` 时走路帧不因两 tick 之间的空档回 idle（1.5 s 宽限）。在 8091 加人类玩家 `move` 到 (44,24)：`path_len 60`，20 s 内采样全部相邻、最大跳 1 格、在走的比例 0.82，录屏 `W9_walk_server_20s.webm`。气泡按 §3.36 的新字段：`blocked_reason: locked` → 「咚咚咚…锁着」、`closed` → 「🚪 还没开门」、`no_path` / `move_done{outcome: blocked}` → 「🚧 走不过去」、走路中 use / interact 被拒（`reason: walking`）→ 「🚶 还在走」。

**主播评分（`data/assets/review.jsonl`，59 条，👎 4 项；与总控备份 `run/data/review-5173-backup-1107-2131.jsonl` 逐行核对一致）**

| 评 | 处理 |
|---|---|
| `villager` 为什么会有村民、和阿蝉重复 | 删掉 `chars/villager.png`，NPC 池改为 cook / grocer / fisher / regular；manifest 6 张角色表 |
| `regular`（小千）应是淡紫色长发、白+淡紫衣服、个子高、御姐、腼腆 | 重写描述重出一张（`W9_rating_xiaoqian_sheet`，游戏里 `W9_rating_xiaoqian_ingame`）；小千 / 小满都映射到 `regular` |
| 路灯顶部被截 | 路灯改用 `objects/lamp.png` 整张（96×192）单独素材，`deco --reslice` 不再覆盖它（之前被覆盖过一次） |
| `desk_long` 桌子应侧着用、椅子在侧面 | 重出：椅子在左长边（`W9_rating_desk_long`）。注：现在地图里没有物品类型用到这张，只在评审页里 |

费用：本轮 2 次调用，累计约 $19 / 200 张预算。

**总控追加（11-07 晚，主播截图）：餐厅老板被画成小千** — 原因：「餐厅老板」没命中任何名字规则，按哈希落到 NPC 池，而池里有小千专属的 `regular`。修法：名字 → 外观规则搬到无 Phaser 依赖的 `src/game/charKey.ts`，`04-npcs.md` 六个角色全部显式匹配（鲸仔 / 阿蝉 / 小千·千小满 / 餐厅老板·厨师 / 杂货店老板·老板娘 / 老渔夫），`regular` 从兜底池拿掉（池子只剩 cook / grocer / fisher）；新增 `tests/charKey.test.ts`（node:test，esbuild 打包后跑，`npm run test:unit`，已并入 `npm test`），覆盖六个名字、带 `_xxxxxx` 后缀的实例 id、一打未知名字都不会变成小千。截图 `W9_fix_cook_follow.jpg`。

## 0c. 总控追加（11-07 晚，主播「先快修」）：底图内墙 / 门与引擎格错位 → 人走真门时画面穿墙

**结论**：22 张底图里 13 张有墙 / 门的（10 栋室内 + 3 栋外观门）全部按引擎格校正，不花钱、不重出图；两段 20 s 以上的走路录屏不再穿墙。

### 1. 调试开关 `&debug=walls`

`/spectate?...&debug=walls`：引擎 `tiles` 里的 wall 格（红）、`edges` 的门 / 楼梯格（黄 / 青）、室内相邻房间之间墙上的开口＝室内门（绿）、arena 边界（白线）、格线与每 5 格坐标，半透明叠在所有东西之上，不随屋顶 / 室内视图切换。校正前后对比：`W9_0c_debug_walls_home_before/after.jpg`、`W9_0c_debug_walls_restaurant_before/after.jpg`、`W9_0c_debug_walls_owners_after.jpg`。校正前一眼能看到：合租房两扇室内门画高了半格到一格、鲸仔房↔厨房横墙高半格多、顶墙多一扇门；餐馆厨房门画在 y25（引擎 26）、左墙多一扇门。

### 2. 怎么修：`tools/rectify_backdrops.py`（量偏差 + 确定性校正，纯本地，0 次 API 调用）

试过「整体平移 / 裁切」——不可行：同一张图里不同墙段偏差方向不同（餐馆顶墙 −0.5、底墙 +0.3），没有一个平移量能同时对上；重出图也不保证（第一轮 QA 0.96 的图照样偏半格，模型把墙画得比格子薄、门往正中放）。所以**墙的位置不再信模型**：

- `measure`：按版式图把每格分成墙 / 地板 / 门 / 楼梯；沿每段引擎墙逐行统计「墙色占比」找出模型画的墙带，偏差 = 墙带中心 − 引擎格中心；墙带里非墙色的窗口是开口，配到 2 格内最近的引擎开口，配不上的记「多余开口」；外观只找正面墙上门大小的深棕色块。写 `data/assets/rectify_before.json`，叠图 `data/assets/rectify/`。
- `fix`：每个引擎 wall 格用**从同一张图量到的墙带**合成一块整格墙砖（墙带贴在格子靠房间一侧，其余用墙顶面均色 + 墙带纹理补满；优先用该格自己位置上的墙带像素，外圈大多对得准、细节保留，不干净的格用整段里最干净的一段）；模型画出引擎格以外的墙（偏进地板的部分 + 墙下阴影）用该房间离墙最远的干净地板补回；室内门的开口格铲平成地板；对外的门先贴墙砖再把模型画的门抠下来贴到引擎门格（没量到就用 `objects/door_closed.png`）；顶墙上多画的门 / 窗随墙重画消失；最后沿墙下缘 / 右缘补一条软阴影（光从左上）。外观只动正面墙的门：整面墙只有一个门大小的深棕块时（合租房：门被画在正中、离引擎门 4.8 格）剪下来连门框平移到引擎门格、原位用旁边墙面补；窗框 / 菜箱也是棕色、候选有歧义的不猜。原图备份在 `data/assets/gen-ai-raw/prefix_<name>.png`，`restore` 可还原；`fix` 永远从备份出发，可重复跑。
- 墙现在是整格厚（引擎的墙本来就是 1 格），比模型画的薄墙显得敦实一点；室外地面三张（广场 / 公园 / 码头）没有墙，不动。

### 3. 偏差表（校正前 ≥ 0.3 格 / 没画开口 / 多余开口 的全部特征；< 0.3 的 39 项不列）

| 底图 | 特征 | 引擎位置 | 校正前偏差（格） | 校正后 |
|---|---|---|---|---|
| classroom_1f_exterior | 正面墙的门 | (9, 6) | +4.01 | 未动（目测门在引擎格 ±0.5 内，人工核对） |
| classroom_1f_interior | 开口（室内门/对外门） | (9, 6) | 墙上没画开口 | 开口铲平成地板 / 门贴到引擎门格 |
| fisher_house_1f_exterior | 正面墙的门 | (52, 7) | 没找到门（窗框/菜箱同为棕色，候选有歧义） | 未动（目测门在引擎格 ±0.5 内，人工核对） |
| fisher_house_1f_interior | 开口（室内门/对外门） | (52, 7) | 墙上没画开口 | 开口铲平成地板 / 门贴到引擎门格 |
| fisher_house_1f_interior | 开口（室内门/对外门） | (52, 4) | 沿墙 -0.34 / 垂直 -0.03 | 开口铲平成地板 / 门贴到引擎门格 |
| grocery_1f_exterior | 正面墙的门 | (51, 38) | +2.28 | 未动（目测门在引擎格 ±0.5 内，人工核对） |
| grocery_1f_interior | 横墙 y=38 x∈[46,56] | — | -0.36 | 墙按引擎格重画（量到 -0.02）
| grocery_1f_interior | 开口（室内门/对外门） | (51, 38) | 沿墙 +0.06 / 垂直 -0.36 | 开口铲平成地板 / 门贴到引擎门格 |
| home_1f_exterior | 正面墙的门 | (12, 33) | 没找到门（窗框/菜箱同为棕色，候选有歧义） | home：门剪下平移到引擎格 |
| home_1f_interior | 横墙 y=28 x∈[2,9] | — | -0.92 | 墙按引擎格重画（量到 +0.10）
| home_1f_interior | 开口（室内门/对外门） | (12, 33) | 墙上没画开口 | 开口铲平成地板 / 门贴到引擎门格 |
| home_1f_interior | 开口（室内门/对外门） | (9, 24) | 沿墙 -0.79 / 垂直 -0.02 | 开口铲平成地板 / 门贴到引擎门格 |
| home_1f_interior | 开口（室内门/对外门） | (9, 30) | 沿墙 -1.15 / 垂直 -0.02 | 开口铲平成地板 / 门贴到引擎门格 |
| home_1f_interior | 多余开口（引擎没有） | 画在 (7.96, 21.21) | 宽 0.94 格 | 随墙重画消失 |
| music_room_1f_interior | 开口（室内门/对外门） | (37, 6) | 墙上没画开口 | 开口铲平成地板 / 门贴到引擎门格 |
| owners_house_1f_exterior | 正面墙的门 | (26, 46) | 没找到门（窗框/菜箱同为棕色，候选有歧义） | 未动（目测门在引擎格 ±0.5 内，人工核对） |
| owners_house_1f_interior | 横墙 y=40 x∈[22,29] | — | +0.75 | 墙按引擎格重画（复测工具未量准：0.77）
| owners_house_1f_interior | 开口（室内门/对外门） | (25, 40) | 墙上没画开口 | 开口铲平成地板 / 门贴到引擎门格 |
| owners_house_1f_interior | 横墙 y=43 x∈[22,29] | — | -0.71 | 墙按引擎格重画（复测工具未量准：-0.7）
| owners_house_1f_interior | 开口（室内门/对外门） | (25, 43) | 墙上没画开口 | 开口铲平成地板 / 门贴到引擎门格 |
| owners_house_1f_interior | 开口（室内门/对外门） | (26, 46) | 墙上没画开口 | 开口铲平成地板 / 门贴到引擎门格 |
| owners_house_1f_interior | 竖墙 x=22 y∈[36,46] | — | +0.77 | 墙按引擎格重画（量到 +0.09）
| owners_house_1f_interior | 竖墙 x=29 y∈[36,46] | — | -0.68 | 墙按引擎格重画（量到 -0.07）
| restaurant_1f_interior | 横墙 y=22 x∈[46,56] | — | -0.53 | 墙按引擎格重画（量到 -0.27）
| restaurant_1f_interior | 横墙 y=30 x∈[46,56] | — | +0.31 | 墙按引擎格重画（量到 -0.21）
| restaurant_1f_interior | 开口（室内门/对外门） | (51, 30) | 墙上没画开口 | 开口铲平成地板 / 门贴到引擎门格 |
| restaurant_1f_interior | 竖墙 x=46 y∈[22,30] | — | +0.56 | 墙按引擎格重画（量到 +0.03）
| restaurant_1f_interior | 竖墙 x=53 y∈[22,30] | — | +0.36 | 墙按引擎格重画（量到 +0.16）
| restaurant_1f_interior | 开口（室内门/对外门） | (53, 26) | 墙上没画开口 | 开口铲平成地板 / 门贴到引擎门格 |
| xiaoqian_house_1f_interior | 开口（室内门/对外门） | (16, 41) | 墙上没画开口 | 开口铲平成地板 / 门贴到引擎门格 |
| xiaoqian_house_1f_interior | 竖墙 x=12 y∈[36,41] | — | +0.34 | 墙按引擎格重画（量到 -0.05）
| xiaoqian_house_1f_interior | 开口（室内门/对外门） | (17, 39) | 沿墙 -0.30 / 垂直 +0.03 | 开口铲平成地板 / 门贴到引擎门格 |
| xiaoqian_house_1f_interior | 多余开口（引擎没有） | 画在 (16.59, 36.33) | 宽 0.62 格 | 随墙重画消失 |

72 项特征里校正前 33 项不合格；校正后墙 / 开口 / 门的位置由引擎格**构造保证**（墙砖、开口、门都按格贴），复测工具对已校正图量到的墙偏差多数 < 0.3（上表括号里），量不准的两处（店主们的家两道横墙）是工具把白瓷砖地板当成了墙色——叠图目检没问题（`W9_0c_debug_walls_owners_after.jpg`）。外观门：合租房已移；教学楼 / 图书馆 / 琴房 / 餐馆 / 小千家 / 杂货店 / 渔夫家目测在引擎门格 ±0.5 内；店主们的家目测偏左约 0.4 格、工具两个候选有歧义没动——**请主播 / 总控看一眼要不要动**。

### 4. 验收录屏（8091，B §3.36 走路，服务器逐格推进）

| 录屏 | 路线 | 结果 |
|---|---|---|
| `W9_0c_walk_home_room_to_kitchen.webm`（跟随） | 鲸仔房 (4,23) → 客厅门 (9,24) → 客厅 → 厨房门 (9,30) → 厨房 (5,31)，19 格 | 两扇门都从画出来的开口走过，不穿墙（`W9_0c_walk_home_mid.jpg`：人正站在 (10,24) 门后）；`..._debug` 版带 `debug=walls` 叠层 |
| `W9_0c_walk_fisher_home_to_dock.webm`（自由镜头停在渔夫家门口） | 渔夫卧室 (49,3) → 家门 (52,7)→(52,8) → 小巷 → 码头 (55,12)，15 格 | 从画出来的门走出、沿巷子到码头，不穿墙。渔夫家对非主人常锁，用 scenario `spawn agent_id=npc_fisher` 放的渔夫走；8091 没有 brain、旁观页把他当离线不跟随，所以用自由镜头 |

两条路线每 0.5 s 采样精灵格坐标都与服务器路径一致（相邻格、无跳格）。前后对比图：`W9_0c_before_after_interiors.jpg`、`W9_0c_before_after_exteriors.jpg`、全镇 `W9_0c_world_after.jpg`。

### 5. 没做 / 留给下轮

- 3/4 俯视墙体有高度、人站墙下一格会与墙面重叠：没动 depth 排序（人物与底图之间现在是人物恒在上；要「北墙前、南墙后」得把墙从底图拆成独立精灵，不是快修范围）。
- 费用：本项 0 次 gpt-image-2 调用；累计仍约 $19。

## 0d. 总控追加（11-08 早，主播截图）：「鲸仔边睡觉边行动」

沙盒侧数据干净（sleeping 只在她 using 床时出现）；问题在前端：头顶标签把 `/state` 轮询来的 `tagsHint`、`players[].tags` 与 `objects[].userList` 反查合在一起，起床走开后后两者可能滞后几秒，标签仍「💤 睡觉中」，而睡姿贴床逻辑同样用 userList 兜底，于是睡姿跟着精灵滑。改法（`src/game/stateLabel.ts`，从 GameScene 拆出来的纯函数 + `tests/stateLabel.test.ts` 6 例）：

- `state === walking` 时标签与姿势一律按走路：忽略 sleeping / eating / sitting 的 tags 与 userList 兜底（`walking_over` 仍显示「走过去聊」）；`tagsHint` 只在 `using / idle` 时参与；userList 反查只在 `using`（或老后端没有 state 字段）时信。
- `ActorSprite`：服务器说在走（两步之间精灵可能短暂静止）就不播睡 / 坐帧、不贴床；走 ↔ 停切换时重算姿势。
- 8091 复现（`/tmp/pw/sleepwalk.mjs`：人类玩家 use bed_whale → scenario release → move）：起身第一帧即站立 / 走路帧、`anchored=false`，沿途标签空；睡觉本身仍正常贴床显示「💤 睡觉中」。8091 的人类玩家数据没有滞后，所以旧版在这条路径上也看不出问题；真正的滞后只在主镇 agent 的 ws / 轮询时序上出现，按总控的分析改成「以 state 为准」后与数据时序无关。

## 0e. 总控追加（11-08）：敲门 §3.40 前端初版（§3.41 改版待 B 定稿后调整）

按 B 70fc870 / api-spec §11 做了：ws `knock` → 门口「🚪 咚咚咚！X 在敲合租房的门」气泡（90 游戏秒 ÷ 倍速，画在门格上方、盖过屋顶）+ 访客头顶「咚咚咚！」；ws `door` → 门口反馈气泡（🔓 开门 / 🙅 没让进 / 😶 没人应门 / 🔒 通行证到期，6 s）+ 访客头顶；操控页 `KnockPanel`（顶部居中）：`GET /player.pending_knocks[]` + ws knock（notified / owners 含我）即时弹「X 在敲门」→ 开门 / 不开 → `POST /door/respond`；行为日志把 `knock / door_respond / door_pass_granted / door_pass_expired` 翻成文案。8091 实测截图 `W9_knock_*.jpg`（访客 E访客 敲 door_home；用 scenario `spawn agent_id=achan` 的阿蝉开门）。

**给 B / 总控的发现**：沙盒目前**不把人类玩家算主人**——人类 `E主人测` 站在客厅里，敲门 `notified` 只有阿蝉 agent，`/door/respond` 回 `not_owner`；只有 `agent_id=achan` 的实例能回应。总控说「人类玩家属 owner（阿蝉）」，§3.41 定稿时请 B 明确人类（操控页）算不算主人，否则操控页的弹窗只能看、按了会报「你不是这家的主人」（面板已这样提示）。

§3.41 收到的方向（等字段）：弹窗按钮改「隔门回一句」（输入 → respond text）/「不开」+「走到门边开门」提示，站门内侧相邻格出「开门」→ `POST /action open_door`；旁观门口气泡加主人喊话原文与门敞开 / 落锁（ws door `opened | closed`）；背包钥匙物品（`type: key`，已先加 🔑 图标）；门敞开 60 游戏秒期间可换开门态贴图。另修了操控页背包面板盖住行为日志的布局问题（背包挪到日志右边）。

## 1. 进度

B 的 W10（南门 / `decor[]` / `use_pos` / `/qq/*` / `gold` + `inventory`）**上午还没落地**：8091 的门仍在北面、`/qq/contacts` 404、`/world` 物品没有 `use_pos`、玩家没有 `gold`。所以 1–3 按交接里的接口形状把前端做好、对字段名做了宽容解析，B 落地后只需对齐字段名；4、5 已完成。

| # | 任务 | 状态 | 做了什么 |
|---|---|---|---|
| 1 | 美术收尾 | **等 B** | ① 南门：外观底图的门已全部画在南面墙正中，B 挪门边后不需要重出图，只需重导版式跑一次 QA（`flat_export` + `refinish`）；② `decor[]`：`DecoLayer` 已能渲染 B 的地图装饰层（假设形状 `{type, x, y}` 或 `{type, tiles}`；树 / 灌木 / 花 / 石 / 灯 / 围栏 / 信箱 / 木桶 / 花坛用现有图，`pond` 画水砖、`path` 画路砖，认不出的跳过并 console.debug）；③ 坐姿：`poseAnchorsFor` 优先读物品的 `use_pos`（相对格；落在 3 格外当绝对格）与 `use_facing`，没有才退回按类型猜；④ 角色问题帧：等主播挑 |
| 2 | QQ 面板 | **做完等联调** | `src/ui/QQPanel.tsx` + `src/api/qq.ts`：联系人 / 群（👥）/ 未读角标、会话、发文字、发文件类物品（下拉只列背包里 kind=file 的歌 / 文稿；实物不列）、「标记已读」（占 1 游戏分钟）。操控页右上（收成图标）；旁观页只读看跟随目标的手机，`layout=live` 或 `hud=0` 收成 📱 图标 + 未读数，`&qq=0` 关。数据：ws `qq` 事件即时推 + 每 4 s 轮询 `/qq/inbox?player=&since=` 兜底；后端 404 时面板显示「后端还没开通」。她读消息时头顶 `📱 看手机`（按 B 的 `reading` 标签） |
| 3 | 金币与背包 | **做完等联调** | 旁观：信息面板末行 `💰 余额 + 背包图标×数量`，React 面板同样一行；操控页：左下 `BackpackPanel` 10 格背包 + 金币，物品可「吃」「送（相邻的人）」「卖（站在柜台 / 卖鱼摊旁）」，站在带 `shop[]` 的物品旁列出可买项（价格、钱不够灰掉）；全部走 `POST /action {type: buy|eat|give|sell}`。反馈气泡：ws `action` 事件 → `🛒 买了🍞面包 -5 金币` / `🍞 吃了面包` / `🎁 把小礼物送给了小千` / `💰 卖了🐟鱼 +10 金币` / `💸 钱不够，买不了面包`（`insufficient_funds`）。物品表 `src/game/items.ts` 按 `03-objects.md` 3.2，中英文名都认 |
| 4 | 室内视角过渡 | 完成 | 进屋 / 出门：140 ms 压黑 → 黑场里直接切 zoom 与屋顶 / 室内视图 → 260 ms 亮起（原来是 650 ms 的 zoom 渐变 + 压暗叠在一起，会抽）；上下楼：180 / 320 ms 并在屏幕中央弹 `2F ↑` / `1F ↓`；锁门提示沿用 W7。录屏 `report_shots/w9/W9_indoor_transition_20s.webm`（8091：广场 → 合租房 1F → 2F → 广场 → 教室 → 餐馆），`W9_transition_last.jpg`。调试钩子 `__whaleDebug.setFocus(sector, floor)` 运行时切取景（录屏用） |
| 5 | 评审页主播评分 | 完成 | 每张底图 / 角色表 / 物品 / 地砖表 / 装饰下面 👍 👎 + 备注框（回车提交），写 `front_end/data/assets/review.jsonl`（一行 `{ts, kind, name, vote, note, by}`；**不进 git**，路径可用 `VITE_REVIEW_FILE` 指到总控的 `run/data/`——总控建议，11-07 晚改），页顶统计 👍/👎 数。写入靠 Vite dev / preview 的 `/review-api/rate` 中间件（`vite.config.ts`），生产静态托管下没有写入口——评审页本来就只在运行台开 |

## 2. 假设（B 落地后要对齐的字段名，全在 `src/api/qq.ts` / `src/game/items.ts` / `BackpackPanel.tsx` / `GameScene.ts` 顶部注释）

- `GET /qq/contacts?player=` → `{contacts:[{id,name,unread}], groups:[{id,name,members,unread}]}`（也接受纯数组 / `is_group`）；`GET /qq/inbox?player=&since=` → `{messages:[{id,ts,from,to|group,kind,text,file_ref,read_at}]}`（也接受 `content` / `sender` / `timestamp`）；`POST /qq/send {from, to|group, kind, text|file_ref+item}`；`POST /qq/read {player, from|group}`；ws `{type:'qq', message:{…}}` 或平铺。
- `players[]` / `GET /player` 带 `gold:number`、`inventory:[{type,name,count}]`（也接受 `item/qty` 或字符串数组）；商店物品 `objects[].shop:[{type|item, name, price, stock}]`；`POST /action` 的 payload 用 `item / item_id / object_id / target / qty`；ws `action` 事件带 `item / item_name / price|gold_delta / target_name`，缺了气泡只说动作。
- `use_pos` 相对物品 `position`；`use_facing` 四向之一。
- `decor[]` 在 `/world.decor` 或 `/world.map.decor`。

## 3. 给其他会话

1. **B**：上面 §2 的字段名若与实现不同请在 api-spec 里写明，我按 spec 改一处即可；`reading` 标签名请确认；`insufficient_funds` 放在 `reason` 字段。
2. **总控**：不切 5173。B 的 W10 一落地（8091 重起）我做：重导版式 + QA、`decor` 实测、坐姿实测、QQ 一来一回联调（阿蝉操控页发给鲸仔 → 她读 → 头顶 📱）、一次购买联调，然后截图补进本节。

## 4. 提交号

| 项 | 值 |
|---|---|
| 代码 | `whale-frontend` @ 本提交（基于 B 的 `e82ac17`） |
| 新增文件 | `src/ui/QQPanel.tsx`、`src/ui/BackpackPanel.tsx`、`src/api/qq.ts`、`src/game/items.ts`、`report_shots/w9/*` |
| 新增参数 | `&qq=0`（旁观页关 QQ 面板）；`mode=free|follow|world`；`__whaleDebug.setFocus()` / `.state()` |
| 新增文件（0b 后） | `src/spectate/SpectateControls.tsx`、`report_shots/w9/W9_free_*`、`W9_rating_*`、`W9_walk_server_20s.webm` |

---

# W8 · 2026-11-07：美术管线 v1.0（gpt-image-2 底图 + 物品 + 角色，任务 1–5 全部完成 + 主播两轮反馈）

## 1. 进度（1–2 上午交主播看过，主播「没问题继续」后下午做完 3–5）

| # | 任务 | 状态 | 做了什么 |
|---|---|---|---|
| 1 | 合租房外观 + 1F/2F 室内 | 完成 | 3 张底图：`home_1f_exterior`（16×15 格，宝可梦式 3/4 外观：蓝瓦屋顶 + 底边正面墙 + 门窗花箱）、`home_1f_interior`（三间 + 厨房瓷砖，内墙按 B 的版式）、`home_2f_interior`（阿蝉房，画在 B 画布的 2F 位置，常显） |
| 2 | 校园三栋外观 + 室内、20 件核心物品 | 完成 | 教室 / 图书馆 / 音乐室各 1 外观 + 1 室内（共 6 张）；物品 21 件（任务书 20 件 + `door_closed`）：bed、pc、fridge、stove、restaurant_table、sofa_tv、pc_music、piano、reading_desk、classroom_desk、shelf、bar、shop_counter、fishing_spot、fish_stall、bench、notice_board、door_closed、stairs、tree、fountain。见 `report_shots/v1art/W8_objects_sheet.png` |
| 3 | 鲸仔 / 阿蝉四向精灵 | 完成 | **按主播 11-07 下午给的新人设**（`ref/jingzai_design_sheet_v2.png`、`ref/achan_design_sheet_v2.png`：鲸仔不再是鲸鱼娘——音乐学本科生、白连帽开衫 + 藏青百褶裙 + 脖挂耳机；阿蝉没有猫耳猫尾）。一张 `images.edit` 出整张 4 列 × 5 行表（下 / 左 / 右 / 上各「站 走 站 走」+ 坐 / 睡 / 坐左 / 坐右），切格后 32×48/帧 → 游戏里 ×3 = 96×144（一格宽、一格半高）。旁观主镇截图 `W8_main_follow_whale.jpg`（对照像素版 `W8_main_follow_whale_pixel.jpg`）、30 s 录屏 `W8_spectate_30s.webm` |
| 4 | 其余区域底图 + 5 NPC | 完成 | 13 张底图：渔夫屋 / 餐馆 / 杂货店 / 小千屋 / 两位老板的房子各外观 + 室内（10），广场 / 公园 / 码头地面（3，常显、物品另叠）；全镇 22 张底图齐了。5 个 NPC 四向表：餐厅老板（厨师）、杂货店老板（**女**，主播 11-07 改）、老渔夫、千小满（小千，复用 `regular` 这套外观键，`charKeyFor` 加了「小千 / 小满」匹配）、村民。全镇换装截图 `W8_overview.jpg`（对照 `W8_overview_pixel.jpg`），`W8_backdrops_task4.png` 13 张一览，`W8_chars_sheet.png` 7 套形象一览 |
| 5 | 评审页 + 报告 | 完成（页）/ 本节 | `/assets-review`：底图四联（平涂版式 → 原始输出 → 对齐 QA 叠图 → 量化成品）+ QA 分 + 次数 + 费用；物品三联（旧像素 → 新 AI → 原始输出）；「一键替换」切 `localStorage.aiAssets`；每张可看提示词 |

**主播补充三条全部按要求做了**：① 统一相机——室内俯视 3/4（参考 `ref/gpt-image-probe/house.png`），外观按主播 11-07 的话改成宝可梦式「看得见正面墙」；鲸仔 / 阿蝉动作表只作画风与配色参考喂给模型，没有照抄侧视；② 小镇视角房屋不镂空（屋顶 + 外墙），相机跟到的人进屋才切室内图；每栋都有外观 + 室内，2F 单独一张；③ 室外小物件（长椅、喷泉、树、公告栏、鱼摊、钓位）一套，室内物件只在室内视图出现（屋顶盖住时隐藏物品和人物）。

## 2. 管线（`tools/gen_assets_ai.py`，全部在 `front_end/`）

```
/flat 页（Vite）──flat_export.mjs──▶ data/assets/flats/<区域>_<层>f_<视图>.png + .json（x0,y0,w,h,px,margin）
   │ 平涂版式：按 B 8091 的 /world 画每格颜色（地板/瓷砖/红毯/墙/门/楼梯；exterior = 屋顶色 + 底边一行外墙色）
   ▼
gen_assets_ai.py backdrops  ──▶ gpt-image-2 images.edit([letterbox 版式, 画风参考], prompt, quality=high)
   │ 对齐 QA：墙/门色块轮廓 vs 生成图边缘，覆盖率 ≥ 0.9 过，否则换提示重试（最多 2 次）
   │ 反 letterbox 裁回版式比例 → 缩到 32 px/格 → ≤ 64 色量化 → public/assets/gen-ai/backdrops/<名>.png + .json
gen_assets_ai.py objects    ──▶ images.edit([画风参考, 室内参考], 「品红 #FF00FF 纯底」prompt)
   │ 品红抠像（tol 90 / 软边 40）→ 裁包围盒 → 等比装进 w×h 格（32 px/格）→ 底对齐 → ≤ 64 色
gen_assets_ai.py manifest   ──▶ public/assets/gen-ai/manifest.json + review/ 缩略图 + gen.jsonl 同步
每次调用一行 data/assets/gen.jsonl：kind/name/attempt/prompt/size/quality/usage tokens/latency/cost_usd_est/qa_score/error
```

子命令：`backdrops --regions home:1:interior,... --attempts 2 --qa 0.9 [--dry-run]`、`objects --items bed,pc`、`qa`（只重算分）、`rekey`（只重抠像，不花钱）、`manifest`。gpt-image-2 **不支持** `input_fidelity`、`background=transparent`、seed（三条都是 400 撞出来的，见 §4）；只能用 1024²/1536×1024/1024×1536 三种尺寸，所以版式先 letterbox 进最接近的比例。

游戏接入：`src/game/aiAssets.ts` 读 manifest、`&ai=0` / `localStorage.aiAssets` 开关；`GameScene.placeBackdrops` 把底图贴在 `(x0,y0)` 格、`setCrop` 裁掉版式四周 1 格地面、深度 0.6（地砖之上、物品之下）；`applyView(inside)`：镜头进了某栋（按 backdrop 的 sector **或 arena** 匹配——校园三栋 sector 都是 `university`，按 arena 分）就显示它的室内图、其余有外观图的显示屋顶并隐藏屋内 1F 物品 / 人物；同层没有外观图的室内（2F）常显。物品精灵优先用 `aiobj_<type>`，别名表 `pc_desk→pc、book→shelf、cook→stove、desk→classroom_desk、bed_21→bed、desk_12→reading_desk、game_console→pc`；1×2 的床遇到 2×1 的占位时转 90°。

## 3. 结果与费用（`data/assets/gen.jsonl`，全周 81 次调用）

| 项 | 值 |
|---|---|
| 成功 / 失败 | **59 / 22**（22 次失败全在上午、全是参数 400：1 次 `input_fidelity`、21 次 `background=transparent`，**不计费**；下午任务 3–4 的 31 次调用 0 失败） |
| 底图 | **22 张成品，29 次成功调用**：任务 1 的 9 张用了 14 次（home_2f 3 次、home_1f_int / classroom_int / library_int / home_1f_ext 各 2 次）；任务 4 的 13 张 13 次一次过，广场 / 公园因版式格线被画成浅色方块重出 1 次（共 15 次） |
| 物品 | 21 张，21 次，一次过 |
| 角色 | **7 套成品，9 次调用**：鲸仔第 1 版按旧人设（鲸鱼娘）出完后主播换了人设 → 重出 1 次；杂货店老板第 1 版画成男性 → 按主播改女性重出 1 次；其余 5 套一次过。切格 QA（5 行 × 4 列按空隙切出、15 个所需格全非空）9/9 通过 |
| 对齐 QA（22 张成品） | 任务 1：外观 home / classroom / music_room 1.000、library 0.965；室内 home_2f 0.972、library 0.949、music_room 0.946、classroom 0.914、**home_1f 0.899**（差 0.001，缺的是门洞一角，放行）。任务 4：外观 fisher / restaurant / grocery / xiaoqian 1.000、owners 0.989；室内 fisher 0.995、grocery 0.982、xiaoqian 0.950、restaurant 0.927、owners 0.912；地面 park / dock 1.000、square 0.945。29 次调用里 ≥ 0.9 的 24 次，中位 0.982 |
| 时延 | 52–105 s / 张，均 73 s（high） |
| token | 558,131（usage 字段汇总，59 次成功调用） |
| 费用估算 | **$14.75**（59 × $0.25；$0.25/张 high 是**假设**，按 gpt-image-1 high 1024² 价；官方账单以 token 计，请总控按实际账单核）。其中因人设 / 性别改动重出的 2 张 $0.50，广场公园重出 $0.50 |
| 预算 | 任务书 ≤ 200 张，用了 59 张（29.5%） |

截图（`report_shots/v1art/`）。任务 3–4 新增：`W8_main_follow_whale.jpg`（主镇 8000 旁观跟随鲸仔：新人设、睡在床上）、`W8_main_follow_whale_pixel.jpg`（同机位像素版）、`W8_spectate_30s.webm`（主镇 30 s 录屏）、`W8_chars_sheet.png`（7 套四向表 ×3）、`W8_backdrops_task4.png`（13 张新底图）、`W8_restaurant_ai.jpg` / `W8_grocery_ai.jpg` / `W8_owners_ai.jpg`（进屋取景）、`W8_square_dock.jpg`（广场 + 公园 + 餐馆外观）；`W8_overview.jpg` 已重拍为全镇 22 张底图齐的版本。上午那批（8091 草图镇，无人物）：`W8_overview.jpg` 全镇 1/6 zoom（屋顶版）与 `W8_overview_pixel.jpg`（`&ai=0` 像素版，同机位对照）、`W8_town_roofs.jpg` 合租房屋顶 + 公园广场物品、`W8_home_1f_ai.jpg` / `W8_home_2f_ai.jpg` 进屋取景、`W8_campus_ai.jpg`（镜头在图书馆：它显示室内、两侧教室 / 音乐室保持屋顶）、`W8_classroom_ai.jpg`、`W8_assets_review.jpg` 评审页整页、`W8_objects_sheet.png` 21 件物品一览。

## 3b. 任务 3–4 的做法

**角色表**（`gen_assets_ai.py chars --keys whale,achan,...`）：姿态版式 = 现有像素表（鲸仔 / 阿蝉用 v1 文字版）每帧 ×9 放进 1024×1536 品红画布的 4 × 5 格里（睡觉格用左向站姿转 90° 平躺、不画床），第二张输入是新人设图；提示词说明行列含义（4 向 × 「站 走 站 走」+ 坐 / 睡 / 坐左 / 坐右）、只取人设图的角色与配色、2 头身、俯视 3/4、品红纯底。输出：品红抠像 → **按 alpha 投影的空隙切 5 行 × 4 列**（模型不严格落在格子里，脚常画到格线下，固定网格会切掉脚；切不出 5 × 4 就退回固定网格并判不过）→ 站姿帧统一比例（最高者 44 px）→ 32×48/帧、脚底对齐 → 右向整行 = 左向镜像、坐右 = 坐左镜像（左右一致）→ 睡觉帧顺时针转 90° 竖躺（头朝上）存表 → 整表 ≤ 64 色 → `public/assets/gen-ai/chars/<key>.png`；`--reslice` 从 raw 重切不花钱。NPC 没有立绘，用两张新人设图定画风 + 文字描述。

**游戏接入**：`manifest.chars` 有的角色优先用 `aichar_<key>` 表（`ai_<key>_walk_<dir>` 等动画键与像素表同形），×3 显示 96×144（像素表 16×24 ×4 = 64×96；主播 11-07：「跟物品一比太小了」→ 放大到一格宽一格半高，头顶名字 / 状态 / 气泡的偏移按高度等比上移）。**睡觉贴床**（主播：「睡觉时候不应该显示在床上吗」）：后端把使用者放在床边一格，床和人现在是两张图，不贴会像睡在地板上 → `sleepAnchorFor`：按 `usingObjectId` → `objects[].userList` 反查 → 相邻的床 / 沙发，取床 footprint 中心，竖床 0°、横床 -90°，只对 AI 表生效（像素表的睡觉帧自带床）；醒来 / 移动即还原。**底图防错位**：底图是照 8091 某版地图画的，`backdropFits` 要求当前地图里该 sector / arena 同层包围盒与 manifest 完全一致才贴——主镇 8000 是旧地图，22 张全部自动跳过（console 有 `[ai] backdrop skipped`），物品和角色照常换新。

## 3c. 主播第二轮反馈（11-07 中午）：物品变形、小镇整体不好看、椅子站位

**物品「被挤压变形」的原因**：生成物品时让模型「填满画布」，成品又被我**缩进** footprint 的格子里（1×1 的冰箱压成 32×32 的方块；后端 2×2 的喷泉 / 主镇 1×2 的长桌借 1×1 图被拉伸）。改法：① `finish_object` 改成**盖住** footprint——按较大的比例缩放，宽最多溢出 25%、高最多到 2 倍，高物件（冰箱 / 书架 / 树 / 路灯）向上长出格子（宝可梦式），画布底边居中；② 前端 `GameObjectSprite` 不再 `setDisplaySize(footprint)`，按纹理实际尺寸 ×3 画、底边贴 footprint 底边；③ 深度改成**按底边 y 与人物排序**（人物按脚底 y），站在冰箱后面会被挡住；④ 补了 3 张：喷泉按后端 2×2 重出、`desk_long` 1×2（主镇 `desk_12` 借用）、树改成竖画布（高于宽）。21 张旧 raw 用 `rekey` 离线重切，没花钱。

**小镇整体为什么不好看（我的分析）**：素材单看都好，拼起来差在「地面 / 建筑 / 空间」三层：
1. **地面是平涂像素，建筑是软阴影手绘**——两种质感打架；草地一个色、路一个色、草↔路硬边、没有投影，建筑像贴在绿纸上。
2. **九栋房子同一张蓝瓦**——没有「谁是谁」的辨识度，远看像复制粘贴。
3. **空间没有层次**——两大块空草坪、两格宽的路、没有花草 / 路灯 / 树 / 围栏这些「人住过」的痕迹；物品只在室内和公园。
对应做法（都在前端，全部可用 `&ai=0` 一键关掉对照）：
- **AI 地砖表**（1 张 1024² 出 16 格：草 ×4 变体 / 路 ×2 / 石板 ×2 / 水 ×2 帧 / 木板 / 公园草 / 室内木地板 / 瓷砖 / 红毯；32 px/格，同类变体按格哈希混用，**平均色对齐到基准格**否则会棋盘格）+ 草↔路 / 水交界处一条半透明暗边 + 水面两帧往复动画。
- **屋顶 / 墙配色各异**：8 栋外观按建筑身份重出——校园三栋统一青灰石板瓦 + 砂岩墙（一个学区的感觉），合租房保留蓝瓦，渔夫屋苔绿木瓦，餐馆赭红陶瓦 + 红白条遮阳篷，杂货店墨绿铁皮 + 绿白条篷 + 门口菜箱，小千屋粉瓦白墙，老板屋棕木瓦米墙。
- **建筑落地阴影**：每栋外观底图下面两层半透明圆角矩形向右下偏，建筑不再「浮着」。
- **装饰层**（1 张 1024² 出 16 件小装饰 + 路灯单出 1 张）。第一版按格哈希随机撒，主播「太乱了，好好规划一下」→ 改成**全部确定性的规划摆放**：① 建筑脚下那排草种花（粉黄交替、每 3 格空 1 格）两端各一丛灌木，像房前花坛；② 路灯只放路的北 / 西侧、每 8 格一盏；③ 河岸每 4 格一棵小松树、偶尔一块青苔石；④ 每片草地中心一簇 2×2 野花、两个对角各一棵小松树；公园沿内缘每 3 格一棵树 / 一丛花，中心一个花坛；其余草地留白。避开物品格、门口及四邻；纯视觉不改可走性，人物按脚底深度从花丛「前面 / 后面」走过。
- 路灯在 4×4 装饰表里被格线截了顶 → 单独出一张竖画布的路灯（1×2 格高）。

**椅子使用者站位**（主播：「椅子添加使用者站位」）：`poseAnchorsFor` 从只认床扩成床 + 座位——桌类（电脑桌 / 课桌 / 阅览桌 / 钢琴 / 长桌 / 直播桌）椅子画在图的下沿 → 坐到 footprint 底格偏下、面朝上；吧台底沿凳子面朝上；长椅 / 沙发坐在人所在那一列、面朝下；餐桌两端椅子，坐离人近的一端、面朝桌子；钓位原地面朝下。坐着时朝向由椅子决定（不跟服务器朝向），起身即还原。**未实测**（截图时鲸仔没在坐），逻辑同睡觉贴床；仍建议 B 在物品上给「使用者站位 + 朝向」字段，前端按类型猜终究是猜。

本轮新增 15 次调用（3 物品 + 地砖 1 + 装饰 1 + 8 外观 + 路灯 1 + 2F 外观 1，0 失败，外观 QA 全 ≥ 0.985），$3.75；**全周累计 96 次 / 74 成功 / 22 失败（不计费）/ 估算 $18.50 / 用了 74 张（37%）**。截图：`W8_overview.jpg`（全镇新貌）、`W8_square_dock.jpg`（广场 + 公园 + 餐馆 / 杂货店新外观）、`W8_campus_ai.jpg`（校园青灰三栋 + 房前花坛 + 路灯）、`W8_tiles_sheet.png` / `W8_deco_sheet.png`（地砖与装饰一览）、`W8_main_follow_whale.jpg`（主镇：物品按实际比例、人物脚底深度）、`W8_spectate_30s.webm` 重录。

## 3d. 主播第三轮（11-07 中午）：不必像素风、2F 也画房子、统一南门

- **全部素材改高清原画**（主播：「角色一定要像素风吗，直接原图不行吗」→「房子和物品也没必要像素」）。原来每类都缩到 32 px/格再压 64 色、游戏里 ×3 最近邻放大，才有像素感。改成：底图 **96 px/格**（= 显示尺寸，1:1）、物品 96 px/格、角色 **96×144/帧**、装饰 96 px 宽、地砖表 48 px/格（地面不需要太细，省显存），**全部不量化**，AI 纹理统一线性过滤（像素兜底素材仍走 `pixelArt` 的最近邻）。**没有重新花钱**：原始 1024 级输出都在，`refinish`（底图，取每区 QA 最高那次 raw）/ `rekey`（物品）/ `--reslice`（角色 / 地砖 / 装饰）离线重导。代价：`public/assets/gen-ai/` 从 ~5 MB 涨到 ~40 MB（底图 37 MB PNG），首屏多加载几秒；若在意可以转 WebP（Phaser 直接支持）。
- **2F 也画成房子**（主播：「虽然 2 楼不是房子，但为了统一」）：出了 `home_2f_exterior`（和主屋同款蓝瓦米墙的小屋，带老虎窗，QA 0.985）；屋顶 / 室内的配对键从「区域」改成「区域|楼层」，镜头在楼上才切 2F 室内，其余时候 2F 那块显示成一栋小房子。
- **统一从南面进门**（主播：「门既然都画在下面，统一从下方进房门如何」）：同意，前端外观已全部把门画在正面墙；但门边（`edges`）的格子在 B 的地图里，**需要 B 把合租房 / 餐馆 / 杂货店 / 小千屋 / 老板屋的门边挪到建筑南侧**（渔夫屋和校园三栋已是南门），见 §5。

## 4. 踩过的坑（都已处理）

1. **gpt-image-2 参数**：`input_fidelity` 400 → 去掉；`background="transparent"` 400 → 改品红纯底 + 自己抠像；没有 seed，重试靠改提示词。
2. **抠像 int16 溢出**：第一版 alpha 全 NaN（物品几乎透明），改 int32；已跑完的 21 张用 `rekey` 离线重抠，没有重新花钱。
3. **小房间照抄参考图**：home_2f 前两次把 `house.png` 参考的房间布局搬进来（QA 0.58 / 0.49）。底图输入去掉室内参考、提示词加「layout must follow the first image exactly」→ 0.972。室内参考现在只喂给物品。
4. **QA 指标**：最初「所有边缘 IoU」把地板纹理也算进去，对齐良好的图只有 0.55；改成「版式的墙 / 门色块轮廓 → 生成图在同位置（±格宽/3）有没有边」的覆盖率，与肉眼一致。
5. **外观视角**：第一版是纯俯视屋顶，主播要宝可梦式正面墙 → 版式底边加一行「外墙色」、提示词改写，4 张外观一次过（3 张 1.0）。
6. **校园三栋不切室内**：tile 的 sector 是 `university`、底图按 arena 命名，匹配不到 → 改成 sector 或 arena 都认（§2）。
7. **角色表固定网格切格切掉脚**（第 1 张鲸仔 16/20 格触边）→ 改按空隙切（§3b）。
8. **人设变更**：鲸仔第 1 张按旧 `jingzai_action_sheet_q.png` 出成了鲸鱼娘（鱼鳍耳 + 女仆装）；主播给新人设后，旧动作表 / 全身图不再喂模型（会把鱼鳍带进去），底图 / 物品的画风参考也换成新人设图（配色同一套）。杂货店老板第 1 张默认画成男性，主播指正后改女性重出。
9. **室外地面被画出浅色方块**：版式导出在广场 / 公园的物品格上画了淡格线，模型把它们画成石板上的浅色方块 → 室外 arena 不画格线，重出 2 张。
10. **FlatApp 一行 `if` 被我追加的行注释吞掉**，`/flat` 500、两次版式导出超时；修好前差点让重出任务拿旧版式去生图（已及时杀掉，没花钱）。
11. **地砖变体直接混用成棋盘格**（草 a / 草 b 亮度差 8%）→ 同类变体把平均色对齐到基准格，只留纹理差；深草只比基准深 6%。
12. **装饰 4×4 表切格串进邻格碎屑**（粉花下面一块黑）→ 每格只保留 alpha 最大的连通块；路灯顶部被格线截掉 → 单独出图。
13. **随机撒点的装饰「太乱」**（主播原话）→ 规则摆放（§3c），随机只用于「有 / 无」都不再用。

## 5. 请主播 / 总控 / B 定

1. **主播**：新的两件请看：① 全镇新貌 `W8_overview.jpg`——屋顶配色、花坛 / 路灯 / 河岸树的规划是否合眼；② 两大块空草坪是地图本身（B 的 64×48 草图留白），前端只在中心放了一簇花 + 两棵树，要不要让 B 在那里加点东西（小径 / 池塘 / 晾衣绳）。之前的两件：① `W8_chars_sheet.png` 7 套形象——鲸仔 / 阿蝉按新人设，NPC 的长相是我按 `04-npcs.md` 身份编的（厨师 / 女店主头巾绿围裙 / 黄雨衣老渔夫 / 红褐发小千 / 紫发村民），哪位要改说一声，一张 $0.25 重出；② 人物现在一格宽一格半高、睡觉贴床（`W8_main_follow_whale.jpg`），大小合适吗？
2. **B（请总控转）**：⓪ **主播拍板：所有建筑统一从南面进门**——请把 `door_home`（现北）、`door_restaurant`（现西）、`door_grocery` / `door_xiaoqian` / `door_owners`（现北）的门边挪到各建筑南墙中间一格（a 在外 b 在内），渔夫屋与校园三栋不动；外观底图的门已经画在南面墙正中。① 睡觉 / 坐下时后端把人放在物品旁一格，前端现在只对床做了「贴到床上」的视觉处理；坐姿（电脑桌 / 阅览桌 / 餐桌）仍在旁边一格，若想坐进椅子需要物品带「使用者站位 / 朝向」字段或前端继续按物品类型猜。② 合租房的入口在 **北边**（`door_home`：a=街道 (12,20)、b=鲸仔房 (12,21)，建筑顶边），而 3/4 外观只能把门画在南面正面墙上，现在从北门进屋在画面上是「从屋顶走进去」。建议 v1 地图把合租房门移到南侧（或所有带外观的建筑门都开在南 / 东西侧），校园三栋门已在南侧没问题。另外合租房的 2F 单独画在画布左下，前端当常显室内处理，不需要改。
3. **总控**：不切 5173（任务书要求）；本周的 `node_modules` 之外新增了 `front_end/tools/.venv`（openai / numpy / pillow，已 gitignore），其他机器跑管线要 `python -m venv tools/.venv && tools/.venv/bin/pip install openai numpy pillow`，密钥从 `~/.env` 读 `OPENAI_API_KEY`。

## 6. 假设（没有依据的决定）

- 费用 $0.25/张（high）；底图 32 px/格、≤ 64 色；对齐阈值 0.9、重试 2 次。
- 版式四周多带 1 格地面让模型画出屋檐 / 投影，贴图时裁掉。
- 角色表一张 1024×1536 出 20 格、右向用左向镜像；32×48/帧 ×3 显示；睡觉帧竖躺头朝上、横床转 -90°；贴床只认 `bed|sofa` 类型物品。NPC 长相、小千复用 `regular` 外观键，都是我定的。

## 7. 提交号

| 项 | 值 |
|---|---|
| 代码 | `whale-frontend` @ 本提交（基于 B 的 `0d091e1`） |
| 新增文件 | `tools/gen_assets_ai.py`（含 `tiles` / `deco` / `refinish` 子命令）、`tools/flat_export.mjs`、`src/flat/FlatApp.tsx`、`src/review/AssetsReviewApp.tsx`、`src/game/aiAssets.ts`、`src/game/systems/DecoLayer.ts`、`public/assets/gen-ai/**`（22 底图 + 23 物品 + 7 角色表 + 地砖表 tiles.png/json + 16 装饰 + manifest + review 缩略图 + gen.jsonl）、`data/assets/{flats/,gen.jsonl}`、`ref/{jingzai,achan}_design_sheet_v2.png`（主播新人设）、`report_shots/v1art/W8_*` |
| 新增参数 | `&ai=0`（旁观 / 操控 / 回放页关 AI 素材）、`/flat?sector=&floor=&view=&px=&margin=`、`/assets-review` |

---

# W7 · 2026-11-07：世界 v1.0 地图呈现（按区域取景、二楼、锁门、评审包）

## 1. 进度

| # | 任务 | 状态 | 做了什么 |
|---|---|---|---|
| 1 | 按区域取景 | 完成 | 跟随目标（或操控的自己）所在格属于室内 sector 时：相机推近到「该 sector 同一楼层的包围盒 + 1 格」（zoom 吸附到 1/6 倍数，上限 1.5）、屋外用深色遮罩压暗（4 块矩形围住包围盒，0.42 s 渐变），相机中心限制在屋内不露屋外；出门还原到默认 zoom、遮罩渐隐。`&scene=world` 关掉。**回放页同样**：她在室内时地图上屋外压暗（不推近，整图保持可读）。实测主镇：阿蝉在小仓库 → 推近到阿蝉家、外面压暗（`focus_indoor`）；走到街道 → 还原（`focus_outdoor`） |
| 2 | 二楼 | 完成 | 按 B 格式 v2 的 `map.floors`（`{achan_room: 2}`）与 `tiles[].floor`：楼层进区域名（「合租房 · 阿蝉房间（2F）· 2F」）、取景包围盒按楼层算（上楼只框 2F 那块），楼梯边（`kind: stairs`，a/b 两格）两端画楼梯图示 + 「1F↔2F」。2F 在 B 的画布上是另一处（不叠在 1F 上），所以不需要图层开关 |
| 3 | 锁门 | 完成 | 门 / 校门边（`kind: door|gate`）带 `open_hours` 的，在时段外画成关着的门 + 「🔒 开 HH:MM–HH:MM」；场所 `access.locked` 为时段或 `always` 的，门口画「🔒 锁 HH:MM–HH:MM（场所名）」/「🔒 常锁（渔夫的卧室）」；每分钟按游戏时间刷新。ws `action` 事件 `reason` 含 `lock` 时在她头顶出气泡「咚咚咚……门锁着呢」4 s（B 的 `locked` 原因落地后自动生效，未实测） |
| 4 | 视觉评审包 | 完成（待主播定） | `tools/v1map_review.mjs --api http://127.0.0.1:8091` 一条命令：自己起临时 Vite、读 `/world` 挑 sector / arena、出 6 张 1920×1080 截图 + 30 s 旁观录屏 → `report_shots/v1map/`：`01_overview`（全景 64×48，1/6 zoom 正好 1024×768 居中）、`02_house_1f`、`03_house_2f`、`04_campus`、`05_square`、`06_dock`、`spectate_30s.webm`。8091 草图镇当时没有 agent，录屏是全景无人物。**主播看后定 64×48 够不够** |
| 5 | UI 位置草图 | 完成 | `report_shots/v1map/ui_sketch_qq_wallet.png`：在 1920×1080 旁观画面上标出现有元素（stats / 时钟 / 信息面板 / 字幕 / 游戏机小窗 / Live2D 安全区）和新增位置——A 金币 + 背包（信息面板右侧，6 格）、B QQ 面板（右上时钟下、游戏机小窗同位，最近 5 条消息；`layout=live` 时收成小图标）、C 锁门 / 敲门提示、D 区域 / 楼层标签 |

## 2. 对接 B 的地图格式 v2（真实形状，11-07 8091 读到）

`/world.map = { format: 2, edges: [{ id, kind: gate|door|stairs, name, a: {arena,x,y}, b: {arena,x,y}, open_hours: [["06:00","23:00"]] }], floors: { achan_room: 2 }, access: { <arena>: { owner: [...], locked: "always" | [["09:00","18:30"]], allow_when_locked: [] } } }`，另有 `zone_names`。前端 `src/game/map/mapv2.ts` 宽容解析（同时接受我之前猜的几种写法），门画在 b（内侧）格；`open_hours` 多段时只用第一段（**假设**）。`zone_names` 现在直接用 `/world` 给的，`zones.ts` 的内置表只作兜底。

**B 把 `tile_gids.json` 用上了**（tileset 已是 `gen/tiles.png`，6 个按类型的 gid）。但按类型的 gid 画不出街道 / 广场 / 公园 / 码头 / 厨房瓷砖 / 餐厅红毯，所以前端**首选按「类型 + arena」的自制地砖渲染**，B 的 tiled 层只作兜底。新增 arena 映射：`street` / `lane` → 街道，`campus` → 石板，其余沿用。

v1.0 的新物品（pc / pc_desk / pc_music / classroom_desk / reading_desk / shelf / stove / sofa_tv / bar / boat / fish_stall / notice_board / piano / fountain）各给了一张自制图（船、鱼摊、公告栏、钢琴、喷泉新画，其余复用近似物），画面里 **0 个占位块**。

## 3. 评审包观感（给主播定规模的参考）

- 64×48 在 1920×1080 全景只能用 1/6 zoom（1024×768，占屏 53%），房子里的物品能认出来、人物是 6 px 小点；进屋取景后 1 栋房子铺满画面，物品 / 人物清楚。再大（80×60）全景就得滚动或拆成两屏；再小（48×36）全景可到 2/6 但室内会挤。
- 街道两格宽、校园石板、广场喷泉 + 长椅、公园树丛、码头两钓位 + 船 + 鱼摊、河 6 格宽，层次分得开；合租房 1F 三间 + 2F 一间（2F 画在左下另一处，靠楼梯图示提示）。
- 没放人物（8091 无 agent），人物比例与 W4–W6 截图一致（16×24 帧 ×4 = 一格高 2/3 格宽）。

## 4. 给其他会话

1. **B**：① `locked` 原因落到 `POST /action` / ws `action` 事件的 `reason` 里时请含 `lock` 字样（我按 `/lock/i` 匹配）；② `open_hours` 多段我只画第一段，若餐厅 11–14 / 17–21 两段都要显示请知会；③ 2F 画在另一处很好，不需要改。
2. **总控**：运行台 5173 可切到 `84ed9cd`（主镇不受影响：主镇没有 `map.format 2`，只是多了室内取景与字幕只跟鲸仔）；评审包随本提交进仓库。

## 5. 提交号

| 项 | 值 |
|---|---|
| 代码 | `whale-frontend` @ `84ed9cd`（基于 B 的 `41b42dd`） |
| 新增参数 | `&scene=world`（关取景）、`&focus=<sector或arena>[:floor]`（不跟人直接取景，评审截图用） |
| 新增文件 | `src/game/map/mapv2.ts`、`src/game/systems/SceneFocus.ts`、`tools/v1map_review.mjs`、`report_shots/v1map/*`、新物品图 |

---

# W6 · 2026-11-06：维护节奏第 1 轮 + Q0 她的脑子 + Q1 回顾视频（原报告）

## 每天一轮

| 步 | 结果 |
|---|---|
| 1 rebase / 测试 / 构建 | rebase 到 `1bfe54d`（20 个提交重放，0 冲突）；`npm test` 通过；`npm run build` 通过 |
| 2 各会话给 E 的条目 | **B**「`worldState.time` 每秒一个 patch，前端可忽略只含 time 的 patch」→ 看过：这类 patch 只更新 store 的 worldState，Phaser 侧只有时钟文字变化、React 侧只有 WorldInfoPanel 重渲染，每秒一次开销可忽略，**不改**，也不需要 B 加 `?fields=` 过滤。B 其余条目（`players.upsert` 含 `stateLabel` 等、`tiled` gid 覆盖口）W4–W5 已接。**A / C / D** 本轮报告里没有新的「给 E」。**主播反馈**：§3.22 裁定已采纳（v1、live 布局），`TODO-主播.md` 第 10 条是把直播姬源地址改成 `…&layout=live`，等主播操作 |
| 3 运行台截图 | `report_shots/W6_runtime_5173_live.jpg`：经 Tailscale `http://100.83.181.41:5173/spectate?follow=鲸仔&hud=0&layout=live&stats=1`，58.5 fps、ws 在线、鲸仔（v1 形象）在码头钓鱼，面板显示「正在钓鱼」与七变量。运行台 5173 现为 `e065963`；本轮新增只有回放 / 回顾功能，**不急切换**，下次顺手切到最新即可 |

## Q1 「她的一天」回顾视频（完成）

- `/replay?...&recap=1`：在原回放画布上叠一条**字幕带**（底部，时间戳 + 一句）与**片头 / 片尾卡**（「鲸仔的一天 · 日期 · 鲸仔小镇」/「明天见」）。字幕来源优先 A 的日摘要 `whale-self/data/self/whale/memory/days/<date>.md` 第一段（她自己写的日记，按句切开均分到时间轴，经只读目录 `/selfdays/`）；**没有日摘要时**退回当天记忆事件里重要度最高的 12 条按时间显示（来源标「她记下的事」）。11-06 她还没睡过、没有 Dream，所以这条用的是事件来源。两个来源都没有弹幕 / 评论原文。
- `&seconds=75` 控制整天压缩时长（30–180 s，默认 60）；`&export=1` 自动录制下载。
- **一键脚本** `front_end/tools/recap_export.mjs --date 2026-11-06 [--town main] [--seconds 75] [--base http://127.0.0.1:5174] [--out /home/shan-dw/Project/run/data/recap]`：无头打开回放页、等下载、存到 `run/data/recap/<date>.webm`。需要 playwright（`PLAYWRIGHT_MODULE` 可指向已装好的 node_modules；本机用的是 `/tmp/pw/node_modules/playwright`，**建议总控在 `run/` 下装一份固定的**）。
- **产物**：`run/data/recap/2026-11-06.webm`，**76.5 s、1600×900、VP8、14.6 MB**（浏览器 `<video>` 核验）；数据：七变量 245 点、思考 119 段、记忆 90 条、行动 398 条、聊天 5 条。帧截图 `report_shots/Q1_recap_frame.jpg`（片头卡 + 字幕带）。主播拿到后只需配音或直接发动态；要「60–90 s」之间的其他长度改 `--seconds`。
- 接入 cron 的建议（给总控）：A 的每日导出 01:00 之后跑 `node front_end/tools/recap_export.mjs --date <昨天> --base http://127.0.0.1:5173`（preview 同样带只读目录中间件），约 90 s 出一条。

## 小队列状态

Q0、Q1 完成；Q2（多角色避让 / 连线 / 切换快捷键）等 C 起 NPC 后做；Q3 `/towns` 总览页、Q4 OBS CEF 实测步骤、Q5 v1 细修排后。

## Q0 「她的脑子」页 `/brain`（插队，完成）

- 地址：`http://<前端主机>:5173/brain`（可加 `?date=YYYY-MM-DD` 看别的日子、`&shadow=1` 把 Shadow 层也列出来）。数据源只有总控的只读观察服务 8002（经 Vite 代理 `/observe`，接口形状按 `whale/scripts/observe_server.py`），加一个只读目录 `/selfmem/` → `whale-self/data/self/whale/memory`（点记忆看 .md 全文）。页面只发 GET，不含弹幕原文（观察服务本身也没有）。
- **左栏 实时思考**：`GET /observe/stream`（SSE）滚动每次 Think / Plan（时间、第几步、计划、她的话——从 `finish(reply=…)` 里抠出来、工具调用、模型、是否命中缓存、费用）；Plan 的 `{"plans": [...]}` 展开成编号列表。SSE 断了退回 3 s 一次 `GET /observe/traces?since=`，顶栏显示「实时（SSE / 轮询）」。「跟随最新」勾选时自动贴底。
- **右栏 今天**：顶栏七变量当前值（`/observe/latest.needs_lines`）与今日统计（调用数 / Think / Plan / 费用 / 记忆数）；四个页签——① **计划批次**：每批的标题、时间段、Think 次数、花费、思考摘录（纯工具调用的批次提示去左栏看），下方可展开 `current_plans.md`；② **写下的记忆**：事件 / 认识，倒序，点开读全文（path 用她记忆目录的月索引 `events/<YYYY-MM>/MEMORY.md` 按描述 + 时间对上，兜底用 A 的当日导出）；③ **日程**：`schedule/<date>.md` 渲染（表格 + 折叠的原始 JSON）；④ **Dream / 日摘要**：有则渲染，没有写明「她睡着以后 Dream 才会写」。右上角常显当前计划。`/observe/today` 每 60 s 刷新，`/latest` 每 5 s。
- **点任一条思考** → `GET /observe/prompt/{call_id}`：左边完整输入（system + user，显示字数），右边输出正文 + 工具调用，顶部 usage（in / out / cache）与费用。
- 实测（运行台 8002 真数据，11-06 12:35 前后）：217 次调用、Think 137、Plan 14、$6.72、记忆 65；SSE 连上即回放当天全部 trace 再实时追加；点 10:30:58 的 Plan 看到 4607 字输入与 4 条计划输出；点 12:34 的事件记忆读到 `events/event_000105.md` 全文。截图 `report_shots/Q0_brain_main.jpg`、`Q0_brain_prompt.jpg`、`Q0_brain_memory.jpg`。
- 给总控 / C：观察服务的 `memories[].path` 现在是 null，我靠月索引匹配；`observe_server.py` 若在 `_jsonl(history/events-*.jsonl)` 的 `result.path` 有值时直接带出来，前端会优先用。`traces` 的 `thought` 对 finish 调用只给「→ finish」，她的话在 `tool_calls` 字串里，我按 `'reply': '…'` 抠，若 C 改成 JSON 字串形式也兼容（双引号）。

## 提交号

| 项 | 值 |
|---|---|
| 代码 | `whale-frontend` @ `3a2eb82`（基于 B 的 `1bfe54d`）；**请总控切运行台 5173 到此提交**（`npm run build && npm run preview`），`/brain` 与 `/replay` 都走 preview 自带的代理与只读目录 |
| 新增 | `/brain` 页（`src/brain/*`）、只读目录 `/selfmem`（`VITE_SELF_MEMORY_DIR`）、`tools/recap_export.mjs`、`/replay` 的 `recap= seconds=`、只读目录 `/selfdays`（`VITE_SELF_DAYS_DIR`） |

---

# W5 · 2026-11-06：形象重画、阿蝉操控台、回放页、多镇旁观、游戏机小窗、OBS 布局（原报告）

## 1. 进度（任务 1–7）

| # | 编号 | 状态 | 做了什么 |
|---|---|---|---|
| 1 | E11 | 完成（主播选 v1） | 主播的立绘已在 `front_end/ref/`（鲸仔 / 阿蝉正面全身 + 设定图 + Live2D 渲染）。**v2** 按正面全身图逐像素重画 16×24 四向：鲸仔——深蓝→浅蓝长卷发、白色荷叶边头饰、两侧蓝蝴蝶结与鳍耳、呆毛、白衬衫泡泡袖 + 深蓝裙 + 白围裙 + 蝴蝶结铃铛、白长袜深蓝鞋、身后鲸尾；阿蝉——白色蓬发 + 呆毛、白猫耳粉内耳、右侧两枚蓝发卡、灰蓝眼、蓝短袖衬衫罩白衬衫 + 黑领带 + 工牌、黑裤、白蓝运动鞋、白猫尾。**v1** 是 W4 按 persona 文字画的版本，保留为 `char_whale_v1 / char_achan_v1`，旁观页 `&art=v1` 可切回对比。两版并排：`report_shots/E11_whale_achan_v1_v2.png`（上：跟随画面局部放大；下：完整精灵表）。每套新增第 5 行：坐（正 / 左 / 右）与睡（侧卧盖被）帧，按 `stateLabel` 自动切（睡觉→躺，坐 / 休息 / 玩游戏 / 看书 / 吃饭 / 钓鱼 / 直播→坐）。所有角色同样有坐 / 睡帧。**主播选了 v1，默认已切回 v1**，`&art=v2` 看立绘版 |
| 2 | E12 | 完成 | 操控页（阿蝉）新增快捷区：显示鲸仔状态与坐标；「**走到她旁边**」= 客户端 BFS 到她的相邻格逐格 move（每步仍由后端裁定；无路时退回后端 `move_to_area`）；「**邀请她聊天**」一键 `POST /chat/request`（human 无冷却，B W6），等待态区分 pending / `walking_over`（「对方接受了，正在走过来」）/ `expired`；房间内打字、看她回复、退出；HUD 新增「🐳 鲸仔」块显示她的七变量**分档**（紧急 <10 / 很差 <15 / 偏低 <25 / 一般 / 不错，只读 `/player/{id}/state`）。**实测**（运行台 8000，C 的真 agent）：走到 (50,24) 与她 (51,24) 相邻 → 邀请 → **4 s 内她接受并回了一句**（「阿蝉，我今天还不错！刚在渔夫家的冰箱里吃了一顿…你呢？」）→ 阿蝉再发两句 → 退出。`data/chat/2026-11-06.jsonl` 里 `room_open`、5 条 `message`（`controller` human / agent）、`player_exit` 全在；`GET /history/chat` 一致（截图 `E12_achan_chat.jpg`）。**没做到的**：她对后两句 90 s 内没有再回复——C 的 agent 在房间里的发言由其 think 节奏决定（接受时那句是 respond 自带的 message），不是前端问题；见 §4 给 C |
| 3 | E13 | 完成 | `/replay?town=main&date=2026-11-06[&speed=1\|8\|60\|fit][&export=1]`：只读 A 的 `data/dataset/<town>/<date>/{state,episodes,events}.jsonl` + B 的 `run/data/sandbox/{actions,chat,state}/<date>.jsonl`（Vite 只读目录中间件 `/dataset` `/sandboxdata`，白名单后缀、拒绝 `..`），地图几何取 `GET /world?fields=tiles,objects` 一次。单张 1600×900 画布：左地图 + 鲸仔位置 / 轨迹（有 state 位置样本用样本，样本开始前按 `move / move_to_area` 近似推算并标注）、右上七变量折线（固定顺序配色，图例带当前值）、「她在想」（episodes 的计划 / 想法 / 模型 / 费用）、「发生了什么」（记忆写入 / 行动 / 聊天倒序 11 条）、底部时间轴（思考与聊天刻度）；可拖动、1× / 8× / 60× / 整天压 60 s。**导出**：`MediaRecorder` 录画布 → `replay_<town>_<date>.webm`。11-06 主镇：七变量 30 点、思考 71 段、记忆 60 条、行动 372 条、聊天 5 条；导出 **60.96 s、1600×900、VP8 30 fps、8.9 MB**（`/tmp/pw/shots/replay_main_2026-11-06.webm`，中途 30 s 处正好是全天中点 09:18，截图 `E13_replay.jpg`） |
| 4 | E14 | 完成 | `?town=m2a` → 前端 API 前缀改为 `/t/m2a/api`（含 ws），Vite 读 `run/towns.yaml` 的 `towns.<name>.k` 生成代理表（端口 8000+10k；`VITE_TOWNS_YAML` 可改），前端只传镇名、浏览器不直连后端。信息面板名字行带 `[m2a]`。实测 `http://127.0.0.1:5174/spectate?town=m2a&follow=鲸仔` → `transport=ws`、`online`，m2a 的鲸仔当时离线所以全景（截图 `E14_town_m2a.jpg`）。矩阵格名（M2a）在 towns.yaml 里有但前端拿不到，见 §4 |
| 5 | E15 | 完成（联调通过） | 跟随目标 `/state.game.status === "playing"`（或 tag `gaming` / stateLabel 玩游戏中）时右上出小窗：第几天 / 时段 / 生命 / 饥饿 / 理智 / 死亡 / 局 id，并从 `/gameruns/<run_id>/` 取最新 `.gif/.png`（D 的 `tools/replay.py` 产物）。**联调一局**：以阿蝉走到 `game_console_whale`(10,11) 旁按 E → 后端 `stateLabel`「阿蝉 玩游戏中」、`game = {status: playing, run_id: run-1793933517, day 3, phase day, health 150, hunger 70.5, sanity 137.6}` → 旁观页小窗如实显示（截图 `E15_game_window.jpg`）→ 按 Q 离开 → `game` 清空。该局 D 的 runs 目录里还没有 GIF，小窗只显示指标。新增 `game_console` 物品图 |
| 6 | E16 | 完成（主播已确认） | `&layout=live`：右下留 Live2D 安全区（= `safe=br`，字幕底中、信息面板左下、时钟右上、游戏机小窗右上时钟下）；`&layout=full`：全屏默认。配色按 W4 反馈已柔和化，本周没再改。截图 `E16_layout_live.jpg` / `E16_layout_full.jpg`。**主播确认见 §2** |
| 7 | 报告 | 本文 | — |

## 2. 主播确认（E16 / E11，2026-11-06）

- **E16 OBS 布局**：主播看过 `E16_layout_live.jpg` / `E16_layout_full.jpg` 后答复「**两种都可以**」。直播姬浏览器源用 `…/spectate?follow=鲸仔&hud=0&layout=live`，全屏回放 / 展示用 `&layout=full`。
- **E11 形象**：主播在 v1（persona 文字版）与 v2（按立绘重画）之间选了 **v1**。已把默认改回 v1（`art=v1` 不用再写），v2 保留为 `&art=v2` 随时可看；两版精灵表都在 `public/assets/gen/`。

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
| 代码 | `whale-frontend` @ `38597b2`（基于 B 的 `59d1ac8`）；总控起 5173 请用分支最新提交 |
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
