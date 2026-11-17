import { useMemo } from 'react'
import { useGameStore } from '../../store/gameStore'
import { EventBus } from '../../game/EventBus'
import { normalizeInventory } from '../../game/items'
import { C } from './theme'

/**
 * 物件交互提示条（上课系统 v1：作业提交箱；任何带 `/world.objects[].hint` 的物件通用）。
 * 自己站在物件旁一格时显示后端给的 hint +「使用」按钮（等同按 E；手机没有键盘）；提交箱旁背包里有多张 CD 时每张一个「交《曲名》」（use 带 request_id）。
 * 前端只发 use、展示回包；能不能交、迟不迟交都以后端为准。只在操控页自己视角（非跟随）显示。
 */
const DIR: Record<string, [number, number]> = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] }

export default function ObjectHint({ compact = false }: { compact?: boolean }) {
  const player = useGameStore((s) => s.player)
  const objects = useGameStore((s) => s.objects)
  const inv = useMemo(() => normalizeInventory(player?.inventory), [player?.inventory])
  if (!player) return null
  const { x, y } = player.position
  const tilesOf = (o: { position: { x: number; y: number }; tiles?: { x: number; y: number }[] }) => (o.tiles?.length ? o.tiles : [o.position])
  const obj = objects.find(o => o.hint && tilesOf(o).some(t => Math.abs(t.x - x) + Math.abs(t.y - y) <= 1))
  if (!obj) return null
  const [dx, dy] = DIR[player.facing] ?? [0, 0]
  const facing = tilesOf(obj).some(t => t.x === x + dx && t.y === y + dy)
  const cds = obj.type === 'homework_box' ? inv.filter(i => i.type === 'cd' && i.meta && typeof i.meta.request_id === 'string') : []
  const use = (request_id?: string) => EventBus.emit('do-use', request_id ? { request_id } : undefined)
  return (
    <div data-testid="object-hint" className="toast9" style={{ position: 'relative', left: '50%', transform: 'translateX(-50%)', width: 'max-content', maxWidth: compact ? 'calc(100vw - 24px)' : 420, margin: '6px 0', padding: '4px 12px', color: C.ink, fontSize: compact ? 13 : 14, display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'center' }}>
      <div style={{ textAlign: 'center' }}>{obj.type === 'homework_box' ? '📮' : '💡'} <b>{obj.name}</b>：{obj.hint}{!facing && <span style={{ color: C.inkSoft }}>（先面朝它）</span>}</div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'center' }}>
        {cds.length > 1
          ? cds.map(c => <button key={String(c.meta!.request_id)} className="k teal" data-testid="hint-use-cd" onClick={() => use(String(c.meta!.request_id))} style={{ minHeight: compact ? 40 : 30, fontSize: 13 }}>交《{String(c.meta!.title ?? c.meta!.request_id).slice(0, 10)}》</button>)
          : <button className="k teal" data-testid="hint-use" onClick={() => use()} style={{ minHeight: compact ? 40 : 30, minWidth: 88, fontSize: 13 }}>{obj.type === 'homework_box' ? '交作业' : '使用'}{compact ? '' : '（E）'}</button>}
      </div>
    </div>
  )
}
