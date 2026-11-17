import { useMemo } from 'react'
import { useGameStore } from '../../store/gameStore'
import { EventBus } from '../../game/EventBus'
import { deriveStateLabel } from '../../game/stateLabel'
import { zoneLabel } from '../../game/map/zones'
import { godotCharKeyFor } from '../../game/godotChars'
import { C, avatarUrl, pillColor, kit } from './theme'
import { displayName } from './PlayerChip'

/** 「镇上的人」（mockC2）：六人两列——28px 头像 · 名字 · 区域 · 状态药丸 · 距离 · 👁 跟随；含阿蝉自己（高亮） */
export default function PeoplePanel({ follow, cols }: { follow: string | null; cols?: 1 | 2 }) {
  const me = useGameStore((s) => s.player)
  const identity = useGameStore((s) => s.identity)
  const players = useGameStore((s) => s.players)
  const objects = useGameStore((s) => s.objects)
  const tiles = useGameStore((s) => s.tiles)
  const tileAt = useMemo(() => new Map(tiles.map(t => [`${t.x},${t.y}`, t] as const)), [tiles])
  if (!me) return null
  type Row = { id: string; key: string; name: string; zone: string; doing: string; dist: number; online: boolean; self: boolean; thought: string; lesson: string }
  const rows: Row[] = players.filter(p => p.id !== me.id).map(p => {
    const t = tileAt.get(`${p.position.x},${p.position.y}`)
    const th = p.last_thought?.text?.trim() ?? ''
    return { id: p.id, key: godotCharKeyFor(p.name, p.controller, p.agent_id), name: p.name, zone: zoneLabel(t) || (t ? '小镇' : '—'), doing: (deriveStateLabel(p, objects) ?? (p.state === 'walking' ? '🚶 走路' : '站着')).replace(/^[^一-龥A-Za-z]+/, ''), dist: Math.abs(p.position.x - me.position.x) + Math.abs(p.position.y - me.position.y), online: p.online !== false, self: false, thought: th, lesson: p.lesson ? (p.lesson.dozing ? '💤 打瞌睡' : `📖 ${p.lesson.title || '上课中'}`) : '' }
  })
  const myTile = tileAt.get(`${me.position.x},${me.position.y}`)
  rows.push({ id: me.id, key: godotCharKeyFor(me.profile?.name ?? me.id, 'human', identity ?? me.agent_id ?? null), name: displayName(me.profile?.name ?? me.id, identity), zone: zoneLabel(myTile) || (myTile ? '小镇' : '—'), doing: me.state === 'walking' ? '走路' : (me.stateLabel ?? me.state ?? '').replace(/^[^一-龥A-Za-z]+/, '') || '站着', dist: 0, online: true, self: true, thought: '', lesson: '' })
  const go = (r: Row) => EventBus.emit('director-cmd', r.self ? { cmd: 'self' } : { cmd: 'follow', id: r.id })
  const STATE_ZH: Record<string, string> = { idle: '站着', walking: '走路', using: '使用中', talking: '聊天中', sleeping: '睡觉中' }
  return (
    <div style={{ display: 'grid', gridTemplateColumns: cols === 1 ? '1fr' : 'repeat(auto-fit, minmax(min(300px, 100%), 1fr))', gap: 8, minWidth: 0 }}>
      {rows.map(r => {
        const doing = STATE_ZH[r.doing] ?? r.doing
        const pc = pillColor(r.online ? doing : '离线')
        const following = r.self ? follow === null : follow === r.id
        return (
          <div key={r.id} data-testid={`people-${r.id}`} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px', borderRadius: 8, minWidth: 0, background: r.self ? '#FFF1CF' : 'rgba(255,255,255,0.55)', border: `1px solid ${r.self ? C.amber : '#E6DCCB'}`, opacity: r.online ? 1 : 0.6 }}>
            <img className="px" src={avatarUrl(r.key, 80)} width={36} height={36} alt="" style={{ borderRadius: 6, border: `1px solid ${C.sky}`, background: '#fff', flexShrink: 0 }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                <b style={{ fontSize: 15, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.name}</b>
                <span style={{ fontSize: 11, padding: '1px 7px', borderRadius: 9, background: pc.bg, color: pc.fg, whiteSpace: 'nowrap', flexShrink: 0 }}>{r.online ? doing : '离线'}</span>
              </div>
              <div style={{ fontSize: 12, color: C.inkSoft, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={r.zone}>{r.zone}</div>
              {r.lesson && <div data-testid={`people-lesson-${r.id}`} style={{ fontSize: 11, color: r.lesson.startsWith('💤') ? '#7E62C9' : '#1F7A6F', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={r.lesson}>{r.lesson}</div>}
              {r.thought && <div style={{ fontSize: 11, color: '#7E62C9', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={r.thought}>💭 {r.thought}</div>}
            </div>
            <div style={{ width: 52, flexShrink: 0, textAlign: 'center' }}>
              <button className={`sq${following ? ' active' : ''}`} onClick={() => go(r)} title={r.self ? '镜头回到阿蝉' : '镜头跟随'} data-testid={`eye-${r.id}`} style={{ width: 44, height: 38, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}><img className="mi" src={kit('mi_eye')} alt="👁" /></button>
              <div style={{ fontSize: 11, color: C.inkSoft, marginTop: 2, whiteSpace: 'nowrap' }}>{r.self ? '我' : `${r.dist} 格`}</div>
            </div>
          </div>
        )
      })}
      {rows.length <= 1 && <div style={{ color: C.inkSoft, padding: 8 }}>镇上没有别人</div>}
    </div>
  )
}
