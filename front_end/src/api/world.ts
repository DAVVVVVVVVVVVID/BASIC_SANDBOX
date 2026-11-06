import { apiGet, apiPost, apiDelete, apiGetOrNull } from './client'
import type { Player, PlayerStateVars, WorldData, WorldEvent, ActionLogEntry, WorldState } from '../types'

export const fetchEvents  = () => apiGet<WorldEvent[]>('/events')
export const fetchWorld   = () => apiGet<WorldData>('/world')
/** W5 瘦身：只要动态部分（约 10 KB）；老后端忽略 query 回全量，调用方按 tiles 是否为空判断 */
export const fetchWorldLive = () => apiGet<WorldData>('/world?fields=players,objects,worldState')
export const fetchHistory = () => apiGet<ActionLogEntry[]>('/history')

export function joinPlayer(name: string) {
  return apiPost<{ playerId: string; player: Player }>('/player/join', { name, controller: 'human' })
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
