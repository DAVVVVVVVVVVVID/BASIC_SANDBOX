import test from 'node:test'
import assert from 'node:assert/strict'
import { mapBuildings, buildingRoofKey } from '../src/game/map/mapv2'

test('mapBuildings 宽容解析 v1.2 buildings[]，坏项跳过', () => {
  const map = { buildings: [
    { id: 'classroom', sector: 'university', floor: 1, footprint: { x: 3, y: 1, w: 7, h: 5 }, doors: [{ door_id: 'door_classroom', cell: { x: 5, y: 5 }, kind: 'door' }] },
    { id: 'home_2f', sector: 'home', floor: 2, footprint: { x: 2, y: 29, w: 6, h: 5 }, doors: [{ door_id: 'stairs_home', cell: { x: 3, y: 30 }, kind: 'stairs' }] },
    { id: 'bad' }, null, { id: 'nodoors', sector: 'grocery', footprint: { x: 22, y: 20, w: 8, h: 5 } },
  ] }
  const bs = mapBuildings(map)
  assert.equal(bs.length, 3)
  assert.equal(buildingRoofKey(bs[0]), 'classroom|1')
  assert.equal(buildingRoofKey(bs[1]), 'home|2')
  assert.equal(buildingRoofKey(bs[2]), 'grocery|1')
  assert.deepEqual(bs[2].doors, [])
  assert.deepEqual(mapBuildings(undefined), []); assert.deepEqual(mapBuildings({}), []); assert.deepEqual(mapBuildings({ buildings: 'x' }), [])
})
