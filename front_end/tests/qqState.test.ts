// 跟随看他的 QQ：隔离面板与全局 store 共用的纯 reducer
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { qqSetContacts, qqMerge, qqReplaceThread, type QQState } from '../src/game/qqState'

const empty: QQState = { contacts: [], messages: [], available: null }
const msg = (id: string, ts: string, from: string, to: string) => ({ id, ts, from, to, kind: 'text', text: id }) as unknown as QQState['messages'][number]

test('qqSetContacts：null = 未开通且保留旧联系人', () => {
  const s = qqSetContacts(empty, [{ id: 'whale', name: '鲸仔', group: false, unread: 2 }])
  assert.equal(s.available, true)
  const t = qqSetContacts(s, null)
  assert.equal(t.available, false)
  assert.equal(t.contacts.length, 1)
})

test('qqMerge 去重排序；qqReplaceThread 只替换该会话', () => {
  let s = qqMerge(empty, [msg('b', '2026-11-19T10:02', 'whale', 'achan'), msg('a', '2026-11-19T10:01', 'achan', 'whale'), msg('c', '2026-11-19T10:03', 'claudine', 'achan')])
  assert.deepEqual(s.messages.map(m => m.id), ['a', 'b', 'c'])
  s = qqReplaceThread(s, m => m.from === 'whale' || m.to === 'whale', [msg('d', '2026-11-19T10:04', 'whale', 'achan')])
  assert.deepEqual(s.messages.map(m => m.id), ['c', 'd'])
  assert.equal(qqMerge(s, []), s)
})
