import { API_BASE } from '../../api/client'
import { fetchWorld, fetchWorldLive } from '../../api/world'
import { useGameStore, mapSignature } from '../../store/gameStore'
import { EventBus } from '../EventBus'
import { setZoneNames } from '../map/zones'
import { startPoller, PollerHandle } from './Poller'
import type { WorldData, WsMessage, WsPatch } from '../../types'

/** 轮询节奏（ms）：ws 不可用时的退路 */
export const POLL_WORLD_MS = 500
/** ws 多久没有任何消息（含 5 s 心跳）视为死连接 */
const WS_IDLE_MS = 15000
/** ws 连接建立超时 */
const WS_CONNECT_MS = 5000
/** ws 重连退避 */
const WS_RETRY_MIN = 2000
const WS_RETRY_MAX = 30000

export interface WorldFeedHandle {
  stop: () => void
  /** 当前通道 */
  readonly transport: 'ws' | 'poll' | 'none'
}

function wsUrl(): string {
  const base = API_BASE
  if (/^https?:\/\//.test(base)) return base.replace(/^http/, 'ws') + '/ws/world'
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${location.host}${base}/ws/world`
}

/** 地图签名：优先后端的 mapVersion（W5），老后端退回本地计算 */
function mapKey(world: Pick<WorldData, 'tiles' | 'tiled' | 'worldState'>): string {
  return world.worldState?.mapVersion ?? mapSignature(world)
}

/** 全量 world → store（tiles 只在地图变了时替换） */
export function applyWorldSnapshot(world: WorldData) {
  const s = useGameStore.getState()
  s.setWorldState(world.worldState)
  s.setObjects(world.objects)
  if (world.tiles && world.tiles.length > 0 && mapKey(world) !== s.mapSig) setZoneNames(world.zone_names)
  s.setMap(world.tiles, world.tiled, mapKey(world), { edges: world.edges, floors: world.floors, access: world.access, arenas: world.arenas, map: world.map })
  s.setPlayers(world.players ?? [])
  s.setConnection('online')
}

function applyPatch(p: WsPatch) {
  const s = useGameStore.getState()
  if (p.worldState) {
    const before = s.worldState?.mapVersion
    s.patchWorldState(p.worldState)
    if (p.worldState.mapVersion && before && p.worldState.mapVersion !== before) {
      // 换图：重拉一次全量
      fetchWorld().then(applyWorldSnapshot).catch(() => {})
    }
  }
  if (p.players) s.patchPlayers(p.players.upsert, p.players.remove)
  if (p.objects) s.patchObjects(p.objects)
  if (p.chat) {
    for (const c of p.chat) {
      EventBus.emit('chat-row', c)   // 导播跟随：只读对话面板实时追加（含 event 行）
      if (c.kind === 'message' && c.from_entity_id && c.content) {
        s.pushBubble(c.from_entity_id, c.content)
        EventBus.emit('chat-message', { entityId: c.from_entity_id, content: c.content, roomId: c.chat_room_id, fromName: c.from_name })
      }
    }
  }
}

/**
 * 世界数据通道：首选 B17 `GET /ws/world`（snapshot + patch），
 * 连不上 / 断开 / 15 s 没消息 → 立刻退回 `GET /world?fields=players,objects,worldState` 500 ms 轮询，
 * 同时按退避重试 ws；ws 一旦重新收到 snapshot 就停掉轮询。两条路都只读。
 */
export function startWorldFeed(opts: { preferWs?: boolean } = {}): WorldFeedHandle {
  const preferWs = opts.preferWs ?? true
  let stopped = false
  let ws: WebSocket | null = null
  let poller: PollerHandle | null = null
  let transport: 'ws' | 'poll' | 'none' = 'none'
  let retryMs = WS_RETRY_MIN
  let retryTimer: number | null = null
  let idleTimer: number | null = null
  let connectTimer: number | null = null
  let lastMapKey = useGameStore.getState().mapSig

  const setTransport = (t: typeof transport) => {
    if (t === transport) return
    transport = t
    useGameStore.getState().setTransport(t)
  }

  // ── 轮询退路 ──
  const startPolling = () => {
    if (stopped || poller) return
    poller = startPoller({
      name: 'world-poll',
      intervalMs: POLL_WORLD_MS,
      fn: async () => {
        const live = await fetchWorldLive()
        const s = useGameStore.getState()
        const key = live.worldState?.mapVersion
        if (live.tiles && live.tiles.length > 0) {
          // 老后端不认 ?fields，回的是全量
          applyWorldSnapshot(live)
        } else {
          s.setWorldState(live.worldState)
          s.setObjects(live.objects)
          s.setPlayers(live.players ?? [])
          s.setConnection('online')
          if (key && key !== lastMapKey) {
            lastMapKey = key
            const full = await fetchWorld()
            applyWorldSnapshot(full)
          }
        }
      },
      onError: (err, n) => {
        useGameStore.getState().setConnection('offline')
        if (n === 1 || n % 10 === 0) console.warn('[WorldFeed] poll failed', n, err)
      },
    })
    setTransport('poll')
  }
  const stopPolling = () => { poller?.stop(); poller = null }

  // ── ws ──
  const clearTimers = () => {
    if (idleTimer !== null) { window.clearTimeout(idleTimer); idleTimer = null }
    if (connectTimer !== null) { window.clearTimeout(connectTimer); connectTimer = null }
  }
  const armIdle = () => {
    if (idleTimer !== null) window.clearTimeout(idleTimer)
    idleTimer = window.setTimeout(() => {
      console.warn('[WorldFeed] ws idle > 15 s, dropping')
      ws?.close()
    }, WS_IDLE_MS)
  }
  const scheduleRetry = () => {
    if (stopped || retryTimer !== null) return
    retryTimer = window.setTimeout(() => { retryTimer = null; connect() }, retryMs)
    retryMs = Math.min(WS_RETRY_MAX, retryMs * 2)
  }
  const onDown = () => {
    clearTimers()
    ws = null
    if (stopped) return
    startPolling()          // 退回轮询（同步，< 1 帧）
    scheduleRetry()
  }

  const connect = () => {
    if (stopped || ws) return
    let sock: WebSocket
    try { sock = new WebSocket(wsUrl()) } catch (e) { console.warn('[WorldFeed] ws ctor failed', e); onDown(); return }
    ws = sock
    connectTimer = window.setTimeout(() => { if (sock.readyState !== WebSocket.OPEN) sock.close() }, WS_CONNECT_MS)
    sock.onopen = () => { if (connectTimer !== null) { window.clearTimeout(connectTimer); connectTimer = null }; armIdle() }
    sock.onmessage = (ev) => {
      armIdle()
      let msg: WsMessage
      try { msg = JSON.parse(ev.data as string) } catch { return }
      switch (msg.type) {
        case 'snapshot':
          applyWorldSnapshot(msg)
          lastMapKey = mapKey(msg)
          retryMs = WS_RETRY_MIN
          stopPolling()
          setTransport('ws')
          break
        case 'patch':
          applyPatch(msg)
          useGameStore.getState().setConnection('online')
          break
        case 'action':
          EventBus.emit('action-event', msg)
          break
        case 'qq':
          EventBus.emit('qq-event', msg)
          break
        case 'thought': {   // B v1.3.19：{type:"thought", entity|player_id|id, text, kind, game_time}
          const m = msg
          const who = m.entity ?? m.player_id ?? m.id
          const text = m.text ?? m.thought?.text
          if (who && typeof text === 'string') useGameStore.getState().setPlayerThought(who, { text, kind: m.kind ?? m.thought?.kind ?? null, game_time: m.game_time ?? m.thought?.game_time ?? null })
          EventBus.emit('thought-event', msg)
          break
        }
        case 'lesson': {   // world-v1.4.0：{event: start|segment|question|doze|end|grade, lesson_id, entity?}；doze 先把他标睡着（下一个 upsert 会再校正）
          const m = msg
          if (m.event === 'doze' && typeof m.entity === 'string') {
            const cur = useGameStore.getState().players.find(p => p.id === m.entity)
            if (cur?.lesson) useGameStore.getState().patchPlayers([{ ...cur, lesson: { ...cur.lesson, dozing: true } }], undefined)
          }
          EventBus.emit('lesson-event', m)
          break
        }
        case 'produce':
          EventBus.emit('produce-event', msg)
          break
        case 'commission':
          EventBus.emit('commission-event', msg)
          break
        case 'knock':
          EventBus.emit('knock-event', msg)
          break
        case 'door':
          EventBus.emit('door-event', msg)
          break
        case 'eat_done': case 'eat_cancelled': case 'spoiled': case 'daily_limit': case 'rent': case 'cook_cancelled':   // world-v1.1（B 11-13）：先分发，面板 / 气泡等 -a 上 bench 后接
          EventBus.emit(`${msg.type}-event`, msg)
          break
        case 'heartbeat':
          break
      }
    }
    sock.onerror = () => { /* onclose 跟着来 */ }
    sock.onclose = () => { if (ws === sock) onDown() }
  }

  if (preferWs && typeof WebSocket !== 'undefined') {
    startPolling()          // 先用轮询把画面撑起来，ws snapshot 一到就切
    connect()
  } else {
    startPolling()
  }

  return {
    stop: () => {
      stopped = true
      if (retryTimer !== null) window.clearTimeout(retryTimer)
      clearTimers()
      stopPolling()
      const s = ws; ws = null; s?.close()
      setTransport('none')
    },
    get transport() { return transport },
  }
}
