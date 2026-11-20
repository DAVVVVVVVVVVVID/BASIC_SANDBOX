/**
 * 小镇直播自动导播 · 打分器（whale docs/systems/town-director-plan.md §1，主播 11-20 拍板；纯函数，单测 tests/director.test.ts）。
 * 每 2 s 调一次 tick()：给每个候选打「看点分」，按停留 / 插播 / 锁定规则决定镜头跟谁，并给出情境（左侧面板用哪块）。
 * 阿蝉（agent_id achan / 人类）与路人不当候选；他们出现在别人画面里照常显示（那是渲染层的事）。
 */
export type Situation = 'chat' | 'trade' | 'event' | 'class' | 'create' | 'fishing' | 'qq' | 'walk' | 'idle' | 'sleep' | 'eat' | 'live' | 'panorama'

export interface Candidate {
  id: string
  name: string
  agentId?: string | null
  controller?: string | null
  role?: string | null
  /** C 的「现在在干嘛」activity（chat / trade / class / fishing / create / qq / walk / idle / sleep / live / eat / work / cook / shop）；没有时从下面的字段推 */
  activity?: string | null
  state?: string | null
  stateLabel?: string | null
  inChat?: boolean
  /** 当面对话里最近一句的墙钟毫秒（刚说出来 +20） */
  lastLineAt?: number | null
  /** 正在交易 / 点餐（店主和顾客都算） */
  trading?: boolean
  inClass?: boolean
  /** 上课时被点名 / 答题（+30） */
  classHot?: boolean
  /** 坐满 / 钓鱼 / 做稿的进度 0–1（> 0.8 +20） */
  progress?: number | null
  /** 走路去赴约（+20） */
  toMeet?: boolean
  /** 和阿蝉互动中（×1.2） */
  withAchan?: boolean
}
export interface DirectorEvent { who: string; at: number; label?: string }

export interface DirectorMemory {
  current: string | null
  since: number               // 切到 current 的时刻
  situation: Situation
  /** 插播：被插播前的人，插播结束切回 */
  insert: { id: string; until: number; back: string | null } | null
  lock: { id: string; until: number } | null
  /** 每人累计连续被看的起点（新鲜度用）：换人即清 */
  watchedSince: Record<string, number>
}
export const newMemory = (now = 0): DirectorMemory => ({ current: null, since: now, situation: 'panorama', insert: null, lock: null, watchedSince: {} })

export const RULES = {
  minStayMs: 20_000,
  maxStayMs: 180_000,
  insertMs: 15_000,
  eventWindowMs: 15_000,
  freshnessPerMin: 0.10,
  whaleBoost: 1.3,
  achanBoost: 1.2,
  /** 换人时下一个至少要有这个分（低于它宁可全景） */
  panoramaBelow: 10.5,
  /** 换人要比当前高出这么多（防抖） */
  switchMargin: 1.15,
}

const ACT_SITUATION: Record<string, Situation> = {
  chat: 'chat', trade: 'trade', shop: 'trade', work: 'trade', cook: 'trade', class: 'class', fishing: 'fishing', create: 'create',
  qq: 'qq', walk: 'walk', idle: 'idle', sleep: 'sleep', live: 'live', eat: 'eat',
}

export const isCandidate = (c: Pick<Candidate, 'agentId' | 'controller' | 'role' | 'name'>) =>
  c.agentId !== 'achan' && c.controller !== 'human' && c.role !== 'passerby' && c.controller !== 'script' && !/阿蝉/.test(c.name)

/** 从候选的字段推情境（C 的 activity 优先） */
export function situationOf(c: Candidate): Situation {
  if (c.inChat) return 'chat'
  if (c.trading) return 'trade'
  if (c.inClass) return 'class'
  const a = c.activity ? ACT_SITUATION[c.activity] : undefined
  if (a) return a
  const s = `${c.state ?? ''} ${c.stateLabel ?? ''}`
  if (/睡|sleep/i.test(s)) return 'sleep'
  if (/talk|聊/.test(s)) return 'chat'
  if (/钓/.test(s)) return 'fishing'
  if (/写歌|作曲|做稿|剪|创作|工作站|compose/.test(s)) return 'create'
  if (/上课|课/.test(s)) return 'class'
  if (/吃|用餐|eat/.test(s)) return 'eat'
  if (/直播|live/i.test(s)) return 'live'
  if (/手机|QQ/i.test(s)) return 'qq'
  if (/walk/.test(c.state ?? '')) return 'walk'
  return 'idle'
}

/** 单人看点分（不含新鲜度） */
export function baseScore(c: Candidate, now: number, events: DirectorEvent[]): { score: number; situation: Situation } {
  const hot = events.some(e => e.who === c.id && now - e.at <= RULES.eventWindowMs)
  const sit = situationOf(c)
  let score: number
  switch (sit) {
    case 'chat': score = 100 + (c.lastLineAt && now - c.lastLineAt < 4000 ? 20 : 0); break
    case 'trade': score = 80; break
    case 'class': score = 50 + (c.classHot ? 30 : 0); break
    case 'fishing': case 'create': score = 30 + ((c.progress ?? 0) > 0.8 ? 20 : 0); break
    case 'qq': score = 40; break
    case 'live': score = 60; break
    case 'eat': score = 20; break
    case 'walk': score = 15 + (c.toMeet ? 20 : 0); break
    case 'sleep': score = 3; break
    default: score = 10
  }
  if (hot && score < 90) score = 90
  if (c.agentId === 'whale') score *= RULES.whaleBoost
  if (c.withAchan) score *= RULES.achanBoost
  return { score, situation: hot && sit !== 'chat' && sit !== 'trade' ? 'event' : sit }
}

export interface TickResult { follow: string | null; situation: Situation; reason: string; scores: { id: string; name: string; score: number; situation: Situation }[] }

/** 每 2 s 调一次。memory 原地更新。 */
export function tick(cands: Candidate[], events: DirectorEvent[], mem: DirectorMemory, now: number): TickResult {
  const pool = cands.filter(isCandidate)
  const scored = pool.map(c => {
    const b = baseScore(c, now, events)
    const ws = mem.watchedSince[c.id]
    const mins = c.id === mem.current && ws !== undefined ? (now - ws) / 60000 : 0
    const fresh = Math.max(0.3, 1 - RULES.freshnessPerMin * Math.floor(mins))
    return { id: c.id, name: c.name, score: Math.round(b.score * fresh * 10) / 10, situation: b.situation }
  }).sort((a, b) => b.score - a.score)
  const byId = new Map(scored.map(s => [s.id, s]))
  const switchTo = (id: string | null, situation: Situation, reason: string): TickResult => {
    if (id !== mem.current) { mem.current = id; mem.since = now; mem.watchedSince = id ? { [id]: now } : {} }
    mem.situation = situation
    return { follow: id, situation, reason, scores: scored }
  }
  const stay = (reason: string): TickResult => {
    const cur = mem.current ? byId.get(mem.current) : undefined
    mem.situation = cur?.situation ?? (mem.current ? mem.situation : 'panorama')
    return { follow: mem.current, situation: mem.situation, reason, scores: scored }
  }

  // 1. 手动锁定永远优先
  if (mem.lock && now < mem.lock.until && byId.has(mem.lock.id)) return switchTo(mem.lock.id, byId.get(mem.lock.id)!.situation, '手动锁定')
  if (mem.lock && now >= mem.lock.until) mem.lock = null

  // 2. 插播进行中 / 结束切回
  if (mem.insert) {
    if (now < mem.insert.until) return stay('插播中')
    const back = mem.insert.back; mem.insert = null
    if (back && byId.has(back)) return switchTo(back, byId.get(back)!.situation, '插播结束，切回')
  }

  const top = scored[0]
  // 全镇都在发呆 / 睡觉（按情境判，不按分数：鲸仔发呆 ×1.3 也算安静）→ 全景
  if (!top || scored.every(s => s.situation === 'idle' || s.situation === 'sleep')) return switchTo(null, 'panorama', '全镇安静，全景')

  const cur = mem.current ? byId.get(mem.current) : undefined
  if (!cur) return switchTo(top.id, top.situation, '开始')
  const stayed = now - mem.since
  const busy = cur.situation === 'chat' || cur.situation === 'trade'

  // 3. 瞬时事件插播（别人身上刚发生，当前不在对话 / 交易里）
  const ev = [...events].reverse().find(e => e.who !== cur.id && now - e.at <= 2500 && byId.has(e.who))
  if (ev && !busy) {
    mem.insert = { id: ev.who, until: now + RULES.insertMs, back: cur.id }
    return switchTo(ev.who, 'event', `插播：${ev.label ?? '事件'}`)
  }

  // 4. 最长停留到点：优先换人
  if (stayed >= RULES.maxStayMs && !busy) {
    const next = scored.find(s => s.id !== cur.id)
    if (next && next.score > RULES.panoramaBelow) return switchTo(next.id, next.situation, '停留到 3 分钟，换人')
  }
  // 5. 最短停留 / 对话交易中不切
  if (stayed < RULES.minStayMs) return stay('最短停留中')
  if (busy) return stay(cur.situation === 'chat' ? '对话进行中' : '交易进行中')
  // 6. 明显更好看才换（防抖）
  if (top.id !== cur.id && top.score > cur.score * RULES.switchMargin) return switchTo(top.id, top.situation, `换到更好看的（${top.score} > ${cur.score}）`)
  return stay('保持')
}

/** 导播台：锁定某人 N 分钟（手动优先）；id = null 解锁 */
export function lockOn(mem: DirectorMemory, id: string | null, minutes: number, now: number) {
  mem.lock = id ? { id, until: now + minutes * 60000 } : null
  mem.insert = null
}
