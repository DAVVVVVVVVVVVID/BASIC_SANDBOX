// 单测：头顶状态标签 / 睡坐姿贴靠（总控 11-08「鲸仔边睡觉边行动」）
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { deriveStateLabel, poseAnchorsFor } from '../src/game/stateLabel'
import type { GameObject, OtherPlayer } from '../src/types'

const bed = { id: 'bed_whale', type: 'bed', name: '床', position: { x: 3, y: 22 }, tiles: [{ x: 3, y: 22 }, { x: 3, y: 23 }], userList: ['鲸仔'], effects: [{ type: 'tag', key: 'sleeping', value: null }], usePos: [{ x: 3, y: 22 }] } as unknown as GameObject
const objects = [bed]
const whale = (over: Partial<OtherPlayer>): OtherPlayer => ({ id: '鲸仔', name: '鲸仔', position: { x: 4, y: 22 }, facing: 'down', state: 'idle', online: true, ...over } as unknown as OtherPlayer)

test('走路中：忽略滞后的 sleeping 标签与床的 userList，不显示睡觉、不贴床', () => {
  const p = whale({ state: 'walking', tags: ['sleeping'], position: { x: 6, y: 24 } })
  assert.equal(deriveStateLabel(p, objects, ['sleeping']), null)
  assert.deepEqual(poseAnchorsFor(p, objects), { sleep: null, sit: null })
  const q = whale({ state: 'walking', position: { x: 4, y: 22 } })   // 刚起床、还挨着床、userList 还含她
  assert.equal(deriveStateLabel(q, objects), null)
  assert.deepEqual(poseAnchorsFor(q, objects), { sleep: null, sit: null })
})

test('walking_over 仍显示「走过去聊」', () => {
  assert.equal(deriveStateLabel(whale({ state: 'walking_over', tags: ['sleeping'] }), objects), '💬 走过去聊')
})

test('真在用床：睡觉中 + 贴到床中心', () => {
  const p = whale({ state: 'using', usingObjectId: 'bed_whale', tags: ['sleeping'], position: { x: 3, y: 22 } })
  assert.equal(deriveStateLabel(p, objects), '💤 睡觉中')
  const a = poseAnchorsFor(p, objects)
  assert.ok(a.sleep); assert.equal(a.sleep!.x, 336); assert.equal(a.sleep!.y, 2208); assert.equal(a.sleep!.angle, 0)
})

test('tagsHint 只在 using / idle 时参与', () => {
  assert.equal(deriveStateLabel(whale({ state: 'using', usingObjectId: 'bed_whale' }), objects, ['eating']), '🍴 吃饭中')
  assert.equal(deriveStateLabel(whale({ state: 'idle' }), objects, ['streaming']), '📺 直播中')
  assert.equal(deriveStateLabel(whale({ state: 'walking' }), objects, ['streaming']), null)
})

test('idle 时床的 userList 滞后不再反查成睡觉；老后端（没有 state）仍走 userList 反查', () => {
  assert.equal(deriveStateLabel(whale({ state: 'idle' }), objects), null)
  assert.equal(deriveStateLabel(whale({ state: undefined as unknown as OtherPlayer['state'] }), objects), '💤 睡觉中')
})

test('离线优先', () => {
  assert.equal(deriveStateLabel(whale({ online: false, state: 'walking' }), objects), '💤 离线')
})
