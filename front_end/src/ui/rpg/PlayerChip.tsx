import { useGameStore } from '../../store/gameStore'
import { godotCharKeyFor } from '../../game/godotChars'
import { C, avatarUrl, moodFace, panel } from './theme'

/** 显示名：阿蝉身份一律「阿蝉」；其余去掉 _xxxxxx 后缀 */
export const displayName = (name: string, identity: string | null) => identity === 'achan' ? '阿蝉' : name.replace(/_[0-9a-f]{6}$/i, '')

/** 左上阿蝉小卡（mockC1）：40px 头像 + 名字 + 心情脸 + 四条迷你属性条一行；点一下打开「我」面板（完整 HUD） */
export default function PlayerChip({ onOpen, active }: { onOpen: () => void; active: boolean }) {
  const player = useGameStore((s) => s.player)
  const identity = useGameStore((s) => s.identity)
  if (!player) return null
  const key = godotCharKeyFor(player.profile?.name ?? player.id, 'human', identity ?? player.agent_id ?? null)
  const bars: [string, string, number][] = [
    ['饱腹', C.bar.fullness, Number(player.fullness ?? player.hp ?? 0)],
    ['精力', C.bar.energy, Number(player.energy ?? 0)],
    ['社交', C.bar.social, Number(player.social ?? 0)],
    ['乐趣', C.bar.fun, Number(player.fun ?? 0)],
  ]
  return (
    <div onClick={onOpen} data-testid="rpg-chip" title="点开看完整状态" className={active ? 'active' : ''}
      style={panel({ position: 'absolute', top: 12, left: 12, display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px 8px 8px', cursor: 'pointer', pointerEvents: 'auto', minWidth: 300 })}>
      <img className="px" src={avatarUrl(key, 80)} width={40} height={40} alt="" style={{ borderRadius: 8, border: `2px solid ${C.sky}`, background: '#fff' }} />
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
          <b style={{ fontSize: 16 }}>{displayName(player.profile?.name ?? player.id, identity)}</b>
          <span style={{ fontSize: 16 }} title={`心情 ${Math.floor(Number(player.mood ?? 0))}`}>{moodFace(Number(player.mood ?? 50))}</span>
          {player.dnd && <span style={{ fontSize: 11, color: C.inkSoft }}>勿扰</span>}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {bars.map(([label, color, v]) => (
            <div key={label} style={{ width: 60 }}>
              <div style={{ fontSize: 11, color: C.inkSoft, textAlign: 'center', lineHeight: 1 }}>{label}</div>
              <div className="bar" style={{ marginTop: 2 }}><i style={{ width: `${Math.max(0, Math.min(100, v))}%`, background: v < 25 ? C.coral : color }} /></div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
