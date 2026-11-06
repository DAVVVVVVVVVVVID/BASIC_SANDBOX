import { useEffect, useRef, useState, useCallback } from 'react'
import Markdown from './Markdown'
import {
  fetchLatest, fetchTraces, fetchPrompt, fetchToday, streamUrl, replyFromToolCalls, toolNames, fetchMemoryText,
  type TraceRow, type Latest, type TodayView, type PromptDetail, type MemoryRow,
} from './api'

/**
 * Q0 「她的脑子」`/brain?date=YYYY-MM-DD&town=main`：
 *  左：实时流（SSE /observe/stream，断了退回 3 s 轮询 /observe/traces?since=）滚动每次 Think / Plan；
 *  右：今天的时间轴 —— 七变量当前值、日程、计划批次（思考摘录 + 花费）、写下的记忆（点开全文）、Dream / 日摘要；
 *  点任一条思考 → /observe/prompt/{call_id} 看完整输入输出。只读；观察服务不含弹幕原文。
 */

const TIER_STYLE: Record<string, { bg: string; label: string }> = {
  think:  { bg: '#3987e5', label: 'Think' },
  plan:   { bg: '#c98500', label: 'Plan' },
  shadow: { bg: '#5b5b58', label: 'Shadow' },
  dream:  { bg: '#d55181', label: 'Dream' },
}
const hhmm = (ts?: string | null) => (ts ? ts.slice(11, 16) : '--:--')
const hhmmss = (ts?: string | null) => (ts ? ts.slice(11, 19) : '--:--:--')
const money = (v?: number | null) => (typeof v === 'number' ? `$${v.toFixed(3)}` : '')

function readParams() {
  const q = new URLSearchParams(window.location.search)
  const date = /^\d{4}-\d{2}-\d{2}$/.test(q.get('date') || '') ? q.get('date')! : null
  const town = (q.get('town') || 'main').replace(/[^a-z0-9_-]/gi, '')
  return { date, town, showShadow: q.get('shadow') === '1' }
}
const PARAMS = readParams()

export default function BrainApp() {
  const { date, town, showShadow } = PARAMS
  const [rows, setRows] = useState<TraceRow[]>([])
  const [latest, setLatest] = useState<Latest | null>(null)
  const [today, setToday] = useState<TodayView | null>(null)
  const [live, setLive] = useState<'sse' | 'poll' | 'off'>('off')
  const [err, setErr] = useState<string | null>(null)
  const [detail, setDetail] = useState<{ kind: 'prompt'; data: PromptDetail } | { kind: 'memory'; m: MemoryRow; path: string | null; text: string | null } | { kind: 'loading'; title: string } | null>(null)
  const [tab, setTab] = useState<'plan' | 'memory' | 'schedule' | 'dream'>('plan')
  const seen = useRef(new Set<string>())
  const lastTs = useRef('')
  const feedRef = useRef<HTMLDivElement>(null)
  const [stick, setStick] = useState(true)

  const pushRows = useCallback((items: TraceRow[]) => {
    const fresh = items.filter(r => { const k = r.call_id ?? `${r.ts}|${r.tier}`; if (seen.current.has(k)) return false; seen.current.add(k); return true })
    if (fresh.length === 0) return
    for (const r of fresh) if (r.ts > lastTs.current) lastTs.current = r.ts
    setRows(prev => [...prev, ...fresh].sort((a, b) => a.ts.localeCompare(b.ts)).slice(-600))
  }, [])

  // 实时流：SSE 优先；失败退回轮询
  useEffect(() => {
    let es: EventSource | null = null
    let pollTimer: number | null = null
    let dead = false
    const startPoll = () => {
      if (pollTimer !== null) return
      setLive('poll')
      const tick = async () => {
        try { const r = await fetchTraces(date ?? undefined, lastTs.current || undefined); pushRows(r.items); setErr(null) } catch (e) { setErr(String(e)) }
        if (!dead) pollTimer = window.setTimeout(tick, 3000)
      }
      tick()
    }
    try {
      es = new EventSource(streamUrl(date ?? undefined))
      es.onopen = () => { setLive('sse'); setErr(null) }
      es.onmessage = (ev) => { try { pushRows([JSON.parse(ev.data) as TraceRow]) } catch { /* skip */ } }
      es.onerror = () => { es?.close(); es = null; startPoll() }
    } catch { startPoll() }
    return () => { dead = true; es?.close(); if (pollTimer !== null) window.clearTimeout(pollTimer) }
  }, [date, pushRows])

  // latest（七变量 / 当前计划）每 5 s；today 每 60 s
  useEffect(() => {
    let dead = false
    const loop = async () => {
      try { setLatest(await fetchLatest()) } catch { /* 静默 */ }
      if (!dead) window.setTimeout(loop, 5000)
    }
    const loopToday = async () => {
      try { setToday(await fetchToday(date ?? undefined)); setErr(null) } catch (e) { setErr(String(e)) }
      if (!dead) window.setTimeout(loopToday, 60000)
    }
    loop(); loopToday()
    return () => { dead = true }
  }, [date])

  // 新行到达时若贴底则滚到底
  useEffect(() => {
    if (stick && feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight
  }, [rows, stick])

  async function openPrompt(r: TraceRow) {
    if (!r.call_id) return
    setDetail({ kind: 'loading', title: '读取完整输入输出…' })
    try { setDetail({ kind: 'prompt', data: await fetchPrompt(r.call_id) }) } catch (e) { setDetail({ kind: 'prompt', data: { call_id: r.call_id, ts: r.ts, prompt_text: `（读取失败：${String(e)}）` } }) }
  }
  async function openMemory(m: MemoryRow) {
    setDetail({ kind: 'loading', title: '读取记忆全文…' })
    const r = await fetchMemoryText(town, today?.date ?? date ?? new Date().toISOString().slice(0, 10), m)
    setDetail({ kind: 'memory', m, path: r.path, text: r.text })
  }

  const visible = rows.filter(r => showShadow || r.tier !== 'shadow')
  const needs = latest?.needs_lines ?? []

  return (
    <div style={{ background: '#101010', color: '#f0efec', minHeight: '100vh', fontFamily: 'system-ui, "PingFang SC", "Microsoft YaHei", sans-serif', display: 'flex', flexDirection: 'column' }}>
      {/* 顶栏 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '10px 18px', borderBottom: '1px solid #2c2c2a', background: '#161615' }}>
        <div style={{ fontSize: 20, fontWeight: 700 }}>🐳 她的脑子</div>
        <div style={{ color: '#8a897f', fontSize: 13 }}>{today?.date ?? date ?? '今天'} · {town}</div>
        <div style={{ display: 'flex', gap: 6, marginLeft: 8 }}>
          {needs.map(n => <span key={n} style={chip}>{n}</span>)}
        </div>
        <div style={{ marginLeft: 'auto', fontSize: 12, color: live === 'off' ? '#d95926' : '#8a897f' }}>
          {live === 'sse' ? '● 实时（SSE）' : live === 'poll' ? '● 实时（轮询）' : '○ 未连接'}
          {today && <span style={{ marginLeft: 12 }}>今天 {today.stats.calls} 次调用 · Think {today.stats.think} · Plan {today.stats.plan_calls} · {money(today.stats.cost_usd)} · 记忆 {today.stats.memories}</span>}
        </div>
      </div>
      {err && <div style={{ background: '#3a1d14', color: '#f6c3b0', padding: '6px 18px', fontSize: 12 }}>观察服务（8002）读取失败：{err}。页面只读，服务恢复后自动续上。</div>}

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(420px, 46%) 1fr', gap: 0, flex: 1, minHeight: 0 }}>
        {/* 左：实时流 */}
        <div style={{ borderRight: '1px solid #2c2c2a', display: 'flex', flexDirection: 'column', minHeight: 0, height: 'calc(100vh - 56px)' }}>
          <div style={{ padding: '8px 14px', fontSize: 13, color: '#c3c2b7', display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontWeight: 600 }}>实时思考</span>
            <span style={{ color: '#8a897f' }}>{visible.length} 条 · 点一条看完整输入输出</span>
            <label style={{ marginLeft: 'auto', fontSize: 12, color: '#8a897f', cursor: 'pointer' }}><input type="checkbox" checked={stick} onChange={e => setStick(e.target.checked)} /> 跟随最新</label>
          </div>
          <div ref={feedRef} onScroll={e => { const el = e.currentTarget; setStick(el.scrollHeight - el.scrollTop - el.clientHeight < 40) }} style={{ overflowY: 'auto', flex: 1, padding: '0 10px 12px' }}>
            {visible.length === 0 && <div style={{ color: '#8a897f', padding: 20, fontSize: 13 }}>还没有今天的思考记录（agent 没起或还没到她起床时间）。</div>}
            {visible.map((r) => {
              const st = TIER_STYLE[r.tier] ?? { bg: '#5b5b58', label: r.tier }
              const reply = replyFromToolCalls(r.tool_calls)
              const tools = toolNames(r.tool_calls).filter(t => t !== 'finish')
              let text = reply ?? (r.thought && !r.thought.startsWith('→') ? r.thought : '')
              let planList: string[] | null = null
              if (r.tier === 'plan' && /^\s*\{\s*"plans"/.test(text)) {
                try { const j = JSON.parse(text) as { plans?: string[] }; if (Array.isArray(j.plans)) { planList = j.plans; text = '' } } catch { /* 原样显示 */ }
              }
              return (
                <div key={r.call_id ?? r.ts} onClick={() => openPrompt(r)} style={{ background: '#1a1a19', border: '1px solid #2c2c2a', borderRadius: 10, padding: '10px 12px', margin: '8px 0', cursor: r.call_id ? 'pointer' : 'default' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: '#8a897f' }}>
                    <span style={{ background: st.bg, color: '#fff', borderRadius: 4, padding: '1px 6px', fontWeight: 600 }}>{st.label}</span>
                    <span>{hhmmss(r.ts)}</span>
                    {r.loop_step != null && <span>第 {r.loop_step} 步</span>}
                    <span style={{ marginLeft: 'auto' }}>{r.model}{r.cache_hit ? ' · 缓存' : ''} {money(r.cost_usd)}</span>
                  </div>
                  {r.plan && <div style={{ fontSize: 12, color: '#c98500', marginTop: 4 }}>计划：{r.plan}</div>}
                  {text && <div style={{ fontSize: 14, lineHeight: 1.55, marginTop: 6, whiteSpace: 'pre-wrap' }}>{text.length > 420 ? text.slice(0, 420) + '…' : text}</div>}
                  {planList && <ol style={{ margin: '6px 0 0 18px', padding: 0, fontSize: 14, lineHeight: 1.55 }}>{planList.map((pl, i) => <li key={i} style={{ margin: '2px 0' }}>{pl}</li>)}</ol>}
                  {tools.length > 0 && <div style={{ fontSize: 12, color: '#86b6ef', marginTop: 6 }}>→ {tools.join('、')}</div>}
                </div>
              )
            })}
          </div>
        </div>

        {/* 右：今天 */}
        <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, height: 'calc(100vh - 56px)' }}>
          <div style={{ display: 'flex', gap: 4, padding: '8px 14px', borderBottom: '1px solid #2c2c2a' }}>
            {([['plan', `计划批次 ${today?.plan_batches.length ?? ''}`], ['memory', `写下的记忆 ${today?.memories.length ?? ''}`], ['schedule', '日程'], ['dream', 'Dream / 日摘要']] as const).map(([k, label]) => (
              <button key={k} onClick={() => setTab(k)} style={{ ...tabBtn, background: tab === k ? '#3987e5' : '#2c2c2a' }}>{label}</button>
            ))}
            {latest?.plan && <span style={{ marginLeft: 'auto', fontSize: 12, color: '#c98500', alignSelf: 'center', maxWidth: 420, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={latest.plan}>当前：{latest.plan}</span>}
          </div>
          <div style={{ overflowY: 'auto', flex: 1, padding: '10px 16px 16px' }}>
            {!today && <div style={{ color: '#8a897f', fontSize: 13 }}>加载今天的记录…</div>}
            {today && tab === 'plan' && (
              <div>
                {today.plan_batches.length === 0 && <div style={{ color: '#8a897f', fontSize: 13 }}>今天还没有计划批次。</div>}
                {today.plan_batches.map(b => (
                  <details key={b.plan_id} open style={{ background: '#1a1a19', border: '1px solid #2c2c2a', borderRadius: 10, padding: '8px 12px', margin: '8px 0' }}>
                    <summary style={{ cursor: 'pointer', fontSize: 14 }}>
                      <span style={{ color: '#c98500', fontWeight: 600 }}>{b.plan_id.split('#').pop()}.</span> {b.plan ?? '（无标题）'}
                      <span style={{ color: '#8a897f', fontSize: 12, marginLeft: 8 }}>{hhmm(b.first_ts)}–{hhmm(b.last_ts)} · Think {b.think_calls} 次 · {money(b.cost_usd)}</span>
                    </summary>
                    <div style={{ marginTop: 6 }}>
                      {b.thoughts.filter(t => !t.text.startsWith('→')).slice(-8).map((t, i) => (
                        <div key={i} style={{ fontSize: 13, color: '#e2e2dc', margin: '4px 0', display: 'flex', gap: 8 }}><span style={{ color: '#8a897f', flexShrink: 0 }}>{hhmm(t.ts)}</span><span>{t.text}</span></div>
                      ))}
                      {b.thoughts.every(t => t.text.startsWith('→')) && <div style={{ fontSize: 12, color: '#8a897f' }}>这一批的思考都是工具调用（{[...new Set(b.thoughts.map(t => t.text))].join('；')}），左侧点开对应条目看她的话。</div>}
                    </div>
                  </details>
                ))}
                {today.plans_md && <details style={{ marginTop: 10 }}><summary style={{ color: '#8a897f', cursor: 'pointer', fontSize: 12 }}>当前计划清单（current_plans.md）</summary><Markdown text={today.plans_md} /></details>}
              </div>
            )}
            {today && tab === 'memory' && (
              <div>
                {today.memories.length === 0 && <div style={{ color: '#8a897f', fontSize: 13 }}>今天还没有写下记忆。</div>}
                {[...today.memories].reverse().map((m, i) => (
                  <div key={i} onClick={() => openMemory(m)} style={{ background: '#1a1a19', border: '1px solid #2c2c2a', borderRadius: 10, padding: '8px 12px', margin: '6px 0', cursor: 'pointer' }}>
                    <div style={{ display: 'flex', gap: 8, fontSize: 12, color: '#8a897f', alignItems: 'center' }}>
                      <span style={{ background: m.type === 'recognition' ? '#d55181' : '#199e70', color: '#fff', borderRadius: 4, padding: '1px 6px', fontWeight: 600 }}>{m.type === 'recognition' ? '认识' : '事件'}</span>
                      <span>{hhmm(m.ts)}</span>
                      <span style={{ marginLeft: 'auto' }}>{(m.keywords ?? []).slice(0, 4).join(' · ')}</span>
                    </div>
                    <div style={{ fontSize: 14, marginTop: 4, lineHeight: 1.5 }}>{m.description}</div>
                  </div>
                ))}
              </div>
            )}
            {today && tab === 'schedule' && (today.schedule_md ? <Markdown text={today.schedule_md} /> : <div style={{ color: '#8a897f', fontSize: 13 }}>今天没有日程文件。</div>)}
            {today && tab === 'dream' && (
              <div>
                <div style={{ fontWeight: 600, margin: '4px 0' }}>日摘要</div>
                {today.day_summary_md ? <Markdown text={today.day_summary_md} /> : <div style={{ color: '#8a897f', fontSize: 13 }}>还没有日摘要（她睡着以后 Dream 才会写）。</div>}
                <div style={{ fontWeight: 600, margin: '14px 0 4px' }}>Dream</div>
                {today.dream ? <pre style={{ fontSize: 12, color: '#c3c2b7', whiteSpace: 'pre-wrap', background: '#161615', padding: 10, borderRadius: 8 }}>{JSON.stringify(today.dream, null, 2)}</pre> : <div style={{ color: '#8a897f', fontSize: 13 }}>今天还没有 Dream 记录。</div>}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 详情弹层 */}
      {detail && (
        <div onClick={() => setDetail(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div onClick={e => e.stopPropagation()} style={{ width: 'min(1100px, 94vw)', maxHeight: '88vh', background: '#1a1a19', border: '1px solid #3a3a37', borderRadius: 12, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <div style={{ display: 'flex', alignItems: 'center', padding: '10px 16px', borderBottom: '1px solid #2c2c2a', gap: 10 }}>
              <div style={{ fontWeight: 600 }}>
                {detail.kind === 'loading' ? detail.title : detail.kind === 'prompt' ? `完整输入输出 · ${hhmmss(detail.data.ts)} · ${detail.data.tier ?? ''} · ${detail.data.model ?? ''}` : `记忆全文 · ${hhmm(detail.m.ts)} · ${detail.m.type}`}
              </div>
              {detail.kind === 'prompt' && detail.data.usage && <span style={{ fontSize: 12, color: '#8a897f' }}>in {detail.data.usage.in} · out {detail.data.usage.out} · cache {detail.data.usage.cache_read} · {money(detail.data.cost_usd)}</span>}
              <button onClick={() => setDetail(null)} style={{ ...tabBtn, marginLeft: 'auto' }}>关闭</button>
            </div>
            <div style={{ overflow: 'auto', padding: 16 }}>
              {detail.kind === 'prompt' && (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                  <div>
                    <div style={{ fontSize: 12, color: '#8a897f', marginBottom: 6 }}>输入（system + user，{detail.data.prompt_text.length} 字）</div>
                    <pre style={pre}>{detail.data.prompt_text || '（这次调用没有留下 prompt 文件）'}</pre>
                  </div>
                  <div>
                    <div style={{ fontSize: 12, color: '#8a897f', marginBottom: 6 }}>输出</div>
                    <pre style={pre}>{detail.data.response || '（无正文）'}</pre>
                    <div style={{ fontSize: 12, color: '#8a897f', margin: '10px 0 6px' }}>工具调用</div>
                    <pre style={pre}>{detail.data.tool_calls ? (typeof detail.data.tool_calls === 'string' ? detail.data.tool_calls : JSON.stringify(detail.data.tool_calls, null, 2)) : '（无）'}</pre>
                  </div>
                </div>
              )}
              {detail.kind === 'memory' && (detail.text ? <Markdown text={detail.text} /> : <div style={{ color: '#8a897f', fontSize: 13 }}>{detail.m.description}<br /><br />（没找到对应的 .md 全文{detail.path ? `：${detail.path}` : '：观察服务没给 path，当日导出里也没匹配到'}）</div>)}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

const chip: React.CSSProperties = { background: '#2c2c2a', color: '#e2e2dc', borderRadius: 999, padding: '2px 10px', fontSize: 12 }
const tabBtn: React.CSSProperties = { padding: '5px 12px', borderRadius: 6, border: 'none', background: '#2c2c2a', color: '#f0efec', fontSize: 12, cursor: 'pointer' }
const pre: React.CSSProperties = { fontSize: 12, color: '#e2e2dc', whiteSpace: 'pre-wrap', wordBreak: 'break-word', background: '#161615', padding: 10, borderRadius: 8, maxHeight: '70vh', overflow: 'auto', margin: 0 }
