import { test } from 'node:test'
import assert from 'node:assert/strict'
import { godotCharKeyFor, godotPoseFor, parseGodotCharManifest } from '../src/game/godotChars'

test('外观键与 Godot Actor.gd key_for 一致', () => {
  assert.equal(godotCharKeyFor('阿蝉_83f3f5', 'human', 'achan'), 'achan')
  assert.equal(godotCharKeyFor('小千', 'agent', 'npc_xiaoqian'), 'claudine')
  assert.equal(godotCharKeyFor('克劳蒂娜', 'agent', null), 'claudine')
  assert.equal(godotCharKeyFor('鲸仔', 'agent', 'whale'), 'whale')
  assert.equal(godotCharKeyFor('餐厅老板', 'agent', 'npc_rest_owner'), 'cook')
  assert.equal(godotCharKeyFor('杂货店老板娘', 'agent'), 'grocer')
  assert.equal(godotCharKeyFor('老渔夫', 'agent', 'npc_fisher'), 'fisher')
  assert.equal(godotCharKeyFor('测试e楼梯', 'human'), 'achan')
  assert.ok(['cook', 'grocer', 'fisher'].includes(godotCharKeyFor('路人甲', 'agent')))
})

test('姿态映射同 _refresh_anim：睡→eat→phone→talk→sit，缺动画退档', () => {
  const all = () => true
  assert.equal(godotPoseFor('💤 睡觉中', all), 'sleep')
  assert.equal(godotPoseFor('🍴 吃饭中', all), 'eat')
  assert.equal(godotPoseFor('📱 刷手机', all), 'phone')
  assert.equal(godotPoseFor('📺 直播中', all), 'talk')
  assert.equal(godotPoseFor('🖥 工作中', all), 'sit')
  assert.equal(godotPoseFor('💬 聊天中', all), 'talk')
  assert.equal(godotPoseFor('💤 离线', all), null)
  assert.equal(godotPoseFor('🍴 吃饭中', a => a !== 'eat'), 'sit')
  assert.equal(godotPoseFor(null, all), null)
})

test('清单解析：anchor / 动画条', () => {
  const m = parseGodotCharManifest({ format: 2, images_dir: 'town/achan', frame_w: 120, frame_h: 126, anchor: [60, 124], scale: 0.5, animations: { idle: { file: 'achan_idle.png', frames: 4, fps: 4 }, walk: { file: 'achan_walk.png', frames: 6, fps: 8, loop: true } } })
  assert.ok(m)
  assert.deepEqual(m!.anchor, [60, 124])
  assert.equal(m!.animations.walk.frames, 6)
  assert.equal(parseGodotCharManifest({ frame_w: 1 }), null)
})

test('路人顾客：sprite 优先，否则 agent_id passerby_<日期>_<NN> 占位推算；isPasserby', async () => {
  const { godotCharKeyFor, isPasserby } = await import('../src/game/godotChars')
  assert.equal(godotCharKeyFor('张大爷', 'script', 'passerby_20261121_03', 'passer05'), 'passer05')
  assert.equal(godotCharKeyFor('张大爷', 'script', 'passerby_20261121_03', null), 'passer03')
  assert.equal(godotCharKeyFor('路人', 'script', 'passerby_20261121_08'), 'passer02')
  assert.equal(godotCharKeyFor('鲸仔', 'agent', 'whale', null), 'whale')
  assert.equal(isPasserby({ role: 'passerby' }), true)
  assert.equal(isPasserby({ agent_id: 'whale', controller: 'agent' }), false)
})
