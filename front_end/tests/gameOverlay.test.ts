// 直播游戏模式信息层：D 的 /game/state → 显示数据
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { deriveGameView, parseOverlayParams, isGameOverlayRoute } from '../src/gameOverlay/view'

const S = {
  status: 'running', screen: 'id_card', visitor: { name: 'Otto Reyes', apartment: '5D', appearance: '六颗牙' },
  checks: [{ item: '姓名', result: 'match', evidence: 'a' }, { item: '牙齿', result: 'mismatch', evidence: 'b' }, { item: '名单', result: 'unknown', evidence: 'c' }],
  verdict: 'reject', suspicion: 0.93, lead: '我要拒绝他。', votes: { admit: 2, reject: 5 },
  decisions: [{ correct: 1 }, { correct: 0 }, { correct: 1 }, { correct: null }],
}

test('核对清单图标 / 判断 / 投票 / 战绩', () => {
  const v = deriveGameView(S)
  assert.equal(v.live, true)
  assert.deepEqual(v.checks.map(c => c.icon), ['✓', '✗', '？'])
  assert.equal(v.verdict.label, '拒绝')
  assert.equal(v.suspicion, 0.93)
  assert.deepEqual(v.votes, { admit: 2, reject: 5, total: 7 })
  assert.deepEqual(v.score, { correct: 2, wrong: 1 })
  assert.equal(v.summary, null)
})

test('没开局 / 已停 → 不显示；结算画面只给 summary', () => {
  assert.equal(deriveGameView(null).live, false)
  assert.equal(deriveGameView({ status: 'stopped' }).live, false)
  const end = deriveGameView({ status: 'running', screen: 'day_end', summary: '夜班结束，correct 4', checks: [], verdict: 'none', suspicion: 0, votes: { admit: 0, reject: 0 } })
  assert.equal(end.summary, '夜班结束，correct 4')
  assert.equal(end.suspicion, null)
  assert.equal(end.verdict.label, '还在看')
  assert.equal(deriveGameView({ status: 'running', paused: true }).statusNote, '暂停中')
  assert.equal(deriveGameView({ status: 'running', paused: false, blocked: 'game_not_foreground' }).statusNote, '等游戏窗口回来')
  assert.equal(deriveGameView({ status: 'running', paused: true, blocked: 'paused_by_api' }).statusNote, '暂停中')
  assert.equal(deriveGameView({ status: 'running', paused: false, blocked: 'paused_by_api' }).statusNote, '暂停中')
  assert.equal(deriveGameView({ status: 'running', paused: false, blocked: 'bridge_paused' }).statusNote, '暂停中')
  assert.equal(deriveGameView({ status: 'running', paused: false, blocked: 'live_mode=闲聊' }).statusNote, '稍等一下')
  assert.equal(deriveGameView({ status: 'running', paused: false, blocked: 'live_paused_or_achan' }).statusNote, '稍等一下')
  assert.equal(deriveGameView({ status: 'running', paused: false, blocked: 'game_not_found' }).statusNote, '卡住了')
  assert.equal(deriveGameView({ status: 'running', paused: false, blocked: null }).statusNote, null)
})

test('URL 参数：选块 / 布局 / 主题 / 缩放', () => {
  const p = parseOverlayParams('?view=game&blocks=checks,votes,bogus&layout=bar&theme=cream&scale=1.5')
  assert.deepEqual([...p.blocks], ['checks', 'votes'])
  assert.equal(p.layout, 'bar'); assert.equal(p.theme, 'cream'); assert.equal(p.scale, 1.5)
  assert.equal(parseOverlayParams('?view=game').blocks.size, 5)
  assert.equal(isGameOverlayRoute('?view=game'), true)
  assert.equal(isGameOverlayRoute('?town=bench'), false)
})

test('游戏舞台 · 档案风：标题天数 / 访客序号、今天四格战绩、核对行排序', async () => {
  const { stageInfo, stageChecks } = await import('../src/gameOverlay/view')
  const st = { status: 'running', day: 2, visitor_no: 3, today: { admit_right: 4, reject_right: 2, admit_wrong: 0, reject_wrong: 1, unknown: 2 }, anomalies: ['带牙的小嘴'] }
  const i = stageInfo(st)
  assert.deepEqual(i.title, { day: 2, visitor: 3 })
  assert.deepEqual(i.quad, { admitOk: 4, rejectOk: 2, admitBad: 0, rejectBad: 1, pending: 2 })
  assert.equal(i.anomaly, '带牙的小嘴')
  assert.deepEqual(stageInfo({ status: 'running', day: 1, visitor_no: 0 }).title, { day: 1, visitor: null })   // 门口没人：不显示访客序号
  assert.equal(stageInfo({ status: 'idle' }).title, null)                                                       // 没在玩：只显示「今晚当门卫」
  assert.equal(stageInfo(null).quad.pending, 0)
  const rows = stageChecks([{ tone: 'ok', item: 'a', evidence: '' }, { tone: 'unknown', item: 'b', evidence: '' }, { tone: 'bad', item: 'c', evidence: '' }, { tone: 'warn', item: 'd', evidence: '' }], 3)
  assert.deepEqual(rows.map(r => r.item), ['c', 'd', 'b'])
  assert.equal(parseOverlayParams('?view=game&layout=stage').layout, 'stage')
})
