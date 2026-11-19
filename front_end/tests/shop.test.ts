// 点商店物件弹商店面板：货品 / 可卖 / 鱼的 meta 标签 / 距离
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { goodsRows, sellRows, metaChips, distanceTo, shopFailText } from '../src/game/shop'

const counter = { shop: [{ type: 'bait', name: '鱼饵', price: 3, sell: null, stock: 10 }, { type: 'bread', name: '面包', price: 5, sell: null, stock: 0 }], stock: null, daily_supply: null }
const stall = { shop: [{ type: 'fish', name: '鱼', price: 15, sell: 10, stock: 6 }, { type: 'fish', id: 'f1', price: 22, stock: 1, meta: { species_name: '金鳞鲤', weight_kg: 1.6, grade: 'rare', freshness: 'fresh' } }], stock: null, daily_supply: null }
const bar = { shop: [{ type: 'fish', name: '鱼', price: null, sell: 10, stock: null }] }

test('货品：只列在卖的；逐条鱼带 id 与 meta 标签', () => {
  assert.deepEqual(goodsRows(counter).map(r => [r.name, r.price, r.stock]), [['鱼饵', 3, 10], ['面包', 5, 0]])
  const g = goodsRows(stall)
  assert.equal(g.length, 2)
  assert.equal(g[1].itemId, 'f1')
  assert.deepEqual(g[1].chips.map(c => `${c.label}:${c.value}`), ['品种:金鳞鲤', '重量:1.6 kg', '品级:稀有', '新鲜度:新鲜'])
  assert.equal(goodsRows(bar).length, 0)
})

test('可卖：背包里这家收的类型', () => {
  const inv = [{ type: 'fish', count: 2, meta: { freshness: 'stale' } }, { type: 'bread', count: 1 }]
  const s = sellRows(bar, inv)
  assert.equal(s.length, 1)
  assert.equal(s[0].sell, 10)
  assert.equal(s[0].chips[0].value, '不新鲜')
  assert.equal(sellRows(counter, inv).length, 0)
})

test('meta 中英文都认；距离取最近一格；失败文案', () => {
  assert.deepEqual(metaChips({ grade: '传说', freshness: '变质' }).map(c => c.tone), ['legendary', 'spoiled'])
  assert.deepEqual(metaChips(null), [])
  assert.equal(distanceTo({ x: 36, y: 12 }, { position: { x: 37, y: 11 }, tiles: [{ x: 37, y: 11 }, { x: 38, y: 11 }] }), 2)
  assert.equal(shopFailText('shop_closed', { opens_at: '09:00' }), '已经打烊了，09:00 开门')
  assert.equal(shopFailText('insufficient_funds', { message: '钱不够，还差 3' }), '钱不够，还差 3')
})
