// 单测：world-v1.1 显示用纯函数
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { gameNowMs, busyProgress, busyText, fridgeRows, supplyText, dailyUseLines, rentText, canEatHere } from '../src/game/v11'

const ws = { date: '2026-11-14', time: '12:10:00' } as never
const now = gameNowMs(ws)!

test('游戏时间拼接与进食插值', () => {
  assert.equal(new Date(now).toISOString(), '2026-11-14T04:10:00.000Z')
  const b = { kind: 'eating', item: 'home_meal', started_at: '2026-11-14T12:00:00+08:00', ends_at: '2026-11-14T12:15:00+08:00', gain: { fullness: 40 } }
  const p = busyProgress(b, now)!
  assert.ok(Math.abs(p.progress - 10 / 15) < 1e-6); assert.equal(p.remainingS, 300)
  assert.equal(busyText(b, now), '🍴 吃家常菜 · 剩 5 分钟 · 饱腹 +40')
  // 没时间字段退回快照
  const q = busyProgress({ kind: 'eating', progress: 0.5, remaining_s: 120 }, now)!
  assert.equal(q.progress, 0.5); assert.equal(q.remainingS, 120)
})

test('冰箱行：保鲜天数按 expires_at 算、坏食标记', () => {
  const rows = fridgeRows({ contents: [{ item: 'home_meal', count: 4, expires_at: '2026-11-16T12:10:00+08:00', expires_in_days: 2, spoiled: false }, { item: 'spoiled_food', count: 1, spoiled: true }] }, now)
  assert.equal(rows[0].days, 2); assert.equal(rows[0].name, '家常菜'); assert.equal(rows[0].spoiled, false)
  assert.equal(rows[1].spoiled, true)
})

test('柜台今日供应', () => {
  const o = { daily_supply: { ingredients: 12 }, stock: { ingredients: 7 }, restock_at: '08:00' }
  assert.equal(supplyText(o, 'ingredients'), '今日 12 · 剩 7')
  assert.equal(supplyText({ ...o, stock: { ingredients: 0 } }, 'ingredients'), '今日 12 · 卖完（08:00 上新）')
  assert.equal(supplyText({ stock: { fish: 3 } }, 'fish'), '剩 3')
  assert.equal(supplyText({}, 'fish'), null)
})

test('每日上限 / 房租 / 餐桌许可', () => {
  const lines = dailyUseLines({ pc: { used_min: 210, limit_min: 360 }, phone: { used_min: 0, limit_min: 120 }, stream_desk: { used_min: 240, limit_min: 240 } })
  assert.deepEqual(lines.map(l => l.text), ['🖥 电脑 3.5/6 h', '📺 直播台 4/4 h · 今天用够了'])
  assert.equal(dailyUseLines({ pc: { used_min: 12, limit_min: 360 } })[0].text, '🖥 电脑 12 分/6 h')
  assert.equal(rentText({ amount: 300, due_at: '2026-12-01T08:00:00+08:00', due_in_days: 3 })!.text, '🏠 房租 300 · 12-01 到期（3 天后）')
  const od = rentText({ amount: 1000, overdue: true, owed: 2000, since: '2026-12-01T08:00:00+08:00', items: [{ kind: 'home', amount: 400 }, { kind: 'shop', amount: 600 }] })!
  assert.equal(od.overdue, true); assert.match(od.text, /欠租 2000 = 住房 400 \+ 铺面 600（自 12-01）/)
  assert.equal(rentText(null), null)
  assert.equal(canEatHere({ dining: true, dining_allow: null }, 'home_meal'), true)
  assert.equal(canEatHere({ dining: true, dining_allow: ['bread'] }, 'home_meal'), false)
  assert.equal(canEatHere({ dining: false }, 'bread'), false)
})
