// 单测：上课系统 v1 前端展示纯函数（B world-v1.4.0 §12.25）
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { dueText, noteRows, cdSheetRows, receiptRows, hasItemDetail, homeworkUseText } from '../src/game/school'

test('dueText：取字面日期算周几，不做时区换算', () => {
  assert.equal(dueText('2026-11-27T10:45:00+08:00'), '周五 10:45')
  assert.equal(dueText(null), '')
})

test('noteRows：睡着 / 没来段给灰字占位', () => {
  const rows = noteRows({ segments: [{ i: 1, text: '战斗音乐要有推进感', status: 'heard' }, { i: 2, text: null, status: 'slept' }, { i: 3, text: null, status: 'absent' }] })
  assert.deepEqual(rows.map(r => [r.i, r.muted]), [[1, false], [2, true], [3, true]])
  assert.equal(rows[1].text, '……（这段睡着了）')
  assert.equal(rows[2].text, '（没来）')
  assert.deepEqual(noteRows(undefined), [])
})

test('cdSheetRows：按定稿顺序、缺字段不显示、歌词算长文', () => {
  const rows = cdSheetRows({ title: '决战', status: 'final', genre: '游戏 BGM', mood: '', chords: ['Am', 'F', 'G'], lyrics: '第一行\n第二行', homework_week: 1 })
  assert.deepEqual(rows.map(r => r.key), ['status', 'homework_week', 'genre', 'chords', 'lyrics'])
  assert.equal(rows.find(r => r.key === 'chords')!.value, 'Am – F – G')
  assert.equal(rows.find(r => r.key === 'homework_week')!.value, '第 1 周作业')
  assert.equal(rows.find(r => r.key === 'lyrics')!.long, true)
  assert.equal(rows.find(r => r.key === 'status')!.value, '定稿')
})

test('receiptRows：迟交标红、音频中文', () => {
  const rows = receiptRows({ receipt_id: 'hw-1', week: 1, title: '决战', late: true, audio: 'pending', due: '2026-11-27T10:45:00+08:00' })
  assert.equal(rows.find(r => r.label === '提交')!.warn, true)
  assert.equal(rows.find(r => r.label === '音频')!.value, '音频待生成')
  assert.equal(rows.find(r => r.label === '截止')!.value, '周五 10:45')
})

test('hasItemDetail：只有带 meta 的笔记 / 回执 / CD', () => {
  assert.equal(hasItemDetail({ type: 'class_notes', meta: {} }), true)
  assert.equal(hasItemDetail({ type: 'cd' }), false)
  assert.equal(hasItemDetail({ type: 'bread', meta: {} }), false)
})

test('homeworkUseText：成功补截止与音频；失败按 reason 翻译、后端 message 优先', () => {
  assert.equal(homeworkUseText({ success: true, result: { message: '《决战》交上了。回执 hw-1。', due: '2026-11-27T10:45:00+08:00', audio: 'none', updated: false } }), '📮 《决战》交上了。回执 hw-1。（截止 周五 10:45 · 无音频）')
  assert.equal(homeworkUseText({ success: false, reason: 'no_item', result: { objectId: 'homework_box' } }), '📮 背包里没有可以交的 CD')
  assert.equal(homeworkUseText({ success: false, reason: 'cd_redo', result: { message: '这首判了重做，交重做后的那张。' } }), '📮 这首判了重做，交重做后的那张。')
  assert.match(homeworkUseText({ success: false, reason: 'already_submitted', result: { week: 1 } }), /第 1 周/)
})
