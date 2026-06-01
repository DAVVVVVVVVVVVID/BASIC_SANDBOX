const API_BASE = 'http://localhost:8000'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface NearbyPlayer {
  entity_id: string
  name: string
  arena_id: string
}

export interface PendingRequest {
  request_id: string
  from_entity_id: string
  from_name: string
  greeting: string
}

export interface RequestStatus {
  request_id: string
  status: string          // 'pending' | 'active' | 'rejected'
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

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`)
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`)
  return res.json()
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`POST ${path} failed: ${res.status}`)
  return res.json()
}

export const getNearby = (entityId: string) =>
  get<{ players: NearbyPlayer[] }>(`/chat/nearby?entity_id=${entityId}`)

export const sendRequest = (fromId: string, toIds: string[], greeting: string) =>
  post<{ request_id: string }>('/chat/request', {
    from_entity_id: fromId,
    to_entity_ids: toIds,
    greeting,
  })

export const getRequestStatus = (requestId: string) =>
  get<RequestStatus>(`/chat/request/${requestId}`)

export const getPending = (entityId: string) =>
  get<{ requests: PendingRequest[] }>(`/chat/pending?entity_id=${entityId}`)

export const respond = (entityId: string, requestId: string, accept: boolean, message: string) =>
  post<RespondResult>('/chat/respond', {
    entity_id: entityId,
    request_id: requestId,
    accept,
    message,
  })

export const getRoom = (roomId: string, entityId: string, sinceSeq: number) =>
  get<RoomData>(`/chat/room/${roomId}?entity_id=${entityId}&since_seq=${sinceSeq}`)

export const sendMessage = (entityId: string, roomId: string, content: string) =>
  post<{ seq: number }>('/chat/message', { entity_id: entityId, chat_room_id: roomId, content })

export const exitRoom = (entityId: string, roomId: string) =>
  post<unknown>('/chat/exit', { entity_id: entityId, chat_room_id: roomId })
