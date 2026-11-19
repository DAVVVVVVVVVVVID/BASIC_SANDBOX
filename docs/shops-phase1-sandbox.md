# 商店系统第一期 · 沙盒侧接口草案（会话 B，11-19 晚）

依据：whale `docs/systems/shops-system.md`（以末段「主播 11-19 修改」为准）§1 进货、§2 换鱼饵、§4 账本。
**实现放到 11-20 12:00 全镇重置之后**；本文先定形状，C / E 按此对接。定稿时进 api-spec（预计 §12.32），有出入会单独通知。

---

## 1. 进货：「镇外批发 · 周叔」

**身份**：沙盒内的系统 QQ 账号 `supplier_zhou`，显示名「镇外批发 · 周叔」。不跑大模型人格，只按规则回复。
- 出现在杂货店老板（`npc_grocer`）和克劳蒂娜（`claudine`，代下单）的 QQ 通讯录里。其他人给他发消息，统一回「我只跟杂货店做生意。」。

**下单**：照常用 `POST /qq/send {from, to: "supplier_zhou", text}`，自然语言即可，例如「明天要面包 10、食材 12、甜食 6」。
- 沙盒先用规则读单：识别货名（面包 / 甜食 / 食材 / 礼物·小礼物 / 鱼饵）后面跟着的数字，常见说法都能读出来。
- 规则读不出来时，用一次 Haiku 兜底（可配置开关）。
- 什么都读不出来，周叔回：「没看懂要什么，按『面包 10、食材 12』这样写一下？」

**周叔回确认单**：一条 QQ，正文例如「收到：面包 ×10、食材 ×12、甜食 ×6，货款 ¥108 + 运费 ¥10 = ¥118，明早 07:30 前送到。回复『确认』就下单。」
- 消息带 `meta.order`，结构见下。agent 用它就行，不用解析正文。

```json
{"order_id": "po-20261120-3fa1", "status": "quoted", "shop": "grocery",
 "items": [{"item": "bread", "name": "面包", "qty": 10, "unit_cost": 3}],
 "goods": 108, "freight": 10, "total": 118,
 "ordered_by": "claudine", "payer": "npc_grocer",
 "quoted_at": "…", "expires_at": "…（报价后 30 游戏分钟）", "deliver_at": "2026-11-21T07:30:00+08:00"}
```

**确认**：下单人回一条正文是「确认」（也认「好」「下单」「可以」，前后空格和标点不计）的 QQ 给周叔，确认的是这个人最近一张 `quoted` 的单。
- 当场从**店主账户**（`payer` = `npc_grocer`，小克代下单也扣店主）扣 `total`，`status` 变为 `confirmed`。周叔回「好的，明早 07:30 送到。」，带 `meta.order`。
- 余额不足：不成单，周叔回「钱不够，差 ¥x」，`status` 变为 `failed`。
- 30 游戏分钟内没确认：`status` 变为 `expired`，不扣钱。

**截单**：每天 22:00。22:00 之后才确认的单，`deliver_at` 是后天 07:30。

**送达**：到 `deliver_at` 自动进杂货店库房，也就是 `objects[counter].stock`（同时在 `objects[counter].warehouse` 里展示，形状见下）。
- 每种货上限 40，超出的退款到店主账户，并记一笔账。
- 周叔给下单人和店主各发一条 QQ「货到了：面包 ×10…」，带 `meta.order`，此时 `status` 为 `delivered`。

**库存**：杂货店不再每日刷新，库存也不清空。卖完就是卖完（`buy` 回 `out_of_stock`，提示改成「卖完了，等进货」）。
- 重置时的初始库存按配置给。

**查单**：`GET /shop/orders?shop=grocery&status=` 返回订单列表；perceive 给店主和小克带 `orders_pending[]`，内容是 `quoted` 和 `confirmed` 的单。

**库房视图**（会话 E 11-19 定的版式，沙盒照这个给）：`/world.objects[]` 的商店物件带
`warehouse: {stock: {item: n}, capacity: 40, incoming: [{order_id, items: [{item, qty}], eta: ISO}]}`。
`incoming` 只列 `confirmed`、还没送达的单。

**价格**：零售价和进价都写在配置里，店主改不了（没有 `set_price`）。进价初值：面包 3 / 甜食 3 / 食材 4 / 小礼物 15 / 鱼饵 1，运费每单 10。

## 2. 账本（三本）

| shop | 店 | 谁能看 |
|---|---|---|
| `grocery` | 杂货店柜台 `counter` | 杂货店老板、克劳蒂娜 |
| `restaurant` | 餐厅（`bar`、点餐） | 餐厅老板 |
| `fish_stall` | 鱼摊 | 老渔夫 |

**每一笔**：`{ts, game_time, kind, who, who_name, item, item_name, qty, unit_price, amount, note?, ref?}`。
- `kind` 取值：`sale`（卖出）、`purchase`（进货货款）、`freight`（运费）、`refund`（超上限退款）、`recycle`（换鱼饵）、`list`（鱼摊上货）、`spoiled`（摊上变质下架）。第三期加 `lost`（路人流失）。改价已取消，没有 `price`。
- `amount`：对店主是收入记正，支出记负。

**返回形状**（agent 动作和导播接口一样）：
`{shop, name, days: [{date, revenue, cost, gross, stock: {item: n}}], entries: [...]}`。
- `days` 按游戏日汇总，04:00 换日；`stock` 是当天结束时的库存，今天就是当前库存。
- `entries` 是这几天的全部流水，按时间排序。

**agent 动作** `read_ledger {shop, days?=1}`：不占时间，不用站在店里。没有权限 → `no_permission`。

**导播视角**：`GET /shops/{shop_id}/ledger?days=7`，`shop_id` 用物件 id（`counter` / `bar` / `fish_stall`），三本都能看，不经过权限检查、不写动作日志（会话 E 11-19 定；公开开播前加 token，见公开前待办）。

## 3. 换鱼饵（覆盖 v1.4.8 的 `exchange`）

在杂货店柜台：`exchange {item, fish_id?, mode?: "pay" | "donate"}`，`mode` 不带时默认 `pay`。
- **收什么**：变质的鱼（`fish` 且 `freshness: spoiled`）、变质食物（`spoiled_food`）、钓上来的垃圾（`junk_*`）。每件换 1 个鱼饵。鱼饵永久保质，凭空产出，不消耗店里的库存。
- `pay`：换的人付 1 金币进店主账户，鱼饵进换的人背包。
- `donate`：不付钱，鱼饵进杂货店库存（`stock.bait` +1），店主可以直接卖。
- 两种都记杂货店账本 `kind: recycle`。
- 失败：`not_exchangeable`（不收这个）、`not_spoiled`（鱼还没坏）、`no_item`、`insufficient_funds`（`pay` 时连 1 金币都没有）。

## 4. 变质物 2 日消失

变质约 2 游戏日后，还没拿去换的，自动从背包、冰箱、鱼摊移除：
- 鱼：变质时刻之后再过 2 日，也就是常温日龄满 8 日；冰箱里按半速算。
- `spoiled_food`：变质时刻之后再过 2 日。
- 移除时给持有人推一条 pendingMessage「X 放坏太久，扔掉了」，external 记 `kind=spoil action=discard_auto`。冰箱里的物品推给冰箱主人。

## 5. 不在第一期

- 餐厅现点现做（第二期）、路人顾客（第三期）。
- 改价已取消。
