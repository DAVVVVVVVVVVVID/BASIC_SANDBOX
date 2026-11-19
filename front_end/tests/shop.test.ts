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
  // B 鱼 meta 草案：tier 品级、name 中文名（有 name 不再出品种标签）
  assert.deepEqual(metaChips({ fish_id: 'f9', species: 'golden_carp', name: '金鳞鲤', tier: 'rare', weight: 1.6, freshness: 'fresh' }).map(c => `${c.label}:${c.value}`), ['重量:1.6 kg', '品级:稀有', '新鲜度:新鲜'])
  assert.equal(distanceTo({ x: 36, y: 12 }, { position: { x: 37, y: 11 }, tiles: [{ x: 37, y: 11 }, { x: 38, y: 11 }] }), 2)
  assert.equal(shopFailText('shop_closed', { opens_at: '09:00' }), '已经打烊了，09:00 开门')
  assert.equal(shopFailText('insufficient_funds', { message: '钱不够，还差 3' }), '钱不够，还差 3')
})

test('§12.31 鱼摊 listings 逐条、卖鱼带 fish_id、钓鱼提示', async () => {
  const { fishingBubbleText } = await import('../src/game/fishing')
  const stall2 = { shop: [{ type: 'fish', name: '鱼', price: 15, sell: 10, stock: 6 }], stock: null, daily_supply: null, listings: [{ listing_id: 'f-1', species: 'golden_carp', name: '金鳞鲤', tier: 'rare', weight: 1.6, freshness: 'fresh', price: 38 }] }
  const g = goodsRows(stall2)
  assert.deepEqual(g.map(r => [r.name, r.price, r.listingId]), [['金鳞鲤', 38, 'f-1']])
  assert.deepEqual(g[0].chips.map(c => c.value), ['1.6 kg', '稀有', '新鲜'])
  assert.equal(goodsRows({ ...stall2, listings: [] }).length, 0)   // 摊上没鱼就是没鱼
  const s = sellRows(stall2, [{ type: 'fish', count: 1, meta: { fish_id: 'f-9', name: '鲫鱼', tier: 'common', weight: 1.1, freshness: 'fresh' } }])
  assert.equal(s[0].fishId, 'f-9'); assert.equal(s[0].sell, null)
  assert.equal(fishingBubbleText({ result: 'fish', fish: { name: '月光鲶', tier: 'legend', weight: 2.4 }, tier_name: '传说' }), '🌟 传说！钓到月光鲶 2.4 kg（传说）')
  assert.equal(fishingBubbleText({ result: 'fish', fish: { name: '鲫鱼', tier: 'common', weight: 1.0 }, record_break: true }), '🏆 破纪录！钓到鲫鱼 1.0 kg')
  assert.equal(fishingBubbleText({ result: 'junk', item_name: '旧靴子' }), '🎣 钓上来一个旧靴子……')
  assert.equal(fishingBubbleText({ result: 'empty' }), null)
})
