import { fetchWorld, fetchPlayer, fetchHistory, fetchPlayerState, joinPlayer } from '../../api/world'
import { useGameStore, mapSignature } from '../../store/gameStore'
import { EventBus } from '../EventBus'
import { startPoller } from './Poller'
import type { OtherPlayer } from '../../types'

/** 轮询节奏（ms）。/world 为主（已含 players），其余降频 */
export const POLL_WORLD_MS   = 500
export const POLL_PLAYER_MS  = 1000   // 也是心跳：人类 10 s 无心跳会被踢
export const POLL_HISTORY_MS = 2000
export const POLL_VARS_MS    = 1000

interface TickHandles { stop: () => void }


function applyWorld(world: Awaited<ReturnType<typeof fetchWorld>>) {
  const s = useGameStore.getState()
  s.setWorldState(world.worldState)
  s.setObjects(world.objects)
  // tiles 很大（几千条），只有地图签名变了才替换（后端换地图 / 重启），避免每轮全量重渲染
  if (mapSignature(world) !== s.mapSig) s.setMap(world.tiles, world.tiled)
  s.setPlayers(world.players ?? [])
  s.setConnection('online')
}

function markOffline(err: unknown, failures: number) {
  useGameStore.getState().setConnection('offline')
  if (failures === 1 || failures % 10 === 0) console.warn('[Tick] /world failed', failures, err)
}

/**
 * 操控模式：/world 500 ms（players、objects、worldState），/player/{id} 1 s（七变量 + 心跳 + 位置校正），/history 2 s。
 * 后端重启把 player 清掉（404）时用同名自动重新 join，不回登录框。
 */
export function startTickSystem(playerId: string, playerName: string): TickHandles {
  const store = useGameStore.getState()
  store.setMyPlayerId(playerId)
  let currentId = playerId
  let rejoinAt = 0

  const world = startPoller({
    name: 'world',
    intervalMs: POLL_WORLD_MS,
    fn: async () => { applyWorld(await fetchWorld()) },
    onError: markOffline,
  })

  const player = startPoller({
    name: 'player',
    intervalMs: POLL_PLAYER_MS,
    fn: async (sentAt) => {
      const p = await fetchPlayer(currentId)
      if (p === null) {
        // 后端重启 / 被清理：同名重新加入（每 3 s 最多一次）
        const now = performance.now()
        if (now - rejoinAt < 3000) return false
        rejoinAt = now
        const { playerId: newId, player: np } = await joinPlayer(playerName)
        currentId = newId
        useGameStore.getState().setMyPlayerId(newId)
        useGameStore.getState().setPlayer(np)
        EventBus.emit('player-rejoined', { playerId: newId, player: np })
        return true
      }
      useGameStore.getState().setPlayer(p)
      EventBus.emit('player-snapshot', { player: p, sentAt })
      if (p.pendingMessage) EventBus.emit('show-interaction', { message: p.pendingMessage })
    },
    onError: (err, n) => { if (n === 1) console.warn('[Tick] /player failed', err) },
  })

  const history = startPoller({
    name: 'history',
    intervalMs: POLL_HISTORY_MS,
    fn: async () => { useGameStore.getState().setActionLog(await fetchHistory()) },
  })

  return {
    stop: () => { world.stop(); player.stop(); history.stop() },
  }
}

/**
 * 旁观模式：只发 GET。/world 500 ms；跟随目标的七变量用只读 /player/{id}/state（不刷心跳、不把离线 agent 标回在线）。
 * follow 可以是 playerName、player id 或 agent_id（agent_id 要靠 /state 解析）。
 */
export function startSpectateTick(getTargetIds: () => string[]): TickHandles {
  const world = startPoller({
    name: 'world',
    intervalMs: POLL_WORLD_MS,
    fn: async () => { applyWorld(await fetchWorld()) },
    onError: markOffline,
  })

  const vars = startPoller({
    name: 'vars',
    intervalMs: POLL_VARS_MS,
    fn: async () => {
      const ids = getTargetIds()
      const s = useGameStore.getState()
      // 清掉已不在场的
      for (const id of Object.keys(s.playerVars)) if (!ids.includes(id)) s.setPlayerVars(id, null)
      await Promise.all(ids.map(async id => {
        const v = await fetchPlayerState(id)
        useGameStore.getState().setPlayerVars(id, v)
      }))
    },
  })

  return { stop: () => { world.stop(); vars.stop() } }
}

export function resolveFollowTarget(players: OtherPlayer[], follow: string | null): OtherPlayer | null {
  if (!follow) return null
  const s = useGameStore.getState()
  const byId = players.find(p => p.id === follow)
  if (byId) return byId
  const byName = players.filter(p => p.name === follow)
  if (byName.length > 0) return byName.find(p => p.online !== false) ?? byName[0]
  // agent_id：在已拉到的 /state 里找
  for (const [id, v] of Object.entries(s.playerVars)) {
    if (v.agent_id === follow) {
      const p = players.find(x => x.id === id)
      if (p) return p
    }
  }
  return null
}
