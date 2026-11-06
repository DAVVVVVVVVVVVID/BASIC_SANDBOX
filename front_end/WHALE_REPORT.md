# WHALE_REPORT — 会话 E（BASIC_SANDBOX/front_end，前端观感线）

分支 `whale-frontend`，worktree `own-repos/BASIC_SANDBOX-fe/`，已 rebase 到 B 的 `4d6a931`（含 B17 `GET /ws/world`）。只改了 `front_end/`。
总控把运行台 5173 换到本分支时请用下文「提交号」一节。

---

# W3 · 2026-11-06：E1–E5 全部完成

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
| 代码 | `whale-frontend` @ `ddc555d`（基于 B 的 `4d6a931`）；本报告提交在其后，总控起 5173 请用含报告的最新提交 |
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
