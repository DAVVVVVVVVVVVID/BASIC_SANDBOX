// 回归：跟随「他今日的对话」——room_id 为 null 的邀请事件不能让分组抛错（总控 11-18 黑屏根因）
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { groupFollowRooms } from '../src/game/followChat'

const rows = [
  { kind: 'event', event: 'room_open', ts: '2026-11-17T13:00:00', room_id: 'room_abcdef123', participants: ['a', 'b'] },
  { kind: 'message', ts: '2026-11-17T13:01:00', room_id: 'room_abcdef123', from: 'a', text: '你好' },
  { kind: 'event', event: 'request_expired', ts: '2026-11-17T14:04:18.187', room_id: null, request_id: '74dc9c0363de', participants: ['餐厅老板_89ad63', '杂货店老板_03807e'] },
  { kind: 'event', event: 'request_rejected', ts: '2026-11-17T18:58:07.916', room_id: null, participants: ['餐厅老板_89ad63', '鲸仔_52f531'] },
  { kind: 'event', event: 'room_close', ts: null, room_id: 'room_abcdef123' },
]

test('room_id 为 null 的邀请事件单列「邀请未成」，不进房间分组、不抛错', () => {
  const { rooms, invites } = groupFollowRooms(rows, null)
  assert.equal(rooms.length, 1)
  assert.equal(rooms[0].room, 'room_abcdef123')
  assert.equal(rooms[0].rs.length, 3)
  assert.deepEqual(invites.map(v => v.label), ['邀请被拒', '邀请过期'])
  assert.deepEqual(invites[1].participants, ['餐厅老板_89ad63', '杂货店老板_03807e'])
})

test('只有 null 房间的行 / ts 缺失也不抛错', () => {
  assert.doesNotThrow(() => groupFollowRooms([{ kind: 'event', event: 'request_expired', room_id: null }, { kind: 'message', room_id: null, text: 'x' }], 'r1'))
  const { rooms, invites } = groupFollowRooms([{ kind: 'event', event: 'request_expired', room_id: null }], null)
  assert.equal(rooms.length, 0)
  assert.equal(invites[0].ts, '')
})

test('进行中房间置顶', () => {
  const { rooms } = groupFollowRooms([...rows, { kind: 'message', ts: '2026-11-17T09:00:00', room_id: 'room_live', from: 'a', text: 'hi' }], 'room_live')
  assert.equal(rooms[0].room, 'room_live')
  assert.equal(rooms[0].active, true)
})
