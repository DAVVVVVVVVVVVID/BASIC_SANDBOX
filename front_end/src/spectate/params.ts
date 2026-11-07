/** `/spectate?follow=<name|id|agent_id>&hud=0&clock=1&zoom=0.667&bg=transparent&stats=1&bars=target` */
export interface SpectateParams {
  follow: string | null
  hud: boolean          // React 面板（默认 1；OBS 用 0）
  clock: boolean        // 画布内时钟（默认 = !hud：OBS 的 hud=0 时画在画布里；hud=1 时由 React 面板显示）
  zoom: number | null   // 跟随镜头 zoom（默认 2/3 → 64 px/格 = 4× 源像素）
  panzoom: number | null // 全景 zoom（默认按地图自动，吸附到 1/6 的整数倍）
  bg: 'dark' | 'transparent'
  stats: boolean        // 画布内帧率
  bars: 'target' | 'all' | 'none'
  /** 直播画面里被 Live2D 等占住的角（如 br=右下），叠加层避开它 */
  safe: 'br' | 'bl' | 'tr' | 'tl' | null
  /** 思考字幕（E8），默认开；C 的 8002 没起时静默 */
  thought: boolean
  /** 画布内基础信息面板（主播反馈：像游戏一样专门放基础信息），默认开 */
  panel: boolean
  /** W9：QQ 面板（跟随目标的手机，只读；layout=live 收成图标） */
  qq: boolean
  /** 形象版本：v1 按 persona 文字（默认，主播 11-06 选定）/ v2 按立绘 */
  art: 'v1' | 'v2'
  /** OBS 布局预设（E16）：live = 右下留 Live2D 安全区、面板左下、字幕底中；full = 全屏无保留 */
  layout: 'live' | 'full' | null
  /** 多镇（E14）：town 名 → 代理前缀 /t/<town>/api；缺省主镇 */
  town: string | null
  /** 取景（W7）：follow = 进屋推近 + 屋外压暗（默认）；world = 一直看整个世界 */
  scene: 'follow' | 'world'
  /** 不跟人、直接取景到某个 sector（评审截图用）：`&focus=achan_house` 或 `&focus=achan_house:2`（楼层） */
  focus: { sector: string; floor: number } | null
  /** W9 任务 0（主播 11-07 晚）：free = 自由镜头（拖动 / WASD / 滚轮 / 点建筑进屋 / 点人跟随）；follow = 跟随 follow= 的人；world = 全景。缺省：有 follow 则 follow，否则 world */
  mode: 'free' | 'follow' | 'world'
  /** W9 0c（总控 11-07 晚）：`&debug=walls` 把引擎的墙格 / 门与楼梯格 / arena 边界 / 格线半透明叠在底图上，核对底图与引擎的错位 */
  debug: 'walls' | null
}

export function parseSpectateParams(search = window.location.search): SpectateParams {
  const q = new URLSearchParams(search)
  const flag = (k: string, def: boolean) => {
    const v = q.get(k)
    if (v === null) return def
    return !(v === '0' || v === 'false' || v === 'no')
  }
  const num = (k: string) => { const v = q.get(k); return v !== null && !Number.isNaN(Number(v)) && Number(v) > 0 ? Number(v) : null }
  const zoom = num('zoom')
  const panzoom = num('panzoom')
  const bars = q.get('bars')
  const layout = q.get('layout') === 'live' ? 'live' : q.get('layout') === 'full' ? 'full' : null
  // layout 预设展开为具体参数；显式给出的参数优先
  const safeRaw = q.get('safe') ?? (layout === 'live' ? 'br' : null)
  const safe = safeRaw
  const townRaw = q.get('town')
  const town = townRaw && /^[a-z0-9_-]{1,32}$/i.test(townRaw) && townRaw !== 'main' ? townRaw : null
  return {
    follow: q.get('follow') || null,
    hud:    flag('hud', true),
    clock:  flag('clock', !flag('hud', true)),
    zoom,
    panzoom,
    bg:     q.get('bg') === 'transparent' ? 'transparent' : 'dark',
    stats:  flag('stats', false),
    bars:   bars === 'all' || bars === 'none' ? bars : 'target',
    safe:   safe === 'br' || safe === 'bl' || safe === 'tr' || safe === 'tl' ? safe : null,
    thought: flag('thought', true),
    panel:  flag('panel', true),
    qq:     flag('qq', true),
    art:    q.get('art') === 'v2' ? 'v2' : 'v1',
    layout,
    town,
    scene:  q.get('scene') === 'world' ? 'world' : 'follow',
    focus:  (() => { const f = q.get('focus'); if (!f) return null; const [sector, fl] = f.split(':'); return /^[\w-]+$/.test(sector) ? { sector, floor: Number(fl) || 1 } : null })(),
    debug:  q.get('debug') === 'walls' ? 'walls' : null,
    mode:   (() => { const m = q.get('mode'); if (m === 'free' || m === 'follow' || m === 'world') return m; return q.get('follow') ? 'follow' : 'world' })(),
  }
}

export function isSpectateRoute(pathname = window.location.pathname): boolean {
  return /^\/spectate\/?$/.test(pathname)
}
