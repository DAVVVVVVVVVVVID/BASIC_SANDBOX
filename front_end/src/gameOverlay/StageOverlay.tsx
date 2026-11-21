import { useEffect, useState, type CSSProperties, type ReactNode } from 'react'
import { stageChecks, stageInfo, type GameState, type GameView } from './view'

/**
 * 游戏舞台 · 档案风（主播 11-21 选定方案 e，概念图 docs/stage-levels/game/game_concept_e.png）：?view=game&layout=stage
 * 1920×1080 设计稿，按窗口等比缩放；全屏透明、不接鼠标。只画左上标题 + 底部四张卡（核对 / 判断 / 投票 / 战绩）。
 * 舞台底图、游戏画面、弹幕字幕立绘都在 G 的舞台页，这里不画；不画「她在想」。
 */
const W = 1920, H = 1080
const INK = '#4a3222', INK_SOFT = '#7a5a40', RED = '#a8321f', GREEN = '#2f6b45', AMBER = '#b07a12', NAVY = '#2e4466'
const FONT = '"Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "Source Han Sans SC", system-ui, sans-serif'
/** 卡片条：x 60–1340、y 900–1065，四张等宽（whale-ec 量的） */
const STRIP = { x: 60, y: 900, w: 1340 - 60, h: 1065 - 900, gap: 16 }
const CARD_W = (STRIP.w - STRIP.gap * 3) / 4
/** 标题：x 205–1240、y 35–150（左边是底图门牌徽章） */
const TITLE = { x: 205, y: 35, w: 1240 - 205, h: 150 - 35 }
const ART = 'assets/stage-game/'

const CSS = `
@keyframes stageStamp {
  0% { transform: scale(2.4) rotate(-6deg); opacity: 0 }
  45% { transform: scale(0.9) rotate(2deg); opacity: 1 }
  58% { transform: scale(1.07) rotate(-2deg) translate(3px, -2px) }
  70% { transform: scale(0.97) rotate(1deg) translate(-3px, 1px) }
  84% { transform: scale(1.01) translate(1px, 0) }
  100% { transform: scale(1) }
}
@keyframes stageInkIn { from { opacity: 0 } to { opacity: 1 } }
`

function useFitScale() {
  const get = () => Math.min(window.innerWidth / W, window.innerHeight / H)
  const [s, setS] = useState(get)
  useEffect(() => { const f = () => setS(get()); window.addEventListener('resize', f); return () => window.removeEventListener('resize', f) }, [])
  return s
}

/** 牛皮纸卡：card_land 去掉夹子后做九宫格（夹子单独一张 clip.png 盖在顶上） */
const paper: CSSProperties = {
  borderStyle: 'solid', borderWidth: 14, borderImage: `url(${ART}card_frame.png) 30 fill / 14px stretch`,
  filter: 'drop-shadow(0 4px 6px rgba(0,0,0,0.45))',
}

function Clip() {
  return (
    <img src={`${ART}clip.png`} alt="" style={{ position: 'absolute', left: '50%', top: -36, transform: 'translateX(-50%)', width: 100, height: 37 }} />
  )
}

function Card({ x, icon, title, extra, children, testid }: { x: number; icon: string; title: string; extra?: ReactNode; children: ReactNode; testid: string }) {
  return (
    <div data-testid={testid} style={{ position: 'absolute', left: x, top: STRIP.y, width: CARD_W, height: STRIP.h, boxSizing: 'border-box', ...paper, padding: '6px 6px 0', color: INK }}>
      <Clip />
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, height: 30, borderBottom: `2px solid ${INK_SOFT}66` }}>
        <img src={`${ART}${icon}.png`} alt="" style={{ width: 26, height: 26, objectFit: 'contain' }} />
        <span style={{ fontSize: 22, fontWeight: 800, letterSpacing: 1 }}>{title}</span>
        <span style={{ flex: 1 }} />
        {extra}
      </div>
      <div style={{ position: 'relative', height: STRIP.h - 28 - 6 - 32 - 4, marginTop: 4 }}>{children}</div>
    </div>
  )
}

/** 圆形墨章（✓ / ✗ / ? / !）：whale-ec 的 badge_*.png；拒错用 ✗ 调成藏青 */
type BadgeKind = 'check' | 'x' | 'q' | 'warn' | 'x_navy'
function Badge({ kind, size = 28 }: { kind: BadgeKind; size?: number }) {
  const file = kind === 'x_navy' ? 'x' : kind
  return <img src={`${ART}badge_${file}.png`} alt="" style={{ width: size, height: size, flexShrink: 0, objectFit: 'contain', filter: kind === 'x_navy' ? 'hue-rotate(205deg) saturate(0.55) brightness(0.85)' : undefined }} />
}

/** 墨字小标签（等游戏窗口回来 / 暂停中 / 稍等一下 / 卡住了） */
function InkTag({ text }: { text: string }) {
  return <span data-testid="stage-status" style={{ fontSize: 14, fontWeight: 800, color: INK, border: `2px solid ${INK}`, borderRadius: 4, padding: '0 6px', lineHeight: '20px', background: 'rgba(255,248,230,0.55)', transform: 'rotate(-3deg)', whiteSpace: 'nowrap' }}>{text}</span>
}

function Bar({ k, color, h = 16 }: { k: number; color: string; h?: number }) {
  return (
    <div style={{ flex: 1, height: h, borderRadius: h / 2, background: 'rgba(120,90,60,0.18)', border: `2px solid ${INK}`, overflow: 'hidden' }}>
      <div style={{ width: `${Math.max(0, Math.min(1, k)) * 100}%`, height: '100%', background: color, transition: 'width 600ms ease' }} />
    </div>
  )
}

const TONE_BADGE = { ok: 'check', bad: 'x', unknown: 'q', warn: 'warn' } as const

export default function StageOverlay({ state, v }: { state: GameState | null; v: GameView }) {
  const s = useFitScale()
  const info = stageInfo(state)
  const rows = stageChecks([...(info.anomaly ? [{ tone: 'warn' as const, item: '她觉得怪', evidence: info.anomaly }] : []), ...v.checks], 3)
  const day = info.title?.day
  const visitor = info.title?.visitor
  const q = info.quad
  const xs = [0, 1, 2, 3].map(i => STRIP.x + i * (CARD_W + STRIP.gap))
  const stamp = v.verdict.tone === 'reject' ? 'stamp_reject' : v.verdict.tone === 'admit' ? 'stamp_admit' : null
  return (
    <div data-testid="game-stage" style={{ position: 'fixed', left: 0, top: 0, width: W, height: H, transform: `scale(${s})`, transformOrigin: 'top left', fontFamily: FONT, pointerEvents: 'none', userSelect: 'none' }}>
      <style>{CSS}</style>
      {/* 标题：今晚当门卫 · 第 N 天 · 第 M 位访客 */}
      <div data-testid="stage-title" style={{ position: 'absolute', left: TITLE.x, top: TITLE.y, width: TITLE.w, height: TITLE.h, display: 'flex', alignItems: 'center', gap: 16, color: INK, fontWeight: 900, whiteSpace: 'nowrap', overflow: 'hidden', textShadow: '0 1px 0 rgba(255,240,210,0.6)' }}>
        <span style={{ fontSize: 72, letterSpacing: 6 }}>今晚当门卫</span>
        {day != null && <><span style={{ fontSize: 44 }}>·</span><span style={{ fontSize: 48 }}>第 <span style={{ color: RED }}>{day}</span> 天</span></>}
        {visitor != null && <><span style={{ fontSize: 44 }}>·</span><span style={{ fontSize: 48 }}>第 <span style={{ color: RED }}>{visitor}</span> 位访客</span></>}
      </div>
      {v.live && <>
        {/* 她在核对 */}
        <Card testid="stage-checks" x={xs[0]} icon="icon_clipboard" title="她在核对">
          {rows.length ? rows.map((c, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 9, height: 31, borderBottom: i < rows.length - 1 ? `1px dashed ${INK_SOFT}88` : 'none' }}>
              <Badge kind={TONE_BADGE[c.tone]} size={26} />
              <div style={{ minWidth: 0, lineHeight: 1.05 }}>
                <div style={{ fontSize: 15.5, fontWeight: 800, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.item}</div>
                {c.evidence && <div style={{ fontSize: 11.5, color: INK_SOFT, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.evidence}</div>}
              </div>
            </div>
          )) : <div style={{ fontSize: 16, color: INK_SOFT, paddingTop: 8, lineHeight: 1.4 }}>{v.summary ?? '等下一位访客'}</div>}
        </Card>
        {/* 她的判断：大圆章（判断变了重新盖一次）+ 可疑度 */}
        <Card testid="stage-verdict" x={xs[1]} icon="icon_scale" title="她的判断" extra={v.statusNote ? <InkTag text={v.statusNote} /> : undefined}>
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 66 }}>
            {stamp
              ? <img key={stamp} data-testid="stage-stamp" src={`${ART}${stamp}.png`} alt={v.verdict.label} style={{ height: 92, marginTop: -14, animation: 'stageStamp 650ms cubic-bezier(.3,1.4,.5,1) both', transformOrigin: 'center' }} />
              : <span data-testid="stage-stamp" style={{ fontSize: 22, fontWeight: 800, color: INK_SOFT, border: `3px dashed ${INK_SOFT}`, borderRadius: '50%', padding: '6px 18px', transform: 'rotate(-8deg)' }}>{v.verdict.label}</span>}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 2 }}>
            <span style={{ fontSize: 14, fontWeight: 800 }}>可疑度</span>
            <Bar k={v.suspicion ?? 0} color={RED} h={13} />
            <span style={{ fontSize: 19, fontWeight: 900, color: RED, width: 50, textAlign: 'right' }}>{v.suspicion === null ? '—' : `${Math.round(v.suspicion * 100)}%`}</span>
          </div>
        </Card>
        {/* 观众投票 */}
        <Card testid="stage-votes" x={xs[2]} icon="icon_people" title="观众投票">
          {([['放行', v.votes?.admit ?? 0, GREEN], ['拒绝', v.votes?.reject ?? 0, RED]] as const).map(([label, n, c], i) => (
            <div key={label} style={{ marginTop: i ? 6 : 0 }}>
              <div style={{ fontSize: 15, fontWeight: 800, color: c, lineHeight: 1.2 }}>{label}</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <Bar k={v.votes && v.votes.total ? n / v.votes.total : 0} color={c} h={16} />
                <span style={{ fontSize: 24, fontWeight: 900, color: c, minWidth: 36, textAlign: 'right', lineHeight: 1 }}>{n}</span>
              </div>
            </div>
          ))}
        </Card>
        {/* 本班战绩：今天的放对 / 拒对 / 放错 / 拒错（白天多半待定，结算后揭晓） */}
        <Card testid="stage-score" x={xs[3]} icon="icon_trophy" title="本班战绩" extra={<span style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          {q.pending > 0 && <span data-testid="stage-pending" style={{ fontSize: 13, fontWeight: 700, color: INK_SOFT }}>待定 {q.pending}</span>}
          {day != null && <span style={{ fontSize: 14, fontWeight: 800, border: `2px solid ${INK}`, borderRadius: 4, padding: '0 5px', lineHeight: '20px' }}>第 {day} 天</span>}
        </span>}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gridTemplateRows: '1fr 1fr', height: '100%' }}>
            {([['放对', q.admitOk, 'check', GREEN], ['拒对', q.rejectOk, 'x', RED], ['放错', q.admitBad, 'warn', AMBER], ['拒错', q.rejectBad, 'x_navy', NAVY]] as const).map(([label, n, kind, c], i) => (
              <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 8, paddingLeft: i % 2 ? 12 : 4, borderLeft: i % 2 ? `1px dashed ${INK_SOFT}99` : 'none' }}>
                <Badge kind={kind} size={28} />
                <div style={{ lineHeight: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 800 }}>{label}</div>
                  <div style={{ fontSize: 26, fontWeight: 900, color: c }}>{n}</div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </>}
    </div>
  )
}
