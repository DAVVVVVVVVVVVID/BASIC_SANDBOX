import { apiGet, apiPost } from './client'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface NearbyPlayer {
  entity_id: string
  name: string
  arena_id: string
}

/** world-v1.4.6 §12.29：≤ 4 格内开着、我不在其中的房间（GET /chat/nearby.rooms[]）；can_join 与 POST /chat/join 同一判定 */
export interface NearbyRoom {
  chat_room_id: string
  participants: { entity_id: string; name: string }[]
  count: number
  last_message_preview: string | null
  can_join: boolean
  reason?: string
  message?: string
}
export interface JoinResult { success: boolean; chat_room_id?: string; participants?: { entity_id: string; name: string }[]; messages?: ChatMessage[]; last_seq?: number; my_count?: number; my_limit?: number | null; reason?: string; message?: string }

export interface PendingRequest {
  request_id: string
  from_entity_id: string
  from_name: string
  greeting: string
}

export interface RequestStatus {
  request_id: string
  status: string          // 'pending' | 'walking_over' | 'active' | 'rejected' | 'expired'
  chat_room_id: string | null
  accepted_ids: string[]
  rejected_ids: string[]
}

export interface RespondResult {
  status: string          // 'rejected' | 'waiting' | 'room_created'
  chat_room_id: string | null
}

export interface ChatMessage {
  seq: number
  from_entity_id: string
  from_name: string
  content: string
  timestamp?: string
}

export interface ChatRoomEvent {
  seq: number
  type: string
  entity_id: string
  name: string
}

export interface RoomData {
  status: string          // 'active' | 'closed'
  participants: string[]
  messages: ChatMessage[]
  events: ChatRoomEvent[]
}

// ─── API calls ────────────────────────────────────────────────────────────────

const get  = <T>(path: string) => apiGet<T>(path)
const post = <T>(path: string, body: unknown) => apiPost<T>(path, body)

/** W5 GET /history/chat：当日聊天 JSONL 回放（只读）。导播跟随的只读对话面板用，按 from / to / participants 过滤 */
export interface ChatHistoryRow { kind: 'message' | 'event'; ts: string; game_time?: string; room_id: string; seq?: number; from?: string; from_name?: string; to?: string[]; text?: string; event?: string; participants?: string[]; entity?: string; reason?: string }
export const getChatHistory = (since: string, limit = 500) => get<ChatHistoryRow[]>(`/history/chat?since=${encodeURIComponent(since)}&limit=${limit}`)
export const getNearby = (entityId: string) =>
  get<{ players: NearbyPlayer[]; rooms?: NearbyRoom[] }>(`/chat/nearby?entity_id=${encodeURIComponent(entityId)}`)

/** world-v1.4.6：中途加入（不需房内同意）；失败 {success:false, reason, message} 原样显示 */
export const joinRoom = (entityId: string, roomId: string, greeting?: string) =>
  post<JoinResult>('/chat/join', { entity_id: entityId, chat_room_id: roomId, ...(greeting ? { greeting } : {}) })

export const sendRequest = (fromId: string, toIds: string[], greeting: string) =>
  post<{ request_id: string }>('/chat/request', {
    from_entity_id: fromId,
    to_entity_ids: toIds,
    greeting,
  })

export const getRequestStatus = (requestId: string) =>
  get<RequestStatus>(`/chat/request/${requestId}`)

export const getPending = (entityId: string) =>
  get<{ requests: PendingRequest[] }>(`/chat/pending?entity_id=${encodeURIComponent(entityId)}`)

export const respond = (entityId: string, requestId: string, accept: boolean, message: string) =>
  post<RespondResult>('/chat/respond', {
    entity_id: entityId,
    request_id: requestId,
    accept,
    message,
  })

export const getRoom = (roomId: string, entityId: string, sinceSeq: number) =>
  get<RoomData>(`/chat/room/${roomId}?entity_id=${encodeURIComponent(entityId)}&since_seq=${sinceSeq}`)

export const sendMessage = (entityId: string, roomId: string, content: string) =>
  post<{ seq: number }>('/chat/message', { entity_id: entityId, chat_room_id: roomId, content })

export const exitRoom = (entityId: string, roomId: string) =>
  post<unknown>('/chat/exit', { entity_id: entityId, chat_room_id: roomId })
