import { useEffect, useRef, useState } from 'react'
import { useGameStore } from '../../store/gameStore'
import { EventBus } from '../../game/EventBus'
import { fetchSchoolToday } from '../../api/school'
import type { SchoolToday } from '../../types'
import { C } from './theme'
import { AUDIO_ZH as AUDIO, dueText } from '../../game/school'

/**
 * 上课系统 v1（总控 11-16 派，B world-v1.4.0 §12.25）：今日课表小卡。
 * 桌面挂「镇上的人」顶部，手机挂顶条下拉。只读 GET /school/today?player=（30 s 一次 + ws lesson 事件后 1 s 补拉）；后端没有该接口时整卡不显示。
 * 作业一栏看「此刻跟随的学生」，没跟学生时看鲸仔。考勤 / 状态全照后端给的显示，前端不判断。
 */
const STUDENT_ZH: Record<string, string> = { whale: '鲸仔', claudine: '小克' }
const STATUS: Record<string, { text: string; bg: string; fg: string }> = {
  upcoming: { text: '未开始', bg: '#EDE3D2', fg: '#7A6A5A' },
  ongoing: { text: '上课中', bg: '#3BB7A8', fg: '#fff' },
  done: { text: '已下课', bg: '#E3F0FB', fg: '#2F5E8A' },
}
const ATT: Record<string, { text: string; color: string }> = {
  present: { text: '✓ 出勤', color: '#2E8B57' },
  late: { text: '⏰ 迟到', color: '#C57B12' },
  absent: { text: '✗ 缺课', color: '#D9534F' },
}
export default function SchoolCard({ follow, compact = false }: { follow: string | null; compact?: boolean }) {
  const players = useGameStore((s) => s.players)
  const followAgent = follow ? players.find(p => p.id === follow)?.agent_id ?? null : null
  const target = followAgent && STUDENT_ZH[followAgent] ? followAgent : 'whale'
  const [data, setData] = useState<SchoolToday | null>(null)
  const [missing, setMissing] = useState(false)
  const [open, setOpen] = useState(() => localStorage.getItem('school-card-open') !== '0')
  const timer = useRef<number | null>(null)
  useEffect(() => {
    let dead = false
    // 带 player 失败（学生不在镇上 → 404）就退回不带 player（只有课表与考勤）；那也失败 = 老后端没有 /school，整卡不显示
    const load = () => fetchSchoolToday(target)
      .catch(() => fetchSchoolToday(null))
      .then(r => { if (!dead) { setData(r); setMissing(false) } })
      .catch(() => { if (!dead) setMissing(true) })
    load()
    const iv = window.setInterval(load, 30_000)
    const onLesson = () => { if (timer.current !== null) window.clearTimeout(timer.current); timer.current = window.setTimeout(load, 1000) }
    EventBus.on('lesson-event', onLesson)
    return () => { dead = true; window.clearInterval(iv); EventBus.off('lesson-event', onLesson); if (timer.current !== null) window.clearTimeout(timer.current) }
  }, [target])
  if (missing || !data) return null
  const nameOf = (agent: string) => {
    const p = players.find(x => x.agent_id === agent)
    return STUDENT_ZH[agent] ?? (p ? p.name.replace(/_[0-9a-f]{6}$/i, '') : agent)
  }
  const toggle = () => setOpen(o => { localStorage.setItem('school-card-open', o ? '0' : '1'); return !o })
  const hw = data.homework
  const fs = compact ? 13 : 14
  return (
    <div data-testid="school-card" onClick={e => e.stopPropagation()} style={{ background: 'rgba(255,255,255,0.7)', border: `1px solid ${C.sky}`, borderRadius: 8, padding: compact ? '6px 8px' : '8px 10px', marginBottom: compact ? 0 : 8, color: C.ink, fontSize: fs }}>
      <div onClick={toggle} style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
        <b>📚 今日课表</b>
        {data.week ? <span style={{ fontSize: 12, color: C.inkSoft }}>第 {data.week} 周 · {data.week_genre}</span> : <span style={{ fontSize: 12, color: C.inkSoft }}>还没开学</span>}
        <span style={{ marginLeft: 'auto', fontSize: 12, color: C.inkSoft }}>{open ? '收起 ▴' : `${data.lessons.length} 节 ▾`}</span>
      </div>
      {open && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginTop: 6 }}>
          {data.lessons.length === 0 && <div style={{ color: C.inkSoft, fontSize: 12 }}>今天没有课</div>}
          {data.lessons.map(l => {
            const st = STATUS[l.status] ?? { text: l.status, bg: '#EDE3D2', fg: C.ink }
            return (
              <div key={l.lesson_id} data-testid={`school-lesson-${l.lesson_id}`} style={{ display: 'flex', flexDirection: 'column', gap: 2, padding: '4px 6px', borderRadius: 6, background: l.status === 'ongoing' ? '#E6F6F3' : 'transparent' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                  <span style={{ fontSize: 12, color: C.inkSoft, whiteSpace: 'nowrap' }}>{l.start}–{l.end}</span>
                  <b style={{ whiteSpace: 'nowrap' }}>{l.course_name}</b>
                  {l.title && l.title !== l.course_name && <span style={{ fontSize: 12, color: C.inkSoft, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }} title={l.title}>{l.title}</span>}
                  <span style={{ marginLeft: 'auto', fontSize: 11, padding: '1px 7px', borderRadius: 9, background: st.bg, color: st.fg, whiteSpace: 'nowrap', flexShrink: 0 }}>{st.text}</span>
                </div>
                <div style={{ display: 'flex', gap: 10, fontSize: 12, flexWrap: 'wrap' }}>
                  {Object.entries(l.attendance).map(([agent, a]) => {
                    const t = a ? ATT[a] ?? { text: String(a), color: C.inkSoft } : { text: '—', color: C.inkSoft }
                    return <span key={agent}>{nameOf(agent)} <span style={{ color: t.color }}>{t.text}</span></span>
                  })}
                </div>
              </div>
            )
          })}
          {hw && (
            <div data-testid="school-homework" style={{ borderTop: '1px dashed #E6DCCB', paddingTop: 5, fontSize: 12 }}>
              <div>📝 {nameOf(target)}第 {hw.week} 周作业：已交 <b>{hw.count}</b> 首{hw.due ? <span style={{ color: C.inkSoft }}> · 截止 {dueText(hw.due)}</span> : null}</div>
              {hw.submitted.map(s => (
                <div key={s.receipt_id} style={{ color: C.inkSoft, paddingLeft: 16, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  《{s.title ?? s.request_id}》{s.late ? <span style={{ color: '#D9534F' }}> 迟交</span> : ' 按时'} · {AUDIO[s.audio] ?? s.audio}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
