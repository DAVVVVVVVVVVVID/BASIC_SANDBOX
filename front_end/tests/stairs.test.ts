import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import { parseMapV2 } from '../src/game/map/mapv2'
import { stairsHop } from '../src/game/stairs'
import type { Tile } from '../src/types'

const tile = (x: number, y: number, arena: string): Tile => ({ x, y, type: 'floor', walkable: true, objectId: null, sector: 'home', arena } as unknown as Tile)
const tiles = [tile(10, 16, 'living_room'), tile(9, 17, 'living_room'), tile(3, 30, 'achan_room'), tile(4, 30, 'achan_room'), { ...tile(20, 8, 'street'), sector: 'outside' }]
const world = { tiles, map: { floors: { achan_room: 2 }, edges: [
  { id: 'door_home', kind: 'door', a: { arena: 'lane', x: 9, y: 18 }, b: { arena: 'living_room', x: 9, y: 17 } },
  { id: 'stairs_home', kind: 'stairs', a: { arena: 'living_room', x: 10, y: 16 }, b: { arena: 'achan_room', x: 3, y: 30 } },
] } }

describe('stairsHop', () => {
  const v2 = parseMapV2(world as unknown as Parameters<typeof parseMapV2>[0])
  it('2F 房间 → 目标是 1F 楼梯格', () => {
    assert.deepEqual(stairsHop(v2, tiles, { x: 4, y: 30 }), { target: { x: 10, y: 16 }, here: { x: 3, y: 30 }, toFloor: 1, fromFloor: 2 })
  })
  it('1F 客厅 → 目标是 2F 楼梯格', () => {
    assert.deepEqual(stairsHop(v2, tiles, { x: 9, y: 17 }), { target: { x: 3, y: 30 }, here: { x: 10, y: 16 }, toFloor: 2, fromFloor: 1 })
  })
  it('户外没有楼梯', () => {
    assert.equal(stairsHop(v2, tiles, { x: 20, y: 8 }), null)
  })
})
