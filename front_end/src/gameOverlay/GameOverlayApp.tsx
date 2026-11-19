import { useEffect, useState, type CSSProperties, type ReactNode } from 'react'
import { deriveGameView, parseOverlayParams, type GameState } from './view'

/**
 * 直播「游戏」模式信息层：5173/?view=game（总控 11-19；G 的积木图画面面板用 iframe 嵌成显示块，可拖）。
 * 背景透明、只读：每 1 s GET /gameapi/game/state（vite 代理到 D 的 8120）。弹幕列 / 回复板子 / 立绘仍是舞台页 G 的呈现块，这里不画。
 * 参数：blocks=visitor,checks,verdict,votes,score（默认全开）· layout=card（竖排，右侧一列）| bar（横条，游戏区底部）· theme=dark | cream · scale=1 · demo=1（没开游戏时用样例，给 G 摆位置）
 */
const GAME_API = ((import.meta.env.VITE_GAME_API as string | undefined) ?? '/gameapi').replace(/\/$/, '')
const POLL_MS = 1000

const DEMO: GameState = {
  status: 'running', game: 'tnmn', screen: 'id_card',
  visitor: { name: 'Otto Reyes', apartment: '5D', appearance: '灰色帽形头发，肤色浅橙，两眼对称，嘴里有六颗小方牙' },
  checks: [
    { item: '姓名、房号与自称是否一致', result: 'match', evidence: '证件和台词都是 Otto Reyes、5D' },
    { item: '牙齿数量：本人 vs 证件照', result: 'mismatch', evidence: '证件照两颗大门牙，本人六颗牙' },
    { item: '眼睛与发型', result: 'match', evidence: '两眼对称，灰色帽形头发相同' },
    { item: '住户名单是否有 5D Otto Reyes', result: 'unknown', evidence: '还没打开名单' },
  ],
  verdict: 'reject', suspicion: 0.93, lead: '他证件照里只有两颗门牙，本人却有六颗，这个对不上，我要拒绝他。',
  votes: { admit: 3, reject: 11 },
  decisions: [{ correct: 1 }, { correct: 1 }, { correct: 0 }, { correct: 1 }],
}

export default function GameOverlayApp() {
  const p = parseOverlayParams(window.location.search)
  const [state, setState] = useState<GameState | null>(p.demo ? DEMO : null)
  const [down, setDown] = useState(false)
  useEffect(() => {
    // 透明底：舞台页 iframe / 直播姬浏览器源里叠在游戏画面上
    for (const el of [document.documentElement, document.body, document.getElementById('root')]) if (el) el.style.background = 'transparent'
    if (p.demo) return
    let stop = false
    const tick = async () => {
      try {
        const r = await fetch(`${GAME_API}/game/state`, { cache: 'no-store' })
        if (!r.ok) throw new Error(String(r.status))
        const j = await r.json() as GameState
        if (!stop) { setState(j); setDown(false) }
      } catch { if (!stop) setDown(true) }
    }
    tick()
    const t = window.setInterval(tick, POLL_MS)
    return () => { stop = true; window.clearInterval(t) }
  }, [p.demo])
  const v = deriveGameView(state)
  if (!v.live) return <div data-testid="game-overlay-idle" style={{ display: 'none' }}>{down ? 'game api down' : 'idle'}</div>
  const T = p.theme === 'cream' ? CREAM : DARK
  const bar = p.layout === 'bar'                                   // 横条：游戏区底部一条，块并排、核对每项一行
  const box = (key: string, children: ReactNode, extra: CSSProperties = {}) => (
    <div key={key} data-testid={`go-${key}`} style={{ background: T.panel, border: `2px solid ${T.border}`, borderRadius: 12, padding: '10px 14px', color: T.ink, boxShadow: '0 4px 14px rgba(0,0,0,0.25)', ...extra }}>{children}</div>
  )
  const blocks: ReactNode[] = []
  if (p.blocks.has('visitor') && v.visitor) blocks.push(box('visitor', (
    <>
      <div style={{ fontSize: 13, color: T.soft }}>门口的人</div>
      <div style={{ fontSize: 22, fontWeight: 700 }}>{v.visitor.name} <span style={{ fontSize: 16, color: T.soft, fontWeight: 400 }}>· {v.visitor.apartment}</span></div>
      {v.visitor.appearance && <div style={{ fontSize: 14, color: T.soft, marginTop: 2 }}>{v.visitor.appearance}</div>}
    </>
  )))
  if (p.blocks.has('checks') && v.checks.length) blocks.push(box('checks', (
    <>
      <div style={{ fontSize: 13, color: T.soft, marginBottom: 4 }}>她在核对</div>
      {v.checks.map((c, i) => (
        <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'baseline', padding: bar ? '1px 0' : '3px 0' }}>
          <span style={{ width: 20, textAlign: 'center', fontWeight: 700, color: c.tone === 'ok' ? T.ok : c.tone === 'bad' ? T.bad : T.soft, flexShrink: 0 }}>{c.icon}</span>
          {bar
            ? <div style={{ minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontSize: 15 }}><b>{c.item}</b>{c.evidence && <span style={{ fontSize: 13, color: T.soft, marginLeft: 10 }}>{c.evidence}</span>}</div>
            : <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 16, fontWeight: 600 }}>{c.item}</div>
                {c.evidence && <div style={{ fontSize: 13, color: T.soft }}>{c.evidence}</div>}
              </div>}
        </div>
      ))}
    </>
  ), { flex: bar ? '1 1 0' : undefined, minWidth: 0 }))
  if (p.blocks.has('verdict') && (v.lead || v.suspicion !== null)) blocks.push(box('verdict', (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ fontSize: 13, color: T.soft }}>她现在的判断</span>
        <span data-testid="go-verdict-badge" style={{ fontSize: 15, fontWeight: 700, padding: '2px 10px', borderRadius: 10, background: v.verdict.tone === 'admit' ? T.ok : v.verdict.tone === 'reject' ? T.bad : T.track, color: v.verdict.tone === 'none' ? T.ink : '#fff' }}>{v.verdict.label}</span>
        {v.statusNote && <span style={{ fontSize: 13, color: T.warn }}>{v.statusNote}</span>}
      </div>
      {v.suspicion !== null && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6 }}>
          <span style={{ fontSize: 13, color: T.soft, width: 44 }}>可疑度</span>
          <div style={{ flex: 1, height: 10, background: T.track, borderRadius: 5, overflow: 'hidden' }}><div style={{ width: `${Math.round(v.suspicion * 100)}%`, height: '100%', background: v.suspicion >= 0.6 ? T.bad : v.suspicion >= 0.3 ? T.warn : T.ok }} /></div>
          <span style={{ fontSize: 14, width: 40, textAlign: 'right' }}>{Math.round(v.suspicion * 100)}%</span>
        </div>
      )}
      {v.lead && <div style={{ fontSize: 17, marginTop: 6, lineHeight: 1.45 }}>「{v.lead}」</div>}
    </>
  ), { flex: bar ? '1 1 0' : undefined, minWidth: 0 }))
  if (p.blocks.has('votes') && v.votes) blocks.push(box('votes', (
    <>
      <div style={{ fontSize: 13, color: T.soft, marginBottom: 4 }}>观众投票</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 16, fontWeight: 700 }}>
        <span style={{ color: T.ok, width: 64 }}>放行 {v.votes.admit}</span>
        <div style={{ flex: 1, height: 12, borderRadius: 6, overflow: 'hidden', display: 'flex', background: T.track }}>
          {v.votes.total > 0 && <><div style={{ width: `${(v.votes.admit / v.votes.total) * 100}%`, background: T.ok }} /><div style={{ flex: 1, background: T.bad }} /></>}
        </div>
        <span style={{ color: T.bad, width: 64, textAlign: 'right' }}>{v.votes.reject} 拒绝</span>
      </div>
    </>
  ), bar ? { width: 320, flexShrink: 0 } : {}))
  if (p.blocks.has('score') && v.score) blocks.push(box('score', (
    <div style={{ fontSize: 15 }}>本班 <b style={{ color: T.ok }}>判对 {v.score.correct}</b> · <b style={{ color: T.bad }}>判错 {v.score.wrong}</b></div>
  ), { padding: '6px 14px' }))
  if (v.summary && p.blocks.has('verdict')) blocks.push(box('summary', <div style={{ fontSize: 16 }}>{v.summary}</div>))
  return (
    <div data-testid="game-overlay" style={{ position: 'fixed', left: 0, top: 0, width: `${100 / p.scale}%`, transform: `scale(${p.scale})`, transformOrigin: 'top left', padding: 8, boxSizing: 'border-box', display: 'flex', flexDirection: p.layout === 'bar' ? 'row' : 'column', alignItems: p.layout === 'bar' ? 'stretch' : 'stretch', gap: 10, fontFamily: '"PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", system-ui, sans-serif', userSelect: 'none', pointerEvents: 'none' }}>
      {blocks}
    </div>
  )
}

const DARK = { panel: 'rgba(18,18,32,0.78)', border: 'rgba(255,255,255,0.18)', ink: '#F5F5F7', soft: '#B9BCCB', ok: '#3BB7A8', bad: '#FF6B5E', warn: '#F2B84B', track: 'rgba(255,255,255,0.16)' }
const CREAM = { panel: 'rgba(255,248,236,0.92)', border: '#7FB6E8', ink: '#3B2F2F', soft: '#7A6A5A', ok: '#2E9E8F', bad: '#E5534B', warn: '#C57B12', track: '#EDE3D2' }
