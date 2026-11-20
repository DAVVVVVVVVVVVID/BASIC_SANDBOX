import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { useGameStore } from '../store/gameStore'
import { apiGetOrNull } from '../api/client'
import { SHOP_ASSET } from '../ui/shop/shopSkin'
import { godotCharKeyFor } from '../game/godotChars'
import QQPanel from '../ui/QQPanel'
import { createKind, createProgress, latestWork, todaySummaryRows, type CreateBase } from './phase3'
import type { OtherPlayer } from '../types'

/**
 * 导播情境面板 · 三期（town-director-plan §2）：上课黑板 / 写歌做稿坐满进度 / QQ 手机放大 / 睡觉「今天的她」。
 * 像素风，材质复用商店切图（frame_chalkboard、card_paper、stock_box、icon_cd / icon_script）。只读：GET /player/{id} 轮询 + store。
 */
const INK = '#3B2F2F'
const CHALK = '#F4F1E6'
const CHALK_Y = '#FFE08A'
const short = (n: string) => n.replace(/_[0-9a-f]{6}$/i, '')
const avatar = (p: OtherPlayer, px = 56) => `assets/ui/avatars/${godotCharKeyFor(p.name, p.controller, p.agent_id, p.sprite)}_${px}.png`
const nine = (img: string, slice: number, width: number): CSSProperties => ({
  borderStyle: 'solid', borderWidth: width, borderColor: 'transparent',
  borderImage: `url(${SHOP_ASSET(img)}) ${slice} fill / ${width}px stretch`, imageRendering: 'pixelated',
})

/** GET /player/{id} 轮询（导播只读；切人即换） */
export function usePlayerDetail(id: string | null, ms: number): Record<string, unknown> | null {
  const [d, setD] = useState<{ id: string; v: Record<string, unknown> } | null>(null)
  useEffect(() => {
    if (!id) return
    let stop = false
    const load = () => apiGetOrNull<Record<string, unknown>>(`/player/${encodeURIComponent(id)}`).then(r => { if (!stop && r) setD({ id, v: r }) }).catch(() => {})
    load(); const t = window.setInterval(load, ms)
    return () => { stop = true; window.clearInterval(t) }
  }, [id, ms])
  return d && d.id === id ? d.v : null
}

export interface AnswerRow { who: string; name: string; text: string; at: number }

// ── 上课黑板 ──────────────────────────────────────────────
interface LessonFull { lesson_id?: string; course?: string; course_name?: string; title?: string; segment_i?: number; segment?: { i?: number; text?: string } | null; dozing?: boolean; question?: { qid?: string; text?: string } | null; questions?: { qid?: string; text?: string }[] }
export function ClassPanel({ target, players, answers }: { target: OtherPlayer; players: OtherPlayer[]; answers: AnswerRow[] }) {
  const d = usePlayerDetail(target.id, 3000)
  const l = (d?.lesson ?? null) as LessonFull | null
  const brief = target.lesson
  const course = l?.course_name ?? brief?.course ?? '上课'
  const title = l?.title ?? brief?.title ?? ''
  const segI = l?.segment_i ?? l?.segment?.i ?? 0
  const q = l?.questions?.length ? l.questions[l.questions.length - 1] : l?.question ?? null
  const lessonId = l?.lesson_id ?? brief?.lesson_id
  const mates = players.filter(p => p.lesson && p.lesson.lesson_id === lessonId)
  const ans = answers.filter(a => mates.some(m => m.id === a.who) || a.who === target.id).slice(-3).reverse()
  return (
    <div data-testid="director-class" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ ...nine('frame_chalkboard', 48, 30), padding: '8px 14px 14px', color: CHALK, fontFamily: 'inherit' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
          <span style={{ fontSize: 32, fontWeight: 700, letterSpacing: 2 }}>📚 {course}</span>
          {title && <span style={{ fontSize: 20, opacity: 0.85, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{title}</span>}
        </div>
        {/* 9 段进度：粉笔点 */}
        <div data-testid="director-class-segs" style={{ display: 'flex', gap: 8, margin: '10px 0' }}>
          {Array.from({ length: 9 }, (_, i) => <span key={i} style={{ width: 34, height: 10, borderRadius: 2, background: i + 1 < segI ? 'rgba(244,241,230,0.75)' : i + 1 === segI ? CHALK_Y : 'rgba(244,241,230,0.18)' }} />)}
          <span style={{ fontSize: 16, opacity: 0.8, marginLeft: 6 }}>{segI ? `第 ${segI} / 9 段` : '还没开讲'}</span>
        </div>
        {l?.segment?.text && <div style={{ fontSize: 20, lineHeight: 1.55, display: '-webkit-box', WebkitLineClamp: 4, WebkitBoxOrient: 'vertical', overflow: 'hidden', opacity: 0.92 }}>{l.segment.text}</div>}
        <div style={{ height: 3, margin: '12px 0', backgroundImage: `url(${SHOP_ASSET('chalk_line')})`, backgroundSize: '100% 100%', imageRendering: 'pixelated', opacity: 0.8 }} />
        {q?.text
          ? <div data-testid="director-class-question" style={{ fontSize: 24, lineHeight: 1.5, color: CHALK_Y }}>❓ 提问{q.qid ? ` ${q.qid}` : ''}：{q.text}</div>
          : <div style={{ fontSize: 20, opacity: 0.7 }}>这段没有提问，认真听讲中……</div>}
      </div>
      {/* 回答（ws action answer） */}
      {ans.length > 0 && (
        <div data-testid="director-class-answers" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {ans.map(a => (
            <div key={`${a.who}-${a.at}`} style={{ ...nine('stock_box', 14, 10), fontSize: 19, lineHeight: 1.45, padding: '2px 6px' }}>
              <b>✏️ {short(a.name)}</b>：{a.text}
            </div>
          ))}
        </div>
      )}
      {/* 在座 */}
      {mates.length > 0 && (
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          <span style={{ fontSize: 16, color: '#7A6A5A' }}>在座</span>
          {mates.map(m => (
            <div key={m.id} style={{ display: 'flex', alignItems: 'center', gap: 6, background: '#fff', border: '1px solid #E6DCCB', borderRadius: 8, padding: '4px 8px', fontSize: 17 }}>
              <img src={avatar(m, 56)} width={32} height={32} alt="" style={{ imageRendering: 'pixelated', borderRadius: 6 }} />
              {short(m.name)}{m.lesson?.dozing ? ' 💤' : ''}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── 写歌 / 做稿 ───────────────────────────────────────────
const createBases = new Map<string, CreateBase>()   // 每人坐下时的 daily_use 基线（跟着页面活）
export function CreatePanel({ target }: { target: OtherPlayer }) {
  const objects = useGameStore((s) => s.objects)
  const d = usePlayerDetail(target.id, 4000)
  const obj = objects.find(o => o.id === target.usingObjectId) ?? null
  const ck = createKind(obj?.type)
  if (!ck || !obj) return <div style={{ fontSize: 24 }}>🎵 创作中</div>
  const du = (d?.daily_use ?? {}) as Record<string, { used_min?: number; used_count?: number; limit_count?: number }>
  const r = createProgress(createBases.get(target.id), obj.id, du[obj.type]?.used_min, ck.needMin)
  createBases.set(target.id, r.base)
  const songs = du.compose?.used_count ?? 0, songMax = du.compose?.limit_count ?? 2
  const last = latestWork(d?.inventory, ck.kind)
  const pct = Math.round((r.progress ?? 0) * 100)
  return (
    <div data-testid="director-create" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ fontSize: 26, fontWeight: 700 }}>{ck.kind === 'song' ? '🎵' : '📄'} {short(target.name)} 在{obj.name}{ck.verb}</div>
      <div style={{ ...nine('card_paper', 28, 18), display: 'flex', gap: 16, alignItems: 'center', padding: 6 }}>
        <img src={SHOP_ASSET(ck.icon)} width={112} height={112} alt="" style={{ imageRendering: 'pixelated', animation: ck.kind === 'song' ? 'dirSpin 6s linear infinite' : undefined }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 18, color: '#7A6A5A' }}>坐满 {ck.needMin} 分钟出{ck.kind === 'song' ? '一张唱片' : '一份稿子'}</div>
          {/* 像素进度条 */}
          <div data-testid="director-create-bar" style={{ ...nine('stock_box', 14, 8), height: 40, marginTop: 8, padding: 0, position: 'relative' }}>
            <div style={{ position: 'absolute', inset: 0, display: 'flex' }}>
              {Array.from({ length: 20 }, (_, i) => <span key={i} style={{ flex: 1, margin: '0 1px', background: i < Math.round(pct / 5) ? (ck.kind === 'song' ? '#9B7BD8' : '#F2A14B') : 'transparent' }} />)}
            </div>
          </div>
          <div style={{ fontSize: 20, fontWeight: 700, marginTop: 6 }}>{r.sat !== null ? `已坐 ${Math.floor(r.sat)} / ${ck.needMin} 分钟` : '读取中…'}{r.progress !== null && r.progress >= 1 ? ' · 快好了！' : ''}</div>
          {ck.kind === 'song' && <div style={{ fontSize: 16, color: '#7A6A5A', marginTop: 2 }}>今天写好 {songs} / {songMax} 首{songs >= songMax ? '（今天写满了）' : ''}</div>}
        </div>
      </div>
      {last && (
        <div data-testid="director-create-last" style={{ ...nine('card_paper', 28, 18), padding: '2px 8px' }}>
          <div style={{ fontSize: 18, color: '#7A6A5A' }}>上一{ck.kind === 'song' ? '首' : '份'}</div>
          <div style={{ fontSize: 24, fontWeight: 700 }}>《{last.title}》</div>
          {last.lines.map((t, i) => <div key={i} style={{ fontSize: 18, lineHeight: 1.5, color: INK, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{t}</div>)}
        </div>
      )}
    </div>
  )
}

/** 产出弹卡：「鲸仔 写完了《…》」——DirectorApp 收到 produce compose / make_video 时挂 6 s */
export interface WorkPop { who: string; name: string; kind: 'song' | 'script'; at: number }
export function WorkPopCard({ pop }: { pop: WorkPop }) {
  const d = usePlayerDetail(pop.who, 2500)
  const w = latestWork(d?.inventory, pop.kind)
  return (
    <div data-testid="director-workpop" style={{ ...nine('card_paper', 28, 22), display: 'flex', alignItems: 'center', gap: 18, padding: '6px 18px 6px 6px', animation: 'dirPop 300ms ease-out', boxShadow: '4px 4px 0 rgba(0,0,0,0.25)' }}>
      <img src={SHOP_ASSET(pop.kind === 'song' ? 'icon_cd' : 'icon_script')} width={128} height={128} alt="" style={{ imageRendering: 'pixelated', animation: 'dirSpin 2.4s linear infinite' }} />
      <div style={{ minWidth: 0, color: INK }}>
        <div style={{ fontSize: 22, color: '#7A6A5A' }}>{pop.kind === 'song' ? '🎵 新歌出炉' : '📄 稿子完成'}</div>
        <div style={{ fontSize: 40, fontWeight: 700, whiteSpace: 'nowrap' }}>{short(pop.name)} {pop.kind === 'song' ? '写完了' : '做完了'}{w ? `《${w.title}》` : pop.kind === 'song' ? '一首新歌' : '一份稿子'}</div>
        {w?.lines[0] && <div style={{ fontSize: 20, marginTop: 4, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 760 }}>「{w.lines[0]}」</div>}
      </div>
    </div>
  )
}

// ── QQ 手机放大 ───────────────────────────────────────────
export function QQBigPanel({ target }: { target: OtherPlayer }) {
  const SCALE = 1.06
  return (
    <div data-testid="director-qq" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {/* transform 让 QQMobile 的 fixed 遮罩以这块为容器，手机居中放大 */}
      <div style={{ width: 684 / SCALE, height: 830 / SCALE, transform: `scale(${SCALE})`, transformOrigin: 'top left', position: 'relative' }}>
        <QQPanel key={target.id} viewOf={{ name: short(target.name), key: godotCharKeyFor(target.name, target.controller, target.agent_id, target.sprite) }} playerId={target.id} readOnly phone forceOpen embedded />
      </div>
    </div>
  )
}

// ── 睡觉：「今天的她」 ─────────────────────────────────────
export function TodaySummary({ target, chattedWith, eventTexts }: { target: OtherPlayer; chattedWith: string[]; eventTexts: string[] }) {
  const d = usePlayerDetail(target.id, 30_000)
  const rows = todaySummaryRows(d, chattedWith, eventTexts)
  const ref = useRef<HTMLDivElement>(null)
  const name = short(target.name)
  const heading = target.agent_id === 'whale' ? '今天的她' : `${name} 的今天`
  return (
    <div data-testid="director-today" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <img src={avatar(target, 112)} width={72} height={72} alt="" style={{ imageRendering: 'pixelated', borderRadius: 12, border: '3px solid #7F8CE8', background: '#fff', filter: 'brightness(0.85)' }} />
        <div>
          <div style={{ fontSize: 26, fontWeight: 700 }}>🌙 {name} 睡着了</div>
          <div style={{ fontSize: 18, color: '#7A6A5A', animation: 'dirPop 1.6s ease-in-out infinite alternate' }}>💤 Zzz…</div>
        </div>
      </div>
      <div ref={ref} style={{ ...nine('card_paper', 28, 20), padding: '4px 10px 10px' }}>
        <div style={{ fontSize: 28, fontWeight: 700, textAlign: 'center', letterSpacing: 4, marginBottom: 6 }}>📔 {heading}</div>
        {rows.length === 0 && <div style={{ fontSize: 20, color: '#7A6A5A', textAlign: 'center', padding: 12 }}>今天过得很安静</div>}
        {rows.map((r, i) => (
          <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'baseline', fontSize: 21, lineHeight: 1.5, padding: '3px 0', borderBottom: i < rows.length - 1 ? '2px dashed rgba(122,106,90,0.25)' : 'none' }}>
            <span style={{ width: 30, textAlign: 'center' }}>{r.icon}</span>
            {r.label && <b style={{ whiteSpace: 'nowrap' }}>{r.label}</b>}
            <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
