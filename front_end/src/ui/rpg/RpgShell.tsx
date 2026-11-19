import { useEffect, useState } from 'react'
import './rpg.css'
import { useGameStore } from '../../store/gameStore'
import { EventBus } from '../../game/EventBus'
import PlayerChip from './PlayerChip'
import TopRight from './TopRight'
import BottomBar, { SUMMON, type PanelKey } from './BottomBar'
import PanelFrame from './PanelFrame'
import PeoplePanel from './PeoplePanel'
import SchoolCard from './SchoolCard'
import ObjectHint from './ObjectHint'
import ErrorBoundary from '../ErrorBoundary'
import SettingsPanel from './SettingsPanel'
import HUD from '../HUD'
import BackpackPanel from '../BackpackPanel'
import ActionLog from '../ActionLog'
import Minimap from '../Minimap'
import ChatPanel from '../ChatPanel'
import QQPanel from '../QQPanel'
import KnockPanel from '../KnockPanel'
import InteractionPanel from '../InteractionPanel'
import ConnectionBadge from '../ConnectionBadge'
import { panel } from './theme'
import { setUiSkin } from '../uiPalette'
import { useFollowedPlayer, FollowBag, FollowChat } from './FollowPanels'
import { godotCharKeyFor } from '../../game/godotChars'
import { displayName } from './PlayerChip'

/**
 * 操控页像素 RPG 菜单风外壳（主播 11-16 定稿 mockC1 / C2）：
 *   左上阿蝉小卡 · 右上 时间天气金币 + 导播三键 · 底部六个召唤键（快捷键 1–6）· 左下 QQ 手机 · 右下常态小地图 · toast 在底栏上方 · 面板从底栏上方弹出（同时只开一块）。
 *   骨架版：布局 + 交互 + 字体；皮肤（九宫格 / 按钮 / 药丸 / 图标）等素材包到了替换。旧面板（HUD / 背包 / 日志 / 聊天）先以暗色内容区嵌入。
 */
export default function RpgShell({ playerId }: { playerId: string }) {
  const [open, setOpen] = useState<PanelKey | null>(null)
  const [dir, setDir] = useState<{ mode: 'self' | 'free' | 'follow'; follow: string | null }>({ mode: 'self', follow: null })
  const toggle = (k: PanelKey) => setOpen(o => (o === k ? null : k))
  useEffect(() => { setUiSkin('rpg'); return () => setUiSkin('dark') }, [])
  useEffect(() => {
    const on = (s: typeof dir) => setDir(s)
    EventBus.on('director-state', on)
    return () => { EventBus.off('director-state', on) }
  }, [])
  // 快捷键 1–6 开关面板；Esc 关面板（输入框聚焦时不抢）
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      const s = SUMMON.find(x => x.hk === e.key)
      if (s) { toggle(s.key); e.preventDefault(); return }
      if (e.key === 'Escape' && open) setOpen(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])
  // 主播 11-16（2552 宽屏）：所有控件按视口统一放大，基准 1920 = 1.0，上限 1.6
  const [uiScale, setUiScale] = useState(() => Math.min(1.6, Math.max(1, window.innerWidth / 1920)))
  useEffect(() => {
    const on = () => setUiScale(Math.min(1.6, Math.max(1, window.innerWidth / 1920)))
    window.addEventListener('resize', on)
    return () => window.removeEventListener('resize', on)
  }, [])
  const title = open ? (open === 'me' ? '我的状态' : SUMMON.find(s => s.key === open)?.label ?? '') : ''
  const players = useGameStore((s) => s.players)
  const myId = useGameStore((s) => s.myPlayerId)
  const followOther = dir.mode === 'follow' && dir.follow && dir.follow !== myId ? players.find(p => p.id === dir.follow) ?? null : null
  const followName = followOther ? displayName(followOther.name, null) : ''
  const followKey = followOther ? godotCharKeyFor(followOther.name, followOther.controller, followOther.agent_id) : 'achan'
  // 导播跟随（director-follow.md）：每 2 s GET /player/{他}，左上卡 / 背包 / 聊天切到他（只读）；镇上的人 / 地图 / 设置 / QQ 不切
  const followed = useFollowedPlayer(followOther ? followOther.id : null)
  return (
    <div className="rpg" style={{ position: 'fixed', inset: 0, pointerEvents: 'none', overflow: 'hidden', zoom: uiScale } as React.CSSProperties}>
      <PlayerChip onOpen={() => { if (followOther) EventBus.emit('director-cmd', { cmd: 'self' }); else toggle('me') }} active={open === 'me'} override={followOther ? { player: followed ?? { ...followOther, profile: { name: followOther.name } } as unknown as import('../../types').Player, name: followName, key: followKey } : null} />
      <TopRight />
      {dir.mode !== 'self' && (
        <div style={panel({ position: 'absolute', top: 12, left: '50%', transform: 'translateX(-50%)', padding: '4px 12px', fontSize: 12, borderRadius: 14 }, '#F2B84B')}>
          🎬 {dir.mode === 'free' ? '自由镜头' : `跟随 ${followName}`} · 点地面阿蝉照样走 · Esc 回阿蝉
        </div>
      )}
      {/* toast / 门禁条：底栏上方；有面板打开时挪到顶部（不被面板盖住） */}
      <div style={{ position: 'absolute', left: 0, right: 0, ...(open ? { top: 64 } : { bottom: 96 }), pointerEvents: 'none' }}>
        <div style={{ pointerEvents: 'auto' }}><KnockPanel anchor="bottom" skin="rpg" /></div>
        <div style={{ pointerEvents: 'auto' }}><InteractionPanel anchor="bottom" skin="rpg" /></div>
        {dir.mode === 'self' && <div style={{ pointerEvents: 'auto' }}><ObjectHint /></div>}
      </div>
      {open && (open !== 'chat' || followOther) && (
        <PanelFrame title={title} onClose={() => setOpen(null)} width={open === 'people' ? 760 : open === 'map' ? 520 : open === 'settings' ? 520 : open === 'chat' ? 600 : 600} dark={false}>
          {open === 'people' && <><SchoolCard follow={dir.mode === 'follow' ? dir.follow : null} /><PeoplePanel follow={dir.mode === 'follow' ? dir.follow : null} /></>}
          {open === 'map' && <div style={{ display: 'flex', justifyContent: 'center' }}><Minimap inline large /></div>}
          {open === 'bag' && (followOther ? <FollowBag player={followed} name={followName} /> : <BackpackPanel embedded />)}
          {open === 'log' && <ActionLog embedded />}
          {open === 'me' && <HUD embedded />}
          {open === 'settings' && <SettingsPanel />}
          {open === 'chat' && followOther && <FollowChat id={followOther.id} name={followName} avatarKey={followKey} player={followed} />}
        </PanelFrame>
      )}
      {/* 聊天：始终挂载（轮询 / 聊天室状态不丢），按 5 显示；来邀请 / 进聊天室自动打开 */}
      <div style={{ pointerEvents: 'auto' }}><ErrorBoundary name="聊天"><ChatPanel embedded visible={open === 'chat' && !followOther} onClose={() => setOpen(null)} onRequestOpen={() => setOpen('chat')} /></ErrorBoundary></div>
      {/* 左下 QQ 手机图标 → 居中手机 */}
      <div style={{ pointerEvents: 'auto' }}><ErrorBoundary name="QQ" resetKey={followOther?.id ?? 'me'}>{followOther
        ? <QQPanel key={`view-${followOther.id}`} viewOf={{ name: followName, key: followKey }} playerId={followOther.id} readOnly compact phone style={{ bottom: 16, left: 16, top: 'auto', right: 'auto' }} />
        : <QQPanel key="me" playerId={playerId} readOnly={false} compact phone style={{ bottom: 16, left: 16, top: 'auto', right: 'auto' }} />}</ErrorBoundary></div>
      {/* 右下常态小地图 */}
      <div className="mm9" style={{ position: 'absolute', right: 12, bottom: 12, pointerEvents: 'auto', background: 'none' }}><Minimap inline /></div>
      <BottomBar open={open} onToggle={toggle} />
      <div style={{ pointerEvents: 'auto' }}><ConnectionBadge /></div>
    </div>
  )
}
