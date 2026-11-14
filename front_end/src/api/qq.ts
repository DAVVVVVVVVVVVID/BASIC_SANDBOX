import { apiGet, apiPost, ApiError } from './client'

/**
 * W9：QQ（沙盒内手机消息）接口客户端。B 的 W10 交接只给了端点名：
 *   POST /qq/send（text 或文件物品引用，实物拒绝）、GET /qq/inbox?player=&since=、POST /qq/read（占 1 游戏分钟 reading 标签）、GET /qq/contacts
 *   ws 推 `qq` 事件；perceive 加 phone.unread
 * 字段名是**假设**，这里对几种常见写法都宽容解析；B 的 api-spec 落地后对齐（见 WHALE_REPORT W9 §假设）。
 */
export interface QQContact { id: string; name: string; group: boolean; members?: string[]; unread: number }
export interface QQMessage {
  id: string; ts: string; from: string; fromName?: string
  to?: string | null; group?: string | null
  kind: 'text' | 'file'; text?: string; file?: { ref?: string; name?: string; type?: string } | null
  readAt?: string | null
  /** 后端给的方向：in = 发给我，out = 我发的。from / to 是 QQ 账号（achan / whale），不是 entity id，会话过滤靠它 */
  direction?: 'in' | 'out'
}

const str = (v: unknown, d = '') => (v === null || v === undefined ? d : String(v))
const obj = (v: unknown) => (v && typeof v === 'object' ? (v as Record<string, unknown>) : {})

export function normalizeMessage(raw: unknown): QQMessage | null {
  const r = obj(raw); if (!r || Object.keys(r).length === 0) return null
  const inner = r.message && typeof r.message === 'object' ? obj(r.message) : r
  const file = inner.file ?? inner.file_ref ?? inner.item ?? null
  const kind: 'text' | 'file' = (inner.kind === 'file' || (!!file && inner.kind !== 'text')) ? 'file' : 'text'
  return {
    id: str(inner.id ?? inner.msg_id ?? `${inner.ts}-${inner.from}`),
    ts: str(inner.ts ?? inner.timestamp ?? inner.time),
    from: str(inner.from ?? inner.from_id ?? inner.sender ?? inner.from_entity_id),
    fromName: typeof (inner.from_name ?? inner.fromName ?? inner.sender_name) === 'string' ? str(inner.from_name ?? inner.fromName ?? inner.sender_name) : undefined,
    to: inner.to !== undefined && inner.to !== null ? str(inner.to ?? inner.to_id) : null,
    group: inner.group !== undefined && inner.group !== null ? str(inner.group ?? inner.group_id) : null,
    kind,
    text: typeof inner.text === 'string' ? inner.text : typeof inner.content === 'string' ? inner.content : undefined,
    file: file ? (typeof file === 'string' ? { ref: file } : { ref: str(obj(file).ref ?? obj(file).id ?? obj(file).file_ref), name: str(obj(file).name, ''), type: str(obj(file).type ?? obj(file).item_type, '') }) : null,
    readAt: inner.read_at !== undefined ? (inner.read_at === null ? null : str(inner.read_at)) : inner.readAt !== undefined ? str(inner.readAt) : undefined,
    direction: inner.direction === 'in' || inner.direction === 'out' ? inner.direction : undefined,
  }
}

export function normalizeContacts(raw: unknown): QQContact[] {
  const r = obj(raw)
  const list = Array.isArray(raw) ? raw : Array.isArray(r.contacts) ? r.contacts : []
  const groups = Array.isArray(r.groups) ? r.groups : []
  const out: QQContact[] = []
  for (const c of list) {
    const o = obj(c)
    out.push({ id: str(o.id ?? o.entity_id ?? o.player_id ?? o.name), name: str(o.name ?? o.id), group: !!(o.group || o.is_group || o.members), members: Array.isArray(o.members) ? o.members.map(String) : undefined, unread: Number(o.unread ?? 0) || 0 })
  }
  for (const g of groups) {
    const o = obj(g)
    out.push({ id: str(o.id ?? o.group_id ?? o.name), name: str(o.name ?? o.id), group: true, members: Array.isArray(o.members) ? o.members.map(String) : undefined, unread: Number(o.unread ?? 0) || 0 })
  }
  return out
}

export async function fetchContacts(playerId: string): Promise<QQContact[] | null> {
  try { return normalizeContacts(await apiGet<unknown>(`/qq/contacts?player=${encodeURIComponent(playerId)}`)) }
  catch (e) { if (e instanceof ApiError && (e.status === 404 || e.status === 405)) return null; throw e }
}

/** 收件箱。后端默认 limit=100 且按时间升序——历史 > 100 条时新消息会被截掉（11-15 主播：5 条未读点开看不到），所以按 peer 取 + 放大 limit */
export async function fetchInbox(playerId: string, since?: string | null, opts: { peer?: string | null; limit?: number } = {}): Promise<QQMessage[] | null> {
  try {
    const q = [`player=${encodeURIComponent(playerId)}`]
    if (since) q.push(`since=${encodeURIComponent(since)}`)
    if (opts.peer) q.push(`peer=${encodeURIComponent(opts.peer)}`)
    q.push(`limit=${opts.limit ?? 500}`)
    const raw = await apiGet<unknown>(`/qq/inbox?${q.join('&')}`)
    const r = obj(raw)
    const list = Array.isArray(raw) ? raw : Array.isArray(r.messages) ? r.messages : Array.isArray(r.inbox) ? r.inbox : []
    return list.map(normalizeMessage).filter((m): m is QQMessage => !!m)
  } catch (e) { if (e instanceof ApiError && (e.status === 404 || e.status === 405)) return null; throw e }
}

/** 发文字；peer 是联系人 id 或群 id（group=true 时放 group 字段） */
export function sendText(from: string, peer: string, text: string, group = false) {
  return apiPost<unknown>('/qq/send', { from, [group ? 'group' : 'to']: peer, kind: 'text', text })
}
/** 发文件类物品（歌 / 文稿）：带背包物品引用；实物后端会拒 */
export function sendFile(from: string, peer: string, item: { id?: string; type: string; name?: string }, group = false) {
  // B 的 schema：file_ref 是对象 {item, name, meta}（字符串会 422）
  return apiPost<unknown>('/qq/send', { entity_id: from, [group ? 'group' : 'to']: peer, kind: 'file', text: item.name ? `发了「${item.name}」` : undefined, file_ref: { item: item.type, name: item.name ?? item.type, meta: item.id ? { id: item.id } : {} } })
}
/** 读某个会话（占用 1 游戏分钟，后端打 reading 标签） */
export function markRead(player: string, peer: string, group = false) {
  return apiPost<unknown>('/qq/read', { player, [group ? 'group' : 'from']: peer })
}
