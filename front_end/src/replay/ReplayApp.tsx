import { useEffect, useRef, useState } from 'react'
import { loadReplay, approximateTrack, ReplayData, PosSample } from './data'
import { zoneLabel } from '../game/map/zones'
import type { Tile } from '../types'

/**
 * 回放页 `/replay?town=main&date=2026-11-06[&speed=8|60|fit][&export=1]`：
 * 把一天的行动、聊天、七变量曲线、记忆写入与思考摘要按时间轴回放，可拖动、1× / 8× / 60× / 整天压成 60 s；
 * 「导出 1 分钟 webm」用 MediaRecorder 录整张画布。只读导出件，不碰运行态。
 */

const W = 1600, H = 900
const MAP_X = 24, MAP_Y = 72, MAP_W = 780
const CHART_X = 840, CHART_Y = 72, CHART_W = 736, CHART_H = 230
// 七变量：固定顺序与颜色（dataviz 参考调色板·暗色），文字一律用文本色
const SERIES: { key: string; label: string; color: string }[] = [
  { key: 'fullness', label: '饱腹', color: '#d95926' },
  { key: 'energy',   label: '精力', color: '#3987e5' },
  { key: 'social',   label: '社交', color: '#d55181' },
  { key: 'fun',      label: '乐趣', color: '#199e70' },
  { key: 'mood',     label: '心情', color: '#c98500' },
]
const TILE_COLORS: Record<string, string> = {
  grass: '#7fb87a', grass1: '#6ea36d', floor: '#d9b98c', object: '#c9a673', wall: '#7a6a63', water: '#6aa2d6',
}
const ARENA_COLORS: Record<string, string> = { road: '#b9a98a', square: '#cfc3ad', dock: '#b48a5a', park: '#73ad72', dining: '#b86a62', grocer_shop: '#cdb48f' }

function fmtClock(t: number) {
  const d = new Date(t)
  return d.toLocaleTimeString('zh-CN', { hour12: false, timeZone: 'Asia/Shanghai' })
}

/** 解析一次 URL 参数（模块级，避免在 render 里调用 Date.now） */
function readParams() {
  const q = new URLSearchParams(window.location.search)
  const town = (q.get('town') || 'main').replace(/[^a-z0-9_-]/gi, '')
  const date = /^\d{4}-\d{2}-\d{2}$/.test(q.get('date') || '') ? q.get('date')! : new Date(Date.now() - 86400000).toISOString().slice(0, 10)
  return { q, town, date }
}
const PARAMS = readParams()

export default function ReplayApp() {
  const { q, town, date } = PARAMS
  const autoExport = q.get('export') === '1'
  const initialSpeed = q.get('speed') === 'fit' ? 'fit' : Number(q.get('speed') || 8)

  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [data, setData] = useState<ReplayData | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [playing, setPlaying] = useState(true)
  const [speed, setSpeed] = useState<number | 'fit'>(initialSpeed)
  const [cursor, setCursor] = useState(0)          // 0..1
  const [exporting, setExporting] = useState(false)
  const stateRef = useRef({ playing: true, speed: initialSpeed as number | 'fit', cursor: 0 })
  stateRef.current = { playing, speed, cursor }
  const trackRef = useRef<PosSample[]>([])
  const tileIndex = useRef(new Map<string, Tile>())

  useEffect(() => {
    loadReplay(town, date).then(d => {
      trackRef.current = approximateTrack(d, { x: 6, y: 9 })
      tileIndex.current = new Map(d.tiles.map(t => [`${t.x},${t.y}`, t]))
      setData(d)
    }).catch(e => setErr(String(e)))
  }, [town, date])

  // ── 时间推进 ──
  useEffect(() => {
    if (!data) return
    let raf = 0, last = performance.now()
    const tick = (now: number) => {
      const dt = now - last; last = now
      const s = stateRef.current
      if (s.playing) {
        const span = data.t1 - data.t0
        const rate = s.speed === 'fit' ? span / 60000 : s.speed       // 回放毫秒 / 真实毫秒
        const next = s.cursor + (dt * rate) / span
        if (next >= 1) { setCursor(1); setPlaying(false) } else setCursor(next)
      }
      draw()
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data])

  // ── 导出：整天压 60 s 录成 webm ──
  const recorderRef = useRef<MediaRecorder | null>(null)
  function startExport() {
    const c = canvasRef.current
    if (!c || exporting) return
    const stream = c.captureStream(30)
    const mime = ['video/webm;codecs=vp8', 'video/webm;codecs=vp9', 'video/webm'].find(m => MediaRecorder.isTypeSupported(m)) ?? 'video/webm'
    const rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 6_000_000 })
    const chunks: Blob[] = []
    rec.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data) }
    rec.onstop = () => {
      const blob = new Blob(chunks, { type: 'video/webm' })
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `replay_${town}_${date}.webm`
      document.body.appendChild(a); a.click(); a.remove()
      setExporting(false)
    }
    recorderRef.current = rec
    setExporting(true)
    setCursor(0); setSpeed('fit'); setPlaying(true)
    rec.start(1000)
    // 61 s 后停（整天 60 s + 收尾 1 s）
    window.setTimeout(() => { if (rec.state !== 'inactive') rec.stop() }, 61000)
  }
  useEffect(() => { if (data && autoExport) window.setTimeout(startExport, 800) /* eslint-disable-line react-hooks/exhaustive-deps */ }, [data])

  // ── 绘制 ──
  function draw() {
    const c = canvasRef.current, d = data
    if (!c || !d) return
    const g = c.getContext('2d')!
    const s = stateRef.current
    const t = d.t0 + s.cursor * (d.t1 - d.t0)
    g.fillStyle = '#1a1a19'; g.fillRect(0, 0, W, H)

    // 标题行
    g.fillStyle = '#f0efec'; g.font = '600 26px system-ui, "PingFang SC", "Microsoft YaHei", sans-serif'; g.textBaseline = 'top'
    g.fillText(`鲸仔的一天 · ${d.town} · ${d.date}`, MAP_X, 20)
    g.font = '22px system-ui, sans-serif'; g.fillStyle = '#c3c2b7'
    g.fillText(fmtClock(t), MAP_X + 520, 22)
    g.font = '14px system-ui, sans-serif'
    g.fillText(`${s.speed === 'fit' ? '整天 → 60 s' : s.speed + '×'}${s.playing ? '' : ' · 暂停'}`, MAP_X + 640, 28)

    // 地图
    const mapW = Math.max(1, ...d.tiles.map(x => x.x + 1)), mapH = Math.max(1, ...d.tiles.map(x => x.y + 1))
    const cell = Math.floor(Math.min(MAP_W / mapW, 560 / mapH))
    const mx = MAP_X, my = MAP_Y
    for (const tile of d.tiles) {
      g.fillStyle = (tile.arena && ARENA_COLORS[tile.arena] && tile.type !== 'wall' && tile.type !== 'water') ? ARENA_COLORS[tile.arena] : (TILE_COLORS[tile.type] ?? '#888')
      g.fillRect(mx + tile.x * cell, my + tile.y * cell, cell, cell)
    }
    for (const o of d.objects) {
      g.fillStyle = 'rgba(60,40,20,0.55)'
      for (const p of (o.tiles && o.tiles.length ? o.tiles : [o.position])) g.fillRect(mx + p.x * cell + 1, my + p.y * cell + 1, cell - 2, cell - 2)
    }
    // 轨迹与当前位置
    const track = trackRef.current
    let cur: PosSample | null = null
    g.strokeStyle = 'rgba(57,135,229,0.55)'; g.lineWidth = 2; g.beginPath()
    let started = false
    for (const p of track) {
      if (p.t > t) break
      const px = mx + (p.pos.x + 0.5) * cell, py = my + (p.pos.y + 0.5) * cell
      if (!started) { g.moveTo(px, py); started = true } else g.lineTo(px, py)
      cur = p
    }
    g.stroke()
    if (cur) {
      const px = mx + (cur.pos.x + 0.5) * cell, py = my + (cur.pos.y + 0.5) * cell
      g.fillStyle = '#1a1a19'; g.beginPath(); g.arc(px, py, cell * 0.9, 0, Math.PI * 2); g.fill()
      g.fillStyle = '#3987e5'; g.beginPath(); g.arc(px, py, cell * 0.7, 0, Math.PI * 2); g.fill()
      g.fillStyle = '#f0efec'; g.font = '600 14px system-ui, sans-serif'; g.textAlign = 'center'
      const zt = tileIndex.current.get(`${cur.pos.x},${cur.pos.y}`)
      g.fillText(`鲸仔 · ${zoneLabel(zt) || '?'}`, px, py - cell * 0.9 - 18)
      g.textAlign = 'left'
    }
    g.fillStyle = '#8a897f'; g.font = '12px system-ui, sans-serif'
    g.fillText(d.positions.length ? (cur && d.positions.some(p => p.t <= cur.t) ? '位置：沙盒 state 样本' : '位置：按行动日志近似推算（state 样本从 ' + fmtClock(d.positions[0].t).slice(0, 5) + ' 起）') : '位置：按行动日志近似推算（move / move_to_area）', mx, my + mapH * cell + 8)

    // 七变量折线
    drawChart(g, d, t)

    // 思考 / 计划
    const ep = [...d.episodes].reverse().find(e => e.t0 <= t)
    const bx = CHART_X, by = CHART_Y + CHART_H + 40
    g.fillStyle = '#242423'; roundRect(g, bx, by, CHART_W, 150, 10); g.fill()
    g.fillStyle = '#c3c2b7'; g.font = '600 14px system-ui, sans-serif'; g.fillText('她在想', bx + 16, by + 12)
    g.fillStyle = '#f0efec'; g.font = '16px system-ui, "PingFang SC", sans-serif'
    if (ep) {
      wrapText(g, `计划：${ep.plan || '—'}`, bx + 16, by + 38, CHART_W - 32, 22, 2)
      wrapText(g, ep.thought ? `想法：${ep.thought}` : `动作：${ep.action || '—'}`, bx + 16, by + 86, CHART_W - 32, 22, 2)
      g.fillStyle = '#8a897f'; g.font = '12px system-ui, sans-serif'
      g.fillText(`${fmtClock(ep.t0)}${ep.model ? ' · ' + ep.model : ''}${ep.cost !== undefined ? ' · $' + ep.cost.toFixed(3) : ''}`, bx + 16, by + 130)
    } else {
      g.fillStyle = '#8a897f'; g.fillText('（这个时刻还没有思考记录）', bx + 16, by + 40)
    }

    // 事件流：最近 10 条（记忆写入 / 行动 / 聊天），按时间倒序
    const fy = by + 170
    g.fillStyle = '#242423'; roundRect(g, bx, fy, CHART_W, H - fy - 24, 10); g.fill()
    g.fillStyle = '#c3c2b7'; g.font = '600 14px system-ui, sans-serif'; g.fillText('发生了什么', bx + 16, fy + 12)
    const feed: { t: number; text: string; kind: 'mem' | 'act' | 'chat' }[] = []
    for (const e of d.events) if (e.t <= t) feed.push({ t: e.t, text: `📝 ${e.description}`, kind: 'mem' })
    for (const a of d.actions) if (a.t <= t && d.whaleIds.has(a.entity) && a.type !== 'move' && a.type !== 'turn') feed.push({ t: a.t, text: `${a.success ? '▶' : '✖'} ${a.label ?? a.type}${a.type === 'move_to_area' ? ' → ' + zoneLabel({ sector: null, arena: String(a.payload.area_id ?? '') }) : ''}${a.success ? '' : '（' + (a.reason ?? '失败') + '）'}`, kind: 'act' })
    for (const c of d.chat) if (c.t <= t && c.kind === 'message') feed.push({ t: c.t, text: `💬 ${c.from_name ?? c.from}：${c.text}`, kind: 'chat' })
    feed.sort((a, b) => b.t - a.t)
    g.font = '14px system-ui, "PingFang SC", sans-serif'
    feed.slice(0, 11).forEach((f, i) => {
      g.fillStyle = '#8a897f'; g.fillText(fmtClock(f.t).slice(0, 5), bx + 16, fy + 40 + i * 24)
      g.fillStyle = f.kind === 'chat' ? '#f0efec' : f.kind === 'mem' ? '#c3c2b7' : '#9a9a90'
      g.fillText(ellipsis(g, f.text, CHART_W - 90), bx + 66, fy + 40 + i * 24)
    })

    // 底部时间轴
    const tx = MAP_X, ty = H - 40, tw = W - MAP_X * 2
    g.fillStyle = '#2c2c2a'; g.fillRect(tx, ty, tw, 6)
    g.fillStyle = '#3987e5'; g.fillRect(tx, ty, tw * s.cursor, 6)
    g.fillStyle = '#8a897f'; g.font = '12px system-ui, sans-serif'
    g.fillText(fmtClock(d.t0), tx, ty + 12); g.textAlign = 'right'; g.fillText(fmtClock(d.t1), tx + tw, ty + 12); g.textAlign = 'left'
    for (const e of d.episodes) { g.fillStyle = 'rgba(201,133,0,0.7)'; g.fillRect(tx + tw * ((e.t0 - d.t0) / (d.t1 - d.t0)), ty - 6, 2, 5) }
    for (const c of d.chat) if (c.kind === 'message') { g.fillStyle = '#d55181'; g.fillRect(tx + tw * ((c.t - d.t0) / (d.t1 - d.t0)), ty - 12, 2, 10) }
  }

  function drawChart(g: CanvasRenderingContext2D, d: ReplayData, t: number) {
    const x0 = CHART_X, y0 = CHART_Y, w = CHART_W, h = CHART_H
    g.fillStyle = '#242423'; roundRect(g, x0, y0, w, h, 10); g.fill()
    g.fillStyle = '#c3c2b7'; g.font = '600 14px system-ui, sans-serif'; g.fillText('七变量（0–100）', x0 + 16, y0 + 12)
    const px0 = x0 + 48, px1 = x0 + w - 16, py0 = y0 + 40, py1 = y0 + h - 28
    g.strokeStyle = '#2c2c2a'; g.lineWidth = 1
    for (const v of [0, 50, 100]) {
      const y = py1 - (v / 100) * (py1 - py0)
      g.beginPath(); g.moveTo(px0, y); g.lineTo(px1, y); g.stroke()
      g.fillStyle = '#8a897f'; g.font = '11px system-ui, sans-serif'; g.textAlign = 'right'; g.fillText(String(v), px0 - 6, y - 6); g.textAlign = 'left'
    }
    const span = d.t1 - d.t0
    const X = (tt: number) => px0 + ((tt - d.t0) / span) * (px1 - px0)
    for (const srs of SERIES) {
      g.strokeStyle = srs.color; g.lineWidth = 2; g.beginPath()
      let started = false
      for (const sm of d.vars) {
        if (sm.t > t) break
        const v = sm.vars[srs.key]; if (typeof v !== 'number') continue
        const x = X(sm.t), y = py1 - (Math.max(0, Math.min(100, v)) / 100) * (py1 - py0)
        if (!started) { g.moveTo(x, y); started = true } else g.lineTo(x, y)
      }
      g.stroke()
    }
    // 游标与当前值
    const cx = X(t)
    g.strokeStyle = '#f0efec'; g.lineWidth = 1; g.beginPath(); g.moveTo(cx, py0); g.lineTo(cx, py1); g.stroke()
    const last = [...d.vars].reverse().find(v => v.t <= t)
    // 图例（固定顺序，直接标值）
    let lx = px0
    g.font = '12px system-ui, sans-serif'
    for (const srs of SERIES) {
      g.fillStyle = srs.color; roundRect(g, lx, py1 + 10, 12, 12, 3); g.fill()
      g.fillStyle = '#c3c2b7'
      const val = last ? Math.round(last.vars[srs.key] ?? 0) : '–'
      const txt = `${srs.label} ${val}`
      g.fillText(txt, lx + 16, py1 + 9)
      lx += 16 + g.measureText(txt).width + 18
    }
    if (d.vars.length === 0) { g.fillStyle = '#8a897f'; g.fillText('（当天没有七变量样本）', px0 + 16, py0 + 16) }
  }

  return (
    <div style={{ background: '#101010', minHeight: '100vh', color: '#f0efec', fontFamily: 'system-ui, sans-serif', padding: 16 }}>
      <canvas ref={canvasRef} width={W} height={H} style={{ width: '100%', maxWidth: W, display: 'block', margin: '0 auto', borderRadius: 12, background: '#1a1a19' }} />
      <div style={{ maxWidth: W, margin: '12px auto 0', display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <button onClick={() => setPlaying(p => !p)} style={btn}>{playing ? '⏸ 暂停' : '▶ 播放'}</button>
        {([1, 8, 60, 'fit'] as const).map(v => (
          <button key={String(v)} onClick={() => setSpeed(v)} style={{ ...btn, background: speed === v ? '#3987e5' : '#2c2c2a' }}>{v === 'fit' ? '整天→60 s' : `${v}×`}</button>
        ))}
        <input type="range" min={0} max={1000} value={Math.round(cursor * 1000)} onChange={e => { setCursor(Number(e.target.value) / 1000) }} style={{ flex: 1, minWidth: 240 }} />
        <button onClick={startExport} disabled={exporting || !data} style={{ ...btn, background: exporting ? '#555' : '#199e70' }}>{exporting ? '录制中（60 s）…' : '导出 1 分钟 webm'}</button>
      </div>
      <div style={{ maxWidth: W, margin: '8px auto 0', color: '#8a897f', fontSize: 12 }}>
        {err && <span style={{ color: '#d95926' }}>加载失败：{err}</span>}
        {data && <span>数据：七变量 {data.vars.length} 点 · 思考 {data.episodes.length} 段 · 记忆 {data.events.length} 条 · 行动 {data.actions.length} 条 · 聊天 {data.chat.filter(c => c.kind === 'message').length} 条{data.notes.length ? ' · ' + data.notes.join('；') : ''}</span>}
        {!data && !err && <span>加载 /dataset/{town}/{date} …</span>}
      </div>
    </div>
  )
}

const btn: React.CSSProperties = { padding: '6px 14px', borderRadius: 6, border: 'none', background: '#2c2c2a', color: '#f0efec', fontSize: 13, cursor: 'pointer' }

function roundRect(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r); g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath()
}
function ellipsis(g: CanvasRenderingContext2D, s: string, maxW: number) {
  if (g.measureText(s).width <= maxW) return s
  let out = s
  while (out.length > 1 && g.measureText(out + '…').width > maxW) out = out.slice(0, -1)
  return out + '…'
}
function wrapText(g: CanvasRenderingContext2D, s: string, x: number, y: number, maxW: number, lh: number, maxLines: number) {
  let line = '', lines = 0
  for (const ch of s) {
    if (g.measureText(line + ch).width > maxW) {
      if (lines === maxLines - 1) { g.fillText(ellipsis(g, line + ch, maxW), x, y + lines * lh); return }
      g.fillText(line, x, y + lines * lh); lines++; line = ch
    } else line += ch
  }
  if (line) g.fillText(line, x, y + lines * lh)
}
