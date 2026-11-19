/**
 * 导播跟随「他今日的对话」分组（纯函数；单测 tests/followChat.test.ts）。
 * 总控 11-18：/history/chat 里 request_expired / request_rejected 等事件行 room_id 为 null，旧代码按 room_id 分组后 room.slice 抛错 → 整页黑屏。
 * 现在：有 room_id 的按房间分组；没有 room_id 的单列成「邀请未成」（过期 / 被拒）；ts / room 一律空值保护。
 */
export interface FollowChatRow { kind?: string; ts?: string | null; room_id?: string | null; event?: string | null; from?: string; participants?: string[]; text?: string }
export interface FollowRoom<R> { room: string; rs: R[]; active: boolean }
export interface FollowInvite { ts: string; event: string; label: string; participants: string[] }

export const INVITE_LABEL: Record<string, string> = { request_expired: '邀请过期', request_rejected: '邀请被拒', request_declined: '邀请被拒', request_cancelled: '邀请取消' }
const tsOf = (r: { ts?: string | null }) => (typeof r.ts === 'string' ? r.ts : '')

export function groupFollowRooms<R extends FollowChatRow>(rows: R[], activeRoom: string | null): { rooms: FollowRoom<R>[]; invites: FollowInvite[] } {
  const m = new Map<string, R[]>()
  const invites: FollowInvite[] = []
  for (const r of rows) {
    const room = typeof r.room_id === 'string' && r.room_id ? r.room_id : null
    if (!room) {
      if (r.kind === 'event') {
        const ev = String(r.event ?? '')
        invites.push({ ts: tsOf(r), event: ev, label: INVITE_LABEL[ev] ?? (ev || '邀请未成'), participants: Array.isArray(r.participants) ? r.participants : [] })
      }
      continue                                                  // 没房间的消息行（不该有）直接略过
    }
    const a = m.get(room) ?? []; a.push(r); m.set(room, a)
  }
  const closed = new Set(rows.filter(r => r.kind === 'event' && r.event === 'room_close' && r.room_id).map(r => r.room_id as string))
  const lastRoom = [...rows].reverse().find(r => r.room_id)?.room_id ?? null
  const rooms = [...m.entries()].map(([room, rs]) => ({
    room, rs,
    active: room === activeRoom || (!closed.has(room) && rs.some(r => r.kind === 'message') && room === lastRoom),
  })).sort((a, b) => Number(b.active) - Number(a.active) || tsOf(b.rs[b.rs.length - 1]).localeCompare(tsOf(a.rs[a.rs.length - 1])))
  invites.sort((a, b) => b.ts.localeCompare(a.ts))
  return { rooms, invites }
}
