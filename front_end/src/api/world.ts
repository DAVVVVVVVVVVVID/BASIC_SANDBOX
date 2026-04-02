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

export async function interactWith(playerId: string) {
  const res = await fetch(`${API_BASE}/action/interact`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ playerId }),
  })
  if (!res.ok) throw new Error(`POST /action/interact failed: ${res.status}`)
  return res.json()
}

export async function turnPlayer(playerId: string, direction: string) {
  const res = await fetch(`${API_BASE}/action/turn`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ playerId, direction }),
  })
  if (!res.ok) throw new Error(`POST /action/turn failed: ${res.status}`)
  return res.json()
}

export async function movePlayer(
  playerId: string,
  params: { direction?: string; targetTile?: { x: number; y: number } },
) {
  const res = await fetch(`${API_BASE}/action/move`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ playerId, ...params }),
  })
  if (!res.ok) throw new Error(`POST /action/move failed: ${res.status}`)
  return res.json()
}
