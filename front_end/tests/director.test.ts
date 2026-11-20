// 小镇自动导播打分器（town-director-plan §1）
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { tick, newMemory, lockOn, baseScore, isCandidate, type Candidate } from '../src/director/scorer'

const whale: Candidate = { id: 'w', name: '鲸仔', agentId: 'whale', controller: 'agent', state: 'idle' }
const cl: Candidate = { id: 'c', name: '克劳蒂娜', agentId: 'claudine', controller: 'agent', state: 'idle' }
const fisher: Candidate = { id: 'f', name: '老渔夫', agentId: 'npc_fisher', controller: 'agent', state: 'using', stateLabel: '钓鱼中' }
const achan: Candidate = { id: 'a', name: '阿蝉', agentId: 'achan', controller: 'human', inChat: true }
const passer: Candidate = { id: 'p', name: '张大爷', agentId: 'passerby_20261121_01', controller: 'script', role: 'passerby', trading: true }

test('阿蝉 / 路人不当候选；鲸仔 ×1.3', () => {
  assert.equal(isCandidate(achan), false); assert.equal(isCandidate(passer), false); assert.equal(isCandidate(whale), true)
  const r = tick([achan, passer, { ...cl, state: 'walking' }, { ...whale, state: 'walking' }], [], newMemory(0), 0)
  assert.equal(r.follow, 'w')
  assert.equal(baseScore({ ...whale, inChat: true }, 0, []).score, 130)
})

test('全镇发呆 / 睡觉 → 全景', () => {
  const r = tick([whale, { ...cl, stateLabel: '睡觉中' }], [], newMemory(0), 0)
  assert.equal(r.follow, null); assert.equal(r.situation, 'panorama')
})

test('最短停留 20 s；对话中不切；之后更好看的才换', () => {
  const m = newMemory(0)
  assert.equal(tick([fisher, whale], [], m, 0).follow, 'f')        // 钓鱼 30 > 鲸仔发呆 13
  assert.equal(tick([fisher, { ...whale, inChat: true }], [], m, 10_000).follow, 'f')   // 10 s：最短停留
  assert.equal(tick([fisher, { ...whale, inChat: true }], [], m, 22_000).follow, 'w')   // 过 20 s 换到对话
  const r = tick([{ ...fisher, progress: 0.9 }, { ...whale, inChat: true }], [], m, 60_000)
  assert.equal(r.follow, 'w'); assert.equal(r.reason, '对话进行中')
})

test('瞬时事件插播 15 s 后切回', () => {
  const m = newMemory(0)
  tick([fisher, { ...whale, state: 'walking' }], [], m, 0)
  assert.equal(m.current, 'f')
  const r = tick([fisher, { ...whale, state: 'walking' }], [{ who: 'w', at: 30_000, label: '写完了《楼下有水声》' }], m, 30_500)
  assert.equal(r.follow, 'w'); assert.equal(r.situation, 'event')
  assert.equal(tick([fisher, { ...whale, state: 'walking' }], [], m, 40_000).follow, 'w')   // 插播中
  assert.equal(tick([fisher, { ...whale, state: 'walking' }], [], m, 46_000).follow, 'f')   // 切回
})

test('最长 3 分钟换人；新鲜度衰减', () => {
  const m = newMemory(0)
  const a = { ...fisher }, b = { ...cl, state: 'walking' }
  tick([a, b], [], m, 0)
  assert.equal(m.current, 'f')
  const r = tick([a, b], [], m, 181_000)
  assert.equal(r.follow, 'c'); assert.match(r.reason, /3 分钟/)
  const sc = tick([a, b], [], m, 181_000 + 125_000).scores.find(s => s.id === 'c')!
  assert.ok(sc.score < 15)   // 看了 2 分钟：15 × 0.8
})

test('手动锁定优先，到期解除', () => {
  const m = newMemory(0)
  lockOn(m, 'c', 1, 0)
  assert.equal(tick([fisher, { ...whale, inChat: true }, cl], [], m, 1000).follow, 'c')
  assert.equal(tick([fisher, { ...whale, inChat: true }, cl], [], m, 61_000).follow, 'w')
})

test('事件提示：公开事件 / 旧事件兜底 / 同人同类 10 s 合并', async () => {
  const { fromPublicEvent, fromLegacy, mergeEvent } = await import('../src/director/events')
  const e1 = fromPublicEvent({ seq: 1, verb: 'buy', category: 'trade', who: { id: 'w', name: '鲸仔' }, gold_delta: -8, text: '鲸仔在杂货店买了 2 个面包（¥8）' }, 1000)!
  assert.equal(e1.icon, '🛒'); assert.equal(e1.category, 'trade')
  const nameOf = (id: string) => ({ f: '老渔夫' } as Record<string, string>)[id] ?? id
  const f = fromLegacy('fishing', { entity: 'f', cast: { result: 'fish', fish: { name: '金鳞鲤', weight: 2.2, tier: 'rare' }, record_break: true } }, nameOf, 2000)!
  assert.equal(f.text, '老渔夫 钓到 金鳞鲤 2.2 kg，破纪录！')
  assert.equal(fromLegacy('fishing', { entity: 'f', cast: { result: 'empty' } }, nameOf, 2000), null)
  assert.equal(fromLegacy('action', { entity: 'w', action: 'buy', success: true, item_name: '面包', gold_delta: -5 }, () => '鲸仔', 1)!.text, '鲸仔 买了 面包 −5')
  let l = mergeEvent([], e1)
  l = mergeEvent(l, { ...e1, key: 'x', at: 5000, gold: -6, text: '鲸仔在杂货店买了 1 个甜食（¥6）' })
  assert.equal(l.length, 1); assert.equal(l[0].count, 2); assert.equal(l[0].gold, -14)
  l = mergeEvent(l, { ...e1, key: 'y', at: 30_000 })
  assert.equal(l.length, 2)
})
