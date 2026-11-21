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
  assert.equal(deriveGameView({ status: 'running', paused: false, blocked: 'live_mode=闲聊' }).statusNote, '卡住了')
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
