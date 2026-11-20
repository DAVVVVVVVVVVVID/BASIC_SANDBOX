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

// ── 三期（phase3.ts）──
import { activityFromWorld, createKind, createProgress, latestWork, todaySummaryRows } from '../src/director/phase3'
import { fromLegacy } from '../src/director/events'

test('三期：物件类型 / tags 推 activity（now 上线前兜底）', () => {
  assert.equal(activityFromWorld('pc_music', []), 'create')
  assert.equal(activityFromWorld('pc_desk', []), 'create')
  assert.equal(activityFromWorld('phone', []), 'qq')
  assert.equal(activityFromWorld(null, ['reading']), 'qq')
  assert.equal(activityFromWorld('bed_21', []), 'sleep')
  assert.equal(activityFromWorld('pc', ['streaming']), 'live')
  assert.equal(activityFromWorld('shelf', []), null)
  assert.equal(activityFromWorld(null, null), null)
})

test('三期：坐满进度按 daily_use 增量，换物件 / 回退重置基线', () => {
  assert.deepEqual(createKind('pc_music')?.needMin, 30)
  assert.deepEqual(createKind('stream_desk')?.kind, 'script')
  assert.equal(createKind('bed'), null)
  let r = createProgress(undefined, 'pc_music', 40, 30)
  assert.equal(r.progress, 0); assert.equal(r.sat, 0)
  r = createProgress(r.base, 'pc_music', 55, 30)
  assert.equal(r.sat, 15); assert.equal(r.progress, 0.5)
  r = createProgress(r.base, 'pc_music', 80, 30)
  assert.equal(r.progress, 1)
  r = createProgress(r.base, 'pc', 80, 60)
  assert.equal(r.sat, 0)
  r = createProgress(r.base, 'pc', 2, 60)   // 04:00 重置
  assert.equal(r.base.base, 2)
  assert.equal(createProgress(undefined, 'x', null, 30).progress, null)
})

test('三期：最新 CD 标题 + 歌词去段标', () => {
  const inv = [{ type: 'key', meta: {} }, { type: 'cd', meta: { title: '楼下有水声', text: '[Verse 1]\n新家的钥匙还有点凉\n\n窗外有风' } }, { type: 'cd', meta: { title: '慢慢变成家', text: '[Verse]\n搬进来的第一周' } }, { type: 'script', meta: { title: '稿' } }]
  assert.deepEqual(latestWork(inv, 'song'), { title: '慢慢变成家', lines: ['搬进来的第一周'] })
  assert.equal(latestWork(inv, 'script')?.title, '稿')
  assert.equal(latestWork(null, 'song'), null)
})

test('三期：今天的她只列非零项', () => {
  const rows = todaySummaryRows({ daily_use: { pc_music: { used_min: 64.6 }, compose: { used_count: 2 }, phone: { used_min: 3.5 }, pc: { used_min: 0 } }, fishing: { casts_today: 3, recent_casts: [{ result: 'fish', fish: { name: '鲫鱼' } }, { result: 'junk' }] }, today_sales: { count: 0 } }, ['阿蝉', '小克'], ['🎵 写完了'])
  assert.deepEqual(rows.map(r => r.label), ['写歌', '看手机', '钓鱼', '聊过', ''])
  assert.equal(rows[0].value, '65 分钟 · 写好 2 首')
  assert.equal(rows[2].value, '3 竿 · 钓到 鲫鱼')
  assert.deepEqual(todaySummaryRows(null, [], []), [])
})

test('三期：answer → 上课事件；compose → 写完新歌', () => {
  const n = (id: string) => (id === 'w' ? '鲸仔' : id)
  assert.equal(fromLegacy('action', { entity: 'w', action: 'answer', success: true }, n, 1)?.category, 'school')
  assert.equal(fromLegacy('produce', { entity: 'w', via: 'compose', item: 'cd' }, n, 1)?.text, '鲸仔 写完了一首新歌')
})
