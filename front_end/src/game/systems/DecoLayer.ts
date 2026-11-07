import Phaser from 'phaser'
import { Tile, GameObject } from '../../types'
import { TILE_SIZE } from '../map/TileMap'
import { aiEnabled, getAiManifest, aiDecoKey } from '../aiAssets'

/**
 * W8 装饰层（11-07 主播：小镇没有花花草草 → 第一版随机撒点「太乱」→ 改成有规划的摆放）。规则全部确定性，不随机：
 *   1. 建筑脚下：外墙正下方那一排草地种花（粉 / 黄交替），两端各一丛灌木——像房前花坛；
 *   2. 路边：路灯等距（每 8 格），只放在路的北侧 / 西侧（单侧），不和花坛抢位；
 *   3. 河岸：靠水的草地每 4 格一棵小松树，中间偶尔一块青苔石；
 *   4. 每片草地（连通块 ≥ 24 格）中心一簇 2×2 野花，两个对角各一棵小松树；公园里再沿内缘每 3 格一棵；
 *   其余草地留白。避开物品格、门口及四邻。纯视觉，不改可走性；深度按底边 y 与人物排序。
 */
export default class DecoLayer {
  private nodes: Phaser.GameObjects.Image[] = []

  constructor(scene: Phaser.Scene, tiles: Tile[], objects: GameObject[], doorTiles: { x: number; y: number }[], decor: unknown[] = []) {
    const m = getAiManifest()
    if (!m || !aiEnabled() || !m.deco.length) return
    // B W10 任务 1：地图自带的装饰层 decor[]（两块大草坪的小径 / 池塘 / 晾衣绳 / 树）。形状假设 {type, x, y} 或 {type, tiles:[{x,y}]}；
    // 认得的类型用我们的装饰 / 物品图，pond → 水砖、path → 路砖（叠在地面上），认不出的跳过
    const kk = TILE_SIZE / (m.tile_px || 32)
    const DECOR_SPRITE: Record<string, string> = { tree: 'aiobj_tree', pine: 'aideco_pine', bush: 'aideco_bush', flower: 'aideco_flowers_pink', flowers: 'aideco_flowers_pink', rock: 'aideco_rock', stump: 'aideco_stump', lamp: 'aideco_lamp', fence: 'aideco_fence', signpost: 'aideco_signpost', flowerbed: 'aideco_flowerbed', mailbox: 'aideco_mailbox', barrel: 'aideco_barrel', crate: 'aideco_crate', pot_plant: 'aideco_pot_plant', clothesline: 'aideco_fence', bench: 'aiobj_bench' }
    const decorTaken = new Set<string>()
    for (const d of decor) {
      if (!d || typeof d !== 'object') continue
      const o = d as { type?: string; kind?: string; x?: number; y?: number; tiles?: { x: number; y: number }[]; position?: { x: number; y: number } }
      const type = String(o.type ?? o.kind ?? '').toLowerCase()
      const ts = o.tiles?.length ? o.tiles : (o.position ? [o.position] : typeof o.x === 'number' && typeof o.y === 'number' ? [{ x: o.x, y: o.y }] : [])
      if (!type || !ts.length) continue
      for (const t of ts) decorTaken.add(`${t.x},${t.y}`)
      if (type === 'pond' || type === 'water' || type === 'path' || type === 'road') {
        const tilesMeta = m.tiles; if (!tilesMeta || !scene.textures.exists('aitiles')) continue
        const frames = tilesMeta.variants[type === 'pond' || type === 'water' ? 'water' : 'road'] ?? []
        for (const t of ts) {
          const f = tilesMeta.index[frames[(t.x + t.y) % Math.max(1, frames.length)]]
          if (typeof f !== 'number') continue
          const img = scene.add.image(t.x * TILE_SIZE, t.y * TILE_SIZE, 'aitiles', f).setOrigin(0, 0).setDisplaySize(TILE_SIZE, TILE_SIZE).setDepth(0.3)
          this.nodes.push(img)
        }
        continue
      }
      const key = DECOR_SPRITE[type]
      if (!key || !scene.textures.exists(key)) { console.debug('[decor] unknown type', type); continue }
      const xs = ts.map(t => t.x), ys = ts.map(t => t.y)
      const cx = (Math.min(...xs) + Math.max(...xs) + 1) / 2, by = Math.max(...ys) + 1
      const src = scene.textures.get(key).getSourceImage() as { width: number; height: number }
      const img = scene.add.image(cx * TILE_SIZE, by * TILE_SIZE, key).setOrigin(0.5, 1).setDisplaySize(src.width * kk, src.height * kk).setDepth(by * TILE_SIZE - 2)
      this.nodes.push(img)
    }
    const has = (n: string) => m.deco.includes(n) && scene.textures.exists(aiDecoKey(n))
    const byKey = new Map<string, Tile>()
    for (const t of tiles) byKey.set(`${t.x},${t.y}`, t)
    const at = (x: number, y: number) => byKey.get(`${x},${y}`)
    const blocked = new Set<string>()
    for (const o of objects) for (const t of (o.tiles && o.tiles.length ? o.tiles : [o.position])) blocked.add(`${t.x},${t.y}`)
    for (const k0 of decorTaken) blocked.add(k0)
    for (const d of doorTiles) for (const [dx, dy] of [[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1], [0, 2], [1, 1], [-1, 1]]) blocked.add(`${d.x + dx},${d.y + dy}`)
    const isRoad = (t: Tile | undefined) => !!t && (/street|lane|road/.test(t.arena ?? '') || t.type === 'road')
    const isWater = (t: Tile | undefined) => !!t && t.type === 'water'
    const isBuilding = (t: Tile | undefined) => !!t && (t.type === 'wall' || (!!t.sector && t.sector !== 'outside'))
    const isGrass = (t: Tile | undefined): t is Tile => !!t && (t.type === 'grass' || t.type === 'grass1') && (!t.sector || t.sector === 'outside') && !/street|lane|road|square|campus|dock/.test(t.arena ?? '')
    const taken = new Set<string>()
    const k = TILE_SIZE / (m.tile_px || 32)
    const place = (x: number, y: number, name: string) => {
      const key = `${x},${y}`
      if (taken.has(key) || blocked.has(key) || !isGrass(at(x, y)) || !has(name)) return false
      const img = scene.add.image((x + 0.5) * TILE_SIZE, (y + 1) * TILE_SIZE, aiDecoKey(name)).setOrigin(0.5, 1)
      const src = scene.textures.get(aiDecoKey(name)).getSourceImage() as { width: number; height: number }
      img.setDisplaySize(src.width * k, src.height * k).setDepth((y + 1) * TILE_SIZE - 2)
      this.nodes.push(img); taken.add(key)
      return true
    }

    const grass = tiles.filter(isGrass)
    // 1. 建筑脚下花坛：正上方是建筑、本格是草
    for (const t of grass) {
      if (!isBuilding(at(t.x, t.y - 1))) continue
      const leftEnd = !(isGrass(at(t.x - 1, t.y)) && isBuilding(at(t.x - 1, t.y - 1)))
      const rightEnd = !(isGrass(at(t.x + 1, t.y)) && isBuilding(at(t.x + 1, t.y - 1)))
      if (leftEnd || rightEnd) place(t.x, t.y, 'bush')
      else if (t.x % 3 !== 2) place(t.x, t.y, t.x % 2 === 0 ? 'flowers_pink' : 'flowers_yellow')   // 每 3 格留 1 格空，别像一条毛毛虫
    }
    // 2. 路灯：路在南侧 → 每 8 格；路在东侧 → 每 8 格；只取一侧
    for (const t of grass) {
      if (isBuilding(at(t.x, t.y - 1))) continue
      const roadS = isRoad(at(t.x, t.y + 1)), roadE = isRoad(at(t.x + 1, t.y))
      if ((roadS && t.x % 8 === 3) || (roadE && !roadS && t.y % 8 === 3)) place(t.x, t.y, 'lamp')
    }
    // 3. 河岸
    for (const t of grass) {
      if (!isWater(at(t.x + 1, t.y)) && !isWater(at(t.x - 1, t.y))) continue
      if (t.y % 4 === 0) place(t.x, t.y, 'pine')
      else if (t.y % 4 === 2 && t.x % 2 === 0) place(t.x, t.y, 'rock_moss')
    }
    // 4. 草地连通块：中心花簇 + 对角小树；公园内缘每 3 格一棵
    const seen = new Set<string>()
    for (const t of grass) {
      const k0 = `${t.x},${t.y}`
      if (seen.has(k0)) continue
      const comp: Tile[] = []; const stack = [t]; seen.add(k0)
      while (stack.length) {
        const c = stack.pop()!; comp.push(c)
        for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
          const n = at(c.x + dx, c.y + dy); const nk = `${c.x + dx},${c.y + dy}`
          if (isGrass(n) && !seen.has(nk) && (n.arena ?? '') === (t.arena ?? '')) { seen.add(nk); stack.push(n) }
        }
      }
      if (comp.length < 24) continue
      const xs = comp.map(c => c.x), ys = comp.map(c => c.y)
      const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys)
      const cx = Math.floor((x0 + x1) / 2), cy = Math.floor((y0 + y1) / 2)
      const park = (t.arena ?? '') === 'park'
      if (!park) {
        place(cx, cy, 'flowers_pink'); place(cx + 1, cy, 'flowers_yellow'); place(cx, cy + 1, 'flowers_yellow'); place(cx + 1, cy + 1, 'flowers_pink')
        place(x0 + 1, y1 - 1, 'pine'); place(x1 - 1, y0 + 1, 'pine')
      } else {
        for (const c of comp) {
          const edge = !isGrass(at(c.x - 1, c.y)) || !isGrass(at(c.x + 1, c.y)) || !isGrass(at(c.x, c.y - 1)) || !isGrass(at(c.x, c.y + 1))
          if (edge && (c.x + c.y) % 3 === 0) place(c.x, c.y, 'pine')
          else if (edge && (c.x + c.y) % 3 === 1) place(c.x, c.y, c.x % 2 ? 'flowers_pink' : 'flowers_yellow')
        }
        place(cx, cy, 'flowerbed')
      }
    }
  }

  destroy() { for (const n of this.nodes) n.destroy(); this.nodes = [] }
}
