/**
 * 小镇导播 · 三期纯函数（town-director-plan §2：上课 / 写歌做稿 / QQ / 睡觉「今天的她」；单测 tests/director.test.ts）。
 * C 的 player.now 上主镇前，情境从 ws 现有的 usingObjectId + 物件类型 + tags 推。
 */

/** 物件类型 → C 的 activity 口径（没有 now 时兜底） */
const TYPE_ACTIVITY: Record<string, string> = {
  pc_music: 'create', pc: 'create', pc_desk: 'create', stream_desk: 'create',
  phone: 'qq', fishing_spot: 'fishing', classroom_desk: 'class',
  dining_table: 'eat', restaurant_table: 'eat',
}
export function activityFromWorld(usingType: string | null | undefined, tags: string[] | null | undefined): string | null {
  const t = tags ?? []
  if (t.includes('sleeping')) return 'sleep'
  if (t.includes('streaming')) return 'live'
  if (t.includes('in_class')) return 'class'
  if (t.includes('reading')) return 'qq'   // 读 QQ 占用 1 游戏分钟（v1.4.27 边走边看）
  if (!usingType) return null
  if (/^bed/.test(usingType)) return 'sleep'
  return TYPE_ACTIVITY[usingType] ?? null
}

/** 坐满门槛（economy production：compose 30 / make_video 60 游戏分钟） */
export function createKind(usingType: string | null | undefined): { kind: 'song' | 'script'; needMin: number; icon: string; verb: string } | null {
  if (usingType === 'pc_music') return { kind: 'song', needMin: 30, icon: 'icon_cd', verb: '写歌' }
  if (usingType === 'pc' || usingType === 'pc_desk' || usingType === 'stream_desk') return { kind: 'script', needMin: 60, icon: 'icon_script', verb: '做稿' }
  return null
}

/**
 * 坐满进度：后端不给「这次坐下的起点」，用 daily_use[type].used_min 的增量算——第一次看到她坐在这件物件上时记基线。
 * 返回新基线表（不改原表）与 0–1 进度、已坐分钟。页面中途打开时从打开那刻算起（偏小，不会超）。
 */
export interface CreateBase { obj: string; base: number }
export function createProgress(prev: CreateBase | undefined, obj: string, usedMin: number | null | undefined, needMin: number): { base: CreateBase; progress: number | null; sat: number | null } {
  if (typeof usedMin !== 'number') return { base: prev ?? { obj, base: NaN }, progress: null, sat: null }
  const base = !prev || prev.obj !== obj || !Number.isFinite(prev.base) || usedMin < prev.base ? { obj, base: usedMin } : prev
  const sat = Math.max(0, usedMin - base.base)
  return { base, progress: Math.min(1, sat / needMin), sat }
}

/** 背包里最新一张 CD / 稿子（产出弹卡、「上一首」用）：标题 + 歌词 / 提纲前几行（去掉 [Verse] 这类段标） */
export function latestWork(inventory: unknown, kind: 'song' | 'script'): { title: string; lines: string[] } | null {
  if (!Array.isArray(inventory)) return null
  const want = kind === 'song' ? /^cd$|song/ : /script/
  let best: { title: string; text: string; at: string } | null = null
  for (const it of inventory as { type?: string; item?: string; meta?: { title?: string; text?: string; created_at?: string } }[]) {
    const k = String(it?.type ?? it?.item ?? '')
    if (!want.test(k) || !it.meta?.title) continue
    const at = String(it.meta.created_at ?? '')
    if (!best || at >= best.at) best = { title: it.meta.title, text: String(it.meta.text ?? ''), at }
  }
  if (!best) return null
  const lines = best.text.split('\n').map(l => l.trim()).filter(l => l && !/^\[.*\]$/.test(l) && !/^#/.test(l))
  return { title: best.title, lines: lines.slice(0, 4) }
}

/** 「今天的她」：GET /player/{id} 里当天能拿到的数（daily_use / fishing / today_sales）+ 页面自己记的聊天对象与事件 */
export interface SummaryRow { icon: string; label: string; value: string }
export function todaySummaryRows(p: Record<string, unknown> | null, chattedWith: string[], eventTexts: string[]): SummaryRow[] {
  const rows: SummaryRow[] = []
  const du = (p?.daily_use ?? {}) as Record<string, { used_min?: number; used_count?: number }>
  const min = (k: string) => Math.round(du[k]?.used_min ?? 0)
  const songs = du.compose?.used_count ?? 0
  if (min('pc_music') > 0 || songs > 0) rows.push({ icon: '🎵', label: '写歌', value: `${min('pc_music')} 分钟${songs ? ` · 写好 ${songs} 首` : ''}` })
  if (min('pc') + min('pc_desk') > 0) rows.push({ icon: '💻', label: '电脑前', value: `${min('pc') + min('pc_desk')} 分钟` })
  if (min('stream_desk') > 0) rows.push({ icon: '📺', label: '直播台', value: `${min('stream_desk')} 分钟` })
  if (min('phone') > 0) rows.push({ icon: '📱', label: '看手机', value: `${min('phone')} 分钟` })
  const f = (p?.fishing ?? {}) as { casts_today?: number; minutes_today?: number; recent_casts?: { result?: string; fish?: { name?: string } | null }[] }
  if ((f.casts_today ?? 0) > 0) {
    const fish = (f.recent_casts ?? []).filter(c => c.result === 'fish' && c.fish?.name).map(c => c.fish!.name!)
    rows.push({ icon: '🎣', label: '钓鱼', value: `${f.casts_today} 竿${fish.length ? ` · 钓到 ${[...new Set(fish)].slice(0, 3).join('、')}` : ''}` })
  }
  if (min('sofa_tv') + min('game_console') > 0) rows.push({ icon: '🛋', label: '看电视 / 打游戏', value: `${min('sofa_tv') + min('game_console')} 分钟` })
  const s = (p?.today_sales ?? {}) as { count?: number; gold?: number }
  if ((s.count ?? 0) > 0) rows.push({ icon: '💰', label: '卖出', value: `${s.count} 单 · ${Math.round(s.gold ?? 0)} 金币` })
  if (chattedWith.length) rows.push({ icon: '💬', label: '聊过', value: chattedWith.slice(0, 4).join('、') + (chattedWith.length > 4 ? ` 等 ${chattedWith.length} 人` : '') })
  for (const t of eventTexts.slice(-3)) rows.push({ icon: '✨', label: '', value: t })
  return rows
}

/**
 * 导播分镜（主播 11-21：视角太高，离人物近一点；只有多人入镜等必要时才拉远）。
 * 单人情境 → 特写；对话 → 框住所有参与者；上课 → 中景（主角 + 附近两三个同学）；全景 → 整图。
 */
export const CAM = { closeDefault: 2.0, closeMin: 1.0, closeMax: 3.0, midRatio: 0.6, margin: 0.15 }
export type FrameKind = 'close' | 'group' | 'pan'
export function frameFor(situation: string, targetId: string | null, groupIds: string[]): { kind: FrameKind; ids: string[] } {
  if (!targetId || situation === 'panorama') return { kind: 'pan', ids: [] }
  const ids = [targetId, ...groupIds.filter(id => id !== targetId)]
  if ((situation === 'chat' || situation === 'class') && ids.length > 1) return { kind: 'group', ids }
  return { kind: 'close', ids: [targetId] }
}
/** 上课的同框同学：同一节课、离主角最近的 3 个（没有课号时取 4 格内的人） */
export function classmates(target: { id: string; position: { x: number; y: number }; lesson?: { lesson_id?: string } | null }, players: { id: string; position: { x: number; y: number }; lesson?: { lesson_id?: string } | null; online?: boolean }[], n = 3): string[] {
  const lid = target.lesson?.lesson_id
  const d = (p: { position: { x: number; y: number } }) => Math.abs(p.position.x - target.position.x) + Math.abs(p.position.y - target.position.y)
  return players.filter(p => p.id !== target.id && p.online !== false && (lid ? p.lesson?.lesson_id === lid : d(p) <= 4)).sort((a, b) => d(a) - d(b)).slice(0, n).map(p => p.id)
}
export const clampClose = (z: number) => Math.min(CAM.closeMax, Math.max(CAM.closeMin, Math.round(z * 4) / 4))
