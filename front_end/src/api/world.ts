const API_BASE = 'http://localhost:8000'

export async function fetchEvents() {
  const res = await fetch(`${API_BASE}/events`)
  if (!res.ok) throw new Error(`GET /events failed: ${res.status}`)
  return res.json()
}

export async function fetchWorld() {
  const res = await fetch(`${API_BASE}/world`)
  if (!res.ok) throw new Error(`GET /world failed: ${res.status}`)
  return res.json()
}

export async function joinPlayer(name: string) {
  const res = await fetch(`${API_BASE}/player/join`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  if (!res.ok) throw new Error(`POST /player/join failed: ${res.status}`)
  return res.json() as Promise<{ playerId: string; player: import('../types').Player }>
}

export async function leavePlayer(playerId: string) {
  await fetch(`${API_BASE}/player/${playerId}/leave`, { method: 'DELETE' })
}

export async function fetchPlayer(playerId: string) {
  const res = await fetch(`${API_BASE}/player/${playerId}`)
  if (res.status === 404) return null   // player 不存在（如后端重启后内存被清空）
  if (!res.ok) throw new Error(`GET /player/${playerId} failed: ${res.status}`)
  return res.json()
}

export async function fetchHistory() {
  const res = await fetch(`${API_BASE}/history`)
  if (!res.ok) throw new Error(`GET /history failed: ${res.status}`)
  return res.json()
}

export async function timeToggle() {
  const res = await fetch(`${API_BASE}/time/toggle`, { method: 'POST' })
  if (!res.ok) throw new Error(`POST /time/toggle failed: ${res.status}`)
  return res.json()
}

export async function timeSpeed(value: number) {
  const res = await fetch(`${API_BASE}/time/speed`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ value }),
  })
  if (!res.ok) throw new Error(`POST /time/speed failed: ${res.status}`)
  return res.json()
}

export async function timeReset() {
  const res = await fetch(`${API_BASE}/time/reset`, { method: 'POST' })
  if (!res.ok) throw new Error(`POST /time/reset failed: ${res.status}`)
  return res.json()
}

export async function sendAction(
  entityId: string,
  type: string,
  payload: Record<string, unknown> = {},
  options: { skipLog?: boolean; logLabel?: string } = {},
) {
  const res = await fetch(`${API_BASE}/action`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      entityId,
      action: { type, payload },
      skipLog:  options.skipLog  ?? false,
      logLabel: options.logLabel ?? null,
    }),
  })
  if (!res.ok) throw new Error(`POST /action failed: ${res.status}`)
  return res.json()
}
