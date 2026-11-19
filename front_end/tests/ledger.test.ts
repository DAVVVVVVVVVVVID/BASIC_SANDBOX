// 商店账本 / 库房：宽容解析 + 汇总（B 的 read_ledger 形状未定）
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { normalizeLedger, summarize, entriesIn, normalizeWarehouse, etaText, demoLedger } from '../src/game/ledger'

test('账本：几种字段写法都认，按时间倒序', () => {
  const l = normalizeLedger({ shop: 'counter', entries: [
    { ts: '2026-11-19T09:00:00', type: 'sell', buyer_name: '鲸仔', item_name: '面包', qty: 2, price: 5 },
    { game_time: '2026-11-19T18:00:00', kind: 'lost_customer', customer: '路人', item: '甜食', reason: '卖完了' },
    { ts: '2026-11-18T07:30:00', kind: 'restock', item: '面包', qty: 10, amount: -30 },
  ], days: [{ date: '2026-11-18', revenue: 50, cost: 40 }, { date: '2026-11-19', income: 10, expense: 0, stock: { 面包: 8 } }] })!
  assert.equal(l.entries[0].kind, 'lost')
  assert.equal(l.entries[1].amount, 10)
  assert.equal(l.entries[2].kind, 'purchase')
  assert.equal(l.days[0].date, '2026-11-19')
  assert.equal(l.days[1].gross, 10)
  const today = summarize(l, 'today')
  assert.deepEqual([today.revenue, today.cost, today.gross, today.lost], [10, 0, 10, 1])
  assert.equal(summarize(l, 'week').revenue, 60)
  assert.equal(entriesIn(l, 'today', 'sale').length, 1)
  assert.equal(entriesIn(l, 'week', 'all').length, 3)
  assert.equal(normalizeLedger({ foo: 1 }), null)
})

test('库房与明早到货', () => {
  const w = normalizeWarehouse({ warehouse: { stock: { bread: 22 }, capacity: 40, incoming: [{ items: [{ item: 'bread', qty: 10 }, { item: 'ingredients', qty: 12 }], eta: '2026-11-20T07:30:00+08:00' }] } })!
  assert.equal(w.stock.bread, 22); assert.equal(w.cap, 40)
  assert.deepEqual(w.incoming.map(i => [i.item, i.qty]), [['bread', 10], ['ingredients', 12]])
  assert.equal(etaText(w.incoming[0].eta, '2026-11-19'), '明早 07:30')
  assert.equal(etaText('2026-11-21T07:30:00', '2026-11-19'), '后天 07:30')
  assert.equal(normalizeWarehouse({ shop: [] }), null)
})

test('样例：7 天、毛利 = 收入 − 成本', () => {
  const l = demoLedger('counter', '2026-11-19')
  assert.equal(l.days.length, 7)
  assert.equal(l.days[0].gross, l.days[0].revenue - l.days[0].cost)
})
