import type { Position, Tile } from '../types'
import type { MapEdge, MapV2 } from './map/mapv2'

export interface StairsHop { target: Position; here: Position; toFloor: number; fromFloor: number }

/**
 * 当前所在楼的楼梯：找一条 stairs 边，其一端与「我」同 sector 同楼层，返回另一端（目标格）。
 * 客户端四邻 BFS 跨不了层，换层一律把另一端当 targetTile 交给后端 `move`（后端 BFS 带楼梯边）。
 */
export function stairsHop(v2: Pick<MapV2, 'edges' | 'floorOf'>, tiles: Tile[], me: Position): StairsHop | null {
  const at = (p: Position) => tiles.find(t => t.x === p.x && t.y === p.y)
  const myTile = at(me)
  if (!myTile) return null
  const myFloor = v2.floorOf(myTile)
  let best: StairsHop | null = null
  for (const e of v2.edges as MapEdge[]) {
    if (e.type !== 'stairs' || e.tiles.length < 2) continue
    for (let i = 0; i < e.tiles.length; i++) {
      const a = e.tiles[i], ta = at(a)
      if (!ta || ta.sector !== myTile.sector || v2.floorOf(ta) !== myFloor) continue
      const b = e.tiles.find((_, j) => j !== i && at(e.tiles[j]) && v2.floorOf(at(e.tiles[j])) !== myFloor)
      if (!b) continue
      const hop = { target: b, here: a, toFloor: v2.floorOf(at(b)), fromFloor: myFloor }
      const d = Math.abs(a.x - me.x) + Math.abs(a.y - me.y)
      if (!best || d < Math.abs(best.here.x - me.x) + Math.abs(best.here.y - me.y)) best = hop
    }
  }
  return best
}
