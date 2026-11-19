import { useEffect, useRef, useState, type ReactNode } from 'react'
import './rpg.css'
import { useGameStore } from '../../store/gameStore'
import { EventBus } from '../../game/EventBus'
import { godotCharKeyFor } from '../../game/godotChars'
import type { DirectorCmd } from '../../game/scenes/GameScene'
import PeoplePanel from './PeoplePanel'
import SchoolCard from './SchoolCard'
import ObjectHint from './ObjectHint'
import ErrorBoundary from '../ErrorBoundary'
import SettingsPanel from './SettingsPanel'
import BackpackPanel from '../BackpackPanel'
import ActionLog from '../ActionLog'
import Minimap from '../Minimap'
import ChatPanel from '../ChatPanel'
import QQPanel from '../QQPanel'
import KnockPanel from '../KnockPanel'
import InteractionPanel from '../InteractionPanel'
import ConnectionBadge from '../ConnectionBadge'
import { useFollowedPlayer, FollowBag, FollowChat } from './FollowPanels'
import { displayName } from './PlayerChip'
import { C, avatarUrl, kit, moodFace } from './theme'
import { setUiSkin } from '../uiPalette'

/**
 * 竖屏手机外壳（总控 mobile.md 11-16，只做竖屏）：顶条（头像 + 名字 + 心情脸，点开五条；右时间 / 天气 / 金币）· 画布满屏 · 右上三枚 40px 圆钮（回阿蝉 / 自由 / 💭）
 * · 底部 Tab（人 / 地图 / 背包 / 聊天 / QQ / ⋯）· 面板 = 底部抽屉（60% ↔ 90%，下滑关）· QQ 全屏（手机 QQ 界面去壳）· toast 在顶条下。
 * 触控一期：点地走路沿用；点角色弹动作条（聊天 / 看看他 / 跟随）。双指缩放 / 长按 / 键盘跟随第二轮。
 */
type Tab = 'people' | 'map' | 'bag' | 'chat' | 'qq' | 'more' | 'log' | 'settings'
const PERIOD: Record<string, string> = { morning: '早晨', day: '白天', dusk: '黄昏', night: '夜晚' }
const SAFE_TOP = 'env(safe-area-inset-top, 0px)', SAFE_BOTTOM = 'env(safe-area-inset-bottom, 0px)'

export default function MobileShell({ playerId, kb }: { playerId: string; kb: number }) {
  const [open, setOpen] = useState<Tab | null>(null)
  const [tall, setTall] = useState(false)
  const [chipOpen, setChipOpen] = useState(false)
  const [dir, setDir] = useState<{ mode: 'self' | 'free' | 'follow'; follow: string | null }>({ mode: 'self', follow: null })
  const [thoughts, setThoughts] = useState(true)
  const [actor, setActor] = useState<{ id: string; name: string; x: number; y: number } | null>(null)
  const player = useGameStore((s) => s.player)
  const identity = useGameStore((s) => s.identity)
  const ws = useGameStore((s) => s.worldState)
  const players = useGameStore((s) => s.players)
  const myId = useGameStore((s) => s.myPlayerId)
  useEffect(() => { setUiSkin('rpg'); return () => setUiSkin('dark') }, [])
  useEffect(() => {
    const onDir = (s: typeof dir) => setDir(s)
    const onTap = (t: { id: string; name: string; x: number; y: number }) => setActor(t)
    EventBus.on('director-state', onDir); EventBus.on('actor-tap', onTap)
    return () => { EventBus.off('director-state', onDir); EventBus.off('actor-tap', onTap) }
  }, [])
  useEffect(() => { if (!actor) return; const t = window.setTimeout(() => setActor(null), 6000); return () => window.clearTimeout(t) }, [actor])
  const send = (c: DirectorCmd) => EventBus.emit('director-cmd', c)
  const followOther = dir.mode === 'follow' && dir.follow && dir.follow !== myId ? players.find(p => p.id === dir.follow) ?? null : null
  const followName = followOther ? displayName(followOther.name, null) : ''
  const followKey = followOther ? godotCharKeyFor(followOther.name, followOther.controller, followOther.agent_id) : 'achan'
  const followed = useFollowedPlayer(followOther ? followOther.id : null)
  const shown = followOther ? (followed ?? null) : player
  const myKey = player ? godotCharKeyFor(player.profile?.name ?? player.id, 'human', identity ?? player.agent_id ?? null) : 'achan'
  const toggle = (t: Tab) => { setOpen(o => (o === t ? null : t)); setTall(false) }
  const bars: [string, string, number, string][] = shown ? [
    ['饱腹', C.bar.fullness, Number(shown.fullness ?? shown.hp ?? 0), 'mi_bread'], ['精力', C.bar.energy, Number(shown.energy ?? 0), 'mi_bolt'],
    ['社交', C.bar.social, Number(shown.social ?? 0), 'mi_people'], ['乐趣', C.bar.fun, Number(shown.fun ?? 0), 'mi_star'], ['心情', C.bar.mood, Number(shown.mood ?? 0), 'mi_happy'],
  ] : []
  const wIcon = ws?.weather === 'rain' ? 'mi_rain' : ws?.weather === 'cloudy' ? 'mi_cloud' : (ws?.period === 'night' ? 'mi_moon' : 'mi_sun')
  const tabs: { key: Tab; icon: string; label: string }[] = [
    { key: 'people', icon: 'summon_people', label: '人' }, { key: 'map', icon: 'summon_map', label: '地图' }, { key: 'bag', icon: 'summon_bag', label: '背包' },
    { key: 'chat', icon: 'summon_chat', label: '聊天' }, { key: 'qq', icon: 'phone_icon', label: 'QQ' }, { key: 'more', icon: 'summon_settings', label: '更多' },
  ]
  const sheetTitle: Record<string, string> = { people: '镇上的人', map: '地图', bag: followOther ? `${followName} 的背包` : '背包', chat: followOther ? `${followName} 的对话` : '聊天', more: '更多', log: '日志', settings: '设置' }
  const round = (icon: string, title: string, active: boolean, onClick: () => void, testid: string) => (
    <button onClick={onClick} title={title} data-testid={testid} style={{ width: 44, height: 44, borderRadius: 22, border: `2px solid ${active ? '#F2B84B' : C.sky}`, background: active ? '#FBEBC9' : C.creamA, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0, boxShadow: `2px 2px 0 ${C.shadow}` }}>
      <img className="mi" src={kit(icon)} alt="" style={{ width: 24, height: 24 }} />
    </button>
  )
  const sheet = (title: string, body: ReactNode) => (
    <BottomSheet title={title} tall={tall} onTall={setTall} onClose={() => setOpen(null)} kb={kb}>{body}</BottomSheet>
  )
  return (
    <div className="rpg mobile" style={{ position: 'fixed', inset: 0, pointerEvents: 'none', overflow: 'hidden', fontSize: 14 }}>
      {/* 顶条 */}
      <div style={{ position: 'absolute', left: 0, right: 0, top: 0, paddingTop: SAFE_TOP, pointerEvents: 'auto' }}>
        <div onClick={() => setChipOpen(o => !o)} data-testid="m-topbar" style={{ height: 44, background: 'rgba(255,248,236,0.92)', borderBottom: `2px solid ${C.sky}`, display: 'flex', alignItems: 'center', gap: 8, padding: '0 10px' }}>
          <span style={{ position: 'relative' }}>
            <img className="px" src={avatarUrl(followOther ? followKey : myKey, 80)} width={36} height={36} alt="" style={{ borderRadius: 8, border: `2px solid ${followOther ? '#C9B6F2' : C.sky}`, background: '#fff', display: 'block' }} />
            {followOther && <span style={{ position: 'absolute', right: -4, bottom: -4, fontSize: 11 }}>🔒</span>}
          </span>
          <b style={{ fontSize: 16 }}>{followOther ? followName : (player ? displayName(player.profile?.name ?? player.id, identity) : '')}</b>
          <span style={{ fontSize: 16 }}>{moodFace(Number(shown?.mood ?? 50))}</span>
          <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
            <img className="mi" src={kit('mi_clock')} alt="" style={{ width: 14, height: 14 }} />{(ws?.time ?? '--:--').slice(0, 5)}
            <img className="mi" src={kit(wIcon)} alt="" style={{ width: 14, height: 14 }} /><span style={{ color: C.inkSoft, fontSize: 11 }}>{PERIOD[ws?.period ?? ''] ?? ''}</span>
            <img className="mi" src={kit('mi_coin')} alt="" style={{ width: 14, height: 14 }} /><b>{typeof shown?.gold === 'number' ? shown.gold.toLocaleString('en-US') : '—'}</b>
          </span>
        </div>
        {chipOpen && (
          <div data-testid="m-chip" style={{ background: 'rgba(255,248,236,0.96)', borderBottom: `2px solid ${C.sky}`, padding: '6px 12px 8px', display: 'flex', flexDirection: 'column', gap: 5 }}>
            {bars.map(([label, color, v, icon]) => (
              <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <img className="mi" src={kit(icon)} alt="" style={{ width: 16, height: 16 }} /><span style={{ width: 32, fontSize: 13, color: C.inkSoft }}>{label}</span>
                <div className="bar" style={{ flex: 1, height: 10 }}><i style={{ width: `${Math.max(0, Math.min(100, v))}%`, background: v < 25 ? C.coral : color }} /></div>
                <span style={{ width: 28, textAlign: 'right', fontSize: 13 }}>{Math.floor(v)}</span>
              </div>
            ))}
            {followOther && <div style={{ fontSize: 12, color: '#5B4A8A' }}>🔒 只看 · 点右上「回阿蝉」回来</div>}
            <SchoolCard follow={dir.mode === 'follow' ? dir.follow : null} compact />
          </div>
        )}
      </div>
      {/* toast / 门禁条：画布底部、Tab 栏上方（主播 11-16：别和右上圆钮重叠） */}
      <div style={{ position: 'absolute', left: 8, right: 8, bottom: `calc(${SAFE_BOTTOM} + 64px)`, pointerEvents: 'auto', zIndex: 5 }}><div style={{ transform: 'scale(0.92)', transformOrigin: 'bottom center' }}><KnockPanel anchor="bottom" skin="rpg" /><InteractionPanel anchor="bottom" skin="rpg" />{dir.mode === 'self' && <ObjectHint compact />}</div></div>
      {/* 右上三枚圆钮（顶条下拉展开时藏起来，别压住五条 / 课表卡） */}
      <div style={{ display: chipOpen ? 'none' : 'flex', position: 'absolute', right: 18, top: `calc(${SAFE_TOP} + 56px)`, flexDirection: 'column', gap: 10, pointerEvents: 'auto' }}>
        {round('dir_back', '回阿蝉', dir.mode === 'self', () => send({ cmd: 'self' }), 'm-dir-self')}
        {round('dir_camera', '自由镜头', dir.mode === 'free', () => send({ cmd: 'free' }), 'm-dir-free')}
        {round('dir_thought', '想法', thoughts, () => { const on = !thoughts; setThoughts(on); EventBus.emit('director-thoughts', { on }) }, 'm-dir-thoughts')}
      </div>
      {dir.mode !== 'self' && <div style={{ position: 'absolute', left: 10, top: `calc(${SAFE_TOP} + 52px)`, background: '#FBEBC9', border: '1px solid #F2B84B', borderRadius: 10, padding: '2px 8px', fontSize: 11, pointerEvents: 'none' }}>🎬 {dir.mode === 'free' ? '自由镜头' : `跟随 ${followName}`}</div>}
      {/* 点角色的动作条 */}
      {actor && (
        <div data-testid="m-actorbar" style={{ position: 'absolute', left: 8, right: 8, top: Math.max(60, Math.min(window.innerHeight - 160, actor.y - 76)), background: C.creamA, border: `2px solid ${C.sky}`, borderRadius: 10, padding: 6, display: 'flex', gap: 6, pointerEvents: 'auto', boxShadow: `2px 2px 0 ${C.shadow}` }}>
          <div style={{ alignSelf: 'center', fontSize: 13, color: C.inkSoft, padding: '0 4px', whiteSpace: 'nowrap', maxWidth: 72, overflow: 'hidden', textOverflow: 'ellipsis' }}>{actor.name}</div>
          <button className="k teal" style={{ flex: 1, minWidth: 96, minHeight: 44, fontSize: 15, whiteSpace: 'nowrap', padding: 0 }} onClick={() => { EventBus.emit('chat-pick', { id: actor.id }); setOpen('chat'); setActor(null) }}>聊天</button>
          <button className="k" style={{ flex: 1, minWidth: 96, minHeight: 44, fontSize: 15, whiteSpace: 'nowrap', padding: 0 }} onClick={() => { send({ cmd: 'follow', id: actor.id }); setOpen('bag'); setActor(null) }}>看看他</button>
          <button className="k" style={{ flex: 1, minWidth: 96, minHeight: 44, fontSize: 15, whiteSpace: 'nowrap', padding: 0 }} onClick={() => { send({ cmd: 'follow', id: actor.id }); setActor(null) }}>跟随</button>
        </div>
      )}
      {/* 抽屉 */}
      {open === 'people' && sheet(sheetTitle.people, <PeoplePanel follow={dir.mode === 'follow' ? dir.follow : null} cols={1} />)}
      {open === 'map' && sheet(sheetTitle.map, <div style={{ display: 'flex', justifyContent: 'center', padding: 4 }}><Minimap inline large /></div>)}
      {open === 'bag' && sheet(sheetTitle.bag, followOther ? <FollowBag player={followed} name={followName} /> : <BackpackPanel embedded />)}
      {open === 'log' && sheet(sheetTitle.log, <ActionLog embedded />)}
      {open === 'settings' && sheet(sheetTitle.settings, <SettingsPanel />)}
      {open === 'more' && sheet('更多', (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <button className="k" style={{ minHeight: 48, fontSize: 15 }} onClick={() => setOpen('log')}>📜 日志</button>
          <button className="k" style={{ minHeight: 48, fontSize: 15 }} onClick={() => setOpen('settings')}>⚙ 设置（楼梯 / 勿扰 / 倍速 / 登出）</button>
        </div>
      ))}
      {open === 'chat' && followOther && sheet(sheetTitle.chat, <FollowChat id={followOther.id} name={followName} avatarKey={followKey} player={followed} />)}
      {/* 聊天（阿蝉自己的）：始终挂载；手机上以抽屉显示 */}
      <div style={{ pointerEvents: 'auto' }}>
        {open === 'chat' && !followOther
          ? sheet('聊天', <ChatPanel embedded frame="plain" visible onClose={() => setOpen(null)} onRequestOpen={() => setOpen('chat')} />)
          : <ErrorBoundary name="聊天"><ChatPanel embedded frame="plain" visible={false} onClose={() => setOpen(null)} onRequestOpen={() => setOpen('chat')} /></ErrorBoundary>}
      </div>
      {/* QQ 全屏（去壳） */}
      <div style={{ pointerEvents: 'auto' }}><ErrorBoundary name="QQ" resetKey={followOther?.id ?? 'me'}>{followOther
        ? <QQPanel key={`view-${followOther.id}`} viewOf={{ name: followName, key: followKey }} playerId={followOther.id} readOnly compact phone fullscreen forceOpen={open === 'qq'} onClosed={() => setOpen(null)} style={{ display: 'none' }} kb={kb} />
        : <QQPanel key="me" playerId={playerId} readOnly={false} compact phone fullscreen forceOpen={open === 'qq'} onClosed={() => setOpen(null)} style={{ display: 'none' }} kb={kb} />}</ErrorBoundary></div>
      {/* 底部 Tab */}
      <div data-testid="m-tabs" style={{ position: 'absolute', left: 0, right: 0, bottom: 0, paddingBottom: SAFE_BOTTOM, background: 'rgba(255,248,236,0.96)', borderTop: `2px solid ${C.sky}`, display: 'flex', pointerEvents: 'auto' }}>
        {tabs.map(t => {
          const active = open === t.key || (t.key === 'more' && (open === 'log' || open === 'settings'))
          return (
            <button key={t.key} onClick={() => toggle(t.key)} data-testid={`m-tab-${t.key}`} style={{ flex: 1, height: 56, border: 'none', background: active ? '#E3F0FB' : 'transparent', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 2, color: active ? '#1F7A6F' : C.ink, padding: 0 }}>
              <img className="mi" src={kit(t.icon)} alt="" style={{ width: t.key === 'qq' ? 16 : 26, height: 26 }} />
              <span style={{ fontSize: 11 }}>{t.label}</span>
            </button>
          )
        })}
      </div>
      <div style={{ pointerEvents: 'auto' }}><ConnectionBadge /></div>
    </div>
  )
}

/** 底部抽屉：60% ↔ 90%（拖柄上滑 / 点切换），下滑或点遮罩关；软键盘弹起时抬高 */
function BottomSheet({ title, tall, onTall, onClose, kb, children }: { title: string; tall: boolean; onTall: (t: boolean) => void; onClose: () => void; kb: number; children: ReactNode }) {
  const startY = useRef<number | null>(null)
  const onStart = (y: number) => { startY.current = y }
  const onEnd = (y: number) => { if (startY.current === null) return; const dy = y - startY.current; startY.current = null; if (dy < -40) onTall(true); else if (dy > 60) { if (tall) onTall(false); else onClose() } }
  return (
    <>
      <div onClick={onClose} style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.25)', pointerEvents: 'auto', zIndex: 6 }} />
      <div data-testid="m-sheet" style={{ position: 'absolute', left: 0, right: 0, bottom: kb, zIndex: 6, height: tall ? '90%' : '60%', background: '#FFF8EC', borderTop: `3px solid ${C.sky}`, borderRadius: '16px 16px 0 0', display: 'flex', flexDirection: 'column', pointerEvents: 'auto', boxShadow: '0 -6px 20px rgba(0,0,0,0.18)', transition: 'height 160ms ease-out' }}>
        <div onTouchStart={e => onStart(e.touches[0].clientY)} onTouchEnd={e => onEnd(e.changedTouches[0].clientY)} onMouseDown={e => onStart(e.clientY)} onMouseUp={e => onEnd(e.clientY)} onClick={() => onTall(!tall)}
          style={{ padding: '8px 14px 6px', display: 'flex', alignItems: 'center', gap: 10, cursor: 'grab', borderBottom: `1px solid #E6DCCB`, touchAction: 'none' }}>
          <span style={{ position: 'absolute', left: '50%', top: 4, transform: 'translateX(-50%)', width: 44, height: 5, borderRadius: 3, background: '#CFC2AE' }} />
          <b style={{ fontSize: 17, marginTop: 6, flex: 1 }}>{title}</b>
          <button className="closex" onClick={e => { e.stopPropagation(); onClose() }} title="关闭" style={{ marginTop: 6 }}>✕</button>
        </div>
        <div className="embed" style={{ flex: 1, overflowY: 'auto', padding: 10, minHeight: 0, color: C.ink, WebkitOverflowScrolling: 'touch' } as React.CSSProperties}><ErrorBoundary name={title} resetKey={title}>{children}</ErrorBoundary></div>
      </div>
    </>
  )
}
