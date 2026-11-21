/**
 * 直播「游戏」模式信息层（总控 11-19，live-modes-plan §3；G 的 iframe 显示块）——D 的 GET /game/state → 显示数据（纯函数；单测 tests/gameOverlay.test.ts）。
 * 只读、只排版：判断 / 怀疑度 / 投票都照 D 给的显示，前端不推断。
 */
export interface GameCheck { item?: string; result?: string; evidence?: string }
export interface GameDecision { id?: number; visitor?: string; verdict?: string; confidence?: number; source?: string; correct?: number | boolean | null }
export interface GameState {
  session?: string; game?: string; status?: string; paused?: boolean; blocked?: unknown; mock?: boolean
  screen?: string; summary?: string
  visitor?: { name?: string; apartment?: string; appearance?: string } | null
  checks?: GameCheck[]; verdict?: string; suspicion?: number; confidence?: number; lead?: string
  votes?: { admit?: number; reject?: number } | null
  decisions?: GameDecision[]
}

export const BLOCKS = ['visitor', 'checks', 'verdict', 'votes', 'score'] as const
export type Block = typeof BLOCKS[number]

export interface CheckRow { icon: '✓' | '✗' | '？'; tone: 'ok' | 'bad' | 'unknown'; item: string; evidence: string }
export interface GameView {
  live: boolean                       // 有可显示的一局（running 或 paused）
  statusNote: string | null           // 暂停 / 卡住 等提示
  visitor: { name: string; apartment: string; appearance: string } | null
  checks: CheckRow[]
  verdict: { label: string; tone: 'admit' | 'reject' | 'none' }
  suspicion: number | null            // 0–1
  lead: string
  votes: { admit: number; reject: number; total: number } | null
  score: { correct: number; wrong: number } | null
  summary: string | null              // 结算 / 非核对画面时的一句话
}

const VERDICT: Record<string, { label: string; tone: 'admit' | 'reject' | 'none' }> = {
  admit: { label: '放行', tone: 'admit' }, reject: { label: '拒绝', tone: 'reject' },
}
const clamp01 = (x: unknown) => (typeof x === 'number' && isFinite(x) ? Math.max(0, Math.min(1, x)) : null)

/**
 * 卡片提示（总控 11-21：主播彩排时看到游戏窗口不在前台也显示「卡住了」，改为按原因显示）。
 * D：blocked 是字符串，没卡住是 null；paused_by_api 时 paused 一定为 true。
 */
export function blockedNote(s: Pick<GameState, 'paused' | 'status' | 'blocked'>): string | null {
  const b = typeof s.blocked === 'string' ? s.blocked : s.blocked ? String(s.blocked) : ''
  if (s.paused || s.status === 'paused' || b === 'paused_by_api' || b === 'bridge_paused') return '暂停中'   // bridge_paused：主播 F10
  if (b === 'game_not_foreground') return '等游戏窗口回来'
  if (b.startsWith('live_mode=') || b === 'live_paused_or_achan') return '稍等一下'   // 不在游戏模式 / 直播暂停或阿蝉在说话
  return b ? '卡住了' : null
}

export function deriveGameView(s: GameState | null | undefined): GameView {
  const empty: GameView = { live: false, statusNote: null, visitor: null, checks: [], verdict: { label: '还在看', tone: 'none' }, suspicion: null, lead: '', votes: null, score: null, summary: null }
  if (!s || (s.status !== 'running' && s.status !== 'paused')) return empty
  const checks: CheckRow[] = (Array.isArray(s.checks) ? s.checks : []).map(c => {
    const r = String(c.result ?? '')
    const tone = r === 'match' ? 'ok' : r === 'mismatch' ? 'bad' : 'unknown'
    return { icon: tone === 'ok' ? '✓' : tone === 'bad' ? '✗' : '？', tone, item: String(c.item ?? ''), evidence: String(c.evidence ?? '') }
  })
  const v = s.visitor && (s.visitor.name || s.visitor.apartment) ? { name: String(s.visitor.name ?? ''), apartment: String(s.visitor.apartment ?? ''), appearance: String(s.visitor.appearance ?? '') } : null
  const va = Number(s.votes?.admit ?? 0) || 0, vr = Number(s.votes?.reject ?? 0) || 0
  const graded = (Array.isArray(s.decisions) ? s.decisions : []).filter(d => d.correct !== null && d.correct !== undefined)
  const correct = graded.filter(d => d.correct === 1 || d.correct === true).length
  const inspecting = checks.length > 0 || !!v
  return {
    live: true,
    statusNote: blockedNote(s),
    visitor: inspecting ? v : null,
    checks: inspecting ? checks : [],
    verdict: VERDICT[String(s.verdict ?? '')] ?? { label: '还在看', tone: 'none' },
    suspicion: inspecting ? clamp01(s.suspicion) : null,
    lead: String(s.lead ?? ''),
    votes: s.votes ? { admit: va, reject: vr, total: va + vr } : null,
    score: graded.length ? { correct, wrong: graded.length - correct } : null,
    summary: !inspecting && s.summary ? String(s.summary) : null,
  }
}

/**
 * 游戏舞台 · 档案风（主播 11-21 选定方案 e；layout=stage 全屏透明，标题 + 底部四张卡）。
 * 标题：「今晚当门卫 · 第 N 天 · 第 M 位访客」；没在玩只显示「今晚当门卫」。天数 / 访客序号照 D 的 /game/state 给的显示。
 * 战绩四格：放对 / 拒对 / 放错 / 拒错 + 待定，取 D 的 today（白天多半是待定，结算后才揭晓）。
 */
export interface Quad { admitOk: number; rejectOk: number; admitBad: number; rejectBad: number; pending: number }
export interface StageInfo { title: { day: number | null; visitor: number | null } | null; quad: Quad; anomaly: string | null }
type StageState = GameState & { day?: unknown; visitor_no?: unknown; today?: Record<string, unknown> | null; anomalies?: unknown }
const posInt = (x: unknown) => (typeof x === 'number' && Number.isFinite(x) && x > 0 ? Math.floor(x) : null)
const cnt = (x: unknown) => (typeof x === 'number' && Number.isFinite(x) && x > 0 ? Math.floor(x) : 0)
/** D 11-21：day / visitor_no（0 = 门口没人且今天没判过）/ today{admit_right, reject_right, admit_wrong, reject_wrong, unknown} / anomalies[] */
export function stageInfo(s: StageState | null | undefined): StageInfo {
  const quad: Quad = { admitOk: 0, rejectOk: 0, admitBad: 0, rejectBad: 0, pending: 0 }
  const t = s?.today
  if (t && typeof t === 'object') {
    quad.admitOk = cnt(t.admit_right); quad.rejectOk = cnt(t.reject_right); quad.admitBad = cnt(t.admit_wrong); quad.rejectBad = cnt(t.reject_wrong); quad.pending = cnt(t.unknown)
  }
  const live = !!s && (s.status === 'running' || s.status === 'paused')
  const an = Array.isArray(s?.anomalies) ? (s!.anomalies as unknown[]).map(String).filter(Boolean) : []
  return { title: live ? { day: posInt(s!.day), visitor: posInt(s!.visitor_no) } : null, quad, anomaly: an[0] ?? null }
}
/** 核对行最多显示 n 条：对不上的先、她觉得怪的（anomalies，盖「!」）、还没查的其次、对上的最后（同类保持原顺序） */
export interface StageRow { tone: 'ok' | 'bad' | 'unknown' | 'warn'; item: string; evidence: string }
export function stageChecks(rows: StageRow[], n = 3): StageRow[] {
  const rank = { bad: 0, warn: 1, unknown: 2, ok: 3 } as const
  return rows.map((r, i) => ({ r, i })).sort((a, b) => rank[a.r.tone] - rank[b.r.tone] || a.i - b.i).slice(0, n).map(x => x.r)
}

/** URL：?view=game&blocks=checks,votes&layout=card|bar&theme=dark|cream&scale=1 */
export function parseOverlayParams(search: string): { blocks: Set<Block>; layout: 'card' | 'bar' | 'stage'; theme: 'dark' | 'cream'; scale: number; demo: boolean } {
  const q = new URLSearchParams(search)
  const raw = (q.get('blocks') ?? '').split(',').map(x => x.trim()).filter(Boolean)
  const blocks = new Set<Block>((raw.length ? raw : BLOCKS).filter((b): b is Block => (BLOCKS as readonly string[]).includes(b)))
  const scale = Number(q.get('scale') ?? '1')
  return {
    blocks,
    layout: q.get('layout') === 'bar' ? 'bar' : q.get('layout') === 'stage' ? 'stage' : 'card',
    theme: q.get('theme') === 'cream' ? 'cream' : 'dark',
    scale: isFinite(scale) && scale > 0.2 && scale < 4 ? scale : 1,
    demo: q.get('demo') === '1',
  }
}
export const isGameOverlayRoute = (search: string) => new URLSearchParams(search).get('view') === 'game'
