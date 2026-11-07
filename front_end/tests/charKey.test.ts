// 单测：名字 → 外观（esbuild 打包后用 node --test 跑；见 package.json test:unit）
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { charKeyFor, NPC_POOL } from '../src/game/charKey'

test('04-npcs 六个角色显式匹配', () => {
  assert.equal(charKeyFor('鲸仔'), 'whale')
  assert.equal(charKeyFor('阿蝉'), 'achan')
  assert.equal(charKeyFor('小千'), 'regular')
  assert.equal(charKeyFor('千小满'), 'regular')
  assert.equal(charKeyFor('餐厅老板'), 'cook')
  assert.equal(charKeyFor('餐厅老板（厨师）'), 'cook')
  assert.equal(charKeyFor('杂货店老板'), 'grocer')
  assert.equal(charKeyFor('杂货店老板娘'), 'grocer')
  assert.equal(charKeyFor('老渔夫'), 'fisher')
})

test('带实例后缀的 id 也能匹配', () => {
  assert.equal(charKeyFor('餐厅老板_634783'), 'cook')
  assert.equal(charKeyFor('杂货店老板_d35843'), 'grocer')
  assert.equal(charKeyFor('小千_aaa22c'), 'regular')
})

test('regular 是小千专属：任何未知名字都不会长成小千', () => {
  assert.ok(!NPC_POOL.includes('regular'))
  assert.ok(!NPC_POOL.includes('villager'))
  for (const name of ['路人甲', '测试员', 'E测试', 'npc_7', 'bob', '镇长', '邮递员', '', '张三', '李四', '王五', 'agent-42']) {
    const k = charKeyFor(name)
    assert.notEqual(k, 'regular', `${name} → ${k}`)
    assert.ok(NPC_POOL.includes(k), `${name} → ${k} 不在池子里`)
  }
})

test('人类操控的未知名字默认阿蝉；哈希稳定', () => {
  assert.equal(charKeyFor('E测试', 'human'), 'achan')
  assert.equal(charKeyFor('路人甲'), charKeyFor('路人甲'))
})
