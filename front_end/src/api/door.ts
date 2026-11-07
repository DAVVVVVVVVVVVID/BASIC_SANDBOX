import { apiPost } from './client'

/** §3.40 敲门（api-spec §11）：主人回应访客的敲门。只限这家的主人（not_owner）；请求须 pending（not_pending:<status>） */
export function respondKnock(requestId: string, entityId: string, accept: boolean) {
  return apiPost<{ success: boolean; reason?: string | null; request?: { id: string; status: string; responded_by?: string | null } }>('/door/respond', { request_id: requestId, entity_id: entityId, accept })
}
