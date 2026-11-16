import { kit } from './theme'

export type PanelKey = 'people' | 'map' | 'bag' | 'log' | 'chat' | 'settings' | 'me'
export const SUMMON: { key: PanelKey; hk: string; icon: string; label: string }[] = [
  { key: 'people', hk: '1', icon: '👥', label: '镇上的人' },
  { key: 'map', hk: '2', icon: '🗺', label: '地图' },
  { key: 'bag', hk: '3', icon: '🎒', label: '背包' },
  { key: 'log', hk: '4', icon: '📜', label: '日志' },
  { key: 'chat', hk: '5', icon: '💬', label: '聊天' },
  { key: 'settings', hk: '6', icon: '⚙', label: '设置' },
]

/** 底部一排六个召唤键（mockC1）：图标 + 文字 + 角上快捷键号；同时只开一块 */
export default function BottomBar({ open, onToggle }: { open: PanelKey | null; onToggle: (k: PanelKey) => void }) {
  return (
    <div data-testid="rpg-bottombar" style={{ position: 'absolute', bottom: 12, left: '50%', transform: 'translateX(-50%)', display: 'flex', gap: 10, pointerEvents: 'auto' }}>
      {SUMMON.map(s => (
        <button key={s.key} className={`sq summon${open === s.key ? ' active' : ''}`} onClick={() => onToggle(s.key)} data-testid={`summon-${s.key}`} title={`${s.label}（快捷键 ${s.hk}）`}>
          <span className="hk">{s.hk}</span>
          <img className="ic" src={kit(`summon_${s.key}${open === s.key ? '_on' : ''}`)} alt={s.icon} />
          <span style={{ fontSize: 14, whiteSpace: 'nowrap' }}>{s.label}</span>
        </button>
      ))}
    </div>
  )
}
