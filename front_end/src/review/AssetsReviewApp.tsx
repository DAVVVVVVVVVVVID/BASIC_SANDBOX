import { useEffect, useState } from 'react'
import { loadAiManifest, aiEnabled, setAiEnabled, type AiManifest } from '../game/aiAssets'

/**
 * `/assets-review`：W8 美术管线评审页。物品：旧自制像素图 vs gpt-image-2 新图并排；底图：平涂版式 / 原始输出 / 对齐 QA 叠图 / 量化后成品 + QA 分数。
 * 「一键替换」= 切 localStorage.aiAssets（旁观 / 操控 / 回放页读它决定用哪套）。生成日志（提示词 / 费用）读 public/assets/gen-ai/gen.jsonl（manifest 命令从 data/assets/gen.jsonl 同步）。
 */
interface GenRow { kind: string; name: string; quality?: string; attempt?: number; qa_score?: number; qa_pass?: boolean; cells_ok?: number; cost_usd_est?: number; usage?: { total_tokens?: number }; latency_s?: number; error?: string; prompt?: string; ts?: string }

function hide(e: React.SyntheticEvent<HTMLImageElement>) { e.currentTarget.style.display = 'none' }

export default function AssetsReviewApp() {
  const [m, setM] = useState<AiManifest | null>(null)
  const [rows, setRows] = useState<GenRow[]>([])
  const [on, setOn] = useState(aiEnabled())
  const [showPrompt, setShowPrompt] = useState<string | null>(null)
  useEffect(() => {
    loadAiManifest().then(setM)
    fetch('assets/gen-ai/gen.jsonl', { cache: 'no-store' }).then(r => r.ok ? r.text() : '').then(t => {
      const parsed: GenRow[] = []
      for (const l of t.split('\n')) { if (!l.trim()) continue; try { parsed.push(JSON.parse(l) as GenRow) } catch { /* skip */ } }
      setRows(parsed)
    }).catch(() => {})
  }, [])
  const byName = new Map<string, GenRow[]>()
  for (const r of rows) { const k = `${r.kind}:${r.name}`; byName.set(k, [...(byName.get(k) ?? []), r]) }
  const cost = rows.reduce((a, r) => a + (r.error ? 0 : (r.cost_usd_est ?? 0)), 0)
  const fails = rows.filter(r => r.error).length
  const qaScores = rows.filter(r => typeof r.qa_score === 'number').map(r => r.qa_score as number)

  return (
    <div style={{ background: '#101010', color: '#f0efec', minHeight: '100vh', fontFamily: 'system-ui, "PingFang SC", sans-serif', padding: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 14 }}>
        <h1 style={{ fontSize: 22, margin: 0 }}>美术评审 · gpt-image-2 管线 v1.0</h1>
        <button onClick={() => { setAiEnabled(!on); setOn(!on) }} style={{ ...btn, background: on ? '#199e70' : '#5b5b58' }}>{on ? '✓ 已启用 AI 素材（点击切回像素版）' : '○ 使用像素版（点击一键替换为 AI 素材）'}</button>
        <span style={{ color: '#8a897f', fontSize: 13 }}>{rows.length} 次生成 · 失败 {fails} · 估算 ${cost.toFixed(2)}{qaScores.length ? ` · 对齐 QA 中位 ${median(qaScores).toFixed(2)}（≥0.9 通过 ${qaScores.filter(s => s >= 0.9).length}/${qaScores.length}）` : ''}</span>
      </div>
      {!m && <div style={{ color: '#8a897f' }}>还没有 manifest（跑 tools/gen_assets_ai.py 后出现）。</div>}
      {m && (
        <>
          <h2 style={h2}>底图（{Object.keys(m.backdrops).length}）</h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(560px, 1fr))', gap: 14 }}>
            {Object.entries(m.backdrops).map(([name, b]) => {
              const log = byName.get(`backdrop:${name}`) ?? []
              const last = log[log.length - 1]
              const spent = log.reduce((a, r) => a + (r.error ? 0 : (r.cost_usd_est ?? 0)), 0)
              return (
                <div key={name} style={card}>
                  <div style={{ display: 'flex', gap: 10, alignItems: 'baseline' }}>
                    <b>{name}</b><span style={{ color: '#8a897f', fontSize: 12 }}>{b.w}×{b.h} 格 · {b.view} · {b.floor}F</span>
                    <span style={{ marginLeft: 'auto', fontSize: 12, color: (b.qa_score ?? 0) >= 0.9 ? '#68d391' : '#f6ad55' }}>QA {b.qa_score?.toFixed(3) ?? '–'}{last ? ` · ${log.length} 次 · $${spent.toFixed(2)}` : ''}</span>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 6, marginTop: 8 }}>
                    {[['平涂版式', `assets/gen-ai/review/${name}_input.png`], ['原始输出', `assets/gen-ai/review/${name}_raw.png`], ['对齐 QA（红=丢失）', `assets/gen-ai/review/${name}_qa.png`], ['成品（32px/格 ≤64 色）', `assets/gen-ai/backdrops/${name}.png`]].map(([lab, src]) => (
                      <div key={lab}><div style={{ fontSize: 11, color: '#8a897f', marginBottom: 3 }}>{lab}</div><img src={src} alt={lab} onError={hide} style={{ width: '100%', imageRendering: 'pixelated', background: '#222', borderRadius: 6 }} /></div>
                    ))}
                  </div>
                  {last?.prompt && <button onClick={() => setShowPrompt(last.prompt!)} style={{ ...btn, marginTop: 6, fontSize: 11 }}>看提示词</button>}
                </div>
              )
            })}
          </div>
          {m.chars.length > 0 && (
            <>
              <h2 style={h2}>角色四向表（{m.chars.length}）· 左旧像素表 → 新 AI 表（32×48/帧，4 列 × 5 行：下 / 左 / 右 / 上 / 坐睡）· 右：姿态版式与原始输出</h2>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(560px, 1fr))', gap: 12 }}>
                {m.chars.map(k => {
                  const log = byName.get(`char:${k}`) ?? []
                  const last = log[log.length - 1]
                  const spent = log.reduce((a, r) => a + (r.error ? 0 : (r.cost_usd_est ?? 0)), 0)
                  return (
                    <div key={k} style={card}>
                      <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}><b>{k}</b><span style={{ color: '#8a897f', fontSize: 12 }}>{CHAR_NAMES[k] ?? ''}</span><span style={{ marginLeft: 'auto', color: '#8a897f', fontSize: 12 }}>{last ? `${log.length} 次 · $${spent.toFixed(2)} · 格 ${last.cells_ok ?? '–'}/15` : ''}</span></div>
                      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', marginTop: 8, background: '#2a3a2a', padding: 8, borderRadius: 6 }}>
                        <img src={`assets/gen/char_${k === 'whale' || k === 'achan' ? `${k}_v1` : k}.png`} alt="old" onError={hide} style={{ height: 300, imageRendering: 'pixelated' }} />
                        <span style={{ color: '#8a897f', alignSelf: 'center' }}>→</span>
                        <img src={`assets/gen-ai/chars/${k}.png`} alt="new" onError={hide} style={{ height: 300, imageRendering: 'pixelated' }} />
                        <img src={`assets/gen-ai/review/char_${k}_input.png`} alt="input" onError={hide} style={{ height: 300, marginLeft: 'auto', borderRadius: 4, opacity: 0.8 }} />
                        <img src={`assets/gen-ai/review/char_${k}_raw.png`} alt="raw" onError={hide} style={{ height: 300, borderRadius: 4 }} />
                      </div>
                      {last?.prompt && <button onClick={() => setShowPrompt(last.prompt!)} style={{ ...btn, marginTop: 6, fontSize: 11 }}>看提示词</button>}
                    </div>
                  )
                })}
              </div>
            </>
          )}
          <h2 style={h2}>物品（{m.objects.length}）· 左旧右新 · 最右原始输出</h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 12 }}>
            {m.objects.map(t => {
              const log = byName.get(`object:${t}`) ?? []
              const last = log[log.length - 1]
              return (
                <div key={t} style={card}>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}><b>{t}</b><span style={{ marginLeft: 'auto', color: '#8a897f', fontSize: 12 }}>{last ? `$${(last.cost_usd_est ?? 0).toFixed(2)} · ${last.latency_s ?? '–'}s` : ''}</span></div>
                  <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', marginTop: 8, background: '#2a3a2a', padding: 8, borderRadius: 6, overflow: 'hidden' }}>
                    <img src={`assets/gen/obj_${t}.png`} alt="old" onError={hide} style={{ ...objImg, imageRendering: 'pixelated' }} />
                    <span style={{ color: '#8a897f' }}>→</span>
                    <img src={`assets/gen-ai/objects/${t}.png`} alt="new" onError={hide} style={{ ...objImg, imageRendering: 'pixelated' }} />
                    <img src={`assets/gen-ai/review/obj_${t}_raw.png`} alt="raw" onError={hide} style={{ ...objImg, marginLeft: 'auto', borderRadius: 4, opacity: 0.9 }} />
                  </div>
                  {last?.prompt && <button onClick={() => setShowPrompt(last.prompt!)} style={{ ...btn, marginTop: 6, fontSize: 11 }}>看提示词</button>}
                </div>
              )
            })}
          </div>
        </>
      )}
      {showPrompt && (
        <div onClick={() => setShowPrompt(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <pre onClick={e => e.stopPropagation()} style={{ maxWidth: 900, whiteSpace: 'pre-wrap', background: '#1a1a19', padding: 16, borderRadius: 10, fontSize: 13, color: '#e2e2dc' }}>{showPrompt}</pre>
        </div>
      )}
    </div>
  )
}
const CHAR_NAMES: Record<string, string> = { whale: '鲸仔', achan: '阿蝉', cook: '餐厅老板', grocer: '杂货店老板（女）', fisher: '老渔夫', regular: '千小满（小千）', villager: '村民' }
const btn: React.CSSProperties = { padding: '6px 12px', borderRadius: 6, border: 'none', background: '#2c2c2a', color: '#f0efec', fontSize: 13, cursor: 'pointer' }
const objImg: React.CSSProperties = { height: 96, maxWidth: '34%', objectFit: 'contain', objectPosition: 'bottom', flex: '0 1 auto' }
const card: React.CSSProperties = { background: '#1a1a19', border: '1px solid #2c2c2a', borderRadius: 10, padding: 12 }
const h2: React.CSSProperties = { fontSize: 16, margin: '18px 0 8px', color: '#c3c2b7' }
function median(a: number[]) { const s = [...a].sort((x, y) => x - y); return s[Math.floor(s.length / 2)] }
