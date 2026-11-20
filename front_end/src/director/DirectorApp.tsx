import { useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { useGameStore } from '../store/gameStore'
import { EventBus } from '../game/EventBus'
import { tick, newMemory, lockOn, type Candidate, type DirectorEvent, type Situation, type TickResult } from './scorer'
import { fromPublicEvent, fromLegacy, mergeEvent, CATEGORY_COLOR, type TownEvent } from './events'
import { godotCharKeyFor, isPasserby } from '../game/godotChars'
import { deriveStateLabel } from '../game/stateLabel'
import { zoneLabel } from '../game/map/zones'
import Minimap from '../ui/Minimap'
import type { OtherPlayer, WsChatEvent } from '../types'
import '../ui/rpg/rpg.css'

/**
 * 小镇直播自动导播（whale docs/systems/town-director-plan.md，主播 11-20 拍板）：`/spectate?director=1`。
 * 一期：打分选人（scorer.ts）+ 导播台锁人 + 情境布局框架（主角右半 x≈1250、左 40% 面板、名牌 / 跑马灯 / 时钟）
 *       + 面板：对话记录 / 走路小地图 / 全景居民卡 / 睡觉；其余情境先用状态卡占位（二期商店 / 钓鱼，三期上课 / 写歌 / QQ）。
 * 只读：只读 store（ws / 轮询已在）+ EventBus；镜头通过 spectate-cmd / spectate-offset 交给 GameScene。
 */
const W = 1920, H = 1080, PANEL_W = 768, TICK_MS = 2000, FOLLOW_X = 1250
const FONT = '"Fusion Pixel 12px", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif'
const C = { cream: 'rgba(255,248,236,0.94)', sky: '#7FB6E8', ink: '#3B2F2F', soft: '#7A6A5A', teal: '#3BB7A8', coral: '#FF8A73', amber: '#F2B84B' }
const SIT_ZH: Record<Situation, string> = { chat: '聊天中', trade: '买卖中', event: '刚刚', class: '上课中', create: '创作中', fishing: '钓鱼中', qq: '看手机', walk: '走路中', idle: '发呆', sleep: '睡觉', eat: '吃饭', live: '直播中', panorama: '全景' }
const avatar = (key: string, px = 80) => `assets/ui/avatars/${key}_${px}.png`
const keyOf = (p: Pick<OtherPlayer, 'name' | 'controller' | 'agent_id' | 'sprite'>) => godotCharKeyFor(p.name, p.controller, p.agent_id, p.sprite)

interface ChatLine { from: string; name: string; text: string; at: number }
interface Room { id: string; participants: string[]; lines: ChatLine[]; at: number }

/** 导播的数据缓冲：对话房间、最后一句、事件（模块内，跟着页面活） */
function useDirectorFeed() {
  const rooms = useRef(new Map<string, Room>())
  const lastLine = useRef(new Map<string, number>())
  const [events, setEvents] = useState<TownEvent[]>([])
  const havePublic = useRef(false)
  const [, bump] = useState(0)
  useEffect(() => {
    const nameOf = (id: string) => useGameStore.getState().players.find(p => p.id === id)?.name ?? id
    const add = (e: TownEvent | null) => { if (e) setEvents(l => mergeEvent(l, e)) }
    const onRow = (c: WsChatEvent) => {
      const now = Date.now()
      const r = rooms.current.get(c.chat_room_id) ?? { id: c.chat_room_id, participants: c.participants ?? [], lines: [], at: now }
      if (c.participants?.length) r.participants = c.participants
      if (c.kind === 'message' && c.from_entity_id && c.content) {
        r.lines = [...r.lines, { from: c.from_entity_id, name: c.from_name ?? nameOf(c.from_entity_id), text: c.content, at: now }].slice(-20)
        lastLine.current.set(c.from_entity_id, now)
      }
      r.at = now
      rooms.current.set(c.chat_room_id, r)
      bump(x => x + 1)
    }
    const onPublic = (e: Record<string, unknown>) => { havePublic.current = true; add(fromPublicEvent(e, Date.now())) }
    const legacy = (t: 'action' | 'produce' | 'fishing') => (m: Record<string, unknown>) => { if (!havePublic.current) add(fromLegacy(t, m, nameOf, Date.now())) }
    const onA = legacy('action'), onP = legacy('produce'), onF = legacy('fishing')
    EventBus.on('chat-row', onRow); EventBus.on('public-event', onPublic)
    EventBus.on('action-event', onA); EventBus.on('produce-event', onP); EventBus.on('fishing-event', onF)
    return () => { EventBus.off('chat-row', onRow); EventBus.off('public-event', onPublic); EventBus.off('action-event', onA); EventBus.off('produce-event', onP); EventBus.off('fishing-event', onF) }
  }, [])
  return { rooms: rooms.current, lastLine: lastLine.current, events }
}

function buildCandidates(players: OtherPlayer[], rooms: Map<string, Room>, lastLine: Map<string, number>, events: TownEvent[], now: number): Candidate[] {
  const achan = players.find(p => p.agent_id === 'achan')
  return players.map(p => {
    const room = [...rooms.values()].filter(r => r.participants.includes(p.id) && now - r.at < 90_000).sort((a, b) => b.at - a.at)[0]
    const talking = p.state === 'talking' || (p.tags ?? []).includes('chat_active') || !!room
    const busy = p.busy as { progress?: number } | null | undefined
    const label = p.stateLabel ?? ''
    return {
      id: p.id, name: p.name, agentId: p.agent_id, controller: p.controller, role: p.role,
      activity: p.now?.activity ?? null, state: p.state, stateLabel: label,
      inChat: talking, lastLineAt: lastLine.get(p.id) ?? null,
      trading: /买|卖|点餐|点菜|结账|收银/.test(label) || events.some(e => e.who === p.id && e.category === 'trade' && now - e.at < 20_000),
      inClass: !!p.lesson, classHot: events.some(e => e.who === p.id && e.category === 'school' && now - e.at < 15_000),
      progress: typeof busy?.progress === 'number' ? busy.progress : null,
      toMeet: !!p.now?.dest?.purpose,
      withAchan: !!achan && !!room && room.participants.includes(achan.id),
    }
  })
}

export default function DirectorApp({ showConsole }: { showConsole: boolean }) {
  const players = useGameStore((s) => s.players)
  const objects = useGameStore((s) => s.objects)
  const tiles = useGameStore((s) => s.tiles)
  const ws = useGameStore((s) => s.worldState)
  const { rooms, lastLine, events } = useDirectorFeed()
  const mem = useRef(newMemory(0))
  const [res, setRes] = useState<TickResult | null>(null)
  const [consoleOpen, setConsoleOpen] = useState(showConsole)
  const [lockMin, setLockMin] = useState(3)
  const [scale, setScale] = useState(() => Math.min(window.innerWidth / W, window.innerHeight / H))
  useEffect(() => { const on = () => setScale(Math.min(window.innerWidth / W, window.innerHeight / H)); window.addEventListener('resize', on); return () => window.removeEventListener('resize', on) }, [])
  useEffect(() => { const k = (e: KeyboardEvent) => { if (e.key === 'd' || e.key === 'D') setConsoleOpen(o => !o) }; window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k) }, [])
  // 主循环：每 2 s 打分；结果变了就下镜头命令
  // 场景回报的当前跟随（spectate-state）：和导播结果不一致就重发——导播挂载时场景可能还没就绪，第一条命令会丢
  const sceneFollow = useRef<string | null | undefined>(undefined)
  useEffect(() => { const on = (s: { follow: string | null; mode: string }) => { sceneFollow.current = s.mode === 'world' ? null : s.follow }; EventBus.on('spectate-state', on); return () => { EventBus.off('spectate-state', on) } }, [])
  const evRef = useRef(events); evRef.current = events
  const runTick = () => {
    const now = Date.now()
    const ps = useGameStore.getState().players
    const dEvents: DirectorEvent[] = evRef.current.filter(e => e.category !== 'trade').map(e => ({ who: e.who, at: e.at, label: e.text }))
    const r = tick(buildCandidates(ps, rooms, lastLine, evRef.current, now), dEvents, mem.current, now)
    setRes(r)
    if (r.follow !== sceneFollow.current) EventBus.emit('spectate-cmd', r.follow ? { cmd: 'follow', id: r.follow } : { cmd: 'world' })
    EventBus.emit('spectate-offset', { x: r.follow ? (FOLLOW_X - W / 2) : 0 })
  }
  useEffect(() => { runTick(); const t = window.setInterval(runTick, TICK_MS); return () => window.clearInterval(t) }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const lock = (id: string | null) => { lockOn(mem.current, id, lockMin, Date.now()); runTick() }

  const target = res?.follow ? players.find(p => p.id === res.follow) ?? null : null
  const sit: Situation = res?.situation ?? 'panorama'
  const tileAt = useMemo(() => new Map(tiles.map(t => [`${t.x},${t.y}`, t] as const)), [tiles])
  const zoneOf = (p: OtherPlayer) => zoneLabel(tileAt.get(`${p.position.x},${p.position.y}`)) || '小镇'
  const doingOf = (p: OtherPlayer) => p.now?.text || (deriveStateLabel(p, objects) ?? '').replace(/^[^一-龥A-Za-z]+/, '') || SIT_ZH[sit]

  // 事件提示：镜头内中下大提示 2.5 s；镜头外右侧小卡 ≤3 张 6 s
  const [nowMs, setNowMs] = useState(0)
  useEffect(() => { const t = window.setInterval(() => setNowMs(Date.now()), 500); return () => window.clearInterval(t) }, [])
  const big = events.filter(e => target && e.who === target.id && nowMs - e.at < 2500).slice(-1)[0]
  const cards = events.filter(e => (!target || e.who !== target.id) && nowMs - e.at < 6000).slice(-3)

  return (
    <div data-testid="director" style={{ position: 'fixed', left: '50%', top: '50%', width: W, height: H, transform: `translate(-50%, -50%) scale(${scale})`, transformOrigin: 'center', pointerEvents: 'none', fontFamily: FONT, color: C.ink }}>
      {/* 左 40% 情境面板（滑入） */}
      <SlidePanel k={`${sit}-${target?.id ?? 'pan'}`} tall={sit === 'chat'}>
        {sit === 'panorama' && <PanoramaPanel players={players.filter(p => !isPasserby(p))} zoneOf={zoneOf} doingOf={doingOf} />}
        {sit === 'chat' && target && <ChatLog target={target} rooms={rooms} players={players} now={nowMs} />}
        {sit === 'walk' && target && <WalkPanel target={target} zone={zoneOf(target)} />}
        {sit === 'sleep' && target && <SleepPanel target={target} />}
        {!['panorama', 'chat', 'walk', 'sleep'].includes(sit) && target && <StateCard target={target} sit={sit} doing={doingOf(target)} zone={zoneOf(target)} />}
      </SlidePanel>
      {sit === 'sleep' && <div style={{ position: 'absolute', inset: 0, background: 'rgba(10,14,40,0.35)' }} />}
      {/* 左上「现在在看」名牌 */}
      <div data-testid="director-nameplate" style={{ ...box, position: 'absolute', left: 24, top: 24, display: 'flex', alignItems: 'center', gap: 14, padding: '10px 18px 10px 10px', minWidth: 360, maxWidth: 720 }}>
        {target ? <img src={avatar(keyOf(target), 80)} width={64} height={64} alt="" style={{ borderRadius: 10, border: `2px solid ${C.sky}`, background: '#fff', imageRendering: 'pixelated' }} /> : <span style={{ fontSize: 44 }}>🗺</span>}
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 14, color: C.soft }}>现在在看 · {SIT_ZH[sit]}</div>
          <div style={{ fontSize: 30, fontWeight: 700, whiteSpace: 'nowrap' }}>{target ? target.name.replace(/_[0-9a-f]{6}$/i, '') : '小镇此刻'}</div>
          {target && <div style={{ fontSize: 18, color: C.soft, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 600 }}>{doingOf(target)}</div>}
        </div>
      </div>
      {/* 右上时钟 / 天气 */}
      <div style={{ ...box, position: 'absolute', right: 24, top: 24, padding: '10px 18px', fontSize: 26, fontWeight: 700 }}>
        {(ws?.time ?? '--:--').slice(0, 5)} <span style={{ fontSize: 18, color: C.soft, fontWeight: 400 }}>{ws?.weather === 'rain' ? '🌧 雨' : ws?.weather === 'cloudy' ? '☁ 阴' : ws?.period === 'night' ? '🌙 夜' : '☀ 晴'}</span>
      </div>
      {/* 镜头内大提示 */}
      {big && <div data-testid="director-big" style={{ position: 'absolute', left: PANEL_W, right: 0, bottom: 330, display: 'flex', justifyContent: 'center' }}><div style={{ ...box, padding: '14px 28px', fontSize: 34, fontWeight: 700, background: CATEGORY_COLOR[big.category].bg, color: CATEGORY_COLOR[big.category].fg, animation: 'dirPop 250ms ease-out' }}>{big.icon} {big.text}</div></div>}
      {/* 镜头外右侧小卡 */}
      <div style={{ position: 'absolute', right: 24, top: 110, display: 'flex', flexDirection: 'column', gap: 10, width: 420 }}>
        {cards.map(e => <div key={e.key} data-testid="director-card" style={{ ...box, padding: '10px 14px', fontSize: 20, background: CATEGORY_COLOR[e.category].bg, color: CATEGORY_COLOR[e.category].fg, animation: 'dirSlide 300ms ease-out' }}>{e.icon} {e.text}</div>)}
      </div>
      {/* 底部跑马灯 */}
      <Ticker events={events} />
      {/* 导播台 */}
      {consoleOpen && res && (
        <div data-testid="director-console" style={{ position: 'absolute', right: 24, bottom: 76, width: 420, background: 'rgba(15,15,30,0.86)', color: '#e2e8f0', borderRadius: 10, padding: '10px 12px', fontSize: 15, pointerEvents: 'auto', fontFamily: 'system-ui, "PingFang SC", sans-serif' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
            <b>导播台</b><span style={{ color: '#a0aec0', fontSize: 13 }}>{res.reason}</span>
            <button onClick={() => setConsoleOpen(false)} style={{ ...cbtn, marginLeft: 'auto' }} title="D 键开关">✕</button>
          </div>
          <div style={{ display: 'flex', gap: 4, alignItems: 'center', marginBottom: 6, fontSize: 13 }}>
            锁定 {[1, 3, 5, 10].map(m => <button key={m} onClick={() => setLockMin(m)} style={{ ...cbtn, background: lockMin === m ? '#2b6cb0' : '#2a2d3e' }}>{m} 分</button>)}
            {mem.current.lock && <button onClick={() => lock(null)} style={{ ...cbtn, background: '#744210' }}>解锁</button>}
          </div>
          {res.scores.map(s => (
            <div key={s.id} onClick={() => lock(s.id)} data-testid={`director-cand-${s.id}`} style={{ display: 'flex', gap: 8, padding: '3px 6px', borderRadius: 6, cursor: 'pointer', background: s.id === res.follow ? 'rgba(59,183,168,0.3)' : 'transparent' }}>
              <span style={{ flex: 1 }}>{mem.current.lock?.id === s.id ? '🔒 ' : ''}{s.name.replace(/_[0-9a-f]{6}$/i, '')}</span>
              <span style={{ color: '#a0aec0' }}>{SIT_ZH[s.situation]}</span>
              <span style={{ width: 50, textAlign: 'right' }}>{s.score}</span>
            </div>
          ))}
          <div style={{ color: '#718096', fontSize: 12, marginTop: 4 }}>点名字锁定 {lockMin} 分钟 · 阿蝉 / 路人不参与 · D 键开关</div>
        </div>
      )}
      <style>{`@keyframes dirSlide { from { transform: translateX(-40px); opacity: 0 } to { transform: none; opacity: 1 } } @keyframes dirPop { from { transform: scale(0.8); opacity: 0 } to { transform: none; opacity: 1 } } @keyframes dirTicker { from { transform: translateX(100%) } to { transform: translateX(-100%) } }`}</style>
    </div>
  )
}

const box: CSSProperties = { background: C.cream, border: `3px solid ${C.sky}`, borderRadius: 12, boxShadow: '3px 3px 0 #D9C9B0' }
const cbtn: CSSProperties = { border: 'none', borderRadius: 5, color: '#fff', background: '#2a2d3e', padding: '2px 8px', cursor: 'pointer', fontSize: 12 }

function SlidePanel({ k, tall, children }: { k: string; tall: boolean; children: ReactNode }) {
  return (
    <div key={k} data-testid="director-panel" style={{ ...box, position: 'absolute', left: 24, top: 130, width: PANEL_W - 48, ...(tall ? { bottom: 80 } : { maxHeight: H - 210 }), padding: 18, overflow: 'hidden', animation: 'dirSlide 300ms ease-out', display: 'flex', flexDirection: 'column', gap: 12 }}>{children}</div>
  )
}

function ChatLog({ target, rooms, players, now }: { target: OtherPlayer; rooms: Map<string, Room>; players: OtherPlayer[]; now: number }) {
  const room = [...rooms.values()].filter(r => r.participants.includes(target.id)).sort((a, b) => b.at - a.at)[0]
  const lines = room?.lines.slice(-8) ?? []
  const names = (room?.participants ?? [target.id]).map(id => players.find(p => p.id === id)?.name.replace(/_[0-9a-f]{6}$/i, '') ?? id)
  return (
    <>
      <div style={{ fontSize: 22, fontWeight: 700 }}>💬 {names.join(' · ')}</div>
      <div data-testid="director-chat" style={{ display: 'flex', flexDirection: 'column', gap: 10, overflow: 'hidden', justifyContent: 'flex-end', flex: 1 }}>
        {lines.length === 0 && <div style={{ color: C.soft, fontSize: 20 }}>正在聊……</div>}
        {lines.map((l, i) => {
          const p = players.find(x => x.id === l.from)
          const fresh = now - l.at < 5000 && i === lines.length - 1
          return (
            <div key={`${l.at}-${i}`} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', opacity: fresh ? 1 : 0.88 }}>
              <img src={avatar(p ? keyOf(p) : 'achan', 56)} width={44} height={44} alt="" style={{ borderRadius: 8, border: `2px solid ${fresh ? C.amber : C.sky}`, background: '#fff', imageRendering: 'pixelated', flexShrink: 0 }} />
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 14, color: C.soft }}>{l.name.replace(/_[0-9a-f]{6}$/i, '')}</div>
                <div style={{ fontSize: 21, lineHeight: 1.4, background: fresh ? '#FFF1CF' : '#fff', border: `1px solid ${fresh ? C.amber : '#E6DCCB'}`, borderRadius: 10, padding: '6px 12px', wordBreak: 'break-word' }}>{l.text}</div>
              </div>
            </div>
          )
        })}
      </div>
    </>
  )
}

function WalkPanel({ target, zone }: { target: OtherPlayer; zone: string }) {
  const d = target.now?.dest
  return (
    <>
      <div style={{ fontSize: 22, fontWeight: 700 }}>🚶 {d?.name ? `→ ${d.name}` : '走路中'}{d?.purpose ? <span style={{ fontWeight: 400, color: C.soft }}>（{d.purpose}）</span> : null}</div>
      <div style={{ fontSize: 16, color: C.soft }}>现在在 {zone}</div>
      <div style={{ display: 'flex', justifyContent: 'center', pointerEvents: 'none' }}><Minimap inline large followId={target.id} /></div>
    </>
  )
}

function SleepPanel({ target }: { target: OtherPlayer }) {
  return (
    <>
      <div style={{ fontSize: 26, fontWeight: 700 }}>🌙 {target.name.replace(/_[0-9a-f]{6}$/i, '')} 睡着了</div>
      <div style={{ fontSize: 60, textAlign: 'center', marginTop: 40, animation: 'dirPop 1.6s ease-in-out infinite alternate' }}>💤 Zzz</div>
    </>
  )
}

function StateCard({ target, sit, doing, zone }: { target: OtherPlayer; sit: Situation; doing: string; zone: string }) {
  const busy = target.busy as { progress?: number } | null | undefined
  const p = typeof busy?.progress === 'number' ? busy.progress : null
  const icon: Partial<Record<Situation, string>> = { trade: '🛒', event: '✨', class: '📚', create: '🎵', fishing: '🎣', qq: '📱', eat: '🍽', live: '📺', idle: '☕' }
  return (
    <>
      <div style={{ fontSize: 26, fontWeight: 700 }}>{icon[sit] ?? '•'} {SIT_ZH[sit]}</div>
      <div style={{ fontSize: 22 }}>{doing}</div>
      <div style={{ fontSize: 16, color: C.soft }}>在 {zone}</div>
      {p !== null && <div style={{ height: 18, background: '#EDE3D2', borderRadius: 9, overflow: 'hidden' }}><div style={{ width: `${Math.round(p * 100)}%`, height: '100%', background: C.teal }} /></div>}
    </>
  )
}

function PanoramaPanel({ players, zoneOf, doingOf }: { players: OtherPlayer[]; zoneOf: (p: OtherPlayer) => string; doingOf: (p: OtherPlayer) => string }) {
  return (
    <>
      <div style={{ fontSize: 24, fontWeight: 700 }}>🗺 小镇此刻</div>
      <div data-testid="director-residents" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {players.map(p => (
          <div key={p.id} style={{ display: 'flex', alignItems: 'center', gap: 12, background: '#fff', border: '1px solid #E6DCCB', borderRadius: 10, padding: '8px 12px', opacity: p.online === false ? 0.6 : 1 }}>
            <img src={avatar(keyOf(p), 56)} width={48} height={48} alt="" style={{ borderRadius: 8, border: `2px solid ${C.sky}`, imageRendering: 'pixelated', background: '#fff' }} />
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 20, fontWeight: 700 }}>{p.name.replace(/_[0-9a-f]{6}$/i, '')} <span style={{ fontSize: 14, color: C.soft, fontWeight: 400 }}>· {zoneOf(p)}</span></div>
              <div style={{ fontSize: 16, color: C.soft, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 560 }}>{doingOf(p)}</div>
            </div>
          </div>
        ))}
      </div>
    </>
  )
}

function Ticker({ events }: { events: TownEvent[] }) {
  const recent = events.slice(-10)
  if (!recent.length) return null
  const text = recent.map(e => `${e.icon} ${e.text}`).join('　　·　　')
  return (
    <div data-testid="director-ticker" style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: 56, background: 'rgba(59,47,47,0.82)', color: '#FFF8EC', overflow: 'hidden', display: 'flex', alignItems: 'center', fontSize: 22 }}>
      <div key={recent[recent.length - 1].key} style={{ whiteSpace: 'nowrap', animation: `dirTicker ${Math.max(20, text.length * 0.35)}s linear infinite` }}>{text}</div>
    </div>
  )
}
