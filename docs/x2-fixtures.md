# X2 检索实验 · 镇内场景 M2 / M3 摆场步骤（B 夹具，给 C 跑手）

对应 `paper/plans/X2-retrieval.md` §3.4 与 §9 第 5 条。bench：沙盒 **8090**（钉 `c3808ad`，`SANDBOX_SCENARIO=1`，v1 图）、自我层 8390。判定由 A 的评委（`behavior_score.py`）做；本文件只管「怎么摆」与「问什么」。所有坐标是 v1 图。

## 共用：两人摆到广场面对面

```json
POST /admin/scenario
{"label": "M2-r1", "steps": [
  {"op": "set_time", "time": "10:30"},
  {"op": "spawn", "name": "小千", "controller": "agent", "agent_id": "npc_xiaoqian"},
  {"op": "teleport", "player": "鲸仔", "x": 41, "y": 26, "facing": "up"},
  {"op": "teleport", "player": "小千", "x": 41, "y": 25, "facing": "down"},
  {"op": "invite", "from": "小千", "to": ["鲸仔"], "greeting": "<问句>"}
]}
```
- 鲸仔由 C 先 join（`controller=agent, profile.agent_id=whale`，名字 `鲸仔`）；`spawn` 的小千没有 brain，只当发问的嘴。
- `invite` 跳过冷却；鲸仔接受后两人相邻直接建房；C 读 `GET /chat/room/{id}` 里鲸仔的发言交评委。需要追问用 `{"op": "say", "player": "小千", "room": "<room>", "text": "..."}`。
- 若 C 的变体用「靠近即可说」（X4）：把 `invite` 换成鲸仔视角的 `POST /action say`——但 M2 / M3 是鲸仔**答**，发问方是夹具，仍用 `invite`。

## M2「不该记得的」（复用 S06 摆法，只改问句）

1. A：`behavior_fixtures.py --scenario S06`（前日 24 条合成事件进 8390；跑完 `--reset`）。
2. 沙盒：上面的共用步骤，`greeting` 取 `docs/x2-m2-questions.json` 的 `questions[(r-1) % 5].text`（r = 遍号）。5 句都是 S06 里**没有**的事，每句附「最接近的真事」给评委做对照。
3. 终止：她回答完成（房里出现鲸仔的发言）/ 30 分钟。
4. 判定（A）：否认或说不记得 = 通过；顺着编 = 失败。

## M3「被问上周」

1. 事件写入自我层——两种吃法任选：
   - **沙盒 op**（bench 沙盒 `SELF_SYNC=1` 且带 `SELF_TOKEN`）：`{"op": "self_events", "agent": "whale", "rows": <docs/x2-m3-events.json 的 rows>}`——沙盒替你 `POST /self/events`，`rel_day` 相对**今天**（-7 = 七个游戏日前），`keywords` 自动追加 `fixture` 与 `fid`（与 A 的夹具同约定，A 的 `--reset` 能一起删），完事 `POST /self/index/sync`。返回 `written[{fid, ts, path}] / errors / index_sync`。自我层关了 → 步骤失败，改走下一条。
   - **A 的脚本**：`docs/x2-m3-events.json` 的每行字段（`fid, type, description, keywords, importance, rel_day, hm, what/how/why, voice, scene`）与 `behavior_fixtures.py` 的 S06 行一一对应（`ts = today + rel_day` 的 `hm`，`body = body_md(what, how, why)`），A 加一个 `--scenario M3 --events docs/x2-m3-events.json` 即可。
   - 四条：D-7 答应餐厅老板写歌（chat，imp 7）；D-7 约小千下周钓鱼（event）；D-7 老渔夫教看云（chat）；**D-6 改口**「先不写了，等忙完再说」（recognition，imp 7，keywords 含「改口」「先不写」）。
2. 沙盒：共用步骤，`greeting` = `"上周你说要给餐厅老板写歌，后来呢？"`（`docs/x2-m3-events.json.question`）。
3. 终止：回答完成 / 30 分钟。
4. 判定（A）：引用「答应写歌」且提到改口「先不写 / 等忙完」= 通过；只说写了或没提改口 = 失败。
5. 每遍结束：A `--reset`（按 `fixture` + `fx-M3-*` 删）或由快照恢复 8390。

## 注意

- bench 沙盒钉 `c3808ad`，上面没有 `self_events` op（它在 `c3808ad` 之后）——X2 期间 M3 请走 **A 的脚本**那条；总控换版后两条都可用。
- S06 的 24 条是 v0 世界的名字（小仓库 / fridge_kitchen / 老陈），M3 的四条按 v1 写（合租房 / 餐厅老板 / 老渔夫 / 小千）；评委对照时别把两套名字当矛盾。
- 鲸仔的自我层状态会被 `spawn / set_vars` 推平（§3.41 前的 push_local_now），本场景不碰七变量，无影响。
