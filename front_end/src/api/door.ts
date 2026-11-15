import { apiPost } from './client'
import { sendAction } from './world'

/** §3.41（api-spec §11）：屋内任何人隔门回一句（text）或拒绝（decline）。开门不走这里——站到门内侧 open_door */
export function respondKnock(requestId: string, entityId: string, reply: { text: string } | { decline: true }) {
  return apiPost<{ success: boolean; reason?: string | null; request?: { id: string; status: string } }>('/door/respond', { request_id: requestId, entity_id: entityId, ...reply })
}
/** §3.41 在上锁的家门外（≤ 2 格）敲门：成功 result {request_id, expires_at, notified[]}；失败 has_key / not_a_home / too_far / already_knocking / already_inside / walking */
export function knockDoor(entityId: string, doorId: string) {
  return sendAction(entityId, 'knock', { door_id: doorId }, { logLabel: '敲门' }) as unknown as Promise<{ success: boolean; reason?: string | null; result?: { message?: string; request_id?: string; expires_at?: string; notified?: string[]; door?: { name?: string } } }>
}
/** 站在门内侧格或其相邻格开门，敞开 60 游戏秒；失败 not_inside_door 带 result.inside{x,y} */
export function openDoor(entityId: string, doorId: string) {
  return sendAction(entityId, 'open_door', { door_id: doorId }, { logLabel: '开门' }) as unknown as Promise<{ success: boolean; reason?: string | null; result?: { message?: string; inside?: { x: number; y: number }; name?: string; open_until?: string } }>
}
