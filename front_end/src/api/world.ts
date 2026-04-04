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

export async function fetchPlayer() {
  const res = await fetch(`${API_BASE}/player`)
  if (!res.ok) throw new Error(`GET /player failed: ${res.status}`)
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
