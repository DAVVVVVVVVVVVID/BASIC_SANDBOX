/**
 * 小镇导播 BGM（whale-ec 11-21 主播拍板）：读 bgm/manifest.json（tools/sync_bgm.py 生成），按游戏时间分组随机不重复轮播，曲间交叉淡入淡出。
 * 纯函数（分组 / 抽歌 / 署名）单测 tests/director.test.ts；BgmPlayer 类管两个 <audio>。
 */
export interface BgmTrack { id: string; src: string; title: string; author: string; license: string; group: 'day' | 'night' | 'sleep'; kind: 'cc' | 'instrumental' }
export type BgmGroup = BgmTrack['group']

/** 06:00–17:00 白天轻快；其余傍晚 / 夜里安静；镜头在睡觉的人身上 → sleep（没有 sleep 组时退回 night，音量另压） */
export function groupFor(time: string | null | undefined, sleeping: boolean): BgmGroup {
  if (sleeping) return 'sleep'
  const h = Number(String(time ?? '').slice(0, 2))
  return Number.isFinite(h) && h >= 6 && h < 17 ? 'day' : 'night'
}
export function poolFor(tracks: BgmTrack[], g: BgmGroup): BgmTrack[] {
  const p = tracks.filter(t => t.group === g)
  if (p.length) return p
  if (g === 'sleep') return tracks.filter(t => t.group === 'night')
  return tracks
}
/** 同组一轮放完才重复（played 记本轮放过的 id）；rand 注入便于测试 */
export function pickNext(pool: BgmTrack[], played: Set<string>, lastId: string | null, rand: () => number = Math.random): BgmTrack | null {
  if (!pool.length) return null
  let left = pool.filter(t => !played.has(t.id))
  if (!left.length) { played.clear(); left = pool.filter(t => t.id !== lastId); if (!left.length) left = pool }
  const t = left[Math.floor(rand() * left.length) % left.length]
  played.add(t.id)
  return t
}
export function creditText(t: BgmTrack): string {
  const by = t.author.replace(/\s*\(.*?\)\s*/g, ' ').trim()
  if (t.kind === 'instrumental') return `♪ ${t.title}（伴奏）${by ? `· ${by}` : ''}`
  return `♪ ${t.title}${by ? ` — ${by}` : ''}${t.license ? ` · ${t.license}` : ''}`
}

const FADE_MS = 3000

/** 两个 audio 交替；换曲时交叉淡入淡出；音量 = 主音量 × 情境系数（睡觉 0.5） */
export class BgmPlayer {
  private els: HTMLAudioElement[]
  private cur = 0
  private tracks: BgmTrack[] = []
  private played = new Map<BgmGroup, Set<string>>()
  private lastId: string | null = null
  private group: BgmGroup = 'day'
  private master = 0.35
  private duck = 1
  private fade: { from: number; start: number } | null = null
  private timer: number | null = null
  current: BgmTrack | null = null
  /** 联调：两路当前音量与曲名 */
  debug() { return this.els.map(e => ({ vol: Math.round(e.volume * 100) / 100, paused: e.paused, src: e.getAttribute('src') })) }
  blocked = false
  onChange: () => void = () => {}

  constructor() {
    this.els = [new Audio(), new Audio()]
    for (const e of this.els) { e.preload = 'auto'; e.volume = 0 }
  }
  setTracks(t: BgmTrack[]) { this.tracks = t }
  setMaster(v: number) { this.master = Math.max(0, Math.min(1, v)); this.applyVolume() }
  setContext(g: BgmGroup) {
    this.duck = g === 'sleep' ? 0.5 : 1
    this.group = g
    this.applyVolume()
  }
  /** 开始 / 恢复（需要用户手势时由「开声音」按钮调） */
  start() {
    if (!this.current) this.next()
    else void this.els[this.cur].play().then(() => { this.blocked = false; this.onChange() }).catch(() => { this.blocked = true; this.onChange() })
    if (this.timer === null) this.timer = window.setInterval(() => this.tick(), 200)
  }
  stop() {
    if (this.timer !== null) window.clearInterval(this.timer)
    this.timer = null
    for (const e of this.els) { e.pause(); e.removeAttribute('src') }
  }
  /** 换下一首：新曲在另一路从 0 淡入，旧曲淡出 */
  next() {
    let set = this.played.get(this.group)
    if (!set) { set = new Set(); this.played.set(this.group, set) }
    const t = pickNext(poolFor(this.tracks, this.group), set, this.lastId)
    if (!t) return
    const old = this.els[this.cur]
    this.cur = 1 - this.cur
    const el = this.els[this.cur]
    el.src = t.src; el.currentTime = 0; el.volume = 0
    this.current = t; this.lastId = t.id
    this.fade = { from: this.current ? old.volume : 0, start: performance.now() }
    void el.play().then(() => { this.blocked = false; this.onChange() }).catch(() => { this.blocked = true; this.onChange() })
    this.onChange()
  }
  private target() { return this.master * this.duck }
  private applyVolume() { if (!this.fade) this.els[this.cur].volume = this.target() }
  private tick() {
    const el = this.els[this.cur], old = this.els[1 - this.cur]
    if (this.fade) {
      const k = Math.min(1, (performance.now() - this.fade.start) / FADE_MS)
      el.volume = this.target() * k
      old.volume = Math.max(0, this.fade.from * (1 - k))
      if (k >= 1) { this.fade = null; old.pause() }
    } else el.volume = this.target()
    // 剩 3 s 开始换下一首（交叉淡）；出错 / 放完也换
    if (!this.blocked && this.current && (el.ended || el.error || (el.duration > 0 && el.duration - el.currentTime < FADE_MS / 1000))) this.next()
  }
}
