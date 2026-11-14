import { test } from 'node:test'
import assert from 'node:assert/strict'
import { godotHash, pickSemantic, mask8, blobPick, lookupIndex, objectEntry, objectImage, planMap } from '../src/game/godotMap'
import type { Tile, GameObject } from '../src/types'

const rules = {
  arena_override: { street: 'road', lane: 'road', square: 'square', campus: 'campus', dock: 'dock', park: { base: 'grass_park', sprinkle: 'grass_flower', sprinkle_pct: 10 } },
  by_type: {
    water: 'water',
    wall: { top: 'wall_top', face: 'wall_face', style_by_arena_regex: { '^classroom$|grocery_shop': 'white' }, style_default: 'wainscot' },
    grass1: 'grass_dark', grass: { base: 'grass', sprinkle: 'grass_flower', sprinkle_pct: 6 },
    floor: { by_arena_regex: { kitchen: 'floor_kitchen', '^dining$': 'floor_tile_cafe' }, default: 'floor_wood' },
    object: 'floor', floor_occupied: 'floor', _default: { by_arena_regex: {}, default: 'grass' },
  },
  structures: { door: 'door', door_open: 'door_open', stairs: 'stairs', gate: null },
}
const T = (x: number, y: number, type: string, sector = 'outside', arena: string | null = null): Tile => ({ x, y, type, walkable: true, objectId: null, sector, arena } as unknown as Tile)

test('godotHash 与 AssetLib._hash 同值（64 位异或）', () => {
  // Godot: (3*73856093) ^ (30*19349663) ^ (7*83492791) = 221568279 ^ 580489890 ^ 584449537 → abs % 1000003
  assert.equal(godotHash(3, 30, 7), Number((BigInt(3 * 73856093) ^ BigInt(30 * 19349663) ^ BigInt(7 * 83492791)) % 1000003n))
  assert.equal(godotHash(45, 40, 13), Number((BigInt(45 * 73856093) ^ BigInt(40 * 19349663) ^ BigInt(13 * 83492791)) % 1000003n))
})

test('pickSemantic：区域优先、墙按下方格分 face/top 带风格、室外 object 格为草', () => {
  assert.equal(pickSemantic(rules, T(1, 1, 'grass', 'outside', 'street'), undefined), 'road')
  assert.equal(pickSemantic(rules, T(1, 1, 'object'), undefined), 'grass')
  assert.equal(pickSemantic(rules, T(1, 1, 'wall', 'home', 'kitchen'), T(1, 2, 'floor', 'home', 'kitchen')), 'wall_face_wainscot')
  assert.equal(pickSemantic(rules, T(1, 1, 'wall', 'university', 'classroom'), T(1, 2, 'wall', 'university', 'classroom')), 'wall_top_white')
  assert.equal(pickSemantic(rules, T(1, 1, 'floor', 'home', 'kitchen'), undefined), 'floor_kitchen')
  assert.equal(pickSemantic(rules, T(1, 1, 'floor', 'home', 'whale_room'), undefined), 'floor_wood')
  assert.equal(pickSemantic(rules, T(1, 1, 'grass1'), undefined), 'grass_dark')
})

test('mask8 角位需两侧边；blobPick 逐步抹角再退全同类', () => {
  const sem = new Map<string, string>()
  for (let x = 0; x < 3; x++) for (let y = 0; y < 3; y++) sem.set(`${x},${y}`, 'road')
  sem.set('1,0', 'grass')   // 上方不是路 → 上=0，右上/左上角也清零
  assert.equal(mask8(sem, 1, 1, ['road']), '00111110')
  assert.deepEqual(blobPick({ '00111110': ['a'], '11111111': ['full'] }, '00111110'), ['a'])
  assert.deepEqual(blobPick({ '01111111': ['x'], '11111111': ['full'] }, '11111111'), ['full'])
  assert.deepEqual(blobPick({ '00101010': ['edge'] }, '00111010'), ['edge'])
})

test('lookupIndex 变体按哈希；objectEntry 别名 / 去后缀；planMap 门楼梯画在 b', () => {
  const meta = { image: 'x.png', tile: 48, columns: 16, index: { g0: 0, g1: 1, door: 5, stairs: 6, road_0: 7 }, variants: { grass: ['g0', 'g1'] }, base: {}, autotile: [], overlay: {}, object_overlays: [] }
  const i = lookupIndex(meta, 'grass', 2, 3); assert.ok(i === 0 || i === 1)
  assert.equal(lookupIndex(meta, 'nope', 0, 0), -1)
  const om = { tile_px: 96, items: { pc: { image: 'gen/pc.png', footprint: [1, 1] as [number, number], px_per_tile: 48 }, tree: { image: 'fantasy/tree.png', variants: ['fantasy/tree.png', 'fantasy/tree_1.png'] } }, alias: { pc_desk: 'pc', game_console: 'pc' } }
  assert.equal(objectEntry(om, 'pc_desk')?.key, 'pc')
  assert.equal(objectEntry(om, 'pc_2')?.key, 'pc')
  assert.equal(objectEntry(om, 'sofa'), null)
  assert.ok(['fantasy/tree.png', 'fantasy/tree_1.png'].includes(objectImage(objectEntry(om, 'tree')!, 4, 5)))
  const tiles = [T(0, 0, 'grass'), T(0, 1, 'grass', 'outside', 'street'), T(0, 2, 'floor', 'home', 'living_room')]
  const plan = planMap(tiles, [] as GameObject[], [{ id: 'd1', kind: 'door', a: { x: 0, y: 1 }, b: { x: 0, y: 2 } }, { id: 's', kind: 'stairs', a: { x: 0, y: 2 }, b: { x: 0, y: 0 } }], rules, meta, null)
  assert.equal(plan.ground.length, 3)
  assert.deepEqual(plan.structures.map(c => [c.x, c.y, c.idx]), [[0, 2, 5], [0, 0, 6]])
  assert.deepEqual(plan.doors.get('d1'), { x: 0, y: 2 })
})
