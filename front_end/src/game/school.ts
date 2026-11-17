/**
 * 上课系统 v1（B world-v1.4.0 §12.25）前端展示用纯函数（不依赖 React / Phaser；单测 `tests/school.test.ts`）。
 * 只把后端给的 meta / result / reason 排成中文，不判断能不能交、算不算迟到——那些都以后端为准。
 */
export const AUDIO_ZH: Record<string, string> = { none: '无音频', pending: '音频待生成', final: '音频已定稿' }
export const CD_STATUS_ZH: Record<string, string> = { pending: '待她听', delivered: '已交付', final: '定稿', redo: '判了重做' }
const WEEKDAY = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

/** "2026-11-27T10:45:00+08:00" → "周五 10:45"（只取字面日期与时刻，不做时区换算） */
export function dueText(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso.slice(0, 10) + 'T00:00:00Z')
  return isNaN(d.getTime()) ? iso : `${WEEKDAY[d.getUTCDay()]} ${iso.slice(11, 16)}`
}

export type NoteSeg = { i: number; text: string | null; status: 'heard' | 'slept' | 'absent' | string }
/** 课堂笔记 meta.segments → 显示行；睡着段 / 没来段给灰字占位（与后端 notes_text 同口径） */
export function noteRows(meta: Record<string, unknown> | undefined): { i: number; text: string; muted: boolean }[] {
  const segs = Array.isArray(meta?.segments) ? (meta!.segments as NoteSeg[]) : []
  return segs.map(s => s.status === 'heard' && s.text
    ? { i: s.i, text: s.text, muted: false }
    : { i: s.i, text: s.status === 'slept' ? '……（这段睡着了）' : s.status === 'absent' ? '（没来）' : '（空）', muted: true })
}

/** CD 创作单（定稿字段 11-16，B / C）：按固定顺序给出有值的行；缺字段不显示 */
const SHEET: [string, string][] = [
  ['homework_week', '作业'], ['genre', '类型'], ['scene', '情境'], ['mood', '情绪'], ['form', '曲式'], ['chords', '和弦进行'], ['lyrics', '歌词'], ['arrangement', '编曲说明'],
]
export function cdSheetRows(meta: Record<string, unknown> | undefined): { key: string; label: string; value: string; long: boolean }[] {
  const out: { key: string; label: string; value: string; long: boolean }[] = []
  if (!meta) return out
  if (typeof meta.status === 'string') out.push({ key: 'status', label: '状态', value: CD_STATUS_ZH[meta.status] ?? meta.status, long: false })
  for (const [k, label] of SHEET) {
    const v = meta[k]
    if (v === null || v === undefined || v === '') continue
    const value = k === 'homework_week' ? `第 ${v} 周作业` : Array.isArray(v) ? v.join(' – ') : String(v)
    out.push({ key: k, label, value, long: k === 'lyrics' || k === 'arrangement' || value.length > 40 })
  }
  return out
}

/** 作业回执 meta → 显示行 */
export function receiptRows(meta: Record<string, unknown> | undefined): { label: string; value: string; warn?: boolean }[] {
  if (!meta) return []
  const rows: { label: string; value: string; warn?: boolean }[] = []
  if (meta.title) rows.push({ label: '曲名', value: `《${meta.title}》` })
  if (meta.week !== undefined && meta.week !== null) rows.push({ label: '周次', value: `第 ${meta.week} 周` })
  if (typeof meta.late === 'boolean') rows.push({ label: '提交', value: meta.late ? '迟交' : '按时', warn: meta.late })
  if (typeof meta.audio === 'string') rows.push({ label: '音频', value: AUDIO_ZH[meta.audio] ?? meta.audio })
  if (typeof meta.due === 'string') rows.push({ label: '截止', value: dueText(meta.due) })
  if (typeof meta.submitted_at === 'string') rows.push({ label: '交于', value: meta.submitted_at.slice(5, 16).replace('T', ' ') })
  if (meta.receipt_id) rows.push({ label: '回执号', value: String(meta.receipt_id) })
  return rows
}

/** 背包里哪些条目可以点开看详情 */
export const hasItemDetail = (it: { type: string; meta?: Record<string, unknown> }) =>
  !!it.meta && (it.type === 'class_notes' || it.type === 'homework_receipt' || it.type === 'cd')

/** 作业提交箱 use 的回包 → 一句中文（成功补截止 / 音频；失败按 reason 翻译，后端带 message 的优先） */
export function homeworkUseText(res: { success?: boolean; reason?: string | null; result?: Record<string, unknown> | null }): string {
  const r = res.result ?? {}
  if (res.success) {
    const extra = [typeof r.due === 'string' ? `截止 ${dueText(r.due)}` : '', typeof r.audio === 'string' && !r.updated ? AUDIO_ZH[r.audio] ?? '' : ''].filter(Boolean).join(' · ')
    return `📮 ${r.message ?? '作业交上了。'}${extra ? `（${extra}）` : ''}`
  }
  if (typeof r.message === 'string' && r.message) return `📮 ${r.message}`
  switch (res.reason) {
    case 'no_item': return '📮 背包里没有可以交的 CD'
    case 'already_submitted': return `📮 这首已经在第 ${r.week ?? '?'} 周交过了，不能再交到这周`
    case 'cd_redo': return '📮 这首判了重做，交重做后的那张'
    case 'no_object_in_front': return '面前没有可使用的对象'
    default: return `📮 交不了（${res.reason ?? '未知原因'}）`
  }
}
