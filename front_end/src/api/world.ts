import { apiGet, apiPost, apiDelete, apiGetOrNull } from './client'
import type { Player, PlayerStateVars, WorldData, WorldEvent, ActionLogEntry, WorldState } from '../types'

export const fetchEvents  = () => apiGet<WorldEvent[]>('/events')
/** B world-v1.3.19：players[].last_thought 只在 `view=admin` 时带出——操控页（导播视角）开，旁观 / 直播不开 */
let adminView = false
export function setAdminView(on: boolean) { adminView = on }
const av = (sep: '?' | '&') => (adminView ? `${sep}view=admin` : '')
export const fetchWorld   = () => apiGet<WorldData>(`/world${av('?')}`)
/** W5 瘦身：只要动态部分（约 10 KB）；老后端忽略 query 回全量，调用方按 tiles 是否为空判断 */
export const fetchWorldLive = () => apiGet<WorldData>(`/world?fields=players,objects,worldState${av('&')}`)
export const fetchHistory = () => apiGet<ActionLogEntry[]>('/history')

export function joinPlayer(name: string) {
  return apiPost<{ playerId: string; player: Player }>('/player/join', { name, controller: 'human' })
}

/** world-v1.3 §12.12：以某个身份（agent_id）加入——账号 / 钥匙 / 家 / QQ 按该身份算；阿蝉缺省 dnd 开，接管时显式关 */
export function joinAs(name: string, agentId: string, dnd?: boolean) {
  return apiPost<{ playerId: string; player: Player }>('/player/join', { name, controller: 'human', profile: { agent_id: agentId }, ...(dnd === undefined ? {} : { dnd }) })
}

/** 只拉 players[]（找常驻的阿蝉用） */
export const fetchPlayersLite = () => apiGet<{ players?: Player[] }>(`/world?fields=players${av('&')}`)
/** 导播视角慢轮询：只拉 players 的 last_thought（ws 通道里的 snapshot 不带它） */
export const fetchThoughts = () => apiGet<{ players?: { id: string; last_thought?: import('../types').PlayerThought | null }[] }>('/world?fields=players&view=admin')

/** world-v1.3：勿扰开关（主播接管时关、离开时开） */
export function setDnd(playerId: string, on: boolean) {
  return apiPost<{ ok: boolean; playerId: string; dnd: boolean; tags: string[] }>(`/admin/player/${encodeURIComponent(playerId)}/dnd`, { on })
}

/** 页面关闭时发（keepalive，不等响应）：主播离开 → 阿蝉勿扰归位；不删人 */
export function setDndOnUnload(playerId: string, on: boolean) {
  const base = (import.meta.env.VITE_API_BASE as string | undefined) || '/api'
  const url = `${base}/admin/player/${encodeURIComponent(playerId)}/dnd`
  const body = JSON.stringify({ on })
  try {
    if (typeof navigator !== 'undefined' && navigator.sendBeacon && navigator.sendBeacon(url, new Blob([body], { type: 'application/json' }))) return
  } catch { /* fall through */ }
  try { void fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, keepalive: true }) } catch { /* ignore */ }
}

export function rejoinPlayer(playerId: string) {
  return apiPost<{ playerId: string; player: Player }>('/player/rejoin', { playerId })
}

export async function leavePlayer(playerId: string) {
  try { await apiDelete(`/player/${encodeURIComponent(playerId)}/leave`) } catch { /* ignore */ }
}

/** 刷新心跳并取完整状态；404（后端清掉了该 player）返回 null */
export const fetchPlayer = (playerId: string) =>
  apiGetOrNull<Player>(`/player/${encodeURIComponent(playerId)}`)

/** B13 只读接口：七变量原始数值，不刷心跳、不清 pendingMessage（旁观模式用它） */
export const fetchPlayerState = (playerId: string) =>
  apiGetOrNull<PlayerStateVars>(`/player/${encodeURIComponent(playerId)}/state`)

export const timeToggle = () => apiPost<Partial<WorldState>>('/time/toggle')
export const timeSpeed  = (value: number) => apiPost<{ speed: number }>('/time/speed', { value })
export const timeReset  = () => apiPost<Partial<WorldState>>('/time/reset')

export interface ActionResponse {
  success: boolean
  type: string
  reason?: string | null
  result?: Record<string, unknown> & {
    facing?: import('../types').Facing
    position?: import('../types').Position
    message?: string
    currentUsers?: number
    maxUsers?: number
    cooldownRemaining?: number
  }
}

/** 走到某个区域里离自己最近的可走格（后端 BFS）；阿蝉操控台「走到鲸仔旁」用 */
export const moveToArea = (entityId: string, areaId: string) =>
  sendAction(entityId, 'move_to_area', { area_type: 'arena', area_id: areaId }, { logLabel: `前往 ${areaId}` })

export function sendAction(
  entityId: string,
  type: string,
  payload: Record<string, unknown> = {},
  options: { skipLog?: boolean; logLabel?: string } = {},
) {
  return apiPost<ActionResponse>('/action', {
    entityId,
    action: { type, payload },
    skipLog:  options.skipLog  ?? false,
    logLabel: options.logLabel ?? null,
  })
}
