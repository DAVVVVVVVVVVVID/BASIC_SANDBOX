import { useGameStore } from '../../store/gameStore'
import { godotCharKeyFor } from '../../game/godotChars'
import { C, avatarUrl, moodFace, panel, kit } from './theme'

/** 显示名：阿蝉身份一律「阿蝉」；其余去掉 _xxxxxx 后缀 */
export const displayName = (name: string, identity: string | null) => identity === 'achan' ? '阿蝉' : name.replace(/_[0-9a-f]{6}$/i, '')

/** 左上阿蝉竖卡（主播 11-16 二稿）：56px 头 + 肩头像 + 名字 + 心情脸；五条属性竖排（饱腹 / 精力 / 社交 / 乐趣 / 心情，微图标 + 数值）；点一下打开「我」面板 */
export default function PlayerChip({ onOpen, active }: { onOpen: () => void; active: boolean }) {
  const player = useGameStore((s) => s.player)
  const identity = useGameStore((s) => s.identity)
  if (!player) return null
  const key = godotCharKeyFor(player.profile?.name ?? player.id, 'human', identity ?? player.agent_id ?? null)
  const bars: [string, string, number, string][] = [
    ['饱腹', C.bar.fullness, Number(player.fullness ?? player.hp ?? 0), 'mi_bread'],
    ['精力', C.bar.energy, Number(player.energy ?? 0), 'mi_bolt'],
    ['社交', C.bar.social, Number(player.social ?? 0), 'mi_people'],
    ['乐趣', C.bar.fun, Number(player.fun ?? 0), 'mi_star'],
    ['心情', C.bar.mood, Number(player.mood ?? 0), 'mi_happy'],
  ]
  return (
    <div onClick={onOpen} data-testid="rpg-chip" title="点开看完整状态" className={`panel9${active ? ' active' : ''}`}
      style={panel({ position: 'absolute', top: 12, left: 12, width: 206, padding: '2px 6px 4px', cursor: 'pointer', pointerEvents: 'auto' })}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
        <img className="px" src={avatarUrl(key, 112)} width={56} height={56} alt="" style={{ borderRadius: 8, border: `2px solid ${C.sky}`, background: '#fff', boxShadow: '0 0 0 1px #fff inset' }} />
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <b style={{ fontSize: 20 }}>{displayName(player.profile?.name ?? player.id, identity)}</b>
            <span style={{ fontSize: 20 }} title={`心情 ${Math.floor(Number(player.mood ?? 0))}`}>{moodFace(Number(player.mood ?? 50))}</span>
          </div>
          <div style={{ fontSize: 12, color: C.inkSoft }}>{player.dnd ? '勿扰 · 工作中' : (player.stateLabel ?? '').replace(/^[^一-龥A-Za-z]+/, '') || ' '}</div>
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {bars.map(([label, color, v, icon]) => (
          <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <img className="mi" src={kit(icon)} alt="" style={{ width: 16, height: 16, verticalAlign: 'middle' }} />
            <span style={{ width: 30, fontSize: 13, color: C.inkSoft }}>{label}</span>
            <div className="bar" style={{ flex: 1, height: 10 }}><i style={{ width: `${Math.max(0, Math.min(100, v))}%`, background: v < 25 ? C.coral : color }} /></div>
            <span style={{ width: 26, textAlign: 'right', fontSize: 13, fontVariantNumeric: 'tabular-nums' }}>{Math.floor(v)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
