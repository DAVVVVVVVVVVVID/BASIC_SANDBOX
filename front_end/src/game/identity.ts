import type { Player } from '../types'

/** 常驻阿蝉：players[] 里 agent_id === achan 的那个（不限 controller，B 可能以 human 常驻在 achan_room）；没有就 null → 新建 */
export function findResidentAchan(players: Player[] | undefined | null): Player | null {
  if (!Array.isArray(players)) return null
  return players.find(p => p && p.agent_id === 'achan') ?? players.find(p => p && typeof p.profile?.name === 'string' && p.profile.name === '阿蝉') ?? null
}

export const ACHAN = { name: '阿蝉', agent_id: 'achan' } as const
