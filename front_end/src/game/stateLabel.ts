/**
 * 别人头顶的状态标签与睡 / 坐姿贴靠位置（纯函数，不依赖 Phaser；单测 `tests/stateLabel.test.ts`）。
 * 总控 11-08「鲸仔边睡觉边行动」：state=walking 时标签与姿势一律按走路，忽略 sleeping / eating / sitting 的 tagsHint 与 objects.userList 兜底；
 * tagsHint（来自更慢的 /state 轮询）只在 state 为 using / idle 时参与；userList 反查只在 using（或老后端没有 state）时信。
 */
import type { GameObject, OtherPlayer, Position } from '../types'
import type { PoseAnchor, PoseAnchors } from './objects/ActorSprite'
import { TILE_SIZE } from './constants'

const USE_ICONS: [RegExp, string][] = [
  [/bed|sofa_bed/i, '💤 睡觉中'],
  [/cook|stove|fridge|kitchen|table|eat/i, '🍴 吃饭中'],
  [/bath|shower/i, '🛁 洗澡中'],
  [/toilet/i, '🚻'],
  [/sink/i, '🚰 洗漱中'],
  [/desk|book|study|computer|phone/i, '📖 专注中'],
  [/stream/i, '📺 直播中'],
  [/sofa|chair|bench/i, '🛋 休息中'],
  [/well/i, '🪣 打水中'],
]

const LABEL_ICON: [RegExp, string][] = [
  [/睡|sleep/i, '💤'], [/吃|饭|eat|food/i, '🍴'], [/直播|stream/i, '📺'], [/聊|talk|chat/i, '💬'], [/洗|bath|shower/i, '🛁'],
  [/钓|fish/i, '🎣'], [/看书|读|read|book/i, '📖'], [/手机|phone|刷/i, '📱'], [/休息|坐|rest|sit/i, '🛋'], [/工作|desk|work|写/i, '🖥'],
]

/** W8：睡觉 / 坐下时要贴到哪件物品上——优先 usingObjectId，其次 objects[].userList 反查，最后找相邻的床 / 座位。
 *  睡：床 / 沙发中心，竖床 0°、横床 -90°（表里的睡觉帧是竖躺头朝上）。
 *  坐（主播 11-07「椅子添加使用者站位」）：桌类（电脑桌 / 课桌 / 阅览桌 / 钢琴 / 长桌）椅子画在图的下沿 → 坐到 footprint 底格偏下、面朝上；
 *  吧台：底沿凳子、面朝上；长椅 / 沙发：坐在人所在列、面朝下；餐桌：两端椅子，坐离人近的一端、面朝桌子；钓位：原地面朝下。
 *  深度 = 物品底边 + 1（画在物品之上）。这是纯视觉摆放，格子与合法性仍以后端为准。 */
const T = TILE_SIZE
const WALKING = (st: string | undefined) => st === 'walking' || st === 'walking_over'
export function poseAnchorsFor(p: { id: string; position: Position; usingObjectId?: string | null; state?: string }, objects: GameObject[]): PoseAnchors {
  // 总控 11-08：「边睡觉边行动」——她起床走开后 objects 里床的 userList 可能滞后几秒仍含她，睡姿就跟着精灵滑过地图。走路中一律不贴；userList 反查只在 state=using 时信
  if (WALKING(p.state)) return { sleep: null, sit: null }
  const tilesOf = (o: GameObject) => (o.tiles && o.tiles.length ? o.tiles : [o.position])
  const isBed = (o: GameObject) => /bed|sofa/i.test(o.type)
  const isSeat = (o: GameObject) => /desk|pc|piano|bar|bench|sofa|table|fishing_spot|game_console|stream/i.test(o.type)
  const near = (o: GameObject) => tilesOf(o).some(t => Math.abs(t.x - p.position.x) + Math.abs(t.y - p.position.y) <= 1)
  const used = (p.usingObjectId ? objects.find(o => o.id === p.usingObjectId) : undefined) ?? (p.state === 'using' || p.state === undefined ? objects.find(o => o.userList?.includes(p.id)) : undefined)
  const bed = used && isBed(used) ? used : objects.filter(isBed).find(near)
  const seat = used && isSeat(used) ? used : objects.filter(isSeat).find(near)
  const box = (o: GameObject) => { const ts = tilesOf(o); return { x0: Math.min(...ts.map(t => t.x)), x1: Math.max(...ts.map(t => t.x)), y0: Math.min(...ts.map(t => t.y)), y1: Math.max(...ts.map(t => t.y)) } }
  let sleep: PoseAnchor | null = null, sit: PoseAnchor | null = null
  if (bed) {
    const b = box(bed)
    sleep = { x: (b.x0 + b.x1 + 1) / 2 * T, y: (b.y0 + b.y1 + 1) / 2 * T, angle: (b.x1 - b.x0) > (b.y1 - b.y0) ? -90 : 0, depth: (b.y1 + 1) * T + 1 }
  }
  // B W10 ②：物品带 usePos（绝对格）时后端 use 已把人挪到座位格并转向 → 坐姿不再前端猜位置；床仍贴到床中心（1×2 的床只给一格，画在中心更像躺在床上）
  const serverPlaced = (o: GameObject) => Array.isArray(o.usePos) && o.usePos.length > 0
  if (seat && serverPlaced(seat)) {
    sit = null
  } else if (seat) {
    const b = box(seat), ty = seat.type
    const col = Math.min(Math.max(p.position.x, b.x0), b.x1)
    const depth = (b.y1 + 1) * T + 1
    if (/bench|sofa/i.test(ty)) sit = { x: (col + 0.5) * T, y: (b.y0 + 0.55) * T, angle: 0, facing: 'down', depth }
    else if (/restaurant_table|table/i.test(ty)) {
      const left = p.position.x <= b.x0
      sit = { x: (left ? b.x0 + 0.15 : b.x1 + 0.85) * T, y: (b.y0 + 0.5) * T, angle: 0, facing: left ? 'right' : 'left', depth }
    } else if (/bar/i.test(ty)) sit = { x: (col + 0.5) * T, y: (b.y1 + 0.9) * T, angle: 0, facing: 'up', depth }
    else if (/fishing_spot/i.test(ty)) sit = { x: (b.x0 + 0.5) * T, y: (b.y0 + 0.6) * T, angle: 0, depth }
    else sit = { x: ((b.x0 + b.x1 + 1) / 2) * T, y: (b.y1 + 0.95) * T, angle: 0, facing: 'up', depth }   // 桌类：椅子在下沿
  }
  return { sleep, sit }
}

/** 后端给的 stateLabel（W5 起 players[] 自带）前面配一个图标 */
export function iconize(label: string): string {
  if (/^\p{Extended_Pictographic}/u.test(label)) return label
  for (const [re, ic] of LABEL_ICON) if (re.test(label)) return `${ic} ${label}`
  return label
}

/** 别人正在干什么：优先后端 `stateLabel` / `tags`（W5），老后端退回 objects.userList 反查推断 */
export function deriveStateLabel(p: OtherPlayer, objects: GameObject[], tagsHint?: string[]): string | null {
  if (p.online === false) return '💤 离线'
  // 总控 11-08：state=walking 时标签一律按走路——/state 轮询来的 tagsHint 与 objects.userList 都比 players 慢，起床走开后会滞后几秒仍显示「💤 睡觉中」
  if (WALKING(p.state)) return p.state === 'walking_over' ? '💬 走过去聊' : null
  const hint = p.state === 'using' || p.state === 'idle' ? (tagsHint ?? []) : []
  const tags = hint.concat(p.tags ?? [])
  if (tags.includes('sleeping')) return '💤 睡觉中'
  if (tags.includes('eating'))   return '🍴 吃饭中'
  if (tags.includes('streaming')) return '📺 直播中'
  if (tags.includes('reading') || tags.includes('phone')) return '📱 看手机'
  if (tags.includes('browsing')) return '📱 刷手机'   // v1.1：手机持续使用
  if (tags.includes('cooking')) return '🍳 做饭中'
  if (tags.includes('working')) return '🖥 工作中'   // W9：读 QQ 消息（B 占 1 游戏分钟打 reading 标签）
  if (p.stateLabel) return iconize(p.stateLabel)
  if (p.state === 'talking') return '💬 聊天中'
  const obj = p.state === 'using' || !p.state ? objects.find(o => o.userList?.includes(p.id)) : undefined   // userList 反查只在 using（或老后端没有 state）时信
  if (obj) {
    const tags = hint.concat(obj.effects?.filter(e => e.type === 'tag').map(e => e.key) ?? [])
    if (tags.includes('sleeping')) return '💤 睡觉中'
    if (tags.includes('eating'))   return '🍴 吃饭中'
    if (tags.includes('streaming')) return '📺 直播中'
    const key = `${obj.type} ${obj.name} ${obj.sprite ?? ''}`
    for (const [re, label] of USE_ICONS) if (re.test(key)) return label
    return `🔧 ${obj.name}`
  }
  switch (p.state) {
    case 'talking':         return '💬 聊天中'
    case 'requesting_talk': return '💬 想找人聊'
    case 'walking_over':    return '💬 走过去聊'
    case 'using':           return '🔧 使用中'
    default:                return null
  }
}
