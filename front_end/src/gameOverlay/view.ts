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
    statusNote: s.paused || s.status === 'paused' ? '暂停中' : s.blocked ? '卡住了，等人帮一下' : null,
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

/** URL：?view=game&blocks=checks,votes&layout=card|bar&theme=dark|cream&scale=1 */
export function parseOverlayParams(search: string): { blocks: Set<Block>; layout: 'card' | 'bar'; theme: 'dark' | 'cream'; scale: number; demo: boolean } {
  const q = new URLSearchParams(search)
  const raw = (q.get('blocks') ?? '').split(',').map(x => x.trim()).filter(Boolean)
  const blocks = new Set<Block>((raw.length ? raw : BLOCKS).filter((b): b is Block => (BLOCKS as readonly string[]).includes(b)))
  const scale = Number(q.get('scale') ?? '1')
  return {
    blocks,
    layout: q.get('layout') === 'bar' ? 'bar' : 'card',
    theme: q.get('theme') === 'cream' ? 'cream' : 'dark',
    scale: isFinite(scale) && scale > 0.2 && scale < 4 ? scale : 1,
    demo: q.get('demo') === '1',
  }
}
export const isGameOverlayRoute = (search: string) => new URLSearchParams(search).get('view') === 'game'
