// 像素商店：图标映射 / 切行 / 卡片
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { iconUrl, rowsOf, kindOfObject, weightText } from '../src/ui/shop/shopSkin'
import { goodsCards, menuCards } from '../src/ui/shop/cards'

test('图标映射：B 的 item / dish / species → 切图 key', () => {
  assert.equal(iconUrl('gift'), 'assets/ui/shop/icon_small_gift.png')
  assert.equal(iconUrl('home_rice'), 'assets/ui/shop/icon_meal_homestyle.png')
  assert.equal(iconUrl('star_kaluga'), 'assets/ui/shop/icon_star_sturgeon.png')
  assert.equal(iconUrl('junk_can'), 'assets/ui/shop/icon_soda_can.png')
  assert.equal(iconUrl('nope'), null)
  assert.deepEqual(rowsOf([1, 2, 3, 4, 5]), [[1, 2, 3], [4, 5]])
  assert.equal(kindOfObject({ type: 'shop_counter', id: 'counter' }), 'grocery')
  assert.equal(kindOfObject({ type: 'bar', id: 'bar' }), 'restaurant')
  assert.equal(kindOfObject({ type: 'fish_stall', id: 'fish_stall' }), 'fish_stall')
  assert.equal(weightText(2.21), '2.2kg')
})

test('卡片：杂货库存 / 售罄；鱼摊逐条重量；菜单 available', () => {
  const g = goodsCards({ shop: [{ type: 'bread', name: '面包', price: 5, stock: 8 }, { type: 'gift', name: '小礼物', price: 25, stock: 0 }], stock: null, daily_supply: null })
  assert.deepEqual(g.map(c => [c.name, c.sub, c.soldOut]), [['面包', '8', false], ['小礼物', '0', true]])
  const f = goodsCards({ shop: [], stock: null, daily_supply: null, listings: [{ listing_id: 'L1', species: 'golden_carp', name: '金鳞鲤', tier: 'rare', weight: 2.2, freshness: 'fresh', price: 48 }] })
  assert.deepEqual([f[0].name, f[0].sub, f[0].tier, f[0].icon], ['金鳞鲤', '2.2kg', 'rare', 'assets/ui/shop/icon_golden_carp.png'])
  const m = menuCards([{ dish: 'catch_of_day', name: '今日鲜鱼', price: 20, price_note: '按鱼', available: false, message: '今天没进鱼' }, { dish: 'dessert', name: '甜品', price: 10, available: true }])
  assert.equal(m[0].soldOut, true); assert.equal(m[0].priceText, '20起'); assert.equal(m[0].note, '今天没进鱼')
  assert.equal(m[1].icon, 'assets/ui/shop/icon_dessert.png')
})
