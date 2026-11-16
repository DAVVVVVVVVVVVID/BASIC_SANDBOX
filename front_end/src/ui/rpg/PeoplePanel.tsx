import { useMemo } from 'react'
import { useGameStore } from '../../store/gameStore'
import { EventBus } from '../../game/EventBus'
import { deriveStateLabel } from '../../game/stateLabel'
import { zoneLabel } from '../../game/map/zones'
import { godotCharKeyFor } from '../../game/godotChars'
import { C, avatarUrl, pillColor } from './theme'
import { displayName } from './PlayerChip'

/** 「镇上的人」（mockC2）：六人两列——28px 头像 · 名字 · 区域 · 状态药丸 · 距离 · 👁 跟随；含阿蝉自己（高亮） */
export default function PeoplePanel({ follow }: { follow: string | null }) {
  const me = useGameStore((s) => s.player)
  const identity = useGameStore((s) => s.identity)
  const players = useGameStore((s) => s.players)
  const objects = useGameStore((s) => s.objects)
  const tiles = useGameStore((s) => s.tiles)
  const tileAt = useMemo(() => new Map(tiles.map(t => [`${t.x},${t.y}`, t] as const)), [tiles])
  if (!me) return null
  type Row = { id: string; key: string; name: string; zone: string; doing: string; dist: number; online: boolean; self: boolean; thought: string }
  const rows: Row[] = players.filter(p => p.id !== me.id).map(p => {
    const t = tileAt.get(`${p.position.x},${p.position.y}`)
    const th = p.last_thought?.text?.trim() ?? ''
    return { id: p.id, key: godotCharKeyFor(p.name, p.controller, p.agent_id), name: p.name, zone: zoneLabel(t) || '—', doing: (deriveStateLabel(p, objects) ?? (p.state === 'walking' ? '🚶 走路' : '站着')).replace(/^[^一-龥A-Za-z]+/, ''), dist: Math.abs(p.position.x - me.position.x) + Math.abs(p.position.y - me.position.y), online: p.online !== false, self: false, thought: th }
  })
  const myTile = tileAt.get(`${me.position.x},${me.position.y}`)
  rows.push({ id: me.id, key: godotCharKeyFor(me.profile?.name ?? me.id, 'human', identity ?? me.agent_id ?? null), name: displayName(me.profile?.name ?? me.id, identity), zone: zoneLabel(myTile) || '—', doing: me.state === 'walking' ? '走路' : (me.stateLabel ?? me.state ?? '').replace(/^[^一-龥A-Za-z]+/, '') || '站着', dist: 0, online: true, self: true, thought: '' })
  const go = (r: Row) => EventBus.emit('director-cmd', r.self ? { cmd: 'self' } : { cmd: 'follow', id: r.id })
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
      {rows.map(r => {
        const pc = pillColor(r.online ? r.doing : '离线')
        const following = r.self ? follow === null : follow === r.id
        return (
          <div key={r.id} data-testid={`people-${r.id}`} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px', borderRadius: 8, background: r.self ? '#FFF1CF' : 'rgba(255,255,255,0.55)', border: `1px solid ${r.self ? C.amber : '#E6DCCB'}`, opacity: r.online ? 1 : 0.6 }}>
            <img className="px" src={avatarUrl(r.key, 80)} width={32} height={32} alt="" style={{ borderRadius: 6, border: `1px solid ${C.sky}`, background: '#fff' }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <b style={{ fontSize: 14 }}>{r.name}</b>
                <span style={{ fontSize: 11, padding: '1px 7px', borderRadius: 9, background: pc.bg, color: pc.fg, whiteSpace: 'nowrap' }}>{r.online ? r.doing : '离线'}</span>
              </div>
              <div style={{ fontSize: 11, color: C.inkSoft, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={r.thought ? `💭 ${r.thought}` : r.zone}>{r.zone}{r.thought ? <span style={{ color: '#7E62C9' }}> · 💭 {r.thought.length > 16 ? r.thought.slice(0, 16) + '…' : r.thought}</span> : null}</div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <button className={`rb${following ? ' active' : ''}`} onClick={() => go(r)} title={r.self ? '镜头回到阿蝉' : '镜头跟随'} data-testid={`eye-${r.id}`} style={{ background: following ? '#E3F0FB' : C.cream, border: `1px solid ${C.sky}`, borderRadius: 6, cursor: 'pointer', fontSize: 14, padding: '1px 6px', lineHeight: 1.3 }}>👁</button>
              <div style={{ fontSize: 11, color: C.inkSoft, marginTop: 2 }}>{r.self ? '我' : `${r.dist} 格`}</div>
            </div>
          </div>
        )
      })}
      {rows.length <= 1 && <div style={{ color: C.inkSoft, padding: 8 }}>镇上没有别人</div>}
    </div>
  )
}
